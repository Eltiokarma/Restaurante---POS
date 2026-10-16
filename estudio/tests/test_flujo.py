"""Flujo de caja a 10 años: cuadra con el modelo mensual y con la teoría."""
from dataclasses import replace

import pytest

from motor import Escenario, cargar_dataset, local_de_ciudad, modelo
from motor.flujo import Supuestos, comparar_regimenes, flujo_caja, recupero, tir, van

DATA = cargar_dataset()
NACIONAL = DATA["nacional"]
JULIACA = next(c for c in DATA["ciudades"] if c["id"] == "juliaca")
LOCAL = local_de_ciudad(JULIACA, precio=11.0)
QUIETO = Supuestos(q=100, meses_arranque=0, inflacion=0, alza_precio=0, alza_rmv=0, regimen="rer")


def test_sin_arranque_ni_inflacion_el_primer_anio_es_12_meses_del_modelo():
    fl = flujo_caja(LOCAL, Escenario(), NACIONAL, QUIETO)
    mes = modelo(LOCAL, 100, Escenario(anio=2026), NACIONAL)
    assert fl.anios[0].utilidad_operativa == pytest.approx(12 * mes.util, abs=0.05)
    assert fl.anios[0].ventas == pytest.approx(12 * mes.ventas)
    # RER: 1.5 % de las ventas sin IGV
    assert fl.anios[0].impuesto == pytest.approx(0.015 * 12 * mes.p_net * mes.q_mes, abs=0.05)


def test_el_igv_sube_por_anio_y_el_nuevo_rus_no_lo_cobra():
    fl = flujo_caja(LOCAL, Escenario(), NACIONAL, QUIETO)
    assert [a.igv for a in fl.anios[:4]] == [10.5, 15.0, 18.0, 18.0]
    assert [a.rmv for a in fl.anios[:3]] == [1230, 1300, 1300]
    rus = flujo_caja(LOCAL, Escenario(), NACIONAL, replace(QUIETO, regimen="nuevo_rus"))
    assert all(a.igv == 0 and a.igv_pagado == 0 for a in rus.anios)
    assert rus.alertas  # 100 menús a S/ 11 pasan largo el tope de S/ 96 mil


def test_curva_de_arranque_baja_el_primer_anio():
    lleno = flujo_caja(LOCAL, Escenario(), NACIONAL, QUIETO)
    arranca = flujo_caja(LOCAL, Escenario(), NACIONAL, replace(QUIETO, meses_arranque=6, arranque_desde=0.4))
    assert arranca.anios[0].menus_dia < lleno.anios[0].menus_dia
    assert arranca.anios[1].flujo == pytest.approx(lleno.anios[1].flujo)


def test_mype_paga_renta_solo_si_gana():
    sup = replace(QUIETO, regimen="mype", q=30)  # muy por debajo del equilibrio
    assert all(a.impuesto == 0 for a in flujo_caja(LOCAL, Escenario(), NACIONAL, sup).anios)


def test_informal_no_paga_igv_ni_renta_y_por_eso_rinde_mas():
    comp = {c["regimen"]: c for c in comparar_regimenes(LOCAL, Escenario(), NACIONAL, QUIETO)}
    assert comp["informal"]["impuestos_10a"] == 0
    assert comp["informal"]["van"] > comp["mype"]["van"]


def test_van_tir_y_recupero():
    flujos = [-100, 60, 60]
    assert van(flujos, 0) == 20
    t = tir(flujos)
    assert van(flujos, t) == pytest.approx(0, abs=0.01)
    assert recupero(flujos) == pytest.approx(1 + 40 / 60, abs=0.01)
    assert recupero([-100, 10, 10]) is None
    assert tir([-100, -10]) is None
