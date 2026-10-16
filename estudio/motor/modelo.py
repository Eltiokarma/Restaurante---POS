"""Motor de rentabilidad de un local de menú (portado de
`prototipos/rentabilidad-ciudades.html`, función `model` y vecinas).

Todo en soles por mes salvo que se diga otra cosa. La lógica es la del
prototipo, línea por línea: si se cambia algo aquí, los tests de regresión
contra los valores del brief tienen que seguir pasando o explicarse.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

RUTA_DATASET = Path(__file__).resolve().parent.parent / "data" / "dataset.json"

# Trayectoria regulatoria (BRIEF: verificado; 2028 es supuesto, no ley)
ANIOS = {
    2026: {"igv": 10.5, "rmv": 1230, "supuesto": False},
    2027: {"igv": 15.0, "rmv": 1300, "supuesto": False},
    2028: {"igv": 18.0, "rmv": 1300, "supuesto": True},
}
DIAS_MES = 26
MERMA = 0.05
OTROS_FIJOS = 400
SUELDO_DUENO = 1500
DESCARTABLES = {"popular": 0.20, "ejecutivo": 0.35}


def cargar_dataset(ruta: Path = RUTA_DATASET) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


MODALIDADES = ("mensual", "quincenal", "diario")
AREAS = ("cocina", "salon", "otro")
TURNOS = ("dia", "noche", "ambos")


@dataclass(frozen=True)
class Trabajador:
    """Una fila de la planilla propia. `monto` es el sueldo del mes
    (mensual o quincenal: cuesta lo mismo, cambia cuándo sale la plata) o el
    jornal del día (diario: se paga solo lo que trabaja, `dias` al mes)."""
    puesto: str
    monto: float
    modalidad: str = "mensual"
    cantidad: int = 1
    area: str = "cocina"
    dias: float | None = None  # solo diario; por defecto los días que abre el local
    turno: str = "dia"  # dia | noche | ambos (para ver cuánto cuesta cada turno)

    def con(self, **cambios) -> "Trabajador":
        return replace(self, **cambios)


def costo_trabajador(t: Trabajador, formal: bool, rmv: float, mult: float, dias_local: float) -> float:
    """Costo del mes para el empleador. Formal: nunca bajo el sueldo mínimo
    (el jornal, bajo la RMV/30) y con las cargas de la micro empresa."""
    if t.modalidad == "diario":
        jornal = max(t.monto, rmv / 30) if formal else t.monto
        base = jornal * (t.dias if t.dias is not None else dias_local)
    else:
        base = max(t.monto, rmv) if formal else t.monto
    return base * t.cantidad * (mult if formal else 1.0)


@dataclass(frozen=True)
class Noche:
    """Segundo servicio del día (cena): sus propios platos/día, precio e
    insumos. Comparte alquiler y local; suma su gas, su luz y, si la
    planilla es automática, su propio equipo (pagado por los días que abre)."""
    q: float = 30
    precio: float = 12.0
    insumos: float = 4.5
    dias: float | None = None  # por defecto los mismos días que el día
    balones: float = 2  # balones extra al mes
    servicios: float = 150  # luz extra al mes

    def con(self, **cambios) -> "Noche":
        return replace(self, **cambios)


@dataclass(frozen=True)
class Escenario:
    """Cómo se mira el negocio (los botones del prototipo)."""
    segmento: str = "popular"  # popular | ejecutivo
    anio: int = 2026
    formal: bool = True
    balones: float = 5  # balones de gas de 45 kg al mes (gasto fijo)
    sueldo_dueno: bool = True
    dias: float = DIAS_MES  # días que abre el local al mes
    # Planilla propia: si está vacía, el personal sale de los menús/día
    # como en el prototipo (cocina cada 80 menús, un mozo cada 70)
    planilla: tuple[Trabajador, ...] = ()
    noche: Noche | None = None

    @property
    def pop(self) -> bool:
        return self.segmento == "popular"


@dataclass(frozen=True)
class Local:
    """Valores de una ciudad (o zona) para un segmento: dataset + correcciones."""
    precio: float
    pmin: float
    pmax: float
    insumos: float
    alquiler_mes: float
    sueldo_cocinero: float
    sueldo_ayudante: float
    sueldo_mozo: float
    gas_balon45: float
    servicios_mes: float
    precio_propio: bool = False  # el precio es dato propio (no del rango estimado)
    id: str = ""
    riesgo_conflicto_anual: float = 0.0
    extra: dict = field(default_factory=dict, compare=False)

    def con(self, **cambios) -> "Local":
        return replace(self, **cambios)


def local_de_ciudad(ciudad: dict, segmento: str = "popular", **correcciones) -> Local:
    pop = segmento == "popular"
    rango = ciudad["precio_popular_rango" if pop else "precio_ejecutivo_rango"]
    base = Local(
        id=ciudad["id"],
        precio=ciudad["precio_popular" if pop else "precio_ejecutivo"],
        pmin=rango[0],
        pmax=rango[1],
        insumos=ciudad["insumos_popular" if pop else "insumos_ejecutivo"],
        alquiler_mes=ciudad["alquiler_mes"],
        sueldo_cocinero=ciudad["sueldo_cocinero"],
        sueldo_ayudante=ciudad["sueldo_ayudante"],
        sueldo_mozo=ciudad["sueldo_mozo"],
        gas_balon45=ciudad["gas_balon45"],
        servicios_mes=ciudad["servicios_mes"],
        riesgo_conflicto_anual=ciudad.get("riesgo_conflicto_anual", 0.0),
    )
    if correcciones:
        base = base.con(precio_propio="precio" in correcciones, **correcciones)
    return base


@dataclass(frozen=True)
class Resultado:
    t: float  # tasa de IGV aplicada
    var_u: float  # costo variable por menú
    p_net: float  # precio sin IGV
    contrib_u: float
    cocina: int
    mozos: int
    personal: float
    alquiler: float
    gas: float
    fijos: float
    q_mes: float
    ventas: float
    util: float
    # Turno noche (cero si no abre de noche)
    q_mes_noche: float = 0.0
    ventas_noche: float = 0.0
    contrib_noche: float = 0.0  # por plato, sin IGV
    p_net_noche: float = 0.0

    @property
    def margen(self) -> float:
        return self.util / self.ventas if self.ventas > 0 else 0.0

    @property
    def ventas_netas(self) -> float:
        """Ventas sin IGV de los dos turnos."""
        return self.p_net * self.q_mes + self.p_net_noche * self.q_mes_noche


def modelo(local: Local, q: float, esc: Escenario, nacional: dict,
           precio: float | None = None, ins_mult: float = 1.0, igv: float | None = None,
           rmv: float | None = None, otros_fijos: float = OTROS_FIJOS,
           sueldo_dueno: float = SUELDO_DUENO) -> Resultado:
    """Estado de resultados de UN mes para q menús por día.

    `igv` (en %) y `rmv` corrigen los del año: los usa el flujo a 10 años
    (después de 2028, o en el Nuevo RUS, que no cobra IGV pero sí paga
    planilla formal). `otros_fijos` y `sueldo_dueno` suben con la inflación."""
    anio = dict(ANIOS[esc.anio]) if esc.anio in ANIOS else dict(ANIOS[max(ANIOS)])
    if igv is not None:
        anio["igv"] = igv
    if rmv is not None:
        anio["rmv"] = rmv
    pop = esc.pop
    t = anio["igv"] / 100 if esc.formal else 0.0
    precio = local.precio if precio is None else precio
    var_u = local.insumos * ins_mult * (1 + MERMA) + DESCARTABLES[esc.segmento]
    p_net = precio / (1 + t)
    contrib_u = p_net - var_u
    cocina = max(2, math.ceil(q / (80 if pop else 55)))
    mozos = max(1, math.ceil(q / (70 if pop else 40)))

    def w(x: float) -> float:
        return max(x, anio["rmv"]) if esc.formal else x

    mult = nacional["mult_micro"] if esc.formal else 1.0
    if esc.planilla:
        personal = sum(costo_trabajador(tr, esc.formal, anio["rmv"], mult, esc.dias) for tr in esc.planilla)
        cocina = sum(tr.cantidad for tr in esc.planilla if tr.area == "cocina")
        mozos = sum(tr.cantidad for tr in esc.planilla if tr.area == "salon")
    else:
        cocinero = max(local.sueldo_cocinero, anio["rmv"] * 1.06) if esc.formal else local.sueldo_cocinero
        personal = mult * (cocinero + (cocina - 1) * w(local.sueldo_ayudante) + mozos * w(local.sueldo_mozo))
    personal += sueldo_dueno if esc.sueldo_dueno else 0
    alquiler = local.alquiler_mes * (1 if pop else 1.25)
    gas = local.gas_balon45 * esc.balones
    q_mes_n = ventas_n = contrib_n = p_net_n = extra_n = 0.0
    if esc.noche is not None and esc.noche.q > 0:
        n = esc.noche
        dias_n = n.dias if n.dias is not None else esc.dias
        p_net_n = n.precio / (1 + t)
        contrib_n = p_net_n - (n.insumos * ins_mult * (1 + MERMA) + DESCARTABLES[esc.segmento])
        q_mes_n = n.q * dias_n
        ventas_n = n.precio * q_mes_n
        gas += local.gas_balon45 * n.balones
        extra_n = n.servicios
        if not esc.planilla:
            # Equipo propio de noche, pagado por la parte del mes que trabaja
            cocina_n = max(1, math.ceil(n.q / (80 if pop else 55)))
            mozos_n = max(1, math.ceil(n.q / (70 if pop else 40)))
            cocinero_n = max(local.sueldo_cocinero, anio["rmv"] * 1.06) if esc.formal else local.sueldo_cocinero
            parte = min(1.0, dias_n / esc.dias) if esc.dias else 1.0
            personal += parte * mult * (cocinero_n + (cocina_n - 1) * w(local.sueldo_ayudante)
                                        + mozos_n * w(local.sueldo_mozo))
            cocina += cocina_n
            mozos += mozos_n
    fijos = personal + alquiler + gas + local.servicios_mes + otros_fijos + extra_n
    q_mes = q * esc.dias
    ventas = precio * q_mes + ventas_n
    util = contrib_u * q_mes + contrib_n * q_mes_n - fijos
    return Resultado(t, var_u, p_net, contrib_u, cocina, mozos, personal, alquiler, gas, fijos,
                     q_mes, ventas, util, q_mes_n, ventas_n, contrib_n, p_net_n)


def equilibrio(local: Local, esc: Escenario, nacional: dict) -> int | None:
    """Primer volumen diario (5–600) con utilidad >= 0."""
    for q in range(5, 601):
        if modelo(local, q, esc, nacional).util >= 0:
            return q
    return None


def precio_minimo(local: Local, q: float, esc: Escenario, nacional: dict) -> float:
    """Frontera de precio: el precio (con IGV) que deja utilidad 0 a q menús/día."""
    m = modelo(local, q, esc, nacional)
    # lo que deja la noche ayuda a cubrir los fijos
    return (1 + m.t) * (m.var_u + (m.fijos - m.contrib_noche * m.q_mes_noche) / m.q_mes)
