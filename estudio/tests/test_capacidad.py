from types import SimpleNamespace

from motor.capacidad import POR_COCINA, POR_MOZO, capacidad, faltan, gente


def _datos(planilla, casa=None):
    return {"escenario": {"planilla": planilla}, "casa": casa or []}


def test_candela_tres_y_tres_aguanta_cien():
    c = capacidad(3, 3)
    assert round(c["tope_cocina"]) == 100
    assert c["tope"] == c["tope_cocina"] and c["limita"] == "cocina"
    assert faltan(100, 3, 3) == (0, 0)
    assert faltan(100, 3, 2) == (0, 0)  # con dos mozos aguanta, sobreexigidos


def test_faltan_cuenta_personas_enteras():
    assert faltan(80, 2, 1) == (1, 1)
    assert faltan(10, 5, 5) == (0, 0)
    assert POR_MOZO == 50 and round(POR_COCINA, 1) == 33.3


def test_gente_sin_planilla_usa_la_automatica():
    r = SimpleNamespace(cocina=2, mozos=2)
    assert gente({"escenario": {}}, r) == (2, 2)


def test_gente_suma_al_propietario_que_cocina_y_no_duplica_la_familia():
    planilla = [
        {"puesto": "Mamá (cocina)", "area": "cocina"},
        {"puesto": "Ayudante", "area": "cocina", "cantidad": 2},
        {"puesto": "Mozo", "area": "salon"},
        {"puesto": "Mozo de noche", "area": "salon", "turno": "noche"},
        {"puesto": "Administrador", "area": "otro"},
    ]
    casa = [{"quien": "Mamá", "rol": "cocinero", "horas_semana": 60},
            {"quien": "Propietario", "rol": "cocinero", "horas_semana": 60}]
    assert gente(_datos(planilla, casa), None) == (4, 1)


def test_sin_mozo_alguien_de_cocina_atiende():
    planilla = [{"puesto": "Ayudante", "area": "cocina"}]
    casa = [{"quien": "Propietario", "rol": "cocinero", "horas_semana": 60}]
    assert gente(_datos(planilla, casa), None) == (1, 1)
