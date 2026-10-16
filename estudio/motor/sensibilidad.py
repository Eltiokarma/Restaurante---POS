"""Sensibilidad: qué número mueve más la utilidad del mes, cuánto puede
moverse cada uno antes de perder y la tabla precio × menús/día.

Mismo `modelo` del simulador; cada variable se mueve sola, el resto queda
quieto."""
from __future__ import annotations

from dataclasses import replace

from .modelo import ANIOS, Escenario, Local, modelo

# variable -> (nombre para la pantalla, cómo aplicarle un factor)
VARIABLES = {
    "precio": "Precio del menú",
    "q": "Menús al día",
    "insumos": "Insumos por menú",
    "sueldos": "Sueldos",
    "alquiler_mes": "Alquiler",
    "gas": "Gas",
    "servicios_mes": "Luz, agua e internet",
    "dias": "Días que abre al mes",
}


def _aplicar(var: str, factor: float, local: Local, esc: Escenario, q: float):
    if var == "precio":
        return local.con(precio=local.precio * factor), esc, q
    if var == "q":
        return local, esc, q * factor
    if var == "insumos":
        return local.con(insumos=local.insumos * factor), esc, q
    if var == "sueldos":
        local = local.con(sueldo_cocinero=local.sueldo_cocinero * factor,
                          sueldo_ayudante=local.sueldo_ayudante * factor,
                          sueldo_mozo=local.sueldo_mozo * factor)
        esc = replace(esc, planilla=tuple(t.con(monto=t.monto * factor) for t in esc.planilla))
        return local, esc, q
    if var == "gas":
        return local.con(gas_balon45=local.gas_balon45 * factor), esc, q
    if var == "dias":
        return local, replace(esc, dias=esc.dias * factor), q
    return local.con(**{var: getattr(local, var) * factor}), esc, q


def utilidad(var: str, factor: float, local: Local, esc: Escenario, q: float, nacional: dict) -> float:
    lo, es, qq = _aplicar(var, factor, local, esc, q)
    return modelo(lo, qq, es, nacional).util


def tornado(local: Local, esc: Escenario, q: float, nacional: dict, delta: float = 0.10) -> list[dict]:
    """Utilidad del mes con cada variable un `delta` abajo y arriba,
    ordenado de la que más mueve a la que menos."""
    base = modelo(local, q, esc, nacional).util
    filas = []
    for var, nombre in VARIABLES.items():
        abajo = utilidad(var, 1 - delta, local, esc, q, nacional)
        arriba = utilidad(var, 1 + delta, local, esc, q, nacional)
        filas.append({"variable": var, "nombre": nombre, "abajo": round(abajo, 2), "arriba": round(arriba, 2),
                      "rango": round(abs(arriba - abajo), 2)})
    filas.sort(key=lambda f: -f["rango"])
    return [{"base": round(base, 2), **f} for f in filas]


def quiebre(var: str, local: Local, esc: Escenario, q: float, nacional: dict) -> float | None:
    """Cambio (en fracción, p. ej. −0.12) que deja la utilidad en cero.
    None si no cruza el cero entre −95 % y +500 %."""
    def u(c: float) -> float:
        return utilidad(var, 1 + c, local, esc, q, nacional)

    u0 = u(0.0)
    if u0 == 0:
        return 0.0
    # Buscar hacia el lado que empeora: probar ambos y quedarse con el más cercano
    candidatos = []
    for extremo in (-0.95, 5.0):
        if u0 * u(extremo) < 0:
            a, b = 0.0, extremo
            for _ in range(60):
                m = (a + b) / 2
                if u0 * u(m) > 0:
                    a = m
                else:
                    b = m
            candidatos.append((a + b) / 2)
    if not candidatos:
        return None
    return round(min(candidatos, key=abs), 4)


def quiebres(local: Local, esc: Escenario, q: float, nacional: dict) -> list[dict]:
    return [{"variable": v, "nombre": n, "cambio": quiebre(v, local, esc, q, nacional)} for v, n in VARIABLES.items()]


def matriz(local: Local, esc: Escenario, q: float, nacional: dict) -> dict:
    """Utilidad del mes para precios de −S/ 2 a +S/ 2 (de 50 en 50
    céntimos) y volúmenes del 50 % al 150 % de q."""
    precios = [round(local.precio + d / 2, 2) for d in range(-4, 5) if local.precio + d / 2 > 0]
    volumenes = sorted({max(5, round(q * k / 10)) for k in range(5, 16)})
    filas = [[round(modelo(local.con(precio=p), v, esc, nacional).util) for p in precios] for v in volumenes]
    return {"precios": precios, "volumenes": volumenes, "utilidad": filas}


__all__ = ["ANIOS", "VARIABLES", "matriz", "quiebre", "quiebres", "tornado"]
