"""Comparar negocios a igualdad de condiciones.

Cada restaurante tipo tiene su precio, su volumen y su alquiler, así que al
compararlos se mezcla todo: no se sabe si uno gana por cómo se organiza o
porque vende más caro. Igualar esos números deja a la vista lo que de verdad
los separa: quién trabaja, cómo se le paga, si es formal y si abre de noche.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from math import factorial

# El local de referencia: el del propietario que cocina (menú popular de Juliaca)
BASE = {"precio": 10.0, "q": 60, "alquiler_mes": 1200.0, "insumos": 4.3, "balones": 4, "servicios_mes": 350.0}
CAMPOS = tuple(BASE)


def igualar(datos: dict, base: dict | None = None) -> dict:
    """Copia del escenario guardado con precio, volumen, alquiler, insumos
    por menú, gas y luz reemplazados por los de la base. Lo demás (planilla,
    sueldo del dueño, formalidad, turno noche) queda como está."""
    cambios = BASE if base is None else {k: v for k, v in base.items() if k in CAMPOS and v is not None}
    salida = deepcopy(datos)
    salida.setdefault("escenario", {}).update(cambios)
    return salida


def personas_casa(escenario: dict) -> int:
    """Cuántas personas de la casa viven de la utilidad: los que trabajan sin
    sueldo en la planilla más el dueño, si se paga un sueldo (porque trabaja)."""
    sin_sueldo = sum(t.get("cantidad", 1) for t in escenario.get("planilla") or [] if not t.get("monto"))
    return sin_sueldo + (1 if escenario.get("sueldo_dueno") else 0)


# Factores en que se diferencian dos negocios. Interactúan (el IGV pesa más
# cuanto más se vende), así que el aporte de cada uno se reparte con valores
# de Shapley: el promedio de su efecto sobre todos los órdenes posibles.
GRUPOS = (
    ("local", "Local y venta", ("ciudad_id", "zona_id", "precio", "q", "dias", "alquiler_mes", "balones",
                                "gas_balon45", "servicios_mes")),
    ("insumos", "Insumos por menú", ("insumos", "segmento")),
    ("personal", "Quién trabaja y cuánto se le paga", ("planilla", "sueldo_dueno", "sueldo_cocinero",
                                                      "sueldo_ayudante", "sueldo_mozo")),
    ("formalidad", "Formalidad (IGV y planilla en regla)", ("formal", "laboral_formal")),
    ("noche", "Turno noche", ("noche",)),
)


def mezclar(desde: dict, hasta: dict, grupos: set[str]) -> dict:
    """El escenario `desde` con los campos de los grupos indicados tomados de
    `hasta`. Lo que ningún grupo cubre (año, etc.) se toma siempre de `hasta`."""
    cubiertos = {c for _, _, campos in GRUPOS for c in campos}
    salida = {k: v for k, v in hasta.items() if k not in cubiertos}
    for clave, _texto, campos in GRUPOS:
        fuente = hasta if clave in grupos else desde
        salida.update({c: fuente[c] for c in campos if c in fuente})
    return salida


def shapley(valor, desde: dict, hasta: dict) -> dict[str, float]:
    """Cuánto aporta cada grupo a la diferencia valor(hasta) − valor(desde).
    Los aportes suman exactamente esa diferencia."""
    claves = [c for c, _, _ in GRUPOS]
    n = len(claves)
    cache: dict[frozenset, float] = {}

    def v(conjunto: frozenset) -> float:
        if conjunto not in cache:
            cache[conjunto] = valor(mezclar(desde, hasta, set(conjunto)))
        return cache[conjunto]

    aportes = {}
    for i in claves:
        otros = [c for c in claves if c != i]
        total = 0.0
        for k in range(n):
            for sub in combinations(otros, k):
                peso = factorial(k) * factorial(n - k - 1) / factorial(n)
                total += peso * (v(frozenset(sub) | {i}) - v(frozenset(sub)))
        aportes[i] = total
    return aportes
