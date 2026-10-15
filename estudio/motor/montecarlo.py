"""Monte Carlo de un año (portado de `simulate` del prototipo).

Usa el MISMO generador que el HTML (mulberry32 sembrado con FNV-1a), así
una corrida en Python da exactamente los mismos números que la calculadora.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .modelo import Escenario, Local, modelo

N_CORRIDAS = 2000
_M32 = 0xFFFFFFFF


def _i32(x: int) -> int:
    x &= _M32
    return x - 0x100000000 if x & 0x80000000 else x


def _imul(a: int, b: int) -> int:
    return _i32((a & _M32) * (b & _M32))


def fnv1a(texto: str) -> int:
    """`hash` del prototipo (FNV-1a de 32 bits con Math.imul)."""
    h = _i32(2166136261)
    for ch in texto:
        h = _imul(h ^ ord(ch), 16777619)
    return h


def mulberry32(semilla: int):
    """`rng` del prototipo: devuelve una función que da floats en [0, 1)."""
    estado = [_i32(semilla)]

    def siguiente() -> float:
        estado[0] = _i32(estado[0] + 0x6D2B79F5)
        s = estado[0]
        t = _imul(s ^ ((s & _M32) >> 15), 1 | s)
        t = _i32(t + _imul(t ^ ((t & _M32) >> 7), 61 | t)) ^ t
        return (((t ^ ((t & _M32) >> 14)) & _M32)) / 4294967296

    return siguiente


def normal(r) -> float:
    u = v = 0.0
    while u == 0:
        u = r()
    while v == 0:
        v = r()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


def triangular(r, a: float, m: float, b: float) -> float:
    if b <= a:
        return m
    u, f = r(), (m - a) / (b - a)
    return a + math.sqrt(u * (b - a) * (m - a)) if u < f else b - math.sqrt((1 - u) * (b - a) * (b - m))


@dataclass(frozen=True)
class ResultadoMC:
    prob_perdida: float
    p10: float
    p50: float
    p90: float


def simular(local: Local, esc: Escenario, nacional: dict, riesgo: dict, q_ref: float,
            incluir_precio: bool = True, n: int = N_CORRIDAS) -> ResultadoMC:
    """Utilidad de un año: volumen lognormal, insumos normal, precio
    triangular en el rango (±4 % si es dato propio) y conflicto social que
    quita 2–8 semanas de contribución con la probabilidad anual de la ciudad."""
    formal = "1" if esc.formal else "0"
    seg = "pop" if esc.pop else "ejec"
    # Misma semilla que el prototipo: id + seg + year + formal + qref
    q_txt = str(int(q_ref)) if float(q_ref).is_integer() else str(q_ref)
    r = mulberry32(fnv1a(f"{local.id}{seg}{esc.anio}{formal}{q_txt}"))
    sd_q, sd_i = riesgo["sd_volumen"], riesgo["sd_insumos_anual"]
    salida = []
    perdidas = 0
    for _ in range(n):
        q = max(5, q_ref * math.exp(sd_q * normal(r) - sd_q * sd_q / 2))
        ins_mult = max(0.6, 1 + sd_i * normal(r))
        precio = local.precio
        if incluir_precio:
            if local.precio_propio:
                precio = local.precio * (1 + 0.04 * normal(r))
            else:
                precio = triangular(r, min(local.pmin, local.precio), local.precio, max(local.pmax, local.precio))
        m = modelo(local, _redondeo_js(q), esc, nacional, precio=precio, ins_mult=ins_mult)
        perdida = 0.0
        if r() < local.riesgo_conflicto_anual:
            perdida = (2 + r() * 6) / 52
        anual = 12 * (m.contrib_u * m.q_mes * (1 - perdida)) - 12 * m.fijos
        salida.append(anual)
        if anual < 0:
            perdidas += 1
    salida.sort()
    return ResultadoMC(perdidas / n, salida[int(n * 0.1)], salida[int(n * 0.5)], salida[int(n * 0.9)])


def _redondeo_js(x: float) -> int:
    """Math.round de JS (las mitades suben siempre)."""
    return math.floor(x + 0.5)
