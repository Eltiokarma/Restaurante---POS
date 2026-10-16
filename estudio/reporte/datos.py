"""Calcula todo lo que necesita el ensayo y lo guarda en salida/datos.json.

Los restaurantes tipo salen de data/arquetipos.json (públicos). El caso de
Candela es privado: se pide al servicio del estudio en Railway si están
ESTUDIO_URL y ESTUDIO_TOKEN; si no, el ensayo sale sin él. La salida no se
sube al repositorio.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import asdict
from pathlib import Path

from motor import Escenario, cargar_dataset, equilibrio, local_de_ciudad, modelo, precio_minimo, simular
from motor.flujo import NOMBRE_REGIMEN, REGIMENES, Supuestos, comparar_regimenes, flujo_caja
from motor.modelo import Noche, Trabajador
from motor.montecarlo import muestras
from motor.sensibilidad import matriz, quiebres, tornado

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "salida"
DATA = cargar_dataset()
NAC, RIESGO = DATA["nacional"], DATA["riesgo"]
CIUDADES = {c["id"]: c for c in DATA["ciudades"]}
CAMPOS_LOCAL = ("precio", "insumos", "alquiler_mes", "sueldo_cocinero", "sueldo_ayudante", "sueldo_mozo",
                "gas_balon45", "servicios_mes")
CAMPOS_SUP = ("inversion", "meses_arranque", "arranque_desde", "crecimiento_q", "inflacion", "alza_precio",
              "alza_rmv", "tasa_descuento", "regimen")


def armar(datos: dict):
    """Lo mismo que hace la API con un escenario guardado."""
    e = datos["escenario"]
    local = local_de_ciudad(CIUDADES[e["ciudad_id"]], e.get("segmento", "popular"))
    cambios = {k: e[k] for k in CAMPOS_LOCAL if e.get(k) is not None}
    local = local.con(precio_propio="precio" in cambios, **cambios)
    esc = Escenario(segmento=e.get("segmento", "popular"), anio=e.get("anio", 2026), formal=e.get("formal", True),
                    balones=e.get("balones", 5), sueldo_dueno=e.get("sueldo_dueno", True), dias=e.get("dias", 26),
                    planilla=tuple(Trabajador(**t) for t in e.get("planilla") or []),
                    noche=Noche(**e["noche"]) if e.get("noche") else None)
    s = datos.get("supuestos", {})
    q = e.get("q", 100)
    sup = Supuestos(q=q, **{k: s[k] for k in CAMPOS_SUP if k in s})
    return local, esc, sup, q


def caso(nombre: str, datos: dict) -> dict:
    local, esc, sup, q = armar(datos)
    m = modelo(local, q, esc, NAC)
    mc = simular(local, esc, NAC, RIESGO, q_ref=q)
    fl = flujo_caja(local, esc, NAC, sup)
    netas = m.ventas_netas
    insumos = m.var_u * m.q_mes + (m.p_net_noche - m.contrib_noche) * m.q_mes_noche
    otros = m.fijos - m.personal - m.alquiler - m.gas
    sueldo = 1500 if esc.sueldo_dueno else 0
    trabajadores = sum(t.cantidad for t in esc.planilla) if esc.planilla else m.cocina + m.mozos
    return {
        "nombre": nombre, "ficha": datos.get("ficha"),
        "precio": local.precio, "q": q, "formal": esc.formal, "noche": esc.noche is not None,
        "sueldo_dueno": esc.sueldo_dueno, "trabajadores": trabajadores, "regimen": NOMBRE_REGIMEN[sup.regimen],
        "inversion": sup.inversion,
        "ventas_mes": m.ventas, "ventas_netas": netas, "utilidad_mes": m.util, "margen": m.margen,
        "ingreso_dueno": m.util + sueldo, "equilibrio": equilibrio(local, esc, NAC),
        "precio_minimo": precio_minimo(local, q, esc, NAC),
        "estructura": {"insumos": insumos / netas, "personal": m.personal / netas, "alquiler": m.alquiler / netas,
                       "gas": m.gas / netas, "otros": otros / netas, "utilidad": m.util / netas},
        "mc": {"prob_perdida": mc.prob_perdida, "p10": mc.p10, "p50": mc.p50, "p90": mc.p90,
               "muestras": [round(x) for x in muestras(local, esc, NAC, RIESGO, q_ref=q)]},
        "quiebres": {x["variable"]: x["cambio"] for x in quiebres(local, esc, q, NAC)},
        "tornado": tornado(local, esc, q, NAC, 0.10),
        "flujo": {"van": fl.van, "tir": fl.tir, "recupero": fl.recupero,
                  "recupero_descontado": fl.recupero_descontado, "alertas": fl.alertas,
                  "anios": [asdict(a) for a in fl.anios]},
        "regimenes": comparar_regimenes(local, esc, NAC, sup),
        "matriz": matriz(local, esc, q, NAC),
    }


def ciudades() -> list[dict]:
    """Equilibrio de referencia del brief (popular, formal, 100 menús, 5
    balones, sin sueldo del dueño) y sus variantes."""
    salida = []
    for c in DATA["ciudades"]:
        local = local_de_ciudad(c)
        fila = {"id": c["id"], "nombre": c["nombre"], "precio": c["precio_popular"],
                "precio_fuente": c.get("precio_popular_fuente"), "confianza": c.get("confianza")}
        for anio in (2026, 2027, 2028):
            fila[f"eq_{anio}"] = equilibrio(local, Escenario(anio=anio, sueldo_dueno=False), NAC)
        fila["eq_con_sueldo"] = equilibrio(local, Escenario(), NAC)
        fila["eq_informal"] = equilibrio(local, Escenario(formal=False, sueldo_dueno=False), NAC)
        salida.append(fila)
    return sorted(salida, key=lambda f: f["eq_2026"])


def _api(ruta: str):
    url, token = os.getenv("ESTUDIO_URL"), os.getenv("ESTUDIO_TOKEN")
    if not url or not token:
        return None
    req = urllib.request.Request(url.rstrip("/") + "/api" + ruta, headers={"X-Token": token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def generar() -> dict:
    arquetipos = json.loads((RAIZ.parent / "data" / "arquetipos.json").read_text(encoding="utf-8"))
    casos = [caso(a["nombre"], a["datos"]) for a in arquetipos]
    candela = platos = None
    guardados = _api("/escenarios")
    if guardados:
        g = next((x for x in guardados if x["nombre"].startswith("Candela")), None)
        if g:
            candela = caso(g["nombre"], g["datos"])
            platos = _api("/platos/analisis?igv=10.5&formal=true")
    datos = {
        "ciudades": ciudades(), "casos": casos, "candela": candela, "platos": platos,
        "nacional": {k: v for k, v in NAC.items() if k != "notas"}, "riesgo": {k: v for k, v in RIESGO.items() if k != "notas"},
        "fuentes": DATA["fuentes"], "regimenes": list(REGIMENES),
    }
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return datos


if __name__ == "__main__":
    d = generar()
    print(len(d["casos"]), "casos;", "con Candela" if d["candela"] else "sin Candela")
