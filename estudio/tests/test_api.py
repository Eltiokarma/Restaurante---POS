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
    r = cliente.get("/api/salud").json()
    assert r["ok"] and r["ciudades"] == 12 and r["parametros"] > 100


def test_todo_lo_demas_pide_token(cliente):
    assert cliente.get("/api/ciudades").status_code == 401
    assert cliente.get("/api/ciudades", headers={"X-Token": "otro"}).status_code == 401
    assert len(cliente.get("/api/ciudades", headers=H).json()) == 12


def test_calcular_reproduce_la_referencia(cliente):
    r = cliente.post("/api/calcular", headers=H, json={
        "ciudad_id": "lima", "segmento": "popular", "anio": 2026, "formal": True,
        "balones": 5, "sueldo_dueno": False, "q": 100}).json()
    assert r["equilibrio_menus_dia"] == 57
    assert 0 <= r["anio_montecarlo"]["prob_perdida"] <= 1


def test_zona_con_precio_de_sondeo(cliente):
    zona = cliente.post("/api/zonas", headers=H, json={"ciudad_id": "juliaca", "nombre": "Centro",
                                                   "tipo": "centro"}).json()
    r = cliente.post("/api/parametros", headers=H, json={
        "ambito": "zona", "zona_id": zona["id"], "segmento": "popular", "clave": "precio",
        "valor": 11, "rango_min": 10, "rango_max": 13, "origen": "sondeo", "fuente": "pizarras"})
    assert r.status_code == 201
    calc = cliente.post("/api/calcular", headers=H, json={"ciudad_id": "juliaca", "zona_id": zona["id"],
                                                       "sueldo_dueno": False, "q": 100}).json()
    assert calc["local"]["precio"] == 11 and calc["local"]["precio_propio"]
    assert calc["equilibrio_menus_dia"] < 138


def test_calcular_con_barras_y_curva(cliente):
    base = {"ciudad_id": "juliaca", "precio": 11, "q": 80}
    r1 = cliente.post("/api/calcular", headers=H, json=base).json()
    r2 = cliente.post("/api/calcular", headers=H, json={**base, "alquiler_mes": 800}).json()
    assert r2["local"]["alquiler_mes"] == 800
    assert r2["equilibrio_menus_dia"] < r1["equilibrio_menus_dia"]
    assert r1["curva"][0]["q"] == 5 and r1["curva"][-1]["q"] >= 160


def test_flujo_y_comparacion(cliente):
    r = cliente.post("/api/flujo", headers=H, json={"ciudad_id": "juliaca", "precio": 11, "q": 100,
                                                    "inversion": 30000, "regimen": "mype"}).json()
    assert len(r["anios"]) == 10 and r["anios"][0]["anio"] == 2026
    assert {c["regimen"] for c in r["comparacion"]} == {"informal", "nuevo_rus", "rer", "mype"}
    assert cliente.post("/api/flujo", headers=H, json={"ciudad_id": "juliaca",
                                                       "regimen": "otro"}).status_code == 422


def test_escenarios_guardados(cliente):
    assert cliente.post("/api/escenarios", headers=H,
                        json={"nombre": "Candela hoy", "datos": {"precio": 11}}).status_code == 201
    cliente.post("/api/escenarios", headers=H, json={"nombre": "Candela hoy", "datos": {"precio": 12}})
    lista = cliente.get("/api/escenarios", headers=H).json()
    assert len(lista) == 1 and lista[0]["datos"]["precio"] == 12
    assert cliente.delete(f"/api/escenarios/{lista[0]['id']}", headers=H).status_code == 204
    assert cliente.get("/api/escenarios", headers=H).json() == []


def test_planilla_y_sensibilidad_por_api(cliente):
    base = {"ciudad_id": "juliaca", "precio": 11, "q": 80, "formal": False, "dias": 30,
            "planilla": [{"puesto": "Ayudante", "monto": 45, "modalidad": "diario", "dias": 30}]}
    r = cliente.post("/api/calcular", headers=H, json=base).json()
    assert r["pagos"]["jornales_por_dia"] == 45 and r["mes_a_q"]["cocina"] == 1
    sens = cliente.post("/api/sensibilidad", headers=H, json=base).json()
    assert sens["tornado"] and sens["quiebres"] and sens["matriz"]["utilidad"]


def test_recetas_por_api(cliente):
    pollo = cliente.post("/api/insumos", headers=H, json={"nombre": "Pollo", "precio": 10, "merma": 0.2}).json()
    assert cliente.post("/api/insumos", headers=H, json={"nombre": "pollo", "precio": 9}).status_code == 409
    plato = cliente.post("/api/platos", headers=H, json={
        "nombre": "Arroz con pollo", "tipo": "segundo", "porciones": 10, "precio": 11, "vendidos": 60,
        "items": [{"insumo_id": pollo["id"], "cantidad": 2}]}).json()
    an = cliente.get("/api/platos/analisis", headers=H).json()
    assert an["platos"][0]["costo_porcion"] == 2.5
    # no se borra un insumo que usa una receta
    assert cliente.delete(f"/api/insumos/{pollo['id']}", headers=H).status_code == 409
    editado = cliente.put(f"/api/platos/{plato['id']}", headers=H, json={**plato, "items": []}).json()
    assert editado["items"] == []
    assert cliente.delete(f"/api/insumos/{pollo['id']}", headers=H).status_code == 204
    assert cliente.delete(f"/api/platos/{plato['id']}", headers=H).status_code == 204
