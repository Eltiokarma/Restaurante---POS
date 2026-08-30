"""Lo esencial para abrir el local: empezar limpio, aviso de impresión
detenida y alertas de stock mínimo."""
from app.models import Config, Insumo, RecetaItem


def crear_orden(client, menu_ejemplo, nombre="Lomo saltado"):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo[nombre], "cantidad": 1}],
    })
    assert r.status_code == 201
    return r.json()["orden"]


# ---------- Empezar limpio ----------


def test_reiniciar_requiere_admin_y_confirmacion(client, admin_headers, menu_ejemplo):
    crear_orden(client, menu_ejemplo)
    assert client.post("/api/mantenimiento/reiniciar",
                       json={"confirmacion": "BORRAR"}).status_code == 401

    r = client.post("/api/mantenimiento/reiniciar",
                    json={"confirmacion": "si"}, headers=admin_headers)
    assert r.status_code == 422
    assert "BORRAR" in r.json()["detail"]
    # Nada se borró con la confirmación equivocada
    assert client.get("/api/mantenimiento/datos", headers=admin_headers).json()["ordenes"] == 1


def test_reiniciar_borra_movimiento_y_conserva_configuracion(
    client, admin_headers, db, menu_ejemplo,
):
    insumo = Insumo(nombre="Carne", unidad="kg", stock_actual=8.0, costo_unitario=20.0)
    db.add(insumo)
    db.flush()
    db.add(RecetaItem(plato_id=menu_ejemplo["Lomo saltado"], insumo_id=insumo.id, cantidad=0.2))
    db.commit()

    client.post("/api/caja/abrir", json={"monto_apertura": 50})
    crear_orden(client, menu_ejemplo)
    client.post("/api/cancellations", json={
        "items": [{"nombre": "Lomo saltado", "precio": 15.0, "cantidad": 1}], "total": 15.0,
    })

    antes = client.get("/api/mantenimiento/datos", headers=admin_headers).json()
    assert antes["ordenes"] == 1 and antes["cancelaciones"] == 1
    assert antes["cierres_caja"] == 1 and antes["movimientos_kardex"] > 0

    r = client.post("/api/mantenimiento/reiniciar",
                    json={"confirmacion": "borrar"},  # sin importar mayúsculas
                    headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["borrado"]["ordenes"] == 1

    # Se borró TODO el movimiento
    despues = client.get("/api/mantenimiento/datos", headers=admin_headers).json()
    assert despues == {"ordenes": 0, "cancelaciones": 0, "cierres_caja": 0,
                       "movimientos_kardex": 0, "voz_logs": 0}
    assert client.get("/api/orders/today").json()["ordenes"] == []
    assert client.get("/api/caja/hoy").json()["abierta"] is False
    assert client.get("/api/stats/today", headers=admin_headers).json()["total_vendido"] == 0

    # Se conservó lo que costó configurar
    assert len(client.get("/api/menu/today").json()["platos"]) == 2
    insumos = client.get("/api/insumos", headers=admin_headers).json()["insumos"]
    assert [i["nombre"] for i in insumos] == ["Carne"]
    assert insumos[0]["stock_actual"] == 0.0  # sin kardex, se parte de cero
    assert client.get(
        f"/api/insumos/recetas/{menu_ejemplo['Lomo saltado']}", headers=admin_headers
    ).json()["items"] != []


def test_reiniciar_puede_conservar_el_stock(client, admin_headers, db):
    db.add(Insumo(nombre="Arroz", unidad="kg", stock_actual=12.0))
    db.commit()
    client.post("/api/mantenimiento/reiniciar",
                json={"confirmacion": "BORRAR", "reiniciar_stock": False},
                headers=admin_headers)
    insumos = client.get("/api/insumos", headers=admin_headers).json()["insumos"]
    assert insumos[0]["stock_actual"] == 12.0


def test_el_correlativo_arranca_de_uno_tras_reiniciar(client, admin_headers, menu_ejemplo):
    crear_orden(client, menu_ejemplo)
    crear_orden(client, menu_ejemplo)
    client.post("/api/mantenimiento/reiniciar",
                json={"confirmacion": "BORRAR"}, headers=admin_headers)
    assert crear_orden(client, menu_ejemplo)["numero_orden_dia"] == 1


# ---------- Aviso de tickets sin imprimir ----------


def test_sin_aviso_en_modo_terminal(client, menu_ejemplo):
    crear_orden(client, menu_ejemplo)  # modo terminal: nace impresa
    assert client.get("/api/orders/today").json()["impresion_pendiente"] == {
        "cantidad": 0, "minutos": 0.0,
    }


def test_aviso_cuenta_los_tickets_atascados(client, db, menu_ejemplo):
    db.add(Config(clave="modo_impresion", valor="puente"))
    db.commit()

    crear_orden(client, menu_ejemplo)
    orden2 = crear_orden(client, menu_ejemplo)
    aviso = client.get("/api/orders/today").json()["impresion_pendiente"]
    assert aviso["cantidad"] == 2 and aviso["minutos"] >= 0

    # Al imprimirse una, baja el contador
    client.post(f"/api/orders/{orden2['id']}/printed")
    assert client.get("/api/orders/today").json()["impresion_pendiente"]["cantidad"] == 1


def test_una_anulada_no_cuenta_como_atascada(client, db, menu_ejemplo):
    db.add(Config(clave="modo_impresion", valor="estacion"))
    db.commit()
    orden = crear_orden(client, menu_ejemplo)
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})
    assert client.get("/api/orders/today").json()["impresion_pendiente"]["cantidad"] == 0


def test_el_historial_de_otro_dia_no_avisa(client, db, menu_ejemplo):
    from datetime import timedelta

    from app.models import hoy_lima

    db.add(Config(clave="modo_impresion", valor="puente"))
    db.commit()
    crear_orden(client, menu_ejemplo)
    ayer = (hoy_lima() - timedelta(days=1)).isoformat()
    # Mirar el movimiento de otro día no debe disparar el cintillo de hoy
    assert client.get(f"/api/orders/of-day?fecha={ayer}").json()[
        "impresion_pendiente"] == {"cantidad": 0, "minutos": 0.0}


# ---------- Alertas de stock mínimo ----------


def test_insumo_avisa_cuando_baja_del_minimo(client, admin_headers, db):
    r = client.post("/api/insumos", json={
        "nombre": "Pollo", "unidad": "kg", "costo_unitario": 12.0, "stock_minimo": 3.0,
    }, headers=admin_headers)
    insumo_id = r.json()["id"]
    assert r.json()["stock_minimo"] == 3.0 and r.json()["bajo_minimo"] is True

    # Compra que lo deja por encima del mínimo: sin aviso
    client.post(f"/api/insumos/{insumo_id}/movimientos", json={
        "tipo": "compra", "cantidad": 10.0, "costo_total": 120.0,
    }, headers=admin_headers)
    datos = client.get("/api/insumos", headers=admin_headers).json()
    assert datos["insumos"][0]["bajo_minimo"] is False and datos["por_agotarse"] == []

    # Merma que lo deja justo en el mínimo: avisa (<=)
    client.post(f"/api/insumos/{insumo_id}/movimientos", json={
        "tipo": "merma", "cantidad": 7.0,
    }, headers=admin_headers)
    datos = client.get("/api/insumos", headers=admin_headers).json()
    assert datos["insumos"][0]["bajo_minimo"] is True
    assert datos["por_agotarse"] == ["Pollo"]


def test_sin_minimo_configurado_nunca_avisa(client, admin_headers, db):
    db.add(Insumo(nombre="Sal", unidad="kg", stock_actual=0.0))
    db.commit()
    datos = client.get("/api/insumos", headers=admin_headers).json()
    assert datos["insumos"][0]["bajo_minimo"] is False
    assert datos["por_agotarse"] == []


def test_insumo_inactivo_no_avisa(client, admin_headers, db):
    insumo = Insumo(nombre="Ají", unidad="kg", stock_actual=0.0, stock_minimo=2.0)
    db.add(insumo)
    db.commit()
    client.put(f"/api/insumos/{insumo.id}", json={"activo": False}, headers=admin_headers)
    assert client.get("/api/insumos", headers=admin_headers).json()["por_agotarse"] == []


def test_se_puede_editar_el_minimo(client, admin_headers, db):
    insumo = Insumo(nombre="Papa", unidad="kg", stock_actual=5.0)
    db.add(insumo)
    db.commit()
    r = client.put(f"/api/insumos/{insumo.id}", json={"stock_minimo": 8.0},
                   headers=admin_headers)
    assert r.json()["stock_minimo"] == 8.0 and r.json()["bajo_minimo"] is True
