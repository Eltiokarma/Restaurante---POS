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
from motor.barrido import Factores, barrido, estres, mezcla_desde_analisis, resumen
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
                    noche=Noche(**e["noche"]) if e.get("noche") else None,
                    laboral_formal=e.get("laboral_formal"))
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


def corridas(nombre: str, datos: dict, mezcla=None) -> dict:
    """Barrido robusto y prueba de estrés de un caso (lo mismo que corre el
    servicio en la pestaña Corridas)."""
    local, esc, sup, q = armar(datos)
    f = Factores(mezcla=sorted({0.25, mezcla.parte_actual, 0.75}) if mezcla else [None])
    if (datos.get("barrido") or {}).get("elasticidad"):
        f.elasticidad = datos["barrido"]["elasticidad"]
    r = barrido(local, esc, q, NAC, RIESGO, sup, f, mezcla)
    porciones = {}
    for d in r["decisiones"]:  # peor caso por precio y porción (mejor mezcla y turno)
        clave = f"{d['precio']}|{d['calidad']}"
        if clave not in porciones or d["utilidad_peor"] > porciones[clave]["utilidad_peor"]:
            porciones[clave] = d
    return {"nombre": nombre, "precio0": local.precio, "q0": q, **resumen(r),
            "decisiones": r["decisiones"][:15], "por_precio_porcion": list(porciones.values()),
            "estres": estres(local, esc, q, NAC, RIESGO)}


HORAS_MES = 60 * 4.33  # supuesto: 60 horas a la semana de quien trabaja sin sueldo


def hallazgos(arquetipos: list[dict], candela_datos: dict | None) -> dict:
    """Cálculos puntuales para la discusión del ensayo."""
    from dataclasses import replace as rep

    from motor.flujo import TOPE_NRUS
    from motor.modelo import Noche, Trabajador

    casos = {a["nombre"]: a["datos"] for a in arquetipos}
    if candela_datos:
        casos["Candela (datos del POS)"] = candela_datos
    salida: dict = {"noche": [], "medio_sol": [], "hora": [], "rmv_hora": 1230 / (48 * 4.33)}
    for nombre, datos in casos.items():
        local, esc, _sup, q = armar(datos)
        e0 = rep(esc, noche=None)
        u0 = modelo(local, q, e0, NAC).util
        umbral = next((qn for qn in range(1, 151) if modelo(
            local, q, rep(e0, noche=Noche(q=qn, precio=local.precio + 1, insumos=local.insumos * 1.05)), NAC).util > u0),
            None)
        salida["noche"].append({"nombre": nombre, "umbral": umbral, "planilla_propia": bool(esc.planilla)})
        m = modelo(local, q, esc, NAC)
        du = modelo(local.con(precio=local.precio + 0.5), q, esc, NAC).util - m.util
        salida["medio_sol"].append({"nombre": nombre, "soles": du, "menus": du / (m.contrib_u * esc.dias)})
    for nombre, personas in (("Dueña que cocina", 1), ("Familia sin sueldos", 3), ("Puesto de mercado informal", 1)):
        local, esc, _sup, q = armar(casos[nombre])
        m = modelo(local, q, esc, NAC)
        ingreso = m.util + (1500 if esc.sueldo_dueno else 0)
        salida["hora"].append({"nombre": nombre, "personas": personas, "ingreso": ingreso,
                               "por_hora": ingreso / personas / HORAS_MES})
    # Trampa del Nuevo RUS: el chiquito creciendo
    local, esc, _sup, _q = armar(casos["Chiquito en Nuevo RUS"])
    curva = []
    for qq in range(20, 61, 2):
        ventas = local.precio * qq * esc.dias
        nrus = modelo(local, qq, esc, NAC, igv=0).util - (20 if ventas <= 5000 else 50)
        mr = modelo(local, qq, esc, NAC)
        curva.append({"q": qq, "ventas_anio": ventas * 12, "cabe_nrus": ventas * 12 <= TOPE_NRUS, "nrus": nrus,
                      "rer": mr.util - 0.015 * mr.ventas_netas})
    ultimo = max((c for c in curva if c["cabe_nrus"]), key=lambda c: c["q"])
    recupera = next((c for c in curva if not c["cabe_nrus"] and c["rer"] >= ultimo["nrus"]), None)
    salida["nrus"] = {"curva": curva, "q_tope": ultimo["q"], "nrus_tope": ultimo["nrus"],
                      "rer_justo_despues": next(c["rer"] for c in curva if not c["cabe_nrus"]),
                      "q_recupera": recupera["q"] if recupera else None}
    # Precio de Candela con la planilla fija (sin el escalón del mozo)
    if candela_datos:
        local, esc, _sup, q = armar(candela_datos)
        m = modelo(local, q, esc, NAC)
        fijo = rep(esc, planilla=(Trabajador("Cocinero", max(local.sueldo_cocinero, 1230 * 1.06)),
                                  Trabajador("Ayudante", local.sueldo_ayudante),
                                  Trabajador("Mozo", local.sueldo_mozo, area="salon", cantidad=m.mozos)))
        deltas = [0, 0.5, 1, 1.5, 2, 2.5, 3]
        tabla = {}
        for modo, e_ in (("automatica", esc), ("fija", fijo)):
            tabla[modo] = {}
            for el in (0.5, 1.0, 1.5, 2.0):
                tabla[modo][str(el)] = [
                    {"precio": local.precio + dp,
                     "utilidad": modelo(local.con(precio=local.precio + dp),
                                        q * ((local.precio + dp) / local.precio) ** (-el), e_, NAC).util}
                    for dp in deltas]

        def u(el, dp):
            pr = local.precio + dp
            return modelo(local.con(precio=pr), q * (pr / local.precio) ** (-el), fijo, NAC).util

        lo, hi = 0.0, 10.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if u(mid, 1) > u(0, 0) else (lo, mid)
        salida["precio_candela"] = {"tabla": tabla, "umbral_elasticidad_mas1": lo, "base": m.util}
    return salida


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
    candela = platos = g = None
    guardados = _api("/escenarios")
    if guardados:
        g = next((x for x in guardados if x["nombre"].startswith("Candela")), None)
        if g:
            candela = caso(g["nombre"], g["datos"])
            platos = _api("/platos/analisis?igv=10.5&formal=true")
    mezcla = mezcla_desde_analisis(platos) if platos else None
    robustez = [corridas(a["nombre"], a["datos"]) for a in arquetipos]
    if candela:
        robustez.append(corridas(g["nombre"], g["datos"], mezcla))
    datos = {
        "hallazgos": hallazgos(arquetipos, g["datos"] if candela else None),
        "ciudades": ciudades(), "casos": casos, "candela": candela, "platos": platos, "robustez": robustez,
        "nacional": {k: v for k, v in NAC.items() if k != "notas"}, "riesgo": {k: v for k, v in RIESGO.items() if k != "notas"},
        "fuentes": DATA["fuentes"], "regimenes": list(REGIMENES),
    }
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return datos


if __name__ == "__main__":
    d = generar()
    print(len(d["casos"]), "casos;", "con Candela" if d["candela"] else "sin Candela")
