"""El trabajo que no se cobra.

La utilidad contable de una fonda familiar no descuenta el trabajo de quienes
no tienen sueldo (o se pagan menos de lo que costaría contratarlos). La
utilidad económica sí: le resta a lo que se lleva la casa lo que valdría ese
trabajo si se pagara a precio de mercado. Si sale negativa, el negocio vive de
un subsidio de la familia.
"""
from __future__ import annotations

from dataclasses import dataclass

SEMANAS_MES = 4.33
JORNADA_LEGAL = 48  # horas a la semana
RECARGO_EXTRA = 0.25  # sobretiempo: la ley paga 25 % las dos primeras horas y 35 % las demás

# Sueldo de mercado al mes por puesto, a jornada completa. Los de cocina y
# salón salen del local (ciudad o escenario); el de administración, de lo que
# paga el inversor ausente por un administrador.
SUELDO_ADMINISTRADOR = 2200.0


@dataclass(frozen=True)
class Persona:
    quien: str
    rol: str  # cocinero | ayudante | mozo | administrador
    horas_semana: float


def sueldo_mercado(rol: str, local) -> float:
    return {"cocinero": local.sueldo_cocinero, "ayudante": local.sueldo_ayudante,
            "mozo": local.sueldo_mozo, "administrador": SUELDO_ADMINISTRADOR}[rol]


def valor_mercado(p: Persona, local) -> float:
    """Lo que costaría al mes contratar a alguien para ese puesto y esas horas
    (las horas sobre la jornada legal, con su recargo)."""
    por_hora = sueldo_mercado(p.rol, local) / (JORNADA_LEGAL * SEMANAS_MES)
    normales = min(p.horas_semana, JORNADA_LEGAL)
    extra = max(0.0, p.horas_semana - JORNADA_LEGAL)
    return por_hora * SEMANAS_MES * (normales + extra * (1 + RECARGO_EXTRA))


def trabajo_de_la_casa(casa: list[Persona], ingreso_casa: float, local, inversion: float = 0.0,
                      tasa_anual: float = 0.15) -> dict:
    """Indicadores del trabajo no cobrado. `ingreso_casa` es lo que se lleva
    la casa: utilidad más el sueldo del dueño si el modelo ya le paga uno. La
    utilidad económica descuenta además lo que rendiría la inversión en otro
    lado (la tasa de descuento del flujo)."""
    horas = sum(p.horas_semana for p in casa) * SEMANAS_MES
    valor = sum(valor_mercado(p, local) for p in casa)
    capital = inversion * tasa_anual / 12
    return {
        "personas": len(casa),
        "horas_mes": horas,
        "valor_mercado": valor,
        "costo_capital": capital,
        "utilidad_economica": ingreso_casa - valor - capital,
        "por_hora": ingreso_casa / horas if horas else None,
        "mercado_por_hora": valor / horas if horas else None,
        # parte del valor de su trabajo que la casa de verdad se lleva
        "parte_cobrada": ingreso_casa / valor if valor else None,
    }


def casa_desde(datos: dict) -> list[Persona]:
    """Quiénes de la casa trabajan en el negocio (campo `casa` del escenario
    guardado: [{"quien", "rol", "horas_semana"}])."""
    return [Persona(x["quien"], x["rol"], float(x["horas_semana"])) for x in datos.get("casa") or []]
