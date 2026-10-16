"""Planilla con modalidades de pago, sensibilidad y costeo de recetas."""
from dataclasses import replace

import pytest

from motor import Escenario, cargar_dataset, local_de_ciudad, modelo
from motor.modelo import Trabajador, costo_trabajador
from motor.personal import calendario_pagos
from motor.recetas import InsumoR, PlatoR, analizar
from motor.sensibilidad import matriz, quiebre, tornado

DATA = cargar_dataset()
NAC = DATA["nacional"]
LOCAL = local_de_ciudad(next(c for c in DATA["ciudades"] if c["id"] == "juliaca"), precio=11.0)


def test_dias_que_abre_cambian_el_volumen_del_mes():
    m26 = modelo(LOCAL, 80, Escenario(), NAC)
    m30 = modelo(LOCAL, 80, Escenario(dias=30), NAC)
    assert m30.q_mes == 80 * 30 and m30.util > m26.util


def test_jornal_se_paga_por_dia_trabajado_y_formal_respeta_el_minimo():
    t = Trabajador("Ayudante", monto=40, modalidad="diario", dias=20)
    assert costo_trabajador(t, formal=False, rmv=1230, mult=1.05, dias_local=26) == 800
    # formal: jornal no menor a RMV/30 (41) y con cargas
    assert costo_trabajador(t, formal=True, rmv=1230, mult=1.05, dias_local=26) == pytest.approx(41 * 20 * 1.05)
    sin_dias = Trabajador("Ayudante", monto=50, modalidad="diario")
    assert costo_trabajador(sin_dias, formal=False, rmv=1230, mult=1, dias_local=24) == 1200


def test_mensual_y_quincenal_cuestan_lo_mismo_pero_salen_en_fechas_distintas():
    mensual = Escenario(formal=False, planilla=(Trabajador("Cocinero", 1600),))
    quincenal = replace(mensual, planilla=(Trabajador("Cocinero", 1600, modalidad="quincenal"),))
    assert modelo(LOCAL, 80, mensual, NAC).personal == modelo(LOCAL, 80, quincenal, NAC).personal
    pagos = calendario_pagos(LOCAL, quincenal, NAC, 1, 0)
    assert pagos["quincena_15"] == 800 and pagos["fin_de_mes"] == 800


def test_planilla_propia_reemplaza_a_la_automatica():
    esc = Escenario(formal=False, sueldo_dueno=False, planilla=(
        Trabajador("Cocinera", 1500), Trabajador("Ayudante", 45, "diario", dias=26),
        Trabajador("Mozo", 40, "diario", area="salon", cantidad=2, dias=26)))
    m = modelo(LOCAL, 80, esc, NAC)
    assert m.personal == 1500 + 45 * 26 + 2 * 40 * 26
    assert (m.cocina, m.mozos) == (2, 2)


def test_tornado_ordena_y_el_quiebre_deja_la_utilidad_en_cero():
    esc = Escenario()
    filas = tornado(LOCAL, esc, 100, NAC)
    assert filas[0]["rango"] >= filas[-1]["rango"]
    assert {f["variable"] for f in filas} >= {"precio", "q", "insumos", "sueldos"}
    c = quiebre("precio", LOCAL, esc, 100, NAC)
    assert c is not None and c < 0
    assert modelo(LOCAL.con(precio=LOCAL.precio * (1 + c)), 100, esc, NAC).util == pytest.approx(0, abs=1)
    mz = matriz(LOCAL, esc, 100, NAC)
    assert len(mz["utilidad"]) == len(mz["volumenes"]) and len(mz["utilidad"][0]) == len(mz["precios"])


POLLO = InsumoR(1, "Pollo", "kg", 10.0, merma=0.2)
ARROZ = InsumoR(2, "Arroz", "kg", 4.0)
PAPA = InsumoR(3, "Papa", "kg", 2.0, merma=0.1)
INS = [POLLO, ARROZ, PAPA]


def test_costo_por_porcion_con_merma_y_menu_con_entrada():
    pollo = PlatoR(1, "Arroz con pollo", "segundo", 10, precio=11.0, vendidos=60,
                   items=((1, 2.0), (2, 1.0)))  # 2 kg netos de pollo = 2.5 kg comprados
    causa = PlatoR(2, "Causa", "entrada", 10, items=((3, 1.8),))
    r = analizar(INS, [pollo, causa], igv=10.5)
    f = {p["nombre"]: p for p in r["platos"]}
    assert f["Arroz con pollo"]["costo_porcion"] == pytest.approx((2 * 10 / 0.8 + 4) / 10)
    assert f["Causa"]["costo_porcion"] == pytest.approx(1.8 * 2 / 0.9 / 10)
    assert f["Arroz con pollo"]["costo_venta"] == pytest.approx(2.9 + 0.4)
    assert f["Arroz con pollo"]["margen"] == pytest.approx(11 / 1.105 - 3.3, abs=1e-3)
    assert r["menu"]["costo"] == pytest.approx(3.3)


def test_ingenieria_de_menu_y_pareto():
    a = PlatoR(1, "A", "segundo", 1, precio=12, vendidos=100, items=((1, 0.1),))  # popular, margen alto
    b = PlatoR(2, "B", "segundo", 1, precio=11, vendidos=90, items=((1, 0.3),))  # popular, margen bajo
    c = PlatoR(3, "C", "segundo", 1, precio=13, vendidos=5, items=((2, 0.1),))  # poco vendido, margen alto
    d = PlatoR(4, "D", "segundo", 1, precio=10, vendidos=5, items=((1, 0.4),))  # poco y bajo
    r = analizar(INS, [a, b, c, d], igv=10.5)
    clases = {p["nombre"]: p["clase"] for p in r["platos"]}
    assert clases == {"A": "estrella", "B": "caballo", "C": "rompecabezas", "D": "perro"}
    assert r["pareto"][0]["insumo"] == "Pollo" and r["pareto"][-1]["acumulado"] == pytest.approx(1)


def test_turno_noche_suma_ventas_gas_luz_y_su_equipo():
    from motor.modelo import Noche
    dia = modelo(LOCAL, 80, Escenario(), NAC)
    n = Noche(q=30, precio=12, insumos=4.5, balones=2, servicios=150)
    ambos = modelo(LOCAL, 80, Escenario(noche=n), NAC)
    assert ambos.ventas == pytest.approx(dia.ventas + 12 * 30 * 26)
    assert ambos.gas == pytest.approx(dia.gas + 2 * LOCAL.gas_balon45)
    assert ambos.personal > dia.personal and ambos.cocina > dia.cocina
    # noche solo 3 días por semana: equipo pagado por esa parte del mes
    corta = modelo(LOCAL, 80, Escenario(noche=n.con(dias=13)), NAC)
    assert dia.personal < corta.personal < ambos.personal
    # con planilla propia la noche no agrega gente sola
    plan = Escenario(planilla=(Trabajador("Cocinero", 1500),))
    assert modelo(LOCAL, 80, replace(plan, noche=n), NAC).personal == modelo(LOCAL, 80, plan, NAC).personal
    pagos = calendario_pagos(LOCAL, Escenario(noche=n), NAC, dia.cocina, dia.mozos)
    assert pagos["por_turno"]["noche"] > 0


def test_plato_sin_receta_no_baja_los_promedios():
    a = PlatoR(1, "A", "segundo", 1, precio=11, vendidos=50, items=((1, 0.3),))
    vacio = PlatoR(2, "Sin receta", "segundo", 1, precio=11, vendidos=50)
    r = analizar(INS, [a, vacio], igv=10.5)
    assert r["sin_receta"] == ["Sin receta"]
    assert r["menu"]["costo"] == pytest.approx(0.3 * 10 / 0.8)
    assert all(p["clase"] is None for p in r["platos"])


def test_medio_tiempo_prorratea_el_minimo_y_la_planilla_se_separa_del_igv():
    medio = Trabajador("Mozo", 700, area="salon", jornada=0.5)
    assert costo_trabajador(medio, formal=True, rmv=1230, mult=1.0, dias_local=26) == 700  # 700 > 615
    assert costo_trabajador(Trabajador("Mozo", 500, jornada=0.5), True, 1230, 1.0, 26) == 615
    con_ruc_pago_directo = Escenario(formal=True, laboral_formal=False, sueldo_dueno=False,
                                     planilla=(Trabajador("Ayudante", 1000),))
    m = modelo(LOCAL, 80, con_ruc_pago_directo, NAC)
    assert m.t > 0 and m.personal == 1000  # cobra IGV, pero sin mínimo ni cargas
    assert modelo(LOCAL, 80, replace(con_ruc_pago_directo, laboral_formal=True), NAC).personal == 1230 * NAC["mult_micro"]
