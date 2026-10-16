"""Cuándo sale la plata del personal en el mes: jornales cada día que se
trabaja, quincena el 15 y fin de mes. Mensual y quincenal cuestan lo mismo;
lo que cambia es cuánta caja hay que tener cada fecha."""
from __future__ import annotations

from .modelo import ANIOS, Escenario, Local, costo_trabajador


def calendario_pagos(local: Local, esc: Escenario, nacional: dict, cocina: int, mozos: int) -> dict:
    anio = ANIOS.get(esc.anio, ANIOS[max(ANIOS)])
    rmv = anio["rmv"]
    mult = nacional["mult_micro"] if esc.formal else 1.0
    por_dia = dia_15 = fin_mes = aportes = 0.0
    filas = []
    if esc.planilla:
        for t in esc.planilla:
            total = costo_trabajador(t, esc.formal, rmv, 1.0, esc.dias)  # lo que recibe el trabajador
            aportes += total * (mult - 1)
            if t.modalidad == "diario":
                dias = t.dias if t.dias is not None else esc.dias
                por_dia += total / dias if dias else 0
            elif t.modalidad == "quincenal":
                dia_15 += total / 2
                fin_mes += total / 2
            else:
                fin_mes += total
            filas.append({"puesto": t.puesto, "cantidad": t.cantidad, "modalidad": t.modalidad,
                          "area": t.area, "costo_mes": round(total * (mult if esc.formal else 1), 2)})
    else:
        def w(x: float) -> float:
            return max(x, rmv) if esc.formal else x
        cocinero = max(local.sueldo_cocinero, rmv * 1.06) if esc.formal else local.sueldo_cocinero
        partes = [("Cocinero", 1, cocinero, "cocina"), ("Ayudante de cocina", cocina - 1, w(local.sueldo_ayudante), "cocina"),
                  ("Mozo", mozos, w(local.sueldo_mozo), "salon")]
        for puesto, n, sueldo, area in partes:
            if n <= 0:
                continue
            fin_mes += sueldo * n
            aportes += sueldo * n * (mult - 1)
            filas.append({"puesto": puesto, "cantidad": n, "modalidad": "mensual", "area": area,
                          "costo_mes": round(sueldo * n * mult, 2)})
    return {
        "jornales_por_dia": round(por_dia, 2),
        "quincena_15": round(dia_15, 2),
        "fin_de_mes": round(fin_mes, 2),
        "aportes_fin_de_mes": round(aportes, 2),
        "filas": filas,
    }
