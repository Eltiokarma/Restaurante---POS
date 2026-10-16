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
