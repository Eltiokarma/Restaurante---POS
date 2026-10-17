"""Cuánto puede producir cada cocina con la gente que tiene.

El modelo arma la planilla según la venta, pero no al revés: no se pregunta
si esa gente alcanza para esa venta. Aquí se mide con lo observado en
Candela: con 3 personas en cocina y 3 mozos aguanta hasta S/ 1 100 al día a
S/ 11 (~100 menús); con 2 mozos también, pero sobreexigidos.
"""
from __future__ import annotations

import math

# Menús al día que saca cada persona en el almuerzo, en su tope
POR_COCINA = 100 / 3  # ~33: 3 en cocina aguantan ~100 menús
POR_MOZO = 100 / 2  # 50: con 2 mozos aguantan ~100, sobreexigidos (con 3, ~33 cómodos)


def gente(datos: dict, resultado) -> tuple[int, int]:
    """Personas en cocina y en salón durante el almuerzo. Si el escenario
    trae planilla, se cuenta de ahí (incluye a la familia sin sueldo); quien
    pone el local y además cocina o atiende se suma aparte."""
    e = datos["escenario"]
    if not e.get("planilla"):
        return resultado.cocina, resultado.mozos
    cocina = sum(t.get("cantidad", 1) for t in e["planilla"] if t.get("area") == "cocina" and t.get("turno") != "noche")
    salon = sum(t.get("cantidad", 1) for t in e["planilla"] if t.get("area") == "salon" and t.get("turno") != "noche")
    en_planilla = {t.get("puesto", "").split(" (")[0].lower() for t in e["planilla"]}
    for p in datos.get("casa") or []:
        if p["quien"].split(" (")[0].lower() in en_planilla:
            continue  # ya está en la planilla (la familia sin sueldo)
        if p["rol"] in ("cocinero", "ayudante"):
            cocina += 1
        elif p["rol"] == "mozo":
            salon += 1
    if salon == 0 and cocina > 1:
        cocina, salon = cocina - 1, 1  # sin mozo, alguien de cocina sale a atender
    return cocina, salon


def capacidad(cocina: int, salon: int) -> dict:
    """Techo de venta diaria y qué lo limita."""
    tope_cocina = cocina * POR_COCINA
    tope_salon = salon * POR_MOZO
    return {"cocina": cocina, "salon": salon, "tope_cocina": tope_cocina, "tope_salon": tope_salon,
            "tope": min(tope_cocina, tope_salon), "limita": "cocina" if tope_cocina <= tope_salon else "salón"}


def faltan(q: float, cocina: int, salon: int) -> tuple[int, int]:
    """Cuánta gente falta en cocina y en salón para vender q menús."""
    return max(0, math.ceil(q / POR_COCINA) - cocina), max(0, math.ceil(q / POR_MOZO) - salon)
