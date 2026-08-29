"""Fase 4: métodos de pago, insumos, recetas y kardex."""


def crear_orden(client, menu_ejemplo, cantidad=1):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": cantidad}],
    })
    assert r.status_code == 201
    return r.json()["orden"]["id"]


def crear_insumo(client, admin_headers, nombre="Papa", unidad="kg", costo=2.0):
    r = client.post("/api/insumos", json={
        "nombre": nombre, "unidad": unidad, "costo_unitario": costo,
    }, headers=admin_headers)
    assert r.status_code == 201
    return r.json()["id"]


# ---------- Métodos de pago ----------

def test_registrar_pago_y_corregirlo(client, menu_ejemplo):
    orden_id = crear_orden(client, menu_ejemplo)
    r = client.patch(f"/api/orders/{orden_id}/pago", json={"metodo_pago": "tarjeta"})
    assert r.status_code == 200 and r.json()["metodo_pago"] == "tarjeta"
    r = client.patch(f"/api/orders/{orden_id}/pago", json={"metodo_pago": "yape"})
    assert r.json()["metodo_pago"] == "yape"
    assert client.patch(f"/api/orders/{orden_id}/pago", json={"metodo_pago": "cheque"}).status_code == 422


def test_orden_anulada_no_se_cobra(client, menu_ejemplo):
    orden_id = crear_orden(client, menu_ejemplo)
    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})
    assert client.patch(f"/api/orders/{orden_id}/pago", json={"metodo_pago": "efectivo"}).status_code == 409


def test_cierre_cuadra_solo_el_efectivo(client, menu_ejemplo):
    client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    efectivo = crear_orden(client, menu_ejemplo)          # 15, efectivo explícito
    tarjeta = crear_orden(client, menu_ejemplo, cantidad=2)  # 30, tarjeta
    crear_orden(client, menu_ejemplo)                     # 15, sin registrar → se asume efectivo
    client.patch(f"/api/orders/{efectivo}/pago", json={"metodo_pago": "efectivo"})
    client.patch(f"/api/orders/{tarjeta}/pago", json={"metodo_pago": "tarjeta"})

    estado = client.get("/api/caja/hoy").json()
    assert estado["ventas_efectivo"] == 30.0   # 15 + 15 sin registrar
    assert estado["ventas_tarjeta"] == 30.0
    assert estado["sin_registrar"] == 1

    # Esperado en efectivo: 50 + 30 = 80. Contado 80 → cuadra, aunque el
    # total vendido del día sea 60.
    r = client.post("/api/caja/cerrar", json={"monto_contado": 80.0})
    data = r.json()
    assert data["diferencia"] == 0.0
    assert data["total_sistema"] == 60.0
    assert data["ventas_tarjeta"] == 30.0


# ---------- Insumos y kardex ----------

def test_compra_actualiza_stock_y_costo_promedio(client, admin_headers):
    insumo_id = crear_insumo(client, admin_headers)
    # 10 kg a S/ 20 → costo 2.0
    r = client.post(f"/api/insumos/{insumo_id}/movimientos", json={
        "tipo": "compra", "cantidad": 10, "costo_total": 20.0,
    }, headers=admin_headers)
    assert r.json()["stock_actual"] == 10 and r.json()["costo_unitario"] == 2.0
    # 10 kg más a S/ 40 → promedio (20+40)/20 = 3.0
    r = client.post(f"/api/insumos/{insumo_id}/movimientos", json={
        "tipo": "compra", "cantidad": 10, "costo_total": 40.0,
    }, headers=admin_headers)
    assert r.json()["stock_actual"] == 20 and r.json()["costo_unitario"] == 3.0


def test_merma_y_ajuste(client, admin_headers):
    insumo_id = crear_insumo(client, admin_headers)
    client.post(f"/api/insumos/{insumo_id}/movimientos", json={
        "tipo": "compra", "cantidad": 5, "costo_total": 10.0,
    }, headers=admin_headers)
    r = client.post(f"/api/insumos/{insumo_id}/movimientos", json={
        "tipo": "merma", "cantidad": 1, "nota": "se malogró",
    }, headers=admin_headers)
    assert r.json()["stock_actual"] == 4
    # Conteo físico: había 3.5 en realidad
    r = client.post(f"/api/insumos/{insumo_id}/movimientos", json={
        "tipo": "ajuste", "cantidad": 3.5,
    }, headers=admin_headers)
    assert r.json()["stock_actual"] == 3.5

    kardex = client.get("/api/insumos/kardex", headers=admin_headers).json()
    tipos = [m["tipo"] for m in kardex["movimientos"]]
    assert tipos[:3] == ["ajuste", "merma", "compra"]  # más reciente primero


# ---------- Recetas y consumo automático ----------

def test_venta_consume_insumos_y_anular_los_devuelve(client, admin_headers, menu_ejemplo):
    papa = crear_insumo(client, admin_headers, "Papa", "kg")
    arroz = crear_insumo(client, admin_headers, "Arroz", "kg")
    for insumo_id in (papa, arroz):
        client.post(f"/api/insumos/{insumo_id}/movimientos", json={
            "tipo": "compra", "cantidad": 10, "costo_total": 30.0,
        }, headers=admin_headers)

    # Receta del lomo: 0.25 kg papa + 0.2 kg arroz por porción
    lomo = menu_ejemplo["Lomo saltado"]
    r = client.put(f"/api/insumos/recetas/{lomo}", json={"items": [
        {"insumo_id": papa, "cantidad": 0.25},
        {"insumo_id": arroz, "cantidad": 0.2},
    ]}, headers=admin_headers)
    assert r.json()["costo_porcion"] == round(0.25 * 3 + 0.2 * 3, 2)  # costo 3.0/kg

    # Vender 2 lomos → papa 10-0.5=9.5, arroz 10-0.4=9.6
    orden_id = crear_orden(client, menu_ejemplo, cantidad=2)
    stocks = {i["nombre"]: i["stock_actual"] for i in
              client.get("/api/insumos", headers=admin_headers).json()["insumos"]}
    assert stocks["Papa"] == 9.5 and stocks["Arroz"] == 9.6

    # Anular devuelve el stock
    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})
    stocks = {i["nombre"]: i["stock_actual"] for i in
              client.get("/api/insumos", headers=admin_headers).json()["insumos"]}
    assert stocks["Papa"] == 10 and stocks["Arroz"] == 10

    # El kardex registró consumo (con la orden como referencia) y la reversión
    kardex = client.get("/api/insumos/kardex", headers=admin_headers).json()["movimientos"]
    referencias = {m["referencia"] for m in kardex}
    assert any(ref.startswith("orden #") for ref in referencias)
    assert any(ref.startswith("anulación orden #") for ref in referencias)


def test_plato_sin_receta_no_genera_movimientos(client, admin_headers, menu_ejemplo):
    crear_orden(client, menu_ejemplo)
    kardex = client.get("/api/insumos/kardex", headers=admin_headers).json()
    assert kardex["movimientos"] == []


def test_insumos_requieren_admin(client):
    assert client.get("/api/insumos").status_code == 401
    assert client.post("/api/insumos", json={"nombre": "X", "unidad": "kg"}).status_code == 401
