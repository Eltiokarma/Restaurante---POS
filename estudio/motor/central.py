"""Cocina central con locales satélite (portado de `centralModel` del
prototipo). Casi todos los parámetros de cocina central son estimados con
confianza baja (ver `data/dataset.json`, bloque `cocina_central`)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .modelo import ANIOS, DESCARTABLES, MERMA, OTROS_FIJOS, SUELDO_DUENO, Escenario, Local, modelo


@dataclass(frozen=True)
class ResultadoCentral:
    util: float
    capex: float
    cocina: int | None = None


def modelo_central(local: Local, esc: Escenario, nacional: dict, cc: dict,
                   q_principal: float, q_satelite: float, n_satelites: int) -> ResultadoCentral:
    pop = esc.pop
    anio = ANIOS[esc.anio]
    principal = modelo(local, q_principal, esc, nacional)
    if n_satelites == 0:
        return ResultadoCentral(principal.util, 0.0)
    total_q = q_principal + n_satelites * q_satelite
    t = principal.t
    mult = nacional["mult_micro"] if esc.laboral else 1.0

    def w(x: float) -> float:
        return max(x, anio["rmv"]) if esc.laboral else x

    var_u = local.insumos * (1 - cc["ahorro_compras"]) * (1 + MERMA) + DESCARTABLES[esc.segmento]
    contrib_u = local.precio / (1 + t) - var_u
    por_trab = cc["menus_por_trabajador_cocina"] if pop else cc["menus_por_trabajador_cocina"] * 0.7
    cocina = max(2, math.ceil(total_q / por_trab))
    cocinero = max(local.sueldo_cocinero, anio["rmv"] * 1.06) if esc.laboral else local.sueldo_cocinero
    mozos_p = max(1, math.ceil(q_principal / (70 if pop else 40)))
    mozos_s = max(1, math.ceil(q_satelite / (70 if pop else 40))) + (1 if q_satelite > (90 if pop else 50) else 0)
    personal = mult * (cocinero + (cocina - 1) * w(local.sueldo_ayudante)
                       + (mozos_p + n_satelites * mozos_s) * w(local.sueldo_mozo))
    personal += SUELDO_DUENO if esc.sueldo_dueno else 0
    alq = local.alquiler_mes * (1 if pop else 1.25)
    fijos = (personal + alq * (1 + 0.8 * n_satelites)
             + local.gas_balon45 * (esc.balones * (total_q / q_principal))
             + local.servicios_mes * (1 + 0.6 * n_satelites) + OTROS_FIJOS
             + cc["costo_transporte_mes"] * math.ceil(n_satelites / 4)
             + cc["overhead_por_local_mes"] * n_satelites)
    util = contrib_u * total_q * esc.dias - fijos
    capex = (25000 if n_satelites <= 2 else cc["capex_cocina_central"]) + cc["capex_satelite"] * n_satelites
    return ResultadoCentral(util, capex, cocina)
