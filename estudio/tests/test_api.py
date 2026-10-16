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
    lista = [g for g in cliente.get("/api/escenarios", headers=H).json() if g["nombre"] == "Candela hoy"]
    assert len(lista) == 1 and lista[0]["datos"]["precio"] == 12
    assert cliente.delete(f"/api/escenarios/{lista[0]['id']}", headers=H).status_code == 204
    assert all(g["nombre"] != "Candela hoy" for g in cliente.get("/api/escenarios", headers=H).json())


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


def test_arquetipos_sembrados_y_comparables(cliente):
    lista = cliente.get("/api/escenarios", headers=H).json()
    nombres = {g["nombre"] for g in lista}
    assert {"Propietario que cocina", "Familiar sin sueldos", "Inversor que supervisa", "Inversor ausente",
            "Exitoso (referencia compuesta)", "Día y noche"} <= nombres
    r = cliente.post("/api/comparar", headers=H, json={"ids": [g["id"] for g in lista]}).json()
    assert len(r) == len(lista) and not any("error" in x for x in r)
    por = {x["nombre"]: x for x in r}
    # la familia que no cobra sueldo se lleva la utilidad entera
    assert por["Familiar sin sueldos"]["ingreso_dueno_mes"] == por["Familiar sin sueldos"]["utilidad_mes"]
    # el inversor ausente paga más gente que el inversor
    assert por["Inversor ausente"]["trabajadores"] > por["Inversor que supervisa"]["trabajadores"]
    assert por["Día y noche"]["noche"] and por["Exitoso (referencia compuesta)"]["utilidad_mes"] > 0


def test_comparar_trae_la_sensibilidad_de_cada_caso(cliente):
    lista = cliente.get("/api/escenarios", headers=H).json()
    ids = [g["id"] for g in lista if g["nombre"] in ("Inversor que supervisa", "Exitoso (referencia compuesta)")]
    r = {x["nombre"]: x for x in cliente.post("/api/comparar", headers=H, json={"ids": ids}).json()}
    exitoso = r["Exitoso (referencia compuesta)"]
    # gana: el precio puede bajar algo antes de perder; los insumos pueden subir
    assert exitoso["quiebres"]["precio"] < 0 < exitoso["quiebres"]["insumos"]
    assert exitoso["tornado"][0]["variable"] == "precio"
    # el inversor casi en cero aguanta mucho menos que el exitoso
    assert abs(r["Inversor que supervisa"]["quiebres"]["precio"]) < abs(exitoso["quiebres"]["precio"])


def test_familia_y_duena_solo_difieren_en_quien_trabaja(cliente):
    lista = cliente.get("/api/escenarios", headers=H).json()
    ids = [g["id"] for g in lista if g["nombre"] in ("Propietario que cocina", "Familiar sin sueldos")]
    r = {x["nombre"]: x for x in cliente.post("/api/comparar", headers=H, json={"ids": ids}).json()}
    duena, familia = r["Propietario que cocina"], r["Familiar sin sueldos"]
    assert duena["ventas_mes"] == familia["ventas_mes"]
    assert (duena["personas_casa"], familia["personas_casa"]) == (1, 3)
    # la casa se lleva parecido, pero la familia lo reparte entre tres
    assert familia["ingreso_por_persona"] < duena["ingreso_por_persona"] / 2


def test_comparar_a_igualdad_de_condiciones(cliente):
    lista = cliente.get("/api/escenarios", headers=H).json()
    ids = [g["id"] for g in lista if g["nombre"] in ("Inversor que supervisa", "Exitoso (referencia compuesta)",
                                                     "Fonda en casa propia")]
    propios = {x["nombre"]: x for x in cliente.post("/api/comparar", headers=H, json={"ids": ids}).json()}
    iguales = cliente.post("/api/comparar", headers=H, json={
        "ids": ids, "igualar": {"precio": 10, "q": 60, "alquiler_mes": 1200}}).json()
    assert {(x["precio"], x["menus_dia"]) for x in iguales} == {(10, 60)}
    assert len({x["ventas_mes"] for x in iguales}) == 1
    # solo con el alquiler igualado, la fonda pierde su casa gratis y gana menos
    con_alquiler = cliente.post("/api/comparar", headers=H, json={"ids": ids, "igualar": {"alquiler_mes": 1200}}).json()
    fonda = next(x for x in con_alquiler if x["nombre"] == "Fonda en casa propia")
    assert fonda["alquiler_pct"] > 0 and fonda["utilidad_mes"] < propios["Fonda en casa propia"]["utilidad_mes"]
    # sin dueño que trabaje no hay "por persona"
    assert next(x for x in iguales if x["nombre"] == "Inversor que supervisa")["ingreso_por_persona"] is None


def _esperar(cliente, id_):
    import time
    for _ in range(300):
        c = cliente.get(f"/api/corridas/{id_}", headers=H).json()
        if c["estado"] in ("lista", "error"):
            return c
        time.sleep(0.05)
    raise AssertionError("la corrida no terminó")


def test_corridas_en_segundo_plano(cliente):
    inv = next(g for g in cliente.get("/api/escenarios", headers=H).json() if g["nombre"] == "Inversor que supervisa")
    r = cliente.post("/api/corridas", headers=H, json={
        "tipo": "decisiones", "escenario_id": inv["id"],
        "factores": {"precio": [0, 1], "calidad": ["estandar"], "noche": [False], "elasticidad": [0.5, 1.5]}})
    assert r.status_code == 201
    c = _esperar(cliente, r.json()["id"])
    assert c["estado"] == "lista" and len(c["resultado"]["decisiones"]) == 2
    # "hoy" en la corrida es exactamente el escenario guardado
    hoy = cliente.post("/api/comparar", headers=H, json={"ids": [inv["id"]]}).json()[0]["utilidad_mes"]
    assert c["resultado"]["base"]["utilidad_media"] == hoy
    e = _esperar(cliente, cliente.post("/api/corridas", headers=H, json={"tipo": "estres"}).json()["id"])
    assert e["estado"] == "lista" and len(e["resultado"]["negocios"]) >= 9
    assert all(len(n["golpes"]) == 8 for n in e["resultado"]["negocios"])
    assert len(cliente.get("/api/corridas", headers=H).json()) == 2
    assert cliente.post("/api/corridas", headers=H, json={"tipo": "decisiones"}).status_code == 404


def test_decisiones_de_todos_los_negocios(cliente):
    c = _esperar(cliente, cliente.post("/api/corridas", headers=H, json={"tipo": "decisiones_todos"}).json()["id"])
    assert c["estado"] == "lista"
    negocios = c["resultado"]["negocios"]
    assert len(negocios) >= 10 and not any("error" in n for n in negocios)
    for n in negocios:
        assert n["mejor"]["utilidad_peor"] >= n["base"]["utilidad_peor"]  # hoy es una de las opciones
        assert set(n["curvas"]) == {"0.5", "1.0", "1.5"}
