"""Flujo de caja a 10 años de un local de menú, por régimen tributario.

Mes a mes con el mismo `modelo` del equilibrio, pero cada año con su IGV,
su sueldo mínimo y sus costos inflados, más la curva de arranque (el local
nuevo no se llena el primer día) y el impuesto de cada régimen.

Lo que NO es ley va marcado como supuesto en `SUPUESTOS` y se puede mover
desde el panel: el IGV de restaurantes desde 2028 (18 %), cómo sube el
sueldo mínimo después de 2028, la tasa de descuento, la inflación.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .modelo import OTROS_FIJOS, SUELDO_DUENO, Escenario, Local, modelo

HORIZONTE = 10
REGIMENES = ("informal", "nuevo_rus", "rer", "mype")
NOMBRE_REGIMEN = {
    "informal": "Informal (sin RUC)",
    "nuevo_rus": "Nuevo RUS",
    "rer": "Régimen Especial (RER)",
    "mype": "Régimen MYPE Tributario",
}
# Topes anuales de ventas (soles). NRUS: S/ 96 mil; RER: S/ 525 mil.
TOPE_NRUS = 96_000
TOPE_NRUS_CAT1_MES = 5_000  # categoría 1: cuota S/ 20; hasta S/ 8 mil al mes: S/ 50
CUOTA_NRUS = (20, 50)
TASA_RER = 0.015  # 1.5 % de los ingresos netos, mensual y cancelatorio
TOPE_RER = 525_000
# MYPE: 10 % hasta 15 UIT de renta neta, 29.5 % por encima
TRAMO_MYPE_UIT, TASA_MYPE_1, TASA_MYPE_2 = 15, 0.10, 0.295
VIDA_UTIL = 10  # años para depreciar la inversión (equipos y mobiliario)

SUPUESTOS = {
    "igv_2028_en_adelante": "18 %: la ley del IGV reducido para restaurantes llega hasta 2027",
    "rmv_despues_2028": "S/ 1,300 en 2027–2028 y luego sube a la tasa elegida (saltos de ~9–10 % cada 2–3 años ≈ 3.7 %/año)",
    "precio": "sube con la tasa elegida y se redondea a S/ 0.50, como en las pizarras",
    "valor_residual": "cero: al año 10 no se vende el local (conservador)",
    "perdidas": "en el MYPE una pérdida no paga renta, pero no se arrastra a años siguientes",
}


@dataclass(frozen=True)
class Supuestos:
    anio_inicio: int = 2026
    inversion: float = 30_000  # lo que costó montar el local
    q: float = 100  # menús/día cuando el local ya se llenó
    meses_arranque: int = 6  # meses hasta llegar a q
    arranque_desde: float = 0.4  # fracción de q en el primer mes
    crecimiento_q: float = 0.0  # crecimiento real anual de la clientela
    inflacion: float = 0.025  # costos (BCRP 2027–2030: 2.0–2.5 %)
    alza_precio: float = 0.025  # el precio de la pizarra
    alza_rmv: float = 0.037  # después de 2028
    tasa_descuento: float = 0.15  # lo que te rendiría la plata en otro lado, con riesgo
    regimen: str = "mype"


@dataclass
class Anio:
    anio: int
    igv: float
    rmv: float
    precio: float
    menus_dia: float
    ventas: float  # con IGV, lo que entra a caja
    igv_pagado: float
    utilidad_operativa: float  # ventas sin IGV − costos (incluye tu sueldo si se marcó)
    impuesto: float  # renta o cuota del régimen
    flujo: float
    acumulado: float
    descontado_acumulado: float


@dataclass
class Flujo:
    regimen: str
    anios: list[Anio]
    van: float
    tir: float | None
    recupero: float | None  # años
    recupero_descontado: float | None
    alertas: list[str] = field(default_factory=list)


def igv_de(anio: int) -> float:
    return {2026: 10.5, 2027: 15.0}.get(anio, 18.0)


def rmv_de(anio: int, alza: float) -> float:
    if anio <= 2026:
        return 1230.0
    if anio <= 2028:
        return 1300.0
    return 1300.0 * (1 + alza) ** (anio - 2028)


def _medio_sol(x: float) -> float:
    return math.floor(x * 2 + 0.5) / 2


def _impuesto_anual(regimen: str, ventas_netas: float, utilidad: float, depreciacion: float,
                    uit: float, ventas_mes: list[float]) -> float:
    if regimen == "informal":
        return 0.0
    if regimen == "nuevo_rus":
        return sum(CUOTA_NRUS[0] if v <= TOPE_NRUS_CAT1_MES else CUOTA_NRUS[1] for v in ventas_mes)
    if regimen == "rer":
        return TASA_RER * ventas_netas
    renta = utilidad - depreciacion
    if renta <= 0:
        return 0.0
    tramo = TRAMO_MYPE_UIT * uit
    return TASA_MYPE_1 * min(renta, tramo) + TASA_MYPE_2 * max(0.0, renta - tramo)


def flujo_caja(local: Local, esc: Escenario, nacional: dict, sup: Supuestos) -> Flujo:
    """Flujo anual de 10 años para un régimen. El año 0 es la inversión."""
    regimen = sup.regimen
    if regimen not in REGIMENES:
        raise ValueError(f"Régimen: {', '.join(REGIMENES)}")
    # Informal: sin IGV y planilla a lo que se pague en la calle. Nuevo RUS:
    # sin IGV pero con planilla formal. RER y MYPE: IGV de restaurantes.
    formal = regimen != "informal"
    esc = Escenario(segmento=esc.segmento, anio=esc.anio, formal=formal, balones=esc.balones,
                    sueldo_dueno=esc.sueldo_dueno)
    uit0 = nacional.get("uit_2026", 5500)
    r = sup.tasa_descuento
    depreciacion = sup.inversion / VIDA_UTIL
    anios: list[Anio] = []
    acumulado, descontado = -sup.inversion, -sup.inversion
    alertas: list[str] = []
    for y in range(HORIZONTE):
        anio = sup.anio_inicio + y
        f = (1 + sup.inflacion) ** y
        igv = 0.0 if regimen == "nuevo_rus" else igv_de(anio)
        rmv = rmv_de(anio, sup.alza_rmv)
        precio = _medio_sol(local.precio * (1 + sup.alza_precio) ** y)
        local_y = local.con(
            precio=precio, insumos=local.insumos * f, alquiler_mes=local.alquiler_mes * f,
            servicios_mes=local.servicios_mes * f, gas_balon45=local.gas_balon45 * f,
            sueldo_cocinero=local.sueldo_cocinero * f, sueldo_ayudante=local.sueldo_ayudante * f,
            sueldo_mozo=local.sueldo_mozo * f,
        )
        ventas = igv_pagado = utilidad = menus = 0.0
        ventas_mes: list[float] = []
        for m in range(12):
            k = 12 * y + m
            rampa = 1.0
            if sup.meses_arranque > 0 and k < sup.meses_arranque:
                rampa = sup.arranque_desde + (1 - sup.arranque_desde) * k / sup.meses_arranque
            q = max(1.0, sup.q * rampa * (1 + sup.crecimiento_q) ** y)
            res = modelo(local_y, q, esc, nacional, igv=igv, rmv=rmv, otros_fijos=OTROS_FIJOS * f,
                         sueldo_dueno=SUELDO_DUENO * f)
            ventas += res.ventas
            ventas_mes.append(res.ventas)
            igv_pagado += res.ventas - res.p_net * res.q_mes
            utilidad += res.util
            menus += q
        ventas_netas = ventas - igv_pagado
        impuesto = _impuesto_anual(regimen, ventas_netas, utilidad, depreciacion, uit0 * f, ventas_mes)
        flujo = utilidad - impuesto
        acumulado += flujo
        descontado += flujo / (1 + r) ** (y + 1)
        anios.append(Anio(anio, igv, round(rmv, 2), precio, round(menus / 12, 1), round(ventas, 2),
                          round(igv_pagado, 2), round(utilidad, 2), round(impuesto, 2), round(flujo, 2),
                          round(acumulado, 2), round(descontado, 2)))
        if regimen == "nuevo_rus" and ventas > TOPE_NRUS and "nrus" not in alertas:
            alertas.append("nrus")
        if regimen == "rer" and ventas_netas > TOPE_RER and "rer" not in alertas:
            alertas.append("rer")
    flujos = [-sup.inversion] + [a.flujo for a in anios]
    return Flujo(
        regimen=regimen,
        anios=anios,
        van=round(van(flujos, r), 2),
        tir=tir(flujos),
        recupero=recupero(flujos),
        recupero_descontado=recupero(flujos, r),
        alertas=[TEXTO_ALERTA[a] for a in alertas],
    )


TEXTO_ALERTA = {
    "nrus": "Con estas ventas no puedes estar en el Nuevo RUS: el tope es S/ 96 mil al año (S/ 8 mil al mes).",
    "rer": "Con estas ventas no puedes estar en el RER: el tope es S/ 525 mil al año.",
}


def van(flujos: list[float], r: float) -> float:
    return sum(f / (1 + r) ** t for t, f in enumerate(flujos))


def tir(flujos: list[float]) -> float | None:
    """Tasa que deja el VAN en cero (bisección). None si no cambia de signo."""
    bajo, alto = -0.99, 10.0
    v_bajo, v_alto = van(flujos, bajo), van(flujos, alto)
    if v_bajo * v_alto > 0:
        return None
    for _ in range(200):
        medio = (bajo + alto) / 2
        v = van(flujos, medio)
        if v_bajo * v <= 0:
            alto = medio
        else:
            bajo, v_bajo = medio, v
    return round((bajo + alto) / 2, 4)


def recupero(flujos: list[float], r: float = 0.0) -> float | None:
    """Años hasta recuperar la inversión (con fracción). None si no se recupera."""
    acumulado = flujos[0]
    if acumulado >= 0:
        return 0.0
    for t, f in enumerate(flujos[1:], start=1):
        f = f / (1 + r) ** t
        if acumulado + f >= 0:
            return round(t - 1 + (-acumulado / f), 2)
        acumulado += f
    return None


def comparar_regimenes(local: Local, esc: Escenario, nacional: dict, sup: Supuestos) -> list[dict]:
    from dataclasses import replace
    salida = []
    for reg in REGIMENES:
        fl = flujo_caja(local, esc, nacional, replace(sup, regimen=reg))
        salida.append({
            "regimen": reg, "nombre": NOMBRE_REGIMEN[reg], "van": fl.van, "tir": fl.tir,
            "recupero": fl.recupero, "impuestos_10a": round(sum(a.impuesto + a.igv_pagado for a in fl.anios), 2),
            "flujo_10a": round(sum(a.flujo for a in fl.anios), 2), "alertas": fl.alertas,
        })
    return salida
