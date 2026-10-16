"""Costeo de platos por receta, margen, ingeniería de menú y peso de cada
insumo.

- Cada receta dice cuánto lleva de cada insumo (cantidad NETA, la que va al
  plato) y cuántas porciones rinde. La merma del insumo (pelado, hueso,
  grasa) sube lo que hay que comprar: costo = cantidad × precio / (1 − merma).
- Un segundo se vende como menú: su precio es el del menú y su costo suma la
  entrada y el refresco promedio (ponderados por lo que se vende).
- Ingeniería de menú (Kasavana y Smith): dentro de cada tipo, un plato es
  popular si su parte de las ventas es al menos 70 % de la parte pareja
  (1/N), y de margen alto si deja al menos el margen promedio ponderado.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TIPOS = ("entrada", "segundo", "sopa", "bebida", "postre", "extra")
CLASES = {
    ("alta", "alto"): ("estrella", "Mantenlo igual y a la vista: es lo que más vende y más deja."),
    ("alta", "bajo"): ("caballo", "Se vende mucho pero deja poco: sube un poco el precio o baja el costo (porción, insumo más barato)."),
    ("baja", "alto"): ("rompecabezas", "Deja bien pero se vende poco: ofrécelo más (pizarra, que el mozo lo recomiende) o cámbiale el nombre."),
    ("baja", "bajo"): ("perro", "Vende poco y deja poco: reemplázalo o rehaz la receta."),
}


@dataclass(frozen=True)
class InsumoR:
    id: int
    nombre: str
    unidad: str
    precio: float  # por unidad
    merma: float = 0.0  # fracción que se pierde al limpiar


@dataclass(frozen=True)
class PlatoR:
    id: int
    nombre: str
    tipo: str
    porciones: float
    precio: float | None = None
    vendidos: float | None = None  # por semana
    items: tuple[tuple[int, float], ...] = field(default_factory=tuple)  # (insumo_id, cantidad)


def costo_insumo(ins: InsumoR, cantidad: float) -> float:
    return cantidad * ins.precio / max(1e-9, 1 - ins.merma)


def _desglose(p: PlatoR, insumos: dict[int, InsumoR]) -> dict[int, float]:
    """Costo por porción de cada insumo del plato."""
    salida: dict[int, float] = {}
    porciones = p.porciones or 1
    for iid, cant in p.items:
        ins = insumos.get(iid)
        if ins is None:
            continue
        salida[iid] = salida.get(iid, 0.0) + costo_insumo(ins, cant) / porciones
    return salida


def _promedio(platos: list[PlatoR], desgloses: dict[int, dict[int, float]]) -> dict[int, float]:
    """Desglose promedio de un grupo (entradas o bebidas), ponderado por lo
    vendido; si nada tiene ventas, promedio simple."""
    if not platos:
        return {}
    pesos = [p.vendidos or 0 for p in platos]
    if sum(pesos) <= 0:
        pesos = [1.0] * len(platos)
    total = sum(pesos)
    salida: dict[int, float] = {}
    for p, w in zip(platos, pesos):
        for iid, c in desgloses[p.id].items():
            salida[iid] = salida.get(iid, 0.0) + c * w / total
    return salida


def analizar(insumos: list[InsumoR], platos: list[PlatoR], igv: float, formal: bool = True) -> dict:
    """Costos, márgenes, clases de ingeniería de menú y peso de cada insumo.
    `igv` en % (el precio de la pizarra lo incluye si el local es formal)."""
    por_id = {i.id: i for i in insumos}
    t = igv / 100 if formal else 0.0
    desg = {p.id: _desglose(p, por_id) for p in platos}
    # Un plato sin receta costaría cero y bajaría los promedios: fuera
    entradas = [p for p in platos if p.tipo == "entrada" and p.items]
    bebidas = [p for p in platos if p.tipo == "bebida" and p.items]
    acomp = {}
    for d in (_promedio(entradas, desg), _promedio(bebidas, desg)):
        for iid, c in d.items():
            acomp[iid] = acomp.get(iid, 0.0) + c
    costo_acomp = sum(acomp.values())

    filas = []
    for p in platos:
        propio = sum(desg[p.id].values())
        es_menu = p.tipo == "segundo"
        costo_venta = propio + (costo_acomp if es_menu else 0.0)
        fila = {
            "id": p.id, "nombre": p.nombre, "tipo": p.tipo, "porciones": p.porciones,
            "precio": p.precio, "vendidos": p.vendidos,
            "costo_porcion": round(propio, 4),
            "costo_venta": round(costo_venta, 4),
            "es_menu": es_menu,
            "desglose": sorted(
                [{"insumo_id": iid, "insumo": por_id[iid].nombre, "costo": round(c, 4),
                  "parte": round(c / propio, 4) if propio else 0}
                 for iid, c in desg[p.id].items()], key=lambda x: -x["costo"]),
            "precio_sin_igv": None, "margen": None, "costo_pct": None, "clase": None, "consejo": None,
            "popularidad": None,
            "sin_receta": not p.items,
        }
        if p.precio:
            neto = p.precio / (1 + t)
            fila["precio_sin_igv"] = round(neto, 4)
            fila["margen"] = round(neto - costo_venta, 4)
            fila["costo_pct"] = round(costo_venta / neto, 4) if neto else None
        filas.append(fila)

    # Ingeniería de menú dentro de cada tipo (solo los que tienen precio y ventas)
    for tipo in TIPOS:
        grupo = [f for f in filas if f["tipo"] == tipo and f["margen"] is not None and (f["vendidos"] or 0) > 0
                 and not f["sin_receta"]]
        if len(grupo) < 2:
            continue
        total = sum(f["vendidos"] for f in grupo)
        margen_prom = sum(f["vendidos"] * f["margen"] for f in grupo) / total
        umbral_pop = 0.7 / len(grupo)
        for f in grupo:
            parte = f["vendidos"] / total
            pop = "alta" if parte >= umbral_pop else "baja"
            mar = "alto" if f["margen"] >= margen_prom else "bajo"
            f["popularidad"] = round(parte, 4)
            f["clase"], f["consejo"] = CLASES[(pop, mar)]
            f["umbral_popularidad"] = round(umbral_pop, 4)
            f["margen_promedio"] = round(margen_prom, 4)

    # Menú promedio (segundos ponderados por lo vendido) y peso de cada insumo en él
    segundos = [p for p in platos if p.tipo == "segundo" and p.items]
    pesos = [p.vendidos or 0 for p in segundos]
    if segundos and sum(pesos) <= 0:
        pesos = [1.0] * len(segundos)
    contrib: dict[int, float] = {}
    precio_prom = None
    if segundos:
        total = sum(pesos)
        for p, w in zip(segundos, pesos):
            for iid, c in desg[p.id].items():
                contrib[iid] = contrib.get(iid, 0.0) + c * w / total
        for iid, c in acomp.items():
            contrib[iid] = contrib.get(iid, 0.0) + c
        con_precio = [(p, w) for p, w in zip(segundos, pesos) if p.precio]
        if con_precio:
            precio_prom = sum(p.precio * w for p, w in con_precio) / sum(w for _, w in con_precio)
    costo_menu = sum(contrib.values())

    # Gasto semanal por insumo según lo vendido de cada plato
    semana: dict[int, float] = {}
    for p in platos:
        for iid, c in desg[p.id].items():
            semana[iid] = semana.get(iid, 0.0) + c * (p.vendidos or 0)
    gasto_total = sum(semana.values())
    acumulado = 0.0
    pareto = []
    for iid, g in sorted(semana.items(), key=lambda x: -x[1]):
        if g <= 0:
            continue
        acumulado += g
        pareto.append({
            "insumo_id": iid, "insumo": por_id[iid].nombre, "gasto_semana": round(g, 2),
            "parte": round(g / gasto_total, 4), "acumulado": round(acumulado / gasto_total, 4),
            # si este insumo sube 10 %, cuánto sube el costo del menú promedio
            "menu_mas_10pct": round(contrib.get(iid, 0.0) * 0.10, 4),
        })
    return {
        "platos": filas,
        "costo_entrada_bebida_promedio": round(costo_acomp, 4),
        "menu": {
            "costo": round(costo_menu, 4),
            "precio_promedio": round(precio_prom, 2) if precio_prom else None,
            "por_insumo": sorted([{"insumo_id": iid, "insumo": por_id[iid].nombre, "costo": round(c, 4)}
                                  for iid, c in contrib.items()], key=lambda x: -x["costo"]),
        },
        "gasto_semana": round(gasto_total, 2),
        "sin_receta": [p.nombre for p in platos if not p.items],
        "pareto": pareto,
    }
