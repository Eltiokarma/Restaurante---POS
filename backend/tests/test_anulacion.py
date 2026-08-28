"""Anulación de órdenes desde la caja."""


def crear_orden(client, menu_ejemplo, plato="Lomo saltado", cantidad=1):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo[plato], "cantidad": cantidad}],
    })
    assert r.status_code == 201
    return r.json()["orden"]["id"]


def test_anular_es_un_estado_valido(client, menu_ejemplo):
    orden_id = crear_orden(client, menu_ejemplo)
    r = client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})
    assert r.status_code == 200 and r.json()["estado"] == "anulada"


def test_anulada_no_cuenta_en_total_vendido(client, menu_ejemplo):
    crear_orden(client, menu_ejemplo)                     # 15.00 vendida
    anulada = crear_orden(client, menu_ejemplo, cantidad=2)  # 30.00 anulada
    client.patch(f"/api/orders/{anulada}/status", json={"estado": "anulada"})

    data = client.get("/api/orders/today").json()
    assert data["total_vendido"] == 15.0
    # Pero la orden sigue visible en la lista (con su estado)
    estados = {o["id"]: o["estado"] for o in data["ordenes"]}
    assert estados[anulada] == "anulada"


def test_anulada_no_cuenta_en_stats(client, admin_headers, menu_ejemplo):
    crear_orden(client, menu_ejemplo)
    anulada = crear_orden(client, menu_ejemplo, cantidad=3)
    client.patch(f"/api/orders/{anulada}/status", json={"estado": "anulada"})

    data = client.get("/api/stats/today", headers=admin_headers).json()
    assert data["num_ordenes"] == 1
    assert data["total_vendido"] == 15.0
    assert data["num_anuladas"] == 1
    ventas = {v["nombre"]: v for v in data["ventas_por_plato"]}
    assert ventas["Lomo saltado"]["cantidad"] == 1  # los 3 anulados no suman


def test_anulada_sale_de_la_cola_de_impresion(client, admin_headers, menu_ejemplo):
    client.put("/api/config", json={"modo_impresion": "estacion"}, headers=admin_headers)
    orden_id = crear_orden(client, menu_ejemplo)
    assert len(client.get("/api/orders/pending-print").json()["ordenes"]) == 1

    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})
    assert client.get("/api/orders/pending-print").json()["ordenes"] == []
