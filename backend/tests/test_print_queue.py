"""Cola de la estación de impresión (/ticketera) y modos de impresión."""


def activar_modo(client, admin_headers, modo):
    r = client.put("/api/config", json={"modo_impresion": modo}, headers=admin_headers)
    assert r.status_code == 200


def crear_orden(client, menu_ejemplo):
    r = client.post("/api/orders", json={"items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}]})
    assert r.status_code == 201
    return r.json()["orden"]["id"]


def test_modo_terminal_no_encola(client, admin_headers, menu_ejemplo):
    # Default: la terminal imprime, la orden nace marcada como impresa
    crear_orden(client, menu_ejemplo)
    assert client.get("/api/orders/pending-print").json()["ordenes"] == []


def test_modo_estacion_encola_y_marca(client, admin_headers, menu_ejemplo):
    activar_modo(client, admin_headers, "estacion")
    orden_id = crear_orden(client, menu_ejemplo)

    cola = client.get("/api/orders/pending-print").json()
    assert [o["id"] for o in cola["ordenes"]] == [orden_id]
    assert "nombre" in cola["local"]

    assert client.post(f"/api/orders/{orden_id}/printed").status_code == 200
    assert client.get("/api/orders/pending-print").json()["ordenes"] == []


def test_reprint_reencola(client, admin_headers, menu_ejemplo):
    activar_modo(client, admin_headers, "estacion")
    orden_id = crear_orden(client, menu_ejemplo)
    client.post(f"/api/orders/{orden_id}/printed")

    assert client.post(f"/api/orders/{orden_id}/reprint").status_code == 200
    assert [o["id"] for o in client.get("/api/orders/pending-print").json()["ordenes"]] == [orden_id]


def test_clear_descarta_pendientes(client, admin_headers, menu_ejemplo):
    activar_modo(client, admin_headers, "estacion")
    crear_orden(client, menu_ejemplo)
    crear_orden(client, menu_ejemplo)

    r = client.post("/api/orders/pending-print/clear")
    assert r.json()["descartadas"] == 2
    assert client.get("/api/orders/pending-print").json()["ordenes"] == []
