"""Corridas sistemáticas: barrido de decisiones y prueba de estrés.

Barrido de decisiones
    Desde un escenario base se prueban todas las combinaciones de precio,
    calidad (porción), mezcla de segundos (más res o más pollo/pasta) y turno
    noche. Como nadie conoce con certeza cuántos clientes se pierden al subir
    el precio, cada combinación se calcula bajo varias elasticidades de la
    demanda; la decisión *robusta* es la que mejor queda en su peor caso.

    Demanda: q = q0 · (p/p0)^(−ε) · f_calidad. Con ε = 0 el modelo de antes
    (subir el precio no espanta a nadie), que sobrestima lo que deja subir.

Prueba de estrés
    Cada negocio frente a golpes uno por uno y todos juntos.

Todo lo que no es dato va marcado como supuesto en SUPUESTOS.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace

from .flujo import Supuestos, flujo_caja
from .modelo import Escenario, Local, Noche, equilibrio, modelo
from .montecarlo import simular

N_MC = 500  # años simulados por combinación (la interfaz usa 2 000; aquí basta para ordenar)

# (insumos ×, demanda ×): supuestos. Una porción generosa cuesta más y atrae algo más de gente.
CALIDAD = {
    "economica": (0.90, 0.94),
    "estandar": (1.00, 1.00),
    "generosa": (1.12, 1.06),
}
NOMBRE_CALIDAD = {"economica": "Porción económica", "estandar": "Porción estándar", "generosa": "Porción generosa"}
NOCHE_TIPO = Noche(q=30, precio=12, insumos=4.5, dias=None, balones=2, servicios=150)

SUPUESTOS = {
    "elasticidad": "Clientes que se pierden por cada 1 % de alza del precio: 0.5 (clientela fiel), 1.0 y 1.5 (mucha competencia). No hay medición para Juliaca; por eso se prueban las tres.",
    "calidad": "Porción económica: insumos −10 %, clientela −6 %. Generosa: insumos +12 %, clientela +6 %.",
    "mezcla": "Parte de los segundos que son de carne de res; el resto, pollo, pasta y otros, con el costo de las recetas propias.",
    "noche": "Turno noche tipo: 30 platos a S/ 12, insumos S/ 4.50, 2 balones y S/ 150 de luz extra, con su propio equipo.",
    "simulacion": f"{N_MC} años simulados por combinación.",
}


@dataclass(frozen=True)
class Mezcla:
    """Costos por menú (con merma de receta) para armar los insumos según la
    parte de segundos de res. Sale del análisis de platos del local."""
    costo_res: float
    costo_otros: float
    acompanamiento: float  # entrada + refresco promedio
    parte_actual: float

    def insumos(self, parte_res: float) -> float:
        menu = self.acompanamiento + parte_res * self.costo_res + (1 - parte_res) * self.costo_otros
        return menu / 1.05  # el modelo suma 5 % de merma; la receta ya la trae


@dataclass
class Factores:
    precio: list[float] = field(default_factory=lambda: [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])  # soles
    calidad: list[str] = field(default_factory=lambda: ["economica", "estandar", "generosa"])
    mezcla: list[float | None] = field(default_factory=lambda: [None])  # parte de res; None = la actual
    noche: list[bool] = field(default_factory=lambda: [False, True])
    elasticidad: list[float] = field(default_factory=lambda: [0.5, 1.0, 1.5])

    def total(self) -> int:
        return (len(self.precio) * len(self.calidad) * len(self.mezcla) * len(self.noche)
                * len(self.elasticidad))


def _aplicar(local: Local, esc: Escenario, q0: float, delta_precio: float, calidad: str,
             parte_res: float | None, noche: bool, elasticidad: float, mezcla: Mezcla | None):
    p0 = local.precio
    precio = max(1.0, p0 + delta_precio)
    mult_ins, mult_dem = CALIDAD[calidad]
    insumos = mezcla.insumos(parte_res) if (mezcla and parte_res is not None) else local.insumos
    q = q0 * (precio / p0) ** (-elasticidad) * mult_dem
    local2 = local.con(precio=precio, insumos=insumos * mult_ins, precio_propio=True)
    if noche:
        n = esc.noche or NOCHE_TIPO
        n = n.con(precio=n.precio + delta_precio, q=n.q * mult_dem * ((n.precio + delta_precio) / n.precio) ** (-elasticidad),
                  insumos=n.insumos * mult_ins)
        esc2 = replace(esc, noche=n)
    else:
        esc2 = replace(esc, noche=None)
    return local2, esc2, max(1.0, q)


def evaluar(local: Local, esc: Escenario, q: float, nacional: dict, riesgo: dict, sup: Supuestos) -> dict:
    m = modelo(local, q, esc, nacional)
    mc = simular(local, esc, nacional, riesgo, q_ref=round(q), n=N_MC)
    fl = flujo_caja(local, esc, nacional, replace(sup, q=q))
    return {
        "q": round(q, 1), "precio": local.precio, "ventas": round(m.ventas), "utilidad": round(m.util),
        "ingreso_dueno": round(m.util + (1500 if esc.sueldo_dueno else 0)),
        "prob_perdida": round(mc.prob_perdida, 3), "p10": round(mc.p10), "van": round(fl.van),
        "equilibrio": equilibrio(local, esc, nacional),
    }


def barrido(local: Local, esc: Escenario, q0: float, nacional: dict, riesgo: dict, sup: Supuestos,
            f: Factores, mezcla: Mezcla | None = None, avance=None) -> dict:
    """Todas las combinaciones y, por decisión, su resultado medio y en el
    peor caso de demanda."""
    filas = []
    total = f.total()
    for k, (dp, cal, mz, noche, el) in enumerate(itertools.product(f.precio, f.calidad, f.mezcla, f.noche,
                                                                   f.elasticidad)):
        l2, e2, q = _aplicar(local, esc, q0, dp, cal, mz, noche, el, mezcla)
        fila = {"delta_precio": dp, "calidad": cal, "mezcla": mz, "noche": noche, "elasticidad": el}
        fila.update(evaluar(l2, e2, q, nacional, riesgo, sup))
        filas.append(fila)
        if avance and (k % 20 == 0 or k == total - 1):
            avance((k + 1) / total)

    decisiones: dict[tuple, list[dict]] = {}
    for fl in filas:
        decisiones.setdefault((fl["delta_precio"], fl["calidad"], fl["mezcla"], fl["noche"]), []).append(fl)
    resumen = []
    for (dp, cal, mz, noche), gr in decisiones.items():
        resumen.append({
            "delta_precio": dp, "precio": gr[0]["precio"], "calidad": cal, "mezcla": mz, "noche": noche,
            "utilidad_media": round(sum(x["utilidad"] for x in gr) / len(gr)),
            "utilidad_peor": min(x["utilidad"] for x in gr),
            "utilidad_mejor": max(x["utilidad"] for x in gr),
            "prob_perdida_max": max(x["prob_perdida"] for x in gr),
            "van_medio": round(sum(x["van"] for x in gr) / len(gr)),
            "van_peor": min(x["van"] for x in gr),
            "q_min": min(x["q"] for x in gr), "q_max": max(x["q"] for x in gr),
        })
    resumen.sort(key=lambda r: (-r["utilidad_peor"], -r["utilidad_media"]))
    base = next((r for r in resumen if r["delta_precio"] == 0 and r["calidad"] == "estandar"
                 and r["mezcla"] in (None, mezcla.parte_actual if mezcla else None)
                 and r["noche"] == (esc.noche is not None)), None)
    return {"filas": filas, "decisiones": resumen, "base": base, "supuestos": SUPUESTOS,
            "mezcla": None if mezcla is None else {"costo_res": mezcla.costo_res, "costo_otros": mezcla.costo_otros,
                                                   "acompanamiento": mezcla.acompanamiento,
                                                   "parte_actual": mezcla.parte_actual}}


# ---------------------------------------------------------------- estrés

def _sueldos(local: Local, esc: Escenario, x: float):
    local = local.con(sueldo_cocinero=local.sueldo_cocinero * x, sueldo_ayudante=local.sueldo_ayudante * x,
                      sueldo_mozo=local.sueldo_mozo * x)
    return local, replace(esc, planilla=tuple(t.con(monto=t.monto * x) for t in esc.planilla))


def _golpes():
    def demanda(l, e, q):
        return l, e, q * 0.85

    def insumos(l, e, q):
        return l.con(insumos=l.insumos * 1.2), e, q

    def igv(l, e, q):
        return l, replace(e, anio=2028), q

    def sueldos(l, e, q):
        l, e = _sueldos(l, e, 1.10)
        return l, e, q

    def alquiler(l, e, q):
        return l.con(alquiler_mes=l.alquiler_mes * 1.25), e, q

    def competidor(l, e, q):
        return l.con(precio=max(1.0, l.precio - 1)), e, q

    def todo(l, e, q):
        l, e = _sueldos(l, e, 1.10)
        return l.con(insumos=l.insumos * 1.2, alquiler_mes=l.alquiler_mes * 1.25), replace(e, anio=2028), q * 0.85

    return [
        ("base", "Como está", lambda l, e, q: (l, e, q)),
        ("demanda", "Clientela −15 %", demanda),
        ("insumos", "Insumos +20 %", insumos),
        ("igv", "IGV 18 % (2028)", igv),
        ("sueldos", "Sueldos +10 %", sueldos),
        ("alquiler", "Alquiler +25 %", alquiler),
        ("competidor", "Competidor: −S/ 1 para no perder clientes", competidor),
        ("todo", "Todo junto", todo),
    ]


GOLPES = [(k, n) for k, n, _ in _golpes()]


def estres(local: Local, esc: Escenario, q: float, nacional: dict, riesgo: dict) -> list[dict]:
    salida = []
    for clave, nombre, golpe in _golpes():
        l2, e2, q2 = golpe(local, esc, q)
        m = modelo(l2, q2, e2, nacional)
        mc = simular(l2, e2, nacional, riesgo, q_ref=round(q2), n=N_MC)
        salida.append({"golpe": clave, "nombre": nombre, "utilidad": round(m.util),
                       "ingreso_dueno": round(m.util + (1500 if e2.sueldo_dueno else 0)),
                       "prob_perdida": round(mc.prob_perdida, 3)})
    return salida


def mezcla_desde_analisis(analisis: dict) -> Mezcla | None:
    """Costo de un segundo de res y de uno de pollo/pasta/otros, ponderado por
    lo vendido, a partir del análisis de platos."""
    claves_res = ("res", "pulpa", "pecho", "chuleta", "bistec", "lomo", "mondongo")
    res = otros = 0.0
    v_res = v_otros = 0.0
    for p in analisis.get("platos", []):
        if p["tipo"] != "segundo" or p.get("sin_receta") or not p.get("vendidos"):
            continue
        es_res = any(any(k in d["insumo"].lower().split() or k in d["insumo"].lower() for k in claves_res)
                     and d["parte"] >= 0.3 for d in p["desglose"])
        if es_res:
            res += p["costo_porcion"] * p["vendidos"]
            v_res += p["vendidos"]
        else:
            otros += p["costo_porcion"] * p["vendidos"]
            v_otros += p["vendidos"]
    if not v_res or not v_otros:
        return None
    return Mezcla(costo_res=res / v_res, costo_otros=otros / v_otros,
                  acompanamiento=analisis.get("costo_entrada_bebida_promedio", 0.0),
                  parte_actual=round(v_res / (v_res + v_otros), 2))


__all__ = ["CALIDAD", "Factores", "GOLPES", "Mezcla", "NOMBRE_CALIDAD", "SUPUESTOS", "barrido", "estres",
           "mezcla_desde_analisis"]
