"""Calcula todo lo que necesita el ensayo y lo guarda en salida/datos.json.

Los restaurantes tipo salen de data/arquetipos.json (públicos). El caso de
Candela es privado: se pide al servicio del estudio en Railway si están
ESTUDIO_URL y ESTUDIO_TOKEN; si no, el ensayo sale sin él. La salida no se
sube al repositorio.
"""
from __future__ import annotations

import json
import math
import os
import urllib.request
from dataclasses import asdict
from pathlib import Path

from motor import Escenario, cargar_dataset, equilibrio, local_de_ciudad, modelo, precio_minimo, simular
from motor.flujo import NOMBRE_REGIMEN, REGIMENES, Supuestos, comparar_regimenes, flujo_caja
from motor.igualdad import BASE as BASE_IGUAL, GRUPOS, igualar, personas_casa, shapley
from motor.incertidumbre import RANGOS, perturbar
from motor.trabajo import casa_desde, trabajo_de_la_casa
from motor import capacidad as cap
from motor import cocina as coc
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
        "montos": {"ventas": m.ventas, "netas": netas, "igv": m.ventas - netas, "insumos": insumos,
                   "personal": m.personal, "alquiler": m.alquiler, "gas": m.gas, "otros": otros,
                   "contrib_u": m.contrib_u, "dias": esc.dias},
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


# Sensibilidad de la clientela al precio medida en Juliaca (historia de
# Candela: la que mejor ajusta sus tres precios es ~2.4), con un margen a cada
# lado. Los restaurantes tipo se prueban con ella y con la supuesta de antes.
ELASTICIDAD_JULIACA = [1.5, 2.4, 3.5]


def corridas(nombre: str, datos: dict, mezcla=None, elasticidad: list[float] | None = None,
             con_estres: bool = True) -> dict:
    """Barrido robusto y prueba de estrés de un caso (lo mismo que corre el
    servicio en la pestaña Corridas)."""
    local, esc, sup, q = armar(datos)
    f = Factores(mezcla=sorted({0.25, mezcla.parte_actual, 0.75}) if mezcla else [None])
    b = datos.get("barrido") or {}
    if elasticidad:
        f.elasticidad = elasticidad
    elif b.get("elasticidad"):
        f.elasticidad = b["elasticidad"]
    if b.get("precio"):
        f.precio = b["precio"]
    f.capacidad = b.get("capacidad")
    r = barrido(local, esc, q, NAC, RIESGO, sup, f, mezcla)
    porciones = {}
    for d in r["decisiones"]:  # peor caso por precio y porción (mejor mezcla y turno)
        clave = f"{d['precio']}|{d['calidad']}"
        if clave not in porciones or d["utilidad_peor"] > porciones[clave]["utilidad_peor"]:
            porciones[clave] = d
    return {"nombre": nombre, "precio0": local.precio, "q0": q, **resumen(r),
            "decisiones": r["decisiones"][:15], "por_precio_porcion": list(porciones.values()),
            "elasticidad": f.elasticidad, "capacidad": f.capacidad,
            "estres": estres(local, esc, q, NAC, RIESGO) if con_estres else None}


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
    for nombre, personas in (("Propietario que cocina", 1), ("Familiar sin sueldos", 3), ("Puesto de mercado informal", 1)):
        local, esc, _sup, q = armar(casos[nombre])
        m = modelo(local, q, esc, NAC)
        ingreso = m.util + (1500 if esc.sueldo_dueno else 0)
        salida["hora"].append({"nombre": nombre, "personas": personas, "ingreso": ingreso,
                               "por_hora": ingreso / personas / HORAS_MES})
    # Trampa del Nuevo RUS: el pequeño creciendo
    local, esc, _sup, _q = armar(casos["Pequeño en Nuevo RUS"])
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
    # Alquiler expresado en menús diarios que hay que vender para pagarlo
    salida["alquiler"] = []
    for nombre, datos in casos.items():
        local, esc, _sup, q = armar(datos)
        m = modelo(local, q, esc, NAC)
        salida["alquiler"].append({"nombre": nombre, "alquiler": m.alquiler,
                                   "menus": m.alquiler / (m.contrib_u * esc.dias) if m.contrib_u > 0 else None})
    if candela_datos:
        local, esc, _sup, q = armar(candela_datos)
        m = modelo(local, q, esc, NAC)

        def u(el, dp, e_=esc):
            pr = local.precio + dp
            return modelo(local.con(precio=pr), q * (pr / local.precio) ** (-el), e_, NAC).util

        lo, hi = 0.0, 10.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if u(mid, 1) > u(0, 0) else (lo, mid)
        sin_igv = rep(esc, formal=False, laboral_formal=False)
        salida["precio_candela"] = {
            "umbral_elasticidad_mas1": lo, "base": m.util,
            "sin_igv": modelo(local, q, sin_igv, NAC).util,
            "historia": HISTORIA,
            # 10 → 11: del par más favorable al más desfavorable, y el central
            "elasticidad_arco": [math.log(HISTORIA["q0_bajo"] / HISTORIA["q1_alto"]) / math.log(1.1),
                                 math.log(HISTORIA["q0_alto"] / HISTORIA["q1_bajo"]) / math.log(1.1)],
            "elasticidad_central": math.log(HISTORIA["q0"] / HISTORIA["q1"]) / math.log(1.1),
            "elasticidad_ajuste": _ajuste_elasticidad(),
            "q0": HISTORIA["q0"],
            "a_10": modelo(local.con(precio=10.0), HISTORIA["q0"], esc, NAC).util,
            "a_10_sin_igv": modelo(local.con(precio=10.0), HISTORIA["q0"], sin_igv, NAC).util,
            "a_15": modelo(local.con(precio=15.0), HISTORIA["q_abrir"], esc, NAC).util,
            "a_15_sin_igv": modelo(local.con(precio=15.0), HISTORIA["q_abrir"], sin_igv, NAC).util,
            "equilibrio_15_sin_igv": equilibrio(local.con(precio=15.0), sin_igv, NAC),
            "curvas_demanda": {str(el): [{"precio": 9 + 0.5 * k, "q": q * ((9 + 0.5 * k) / local.precio) ** (-el)}
                                         for k in range(13)] for el in (1.0, 2.0, 2.4, 3.0, 4.0)},
        }
    return salida


# Historia de precios de Candela (entrevista, oct-2026): venta diaria en caja
HISTORIA = {"p_abrir": 15.0, "q_abrir": 500 / 15, "q_abrir_bajo": 450 / 15, "q_abrir_alto": 550 / 15,
            "p0": 10.0, "q0": 90.0, "q0_bajo": 80.0, "q0_alto": 100.0,
            "p1": 11.0, "q1": 775 / 11, "q1_bajo": 750 / 11, "q1_alto": 800 / 11}


def _ajuste_elasticidad() -> float:
    """Elasticidad constante que mejor ajusta (mínimos cuadrados en
    logaritmos) los tres puntos de la historia de Candela."""
    h = HISTORIA
    pts = [(h["p_abrir"], h["q_abrir"]), (h["p0"], h["q0"]), (h["p1"], h["q1"])]
    xs = [math.log(p) for p, _ in pts]
    ys = [math.log(q) for _, q in pts]
    mx, my = sum(xs) / 3, sum(ys) / 3
    return -sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


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
        if c["id"] == "juliaca":
            # experimento: la misma Juliaca con el precio que se observa en Candela
            obs = local.con(precio=PRECIO_JULIACA_OBSERVADO, precio_propio=True)
            fila = {**fila, "id": "juliaca_obs", "nombre": "Juliaca (observado)", "precio": PRECIO_JULIACA_OBSERVADO,
                    "precio_fuente": "local"}
            for anio in (2026, 2027, 2028):
                fila[f"eq_{anio}"] = equilibrio(obs, Escenario(anio=anio, sueldo_dueno=False), NAC)
            fila["eq_con_sueldo"] = equilibrio(obs, Escenario(), NAC)
            fila["eq_informal"] = equilibrio(obs, Escenario(formal=False, sueldo_dueno=False), NAC)
            salida.append(fila)
    return sorted(salida, key=lambda f: f["eq_2026"])


# Precio del menú que se observa en Juliaca: el de Candela (un solo local; el
# dataset estima S/ 8 a partir del ingreso y lo deja tal cual por la paridad
# con la calculadora original)
PRECIO_JULIACA_OBSERVADO = 11.0


def igualdad(arquetipos: list[dict], candela: dict | None) -> dict:
    """Cada negocio con sus números y en el local de referencia (mismo
    precio, venta, alquiler, insumos, gas y luz): lo que queda distinto es
    cómo se organiza."""
    pares = [(a["nombre"], a["datos"]) for a in arquetipos]
    if candela:
        pares.append(("Candela (datos del POS)", candela))

    def medir(datos: dict) -> dict:
        local, esc, _sup, q = armar(datos)
        m = modelo(local, q, esc, NAC)
        ingreso = m.util + (1500 if esc.sueldo_dueno else 0)
        personas = personas_casa(datos["escenario"])
        return {"utilidad": m.util, "ingreso": ingreso, "personas": personas,
                "por_persona": ingreso / personas if personas else None,
                "personal": m.personal, "equilibrio": equilibrio(local, esc, NAC)}

    filas = [{"nombre": n, "propio": medir(d), "igual": medir(igualar(d))} for n, d in pares]
    return {"base": BASE_IGUAL, "filas": filas, "ausencia": costo_de_no_estar(arquetipos),
            "descomposicion": descomponer(pares)}


REFERENCIA = "Propietario que cocina"


def descomponer(pares: list[tuple[str, dict]]) -> dict | None:
    """Del propietario que cocina a cada negocio, un factor a la vez: cuánto de la
    diferencia en lo que se lleva la casa viene del local y la venta, de los
    insumos, de quién trabaja, de la formalidad y de la noche."""
    ref = dict(pares).get(REFERENCIA)
    if not ref:
        return None

    def ingreso(escenario: dict) -> float:
        local, esc, _sup, q = armar({"escenario": escenario})
        return modelo(local, q, esc, NAC).util + (1500 if esc.sueldo_dueno else 0)

    base = ingreso(ref["escenario"])
    filas = []
    for nombre, datos in pares:
        if nombre == REFERENCIA:
            continue
        aportes = shapley(ingreso, ref["escenario"], datos["escenario"])
        filas.append({"nombre": nombre, "aportes": aportes, "propio": ingreso(datos["escenario"])})
    return {"referencia": REFERENCIA, "base": base, "grupos": [(c, t) for c, t, _ in GRUPOS], "filas": filas}


def costo_de_no_estar(arquetipos: list[dict]) -> list[dict] | None:
    """Del inversor al inversor ausente, en el local de referencia y un cambio a la
    vez: su cocina y salón, la gerencia pagada (administrador, cajero, compras),
    el contador externo y las compras más caras sin el ojo del dueño."""
    por_nombre = {a["nombre"]: a["datos"] for a in arquetipos}
    inv, aus = por_nombre.get("Inversor que supervisa"), por_nombre.get("Inversor ausente")
    if not inv or not aus:
        return None
    e_inv, e_aus = inv["escenario"], aus["escenario"]
    planilla = e_aus.get("planilla") or []
    operativa = [t for t in planilla if t.get("area") != "otro"]
    sobrecosto = e_aus["insumos"] / e_inv["insumos"]  # 6 % más caro sin el regateo del dueño
    contador = e_aus["servicios_mes"] - e_inv["servicios_mes"]

    def util(escenario: dict) -> float:
        local, esc, _sup, q = armar({"escenario": escenario})
        return modelo(local, q, esc, NAC).util

    base = igualar(inv)["escenario"]
    pasos = [("El inversor, que supervisa, compra y cobra sin sueldo", base)]
    e = {**base, "planilla": operativa}
    pasos.append(("Cocina y salón del inversor ausente (más gente y mejor pagada)", e))
    e = {**e, "planilla": planilla}
    pasos.append(("Gerencia pagada: administrador, cajero y encargado de compras", e))
    e = {**e, "servicios_mes": e["servicios_mes"] + contador}
    pasos.append(("Contador externo", e))
    e = {**e, "insumos": round(e["insumos"] * sobrecosto, 4)}
    pasos.append((f"Compras {round((sobrecosto - 1) * 100)} % más caras sin el control del dueño", e))
    salida, previo = [], None
    for texto, esc_ in pasos:
        u = util(esc_)
        salida.append({"paso": texto, "utilidad": u, "cambio": None if previo is None else u - previo})
        previo = u
    return salida


def trabajo(arquetipos: list[dict], candela: dict | None) -> list[dict]:
    """El trabajo que no se cobra, caso por caso: horas de la casa, lo que
    valdría ese trabajo a precio de mercado y la utilidad económica."""
    pares = [(a["nombre"], a["datos"]) for a in arquetipos]
    if candela:
        pares.append(("Candela (datos del POS)", candela))
    salida = []
    for nombre, datos in pares:
        local, esc, sup, q = armar(datos)
        m = modelo(local, q, esc, NAC)
        ingreso = m.util + (1500 if esc.sueldo_dueno else 0)
        casa = casa_desde(datos)
        salida.append({"nombre": nombre, "utilidad": m.util, "ingreso": ingreso,
                       "casa": [{"quien": c.quien, "rol": c.rol, "horas_semana": c.horas_semana} for c in casa],
                       **trabajo_de_la_casa(casa, ingreso, local, sup.inversion, sup.tasa_descuento)})
    return salida


def capacidades(arquetipos: list[dict], candela: dict | None) -> list[dict]:
    """Experimento: con la productividad observada en Candela, ¿alcanza la gente
    de cada negocio para su venta? Si falta, cuánto cuesta la que falta; si
    sobra, cuánto dejarían los menús que ya podría sacar."""
    pares = [(a["nombre"], a["datos"]) for a in arquetipos]
    if candela:
        pares.append(("Candela (datos del POS)", candela))
    salida = []
    for nombre, datos in pares:
        local, esc, _sup, q = armar(datos)
        m = modelo(local, q, esc, NAC)
        cocina, salon = cap.gente(datos, m)
        c = cap.capacidad(cocina, salon)
        f_cocina, f_salon = cap.faltan(q, cocina, salon)
        mult = 1.05 if esc.laboral else 1.0  # cargas de la microempresa, como el modelo
        costo = mult * (f_cocina * local.sueldo_ayudante + f_salon * local.sueldo_mozo)
        holgura = c["tope"] - q
        extra = modelo(local, c["tope"], esc, NAC).util - m.util if holgura >= 1 and esc.planilla else None
        salida.append({"nombre": nombre, "q": q, **c, "falta_cocina": f_cocina, "falta_salon": f_salon,
                       "costo_falta": costo, "utilidad": m.util, "utilidad_ajustada": m.util - costo,
                       "holgura": holgura, "valor_holgura": extra})
    return salida


def _costo_cocina(personas: int, horas_dia: float, sueldo: float, dias: int = 26) -> float:
    """Planilla de cocina al mes: sueldos más las horas sobre ocho al día, con
    25 % de recargo."""
    por_hora = sueldo / (48 * 4.33)
    return personas * (sueldo + max(0.0, horas_dia - 8) * dias * por_hora * 1.25)


def organizacion(arquetipos: list[dict], candela: dict | None) -> list[dict]:
    """Experimento: cada negocio organizando su cocina de cada forma. Cuánta
    gente necesita para su venta, cuánto se ahorra frente a la doméstica y
    cuántos menús aguantaría con la gente que tiene."""
    c = coc.cargar()
    pares = [(a["nombre"], a["datos"]) for a in arquetipos]
    if candela:
        pares.append(("Candela (datos del POS)", candela))
    salida = []
    for nombre, datos in pares:
        local, esc, _sup, q = armar(datos)
        m = modelo(local, q, esc, NAC)
        cocina_, _salon = cap.gente(datos, m)
        mult = 1.05 if esc.laboral else 1.0
        fila = {"nombre": nombre, "q": q, "cocina": cocina_, "modos": {}}
        base = None
        for modo in coc.MODOS:
            necesita = coc.gente_necesaria(modo, q, c)
            tope = coc.capacidad_cocina(modo, cocina_, c)["tope"] if cocina_ else 0
            costo = None
            if necesita:
                horas = coc.jornada(modo, q, necesita, c)["horas"]
                costo = _costo_cocina(necesita, horas, local.sueldo_ayudante) * mult
            if base is None:
                base = costo  # la doméstica; si no alcanza, la primera organización que sí
            ahorro = None if costo is None or base is None else base - costo
            fila["modos"][modo] = {"necesita": necesita, "tope": tope, "ahorro": ahorro, "costo": costo,
                                   "horas": None if not necesita else coc.jornada(modo, q, necesita, c)["horas"]}
        salida.append(fila)
    return salida


def cocina(q_candela: float | None, candela: dict | None = None) -> dict:
    """Experimento: la misma cocina trabajando de tres maneras. Gantt de la
    mañana, cola del almuerzo y cuántos menús aguanta cada forma de trabajar."""
    c = coc.cargar()
    q = round(q_candela) if q_candela else 74
    d = coc.desorden_calibrado(c)
    paneles = [("domestico", 3), ("bloques", 3), ("mise", 3), ("estaciones", 3), ("mise", 2)]
    gantt = []
    for modo, n in paneles:
        r = coc.plan(modo, q, n, c)
        j = coc.jornada(modo, q, n, c)
        gantt.append({**{k: r[k] for k in ("modo", "personas", "manana", "tarde", "puestos", "dueno", "listo", "inicio",
                                             "trabajo_manana", "trabajo_tarde", "cambios", "fin_tarde")},
                      "jornada": j, "espera": coc.servicio(modo, q, n, c, d)["espera_maxima"]})
    colas = [coc.servicio(m, q, n, c, d) for m, n in (("domestico", 3), ("domestico", 2), ("bloques", 2), ("mise", 2),
                                                        ("estaciones", 2))]
    # la misma comparación con gente más lenta y más rápida en la preparación
    velocidad = [{"factor": f, "topes": {m: coc.capacidad_cocina(m, 3, coc.con_velocidad(c, f))["tope"] for m in coc.MODOS},
                  "necesita": {m: coc.gente_necesaria(m, q, coc.con_velocidad(c, f)) for m in coc.MODOS}}
                 for f in (0.6, 1.0, 1.5)]
    capacidad = [{**coc.capacidad_cocina(m, n, c), "horas_persona": coc.jornada(m, q, n, c)["horas_persona"],
                  "espera_q": coc.servicio(m, q, n, c, d)["espera_maxima"]}
                 for m in coc.MODOS for n in (2, 3, 4)]
    # Candela con mise en place y una persona menos en cocina: se ahorra el
    # sueldo más bajo de la cocina y se pagan las horas sobre 8 de los que quedan
    ahorro = None
    if candela:
        sueldos = sorted(t["monto"] for t in candela["escenario"].get("planilla") or []
                         if t.get("area") == "cocina" for _ in range(t.get("cantidad", 1)))
        if len(sueldos) >= 3:
            j = coc.jornada("mise", q, len(sueldos) - 1, c)
            extra_h = max(0.0, j["horas"] - 8) * 26
            por_hora = [x / (48 * 4.33) for x in sueldos[1:]]
            costo_extra = sum(h * extra_h * 1.25 for h in por_hora)
            ahorro = {"sueldo": sueldos[0], "horas_dia": j["horas"], "costo_extra": costo_extra,
                      "neto": sueldos[0] - costo_extra, "personas": len(sueldos)}
    return {"q": q, "desorden": d, "gantt": gantt, "ahorro": ahorro, "velocidad": velocidad, "colas": colas, "capacidad": capacidad,
            "tareas": [{**t, "var": coc.variable(t)} for t in c["tareas"]], "notas": c["notas"], "servicio": c["servicio"], "perfil": c["demanda_15min"]["perfil"],
            "horarios": {k: c[k] for k in ("inicio", "almuerzo", "servicio_fin", "tarde_inicio", "tarde_fin", "cambio_estacion")},
            "estaciones": c["estaciones"], "platos": c["platos"]}


def entradas(arquetipos: list[dict], candela: dict | None) -> list[dict]:
    """Con qué números entra cada negocio a los análisis."""
    pares = [(a["nombre"], a["datos"]) for a in arquetipos]
    if candela:
        pares.append(("Candela (datos del POS)", candela))
    salida = []
    for nombre, datos in pares:
        local, esc, sup, q = armar(datos)
        m = modelo(local, q, esc, NAC)
        cocina_, salon = cap.gente(datos, m)
        salida.append({
            "nombre": nombre, "precio": local.precio, "q": q, "dias": esc.dias, "alquiler": local.alquiler_mes,
            "insumos": local.insumos, "balones": esc.balones, "servicios": local.servicios_mes,
            "gas_luz": esc.balones * local.gas_balon45 + local.servicios_mes,
            "cocina": cocina_, "salon": salon, "otros": sum(t.cantidad for t in esc.planilla if t.area == "otro"),
            "personal_mes": m.personal - (1500 if esc.sueldo_dueno else 0), "planilla_propia": bool(esc.planilla),
            "sueldo_dueno": esc.sueldo_dueno, "formal": esc.formal, "laboral": esc.laboral,
            "noche": None if esc.noche is None else {"q": esc.noche.q, "precio": esc.noche.precio},
            "inversion": sup.inversion, "regimen": NOMBRE_REGIMEN[sup.regimen],
        })
    return salida


def parametros() -> dict:
    """Los supuestos fijos de cada análisis, para los cuadros del ensayo."""
    from motor import trabajo as trb
    from motor.barrido import CALIDAD, GOLPES, N_MC, NOCHE_TIPO
    from motor.flujo import TOPE_NRUS

    jul = local_de_ciudad(CIUDADES["juliaca"], "popular")
    f = Factores()
    return {
        "juliaca": {"precio": jul.precio, "insumos": jul.insumos, "alquiler": jul.alquiler_mes,
                    "sueldo_cocinero": jul.sueldo_cocinero, "sueldo_ayudante": jul.sueldo_ayudante,
                    "sueldo_mozo": jul.sueldo_mozo, "gas_balon45": jul.gas_balon45, "servicios": jul.servicios_mes},
        "igualdad": dict(BASE_IGUAL),
        "grupos": [{"clave": c, "nombre": t, "campos": list(campos)} for c, t, campos in GRUPOS],
        "rangos": dict(RANGOS), "n_sorteos": N_SORTEOS,
        "riesgo": {k: v for k, v in RIESGO.items() if k != "notas"},
        "barrido": {"precio": f.precio, "calidad": {k: list(v) for k, v in CALIDAD.items()},
                    "elasticidad_supuesta": f.elasticidad, "elasticidad_medida": ELASTICIDAD_JULIACA, "n_mc": N_MC,
                    "noche": {"q": NOCHE_TIPO.q, "precio": NOCHE_TIPO.precio, "insumos": NOCHE_TIPO.insumos,
                              "balones": NOCHE_TIPO.balones, "servicios": NOCHE_TIPO.servicios}},
        "golpes": [n for k, n in GOLPES if k != "base"],
        "trabajo": {"jornada": trb.JORNADA_LEGAL, "recargo": trb.RECARGO_EXTRA, "administrador": trb.SUELDO_ADMINISTRADOR,
                    "tasa": 0.15},
        "capacidad": {"por_cocina": cap.POR_COCINA, "por_mozo": cap.POR_MOZO},
        "tope_nrus": TOPE_NRUS,
    }


def estados_anuales(arquetipos: list[dict], candela: dict | None) -> list[dict]:
    """Estado de resultados de un año lleno (el mes de cada negocio por doce),
    con el impuesto de su régimen. Es el apoyo visual de los anexos."""
    from motor.flujo import VIDA_UTIL, _impuesto_anual

    pares = [(a["nombre"], a["datos"]) for a in arquetipos]
    if candela:
        pares.append(("Candela (datos del POS)", candela))
    salida = []
    for nombre, datos in pares:
        local, esc, sup, q = armar(datos)
        m = modelo(local, q, esc, NAC)
        dueno = 1500.0 if esc.sueldo_dueno else 0.0
        ventas, netas = 12 * m.ventas, 12 * m.ventas_netas
        insumos = 12 * (m.var_u * m.q_mes + (m.p_net_noche - m.contrib_noche) * m.q_mes_noche)
        planilla = 12 * (m.personal - dueno)
        alquiler, gas = 12 * m.alquiler, 12 * m.gas
        otros = 12 * (m.fijos - m.personal - m.alquiler - m.gas)
        operativa = 12 * m.util
        deprec = sup.inversion / VIDA_UTIL
        impuesto = _impuesto_anual(sup.regimen, netas, operativa, deprec, NAC.get("uit_2026", 5500), [m.ventas] * 12)
        salida.append({
            "nombre": nombre, "regimen": NOMBRE_REGIMEN[sup.regimen], "q": q, "precio": local.precio,
            "dias": 12 * esc.dias, "menus": 12 * esc.dias * q, "ventas": ventas, "igv": ventas - netas, "netas": netas,
            "insumos": insumos, "contribucion": netas - insumos, "planilla": planilla, "dueno": 12 * dueno,
            "alquiler": alquiler, "gas": gas, "otros": otros, "operativa": operativa, "depreciacion": deprec,
            "antes_impuesto": operativa - deprec, "impuesto": impuesto, "neta": operativa - impuesto,
            "casa": operativa - impuesto + 12 * dueno,
        })
    return salida


PRECIOS_COMUNES = [7, 9, 10, 11, 12, 13, 15, 18]


def mismos_precios(arquetipos: list[dict], candela: dict | None) -> dict:
    """Experimento: todos los negocios a los mismos precios de pizarra. Para
    cada precio, los menús diarios que necesita cada uno para no perder (sin
    suponer nada sobre la clientela) y lo que se llevaría la casa si vendiera
    lo mismo que hoy (solo cambia el precio)."""
    pares = [(a["nombre"], a["datos"]) for a in arquetipos]
    if candela:
        pares.append(("Candela (datos del POS)", candela))
    filas = []
    for nombre, datos in pares:
        local, esc, _sup, q = armar(datos)
        sueldo = 1500 if esc.sueldo_dueno else 0
        eq, casa = {}, {}
        for pr in PRECIOS_COMUNES:
            l2 = local.con(precio=float(pr), precio_propio=True)
            eq[str(pr)] = equilibrio(l2, esc, NAC)
            casa[str(pr)] = modelo(l2, q, esc, NAC).util + sueldo
        filas.append({"nombre": nombre, "precio": local.precio, "q": q, "equilibrio": eq, "casa": casa,
                      "precio_minimo": precio_minimo(local, q, esc, NAC)})
    return {"precios": PRECIOS_COMUNES, "filas": filas}


N_SORTEOS = 1000


def robustez_supuestos(arquetipos: list[dict], candela: dict | None, n: int = N_SORTEOS, semilla: int = 7) -> dict:
    """Cuántas veces se sostiene cada hallazgo si los números de cada caso se
    mueven al azar dentro de rangos razonables (motor/incertidumbre.py)."""
    import random
    from dataclasses import replace as rep

    casos = {a["nombre"]: a["datos"] for a in arquetipos}
    if candela:
        casos["Candela (datos del POS)"] = candela

    def medir(datos: dict) -> dict:
        local, esc, _sup, q = armar(datos)
        m = modelo(local, q, esc, NAC)
        sueldo = 1500 if esc.sueldo_dueno else 0
        personas = personas_casa(datos["escenario"])
        valor = trabajo_de_la_casa(casa_desde(datos), m.util + sueldo, local)["valor_mercado"]
        return {"util": m.util, "ingreso": m.util + sueldo, "valor_trabajo": valor,
                "por_persona": (m.util + sueldo) / personas if personas else None,
                "sin_igv": modelo(local, q, rep(esc, formal=False, laboral_formal=False), NAC).util + sueldo,
                "sin_noche": modelo(local, q, rep(esc, noche=None), NAC).util if esc.noche else None}

    def ingreso(escenario: dict) -> float:
        local, esc, _sup, q = armar({"escenario": escenario})
        return modelo(local, q, esc, NAC).util + (1500 if esc.sueldo_dueno else 0)

    rng = random.Random(semilla)
    sorteos = []
    for _ in range(n):
        datos = {k: perturbar(v, rng) for k, v in casos.items()}
        r = {k: medir(v) for k, v in datos.items()}
        ap = shapley(ingreso, datos["Propietario que cocina"]["escenario"], datos["Puesto de mercado informal"]["escenario"])
        r["_puesto"] = ap
        sorteos.append(r)

    rmv_hora = 1230 / (48 * 4.33)
    pruebas = [
        ("El propietario que cocina se lleva más que el inversor",
         lambda r: r["Propietario que cocina"]["ingreso"] > r["Inversor que supervisa"]["ingreso"]),
        ("El inversor ausente pierde plata", lambda r: r["Inversor ausente"]["util"] < 0),
        ("Cada integrante de la familia se lleva menos que el propietario solo",
         lambda r: r["Familiar sin sueldos"]["por_persona"] < r["Propietario que cocina"]["por_persona"]),
        ("La familia recibe menos de lo que valdría su trabajo a precio de mercado",
         lambda r: r["Familiar sin sueldos"]["ingreso"] < r["Familiar sin sueldos"]["valor_trabajo"]),
        ("El propietario que cocina se lleva más de lo que valdría su trabajo",
         lambda r: r["Propietario que cocina"]["ingreso"] > r["Propietario que cocina"]["valor_trabajo"]),
        ("La familia cobra por hora menos que el sueldo mínimo",
         lambda r: r["Familiar sin sueldos"]["por_persona"] / HORAS_MES < rmv_hora),
        ("Abrir de noche mejora al local de día y noche",
         lambda r: r["Día y noche"]["util"] > r["Día y noche"]["sin_noche"]),
        ("El exitoso es el que más gana",
         lambda r: max((k for k in r if not k.startswith("_")), key=lambda k: r[k]["ingreso"]).startswith("Exitoso")),
        ("El puesto de mercado gana por su plato más que por su volumen",
         lambda r: r["_puesto"]["insumos"] > r["_puesto"]["local"]),
        ("La fonda en casa propia se lleva menos que el propietario con local alquilado",
         lambda r: r["Fonda en casa propia"]["ingreso"] < r["Propietario que cocina"]["ingreso"]),
    ]
    if candela:
        pruebas += [
            ("Candela pierde si paga IGV sobre toda la venta (sin contar el sueldo del dueño)",
             lambda r: r["Candela (datos del POS)"]["util"] + 1500 < 0),
            ("Candela cubre sus costos sin IGV (sin contar el sueldo del dueño)",
             lambda r: r["Candela (datos del POS)"]["sin_igv"] >= 0),
        ]
    hallazgos = [{"hallazgo": texto, "parte": sum(1 for r in sorteos if f(r)) / n} for texto, f in pruebas]

    # Lugar de cada negocio por lo que se lleva la casa, en cada sorteo
    nombres = list(casos)
    lugares: dict[str, list[int]] = {k: [] for k in nombres}
    for r in sorteos:
        orden = sorted(nombres, key=lambda k: -r[k]["ingreso"])
        for i, k in enumerate(orden, start=1):
            lugares[k].append(i)
    hoy = sorted(nombres, key=lambda k: -medir(casos[k])["ingreso"])

    def cuantil(xs: list[int], q: float) -> int:
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(q * len(xs)))]

    orden = [{"nombre": k, "hoy": hoy.index(k) + 1, "p05": cuantil(lugares[k], 0.05), "p95": cuantil(lugares[k], 0.95),
              "mismo": sum(1 for x in lugares[k] if x == hoy.index(k) + 1) / n,
              "gana": sum(1 for r in sorteos if r[k]["ingreso"] > 0) / n} for k in hoy]
    return {"n": n, "rangos": RANGOS, "hallazgos": hallazgos, "orden": orden}


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
    variantes: list = []
    guardados = _api("/escenarios")
    if guardados:
        g = next((x for x in guardados if x["nombre"] == "Candela (datos del POS)"), None)
        if g:
            candela = caso(g["nombre"], g["datos"])
            variantes = [caso(x["nombre"], x["datos"]) for x in guardados
                         if x["nombre"].startswith("Candela") and x["nombre"] != g["nombre"]]
            platos = _api("/platos/analisis?igv=10.5&formal=true")
    mezcla = mezcla_desde_analisis(platos) if platos else None
    robustez = [corridas(a["nombre"], a["datos"], elasticidad=ELASTICIDAD_JULIACA) for a in arquetipos]
    # el mismo barrido con la clientela poco sensible que se suponía antes de medirla
    robustez_supuesta = [corridas(a["nombre"], a["datos"], con_estres=False) for a in arquetipos]
    if candela:
        robustez.append(corridas(g["nombre"], g["datos"], mezcla))
    datos = {
        "hallazgos": hallazgos(arquetipos, g["datos"] if candela else None),
        "igualdad": igualdad(arquetipos, g["datos"] if candela else None),
        "trabajo": trabajo(arquetipos, g["datos"] if candela else None),
        "capacidad": capacidades(arquetipos, g["datos"] if candela else None),
        "mismos_precios": mismos_precios(arquetipos, g["datos"] if candela else None),
        "estados": estados_anuales(arquetipos, g["datos"] if candela else None),
        "entradas": entradas(arquetipos, g["datos"] if candela else None),
        "parametros": parametros(),
        "organizacion": organizacion(arquetipos, g["datos"] if candela else None),
        "cocina": cocina(candela["q"] if candela else None, g["datos"] if candela else None),
        "supuestos_robustez": robustez_supuestos(arquetipos, g["datos"] if candela else None),
        "ciudades": ciudades(), "casos": casos, "candela": candela, "candela_variantes": variantes, "platos": platos, "robustez": robustez, "robustez_supuesta": robustez_supuesta,
        "nacional": {k: v for k, v in NAC.items() if k != "notas"}, "riesgo": {k: v for k, v in RIESGO.items() if k != "notas"},
        "fuentes": DATA["fuentes"], "regimenes": list(REGIMENES),
    }
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return datos


if __name__ == "__main__":
    d = generar()
    print(len(d["casos"]), "casos;", "con Candela" if d["candela"] else "sin Candela")
