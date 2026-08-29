"""Candado PIN_LOCAL para despliegues en internet (Railway)."""
import pytest


@pytest.fixture()
def con_pin(monkeypatch):
    monkeypatch.setenv("PIN_LOCAL", "4321")


def test_sin_pin_definido_todo_abierto(client):
    # Comportamiento LAN de siempre: sin PIN_LOCAL nada cambia
    assert client.get("/api/menu/today").status_code == 200


def test_con_pin_la_api_exige_header(client, con_pin):
    r = client.get("/api/menu/today")
    assert r.status_code == 401
    assert r.json()["detail"] == "PIN requerido"

    assert client.get("/api/menu/today", headers={"X-Pin-Local": "malo"}).status_code == 401
    assert client.get("/api/menu/today", headers={"X-Pin-Local": "4321"}).status_code == 200


def test_health_y_login_quedan_exentos(client, con_pin):
    assert client.get("/api/health").status_code == 200
    # El login responde (401 por contraseña mala, no por PIN)
    r = client.post("/api/admin/login", json={"password": "mala"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Contraseña incorrecta"


def test_ordenes_tambien_protegidas(client, con_pin, menu_ejemplo):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
    })
    assert r.status_code == 401
    r = client.post(
        "/api/orders",
        json={"items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}]},
        headers={"X-Pin-Local": "4321"},
    )
    assert r.status_code == 201
