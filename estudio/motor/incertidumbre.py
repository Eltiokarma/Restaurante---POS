"""¿Cuánto dependen las conclusiones de los supuestos?

Los restaurantes tipo son números razonados, no observados. Para saber si un
hallazgo es una conclusión o una opinión, se repite el cálculo muchas veces
moviendo esos números al azar dentro de rangos razonables y se cuenta en qué
parte de los sorteos se sostiene.
"""
from __future__ import annotations

import random
from copy import deepcopy

# Cuánto puede equivocarse cada número de un caso (±, uniforme)
RANGOS = {
    "precio": 0.05,
    "q": 0.20,
    "insumos": 0.10,
    "alquiler_mes": 0.25,
    "sueldos": 0.10,
    "balones": 0.20,
    "servicios_mes": 0.20,
}
SUELDOS = ("sueldo_cocinero", "sueldo_ayudante", "sueldo_mozo")


def perturbar(datos: dict, rng: random.Random, rangos: dict = RANGOS) -> dict:
    """Copia del escenario guardado con sus números movidos al azar. Los
    sueldos se mueven juntos (el mercado laboral sube o baja para todos), y
    quien trabaja sin sueldo sigue sin sueldo."""
    salida = deepcopy(datos)
    e = salida["escenario"]

    def factor(clave: str) -> float:
        r = rangos.get(clave, 0)
        return 1 + rng.uniform(-r, r)

    for clave in ("precio", "q", "insumos", "alquiler_mes", "balones", "servicios_mes"):
        if e.get(clave) is not None:
            e[clave] = e[clave] * factor(clave)
    f_sueldo = factor("sueldos")
    for clave in SUELDOS:
        if e.get(clave) is not None:
            e[clave] = e[clave] * f_sueldo
    for t in e.get("planilla") or []:
        t["monto"] = t["monto"] * f_sueldo
    return salida

