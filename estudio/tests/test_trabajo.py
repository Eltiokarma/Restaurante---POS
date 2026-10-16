from types import SimpleNamespace

from motor.trabajo import JORNADA_LEGAL, Persona, casa_desde, trabajo_de_la_casa, valor_mercado

LOCAL = SimpleNamespace(sueldo_cocinero=1300.0, sueldo_ayudante=1230.0, sueldo_mozo=1230.0)


def test_jornada_legal_vale_un_sueldo_y_las_horas_extra_llevan_recargo():
    assert abs(valor_mercado(Persona("Ana", "cocinero", JORNADA_LEGAL), LOCAL) - 1300) < 1e-9
    sesenta = valor_mercado(Persona("Ana", "cocinero", 60), LOCAL)
    assert sesenta > 1300 * 60 / 48  # las 12 horas extra cuestan más que las normales


def test_utilidad_economica_descuenta_trabajo_y_capital():
    casa = [Persona("Mamá", "cocinero", 48), Persona("Hijo", "mozo", 48)]
    r = trabajo_de_la_casa(casa, ingreso_casa=3000, local=LOCAL, inversion=12000, tasa_anual=0.15)
    assert abs(r["valor_mercado"] - 2530) < 1e-9
    assert abs(r["costo_capital"] - 150) < 1e-9
    assert abs(r["utilidad_economica"] - (3000 - 2530 - 150)) < 1e-9
    assert abs(r["parte_cobrada"] - 3000 / 2530) < 1e-9


def test_sin_gente_de_la_casa_no_hay_pago_por_hora():
    r = trabajo_de_la_casa([], ingreso_casa=-500, local=LOCAL)
    assert r["horas_mes"] == 0 and r["por_hora"] is None and r["parte_cobrada"] is None
    assert r["utilidad_economica"] == -500


def test_casa_desde_el_escenario_guardado():
    datos = {"casa": [{"quien": "Propietario", "rol": "cocinero", "horas_semana": 60}]}
    assert casa_desde(datos) == [Persona("Propietario", "cocinero", 60.0)]
    assert casa_desde({}) == []
