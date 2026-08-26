"""Log de cancelaciones durante la ventana de espera."""


def test_registrar_y_listar(client, admin_headers):
    r = client.post("/api/cancellations", json={
        "items": [{"nombre": "Lomo saltado", "precio": 15.0, "cantidad": 2}],
        "total": 30.0,
    })
    assert r.status_code == 201

    data = client.get("/api/cancellations/today", headers=admin_headers).json()
    assert len(data["cancelaciones"]) == 1
    c = data["cancelaciones"][0]
    assert c["total"] == 30.0
    assert c["items"][0]["nombre"] == "Lomo saltado"


def test_listado_requiere_admin(client):
    assert client.get("/api/cancellations/today").status_code == 401


def test_cancelacion_vacia_es_422(client):
    assert client.post("/api/cancellations", json={"items": [], "total": 0}).status_code == 422
