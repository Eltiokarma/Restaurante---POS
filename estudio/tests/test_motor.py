"""Regresión contra los valores de referencia del BRIEF (popular, 2026,
formal, 100 menús/día, 5 balones, SIN sueldo del dueño)."""
import pytest

from motor import Escenario, cargar_dataset, equilibrio, local_de_ciudad, modelo, precio_minimo

DATA = cargar_dataset()
CIUDAD = {c["id"]: c for c in DATA["ciudades"]}
ESC = Escenario(segmento="popular", anio=2026, formal=True, balones=5, sueldo_dueno=False)

REFERENCIA = {
    "lima": 57, "arequipa": 65, "ica": 66, "piura": 84, "cusco": 86, "trujillo": 87,
    "huancayo": 94, "tacna": 94, "iquitos": 96, "chiclayo": 98, "puno": 108, "juliaca": 138,
}


@pytest.mark.parametrize("ciudad,esperado", REFERENCIA.items())
def test_equilibrio_de_referencia(ciudad, esperado):
    assert equilibrio(local_de_ciudad(CIUDAD[ciudad]), ESC, DATA["nacional"]) == esperado


def test_frontera_de_precio_es_utilidad_cero():
    local = local_de_ciudad(CIUDAD["lima"])
    p = precio_minimo(local, 100, ESC, DATA["nacional"])
    assert abs(modelo(local, 100, ESC, DATA["nacional"], precio=p).util) < 1e-6


def test_informal_no_paga_igv_ni_cargas():
    local = local_de_ciudad(CIUDAD["juliaca"])
    formal = modelo(local, 100, ESC, DATA["nacional"])
    informal = modelo(local, 100, Escenario(formal=False, sueldo_dueno=False), DATA["nacional"])
    assert informal.t == 0 and informal.p_net == local.precio
    assert informal.util > formal.util


def test_precio_observado_mueve_juliaca():
    """Juliaca está a S/ 8 en el dataset (estimado y mal); a S/ 11 el
    equilibrio baja mucho. Cifra sólo de control, no de calibración."""
    local = local_de_ciudad(CIUDAD["juliaca"], precio=11)
    assert equilibrio(local, ESC, DATA["nacional"]) < 138
