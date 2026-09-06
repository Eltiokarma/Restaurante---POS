"""Bebidas embotelladas (gaseosas) y traslado de pedidos entre mesas."""
from app.db import SessionLocal


def _crear_orden(client, menu_ejemplo, **extra):
    payload = {"items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}]}
    payload.update(extra)
    r = client.post("/api/orders", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["orden"]


def _crear_bebida(client, admin_headers, nombre="Inca Kola 500 ml", precio=3.5):
    r = client.post("/api/bebidas", json={"nombre": nombre, "precio": precio},
                    headers=admin_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _crear_mesas(db, *nombres):
    from app.models import Mesa

    mesas = [Mesa(nombre=n) for n in nombres]
    db.add_all(mesas)
    db.commit()
    return {m.nombre: m.id for m in mesas}


# ---------- Lista fija de bebidas ----------

def test_crud_de_bebidas_y_kardex_ligado(client, admin_headers, db):
    bebida = _crear_bebida(client, admin_headers)
    assert bebida["precio"] == 3.5
    # El insumo del kardex se crea solo, en "unidad"
    from app.models import Insumo

    insumo = db.get(Insumo, bebida["insumo_id"])
    assert insumo is not None and insumo.unidad == "unidad"

    # Repetida → 409; editar precio y apagar
    assert client.post("/api/bebidas", json={"nombre": "inca kola 500 ml", "precio": 4},
                       headers=admin_headers).status_code == 409
    r = client.patch(f"/api/bebidas/{bebida['id']}", json={"precio": 4.0, "activa": False},
                     headers=admin_headers)
    assert r.json()["precio"] == 4.0 and r.json()["activa"] is False

    publica = client.get("/api/bebidas").json()["bebidas"]
    assert len(publica) == 1

    assert client.delete(f"/api/bebidas/{bebida['id']}", headers=admin_headers).json()["borrada"]
    assert client.get("/api/bebidas").json()["bebidas"] == []


def test_crear_bebida_requiere_admin(client):
    assert client.post("/api/bebidas", json={"nombre": "X", "precio": 1}).status_code in (401, 403)


# ---------- Agregar gaseosas a una orden ----------

def test_agregar_gaseosas_suma_total_kardex_y_ticket_chico(client, admin_headers, menu_ejemplo, db):
    bebida = _crear_bebida(client, admin_headers)
    orden = _crear_orden(client, menu_ejemplo)
    total_antes = orden["total"]

    r = client.post(f"/api/orders/{orden['id']}/bebidas",
                    json={"items": [{"bebida_id": bebida["id"], "cantidad": 2}]})
    assert r.status_code == 200, r.text
    data = r.json()

    # Total: backend autoridad; item nace entregado y es_cargo (cocina no lo ve)
    assert data["orden"]["total"] == round(total_antes + 7.0, 2)
    gaseosas = [i for i in data["orden"]["items"] if i["nombre"] == "Inca Kola 500 ml"]
    assert len(gaseosas) == 1
    assert gaseosas[0]["es_cargo"] is True and gaseosas[0]["estado"] == "entregado"
    # El ticket chico trae solo las gaseosas
    assert data["ticket_bebida"]["total"] == 7.0
    assert data["ticket_bebida"]["items"][0]["cantidad"] == 2

    # Kardex: 2 botellas menos, ligadas a la orden
    from app.models import Insumo

    insumo = db.get(Insumo, bebida["insumo_id"])
    assert insumo.stock_actual == -2.0

    # Anular la orden devuelve las botellas (neteo por orden)
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})
    db.expire_all()
    assert db.get(Insumo, bebida["insumo_id"]).stock_actual == 0.0


def test_gaseosa_inactiva_o_orden_anulada_se_rechazan(client, admin_headers, menu_ejemplo):
    bebida = _crear_bebida(client, admin_headers)
    client.patch(f"/api/bebidas/{bebida['id']}", json={"activa": False}, headers=admin_headers)
    orden = _crear_orden(client, menu_ejemplo)
    r = client.post(f"/api/orders/{orden['id']}/bebidas",
                    json={"items": [{"bebida_id": bebida["id"], "cantidad": 1}]})
    assert r.status_code == 422

    client.patch(f"/api/bebidas/{bebida['id']}", json={"activa": True}, headers=admin_headers)
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})
    r = client.post(f"/api/orders/{orden['id']}/bebidas",
                    json={"items": [{"bebida_id": bebida["id"], "cantidad": 1}]})
    assert r.status_code == 409


def test_ticket_de_gaseosa_espera_en_cola_en_modo_puente(client, admin_headers, menu_ejemplo, db):
    from app.models import Config

    db.add(Config(clave="modo_impresion", valor="puente"))
    db.commit()
    bebida = _crear_bebida(client, admin_headers)
    orden = _crear_orden(client, menu_ejemplo)
    client.post(f"/api/orders/{orden['id']}/bebidas",
                json={"items": [{"bebida_id": bebida["id"], "cantidad": 1}]})

    cola = client.get("/api/print/cola").json()
    de_bebida = [t for t in cola["trabajos"] if t["tipo"] == "bebida"]
    assert len(de_bebida) == 1 and de_bebida[0]["datos_b64"]

    # Confirmada → sale de la cola (y de la de la estación HTML)
    client.post(f"/api/print/bebida/{de_bebida[0]['ticket_bebida_id']}/impresa")
    cola2 = client.get("/api/print/cola").json()
    assert [t for t in cola2["trabajos"] if t["tipo"] == "bebida"] == []
    assert client.get("/api/orders/pending-print").json()["tickets_bebida"] == []


def test_modo_terminal_no_encola_el_ticket_de_gaseosa(client, admin_headers, menu_ejemplo):
    # Sin config → modo terminal (default): la caja imprime con la respuesta
    bebida = _crear_bebida(client, admin_headers)
    orden = _crear_orden(client, menu_ejemplo)
    r = client.post(f"/api/orders/{orden['id']}/bebidas",
                    json={"items": [{"bebida_id": bebida["id"], "cantidad": 3}]})
    assert r.json()["modo_impresion"] == "terminal"
    assert client.get("/api/orders/pending-print").json()["tickets_bebida"] == []


# ---------- Traslado de mesa ----------

def test_trasladar_mesa_mueve_todos_los_pedidos(client, menu_ejemplo, db):
    mesas = _crear_mesas(db, "Mesa 2", "Mesa 5")
    o1 = _crear_orden(client, menu_ejemplo, mesa_ids=[mesas["Mesa 2"]])
    o2 = _crear_orden(client, menu_ejemplo, mesa_ids=[mesas["Mesa 2"]])
    o3 = _crear_orden(client, menu_ejemplo)  # sin mesa: no se toca

    r = client.post("/api/orders/trasladar-mesa",
                    json={"de_mesa_id": mesas["Mesa 2"], "a_mesa_id": mesas["Mesa 5"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["trasladadas"] == 2
    assert all(o["mesa_ids"] == [mesas["Mesa 5"]] for o in data["ordenes"])
    assert {o["id"] for o in data["ordenes"]} == {o1["id"], o2["id"]}

    # La mesa 2 quedó libre; la 5 ocupada
    estado = {m["nombre"]: m["ocupada"] for m in client.get("/api/mesas").json()["mesas"]}
    assert estado == {"Mesa 2": False, "Mesa 5": True}
    assert o3["id"] not in {o["id"] for o in data["ordenes"]}


def test_trasladar_mesa_combinada_solo_reemplaza_la_de_origen(client, menu_ejemplo, db):
    mesas = _crear_mesas(db, "M1", "M2", "M3")
    orden = _crear_orden(client, menu_ejemplo, mesa_ids=[mesas["M1"], mesas["M2"]])
    r = client.post("/api/orders/trasladar-mesa",
                    json={"de_mesa_id": mesas["M1"], "a_mesa_id": mesas["M3"]})
    movida = next(o for o in r.json()["ordenes"] if o["id"] == orden["id"])
    assert movida["mesa_ids"] == [mesas["M3"], mesas["M2"]]


def test_trasladar_mesa_valida_y_reimprime_si_se_pide(client, menu_ejemplo, db):
    mesas = _crear_mesas(db, "A", "B")
    # Mesa sin pedidos → 409; misma mesa → 422
    assert client.post("/api/orders/trasladar-mesa",
                       json={"de_mesa_id": mesas["A"], "a_mesa_id": mesas["B"]}).status_code == 409
    assert client.post("/api/orders/trasladar-mesa",
                       json={"de_mesa_id": mesas["A"], "a_mesa_id": mesas["A"]}).status_code == 422

    orden = _crear_orden(client, menu_ejemplo, mesa_ids=[mesas["A"]])
    client.post(f"/api/orders/{orden['id']}/printed")
    client.post("/api/orders/trasladar-mesa",
                json={"de_mesa_id": mesas["A"], "a_mesa_id": mesas["B"], "reimprimir": True})
    pendientes = client.get("/api/orders/pending-print").json()["ordenes"]
    assert [o["id"] for o in pendientes] == [orden["id"]]
