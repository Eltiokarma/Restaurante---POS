from motor.igualdad import BASE, igualar, personas_casa


def test_igualar_no_toca_al_original_ni_a_la_planilla():
    datos = {"escenario": {"precio": 7, "q": 120, "alquiler_mes": 600, "planilla": [{"puesto": "Mozo", "monto": 40}]}}
    nuevo = igualar(datos)
    assert datos["escenario"]["precio"] == 7
    assert {k: nuevo["escenario"][k] for k in BASE} == BASE
    assert nuevo["escenario"]["planilla"] == datos["escenario"]["planilla"]


def test_igualar_solo_lo_que_se_pide():
    nuevo = igualar({"escenario": {"precio": 7, "q": 120}}, {"precio": 12, "q": None, "otra_cosa": 1})
    assert nuevo["escenario"] == {"precio": 12, "q": 120}


def test_personas_de_la_casa():
    familia = {"planilla": [{"monto": 0, "cantidad": 1}, {"monto": 0, "cantidad": 2}, {"monto": 40, "cantidad": 1}],
               "sueldo_dueno": False}
    assert personas_casa(familia) == 3
    assert personas_casa({"planilla": [], "sueldo_dueno": True}) == 1
    assert personas_casa({"sueldo_dueno": False}) == 0


def test_shapley_reparte_toda_la_diferencia():
    from motor.igualdad import GRUPOS, mezclar, shapley

    desde = {"precio": 10, "q": 60, "formal": False, "planilla": [], "noche": None, "anio": 2026}
    hasta = {"precio": 12, "q": 80, "formal": True, "planilla": [{"monto": 0}], "noche": {"q": 20}, "anio": 2027}

    # un "modelo" con interacción: el IGV pesa sobre la venta
    def valor(e):
        venta = e["precio"] * e["q"] + (100 if e.get("noche") else 0)
        return venta * (0.9 if e["formal"] else 1.0) - 50 * len(e["planilla"])

    aportes = shapley(valor, desde, hasta)
    assert set(aportes) == {c for c, _, _ in GRUPOS}
    assert abs(sum(aportes.values()) - (valor(hasta) - valor(desde))) < 1e-9
    assert aportes["insumos"] == 0 and abs(aportes["personal"] + 50) < 1e-9
    # lo que ningún grupo cubre viene siempre del destino
    assert mezclar(desde, hasta, set())["anio"] == 2027
