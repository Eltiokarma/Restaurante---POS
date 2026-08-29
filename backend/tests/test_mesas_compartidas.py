"""Mesas compartidas (liberación por ticket) y notas por plato."""


def crear_mesa(client, admin_headers, nombre):
    return client.post("/api/mesas", json={"nombre": nombre}, headers=admin_headers).json()["id"]


def crear_orden(client, menu_ejemplo, mesa_ids=None, nota=""):
    item = {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}
    if nota:
        item["nota"] = nota
    payload = {"items": [item]}
    if mesa_ids is not None:
        payload["mesa_ids"] = mesa_ids
    r = client.post("/api/orders", json=payload)
    assert r.status_code == 201
    return r.json()["orden"]


def test_dos_tickets_comparten_mesa_y_se_liberan_por_separado(client, admin_headers, menu_ejemplo):
    m1 = crear_mesa(client, admin_headers, "Mesa 1")

    # Grupo A se sienta; el local se llena y el cliente B comparte la mesa
    orden_a = crear_orden(client, menu_ejemplo, mesa_ids=[m1])
    orden_b = crear_orden(client, menu_ejemplo, mesa_ids=[m1])

    mesa = client.get("/api/mesas").json()["mesas"][0]
    assert mesa["ocupada"] is True
    assert sorted(mesa["ordenes"]) == sorted([
        orden_a["numero_orden_dia"], orden_b["numero_orden_dia"],
    ])

    # El grupo A termina y se va: se libera SU ticket, no la mesa entera
    client.post(f"/api/orders/{orden_a['id']}/liberar-mesa")
    mesa = client.get("/api/mesas").json()["mesas"][0]
    assert mesa["ocupada"] is True  # B sigue comiendo
    assert mesa["ordenes"] == [orden_b["numero_orden_dia"]]

    # B termina: la mesa queda libre
    client.post(f"/api/orders/{orden_b['id']}/liberar-mesa")
    assert client.get("/api/mesas").json()["mesas"][0]["ocupada"] is False


def test_liberar_mesa_entera_sigue_liberando_todo(client, admin_headers, menu_ejemplo):
    m1 = crear_mesa(client, admin_headers, "Mesa 1")
    crear_orden(client, menu_ejemplo, mesa_ids=[m1])
    crear_orden(client, menu_ejemplo, mesa_ids=[m1])

    r = client.post(f"/api/mesas/{m1}/liberar")
    assert r.json()["tickets_liberados"] == 2
    assert client.get("/api/mesas").json()["mesas"][0]["ocupada"] is False


# ---------- Notas por plato ----------

def test_nota_se_guarda_y_devuelve(client, menu_ejemplo):
    orden = crear_orden(client, menu_ejemplo, nota="  sin frijoles, con un huevo frito ")
    assert orden["items"][0]["nota"] == "sin frijoles, con un huevo frito"

    hoy = client.get("/api/orders/today").json()["ordenes"]
    assert hoy[0]["items"][0]["nota"] == "sin frijoles, con un huevo frito"


def test_nota_vacia_por_defecto_y_larga_es_422(client, menu_ejemplo):
    orden = crear_orden(client, menu_ejemplo)
    assert orden["items"][0]["nota"] == ""

    r = client.post("/api/orders", json={"items": [{
        "plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1, "nota": "x" * 200,
    }]})
    assert r.status_code == 422


def test_nota_en_csv(client, admin_headers, menu_ejemplo):
    crear_orden(client, menu_ejemplo, nota="sin arroz")
    r = client.get("/api/stats/export", headers=admin_headers)
    assert ";nota;" in r.text.splitlines()[0]
    assert ";sin arroz;" in r.text
