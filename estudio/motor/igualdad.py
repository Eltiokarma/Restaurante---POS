"""Comparar negocios a igualdad de condiciones.

Cada restaurante tipo tiene su precio, su volumen y su alquiler, así que al
compararlos se mezcla todo: no se sabe si uno gana por cómo se organiza o
porque vende más caro. Igualar esos números deja a la vista lo que de verdad
los separa: quién trabaja, cómo se le paga, si es formal y si abre de noche.
"""
from __future__ import annotations

from copy import deepcopy

# El local de referencia: el de la dueña que cocina (menú popular de Juliaca)
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
