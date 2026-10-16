"""Cuándo sale la plata del personal en el mes: jornales cada día que se
trabaja, quincena el 15 y fin de mes. Mensual y quincenal cuestan lo mismo;
lo que cambia es cuánta caja hay que tener cada fecha."""
from __future__ import annotations

import math

from .modelo import ANIOS, Escenario, Local, costo_trabajador


def calendario_pagos(local: Local, esc: Escenario, nacional: dict, cocina: int, mozos: int) -> dict:
    """`cocina` y `mozos`: el equipo del DÍA (el de noche se arma aquí)."""
    anio = ANIOS.get(esc.anio, ANIOS[max(ANIOS)])
    rmv = anio["rmv"]
    mult = nacional["mult_micro"] if esc.laboral else 1.0
    por_dia = dia_15 = fin_mes = aportes = 0.0
    por_turno = {"dia": 0.0, "noche": 0.0, "ambos": 0.0}
    filas = []
    if esc.planilla:
        for t in esc.planilla:
            total = costo_trabajador(t, esc.laboral, rmv, 1.0, esc.dias)  # lo que recibe el trabajador
            aportes += total * (mult - 1)
            if t.modalidad == "diario":
                dias = t.dias if t.dias is not None else esc.dias
                por_dia += total / dias if dias else 0
            elif t.modalidad == "quincenal":
                dia_15 += total / 2
                fin_mes += total / 2
            else:
                fin_mes += total
            costo = total * (mult if esc.laboral else 1)
            por_turno[t.turno] = por_turno.get(t.turno, 0.0) + costo
            filas.append({"puesto": t.puesto, "cantidad": t.cantidad, "modalidad": t.modalidad,
                          "area": t.area, "turno": t.turno, "costo_mes": round(costo, 2)})
    else:
        def w(x: float) -> float:
            return max(x, rmv) if esc.laboral else x
        cocinero = max(local.sueldo_cocinero, rmv * 1.06) if esc.laboral else local.sueldo_cocinero
        partes = [("Cocinero", 1, cocinero, "cocina", "dia"),
                  ("Ayudante de cocina", cocina - 1, w(local.sueldo_ayudante), "cocina", "dia"),
                  ("Mozo", mozos, w(local.sueldo_mozo), "salon", "dia")]
        n = esc.noche
        if n is not None and n.q > 0:
            pop = esc.pop
            dias_n = n.dias if n.dias is not None else esc.dias
            parte = min(1.0, dias_n / esc.dias) if esc.dias else 1.0
            cocina_n = max(1, math.ceil(n.q / (80 if pop else 55)))
            mozos_n = max(1, math.ceil(n.q / (70 if pop else 40)))
            partes += [("Cocinero de noche", 1, cocinero * parte, "cocina", "noche"),
                       ("Ayudante de noche", cocina_n - 1, w(local.sueldo_ayudante) * parte, "cocina", "noche"),
                       ("Mozo de noche", mozos_n, w(local.sueldo_mozo) * parte, "salon", "noche")]
        for puesto, cant, sueldo, area, turno in partes:
            if cant <= 0:
                continue
            fin_mes += sueldo * cant
            aportes += sueldo * cant * (mult - 1)
            por_turno[turno] += sueldo * cant * mult
            filas.append({"puesto": puesto, "cantidad": cant, "modalidad": "mensual", "area": area,
                          "turno": turno, "costo_mes": round(sueldo * cant * mult, 2)})
    return {
        "jornales_por_dia": round(por_dia, 2),
        "quincena_15": round(dia_15, 2),
        "fin_de_mes": round(fin_mes, 2),
        "aportes_fin_de_mes": round(aportes, 2),
        "filas": filas,
        "por_turno": {k: round(v, 2) for k, v in por_turno.items()},
    }
