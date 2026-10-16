"""Barrido de decisiones y prueba de estrés."""
from motor import Escenario, cargar_dataset, local_de_ciudad, modelo
from motor.barrido import Factores, Mezcla, _aplicar, barrido, estres
from motor.flujo import Supuestos

DATA = cargar_dataset()
NAC, RIESGO = DATA["nacional"], DATA["riesgo"]
LOCAL = local_de_ciudad(next(c for c in DATA["ciudades"] if c["id"] == "juliaca"), precio=11.0)


def test_sin_elasticidad_subir_precio_no_espanta_y_con_elasticidad_si():
    _, _, q0 = _aplicar(LOCAL, Escenario(), 80, 1.0, "estandar", None, False, 0.0, None)
    _, _, q1 = _aplicar(LOCAL, Escenario(), 80, 1.0, "estandar", None, False, 1.0, None)
    assert q0 == 80 and q1 < 80
    assert abs(q1 - 80 * (12 / 11) ** -1) < 1e-9


def test_mezcla_mas_res_cuesta_mas():
    mz = Mezcla(costo_res=4.0, costo_otros=3.5, acompanamiento=1.4, parte_actual=0.5)
    assert mz.insumos(0.75) > mz.insumos(0.25)
    assert abs(mz.insumos(0.5) - (1.4 + 3.75) / 1.05) < 1e-9


def test_barrido_cubre_todas_las_combinaciones_y_ordena_por_peor_caso():
    f = Factores(precio=[0.0, 1.0], calidad=["estandar"], noche=[False], elasticidad=[0.5, 1.5])
    r = barrido(LOCAL, Escenario(), 80, NAC, RIESGO, Supuestos(), f)
    assert len(r["filas"]) == 4 and len(r["decisiones"]) == 2
    peores = [d["utilidad_peor"] for d in r["decisiones"]]
    assert peores == sorted(peores, reverse=True)
    base = r["base"]
    assert base["delta_precio"] == 0 and base["utilidad_peor"] == round(modelo(LOCAL, 80, Escenario(), NAC).util)


def test_estres_el_golpe_combinado_es_el_peor():
    g = {x["golpe"]: x for x in estres(LOCAL, Escenario(), 100, NAC, RIESGO)}
    assert g["insumos"]["utilidad"] < g["base"]["utilidad"]
    assert g["igv"]["utilidad"] < g["base"]["utilidad"]
    assert g["todo"]["utilidad"] == min(x["utilidad"] for x in g.values())


def test_techo_de_cocina_corta_la_venta():
    local = local_de_ciudad(DATA["ciudades"][0])
    esc = Escenario()
    # bajar el precio con clientela sensible promete más menús de los que la cocina saca
    _l, _e, q_libre = _aplicar(local, esc, 80, -2.0, "estandar", None, False, 2.5, None)
    _l, _e, q_techo = _aplicar(local, esc, 80, -2.0, "estandar", None, False, 2.5, None, capacidad=90)
    assert q_libre > 90 and q_techo == 90
    # si la venta no llega al techo, no cambia nada
    _l, _e, q_bajo = _aplicar(local, esc, 80, 1.0, "estandar", None, False, 2.5, None, capacidad=90)
    assert q_bajo < 80
