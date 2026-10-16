import random

from motor.incertidumbre import RANGOS, perturbar


def test_perturbar_respeta_rangos_y_no_toca_el_original():
    datos = {"escenario": {"precio": 10.0, "q": 60, "alquiler_mes": 1200, "sueldo_cocinero": 1300,
                           "planilla": [{"puesto": "Mamá", "monto": 0}, {"puesto": "Ayudante", "monto": 40}]}}
    rng = random.Random(1)
    for _ in range(200):
        e = perturbar(datos, rng)["escenario"]
        assert abs(e["precio"] / 10 - 1) <= RANGOS["precio"] + 1e-12
        assert abs(e["q"] / 60 - 1) <= RANGOS["q"] + 1e-12
        assert abs(e["alquiler_mes"] / 1200 - 1) <= RANGOS["alquiler_mes"] + 1e-12
        # quien trabaja sin sueldo sigue sin sueldo; los sueldos se mueven juntos
        assert e["planilla"][0]["monto"] == 0
        assert abs(e["planilla"][1]["monto"] / 40 - e["sueldo_cocinero"] / 1300) < 1e-12
    assert datos["escenario"]["precio"] == 10.0 and datos["escenario"]["planilla"][1]["monto"] == 40


def test_perturbar_es_reproducible_con_la_misma_semilla():
    datos = {"escenario": {"precio": 10.0, "q": 60}}
    a = perturbar(datos, random.Random(7))
    b = perturbar(datos, random.Random(7))
    assert a == b
