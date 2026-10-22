"""Autoservicio de comida criolla: carta fija que rota, todo preparado antes
del almuerzo y servido desde una línea de baño maría.

El cliente pide en una tablet, paga en caja y recoge su bandeja (o su bolsa).
No hay mozos: la gente se calcula por puesto con el mismo modelo de cocina de
Candela, cambiando lo que cambia el formato:

- la producción es la misma comida por menú (una entrada y un fondo), pero
  repartida en más ollas (seis fondos en vez de dos o tres) y hecha por gente
  que repite los mismos platos día por medio (más rápida);
- en el almuerzo no se arma un plato a pedido: se sirve lo porcionado del
  baño maría, se reponen frituras en tandas y se lava lo de quien come ahí;
- lo que hacían los mozos (tomar el pedido, llevarlo, cobrar) lo hacen las
  tablets y una caja.

La planilla sale de la venta: a más menús, más gente, y se recalcula para cada
volumen. El dueño invierte y supervisa sin sueldo, como el inversor que
supervisa, para que la comparación sea justa.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import cocina as coc
from .modelo import Escenario, Local, Trabajador, modelo
from .modelo import precio_minimo as _pmin_fijo

RUTA = Path(__file__).resolve().parent.parent / "data" / "autoservicio.json"
MODO = "estaciones"  # puestos fijos y todo lo anticipable la tarde anterior


def cargar(ruta: Path = RUTA) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def cocina_de(cfg: dict, base: dict | None = None) -> dict:
    """La cocina de Candela convertida en la del autoservicio."""
    base = coc.con_velocidad(base or coc.cargar(), cfg["estandarizacion"]["velocidad"])
    k = cfg["fondos_en_olla"]
    tareas = []
    for t in base["tareas"]:
        if t["id"] in ("aderezo", "guiso"):
            # el mismo volumen de comida en k ollas: cada una con su tiempo fijo
            for i in range(1, k + 1):
                tid = f"{t['id']}{i}"
                deps = [f"aderezo{i}" if d == "aderezo" else d for d in t.get("deps", [])]
                tareas.append({**t, "id": tid, "plato": f"guiso{i}", "var": t["var"] / k, "deps": deps,
                               "corto": f"{t.get('corto', t['nombre'])} {i}"})
            continue
        if t["id"] == "plancha_lista":
            t = {**t, "nombre": "Frituras y saltados en tanda", "corto": "Tandas"}
        tareas.append(t)
    sv = base["servicio"]
    puestos = {e: {**sv["puestos"][e], "min": cfg["servicio"][e]} for e in ("armado", "plancha", "lavado")}
    puestos["lavado"]["min"] = cfg["servicio"]["lavado"] * (1 - cfg["para_llevar"])
    servicio = {**sv, "puestos": puestos,
                "desorden_queda": {**sv["desorden_queda"], MODO: cfg["estandarizacion"]["desorden_queda"]}}
    platos = {**{p: n for p, n in base["platos"].items() if p != "guiso"},
              **{f"guiso{i}": f"Fondo de olla {i}" for i in range(1, k + 1)}}
    return {**base, "tareas": tareas, "servicio": servicio, "platos": platos}


def _pico_15(base: dict) -> float:
    perfil = base["demanda_15min"]["perfil"]
    return max(perfil.values()) / sum(perfil.values())


def equipo(q: float, cfg: dict | None = None, base: dict | None = None) -> dict:
    """La gente que necesita el autoservicio para q menús al día y qué hace
    cada uno en el almuerzo."""
    cfg = cfg or cargar()
    base = base or coc.cargar()
    cc = cocina_de(cfg, base)
    d = coc.desorden_calibrado(base)  # el desorden medido en Candela
    n = next((n for n in range(1, 15) if coc.cabe(MODO, q, n, cc)
              and coc.servicio(MODO, q, n, cc, d)["aguanta"]), None)
    if n is None:
        raise ValueError(f"ninguna cocina de hasta 14 personas saca {q} menús")
    n_prep = coc.gente_minima(MODO, q, cc, maximo=14)
    sv = cc["servicio"]
    tiempos = {e: x["min"] for e, x in sv["puestos"].items()}
    total = sum(tiempos.values())
    dd = d * sv["desorden_queda"][MODO]
    _ritmo, grupos = coc._reparto(n, {e: t + dd * t / total for e, t in tiempos.items()})
    almuerzo = {e: 0.0 for e in tiempos}
    for g in grupos:  # con menos gente que puestos, alguien hace dos
        for e in set(g):
            almuerzo[e] += g.count(e) / len(set(g)) if len(set(g)) > 1 else g.count(e)
    caja = cfg["caja"]
    pedidos_pico = q * _pico_15(base) / caja["menus_por_pedido"]
    cajas = max(1, math.ceil(pedidos_pico * caja["min_por_pedido"] / 15))
    en_local = q * (1 - cfg["para_llevar"])
    salon = en_local / cfg["salon"]["menus_por_persona"]
    j = coc.jornada(MODO, q, n, cc)
    r = coc.plan(MODO, q, n, cc)
    return {"q": q, "cocina": n, "cocina_preparacion": n_prep, "almuerzo": almuerzo, "puestos": r["puestos"],
            "cajas": cajas, "uso_caja": pedidos_pico * caja["min_por_pedido"] / 15 / cajas,
            "salon": max(0.5, math.ceil(salon * 2) / 2), "jornada": j,
            "servicio": coc.servicio(MODO, q, n, cc, d), "plan": r}


def planilla(eq: dict, cfg: dict | None = None) -> list[Trabajador]:
    """Cargos y sueldos del equipo, en turnos de ocho horas. La cocina entra
    lo justo para tener todo listo antes del almuerzo; las horas que pasan de
    ocho (la mise en place del día siguiente, en la tarde) las cubre un turno
    tarde de auxiliares que entra a media mañana, en vez de pagar horas extra
    a todos (cuesta casi lo mismo y no alarga la jornada de nadie)."""
    cfg = cfg or cargar()
    s = cfg["sueldos"]
    n = eq["cocina"]
    tarde = turno_tarde(eq)
    despacho = max(1, round(eq["almuerzo"].get("armado", 1)))
    lavado = max(0, round(eq["almuerzo"].get("lavado", 0)))
    # el turno tarde lava y despacha en el almuerzo: lo que cubre no lo hace la cocina
    cubre = min(tarde, lavado)
    lavado -= cubre
    cubre_d = min(tarde - cubre, max(0, despacho - 1))
    despacho -= cubre_d
    cocineros = max(0, n - 1 - despacho - lavado)
    if n - 1 < despacho + lavado:  # con poca gente, los cocineros también despachan
        despacho = max(0, n - 1 - lavado)
    filas = [Trabajador("Jefe de cocina", s["jefe"], area="cocina")]
    if cocineros:
        filas.append(Trabajador("Cocinero de producción", s["cocinero"], cantidad=cocineros, area="cocina"))
    if despacho:
        filas.append(Trabajador("Despachador de línea", s["auxiliar"], cantidad=despacho, area="cocina"))
    if lavado:
        filas.append(Trabajador("Auxiliar de lavado", s["auxiliar"], cantidad=lavado, area="cocina"))
    if tarde:
        filas.append(Trabajador("Auxiliar de turno tarde", s["auxiliar"], cantidad=tarde, area="cocina"))
    filas.append(Trabajador("Cajero", s["cajero"], cantidad=eq["cajas"], area="otro"))
    sal = eq["salon"]  # medio tiempo si alcanza; si no, tiempos completos
    filas.append(Trabajador("Salón: recojo y limpieza", s["salon"], cantidad=max(1, math.ceil(sal)), area="otro",
                            jornada=0.5 if sal < 1 else 1.0))
    return filas


def turno_tarde(eq: dict) -> int:
    """Auxiliares de turno tarde: las horas de cocina que pasan de ocho por
    persona, en turnos de ocho."""
    j = eq["jornada"]
    return math.ceil(round(eq["cocina"] * max(0.0, j["horas"] - 8), 6) / 8)


def horarios(eq: dict) -> dict:
    """Entrada y salida de cada turno."""
    j = eq["jornada"]
    sale = 15 * round(j["sale"] / 15)
    temprano = (j["entra"], min(sale, j["entra"] + 8 * 60))
    tarde = (sale - 8 * 60, sale)
    return {"temprano": temprano, "tarde": tarde if turno_tarde(eq) else None,
            "caja": (coc.minutos("11:45"), coc.minutos("15:45")), "salon": (coc.minutos("11:30"), coc.minutos("16:00"))}


def escenario(q: float, precio: float | None = None, cfg: dict | None = None, base: dict | None = None,
              anio: int = 2026, encargado: bool = False, local: Local | None = None,
              eq: dict | None = None) -> tuple[Local, Escenario]:
    """Local y escenario del autoservicio para q menús al día."""
    cfg = cfg or cargar()
    eq = eq or equipo(q, cfg, base)
    filas = planilla(eq, cfg)
    if encargado:
        filas.append(Trabajador("Encargado del local", cfg["sueldos"]["encargado"], area="otro"))
    loc = local or local_de(cfg, precio)
    esc = Escenario(segmento="popular", anio=anio, formal=True, sueldo_dueno=False,
                    balones=math.ceil(q / cfg["menus_por_balon"]), planilla=tuple(filas))
    return loc, esc


def local_de(cfg: dict, precio: float | None = None) -> Local:
    """El local del autoservicio en Juliaca: insumos con el táper de lo que se
    lleva, alquiler de una calle con paso de gente, más luz por el baño maría,
    las vitrinas y las tablets."""
    return Local(precio=float(precio or cfg["precio"]), pmin=7, pmax=18, id="juliaca",
                 insumos=cfg["insumos"] + cfg["para_llevar"] * cfg["taper"],
                 alquiler_mes=cfg["alquiler_mes"], sueldo_cocinero=cfg["sueldos"]["cocinero"],
                 sueldo_ayudante=cfg["sueldos"]["auxiliar"], sueldo_mozo=cfg["sueldos"]["auxiliar"],
                 gas_balon45=220, servicios_mes=cfg["servicios_mes"] + cfg["otros_mes"], precio_propio=True)


class _Equipos:
    """Equipos ya calculados por volumen (el plan de cocina es lento)."""

    def __init__(self, cfg: dict, base: dict):
        self.cfg, self.base, self.memo = cfg, base, {}

    def __call__(self, q: float) -> dict:
        k = round(q)
        if k not in self.memo:
            self.memo[k] = equipo(k, self.cfg, self.base)
        return self.memo[k]


def utilidad(q: float, precio: float, nacional: dict, equipos: _Equipos, **kw) -> float:
    loc, esc = escenario(q, precio, equipos.cfg, equipos.base, eq=equipos(q), **kw)
    return modelo(loc, q, esc, nacional).util


def equilibrio(precio: float, nacional: dict, equipos: _Equipos, paso: int = 5, maximo: int = 400,
               **kw) -> int | None:
    """Menos menús al día con que el autoservicio no pierde a ese precio,
    con la gente que necesita cada volumen (de 5 en 5)."""
    for q in range(paso, maximo + 1, paso):
        if utilidad(q, precio, nacional, equipos, **kw) >= 0:
            return q
    return None


def precio_minimo(q: float, nacional: dict, equipos: _Equipos, **kw) -> float:
    loc, esc = escenario(q, None, equipos.cfg, equipos.base, eq=equipos(q), **kw)
    return _pmin_fijo(loc, q, esc, nacional)


def equipos(cfg: dict | None = None, base: dict | None = None) -> _Equipos:
    return _Equipos(cfg or cargar(), base or coc.cargar())


def datos(q: float | None = None, precio: float | None = None, cfg: dict | None = None,
          base: dict | None = None) -> dict:
    """El autoservicio como un caso más del estudio (mismo formato que
    data/arquetipos.json), con la planilla que necesita a q menús al día."""
    cfg = cfg or cargar()
    q = q or cfg["q"]
    precio = precio or cfg["precio"]
    eq = equipo(q, cfg, base)
    loc, esc = escenario(q, precio, cfg, base, eq=eq)
    return {
        "autoservicio": True,
        "ficha": {"categoria": "Formato", "descripcion": (
            "Autoservicio de comida criolla: carta fija que rota (menú A, menú B), seis fondos y tres entradas "
            "preparados antes del almuerzo; se pide en tablets, se paga en caja y se recoge la bandeja. Sin mozos. "
            "El dueño invierte y supervisa. Formal MYPE."),
                  "supuestos": [f"precio S/ {precio:g}", f"{q:g} menús/día", f"alquiler S/ {cfg['alquiler_mes']:,}",
                                "planilla por puesto"],
                  "fuente": "Supuesto del estudio, a contrastar con un local real"},
        "escenario": {"ciudad_id": "juliaca", "zona_id": None, "segmento": "popular", "anio": 2026, "formal": True,
                      "balones": esc.balones, "sueldo_dueno": False, "q": q, "dias": 26,
                      "planilla": [{"puesto": t.puesto, "monto": t.monto, "modalidad": t.modalidad,
                                    "cantidad": t.cantidad, "area": t.area, "dias": None, "turno": t.turno,
                                    "jornada": t.jornada} for t in esc.planilla],
                      "noche": None, "precio": precio, "insumos": round(loc.insumos, 2),
                      "alquiler_mes": loc.alquiler_mes, "sueldo_cocinero": loc.sueldo_cocinero,
                      "sueldo_ayudante": loc.sueldo_ayudante, "sueldo_mozo": loc.sueldo_mozo,
                      "gas_balon45": loc.gas_balon45, "servicios_mes": loc.servicios_mes},
        "supuestos": {"inversion": cfg["inversion"], "meses_arranque": 6, "arranque_desde": 0.4, "crecimiento_q": 0,
                      "inflacion": 0.025, "alza_precio": 0.025, "alza_rmv": 0.037, "tasa_descuento": 0.15,
                      "regimen": "mype"},
        "casa": [{"quien": "Dueño (supervisa, compra y cuadra la caja)", "rol": "administrador", "horas_semana": 20}],
    }


# --- El mismo local con mozos ------------------------------------------------
#
# Para aislar el efecto del formato: el mismo local, la misma comida, el mismo
# precio y la misma formalidad, pero servido como un menú de siempre. La cocina
# es la de Candela (armado a pedido y plancha al momento) organizada por
# estaciones, que es lo mejor que puede hacer; los mozos toman el pedido, lo
# llevan y cobran, uno cada 50 menús como en Candela en su tope.

POR_MOZO = 50


def equipo_mozos(q: float, cfg: dict | None = None, base: dict | None = None) -> dict:
    cfg = cfg or cargar()
    base = base or coc.cargar()
    n = coc.gente_necesaria(MODO, q, base, maximo=14)
    if n is None:
        raise ValueError(f"ninguna cocina de hasta 14 personas saca {q} menús")
    eq = {"cocina": n, "jornada": coc.jornada(MODO, q, n, base)}
    return {**eq, "turno_tarde": turno_tarde(eq), "mozos": math.ceil(q / POR_MOZO)}


def escenario_mozos(q: float, precio: float | None = None, cfg: dict | None = None,
                    base: dict | None = None, eq: dict | None = None, local: Local | None = None,
                    sueldos: dict | None = None) -> tuple[Local, Escenario]:
    """Un menú con mozos y la gente que pide la simulación de su cocina. Por
    defecto, el local del autoservicio sin táper; con `local` y `sueldos`, el
    de otro negocio (el inversor que supervisa)."""
    cfg = cfg or cargar()
    eq = eq or equipo_mozos(q, cfg, base)
    s = sueldos or cfg["sueldos"]
    filas = [Trabajador("Jefe de cocina", s["jefe"], area="cocina")]
    if eq["cocina"] > 1:
        filas.append(Trabajador("Cocinero", s["cocinero"], cantidad=eq["cocina"] - 1, area="cocina"))
    if eq["turno_tarde"]:
        filas.append(Trabajador("Auxiliar de turno tarde", s["auxiliar"], cantidad=eq["turno_tarde"], area="cocina"))
    filas.append(Trabajador("Mozo", s["auxiliar"], cantidad=eq["mozos"], area="salon"))
    if local is None:
        local = local_de(cfg).con(insumos=cfg["insumos"])  # todo se come en el local: sin táper
    if precio is not None:
        local = local.con(precio=float(precio))
    esc = Escenario(segmento="popular", anio=2026, formal=True, sueldo_dueno=False,
                    balones=math.ceil(q / cfg["menus_por_balon"]), planilla=tuple(filas))
    return local, esc


class _EquiposMozos(_Equipos):
    def __call__(self, q: float) -> dict:
        k = round(q)
        if k not in self.memo:
            self.memo[k] = equipo_mozos(k, self.cfg, self.base)
        return self.memo[k]


def equipos_mozos(cfg: dict | None = None, base: dict | None = None) -> _EquiposMozos:
    return _EquiposMozos(cfg or cargar(), base or coc.cargar())


def utilidad_mozos(q: float, precio: float, nacional: dict, equipos: _EquiposMozos, **kw) -> float:
    loc, esc = escenario_mozos(q, precio, equipos.cfg, equipos.base, eq=equipos(q), **kw)
    return modelo(loc, q, esc, nacional).util


def equilibrio_mozos(precio: float, nacional: dict, equipos: _EquiposMozos, paso: int = 5, maximo: int = 400,
                     **kw) -> int | None:
    """Menos menús al día con que el menú con mozos no pierde a ese precio,
    con la gente que pide la simulación para cada volumen."""
    for q in range(paso, maximo + 1, paso):
        if utilidad_mozos(q, precio, nacional, equipos, **kw) >= 0:
            return q
    return None
