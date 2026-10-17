"""Organización de la cocina: cuánto demora la mañana según cómo se trabaja.

La producción del día es una lista de tareas con dependencias (no se hace el
aderezo sin la cebolla picada) y dos tiempos: el activo, que ocupa a una
persona, y la espera, en que la olla cocina sola. Un programador reparte las
tareas entre la gente minuto a minuto, dándole prioridad a la que tiene más
camino por delante (la ruta crítica). Se comparan tres formas de trabajar:

- doméstica: cada persona hace sus platos de principio a fin, como en casa;
  lo que usan varios platos (la cebolla, el ajo) lo pica cada uno para el suyo,
  y todo se hace la misma mañana;
- por bloques: lo que usan varios platos se prepara de una vez (toda la
  cebolla junta), pero todo la misma mañana; separa el ahorro de agrupar del
  ahorro de adelantar;
- mise en place: lo que aguanta de un día para otro se deja listo la tarde
  anterior, de una vez para todos los platos; en la mañana cualquiera hace
  cualquier cosa, pero cambiar de puesto cuesta unos minutos;
- estaciones: mise en place y además cada persona tiene su puesto fijo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "data" / "cocina.json"
MODOS = ("domestico", "bloques", "mise", "estaciones")
NOMBRE_MODO = {"domestico": "Doméstica", "bloques": "Por bloques", "mise": "Mise en place",
               "estaciones": "Por estaciones"}


def cargar(ruta: Path = RUTA) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def minutos(hora: str) -> int:
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def hora(m: float) -> str:
    m = round(m)
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass
class Tarea:
    id: str
    nombre: str
    corto: str
    activo: float
    espera: float
    estacion: str
    plato: str | None
    deps: list[str] = field(default_factory=list)
    anticipable: bool = False


def _tareas(cocina: dict, q: float, modo: str) -> list[Tarea]:
    """Las tareas del día para q menús. En la cocina doméstica, lo que usan
    varios platos se parte en una tarea por plato, cada una con su tiempo fijo."""
    esc = q / 100
    salida: list[Tarea] = []
    partes: dict[str, dict[str, str]] = {}
    for t in cocina["tareas"]:
        usa = t.get("usa")
        if usa is not None and modo == "domestico" and len(usa) > 1:
            partes[t["id"]] = {}
            for plato in usa:
                tid = f"{t['id']}@{plato}"
                partes[t["id"]][plato] = tid
                salida.append(Tarea(tid, t["nombre"], t.get("corto", t["nombre"]), t["fijo"] + t["var"] * esc / len(usa), t.get("espera", 0),
                                    t["estacion"], plato, [], bool(t.get("anticipable"))))
            continue
        plato = t.get("plato") or (usa[0] if usa else None)
        salida.append(Tarea(t["id"], t["nombre"], t.get("corto", t["nombre"]), t["fijo"] + t["var"] * esc, t.get("espera", 0), t["estacion"],
                            plato, list(t.get("deps", [])), bool(t.get("anticipable"))))
    for t in salida:  # cada plato depende de su parte de la preparación compartida
        t.deps = [partes[d].get(t.plato, next(iter(partes[d].values()))) if d in partes else d for d in t.deps]
    return salida


def _prioridades(tareas: list[Tarea]) -> dict[str, float]:
    """Camino más largo desde que empieza cada tarea hasta el final del día."""
    hijos: dict[str, list[str]] = {t.id: [] for t in tareas}
    for t in tareas:
        for d in t.deps:
            hijos.setdefault(d, []).append(t.id)
    por_id = {t.id: t for t in tareas}
    memo: dict[str, float] = {}

    def largo(i: str) -> float:
        if i not in memo:
            t = por_id[i]
            memo[i] = t.activo + t.espera + max((largo(h) for h in hijos.get(i, []) if h in por_id), default=0)
        return memo[i]

    return {t.id: largo(t.id) for t in tareas}


def _programar(tareas: list[Tarea], puede: list[set[str] | None], inicio: float, cambio: float,
               listas: dict[str, float], dueno: dict[str, int] | None = None,
               ayuda: bool = False) -> tuple[list[dict], dict[str, float]]:
    """Reparte las tareas entre las personas. `puede[p]` son las estaciones de
    la persona p (None: cualquiera); `dueno` fija la persona de cada plato. Con
    `ayuda`, quien no tiene nada listo en su puesto ayuda en otro (y paga el
    cambio de puesto)."""
    prio = _prioridades(tareas)
    libre = [inicio] * len(puede)
    ultima: list[str | None] = [None] * len(puede)
    fin = dict(listas)
    pendientes = sorted(tareas, key=lambda t: -prio[t.id])
    bloques: list[dict] = []
    t_actual = inicio
    while pendientes:
        asignada = False
        for p in sorted(range(len(puede)), key=lambda p: libre[p]):
            if libre[p] > t_actual:
                continue
            listas_p = [t for t in pendientes
                        if all(fin.get(d, float("inf")) <= t_actual for d in t.deps)
                        and (dueno is None or dueno.get(t.plato, p) == p)]
            propias = [t for t in listas_p if puede[p] is None or t.estacion in puede[p]]
            for tarea in propias or (listas_p if ayuda else []):
                extra = cambio if ultima[p] not in (None, tarea.estacion) else 0
                act = tarea.activo + extra
                bloques.append({"persona": p, "id": tarea.id, "nombre": tarea.nombre, "corto": tarea.corto, "estacion": tarea.estacion,
                                "plato": tarea.plato, "inicio": t_actual, "fin_activo": t_actual + act,
                                "fin": t_actual + act + tarea.espera, "cambio": extra})
                libre[p] = t_actual + act
                ultima[p] = tarea.estacion
                fin[tarea.id] = t_actual + act + tarea.espera
                pendientes.remove(tarea)
                asignada = True
                break
        if not asignada:
            futuros = [x for x in libre + list(fin.values()) if x > t_actual]
            if not futuros:
                raise ValueError("tareas que nadie puede hacer: " + ", ".join(t.id for t in pendientes))
            t_actual = min(futuros)
    return bloques, fin


def _estaciones_de(n: int, carga: dict[str, float]) -> list[set[str]]:
    """Puesto fijo de cada persona: las estaciones más pesadas primero, a
    quien tenga menos carga; si sobra gente, refuerza las más pesadas."""
    orden = sorted(carga, key=lambda e: -carga[e])
    gente: list[set[str]] = [set() for _ in range(n)]
    peso = [0.0] * n
    for e in orden:
        p = min(range(n), key=lambda i: peso[i])
        gente[p].add(e)
        peso[p] += carga[e]
    for p in range(len(orden), n):  # más gente que estaciones
        gente[p] = {orden[(p - len(orden)) % len(orden)]}
    return gente


def plan(modo: str, q: float, personas: int, cocina: dict | None = None) -> dict:
    """La mañana (y, si corresponde, la tarde anterior) de una cocina."""
    if modo not in MODOS:
        raise ValueError(modo)
    cocina = cocina or cargar()
    tareas = _tareas(cocina, q, modo)
    inicio, servicio = minutos(cocina["inicio"]), minutos(cocina["almuerzo"])
    cambio = cocina.get("cambio_estacion", 0)
    tarde: list[dict] = []
    listas: dict[str, float] = {}
    dueno = None
    if modo == "domestico":
        carga: dict[str, float] = {}
        for t in tareas:
            carga[t.plato] = carga.get(t.plato, 0) + t.activo
        peso = [0.0] * personas
        dueno = {}
        for plato in sorted(carga, key=lambda x: -carga[x]):
            p = min(range(personas), key=lambda i: peso[i])
            dueno[plato] = p
            peso[p] += carga[plato]
        puede: list[set[str] | None] = [None] * personas
        cambio = 0  # cada uno sigue su plato
    elif modo in ("bloques", "mise"):
        puede = [None] * personas
    else:
        carga = {}
        for t in tareas:
            carga[t.estacion] = carga.get(t.estacion, 0) + t.activo
        puede = _estaciones_de(personas, carga)
    if modo not in ("domestico", "bloques"):
        antes = [t for t in tareas if t.anticipable]
        tarde, fin_tarde = _programar(antes, puede, minutos(cocina["tarde_inicio"]), cambio, {}, ayuda=True)
        listas = {t.id: -1.0 for t in antes}
        tareas = [t for t in tareas if not t.anticipable]
    manana, fin = _programar(tareas, puede, inicio, cambio, listas, dueno, ayuda=modo == "estaciones")
    listo = max(b["fin"] for b in manana)
    trabajo_m = sum(b["fin_activo"] - b["inicio"] for b in manana)
    trabajo_t = sum(b["fin_activo"] - b["inicio"] for b in tarde)
    fin_t = max((b["fin_activo"] for b in tarde), default=minutos(cocina["tarde_inicio"]))
    return {
        "modo": modo, "q": q, "personas": personas, "manana": manana, "tarde": tarde,
        "puestos": [sorted(x) if x else None for x in puede], "dueno": dueno,
        "inicio": inicio, "servicio": servicio, "listo": listo, "a_tiempo": listo <= servicio,
        "minutos_manana": listo - inicio,
        "trabajo_manana": trabajo_m, "trabajo_tarde": trabajo_t, "trabajo": trabajo_m + trabajo_t,
        "fin_tarde": fin_t if tarde else None,
        "tarde_cabe": not tarde or fin_t <= minutos(cocina["tarde_fin"]),
        "cambios": sum(b["cambio"] for b in manana + tarde),
        "ocio_manana": personas * (listo - inicio) - trabajo_m,
    }


def cabe(modo: str, q: float, personas: int, cocina: dict | None = None) -> bool:
    r = plan(modo, q, personas, cocina)
    return r["a_tiempo"] and r["tarde_cabe"]


def tope(modo: str, personas: int, cocina: dict | None = None, paso: int = 5, maximo: int = 400) -> int:
    """Cuántos menús alcanza a preparar esa gente antes del almuerzo."""
    cocina = cocina or cargar()
    mejor = 0
    for q in range(paso, maximo + 1, paso):
        if cabe(modo, q, personas, cocina):
            mejor = q
        elif mejor:
            break
    return mejor


def gente_minima(modo: str, q: float, cocina: dict | None = None, maximo: int = 8) -> int | None:
    """Cuántas personas hacen falta para tener q menús listos a tiempo."""
    cocina = cocina or cargar()
    return next((n for n in range(1, maximo + 1) if cabe(modo, q, n, cocina)), None)


# --- El almuerzo -----------------------------------------------------------
#
# En el servicio la cocina despacha menús a medida que llegan los pedidos. Cada
# menú pide unos minutos en cada puesto (armar, plancha, lavar) más un tiempo
# de desorden que se calibra con lo observado: una cocina doméstica de tres
# personas aguanta ~100 menús en Candela. La cola se sigue por cuartos de hora
# con la llegada de pedidos medida en su POS; la cocina colapsa cuando un
# cliente tendría que esperar más de lo tolerable por su plato.

def _perfil(cocina: dict) -> list[tuple[int, float]]:
    perfil = cocina["demanda_15min"]["perfil"]
    total = sum(perfil.values())
    return [(minutos(h), v / total) for h, v in sorted(perfil.items())]


def _reparto(n: int, tiempos: dict[str, float]) -> tuple[float, list[list[str]]]:
    """Mejor forma de repartir los puestos entre n personas: menús por minuto
    que salen y quién hace qué. Con menos gente que puestos se juntan puestos;
    con más, se refuerza el cuello de botella."""
    puestos = list(tiempos)
    if n < len(puestos):
        mejor = (0.0, [])
        for asign in _asignaciones(len(puestos), n):
            grupos = [[puestos[i] for i in range(len(puestos)) if asign[i] == g] for g in range(n)]
            if any(not g for g in grupos):
                continue
            ritmo = min(1 / sum(tiempos[e] for e in g) for g in grupos)
            if ritmo > mejor[0]:
                mejor = (ritmo, grupos)
        return mejor
    gente = {e: 1 for e in puestos}
    for _ in range(n - len(puestos)):
        cuello = min(puestos, key=lambda e: gente[e] / tiempos[e])
        gente[cuello] += 1
    return min(gente[e] / tiempos[e] for e in puestos), [[e] * gente[e] for e in puestos]


def _asignaciones(k: int, n: int):
    if k == 0:
        yield ()
        return
    for resto in _asignaciones(k - 1, n):
        for g in range(n):
            yield resto + (g,)


def ritmo_servicio(modo: str, personas: int, cocina: dict | None = None, desorden: float | None = None) -> float:
    """Menús por minuto que despacha la cocina en el almuerzo."""
    cocina = cocina or cargar()
    sv = cocina["servicio"]
    d = (desorden if desorden is not None else desorden_calibrado(cocina)) * sv["desorden_queda"][modo]
    tiempos = {e: x["min"] for e, x in sv["puestos"].items()}
    if modo != "estaciones":  # todos hacen de todo: cada menú pasa por una sola persona
        return personas / (sum(tiempos.values()) + d)
    total = sum(tiempos.values())
    con_desorden = {e: t + d * t / total for e, t in tiempos.items()}
    return _reparto(personas, con_desorden)[0]


def servicio(modo: str, q: float, personas: int, cocina: dict | None = None, desorden: float | None = None) -> dict:
    """La cola del almuerzo por cuartos de hora: pedidos que llegan, menús que
    salen, cuántos esperan y cuánto espera el último en llegar."""
    cocina = cocina or cargar()
    ritmo = ritmo_servicio(modo, personas, cocina, desorden)
    cola, tramos = 0.0, []
    for inicio, parte in _perfil(cocina):
        llegan = q * parte
        salen = min(cola + llegan, ritmo * 15)
        cola += llegan - salen
        tramos.append({"inicio": inicio, "llegan": llegan, "salen": salen, "cola": cola, "espera": cola / ritmo})
    while cola > 1e-6:  # se sigue despachando lo que quedó
        inicio = tramos[-1]["inicio"] + 15
        salen = min(cola, ritmo * 15)
        cola -= salen
        tramos.append({"inicio": inicio, "llegan": 0.0, "salen": salen, "cola": cola, "espera": cola / ritmo})
    return {"modo": modo, "q": q, "personas": personas, "ritmo_hora": ritmo * 60, "tramos": tramos,
            "espera_maxima": max(t["espera"] for t in tramos),
            "aguanta": max(t["espera"] for t in tramos) <= cocina["servicio"]["espera_maxima"]}


def _tope_servicio(modo: str, personas: int, cocina: dict, desorden: float) -> float:
    """Menús al día con los que la espera llega justo al máximo (la espera
    crece en proporción a la venta, así que se busca por bisección)."""
    lo, hi = 0.0, 2000.0
    for _ in range(40):
        q = (lo + hi) / 2
        if servicio(modo, q, personas, cocina, desorden)["aguanta"]:
            lo = q
        else:
            hi = q
    return lo


def desorden_calibrado(cocina: dict | None = None) -> float:
    """Minutos de desorden por menú que hacen que la cocina de la calibración
    aguante justo los menús observados."""
    cocina = cocina or cargar()
    cal = cocina["servicio"]["calibracion"]
    lo, hi = 0.0, 30.0
    for _ in range(40):
        d = (lo + hi) / 2
        if _tope_servicio(cal["modo"], cal["personas"], cocina, d) > cal["menus"]:
            lo = d
        else:
            hi = d
    return (lo + hi) / 2


def capacidad_cocina(modo: str, personas: int, cocina: dict | None = None) -> dict:
    """Cuántos menús al día aguanta la cocina: lo que alcanza a preparar en la
    mañana y lo que alcanza a despachar en el almuerzo."""
    cocina = cocina or cargar()
    d = desorden_calibrado(cocina)
    t_serv = _tope_servicio(modo, personas, cocina, d)
    t_man = tope(modo, personas, cocina)
    return {"modo": modo, "personas": personas, "manana": t_man, "servicio": t_serv, "tope": min(t_man, t_serv),
            "limita": "mañana" if t_man < t_serv else "almuerzo"}


def jornada(modo: str, q: float, personas: int, cocina: dict | None = None, margen: int = 15) -> dict:
    """Horas que pasa la cocina en el local: entra lo justo para tener todo
    listo antes del almuerzo (con un margen), atiende y, si trabaja con mise en
    place, se queda a dejar lista la mañana siguiente."""
    cocina = cocina or cargar()
    r = plan(modo, q, personas, cocina)
    entra = r["servicio"] - margen - r["minutos_manana"]
    entra = 15 * (entra // 15)
    sale = minutos(cocina["servicio_fin"]) + (r["fin_tarde"] - minutos(cocina["tarde_inicio"]) if r["fin_tarde"] else 0)
    return {"entra": entra, "sale": sale, "horas": (sale - entra) / 60, "horas_persona": personas * (sale - entra) / 60}


def gente_necesaria(modo: str, q: float, cocina: dict | None = None, maximo: int = 10) -> int | None:
    """Menos personas en cocina con que se prepara la mañana a tiempo y se
    despacha el almuerzo sin pasar la espera máxima."""
    cocina = cocina or cargar()
    d = desorden_calibrado(cocina)
    for n in range(1, maximo + 1):
        if cabe(modo, q, n, cocina) and servicio(modo, q, n, cocina, d)["aguanta"]:
            return n
    return None
