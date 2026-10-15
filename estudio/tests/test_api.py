"""El servicio: arranca, siembra, pide token y calcula."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/e.db")
    monkeypatch.setenv("ESTUDIO_TOKEN", "secreto-de-prueba")
    import api
    importlib.reload(api)
    with TestClient(api.app) as c:
        yield c


H = {"X-Token": "secreto-de-prueba"}


def test_salud_sin_token_y_siembra(cliente):
    r = cliente.get("/salud").json()
    assert r["ok"] and r["ciudades"] == 12 and r["parametros"] > 100


def test_todo_lo_demas_pide_token(cliente):
    assert cliente.get("/ciudades").status_code == 401
    assert cliente.get("/ciudades", headers={"X-Token": "otro"}).status_code == 401
    assert len(cliente.get("/ciudades", headers=H).json()) == 12


def test_calcular_reproduce_la_referencia(cliente):
    r = cliente.post("/calcular", headers=H, json={
        "ciudad_id": "lima", "segmento": "popular", "anio": 2026, "formal": True,
        "balones": 5, "sueldo_dueno": False, "q": 100}).json()
    assert r["equilibrio_menus_dia"] == 57
    assert 0 <= r["anio_montecarlo"]["prob_perdida"] <= 1


def test_zona_con_precio_de_sondeo(cliente):
    zona = cliente.post("/zonas", headers=H, json={"ciudad_id": "juliaca", "nombre": "Centro",
                                                   "tipo": "centro"}).json()
    r = cliente.post("/parametros", headers=H, json={
        "ambito": "zona", "zona_id": zona["id"], "segmento": "popular", "clave": "precio",
        "valor": 11, "rango_min": 10, "rango_max": 13, "origen": "sondeo", "fuente": "pizarras"})
    assert r.status_code == 201
    calc = cliente.post("/calcular", headers=H, json={"ciudad_id": "juliaca", "zona_id": zona["id"],
                                                       "sueldo_dueno": False, "q": 100}).json()
    assert calc["local"]["precio"] == 11 and calc["local"]["precio_propio"]
    assert calc["equilibrio_menus_dia"] < 138
