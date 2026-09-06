"""Tandas de cocina (sesión 3): partición, gating por tiempos, capacidad
por plato, acciones empezar/salió y tanda_logs."""
from datetime import datetime, timedelta

from app.models import LIMA, Plato, hoy_lima


def _platos(db):
    platos = [
        Plato(nombre="Sopa criolla", categoria="entrada", precio=6.0, activo_hoy=True,
              en_catalogo=True, ultima_vez_activo=hoy_lima()),
        Plato(nombre="Chuleta frita", categoria="fondo", precio=15.0, activo_hoy=True,
              en_catalogo=True, sale_al_momento=True, capacidad_tanda=6,
              ultima_vez_activo=hoy_lima()),
        Plato(nombre="Ají de gallina", categoria="fondo", precio=13.0, activo_hoy=True,
              en_catalogo=True, ultima_vez_activo=hoy_lima()),
        Plato(nombre="Chicha morada", categoria="bebida", precio=3.0, activo_hoy=True,
              en_catalogo=True, ultima_vez_activo=hoy_lima()),
    ]
    db.add_all(platos)
    db.commit()
    return {p.nombre: p.id for p in platos}


def _orden(client, items, entrega="junto", hora=None):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": pid, "cantidad": c} for pid, c in items],
        "entrega": entrega,
    })
    assert r.status_code == 201, r.text
    orden = r.json()["orden"]
    if hora is not None:
        # Los tests controlan la hora de llegada para probar la ventana
        from app.db import SessionLocal
        from app.models import Orden

        db = SessionLocal()
        db.get(Orden, orden["id"]).hora = hora
        db.commit()
        db.close()
    return orden


def _hora(minutos_atras: int) -> str:
    # En hora de Lima, como el backend (el contenedor corre en UTC)
    return (datetime.now(LIMA) - timedelta(minutes=minutos_atras)).strftime("%H:%M:%S")


def test_particion_por_ventana_y_tope(client, db):
    ids = _platos(db)
    # Ventana de 10 min y tope de 4 (defaults): tres órdenes juntas y una tardía
    o1 = _orden(client, [(ids["Ají de gallina"], 1)], hora=_hora(20))
    o2 = _orden(client, [(ids["Ají de gallina"], 2)], hora=_hora(18))
    o3 = _orden(client, [(ids["Chuleta frita"], 1)], entrega="separado", hora=_hora(15))
    o4 = _orden(client, [(ids["Ají de gallina"], 1)], hora=_hora(2))

    data = client.get("/api/orders/tandas").json()
    assert data["habilitado"] is True
    assert len(data["tandas"]) == 2
    t1, t2 = data["tandas"]
    assert t1["orden_ids"] == [o1["id"], o2["id"], o3["id"]]
    assert t2["orden_ids"] == [o4["id"]]
    # Espera de la más antigua, en minutos
    assert t1["espera_min"] >= 19
    # Al momento primero: la chuleta manda la duración
    assert t1["platos"][0]["nombre"] == "Chuleta frita"
    assert t1["platos"][0]["al_momento"] is True
    aji = next(p for p in t1["platos"] if p["nombre"] == "Ají de gallina")
    assert aji["cantidad"] == 3


def test_tope_de_tickets_cierra_la_tanda(client, db, admin_headers):
    ids = _platos(db)
    client.put("/api/config", json={"cocina_tanda_max_tickets": 2}, headers=admin_headers)
    for _ in range(3):
        _orden(client, [(ids["Ají de gallina"], 1)], hora=_hora(5))
    data = client.get("/api/orders/tandas").json()
    assert [len(t["orden_ids"]) for t in data["tandas"]] == [2, 1]


def test_gating_separado_y_bebidas_fuera(client, db):
    ids = _platos(db)
    # Separado: la sopa entra, el fondo espera; la chicha no va a cocina
    orden = _orden(
        client,
        [(ids["Sopa criolla"], 1), (ids["Ají de gallina"], 1), (ids["Chicha morada"], 1)],
        entrega="separado",
    )
    data = client.get("/api/orders/tandas").json()
    t1 = data["tandas"][0]
    assert [p["nombre"] for p in t1["platos"]] == ["Sopa criolla"]
    assert t1["esperando"] == [{"numero": f"{orden['numero_orden_dia']:03d}",
                               "platos": ["1× Ají de gallina"]}]

    # La sopa sale → el ají entra a la tanda en el siguiente cálculo
    client.post("/api/orders/tandas/salio", json={"orden_ids": [orden["id"]]})
    data = client.get("/api/orders/tandas").json()
    t1 = data["tandas"][0]
    assert [p["nombre"] for p in t1["platos"]] == ["Ají de gallina"]
    assert t1["esperando"] == []


def test_capacidad_parte_la_tanda(client, db):
    ids = _platos(db)
    _orden(client, [(ids["Chuleta frita"], 9)], entrega="separado")
    data = client.get("/api/orders/tandas").json()
    chuleta = data["tandas"][0]["platos"][0]
    assert chuleta["cantidad"] == 9
    assert chuleta["partes"] == [6, 3]


def test_empezar_y_salio_con_log(client, db):
    from app.models import TandaLog

    ids = _platos(db)
    o1 = _orden(client, [(ids["Ají de gallina"], 2)])
    o2 = _orden(client, [(ids["Chuleta frita"], 1)], entrega="separado")

    r = client.post("/api/orders/tandas/empezar", json={"orden_ids": [o1["id"], o2["id"]]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert all(o["estado"] == "preparando" for o in data["ordenes"])
    log_id = data["log_id"]

    data = client.get("/api/orders/tandas").json()
    assert data["tandas"][0]["empezada"] is True

    r = client.post("/api/orders/tandas/salio",
                    json={"orden_ids": [o1["id"], o2["id"]], "log_id": log_id})
    assert all(o["estado"] == "listo" for o in r.json()["ordenes"])
    assert client.get("/api/orders/tandas").json()["tandas"] == []

    log = db.get(TandaLog, log_id)
    assert log.hora_inicio is not None and log.hora_listo is not None
    assert "Chuleta frita" in log.composicion_json


def test_salio_avisa_del_segundo_gateado_sin_bloquear(client, db):
    ids = _platos(db)
    orden = _orden(client, [(ids["Sopa criolla"], 1), (ids["Ají de gallina"], 1)],
                   entrega="separado")
    r = client.post("/api/orders/tandas/salio", json={"orden_ids": [orden["id"]]})
    data = r.json()
    # La sopa salió; el aviso informa que el segundo espera (no bloquea)
    assert any("esperando su entrada" in a for a in data["avisos"])
    estados = {i["nombre"]: i["estado"] for i in data["ordenes"][0]["items"]}
    assert estados["Sopa criolla"] == "listo"
    assert estados["Ají de gallina"] == "pendiente"


def test_toggle_apaga_el_tablero(client, db, admin_headers):
    ids = _platos(db)
    _orden(client, [(ids["Ají de gallina"], 1)])
    client.put("/api/config", json={"cocina_tandas": False}, headers=admin_headers)
    data = client.get("/api/orders/tandas").json()
    assert data["habilitado"] is False and data["tandas"] == []


def test_capacidad_tanda_editable_en_el_menu(client, db, admin_headers):
    ids = _platos(db)
    r = client.put("/api/menu/today", json={"platos": [{
        "id": ids["Chuleta frita"], "nombre": "Chuleta frita", "categoria": "fondo",
        "precio": 15.0, "activo_hoy": True, "sale_al_momento": True,
        "capacidad_tanda": 4,
    }]}, headers=admin_headers)
    assert r.status_code == 200, r.text
    chuleta = next(p for p in r.json()["platos"] if p["nombre"] == "Chuleta frita")
    assert chuleta["capacidad_tanda"] == 4


# ---------- Métricas y estimado de tiempo de servido ----------

def test_servido_se_registra_y_alimenta_el_estimado(client, db):
    ids = _platos(db)
    # Un ticket ya servido (pedido hace 12 min) fija el promedio del día
    previa = _orden(client, [(ids["Ají de gallina"], 1)], hora=_hora(12))
    client.post("/api/orders/tandas/salio", json={"orden_ids": [previa["id"]]})

    from app.models import Orden

    db.expire_all()
    servida = db.get(Orden, previa["id"])
    assert servida.listo_en is not None  # métrica registrada en la BD

    # servido_min viaja en la API (~12 min)
    ordenes = client.get("/api/orders/today").json()["ordenes"]
    servido = next(o["servido_min"] for o in ordenes if o["id"] == previa["id"])
    assert 11 <= servido <= 13

    # Un ticket nuevo con 4 min esperando: estimado ≈ promedio − espera ≈ 8
    _orden(client, [(ids["Chuleta frita"], 1)], entrega="separado", hora=_hora(4))
    data = client.get("/api/orders/tandas").json()
    assert data["metricas"]["servidas"] == 1
    assert 11 <= data["metricas"]["promedio_min"] <= 13
    assert 7 <= data["tandas"][0]["estimado_min"] <= 9


def test_sin_historia_no_hay_estimado(client, db):
    ids = _platos(db)
    _orden(client, [(ids["Ají de gallina"], 1)])
    data = client.get("/api/orders/tandas").json()
    assert data["metricas"] == {"servidas": 0, "promedio_min": None}
    assert data["tandas"][0]["estimado_min"] is None


def test_avanzar_ticket_suelto_tambien_sella_el_servido(client, db):
    ids = _platos(db)
    orden = _orden(client, [(ids["Ají de gallina"], 1)], hora=_hora(7))
    # La cocina atiende el ticket por separado (tarjeta de abajo)
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "listo"})
    ordenes = client.get("/api/orders/today").json()["ordenes"]
    servido = next(o["servido_min"] for o in ordenes if o["id"] == orden["id"])
    assert 6 <= servido <= 8
    # Y desaparece de las tandas (se atendió aparte)
    assert client.get("/api/orders/tandas").json()["tandas"] == []


def test_log_sin_empezar_arranca_en_la_orden_mas_antigua(client, db):
    from app.models import TandaLog

    ids = _platos(db)
    orden = _orden(client, [(ids["Ají de gallina"], 1)], hora=_hora(10))
    r = client.post("/api/orders/tandas/salio", json={"orden_ids": [orden["id"]]})
    log = db.get(TandaLog, r.json()["log_id"])
    # hora_inicio = hora del pedido (no el momento del toque): el log mide
    # el tiempo de servido real
    assert log.hora_inicio == _hora(10)[:5] + log.hora_inicio[5:]  # mismo HH:MM
    assert log.hora_listo is not None
