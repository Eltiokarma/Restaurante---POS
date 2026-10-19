"""Arma el ensayo en LaTeX con los números de salida/datos.json y lo compila
con XeLaTeX. Todos los números del texto salen del motor: si cambian los
datos, el ensayo cambia con ellos.

Uso (desde estudio/):
    ESTUDIO_URL=... ESTUDIO_TOKEN=... python -m reporte.ensayo
"""
from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from . import datos as mod_datos
from . import figuras

SALIDA = Path(__file__).resolve().parent / "salida"
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


# ---------------------------------------------------------------- formato

def n(v: float, dec: int = 0) -> str:
    """Número con separador de miles fino (estilo libro)."""
    txt = f"{abs(v):,.{dec}f}".replace(",", "\\,")
    return ("$-$" if v < 0 else "") + txt


def s(v: float, dec: int = 0) -> str:
    return "S/~" + n(v, dec) if v >= 0 else "$-$S/~" + n(-v, dec)


def p(v: float | None, dec: int = 0) -> str:
    return "---" if v is None else f"{n(v * 100, dec)}\\,\\%"


def esc(t: str) -> str:
    for a, b in (("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"),
                 ("_", "\\_"), ("{", "\\{"), ("}", "\\}"), ("~", "\\textasciitilde{}"), ("^", "\\^{}")):
        t = t.replace(a, b)
    return t


def anios(v: float | None) -> str:
    if v is None:
        return "no recupera"
    return f"{n(v * 12)} meses" if v < 1 else f"{n(v, 1)} años"


def corto(nombre: str) -> str:
    return figuras.corto(nombre)


PORCION = {"economica": "porción económica", "estandar": "porción estándar", "generosa": "porción generosa"}


def combinaciones(r: dict) -> int:
    """Precios × porciones × mezclas × turnos × elasticidades del barrido."""
    precios = len(next(iter(r["curvas"].values()), []))
    return precios * 3 * (3 if r.get("mezcla") else 1) * 2 * len(r["curvas"])


def describir_decision(dd: dict) -> str:
    partes = [f"menú a S/ {dd['precio']:.2f}", PORCION[dd["calidad"]]]
    if dd.get("mezcla") is not None:
        partes.append(f"{round(dd['mezcla'] * 100)} % de segundos de res")
    partes.append("abriendo de noche" if dd["noche"] else "solo de día")
    return ", ".join(partes)


# ---------------------------------------------------------------- piezas

# Los negocios se presentan siempre en el mismo orden, agrupados por quién pone el trabajo
GRUPOS_NEGOCIO = [('La casa pone el trabajo', ['Propietario que cocina', 'Familiar sin sueldos', 'Fonda en casa propia', 'Puesto de mercado informal', 'Pequeño en Nuevo RUS']), ('El capital contrata', ['Inversor que supervisa', 'Día y noche', 'Ejecutivo en el centro', 'Inversor ausente']), ('Referencia', ['Exitoso (referencia compuesta)']), ('Caso real', ['Candela (datos del POS)'])]
ORDEN_NEGOCIO = [nm for _, nms in GRUPOS_NEGOCIO for nm in nms]
GRUPO_DE = {nm: g for g, nms in GRUPOS_NEGOCIO for nm in nms}


def en_orden(items, nombre=lambda x: x["nombre"]):
    return sorted(items, key=lambda x: ORDEN_NEGOCIO.index(nombre(x)) if nombre(x) in ORDEN_NEGOCIO else 99)


def con_grupos(pares, ncols: int) -> str:
    """Filas de una tabla de negocios con un subtítulo por grupo. `pares`:
    (nombre del negocio, fila en LaTeX), ya en orden."""
    salida, ultimo = [], None
    for nombre, fila in pares:
        g = GRUPO_DE.get(nombre, "")
        if g != ultimo:
            salida.append(r"\rowcolor{white}\multicolumn{" + str(ncols) + r"}{@{}l}{\textit{\color{acento}" + g
                          + r"}} \\")
            ultimo = g
        salida.append(fila)
    return "\n".join(salida)


def tabla_casos(cs: list[dict]) -> str:
    filas = []
    for c in en_orden(cs):
        filas.append((c["nombre"], " & ".join([
            esc(corto(c["nombre"])), s(c["precio"], 2 if c["precio"] % 1 else 0),
            n(c["q"]) + ("+n" if c["noche"] else ""), str(c["trabajadores"]), "sí" if c["formal"] else "no",
            s(c["ingreso_dueno"]), str(c["equilibrio"] or "$>$600"), p(c["mc"]["prob_perdida"]),
            s(c["flujo"]["van"]), anios(c["flujo"]["recupero"]),
        ]) + r" \\"))
    return con_grupos(filas, 10)


def tabla_quiebres(cs: list[dict]) -> str:
    claves = ("precio", "q", "insumos", "sueldos", "alquiler_mes")
    filas = []
    for c in en_orden(cs):
        pierde = c["utilidad_mes"] < 0
        celdas = []
        for k in claves:
            x = c["quiebres"].get(k)
            if x is None:
                celdas.append("\\textcolor{perdida}{no alcanza}" if pierde else "sobra")
            elif pierde:
                celdas.append(f"\\textcolor{{perdida}}{{falta {p(abs(x))}}}")
            else:
                celdas.append(("$\\downarrow$\\," if x < 0 else "$\\uparrow$\\,") + p(abs(x)))
        filas.append((c["nombre"], esc(corto(c["nombre"])) + " & " + " & ".join(celdas) + r" \\"))
    return con_grupos(filas, 6)


def tabla_ciudades(cs: list[dict]) -> str:
    return "\n".join(
        f"{esc(c['nombre'].replace(' Metropolitana', ''))} & {s(c['precio'], 1 if c['precio'] % 1 else 0)} & "
        f"{ {'observado': 'observado', 'local': 'un local'}.get(c['precio_fuente'], 'estimado')} & {c['eq_2026']} & {c['eq_2027']} & "
        f"{c['eq_2028']} & {c['eq_con_sueldo']} & {c['eq_informal']} \\\\"
        for c in cs)


def fuentes(fs: list[dict]) -> str:
    return "\n".join(f"\\item {esc(f['tema'])}. \\url{{{f['url']}}}" for f in fs)


# ---------------------------------------------------------------- documento

def construir(d: dict) -> str:
    casos = {c["nombre"]: c for c in d["casos"]}
    dc, fam, inv, aus = (casos["Propietario que cocina"], casos["Familiar sin sueldos"], casos["Inversor que supervisa"],
                         casos["Inversor ausente"])
    mer, rus, eje, dyn, exi = (casos["Puesto de mercado informal"], casos["Pequeño en Nuevo RUS"],
                               casos["Ejecutivo en el centro"], casos["Día y noche"],
                               casos["Exitoso (referencia compuesta)"])
    cand, pl = d.get("candela"), d.get("platos")
    todos = d["casos"] + ([cand] if cand else [])
    orden = sorted(todos, key=lambda c: -c["ingreso_dueno"])
    ciud = {c["id"]: c for c in d["ciudades"]}
    hoy = date.today()
    fecha = f"{MESES[hoy.month - 1]} de {hoy.year}"

    PALABRAS = {9: "nueve", 10: "diez", 11: "once", 12: "doce"}
    NN = PALABRAS.get(len(todos), str(len(todos)))
    NT = PALABRAS.get(len(d["casos"]), str(len(d["casos"])))
    rob = {r["nombre"]: r for r in d.get("robustez", [])}
    rc = next((r for r in d.get("robustez", []) if r["nombre"].startswith("Candela")), None)
    r_inv, r_dc = rob["Inversor que supervisa"], rob["Propietario que cocina"]
    sobreviven = [corto(r["nombre"]) for r in d.get("robustez", []) if r["estres"][-1]["utilidad"] >= 0]
    al_tope = sum(1 for r in d.get("robustez", []) if r["mejor"]["precio"] >= r["precio0"] + 3 - 1e-9)
    # Experimento: el mismo barrido con la sensibilidad supuesta y con la medida en Juliaca
    tipo = [r for r in d.get("robustez", []) if not r["nombre"].startswith("Candela")]
    sup_ = d.get("robustez_supuesta", [])
    sube_sup = [r["mejor"]["precio"] - r["precio0"] for r in sup_]
    sube_med = [r["mejor"]["precio"] - r["precio0"] for r in tipo]
    al_tope_sup = sum(1 for x in sube_sup if x >= 3 - 1e-9)
    quietos_med = sum(1 for x in sube_med if abs(x) < 1e-9)
    max_sube_med = max(sube_med) if sube_med else 0
    el_med = ", ".join(n(x, 1) for x in (tipo[0]["elasticidad"] if tipo else []))

    hz = d.get("hallazgos", {})
    nr = hz.get("nrus", {})
    pc = hz.get("precio_candela")
    hora = {h["nombre"]: h for h in hz.get("hora", [])}
    medio = sorted(hz.get("medio_sol", []), key=lambda x: x["menus"])
    noche_u = {x["nombre"]: x for x in hz.get("noche", [])}
    ig = {f["nombre"]: f for f in d.get("igualdad", {}).get("filas", [])}

    def ig_(nombre, cual="igual", campo="ingreso"):
        return ig[nombre][cual][campo]

    pasos_aus = d.get("igualdad", {}).get("ausencia")
    dcp = d.get("igualdad", {}).get("descomposicion")
    fac = {f["nombre"]: f for f in (dcp or {}).get("filas", [])}
    u_dc, u_fam = (noche_u.get(n, {}).get("umbral") for n in ("Propietario que cocina", "Familiar sin sueldos"))
    umbral_familiar = f"unos {u_dc}" if u_dc == u_fam else f"{u_dc} o {u_fam}"

    def ap(nombre, clave):
        return fac[nombre]["aportes"][clave]

    def tabla_factores():
        filas = en_orden([f for f in dcp["filas"] if f["nombre"] != dcp["referencia"]])
        celda = lambda v: "" if abs(v) < 1 else s(v)  # noqa: E731
        lineas = [f"{esc(corto(dcp['referencia']))} (referencia) & & & & & & {s(dcp['base'])} \\\\ \\midrule"]
        lineas.append(con_grupos([(f["nombre"], f"{esc(corto(f['nombre']))} & "
                                   + " & ".join(celda(f['aportes'][c]) for c, _ in dcp['grupos'])
                                   + f" & {s(f['propio'])} \\\\") for f in filas], 7))
        return "\n".join(lineas)

    formales = [f for f in (dcp or {}).get("filas", []) if abs(f["aportes"]["formalidad"]) >= 1]

    sr = d.get("supuestos_robustez")

    def veredicto(parte):
        parte = round(parte, 2)  # el mismo número que se muestra en la tabla
        return "se sostiene" if parte >= 0.9 else ("probable" if parte >= 0.7 else "no concluyente")

    def tabla_supuestos():
        return "\n".join(f"{esc(h['hallazgo'])} & {p(h['parte'])} & {veredicto(h['parte'])} \\\\"
                         for h in sorted(sr["hallazgos"], key=lambda h: -h["parte"]))

    def tabla_lugares():
        return "\n".join(f"{esc(corto(o['nombre']))} & {o['hoy']} & "
                         f"{o['p05'] if o['p05'] == o['p95'] else str(o['p05']) + '--' + str(o['p95'])} & "
                         f"{p(o['mismo'])} & {p(o['gana'])} \\\\" for o in sr["orden"])

    def parte_de(inicio):
        h = next((h for h in (sr or {}).get("hallazgos", []) if h["hallazgo"].startswith(inicio)), None)
        return h["parte"] if h else None

    def sorteos_txt(inicio):
        x = parte_de(inicio)
        return "" if x is None else f" ({veredicto(x)} en el {p(x)} de los sorteos)"

    def tabla_experimentos():
        filas = []
        if ig:
            filas.append((
                "¿Decide quién trabaja?", "Todos los negocios en el mismo local",
                f"Familia {s(ig_('Familiar sin sueldos'))} (para tres), propietario {s(ig_('Propietario que cocina'))}, inversor "
                f"{s(ig_('Inversor que supervisa'))}, ausente {s(ig_('Inversor ausente'))}",
                veredicto(parte_de("El propietario que cocina se lleva más que el inversor")) if sr else "--"))
        if fac:
            filas.append((
                "¿El exitoso y el puesto ganan por cómo se organizan?", "La diferencia repartida en cinco factores",
                f"Exitoso: local y venta {s(ap('Exitoso (referencia compuesta)', 'local'))}. Puesto: plato "
                f"{s(ap('Puesto de mercado informal', 'insumos'))}, volumen {s(ap('Puesto de mercado informal', 'local'))}",
                "no: escala y plato barato"))
        if pasos_aus:
            filas.append((
                "¿Cuánto cuesta no estar?", "Del inversor al inversor ausente, un cambio a la vez",
                f"{s(-(pasos_aus[2]['cambio'] + pasos_aus[3]['cambio'] + pasos_aus[4]['cambio']))} al mes; la gerencia "
                f"pagada, {s(-pasos_aus[2]['cambio'])}",
                veredicto(parte_de("El inversor ausente pierde")) if sr else "--"))
        if sup_:
            filas.append((
                "¿Conviene subir el precio?", "Barrido con la sensibilidad supuesta y con la medida en Juliaca",
                f"Supuesta: {al_tope_sup} de {len(sup_)} suben S/~3. Medida: {quietos_med} de {len(tipo)} no lo mueven",
                "no, con la medida"))
        if "juliaca_obs" in ciud:
            filas.append((
                "¿Es Juliaca la plaza más difícil?", "Precio observado (S/~11) en vez del estimado (S/~8)",
                f"Equilibrio de {ciud['juliaca']['eq_2026']} a {ciud['juliaca_obs']['eq_2026']} menús diarios",
                "no; dependía del supuesto"))
        if pc:
            filas.append((
                "¿Qué dejó a Candela subir de S/~10 a S/~11?", "Sus tres precios de la historia",
                f"Sensibilidad {n(pc['elasticidad_ajuste'], 1)}; S/~10 con {n(pc['q0'])} menús deja "
                f"{s(abs(pc['a_10'] - cand['utilidad_mes']))} {'más' if pc['a_10'] > cand['utilidad_mes'] else 'menos'} al mes",
                "casi neutro; sacó a la cocina del colapso"))
        if rc and rc.get("capacidad"):
            filas.append((
                "¿Bajar el precio llena el local?", f"Techo de cocina de {n(rc['capacidad'])} menús",
                f"La venta no pasa de {n(rc['capacidad'])}; a S/~10 la cocina vuelve al colapso",
                "la organización pone el techo"))
        if mp:
            filas.append((
                "¿Quién necesita menos para no perder?", "Todos a los mismos precios (S/~7 a S/~18)",
                f"A S/~10: familia {eq_('Familiar sin sueldos', 10)}, propietario {eq_('Propietario que cocina', 10)}, inversor "
                f"{eq_('Inversor que supervisa', 10)}, ausente {eq_('Inversor ausente', 10)} menús; a S/~7 ningún negocio con planilla "
                "contratada cubre costos", "ordena sin suponer clientela"))
        if mv:
            filas.append((
                "¿Quién gana con la misma venta?", "Todos con los mismos menús al día (40 a 140), cada uno a su precio",
                f"A 60: familia {s(vcasa_('Familiar sin sueldos', 60))}, inversor {s(vcasa_('Inversor que supervisa', 60))}; "
                f"el puesto gana desde {volumen_cubre('Puesto de mercado informal')} y el ausente desde "
                f"{volumen_cubre('Inversor ausente') or 'más de 140'} menús", "ordena sin suponer precio"))
        filas.append((
            "¿Casa propia o local alquilado?", "Fonda en casa propia frente al propietario con local",
            f"{s(casos['Fonda en casa propia']['ingreso_dueno'])} contra {s(dc['ingreso_dueno'])} al mes",
            veredicto(parte_de("La fonda en casa propia")) if sr else "--"))
        if trab:
            filas.append((
                "¿Es rentable la fonda familiar si se paga su trabajo?",
                "Su trabajo y su capital a precio de mercado",
                f"Utilidad económica {s(trab['Familiar sin sueldos']['utilidad_economica'])}; cobran el "
                f"{p(trab['Familiar sin sueldos']['parte_cobrada'])} de lo que vale su trabajo",
                veredicto(parte_de("La familia recibe menos")) if parte_de("La familia recibe menos") is not None else "--"))
        if capac:
            faltos = [c for c in capac.values() if c["costo_falta"] > 0]
            cnd = capac.get("Candela (datos del POS)")
            filas.append((
                "¿Alcanza la gente para lo que se vende?", "Productividad de Candela: unos 33 menús por persona en cocina, 50 por mozo",
                f"A {len(faltos)} de {len(capac)} les falta gente"
                + ("" if not cnd else f"; Candela tiene sitio para {n(cnd['holgura'])} menús más ({s(cnd['valor_holgura'])} al mes)"),
                "su cuello es la demanda, no la cocina" if cnd else "--"))
        if co:
            filas.append((
                "¿Rinde más una cocina organizada?", "La misma cocina en doméstico, por bloques, mise en place y estaciones",
                f"Con 3 personas aguanta {n(cap_('domestico', 3)['tope'])}, {n(cap_('bloques', 3)['tope'])}, "
                f"{n(cap_('mise', 3)['tope'])} y {n(cap_('estaciones', 3)['tope'])} menús"
                + ("" if not org_c else f"; Candela podría trabajar con una persona menos y ahorrar {s(org_c['modos'][mejor_c]['ahorro'])} al mes"),
                "sí; el orden se mantiene con gente lenta o rápida"))
        filas.append((
            "¿Conviene abrir de noche?", "Barrido con una noche tipo de 30 platos",
            "Mejora a todos los negocios", "sí, si existe esa demanda (no medida)"))
        if sr and parte_de("Candela cubre") is not None:
            filas.append((
                "¿Cubre Candela sus costos sin IGV?", f"{n(sr['n'])} sorteos de sus números",
                f"Sí en el {p(parte_de('Candela cubre'))} de los sorteos", veredicto(parte_de("Candela cubre"))))
        filas.append((
            "¿Quién resiste un año malo?", "Seis golpes a la vez",
            f"{len(sobreviven)} de {NN}: {lista_neg(sobreviven)}", "--"))
        # las celdas ya vienen en LaTeX (cifras con s(), p() y n()): no se escapan
        return "\n".join(f"{k} & {a} & {b} & {c} & {v} \\\\ \\addlinespace[2pt]"
                         for k, (a, b, c, v) in enumerate(filas, start=1))

    trab = {t["nombre"]: t for t in d.get("trabajo", [])}
    capac = {c["nombre"]: c for c in d.get("capacidad", [])}
    co = d.get("cocina")
    pr = d.get("parametros", {})
    ent = d.get("entradas", [])

    def cuadro(titulo, etiqueta, filas):
        """Cuadro de supuestos de un análisis: variable, valor y de dónde sale.
        Los valores ya vienen en LaTeX (s(), p(), n())."""
        cuerpo = "\n".join(f"{esc(v)} & {x} & {t} \\\\" for v, x, t in filas)
        return rf"""\begin{{table}}[H]
\centering\footnotesize
\caption{{{titulo}}}\label{{{etiqueta}}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}p{{0.3\textwidth}}>{{\raggedright\arraybackslash}}Xl}}
\toprule
Variable & Valor & Origen \\
\midrule
{cuerpo}
\bottomrule
\end{{tabularx}}
\end{{table}}
"""

    def lista_n(xs, dec=1):
        return ", ".join(n(x, dec) for x in xs)

    _nch = next((e["noche"] for e in ent if e["noche"]), None)
    noche_txt = "" if not _nch else f"{n(_nch['q'])} platos a {s(_nch['precio'])}"

    def tabla_entradas():
        filas = []
        for e in en_orden(ent):
            gente = f"{e['cocina']} + {e['salon']}" + (f" + {e['otros']}" if e["otros"] else "")
            formal = ("IGV, pl." if e["formal"] and e["laboral"] else "IGV" if e["formal"]
                      else "pl." if e["laboral"] else "no")
            filas.append((e["nombre"],
                f"{esc(corto(e['nombre']))} & {s(e['precio'])} & {n(e['q'])} & {s(e['alquiler'])} & {s(e['insumos'], 2)} & "
                f"{s(e['gas_luz'])} & {gente}{'' if e['planilla_propia'] else '*'} & {s(e['personal_mes'])} & "
                f"{'sí' if e['sueldo_dueno'] else 'no'} & {formal} & {s(e['inversion'])} \\\\"))
        return con_grupos(filas, 11)

    CAMPO_TXT = {"ciudad_id": "ciudad", "zona_id": "zona", "precio": "precio", "q": "menús al día", "dias": "días",
                 "alquiler_mes": "alquiler", "balones": "gas", "gas_balon45": "precio del gas",
                 "servicios_mes": "luz y agua", "insumos": "costo por menú", "segmento": "segmento",
                 "planilla": "planilla", "sueldo_dueno": "sueldo del dueño", "sueldo_cocinero": "sueldo de cocinero",
                 "sueldo_ayudante": "de ayudante", "sueldo_mozo": "de mozo", "formal": "IGV",
                 "laboral_formal": "cargas laborales", "noche": "turno noche completo"}

    def sup_ciudades():
        return cuadro("Supuestos del mapa de ciudades.", "tab:sup_ciudades", [
            ("Local", "menú popular, formal (IGV y cargas laborales)", "método"),
            ("Precio", "el de la pizarra de cada ciudad", "observado (Lima, Cusco, Puno) / estimado"),
            ("Insumos, alquiler y sueldos", "los de la base para cada ciudad", "ver anexo de fuentes"),
            ("Personal", "automático: cocinero, un ayudante cada 80 menús, un mozo cada 70", "supuesto"),
            ("Gas", "5 balones de 45~kg al mes", "supuesto"),
            ("Sueldo del dueño", r"no se cuenta (columna aparte con S/~1\,500)", "método"),
            ("Días de atención", "26 al mes", "supuesto"),
            ("IGV de restaurantes", r"10.5\,\% (2026), 15\,\% (2027), 18\,\% (2028)", "ley / supuesto 2028"),
        ])

    def sup_igualdad():
        b = pr["igualdad"]
        return cuadro("Supuestos de la comparación a igualdad de condiciones: el local común.", "tab:sup_igualdad", [
            ("Precio", s(b["precio"]), "el del propietario que cocina"),
            ("Menús al día", n(b["q"]), "ídem"),
            ("Alquiler", s(b["alquiler_mes"]), "ídem"),
            ("Insumos por menú", s(b["insumos"], 2), "ídem"),
            ("Gas y luz", f"{n(b['balones'])} balones al mes; {s(b['servicios_mes'])} de luz y agua", "ídem"),
            ("Lo que queda de cada uno", "quién trabaja y cuánto se le paga, sueldo del dueño, formalidad y noche",
             "cada negocio"),
        ])

    def sup_factores():
        filas = [(g["nombre"], ", ".join(CAMPO_TXT.get(c, c) for c in g["campos"]), "método") for g in pr["grupos"]]
        filas.append(("Reparto", "valor de Shapley: promedio sobre los 120 órdenes posibles", "método"))
        return cuadro("Supuestos de la descomposición: qué entra en cada factor.", "tab:sup_factores", filas)

    def sup_riesgo():
        r = pr["riesgo"]
        return cuadro("Supuestos de la simulación de riesgo.", "tab:sup_riesgo", [
            ("Años simulados", r"2\,000 por negocio", "método"),
            ("Clientela", f"lognormal, desvío de {p(r['sd_volumen'])}", "supuesto"),
            ("Costo de insumos", f"normal, desvío de {p(r['sd_insumos_anual'])} al año", "supuesto"),
            ("Precio", r"triangular en el rango de la ciudad ($\pm$4\,\% si es dato propio)", "supuesto"),
            ("Paros", "2 a 8 semanas sin venta, con la probabilidad anual de cada ciudad", "historial de paros"),
            ("Resto", "los números de cada negocio (cuadro~\\ref{tab:entradas})", "cada negocio"),
        ])

    def sup_sensibilidad():
        return cuadro("Supuestos del análisis de sensibilidad.", "tab:sup_sensibilidad", [
            ("Variables", "precio, menús al día, insumos, sueldos, alquiler, gas, luz y agua, días al mes", "método"),
            ("Cómo se mueven", "una a la vez; las demás quedan como están", "método"),
            ("Quiebre", "cuánto puede cambiar la variable hasta que la utilidad llega a cero", "método"),
            ("Tornado", r"cada variable $\pm$10\,\%", "método"),
            ("Matriz", r"precio de S/~2 menos a S/~2 más, en pasos de 50 céntimos; venta del 50 al 150\,\% de la actual",
             "método"),
        ])

    def sup_barrido():
        b = pr["barrido"]
        cal = b["calidad"]
        return cuadro("Supuestos del barrido de decisiones.", "tab:sup_barrido", [
            ("Precio", f"de {s(b['precio'][0])} a {s(b['precio'][-1])} sobre el actual, en pasos de 50 céntimos", "método"),
            ("Porción económica", f"insumos {p(cal['economica'][0] - 1)}, clientela {p(cal['economica'][1] - 1)}", "supuesto"),
            ("Porción generosa", f"insumos +{p(cal['generosa'][0] - 1)}, clientela +{p(cal['generosa'][1] - 1)}", "supuesto"),
            ("Sensibilidad al precio, medida", lista_n(b["elasticidad_medida"]), "medida en Candela ± margen"),
            ("Sensibilidad al precio, supuesta", lista_n(b["elasticidad_supuesta"]), "supuesto inicial"),
            ("Noche tipo", f"{n(b['noche']['q'])} platos a {s(b['noche']['precio'])}, insumos {s(b['noche']['insumos'], 2)}, "
                           f"{n(b['noche']['balones'])} balones y {s(b['noche']['servicios'])} de luz, equipo propio", "supuesto"),
            ("Techo de Candela", f"{n(rc['capacidad']) if rc and rc.get('capacidad') else 100} menús al día", "propio"),
            ("Años simulados", f"{n(b['n_mc'])} por combinación", "método"),
            ("Decisión robusta", "la que más deja con la sensibilidad más desfavorable", "método"),
        ])

    def sup_estres():
        return cuadro("Supuestos de la prueba de estrés: los golpes.", "tab:sup_estres",
                      [(g, "uno a la vez" if g != "Todo junto" else "los seis a la vez", "supuesto")
                       for g in pr["golpes"]])

    def sup_sorteos():
        r = pr["rangos"]
        return cuadro("Supuestos de los sorteos: cuánto puede equivocarse cada número.", "tab:sup_sorteos", [
            ("Sorteos", f"{n(pr['n_sorteos'])} por negocio, cada número uniforme en su rango", "método"),
            ("Precio", f"$\\pm${p(r['precio'], 0)}", "supuesto"),
            ("Menús al día", f"$\\pm${p(r['q'], 0)}", "supuesto"),
            ("Insumos por menú", f"$\\pm${p(r['insumos'], 0)}", "supuesto"),
            ("Alquiler", f"$\\pm${p(r['alquiler_mes'], 0)}", "supuesto"),
            ("Sueldos", f"$\\pm${p(r['sueldos'], 0)}, todos juntos; quien no cobra sigue sin cobrar", "supuesto"),
            ("Gas y luz", f"$\\pm${p(r['balones'], 0)}", "supuesto"),
            ("Veredicto", r"se sostiene ($\geq$90\,\% de los sorteos), probable (70--90\,\%), no concluyente", "método"),
        ])

    def sup_trabajo():
        j, t = pr["juliaca"], pr["trabajo"]
        return cuadro("Supuestos del valor del trabajo de la casa.", "tab:sup_trabajo", [
            ("Sueldo de mercado", f"cocinero {s(j['sueldo_cocinero'])}, ayudante {s(j['sueldo_ayudante'])}, mozo "
                                  f"{s(j['sueldo_mozo'])}, administrador {s(t['administrador'])} al mes", "base de Juliaca / supuesto"),
            ("Jornada", f"{n(t['jornada'])} horas a la semana; las extra, con {p(t['recargo'])} de recargo", "ley"),
            ("Horas de la casa", "60 a la semana quien cocina o atiende; 20 a 60 quien administra (cuadro~\\ref{tab:trabajo})",
             "supuesto"),
            ("Costo del capital", f"{p(t['tasa'])} al año sobre la inversión", "supuesto (tasa del flujo)"),
        ])

    def sup_capacidad():
        c = pr["capacidad"]
        return cuadro("Supuestos del experimento de capacidad.", "tab:sup_capacidad", [
            ("Menús por persona en cocina", n(c["por_cocina"]), r"propio: 3 aguantan $\sim$100"),
            ("Menús por mozo", n(c["por_mozo"]), r"propio: 2 aguantan $\sim$100, sobreexigidos"),
            ("Quién cuenta", "la planilla de día por área, más la gente de la casa que cocina o atiende", "método"),
            ("Costo de quien falta", "sueldo de ayudante o de mozo (más 5\\,\\% si la planilla es formal)", "supuesto"),
            ("Valor de la holgura", "utilidad del modelo vendiendo hasta el tope con la misma planilla", "método"),
        ])

    def sup_candela():
        e = next((x for x in ent if x["nombre"].startswith("Candela")), None)
        if not e:
            return ""
        return cuadro("Los números de Candela.", "tab:sup_candela", [
            ("Precio y venta", f"{s(e['precio'])}; {n(e['q'])} menús al día, {n(e['dias'])} días", "propio (POS y dueño)"),
            ("Insumos por menú", s(e["insumos"], 2), "propio (recetas y notas de compra)"),
            ("Alquiler", f"{s(e['alquiler'])} (el de mercado sería S/~3\\,000)", "propio"),
            ("Planilla", f"{e['cocina']} en cocina y {e['salon']} mozos a medio tiempo: {s(e['personal_mes'])} al mes", "propio"),
            ("Gas, luz y agua", s(e["gas_luz"]), "propio"),
            ("Sueldo del dueño", r"S/~1\,500 cuando se cuenta", "supuesto"),
            ("IGV", r"sobre toda la venta (peor caso); emite boleta solo cuando se la piden", "propio / supuesto"),
            ("Inversión", s(e["inversion"]), "propio"),
        ])

    def sup_deja_ver():
        return cuadro("Supuestos de los cálculos de esta sección.", "tab:sup_deja_ver", [
            ("Tope del Nuevo RUS", s(pr["tope_nrus"]) + " de ventas al año; cuota de S/~20 o S/~50 al mes", "ley"),
            ("Noche con la misma gente", "precio S/~1 más que el día, insumos 5\\,\\% más, sin equipo nuevo", "supuesto"),
            ("Casa propia", "alquiler cero; la venta y el precio, los de la fonda del catálogo", "supuesto"),
        ])

    def hhmm(m):
        m = int(round(m))
        return f"{m // 60}:{m % 60:02d}"

    def cola_(modo, n_):
        return next(c for c in co["colas"] if c["modo"] == modo and c["personas"] == n_)

    def cap_(modo, n_):
        return next(c for c in co["capacidad"] if c["modo"] == modo and c["personas"] == n_)

    gd = gm3 = gb = None
    punta = 0
    if co:
        gd = next(g for g in co["gantt"] if g["modo"] == "domestico")
        gm3 = next(g for g in co["gantt"] if g["modo"] == "mise" and g["personas"] == 3)
        gb = next(g for g in co["gantt"] if g["modo"] == "bloques")
        perf = co["perfil"]
        punta = sum(v for h, v in perf.items() if "12:45" <= h <= "13:30") / sum(perf.values())

    NOMBRE_ORG = {"domestico": "Doméstica", "bloques": "Por bloques", "mise": "Mise en place",
                  "estaciones": "Por estaciones"}

    def tabla_prep():
        filas = []
        for t in co["tareas"]:
            if "partes" not in t:
                continue
            for i, x in enumerate(t["partes"]):
                nombre = esc(t["nombre"]) if i == 0 else ""
                antes = ("sí" if t.get("anticipable") else "no") if i == 0 else ""
                filas.append(f"{nombre} & {esc(x['insumo'])} & {n(x['cantidad'], 1)} {esc(x['unidad'])} & "
                             f"{n(x['min_por'], 1)} & {n(x['cantidad'] * x['min_por'])} & {antes} & "
                             f"{esc(x['fuente_velocidad'])} \\\\")
            filas.append(r"\addlinespace[1pt]")
        return "\n".join(filas)

    def tabla_coccion():
        filas = []
        for t in co["tareas"]:
            if "partes" in t:
                continue
            filas.append(f"{esc(t['nombre'])} & {esc(co['estaciones'][t['estacion']])} & {n(t['fijo'] + t['var'])} & "
                         f"{t.get('espera') or '--'} \\\\")
        return "\n".join(filas)

    def tabla_servicio():
        sv, h = co["servicio"], co["horarios"]
        dq = sv["desorden_queda"]
        filas = [(f"{x['nombre']} (por menú)", f"{n(x['min'], 2)} min (estimación)") for x in sv["puestos"].values()]
        filas += [
            ("Desorden por menú, cocina doméstica", f"{n(co['desorden'], 2)} min (calibrado: {sv['calibracion']['personas']} personas aguantan {sv['calibracion']['menus']} menús)"),
            ("Desorden que queda", f"por bloques {p(dq['bloques'])}, mise en place {p(dq['mise'])}, estaciones {p(dq['estaciones'])} (supuesto)"),
            ("Espera máxima tolerable", f"{sv['espera_maxima']} min en la hora punta (supuesto)"),
            ("Llegada de pedidos", f"por cuarto de hora, medida en el POS de Candela; el {p(punta)} entre 12:45 y 13:45"),
            ("Horarios", f"almuerzo {h['almuerzo']}--{h['servicio_fin']}; la tarde de mise en place va desde las {h['tarde_inicio']} hasta las {h['tarde_fin']} como máximo, y lo que no alcanza pasa a la mañana"),
            ("Cambio de puesto", f"{h['cambio_estacion']} min cada vez (supuesto)"),
            ("Menús del día", f"{n(co['q'])}, la venta actual de Candela"),
        ]
        return "\n".join(f"{esc(a)} & {b} \\\\" for a, b in filas)

    def tabla_org():
        filas = []
        for m in NOMBRE_ORG:
            celdas = " & ".join(f"{n(cap_(m, k)['tope'])} ({cap_(m, k)['limita'][:3]}.)" for k in (2, 3, 4))
            filas.append(f"{NOMBRE_ORG[m]} & {celdas} & {n(cap_(m, 3)['horas_persona'], 1)} \\\\")
        return "\n".join(filas)

    orgs = d.get("organizacion", [])

    def tabla_org_negocios():
        filas = []
        for f in en_orden(orgs):
            md = f["modos"]
            nec = " & ".join(str(md[m]["necesita"] or "--") for m in NOMBRE_ORG)
            mejor = max((md[m]["ahorro"] or 0 for m in NOMBRE_ORG), default=0)
            filas.append((f["nombre"], f"{esc(corto(f['nombre']))} & {n(f['q'])} & {f['cocina']} & {nec} & "
                         f"{s(mejor) if mejor > 0 else '--'} & {n(md['domestico']['tope'])} & {n(md['mise']['tope'])} \\\\"))
        return con_grupos(filas, 10)

    ahorros_pos = [max(f["modos"][m]["ahorro"] or 0 for m in NOMBRE_ORG) for f in orgs]
    ahorros_pos = [x for x in ahorros_pos if x > 0] or [0]
    org_c = next((f for f in orgs if f["nombre"].startswith("Candela")), None)
    mejor_c = None if not org_c else max(NOMBRE_ORG, key=lambda m: org_c["modos"][m]["ahorro"] or -1e9)

    def vel_(f, clave, m):
        return next(v for v in co["velocidad"] if abs(v["factor"] - f) < 1e-9)[clave][m]

    def tabla_capacidad():
        filas = []
        for c in en_orden(list(capac.values())):
            falta = " + ".join(x for x in (f"{c['falta_cocina']} cocina" if c["falta_cocina"] else "",
                                           f"{c['falta_salon']} salón" if c["falta_salon"] else "") if x) or "--"
            filas.append((c["nombre"], f"{esc(corto(c['nombre']))} & {n(c['q'])} & {c['cocina']} + {c['salon']} & {n(c['tope'])} "
                         f"({c['limita']}) & {falta} & {s(c['utilidad'])} & {s(c['utilidad_ajustada'])} \\\\"))
        return con_grupos(filas, 7)

    estados = en_orden(d.get("estados", []))

    def estado_tabla(e):
        net = e["netas"] or 1
        filas = [("Ventas (lo que entra a caja)", e["ventas"], False), ("IGV", -e["igv"], False),
                 ("Ventas sin IGV", e["netas"], True), ("Insumos", -e["insumos"], False),
                 ("Margen de contribución", e["contribucion"], True), ("Planilla", -e["planilla"], False),
                 ("Sueldo del dueño", -e["dueno"], False), ("Alquiler", -e["alquiler"], False),
                 ("Gas", -e["gas"], False), ("Luz, agua y otros", -e["otros"], False),
                 ("Utilidad operativa", e["operativa"], True), ("Impuesto del régimen", -e["impuesto"], False),
                 ("Utilidad después de impuestos", e["neta"], True),
                 ("Para la casa (con sueldo del dueño)", e["casa"], True)]
        cuerpo = "\n".join((r"\textbf{" + esc(t) + "} & \\textbf{" + s(v) + "} & \\textbf{" + p(v / net) + "}" if negrita
                             else esc(t) + " & " + s(v) + " & " + p(v / net)) + r" \\"
                            for t, v, negrita in filas if not (t == "Sueldo del dueño" and v == 0))
        return (r"\begin{minipage}[t]{0.485\textwidth}\footnotesize" + "\n"
                + r"\textbf{" + esc(corto(e["nombre"])) + r"}\\[1pt]{\color{gris}\scriptsize " + f"{n(e['menus'])} menús al año a "
                + f"{s(e['precio'])}; {esc(e['regimen'])}" + r"}\par\vspace{2pt}" + "\n"
                + r"\begin{tabularx}{\linewidth}{@{}Xrr@{}}\toprule & Soles & \% \\\midrule" + "\n" + cuerpo + "\n"
                + r"\bottomrule\end{tabularx}\end{minipage}")

    def anexo_estados():
        bloques = []
        for i in range(0, len(estados), 2):
            par = estados[i:i + 2]
            bloques.append(r"\noindent " + r"\hfill ".join(estado_tabla(e) for e in par) + r"\par\vspace{10pt}")
        return "\n".join(bloques)

    mp = d.get("mismos_precios")

    def tabla_precios(clave):
        filas = []
        for f in en_orden(mp["filas"]):
            celdas = []
            for pr in mp["precios"]:
                v = f[clave][str(pr)]
                if clave == "equilibrio":
                    celdas.append("--" if v is None else (r"\textbf{" + str(v) + "}" if pr == f["precio"] else str(v)))
                else:
                    txt = s(v)
                    celdas.append((r"\textcolor{perdida}{" + txt + "}") if v < 0 else (r"\textbf{" + txt + "}" if pr == f["precio"] else txt))
            filas.append((f["nombre"], esc(corto(f["nombre"])) + " & " + s(f["precio"]) + " & " + " & ".join(celdas) + r" \\"))
        return con_grupos(filas, 2 + len(mp["precios"]))

    def eq_(nombre, pr):
        return next(f for f in mp["filas"] if f["nombre"] == nombre)["equilibrio"][str(pr)]

    def casa_(nombre, pr):
        return next(f for f in mp["filas"] if f["nombre"] == nombre)["casa"][str(pr)]

    def precio_cubre(nombre):
        f = next(f for f in mp["filas"] if f["nombre"] == nombre)
        return next((pr for pr in mp["precios"] if f["casa"][str(pr)] >= 0), None)

    mv = d.get("mismos_volumenes")

    def tabla_volumenes(clave):
        filas = []
        for f in en_orden(mv["filas"]):
            celdas = []
            for v in mv["volumenes"]:
                x = f[clave][str(v)]
                pasa = f["tope"] is not None and v > f["tope"] + 0.5
                if clave == "casa":
                    txt = s(x)
                    txt = (r"\textcolor{perdida}{" + txt + "}") if x < 0 else (r"\textbf{" + txt + "}" if v == f["q"] else txt)
                else:
                    txt = s(x, 2)
                    txt = (r"\textbf{" + txt + "}") if v == f["q"] else txt
                celdas.append(txt + (r"$^{\dagger}$" if pasa else ""))
            filas.append((f["nombre"], esc(corto(f["nombre"])) + " & " + n(f["q"]) + " & " + " & ".join(celdas) + r" \\"))
        return con_grupos(filas, 2 + len(mv["volumenes"]))

    def vcasa_(nombre, v):
        return next(f for f in mv["filas"] if f["nombre"] == nombre)["casa"][str(v)]

    def vpmin_(nombre, v):
        return next(f for f in mv["filas"] if f["nombre"] == nombre)["precio_minimo"][str(v)]

    def volumen_cubre(nombre):
        f = next(f for f in mv["filas"] if f["nombre"] == nombre)
        return next((v for v in mv["volumenes"] if f["casa"][str(v)] >= 0), None)

    def mapas_anexo():
        from reporte.figuras import archivo_matriz
        bloques = []
        for c in en_orden(d["casos"] + ([cand] if cand else [])):
            bloques.append(r"\begin{figure}[H]\centering" + "\n"
                           + r"\includegraphics[width=\textwidth]{fig/" + archivo_matriz(c["nombre"]) + ".pdf}" + "\n"
                           + r"\caption{" + esc(corto(c["nombre"])) + f": utilidad del mes (miles de soles) por precio y menús al día; hoy, {n(c['q'])} menús a {s(c['precio'])}." + "}"
                           + r"\label{fig:matriz_" + archivo_matriz(c["nombre"])[7:] + "}\n"
                           + r"\end{figure}")
        return "\n\n".join(bloques)

    def lista_neg(nombres):
        return y_lista([("la " if corto(x).startswith("Fonda") else "el ") + corto(x)[:1].lower() + corto(x)[1:]
                        for x in nombres])

    def y_lista(xs):
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]

    def tr_(nombre, campo):
        return trab[nombre][campo]

    def tabla_trabajo():
        filas = []
        for t in en_orden(list(trab.values())):
            horas = [c["horas_semana"] for c in t["casa"]]
            gente = ("nadie" if not horas else f"{len(horas)} × {n(horas[0])}~h" if len(set(horas)) == 1 and len(horas) > 1
                     else " + ".join(f"{n(h)}~h" for h in horas))
            cobra = ("--" if t["parte_cobrada"] is None else "nada" if t["parte_cobrada"] <= 0
                     else p(t["parte_cobrada"]))
            filas.append((t["nombre"], f"{esc(corto(t['nombre']))} & {gente} & {s(t['ingreso'])} & {s(t['valor_mercado'])} & "
                         f"{s(t['costo_capital'])} & {s(t['utilidad_economica'])} & {cobra} \\\\"))
        return con_grupos(filas, 7)

    def tabla_ausencia():
        return "\n".join(f"{esc(x['paso'])} & {s(x['utilidad'])} & {'' if x['cambio'] is None else s(x['cambio'])} \\\\"
                         for x in pasos_aus)

    def menus_medio(prefijo):
        return next(x["menus"] for x in medio if x["nombre"].startswith(prefijo))

    def golpe(r, clave):
        return next(g for g in r["estres"] if g["golpe"] == clave)["utilidad"]

    def reg(c, clave):
        return next(x for x in c["regimenes"] if x["regimen"] == clave)

    candela_resumen = ""
    candela_seccion = ""
    if cand and pl:
        par = pl["pareto"]
        top3 = ", ".join(f"{esc(x['insumo'].lower())} ({p(x['parte'])})" for x in par[:3])
        prec_neto = pl["menu"]["precio_promedio"] / 1.105
        candela_resumen = (
            f"\\item \\textbf{{Candela está en su punto de equilibrio antes de impuestos y su clientela es sensible "
            f"al precio.}} Si paga IGV sobre todo lo vendido, pierde {s(-cand['utilidad_mes'] - 1500)} al mes sin "
            f"contar el sueldo del dueño. Al subir de S/~10 a S/~11 perdió cerca de "
            f"{round(10 * (1 - pc['historia']['q1'] / pc['historia']['q0']))} clientes de cada 10, lo justo para que el "
            f"alza no ganara ni perdiera: la mejora tiene que venir del costo. Sin IGV, cubrir o no sus costos es una "
            f"moneda al aire"
            f"{'' if parte_de('Candela cubre') is None else ' (sale que sí en el ' + p(parte_de('Candela cubre')) + ' de los sorteos)'}.")
        candela_seccion = rf"""
\subsection{{El caso Candela}}\label{{sec:candela}}

\subsubsection{{Cuánto cuesta un menú}}

El sistema de ventas de Candela trae 112 insumos con su costo de referencia y recetas por porción para
51 platos, junto con lo que se vendió de cada uno en los últimos 60 días. Las recetas de partida venían de
una base genérica y sobrestimaban las cantidades: daban un menú de unos S/~7.5 en insumos, el 74\,\% del
precio sin IGV, una cifra imposible para un local que lleva meses abierto. Se calibraron con lo que observa el
dueño en la cocina: la proteína del segundo cuesta cerca de S/~3, el resto (incluido el arroz) cerca de S/~1 y la
sopa o entrada alrededor de S/~1. El arroz se fijó en su dato medido ---4.7~kg para 40 platos, 117~g por
plato--- que coincide con las recetas originales: el exceso estaba en la carne y en los acompañamientos, no
en el arroz. Solo se corrigió a la baja; los platos más baratos (cau cau, tallarines, locro de zapallo)
quedaron como estaban.

Después se reemplazaron los precios de referencia por los de las compras reales del dueño (octubre de 2026). El
pollo entra entero a S/~20 y rinde ocho presas: S/~2.50 por presa, y las dos de pechuga van a la causa y al
ají de gallina. La res para asado, estofado y seco cuesta S/~18 el kilo y rinde seis trozos, S/~3 por plato;
el chancho, S/~15 el kilo, S/~2.50 por trozo. El lomo saltado usa la misma pulpa pero solo unos 80~g ---dos kilos
alcanzan para 25 platos---, de modo que es el segundo de res que más deja. La carne picada y la molida se
compran a S/~20, el arroz a S/~3.70 (cien kilos cada dos semanas) y el gas en cuatro balones de S/~50 por semana.
Las cantidades semanales que declara el dueño ---unos 5~kg de carne para sopa, 4~kg de picada, 700~g de
molida--- coinciden con lo que piden las recetas por lo vendido, lo que da confianza en la calibración. La
verdura, en cambio, pesa poco: la nota semanal del mercado suma S/~237, alrededor de medio sol por menú. La
palanca del costo está en la proteína, no en el mercado de verduras: cada segundo de res que se cambia por uno
de pollo o de chancho ahorra entre S/~0.50 y S/~1.50.

Con esa calibración, un menú promedio ---segundo ponderado por lo que se vende, más la entrada y el refresco
promedio--- cuesta \textbf{{{s(pl['menu']['costo'], 2)}}}: {s(pl['menu']['costo'] - pl['costo_entrada_bebida_promedio'], 2)}
el segundo y {s(pl['costo_entrada_bebida_promedio'], 2)} lo demás. Sobre un precio promedio de
{s(pl['menu']['precio_promedio'], 2)} ({s(prec_neto, 2)} sin IGV), los insumos se llevan el
{p(pl['menu']['costo'] / prec_neto)}. Es más que el 35--45\,\% de referencia para menú popular, pero coherente
con un menú bien servido a S/~11 en el sur. El gasto semanal en insumos según lo vendido ronda los
{s(pl['gasto_semana'])}, y se concentra en pocos productos: {top3}. Los tres primeros suman
{p(par[2]['acumulado'])} de las compras (\figura{{fig:platos}}, derecha).

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/platos.pdf}}
\caption{{Candela. Izquierda: ingeniería de menú de los segundos (parte de las ventas contra margen por menú;
las líneas son el umbral de popularidad y el margen promedio). Derecha: peso de cada insumo en el gasto
semanal.}}\label{{fig:platos}}
\end{{figure}}

\subsubsection{{Qué platos sostienen el negocio}}

La ingeniería de menú clasifica cada segundo por lo que vende y por lo que deja. Los platos de pollo (arroz
con pollo, arroz a la jardinera) y los tallarines rojos son \emph{{estrellas}}: venden mucho y dejan cerca de
S/~5 por menú. Los de res ---asado, seco, estofado, chuleta--- son \emph{{caballitos de batalla}}: sostienen
el volumen pero dejan unos 50 céntimos menos, porque la res pesa más en el costo. La pulpa de res es, por sí
sola, el insumo más caro del local. La consecuencia práctica es de mezcla, no de precio: cada día que el menú
ofrece dos segundos de res y uno de pollo, el margen promedio baja; un segundo de pollo o de pasta más por
semana sube la utilidad sin tocar la pizarra.

\subsubsection{{Los números del local}}

La entrevista con el dueño completó lo que el sistema de ventas no tiene. El local paga S/~2\,000 de alquiler
---un precio de conocido; el de mercado para ese tamaño y esa calle es S/~3\,000---. En cocina trabajan tres
personas a tiempo completo (S/~1\,500, S/~1\,500 y S/~1\,300) y en el salón tres mozos a medio tiempo (S/~700 cada
uno); las compras las hace el dueño. Opera con RUC de persona natural y emite boleta solo cuando el cliente la pide, así que el IGV que de verdad paga está entre los dos extremos del cuadro. La inversión inicial fue de S/~20 mil y
el local tardó unos seis meses en llenarse.

{sup_candela()}
\begin{{table}}[H]
\centering\small
\caption{{Candela: el mes con los datos reales (74 menús diarios a S/~11, 26 días). El IGV se muestra aparte
porque depende de si se emite comprobante por toda la venta.}}\label{{tab:candela}}
\begin{{tabular}}{{lrr}}
\toprule
& Soles al mes & De la venta sin IGV \\
\midrule
Venta (lo que entra a caja) & {s(cand['montos']['ventas'])} & \\
\quad IGV de restaurantes (10.5\,\%) & {s(cand['montos']['igv'])} & \\
Venta sin IGV & {s(cand['montos']['netas'])} & 100\,\% \\
\quad Insumos (con merma y descartables) & {s(cand['montos']['insumos'])} & {p(cand['montos']['insumos'] / cand['montos']['netas'])} \\
\quad Planilla (sin el dueño) & {s(cand['montos']['personal'] - 1500)} & {p((cand['montos']['personal'] - 1500) / cand['montos']['netas'])} \\
\quad Alquiler & {s(cand['montos']['alquiler'])} & {p(cand['montos']['alquiler'] / cand['montos']['netas'])} \\
\quad Gas, luz, agua y otros & {s(cand['montos']['gas'] + cand['montos']['otros'])} & {p((cand['montos']['gas'] + cand['montos']['otros']) / cand['montos']['netas'])} \\
\midrule
Queda para el dueño, pagando IGV & {s(cand['utilidad_mes'] + 1500)} & \\
Queda para el dueño, sin IGV & {s(pc['sin_igv'] + 1500)} & \\
\bottomrule
\end{{tabular}}
\end{{table}}

El \cuadro{{tab:candela}} cuenta la situación sin adornos. Sin IGV, la venta alcanza justo para pagar
insumos, sueldos y local: al dueño le quedan {s(pc['sin_igv'] + 1500)} al mes por hacer las compras y
administrar, {"menos de lo que gana una de sus cocineras" if pc['sin_igv'] + 1500 < 1500 else "apenas lo que gana una de sus cocineras"}. Si el IGV se paga sobre toda la venta, el local
{"pierde " + s(-(cand['utilidad_mes'] + 1500)) if cand['utilidad_mes'] + 1500 < 0 else "deja " + s(cand['utilidad_mes'] + 1500)} al mes. Los insumos se llevan más de la mitad de la venta neta; la planilla,
un tercio. Esos dos renglones ---no el alquiler--- son los que deciden.

Que el local siga abierto después de año y medio con estas cuentas es coherente: un negocio que cubre sus
costos de caja puede durar mucho tiempo si el dueño no se cobra. Pero no es una situación estable: cualquier
golpe ---una subida de insumos, un competidor, el IGV de 15\,\% en 2027--- la empuja a pérdida, y el trabajo del
dueño no tiene recompensa.

\subsubsection{{La lección del precio}}

Candela tiene algo que ningún estudio de mercado ofrece: un experimento propio, con tres precios. Abrió a
S/~15 durante tres meses y en un buen día vendía S/~450--550 (unos 33 menús). Bajó a S/~10 durante un año y la
venta saltó a S/~800--1\,000 diarios (unos 90 menús), tanto que la cocina colapsaba. Subió a S/~11 por el alza
de los insumos y para mejorar la comida, y hoy vende S/~750--800 (unos 70). Los tres puntos caen cerca de una
misma curva: la sensibilidad constante que mejor los ajusta es de {n(pc['elasticidad_ajuste'], 1)}, y el paso de
S/~10 a S/~11, por sí solo, da {n(pc['elasticidad_central'], 1)} (entre {n(pc['elasticidad_arco'][0], 1)} y
{n(pc['elasticidad_arco'][1], 1)} según qué extremo de cada rango se tome; \figura{{fig:historia}}).

\begin{{figure}}[H]
\centering
\includegraphics[width=0.8\textwidth]{{fig/historia.pdf}}
\caption{{Candela: la venta diaria en sus tres precios (barras: el rango que da el dueño) frente a curvas de
demanda con distinta sensibilidad, ancladas en la venta de hoy. La curva de $\varepsilon=2.4$ pasa cerca de
los tres.}}\label{{fig:historia}}
\end{{figure}}

Es una clientela sensible, aunque menos de lo que sugería la primera lectura. El modelo calcula que subir un sol
deja de convenir cuando se pierde más de {n(pc['umbral_elasticidad_mas1'], 1)}\,\% de clientes por cada 1\,\% de
alza; la historia de Candela está {"por encima" if pc['elasticidad_ajuste'] > pc['umbral_elasticidad_mas1'] else "apenas por debajo"}
de ese umbral. Por eso la cuenta en soles sale pareja: con los costos de hoy, S/~10 con {n(pc['q0'])} menús
dejaría {s(abs(pc['a_10'] - cand['utilidad_mes']))} {"más" if pc['a_10'] > cand['utilidad_mes'] else "menos"} al mes
que S/~11 con la venta actual. El alza a S/~11 no hizo ganar ni perder mucho dinero; lo que sí hizo fue sacar a la
cocina del colapso, y eso vale aunque el modelo no lo cobre: menos errores, menos espera, menos clientes que se
van sin comer.

El precio de apertura deja otra lección. A S/~15 el menú cubre sus costos con muy poca gente: sin IGV, y pagando
también un sueldo al dueño, el equilibrio está en {pc['equilibrio_15_sin_igv']} menús diarios. Si a ese precio el
local vendía unos 33 fue, en buena parte, porque recién abría ---tardó seis meses en llenarse---. No se sabe
cuánta clientela habría tenido a S/~15 un local ya conocido, y es la pregunta más rentable que queda abierta: un
menú de S/~15 que llegue a 45 o 50 platos diarios gana más que uno de S/~11 con 70, con menos trabajo. Probarlo
no exige cambiar la pizarra: basta un segundo ``especial'' a S/~15 junto al menú de siempre.

\subsubsection{{Dónde está Candela}}

La \figura{{fig:matriz}} muestra el mapa completo: cada celda es la utilidad mensual para una combinación
de precio y volumen, con los costos reales y pagando IGV; el recuadro marca la situación actual. Su
equilibrio ---pagando IGV sobre toda la venta y un sueldo de S/~1\,500 al dueño--- está en {cand['equilibrio']} menús
diarios a S/~11. Leído junto con la lección del precio, el mapa dice
que la salida no está en moverse hacia la derecha (más precio, menos clientes) sino hacia abajo en el costo:
el margen por plato es el que no alcanza.

\begin{{figure}}[H]
\centering
\includegraphics[width=0.92\textwidth]{{fig/matriz.pdf}}
\caption{{Candela: utilidad del mes (miles de soles) por precio y menús al día, con los costos reales y pagando
IGV. El recuadro es la situación de hoy.}}\label{{fig:matriz}}
\end{{figure}}

\subsubsection{{El alquiler del conocido}}

El alquiler de Candela equivale a vender {n(next(a['menus'] for a in hz['alquiler'] if a['nombre'].startswith('Candela')))}
menús diarios solo para pagarlo. El descuento de conocido vale S/~1\,000 al mes. Con la misma medida del
\cuadro{{tab:candela}} ---pagando IGV y sin contar el sueldo del dueño---, hoy el local pierde
{s(-(cand['utilidad_mes'] + 1500))} al mes; con el alquiler de mercado perdería
{s(-(next(v['utilidad_mes'] for v in d['candela_variantes'] if 'mercado' in v['nombre']) + 1500))}, y en un local
propio quedaría en {s(next(v['utilidad_mes'] for v in d['candela_variantes'] if 'propio' in v['nombre']) + 1500)}. El
descuento es, en los hechos, un subsidio del dueño del local, y como todo subsidio de una relación personal,
puede terminarse. Conviene tratarlo como lo que es: una ventaja temporal, no un costo seguro.
"""

    fig_candela_tornado = ("Candela, " if cand else "")

    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage{{fontspec}}
\setmainfont{{Latin Modern Roman}}[SmallCapsFont={{Latin Modern Roman Caps}}]
\setsansfont{{Latin Modern Sans}}
\usepackage{{polyglossia}}
\setmainlanguage[variant=mexican]{{spanish}}
\usepackage[a4paper,top=2.7cm,bottom=2.6cm,left=2.7cm,right=2.7cm,headheight=14pt]{{geometry}}
\usepackage{{microtype}}
\usepackage{{amsmath}}
\usepackage{{booktabs,tabularx,array,multirow}}
\usepackage{{graphicx}}
\usepackage[table]{{xcolor}}
\usepackage{{caption}}
\usepackage{{enumitem}}
\usepackage{{titlesec}}
\usepackage{{fancyhdr}}
\usepackage[most]{{tcolorbox}}
\usepackage{{float}}
\usepackage[section]{{placeins}}
\usepackage{{etoolbox}}
\usepackage{{hyperref}}
\usepackage[all]{{hypcap}}
\usepackage{{xurl}}

\definecolor{{acento}}{{HTML}}{{1F4E79}}
\definecolor{{perdida}}{{HTML}}{{B03024}}
\definecolor{{gris}}{{HTML}}{{5B5A56}}
\definecolor{{fondo}}{{HTML}}{{F4F2EC}}
\definecolor{{franja}}{{HTML}}{{EFEDE6}}
\hypersetup{{colorlinks=true,linkcolor=acento,urlcolor=acento,citecolor=acento}}

\captionsetup{{font=small,labelfont={{sc}},labelsep=period,margin=0.5cm}}
\titleformat{{\section}}{{\normalfont\Large\bfseries\color{{acento}}}}{{\thesection}}{{0.8em}}{{}}
\titleformat{{\subsection}}{{\normalfont\large\itshape}}{{\thesubsection}}{{0.7em}}{{}}
\titleformat{{\subsubsection}}{{\normalfont\normalsize\bfseries}}{{\thesubsubsection}}{{0.6em}}{{}}
\titlespacing*{{\section}}{{0pt}}{{2.2ex plus 1ex}}{{1.2ex}}
\setcounter{{tocdepth}}{{2}}
\setlist{{itemsep=0.35ex,topsep=0.6ex}}
% tablas más aireadas y con franjas para seguir cada fila
\renewcommand{{\arraystretch}}{{1.22}}
\AtBeginEnvironment{{tabular}}{{\rowcolors{{2}}{{white}}{{franja}}}}
\AtBeginEnvironment{{tabularx}}{{\rowcolors{{2}}{{white}}{{franja}}}}
% los cuadros se llaman cuadros, como en el texto
\gappto\captionsspanish{{\renewcommand{{\tablename}}{{Cuadro}}\renewcommand{{\listtablename}}{{Índice de cuadros}}\renewcommand{{\listfigurename}}{{Índice de figuras}}\renewcommand{{\partname}}{{Capítulo}}}}
% referencias que se pueden tocar: lleva a la figura, el cuadro o la sección
\newcommand{{\cuadro}}[1]{{\hyperref[#1]{{cuadro~\ref*{{#1}}}}}}
\newcommand{{\figura}}[1]{{\hyperref[#1]{{figura~\ref*{{#1}}}}}}
\newcommand{{\seccion}}[1]{{\hyperref[#1]{{sección~\ref*{{#1}}}}}}
\newcommand{{\anexo}}[1]{{\hyperref[#1]{{anexo~\ref*{{#1}}}}}}
\newcommand{{\capitulo}}[1]{{\hyperref[#1]{{capítulo~\ref*{{#1}}}}}}
% capítulos: cada uno con su propia numeración de secciones
\renewcommand{{\partname}}{{Capítulo}}
\renewcommand{{\thepart}}{{\arabic{{part}}}}
\counterwithin*{{section}}{{part}}
\titleformat{{\part}}[display]{{\normalfont\huge\bfseries\color{{acento}}}}{{\partname~\thepart}}{{0.4em}}{{}}
\setlength{{\parskip}}{{0.35ex}}
\linespread{{1.06}}

\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[L]{{\small\scshape La economía del menú}}
\fancyhead[R]{{\small\scshape Juliaca, {fecha}}}
\fancyfoot[C]{{\small\thepage}}
\renewcommand{{\headrulewidth}}{{0.3pt}}

\newtcolorbox{{recuadro}}[1]{{enhanced,colback=fondo,colframe=fondo,coltitle=acento,fonttitle=\bfseries,
  title=#1,boxrule=0pt,arc=1pt,left=9pt,right=9pt,top=6pt,bottom=6pt,attach title to upper,after title={{\quad}}}}

\begin{{document}}

\begin{{titlepage}}
\setlength{{\parindent}}{{0pt}}
\vspace*{{3.2cm}}
{{\color{{acento}}\rule{{\linewidth}}{{1.2pt}}}}\par\vspace{{0.9cm}}
{{\fontsize{{26}}{{31}}\selectfont\bfseries La economía del menú\par}}
\vspace{{0.4cm}}
{{\Large\itshape Rentabilidad, formalidad y modelos de operación de los restaurantes de menú en el Perú,
con el caso de una fonda en Juliaca\par}}
\vspace{{0.9cm}}
{{\color{{acento}}\rule{{\linewidth}}{{0.4pt}}}}\par
\vspace{{1.2cm}}
{{\large Estudio de rentabilidad --- Candela, Juliaca\par}}
\vspace{{0.2cm}}
{{\large\color{{gris}} {fecha.capitalize()}\par}}
\vfill
\begin{{minipage}}{{0.86\linewidth}}\small\color{{gris}}
Todas las cifras de este documento salen de un mismo motor de cálculo, verificado contra la calculadora
original del estudio (doce equilibrios por ciudad y 96 simulaciones idénticas). Cada parámetro guarda su
procedencia: observado, estimado, supuesto, de sondeo o propio del local. Las cifras del local son privadas.
\end{{minipage}}
\end{{titlepage}}

\section*{{Resumen}}
\addcontentsline{{toc}}{{section}}{{Resumen}}

Este estudio responde una pregunta que importa a quien tiene o quiere abrir una fonda en el Perú:
\emph{{¿quién gana con un menú, y por qué?}} Para contestarla construye un modelo de costos de un local de menú y
lo usa como laboratorio sobre {NN} negocios ---{NT} restaurantes tipo, situados en Juliaca para que la plaza no confunda
la comparación, y el caso real de Candela, una fonda de esa ciudad con datos de su propio sistema de ventas, sus
recetas, sus compras y una entrevista con el dueño---. Los negocios difieren en lo que define cómo se opera: quién
pone el trabajo y cuánto se le paga, si pagan IGV y planilla en regla, a qué precio y cuánto venden, cuántas horas
abren y cómo organizan la cocina.

Cada análisis es un experimento sobre el modelo: se fija todo, se cambia una cosa y se mide qué pasa, con los
supuestos a la vista. Así se compara a los negocios con sus propios números y a igualdad de condiciones, se reparte
la diferencia entre factores, se los pone a todos a los mismos precios, se simula el riesgo de un año malo, se
buscan las decisiones que resisten la incertidumbre sobre la clientela, se les pone precio al trabajo de la casa y a
la capacidad de la cocina, y se simula minuto a minuto un día de cocina en cuatro formas de organizarla. Un sorteo
de los supuestos dice qué conclusiones se sostienen aunque los números se equivoquen.

Los resultados principales, que la \seccion{{sec:conclusiones}} desarrolla, son cuatro. En una fonda de provincia
gana el trabajo y no el capital: a S/~10, la familia necesita {eq_('Familiar sin sueldos', 10) if mp else 29} menús al día
para no perder, el propietario que cocina {eq_('Propietario que cocina', 10) if mp else 48} y el inversor que contrata a
todos {eq_('Inversor que supervisa', 10) if mp else 99}. Con la clientela medida en Juliaca, subir el precio no paga: la
mejora tiene que venir del costo, la mezcla de platos, más horas de venta o una cocina mejor organizada. La
formalidad cuesta, y el calendario del IGV la encarece. Y Candela está en su punto de equilibrio antes de impuestos
con capacidad de sobra: le falta clientela, no gente. El documento tiene dos capítulos: el primero, sobre los
negocios; el segundo, todavía en construcción, sobre las ciudades.

\clearpage
\tableofcontents
\clearpage
\listoffigures
\listoftables
\clearpage

\clearpage
\part{{Los negocios del menú}}\label{{cap:negocios}}

\section{{Introducción}}

El menú es una institución económica peruana antes que un plato. A mediodía, en cualquier ciudad, una
pizarra ofrece por un precio fijo una entrada o sopa, un segundo a elegir y un refresco. El cliente es el
trabajador que no vuelve a casa a almorzar; el proveedor, un local pequeño que cocina en grandes ollas y
sirve rápido. Detrás de esa escena hay un negocio de márgenes finos que sostiene a cientos de miles de
familias: a fines de 2025 el INEI contaba más de 287 mil empresas formales de comidas y bebidas, y la
informalidad en alojamiento y restaurantes supera el 75\,\%.

El menú se vende a precios muy distintos ---S/~7 en un puesto de mercado, S/~18 en un local de oficinas--- y
con organizaciones muy distintas detrás: una familia que no se cobra sueldos, un propietario que cocina con un
ayudante, un inversor que contrata a todos. La pregunta que ordena este capítulo es cuál de esas formas de operar
gana, cuánto, y por qué: dentro de una misma ciudad, con el mismo costo de insumos, ¿por qué unos locales prosperan
y otros apenas sobreviven?

La hipótesis de este ensayo es que la respuesta está menos en la cocina que en la organización: quién
trabaja y cuánto se le paga, si el local paga impuestos y cargas, cuántos menús logra vender y cuántas horas
aprovecha el alquiler. Para examinarla se construyó un catálogo de restaurantes tipo y se los hizo pasar por
el mismo motor de cálculo, junto con el caso real de Candela, una fonda de Juliaca cuyos datos de ventas,
recetas y costos provienen de su propio sistema.

\section{{Marco teórico}}\label{{sec:marco}}

Este ensayo no propone teoría nueva: aplica a una fonda ideas conocidas de la contabilidad de costos, la economía
del trabajo, la teoría de la decisión y la gestión de operaciones. Esta sección las presenta en el orden en que
se usan.

\subsection{{Un negocio de costos fijos y margen fino}}

Un local de menú vende un producto de precio fijo con un costo variable alto ---los insumos se llevan la mitad
de la venta--- y carga costos fijos que no dependen de cuánto venda: el alquiler, la planilla, el gas y la luz. La
diferencia entre el precio neto de impuestos y el costo variable de cada plato es el \emph{{margen de
contribución}}; el \emph{{punto de equilibrio}} es el número de platos cuyo margen paga los costos fijos. Cuando el
margen por plato es fino, el negocio tiene un \emph{{apalancamiento operativo}} alto: una variación pequeña del
precio o de la clientela mueve mucho la utilidad, en ambas direcciones. Por eso una fonda puede pasar de ganar a
perder con medio sol de diferencia, y por eso el volumen y las horas que rinde el local ---el turno noche reparte
el mismo alquiler entre más platos--- pesan tanto como el costo del plato.

\subsection{{Precio, referencia y sensibilidad de la clientela}}

La \emph{{elasticidad precio}} de la demanda mide cuántos clientes se pierden por cada 1\,\% de alza. Con una
elasticidad mayor que uno, subir el precio reduce la venta en soles; que además reduzca la utilidad depende del
margen. En el menú la elasticidad es alta porque el producto tiene sustitutos cercanos a una cuadra y porque el
cliente lo compara con un \emph{{precio de referencia}} ---la pizarra de la cuadra---: la economía conductual
muestra que los consumidores juzgan un precio por su distancia a esa referencia más que por su nivel (Kahneman y
Tversky, 1979; Thaler, 1985). La consecuencia es que el precio del menú lo fija la competencia local, no el costo,
y que un local que se sale de la referencia pierde clientes aunque su plato lo valga.

\subsection{{Trabajo familiar y costo de oportunidad}}

La utilidad contable de un negocio familiar no descuenta el trabajo de quienes no tienen sueldo. La economía lo
llama \emph{{costo de oportunidad}}: lo que esas personas ganarían trabajando para otro. Restarlo da la
\emph{{utilidad económica}}, que dice si el negocio crea valor o solo transforma trabajo en caja. Chayanov (1925)
describió cómo la unidad familiar campesina acepta jornadas largas y una retribución por hora baja ---la
\emph{{autoexplotación}}--- porque decide por el ingreso del hogar y no por la ganancia por hora; la fonda familiar
urbana se comporta igual. De ahí sale una regla que se usa en todo el ensayo: un negocio que solo gana porque su
gente cobra menos que el mercado no es rentable en sentido estricto; es un empleo mal pagado.

\subsection{{El costo de la formalidad}}

En el Perú, más de tres de cada cuatro empleos de restaurantes son informales. La literatura explica la
informalidad como una decisión: se queda afuera quien no puede pagar los costos de entrar y permanecer en la
formalidad ---impuestos, cargas laborales, trámites--- con la productividad que tiene (De Soto, 1986; Loayza,
2007). En el menú esos costos son concretos: el IGV de restaurantes (10.5\,\% en 2026, 15\,\% en 2027 y 18\,\% si no
cambia la ley), el sueldo mínimo y las cargas de la planilla, y los saltos entre regímenes tributarios, como el tope
del Nuevo RUS. Este ensayo mide cada uno en soles por mes, para saber cuánta productividad hace falta para
pagarlos.

\subsection{{Decidir con incertidumbre}}

Los números de un negocio pequeño no se conocen con exactitud, y las decisiones se toman antes de saber cómo
reaccionará la clientela. Tres herramientas ordenan esa incertidumbre. El \emph{{análisis de sensibilidad}} mueve
una variable a la vez para saber cuál decide el resultado. La \emph{{simulación de Monte Carlo}} repite el año
miles de veces con las variables al azar y entrega una distribución en vez de un número. Y el criterio de
\emph{{decisión robusta}} elige la opción con el mejor resultado en el peor escenario (el criterio maximin de Wald,
1945): no la que más promete, sino la que menos arriesga cuando no se sabe qué escenario vendrá.

\subsection{{Atribuir una diferencia entre factores}}

Cuando dos negocios difieren en varias cosas a la vez, la diferencia de resultados no se puede repartir mirando un
factor por vez, porque los factores interactúan: el IGV pesa más cuanto más se vende. El \emph{{valor de Shapley}}
(Shapley, 1953), nacido en la teoría de juegos cooperativos, reparte la diferencia promediando el aporte de cada
factor sobre todos los órdenes posibles en que podría agregarse. Es el único reparto que suma exactamente la
diferencia total y trata igual a los factores que aportan igual.

\subsection{{La organización de la producción}}

Que la organización del trabajo cambie la productividad con la misma gente es una de las ideas más viejas de la
economía: la división del trabajo de Smith (1776) y, en la cocina profesional, la brigada y el \emph{{mise en
place}} de Escoffier (1903), que separa la preparación del servicio y asigna a cada cocinero un puesto. Tres
herramientas de la gestión de operaciones permiten medirlo. La primera son los \emph{{tiempos de preparación}}:
cada tarea tiene un tiempo fijo ---sacar, lavar, ordenar--- que se paga una vez por tanda, así que agrupar tareas
iguales ahorra tiempo. La segunda es la \emph{{programación con ruta crítica}} (Kelley y Walker, 1959): una lista de
tareas con precedencias termina cuando termina su cadena más larga, y repartir bien la gente consiste en atender
primero esa cadena; el resultado se dibuja como un diagrama de Gantt. La tercera es la \emph{{teoría de colas}}: si
los pedidos llegan más rápido de lo que la cocina despacha, la espera crece aunque el día entero alcance, y la
capacidad la decide la hora punta, no el promedio. La ley de Little (1961) liga esas magnitudes: los clientes que
esperan son el ritmo de llegada por el tiempo de espera.

\section{{Metodología}}\label{{sec:metodologia}}

El estudio combina un modelo de costos de un local de menú con datos de tres fuentes ---una base de doce
ciudades, un catálogo de restaurantes tipo y el caso real de Candela--- y lo usa como laboratorio: cada
pregunta se contesta con un experimento sobre el modelo. Esta sección describe el diseño, el motor, los datos,
los casos y los dos experimentos que necesitan un modelo propio: el barrido de decisiones y la simulación de la
cocina. Los demás análisis se describen al presentar sus resultados, cada uno con su cuadro de supuestos.

\subsection{{Diseño: cada análisis es un experimento}}\label{{sec:metodo}}

Cada análisis de este ensayo es un experimento hecho sobre el modelo, no sobre un local de verdad: se parte de
un caso base, se cambia una cosa (o un grupo de cosas definido de antemano), todo lo demás queda igual y se mide
qué le pasa a un resultado. El protocolo es siempre el mismo:
\begin{{enumerate}}[leftmargin=1.4em,itemsep=1pt]
\item \textbf{{Pregunta.}} Una sola, que se pueda contestar con un número: ¿cuánto cuesta no estar en el local?
\item \textbf{{Caso base.}} Los números con los que entra cada negocio (\cuadro{{tab:entradas}}).
\item \textbf{{Qué se mueve y qué queda fijo.}} Cada análisis abre con un cuadro de \emph{{supuestos}}: las variables
que entran, su valor y su origen ---dato \emph{{propio}} de Candela, \emph{{observado}}, \emph{{ley}}, \emph{{estimado}},
\emph{{calibrado}} para reproducir algo observado, o \emph{{supuesto}} razonado---. Lo que no aparece en ese cuadro es
lo del caso base.
\item \textbf{{Resultado.}} Casi siempre la utilidad del mes o lo que se lleva la casa; a veces el equilibrio, la
probabilidad de perder, los menús que aguanta la cocina o los minutos de espera.
\item \textbf{{Veredicto.}} Si el resultado depende de números supuestos, se repite el cálculo con esos números
movidos al azar (\seccion{{sec:supuestos}}) y se cuenta en qué parte de los sorteos se sostiene.
\end{{enumerate}}
El \cuadro{{tab:tipos}} resume los tipos de experimento que se usan, y el registro de la
\seccion{{sec:experimentos}} reúne cada pregunta con su resultado.

\begin{{table}}[H]
\centering\footnotesize
\caption{{Tipos de experimento del ensayo.}}\label{{tab:tipos}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}p{{0.2\textwidth}}>{{\raggedright\arraybackslash}}X>{{\raggedright\arraybackslash}}p{{0.2\textwidth}}l}}
\toprule
Experimento & Qué se fija y qué se mueve & Qué se mide & Dónde \\
\midrule
Comparación de casos & Cada negocio con sus propios números & Utilidad, equilibrio, VAN & \S\ref{{sec:negocios}} \\
A los mismos precios & Todos con la misma pizarra, de S/~7 a S/~18; cada uno con su venta y sus costos & Equilibrio y lo que se lleva la casa & \S\ref{{sec:precios}} \\
Con la misma venta & Todos con los mismos menús al día, de 40 a 140; cada uno a su precio & Lo que se lleva la casa y precio mínimo & \S\ref{{sec:volumenes}} \\
A igualdad de condiciones & Todos en el mismo local; queda distinto solo quién trabaja, la formalidad y la noche & Lo que se lleva la casa & \S\ref{{sec:negocios}} \\
Descomposición & Se pasa de un negocio a otro factor por factor, en todos los órdenes (Shapley) & Aporte de cada factor & \S\ref{{sec:negocios}} \\
Un cambio a la vez & Se cambia una variable o una decisión; el resto queda quieto & Cambio en la utilidad, quiebre & \S\ref{{sec:negocios}}, \S\ref{{sec:sensibilidad}} \\
Simulación de riesgo & Clientela, insumos, precio y paros al azar, 2\,000 años & Probabilidad de perder & \S\ref{{sec:riesgo}} \\
Barrido de decisiones & Todas las combinaciones de precio, porción y noche, con varias sensibilidades & Mejor decisión en el peor caso & \S\ref{{sec:robustez}} \\
Prueba de estrés & Seis golpes, uno a uno y juntos & Utilidad con el golpe & \S\ref{{sec:estres}} \\
Sorteos de supuestos & Todos los números supuestos al azar en su rango, {n(pr.get('n_sorteos', 1000))} veces & Parte de los sorteos en que se cumple & \S\ref{{sec:supuestos}} \\
Valor de mercado & Se le pone precio al trabajo y al capital de la casa & Utilidad económica & \S\ref{{sec:trabajo}} \\
Simulación de la cocina & Misma cocina, cuatro formas de trabajar, tareas y pedidos minuto a minuto & Menús que aguanta, horas & \S\ref{{sec:cocina}} \\
\bottomrule
\end{{tabularx}}
\end{{table}}

\subsection{{El motor de cálculo}}

El núcleo es un estado de resultados mensual. Para un precio $p$ (con IGV), una tasa de IGV $t$, un costo
de insumos por menú $c$, una merma $m=5\,\%$, descartables $d$, $q$ menús diarios y $D$ días de atención, la
utilidad del mes es
\begin{{equation}}
U \;=\; \Bigl(\frac{{p}}{{1+t}} - c\,(1+m) - d\Bigr)\, q\, D \;-\; F,
\end{{equation}}
donde $F$ reúne los costos fijos: personal (con las cargas de la microempresa si el local es formal y nunca
por debajo del sueldo mínimo), alquiler, gas, luz y agua, S/~400 de otros gastos y, si se decide contarlo,
S/~1\,500 de sueldo del dueño. El personal crece por escalones con el volumen ---un cocinero, un ayudante más
cada 80 menús, un mozo cada 70--- salvo que el escenario traiga su propia planilla, persona por persona,
con pago mensual, quincenal o por día. El punto de equilibrio es el primer volumen diario con $U\ge0$; el
precio mínimo es el que deja $U=0$ al volumen dado. El turno noche, cuando existe, suma su propio volumen,
precio, insumos, gas, luz y equipo, pagado por las noches que trabaja.

Sobre ese núcleo se apoyan tres herramientas. La \emph{{simulación de Monte Carlo}} repite 2\,000 años con la
clientela, el costo de insumos y el precio moviéndose al azar (volumen lognormal con desvío de 20\,\%,
insumos con 8\,\% anual) y, en las ciudades con historial de paros, la pérdida de dos a ocho semanas de venta.
El \emph{{flujo de caja a diez años}} recorre 2026--2035 mes a mes con la curva de arranque, la inflación de
costos, el ajuste del precio en saltos de 50 céntimos, el IGV de cada año, el sueldo mínimo y el impuesto de
cada régimen; de él salen el VAN al 15\,\%, la TIR y el plazo de recuperación. Y el \emph{{análisis de
sensibilidad}} mueve una variable a la vez para medir cuánto cambia la utilidad y cuánto puede moverse cada
número antes de llevarla a cero.

\subsection{{Datos y procedencia de las cifras}}

Cada parámetro de la base de datos lleva su origen. Los precios de menú de Lima, Cusco y Puno son
\emph{{observados}}; los del resto de ciudades, \emph{{estimados}} a partir del ingreso. El IGV de restaurantes
(10.5\,\% en 2026 y 15\,\% en 2027) y el sueldo mínimo (S/~1\,230, luego S/~1\,300) son ley; el 18\,\% desde
2028 es un \emph{{supuesto}}: la ley vigente no prevé una tasa especial más allá de 2027. Los restaurantes
tipo son \emph{{supuestos}} explícitos, documentados en su ficha. Los datos de Candela son \emph{{propios}}: salen
de su sistema de ventas (recetas y lo vendido de cada plato), de una entrevista con el dueño (alquiler, planilla,
historia de precios) y de sus notas de compra (precios de carnes, verduras, abarrotes y gas). La lista de fuentes está en el anexo.

\subsection{{Los casos de estudio}}\label{{sec:casos}}

Para separar el efecto de la organización del efecto de la ciudad, los {NT} restaurantes tipo están en
Juliaca y comparten la misma base de costos; difieren en lo que define el modelo de negocio:

\begin{{description}}[leftmargin=1em,style=nextline]
\item[Quién trabaja] El \emph{{propietario que cocina}} reemplaza al cocinero y se paga los S/~1\,500 del dueño; el \emph{{negocio familiar sin sueldos}} cocina y atiende sin cobrar, en un local igual al del propietario (mismo precio, venta y
alquiler); el \emph{{inversor}} pone el capital y contrata a todo el
personal sin cobrar sueldo; el \emph{{inversor ausente}} no pisa el local: paga administrador, cajero, encargado de
compras y contador, y sus compras cuestan 6\,\% más sin el regateo y el control del dueño.
\item[Formalidad] El \emph{{puesto de mercado}} vende barato y mucho, sin RUC y con alquiler mínimo; el
\emph{{pequeño en Nuevo RUS}} se mantiene bajo S/~8\,000 de ventas al mes para no salir del régimen.
\item[Precio y servicio] El \emph{{ejecutivo}} vende a S/~18 en un local caro; \emph{{día y noche}} es el inversor
que además abre de noche con su propio equipo.
\item[Local] La \emph{{fonda en casa propia}} no paga alquiler, pero está fuera de la calle con más paso:
vende a S/~9 y unos 45 menús diarios.
\item[Referencia] El \emph{{exitoso}} es una referencia compuesta, no un local real: 220 menús a S/~13 con
compras por volumen. Ningún local de menú publica sus números; la referencia combina el dato del MINCETUR de
que la mitad de los restaurantes recupera su inversión en 19 a 24 meses y las ventas de franquicias chicas,
cercanas a S/~50 mil al mes.
\end{{description}}

El \cuadro{{tab:entradas}} reúne los números con los que entra cada negocio a todos los análisis; los que
no son de Candela son supuestos razonados.

\begin{{table}}[H]
\centering\scriptsize
\caption{{Con qué números entra cada negocio. Insumos por menú; gas, luz, planilla e inversión en soles al mes
(la inversión, una vez). Gente: en cocina + en salón (+ administración); * planilla automática del modelo.
Planilla: sin el sueldo del dueño. Formal: qué paga en regla (IGV, planilla). Día y noche suma de noche
{noche_txt}.}}\label{{tab:entradas}}
\setlength{{\tabcolsep}}{{2.5pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xrrrrrcrccr}}
\toprule
Negocio & Precio & Menús & Alquiler & Insumos & Gas y luz & Gente & Planilla & Dueño & Formal & Inversión \\
\midrule
{tabla_entradas()}
\bottomrule
\end{{tabularx}}
\end{{table}}

\begin{{table}}[H]
\centering\footnotesize
\caption{{Los {NN} negocios. ``Dueño'': utilidad del mes más el sueldo del dueño si se paga uno. VAN al
15\,\% a diez años; $+$n: abre también de noche.}}\label{{tab:casos}}
\setlength{{\tabcolsep}}{{3.2pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xrrrcrrrrr}}
\toprule
Negocio & Precio & Menús & Pers. & Formal & Dueño/mes & Equil. & P(pérd.) & VAN & Recupera \\
\midrule
{tabla_casos(orden)}
\bottomrule
\end{{tabularx}}
\end{{table}}

\subsection{{Decisiones con demanda incierta: el barrido}}\label{{sec:barrido}}

Para cada negocio se calcularon todas las combinaciones de cuatro decisiones: el precio (de S/~1 menos a
S/~3 más que hoy, en pasos de 50 céntimos), la porción (económica, con 10\,\% menos de insumos y 6\,\% menos
de clientela; estándar; o generosa, con 12\,\% más de insumos y 6\,\% más de clientela), la mezcla de
segundos (en Candela, la parte que es de res, con el costo de sus propias recetas) y abrir o no un turno
noche tipo. La clientela responde al precio según
\begin{{equation}}
q \;=\; q_0\,\Bigl(\frac{{p}}{{p_0}}\Bigr)^{{-\varepsilon}} f_{{\text{{porción}}}},
\end{{equation}}
donde $\varepsilon$ es la elasticidad: cuántos clientes se pierden por cada 1\,\% de alza. Al empezar el
estudio nadie la había medido para el menú de Juliaca, y el barrido suponía una clientela poco sensible
---0.5, 1.0 y 1.5---. La historia de precios de Candela la midió después: la sensibilidad que mejor ajusta sus
tres precios es de {n(pc['elasticidad_ajuste'], 1) if pc else "2.4"} (\seccion{{sec:candela}}). Por eso cada
combinación se calculó dos veces: con la sensibilidad medida en Juliaca y un margen a cada lado ({el_med}), que
es la versión principal, y con la supuesta de antes, para ver qué conclusiones dependían de ella. En cada caso
se le asignó a la combinación su \emph{{peor}} resultado. La decisión robusta es la que tiene el
mejor peor caso: la que conviene aunque la demanda resulte ser la menos favorable. En total, el servicio del
estudio calculó {n(sum(combinaciones(r) for r in d.get('robustez', [])))} combinaciones
para los {NN} negocios, cada una con su simulación de riesgo y su flujo a diez años.

{sup_barrido()}

{"" if not co else rf"""\subsection{{La simulación de la cocina}}\label{{sec:sim_cocina}}

El día se divide en dos partes. La \emph{{mañana}} es una lista de {len(co['tareas'])} tareas con precedencias ---no
hay aderezo sin cebolla picada ni sopa sin fondo---. Cada preparación toma la \emph{{cantidad de las recetas}} de
Candela (por ejemplo, {n(next(x for t in co['tareas'] if t['id'] == 'papa' for x in t['partes'])['cantidad'], 1)} kilos de
papa y camote cada 100 menús) por la \emph{{velocidad}} de una persona promedio: la del propio dueño donde la midió
(10 kilos de papa en 45 minutos, un kilo de arvejas en vaina en media hora), la tabla de la industria cebollera de
Estados Unidos para la cebolla y estimaciones para el resto (\cuadro{{tab:prep}}). Las recetas del sistema casi
no registran la cebolla ni el ajo de los aderezos, así que esas dos cantidades son supuestas. A eso se suma un tiempo
fijo por tarea (sacar, lavar, ordenar). Las cocciones llevan además una \emph{{espera}} en que la olla cocina sola,
con los tiempos de Juliaca: a 3\,825 metros el agua hierve a unos 88\,°C y el arroz, la papa y los guisos tardan
entre 1.3 y 2 veces lo que tardan en la costa; las menestras, en olla a presión (\cuadro{{tab:coccion}}). Las
preparaciones de más de una hora se parten en tandas que pueden hacer varias personas. Un programador reparte las
tareas minuto a minuto entre la gente disponible, siempre empezando por la que tiene más camino por delante (la ruta
crítica), y así se obtiene a qué hora está todo listo.

El \emph{{almuerzo}} es una cola: los pedidos llegan cada cuarto de hora según el perfil medido en el POS de Candela
y la cocina los despacha a su ritmo; si se atrasa, los clientes esperan. Además de servir, freír y lavar, cada menú se
lleva un tiempo de \emph{{desorden}} ---buscar, reponer, picar lo que faltó, cambiar de tarea---, que no se puede medir
con un cronómetro y se \emph{{calibra}}: es el valor con que una cocina doméstica de
{co['servicio']['calibracion']['personas']} personas aguanta justo los {co['servicio']['calibracion']['menus']} menús que
aguanta Candela sin que nadie espere más de {co['servicio']['espera_maxima']} minutos (\cuadro{{tab:servicio}}).

Se comparan cuatro formas de trabajar, cada una con un cambio más que la anterior, para saber cuánto aporta cada
cambio por separado:
\begin{{description}}[leftmargin=1em,style=nextline,itemsep=1pt]
\item[Doméstica] Cada persona hace sus platos completos; lo que usan varios platos (la cebolla, el ajo, la papa) lo
prepara cada una para el suyo, con su propio tiempo fijo. Todo en la mañana.
\item[Por bloques] Lo compartido se prepara de una sola vez (toda la cebolla junta) y cualquiera hace cualquier cosa,
pero cambiar de puesto cuesta {co['horarios']['cambio_estacion']} minutos. Todo sigue en la mañana.
\item[Mise en place] Además, lo que aguanta de un día para otro ---las verduras peladas, las carnes porcionadas, el
fondo, la menestra--- se deja listo la tarde anterior, después del almuerzo; lo que no alcanza a terminarse antes de
las {co['horarios']['tarde_fin']} vuelve a la mañana.
\item[Por estaciones] Además, cada persona tiene un puesto fijo (fondos, verduras, carnes) y solo ayuda en otro
cuando el suyo no tiene nada listo.
\end{{description}}

\begin{{table}}[H]
\centering\scriptsize
\caption{{Supuestos de la preparación, por cada 100 menús: cantidad de las recetas de Candela, minutos de una persona por
unidad y de dónde sale la velocidad. ``Antes'': se puede dejar listo la tarde anterior. A cada tarea se suman de 3 a 10
minutos fijos.}}\label{{tab:prep}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}p{{0.17\textwidth}}>{{\raggedright\arraybackslash}}p{{0.2\textwidth}}rrrc>{{\raggedright\arraybackslash}}X}}
\toprule
Tarea & Insumo & Cantidad & Min/unidad & Minutos & Antes & Velocidad \\
\midrule
{tabla_prep()}
\bottomrule
\end{{tabularx}}
\end{{table}}

\begin{{table}}[H]
\centering\footnotesize
\caption{{Supuestos de las cocciones y el montaje, por cada 100 menús: minutos de trabajo y minutos en que la olla
cocina sola, en Juliaca.}}\label{{tab:coccion}}
\begin{{tabular}}{{llrr}}
\toprule
Tarea & Puesto & Trabajo & Espera \\
\midrule
{tabla_coccion()}
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{table}}[H]
\centering\footnotesize
\caption{{Supuestos del almuerzo y de la calibración.}}\label{{tab:servicio}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}p{{0.34\textwidth}}>{{\raggedright\arraybackslash}}X}}
\toprule
Variable & Valor y origen \\
\midrule
{tabla_servicio()}
\bottomrule
\end{{tabularx}}
\end{{table}}

"""}

\section{{Resultados}}\label{{sec:resultados}}

Los resultados van de lo general a lo particular: primero los once negocios y el caso Candela, luego el riesgo y la robustez de las conclusiones, y al final lo que el modelo deja ver sobre el trabajo,
la capacidad y la organización de la cocina. La sección cierra con el registro de todos los experimentos.

\subsection{{{NN.capitalize()} negocios}}\label{{sec:negocios}}

\subsubsection{{Quién se lleva qué}}

La \figura{{fig:ingreso}} ordena los negocios por lo que se lleva el dueño cada mes. El resultado más
claro es el de las cuatro formas de organizar el trabajo. Con los mismos costos de insumos y la misma ciudad,
el propietario que cocina gana {s(dc['ingreso_dueno'])} al mes, la familia {s(fam['ingreso_dueno'])}, el inversor
{s(inv['ingreso_dueno'])} y el inversor ausente pierde {s(-aus['ingreso_dueno'])}. La diferencia no está en la
eficiencia de la cocina sino en a quién se le paga por el trabajo. En la fonda familiar el trabajo no
remunerado es, literalmente, la utilidad: lo que el estado de resultados muestra como ganancia es el sueldo
que la familia no se cobra. El inversor ausente es el caso opuesto: compra con plata lo que los otros ponen
con su tiempo, y a 100 menús diarios no le alcanza.

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/ingreso.pdf}}
\caption{{Lo que se lleva el dueño al mes: utilidad más su sueldo, si el modelo le asigna uno.}}\label{{fig:ingreso}}
\end{{figure}}

La estructura de costos (\figura{{fig:estructura}}) explica el orden. En todos los casos los insumos se
llevan entre 40 y 57 centavos de cada sol vendido sin IGV: esa parte es casi fija. Lo que separa a los
ganadores de los perdedores es el personal, que va del {p(fam['estructura']['personal'])} de la venta en la
fonda familiar al {p(aus['estructura']['personal'])} del inversor ausente, y el alquiler, que va del
{p(mer['estructura']['alquiler'])} en el mercado al {p(eje['estructura']['alquiler'])} del ejecutivo. El
exitoso gana porque diluye ambos: con 220 menús, su personal es apenas el {p(exi['estructura']['personal'])} y
sus compras por volumen bajan los insumos al {p(exi['estructura']['insumos'])}.

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/estructura.pdf}}
\caption{{A dónde va cada sol vendido (sin IGV). Más allá de la línea del 100\,\%, el negocio pierde.}}\label{{fig:estructura}}
\end{{figure}}

Dos casos merecen comentario. El \emph{{pequeño en Nuevo RUS}} muestra una trampa del régimen: para no pasar
el tope de S/~96 mil al año tiene que vender poco, y con 30 menús diarios no alcanza a pagar una planilla
formal ni el alquiler; si crece, sale del régimen. El Nuevo RUS sirve para formalizar a quien ya vende poco,
no para construir un negocio que crezca. Y el turno noche funciona porque el alquiler, el local y buena parte
de la luz ya están pagados al mediodía: cada cena vendida aporta casi todo su margen.

{"" if not ig else rf"""\subsubsection{{A igualdad de condiciones}}

Los negocios del catálogo difieren en todo a la vez: precio, venta, alquiler y forma de organizarse. Para
separar lo que se debe a la organización, la \figura{{fig:igualdad}} los pone a todos en el mismo local:
el del propietario que cocina, con S/~10 por menú, 60 menús diarios, S/~1\,200 de alquiler y los mismos insumos, gas
y luz. Lo único que queda distinto es quién trabaja, cómo se le paga, si es formal y si abre de noche.

{sup_igualdad()}
\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/igualdad.pdf}}
\caption{{Lo que se lleva la casa al mes, con los números de cada negocio (gris) y con todos en el mismo local
(color). En rojo, los que pierden.}}\label{{fig:igualdad}}
\end{{figure}}

La primera lección es que varios resultados no venían de la organización sino del lugar y del volumen. El
\emph{{exitoso}} se lleva {s(ig_('Exitoso (referencia compuesta)', 'propio'))} con sus números y
{s(ig_('Exitoso (referencia compuesta)'))} en el mismo local: casi lo mismo que el inversor
({s(ig_('Inversor que supervisa'))}). Su éxito es la escala y el precio, y eso no se copia contratando igual. El
\emph{{puesto de mercado}} baja de {s(ig_('Puesto de mercado informal', 'propio'))} a
{s(ig_('Puesto de mercado informal'))}: su ventaja era un plato más barato de hacer, que la igualación le quita. En sentido contrario, la
\emph{{fonda en casa propia}} sube de {s(ig_('Fonda en casa propia', 'propio'))} a
{s(ig_('Fonda en casa propia'))} aun pagando alquiler: lo que la frenaba era vender poco y barato, no el local.
El \emph{{pequeño en Nuevo RUS}} también mejora, pero a 60 menús ya no cabe en el régimen.

La segunda es que, a igualdad de todo lo demás, el orden lo decide quién trabaja. El negocio familiar sin sueldos junta
{s(ig_('Familiar sin sueldos'))} al mes, más que el propietario que cocina ({s(ig_('Propietario que cocina'))}), pero lo
reparte entre {ig_('Familiar sin sueldos', campo='personas')} personas: {s(ig_('Familiar sin sueldos', campo='por_persona'))}
cada una, frente a los {s(ig_('Propietario que cocina', campo='por_persona'))} que se lleva el propietario solo. El inversor,
que contrata todo, queda en {s(ig_('Inversor que supervisa'))}, y el inversor ausente pierde
{s(-ig_('Inversor ausente'))}. {"" if 'Candela (datos del POS)' not in ig else rf"""Candela, con su
planilla de seis personas, perdería {s(-ig_('Candela (datos del POS)'))} en ese local: necesita
{ig_('Candela (datos del POS)', campo='equilibrio')} menús diarios para cubrirse, frente a los
{ig_('Propietario que cocina', campo='equilibrio')} del propietario que cocina. """}

{"" if not pasos_aus else rf"""El caso del inversor ausente merece separarse en partes, porque mezcla dos cosas: un equipo de
cocina más grande y el costo de no estar. El \cuadro{{tab:ausencia}} parte del inversor en el mismo local y le
agrega, uno por uno, los cambios del inversor ausente. La gerencia pagada ---administrador, cajero y encargado de
compras--- es el golpe más grande: {s(-pasos_aus[2]['cambio'])} al mes. El contador externo suma {s(-pasos_aus[3]['cambio'])} y
las compras sin el control del dueño, {s(-pasos_aus[4]['cambio'])} más; ese último renglón crece con el volumen, porque
el sobrecosto se paga en cada plato. En total, no estar le cuesta
{s(-(pasos_aus[2]['cambio'] + pasos_aus[3]['cambio'] + pasos_aus[4]['cambio']))} al mes a un local de 60 menús: {n(-(pasos_aus[2]['cambio'] + pasos_aus[3]['cambio'] + pasos_aus[4]['cambio']) / ig_('Propietario que cocina'), 1)} veces
lo que el propietario que cocina se lleva a su casa. El resto de la brecha, {s(-pasos_aus[1]['cambio'])}, no es ausencia sino
una cocina con más gente y mejor pagada.

\begin{{table}}[H]
\centering\small
\caption{{Del inversor al inversor ausente, un cambio a la vez, en el mismo local (S/~10, 60 menús, S/~1\,200 de
alquiler). Utilidad del mes, sin sueldo del dueño.}}\label{{tab:ausencia}}
\begin{{tabularx}}{{\textwidth}}{{Xrr}}
\toprule
 & Utilidad & Cambio \\
\midrule
{tabla_ausencia()}
\bottomrule
\end{{tabularx}}
\end{{table}}

"""}La lección práctica sirve para cualquier caso: antes de copiar a un negocio que gana, conviene separar si gana
por cómo se organiza o por dónde está y cuánto vende. Lo primero se puede imitar; lo segundo, casi nunca. El panel
del estudio tiene esta misma comparación en su pestaña \emph{{Comparar}}, con el precio, la venta, el alquiler y los
insumos que se quieran poner.
"""}

{"" if not dcp else rf"""\subsubsection{{Qué separa a cada negocio del propietario que cocina}}

La igualación responde qué pasaría si todos tuvieran el mismo local. La pregunta inversa es de dónde viene la
diferencia de cada uno. El \cuadro{{tab:factores}} y la \figura{{fig:factores}} parten del propietario que
cocina ({s(dcp['base'])} al mes para su casa) y reparten la distancia a cada negocio entre cinco factores: el
local y la venta (precio, menús, alquiler, gas y luz), los insumos por menú, quién trabaja y cuánto se le paga, la
formalidad y el turno noche. Como los factores se potencian entre sí ---el IGV pesa más cuanto más se vende---, el
aporte de cada uno es el promedio de su efecto sobre todos los órdenes posibles en que podrían agregarse (el valor
de Shapley de la teoría de juegos), y los cinco aportes suman exactamente la diferencia.

{sup_factores()}
\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/factores.pdf}}
\caption{{Del propietario que cocina a cada negocio: cuánto suma o resta cada factor a lo que se lleva la casa al
mes. El rombo es la diferencia total.}}\label{{fig:factores}}
\end{{figure}}

\begin{{table}}[H]
\centering\footnotesize
\caption{{Aporte de cada factor a la diferencia con el propietario que cocina, en soles al mes (valores de Shapley). La
última columna es lo que se lleva la casa: utilidad más el sueldo del dueño, si trabaja.}}\label{{tab:factores}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xrrrrrr}}
\toprule
Negocio & Local y venta & Insumos & Personal & Formalidad & Noche & La casa \\
\midrule
{tabla_factores()}
\bottomrule
\end{{tabularx}}
\end{{table}}

Cuatro patrones saltan a la vista. Primero, \emph{{quién trabaja}} es el factor que más resta: le quita
{s(-ap('Inversor que supervisa', 'personal'))} al mes al inversor, {s(-ap('Candela (datos del POS)', 'personal'))} a
Candela y {s(-ap('Inversor ausente', 'personal'))} al inversor ausente. Solo suma en los negocios
donde el trabajo se paga menos que en la referencia: {", ".join(f"{corto(f['nombre'])[:1].lower() + corto(f['nombre'])[1:]} ({s(f['aportes']['personal'])})" for f in sorted(dcp['filas'], key=lambda f: -f['aportes']['personal']) if f['aportes']['personal'] >= 1)}. Segundo, la \emph{{formalidad}} ---el IGV
y la planilla en regla--- cuesta entre {s(-max(f['aportes']['formalidad'] for f in formales))} y
{s(-min(f['aportes']['formalidad'] for f in formales))} al mes a los negocios formales, y cuesta más a quien más
vende. Tercero, \emph{{el local y la venta}} es lo que separa a los que ganan mucho: le da
{s(ap('Exitoso (referencia compuesta)', 'local'))} al exitoso y {s(ap('Ejecutivo en el centro', 'local'))} al
ejecutivo, aunque este último devuelve {s(-ap('Ejecutivo en el centro', 'insumos'))} en un plato más caro de hacer.
Cuarto, el \emph{{puesto de mercado}} no gana por volumen ---su local y su venta aportan
{s(ap('Puesto de mercado informal', 'local'))}--- sino por un plato barato: sus insumos le suman
{s(ap('Puesto de mercado informal', 'insumos'))} al mes. Y el turno noche es lo único que separa al local de
\emph{{día y noche}} de un inversor: le suma {s(ap('Día y noche', 'noche'))}.

{"" if 'Candela (datos del POS)' not in fac else rf"""Candela se explica con la misma tabla. Vende más y más caro que el propietario que cocina, y eso le suma
{s(ap('Candela (datos del POS)', 'local'))}; pero su planilla de seis personas le resta
{s(-ap('Candela (datos del POS)', 'personal'))}, sus insumos {s(-ap('Candela (datos del POS)', 'insumos'))} y la
formalidad {s(-ap('Candela (datos del POS)', 'formalidad'))}. La palanca más grande no está en el precio ni en el
local, sino en cómo se reparte el trabajo de la cocina y del salón."""}
"""}

{"" if not mp else rf"""
\subsubsection{{Todos a los mismos precios}}\label{{sec:precios}}

Cada negocio del catálogo vende a su propio precio, y eso hace difícil ordenarlos: ¿el ejecutivo gana por lo que
cobra o pierde por lo que gasta? Este experimento pone la misma pizarra a todos ---S/~7, 9, 10, 11, 12, 13, 15 y
18--- y mide dos cosas que no dependen de cómo reaccione la clientela. La primera es el \emph{{punto de equilibrio}}:
cuántos menús al día tiene que vender cada negocio, a ese precio, para no perder (\cuadro{{tab:precios_eq}} y
\figura{{fig:precios}}). La segunda es lo que se llevaría la casa si vendiera lo mismo que hoy pero a cada precio
(\cuadro{{tab:precios_casa}}): es el efecto puro del precio, sin suponer cuántos clientes se ganan o se pierden; la
\seccion{{sec:robustez}} agrega después la reacción de la clientela.

{cuadro("Supuestos del experimento de precios comunes.", "tab:sup_precios", [
    ("Precios", ", ".join("S/~" + str(x) for x in mp["precios"]), "elegidos para cubrir del puesto al ejecutivo"),
    ("Lo que queda de cada negocio", "su venta, su planilla, su alquiler, sus insumos y su régimen", "cada negocio"),
    ("Equilibrio", "menús al día con utilidad cero a ese precio; `--': ni con 600 al día", "método"),
    ("Lo que se lleva la casa", "utilidad del mes más el sueldo del dueño, con la venta de hoy", "método"),
])}

\begin{{table}}[H]
\centering\footnotesize
\caption{{Menús al día que necesita cada negocio para no perder, según el precio del menú. En negrita, su precio
actual; ``--'': no alcanza ni con 600 menús diarios.}}\label{{tab:precios_eq}}
\setlength{{\tabcolsep}}{{3.5pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xr{"r" * len(mp["precios"])}}}
\toprule
Negocio & Hoy & {" & ".join("S/~" + str(x) for x in mp["precios"])} \\
\midrule
{tabla_precios("equilibrio")}
\bottomrule
\end{{tabularx}}
\end{{table}}

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/precios.pdf}}
\caption{{Menús al día para no perder, según el precio del menú, con la planilla, el alquiler y los insumos de
cada negocio. Las curvas cortadas arriba pasan de 300.}}\label{{fig:precios}}
\end{{figure}}

\begin{{table}}[H]
\centering\footnotesize
\caption{{Lo que se llevaría la casa al mes si cada negocio vendiera lo de hoy a cada precio (utilidad más sueldo del
dueño). En negrita, su precio actual; en rojo, pérdida.}}\label{{tab:precios_casa}}
\scriptsize\setlength{{\tabcolsep}}{{2.2pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xr{"r" * len(mp["precios"])}}}
\toprule
Negocio & Hoy & {" & ".join("S/~" + str(x) for x in mp["precios"])} \\
\midrule
{tabla_precios("casa")}
\bottomrule
\end{{tabularx}}
\end{{table}}

El \cuadro{{tab:precios_eq}} ordena a los negocios mejor que cualquier gráfica de utilidad, porque elimina el precio
de la comparación. A S/~10, el precio más común del menú popular, el negocio familiar sin sueldos necesita
{eq_('Familiar sin sueldos', 10)} menús al día para no perder; el propietario que cocina,
{eq_('Propietario que cocina', 10)}; la fonda en casa propia, {eq_('Fonda en casa propia', 10)}; el inversor que
supervisa, {eq_('Inversor que supervisa', 10)}, y el inversor ausente, {eq_('Inversor ausente', 10)}. Los cinco cocinan el
mismo plato: lo que los separa es a quién le pagan por el trabajo y cuánto. A S/~7, el precio del puesto de
mercado, ningún negocio con planilla contratada y en regla cubre sus costos con ninguna cantidad de menús: a ese
precio el margen de un plato no paga a la gente que hace falta para servirlo, y solo sobreviven los que no pagan
ese trabajo o lo pagan por debajo del mercado. El ejecutivo, con su local caro y sus insumos de S/~7 por plato,
recién tiene un equilibrio alcanzable desde S/~{next(pr for pr in mp['precios'] if eq_('Ejecutivo en el centro', pr) is not None)}:
no es un negocio de menú popular con otro nombre, es otro negocio.

El \cuadro{{tab:precios_casa}} muestra cuánto vale un sol en cada caso. Como el precio entra entero al margen, cada sol
más vale lo mismo que la venta del mes: {s(casa_('Propietario que cocina', 11) - casa_('Propietario que cocina', 10))}
en un local de 60 menús y {s(casa_('Exitoso (referencia compuesta)', 11) - casa_('Exitoso (referencia compuesta)', 10))}
en uno de 220. Por eso el precio es la variable más sensible de todas y por eso el puesto de mercado, que vende a
S/~7, es el que más pierde cuando un competidor lo obliga a bajar un sol. El cuadro también dice desde qué precio
cubre sus costos cada uno con su venta actual: el inversor que supervisa desde S/~{precio_cubre('Inversor que supervisa')},
el inversor ausente desde S/~{precio_cubre('Inversor ausente')}, el ejecutivo desde S/~{precio_cubre('Ejecutivo en el centro')}{"" if not cand else f" y Candela desde S/~{precio_cubre('Candela (datos del POS)')}"}.
Que esos precios se puedan cobrar es otra pregunta, y la contesta la clientela: la \seccion{{sec:robustez}} muestra que,
con la sensibilidad medida en Juliaca, subir la pizarra pierde más clientes de los que el margen compensa.
"""}

{"" if not mv else rf"""
\subsubsection{{Todos con la misma venta}}\label{{sec:volumenes}}

El experimento anterior fijó el precio; este fija la venta. Todos los negocios venden los mismos menús al día
---40, 60, 80, 100, 120 y 140---, cada uno a su propio precio y con sus costos, y se mide lo que se llevaría la casa
(\cuadro{{tab:volumenes_casa}} y \figura{{fig:volumenes}}) y el precio mínimo que necesitaría a esa venta para no perder
(\cuadro{{tab:volumenes_pmin}}). Hay una diferencia con el precio que conviene tener presente: vender más exige
gente. Los negocios con planilla automática la agrandan solos (un ayudante cada 80 menús, un mozo cada 70); los que
traen su planilla ---el propietario, la familia, la fonda, el puesto, el pequeño, el inversor ausente y Candela--- la
mantienen fija, así que sus cifras a volúmenes altos suponen la misma gente sirviendo más de lo que aguanta. El
símbolo $\dagger$ marca las celdas donde la venta pasa de lo que su gente puede atender según la
\seccion{{sec:capacidad}}: ahí haría falta contratar, y la utilidad real sería menor.

{cuadro("Supuestos del experimento de ventas comunes.", "tab:sup_volumenes", [
    ("Menús al día", ", ".join(str(x) for x in mv["volumenes"]), "elegidos para cubrir del pequeño al exitoso"),
    ("Lo que queda de cada negocio", "su precio, su planilla, su alquiler, sus insumos y su régimen", "cada negocio"),
    ("Planilla", "la automática crece con la venta; la propia queda fija ($\\dagger$ cuando la venta pasa de su capacidad)", "método"),
    ("Precio mínimo", "el que deja la utilidad en cero a esa venta", "método"),
])}

\begin{{table}}[H]
\centering\footnotesize
\caption{{Lo que se llevaría la casa al mes si cada negocio vendiera cada volumen, a su propio precio (utilidad más
sueldo del dueño). En negrita, su venta actual; en rojo, pérdida; $\dagger$: más de lo que aguanta su gente.}}\label{{tab:volumenes_casa}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xr{"r" * len(mv["volumenes"])}}}
\toprule
Negocio & Hoy & {" & ".join(str(x) for x in mv["volumenes"])} \\
\midrule
{tabla_volumenes("casa")}
\bottomrule
\end{{tabularx}}
\end{{table}}

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/volumenes.pdf}}
\caption{{Lo que se lleva la casa al mes según los menús al día, con el precio, la planilla, el alquiler y los insumos
de cada negocio.}}\label{{fig:volumenes}}
\end{{figure}}

\begin{{table}}[H]
\centering\footnotesize
\caption{{Precio mínimo del menú para no perder a cada venta diaria. En negrita, la venta actual de cada negocio;
$\dagger$: más de lo que aguanta su gente.}}\label{{tab:volumenes_pmin}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xr{"r" * len(mv["volumenes"])}}}
\toprule
Negocio & Hoy & {" & ".join(str(x) for x in mv["volumenes"])} \\
\midrule
{tabla_volumenes("precio_minimo")}
\bottomrule
\end{{tabularx}}
\end{{table}}

Las curvas de la \figura{{fig:volumenes}} son rectas, y su pendiente es el margen de contribución del mes por cada
menú diario: unos {s((vcasa_('Propietario que cocina', 100) - vcasa_('Propietario que cocina', 80)) / 20)} al mes por
cada menú más al día en el propietario que cocina, {s((vcasa_('Ejecutivo en el centro', 100) - vcasa_('Ejecutivo en el centro', 80)) / 20)}
en el ejecutivo. Lo que las separa es dónde cortan el cero. A 60 menús ---la venta del propietario--- la familia se
lleva {s(vcasa_('Familiar sin sueldos', 60))} y el inversor que supervisa pierde {s(-vcasa_('Inversor que supervisa', 60))};
a 100, todos los de la casa ganan y el inversor ya se lleva {s(vcasa_('Inversor que supervisa', 100))}, pero el ausente
sigue perdiendo {s(-vcasa_('Inversor ausente', 100))} y recién cubre costos pasados los {volumen_cubre('Inversor ausente') or 140}
menús diarios. El puesto de mercado es el caso más claro de negocio de volumen: a 60 menús pierde, porque a S/~7 el
margen por plato es chico, y recién a {volumen_cubre('Puesto de mercado informal')} empieza a ganar; vende 120 porque
no puede vender menos. El exitoso, al revés, necesita {volumen_cubre('Exitoso (referencia compuesta)')} menús para
cubrir su local y su planilla, y a 220 los diluye hasta ganar más que todos: su ventaja es la escala, como ya mostró
la descomposición.

El \cuadro{{tab:volumenes_pmin}} lee lo mismo desde el precio. A 60 menús, la familia podría cobrar
{s(vpmin_('Familiar sin sueldos', 60), 2)} sin perder; el propietario, {s(vpmin_('Propietario que cocina', 60), 2)}; el
inversor que supervisa, {s(vpmin_('Inversor que supervisa', 60), 2)}, y el inversor ausente,
{s(vpmin_('Inversor ausente', 60), 2)}. Ese es el precio con el que cada organización puede competir en la cuadra, y
explica por qué la pizarra la marcan los que no pagan el trabajo: con 60 menús, el que contrata a todos necesita
cobrar S/~{n(vpmin_('Inversor que supervisa', 60) - vpmin_('Familiar sin sueldos', 60), 1)} más que la familia por el mismo
plato. El volumen cierra parte de esa brecha ---a 140 menús la diferencia baja a
S/~{n(vpmin_('Inversor que supervisa', 140) - vpmin_('Familiar sin sueldos', 140), 1)}--- pero no la elimina, porque la
planilla automática también crece con la venta.
{"" if not cand else rf"""
Candela, con su planilla de seis, se lleva {s(vcasa_('Candela (datos del POS)', 100))} al mes a 100 menús, el tope de su
cocina y de su salón, y necesita {s(cand['precio_minimo'], 2)} para no perder con la venta de hoy frente
a {s(vpmin_('Candela (datos del POS)', 100), 2)} si vendiera 100: la lectura es la misma que la de la \seccion{{sec:capacidad}},
ahora en soles por menú."""}
"""}

{candela_seccion}

\subsection{{Riesgo}}\label{{sec:riesgo}}

Un promedio esconde la pregunta que quita el sueño: ¿qué pasa en un año malo? La \figura{{fig:riesgo}}
muestra la distribución de la utilidad anual en 2\,000 años simulados para cada negocio. Los locales con
margen holgado ---el exitoso, día y noche, la familia--- casi nunca terminan el año en pérdida; el inversor
lo hace la mitad de las veces y el inversor ausente casi siempre.

{sup_riesgo()}
\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/riesgo.pdf}}
\caption{{Distribución de la utilidad de un año (2\,000 simulaciones por caso) y probabilidad de terminarlo
en pérdida.}}\label{{fig:riesgo}}
\end{{figure}}

La forma de las cajas importa tanto como su posición. El ejecutivo tiene una utilidad media positiva pero
una dispersión ancha: depende de una clientela de oficina más volátil y su margen se lo come el IGV. El
propietario que cocina tiene una caja angosta y casi toda a la derecha del cero: su costo fijo es bajo y su
principal costo laboral, él mismo, se ajusta solo cuando las ventas bajan. Esa es la razón económica de la
resistencia de la fonda familiar: no es más rentable por plato, sino más flexible ante un mal año.

\subsection{{Sensibilidad: cuánto aguanta cada negocio}}\label{{sec:sensibilidad}}

La sensibilidad mide lo que el promedio no muestra: cuánto margen de error tiene cada negocio. La
\figura{{fig:quiebres}} y el \cuadro{{tab:quiebres}} muestran, para cada uno, cuánto puede moverse
cada variable ---sola, con las demás quietas--- antes de que la utilidad llegue a cero. Si el negocio ya
pierde, la celda indica cuánto tendría que moverse para dejar de perder.

{sup_sensibilidad()}
\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/quiebres.pdf}}
\caption{{Cuánto puede moverse cada número antes de llegar a pérdida ($\downarrow$ bajar, $\uparrow$ subir). En
rojo, los negocios que ya pierden: cuánto les falta. ``Sobra'': aguanta cualquier cambio razonable.}}\label{{fig:quiebres}}
\end{{figure}}

\begin{{table}}[H]
\centering\small
\caption{{Cambio que deja la utilidad en cero (variables principales).}}\label{{tab:quiebres}}
\begin{{tabular}}{{lccccc}}
\toprule
Negocio & Precio & Menús/día & Insumos & Sueldos & Alquiler \\
\midrule
{tabla_quiebres(todos)}
\bottomrule
\end{{tabular}}
\end{{table}}

El patrón es consistente: \emph{{el precio es siempre la variable más sensible, y el volumen la segunda}}. En
el propietario que cocina, el precio puede bajar {p(abs(dc['quiebres']['precio']))} y el volumen
{p(abs(dc['quiebres']['q']))} antes de perder; en el inversor, apenas {p(abs(inv['quiebres']['precio']), 1)}
y {p(abs(inv['quiebres']['q']), 1)}: cualquier competidor que baje cincuenta céntimos lo saca del negocio. En
cambio, el alquiler y el gas casi nunca deciden: pueden duplicarse en la mayoría de los casos sin llevar al
local a pérdida. Esto ordena las prioridades de gestión: proteger el precio y el volumen ---la ubicación, la
calidad que sostiene la pizarra, la clientela fija--- vale más que negociar el alquiler o cambiar de
proveedor de gas.

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/tornados.pdf}}
\caption{{Utilidad del mes cuando cada variable baja (naranja) o sube (azul) 10\,\%: {fig_candela_tornado}el
propietario que cocina y el exitoso. La línea vertical es la utilidad actual.}}\label{{fig:tornados}}
\end{{figure}}

La \figura{{fig:tornados}} muestra el mismo análisis en forma de tornado para tres casos. En todos, un
10\,\% de precio mueve la utilidad más que un 10\,\% de cualquier costo. Un detalle técnico ayuda a leer los
casos chicos: como el personal crece por escalones, una baja del volumen puede, en un rango corto, mejorar la
utilidad, porque permite prescindir de un mozo. Los negocios pequeños viven en esos escalones.

\subsection{{Decisiones robustas}}\label{{sec:robustez}}

La sensibilidad mueve una variable a la vez. Las decisiones reales se toman juntas ---subir el precio y a la
vez cambiar la porción, o abrir de noche--- y, sobre todo, se toman sin saber cómo va a reaccionar la
clientela. El análisis anterior tenía un supuesto optimista escondido: si el precio sube, la clientela no
cambia. Esta sección lo quita con el barrido de decisiones descrito en la \seccion{{sec:barrido}}.

{"" if not rc else rf"""\subsubsection{{Candela, con su propia elasticidad}}

Para Candela no hace falta suponer cómo reacciona la clientela: su historia lo mide. El barrido usó tres
sensibilidades alrededor de la observada ({", ".join(n(float(k), 1) for k in sorted(rc['curvas'], key=float))}) y precios entre
S/~9 y S/~13. La \figura{{fig:precio_robusto}} muestra el resultado: con la sensibilidad medida, la curva es
casi plana entre S/~10 y S/~11; con una clientela algo más sensible conviene bajar, y con una algo menos
sensible, subir, pero en ningún caso el mejor precio deja más de
{s(max(max(x['utilidad'] for x in serie) - next(x['utilidad'] for x in serie if abs(x['precio'] - rc['precio0']) < 1e-9) for serie in rc['curvas'].values()))}
al mes sobre el de hoy. El barrido tiene además un techo: con tres en cocina y tres mozos, Candela aguanta unos
{n(rc['capacidad']) if rc.get('capacidad') else 90} menús al día (a S/~10, cuando los pasaba, colapsaba), así que ninguna combinación vende más que eso, por mucho que la curva prometa
más clientela al bajar el precio.

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/precio_robusto.pdf}}
\caption{{Candela: utilidad del mes según el precio con la sensibilidad medida en su propia historia y dos
valores vecinos (porción, mezcla y turno de hoy).}}\label{{fig:precio_robusto}}
\end{{figure}}

El dueño ya decidió no abrir de noche, así que la decisión que importa es la mejor sin turno noche:
\textbf{{{esc(describir_decision(rc['mejor_sin_cambiar_turno']))}}}, que en el peor supuesto deja
{s(rc['mejor_sin_cambiar_turno']['utilidad_peor'])} al mes frente a {s(rc['base']['utilidad_media'])} de hoy. Todas
las combinaciones sin noche siguen en pérdida si se paga IGV sobre toda la venta: precio, porción y mezcla
mejoran la situación, pero no la cambian de signo. Con noche ---que el barrido sigue señalando como la palanca
más grande--- la mejor combinación llegaría a {s(rc['mejor']['utilidad_peor'])} en el peor caso, siempre que
existiera esa demanda nocturna.

"""}

\subsubsection{{Todos los negocios}}

La \figura{{fig:decisiones}} resume el barrido de los {NN} negocios: la utilidad de hoy, la de la mejor
decisión sin abrir de noche y la de la mejor decisión en general, siempre en el peor supuesto de demanda. En
todos los casos existe una combinación que mejora la situación actual aun con la demanda más desfavorable. El
inversor pasa de {s(r_inv['base']['utilidad_media'])} a {s(r_inv['mejor']['utilidad_peor'])} de utilidad al mes; el propietario que
cocina, de {s(r_dc['base']['utilidad_media'])} a {s(r_dc['mejor']['utilidad_peor'])}, ya descontado su propio sueldo de
S/~1\,500.

El experimento de la sensibilidad cambia una conclusión importante. Con la clientela poco sensible que se
suponía, en {al_tope_sup} de los {len(sup_)} restaurantes tipo la mejor decisión subía el precio hasta el tope
probado ---S/~3 más---, y de ahí salía la idea de que el menú de Juliaca se vende barato. Con la sensibilidad
medida, la mejor decisión deja el precio donde está en {quietos_med} de los {len(tipo)} y, en el resto, lo sube
{"a lo más" if max_sube_med > 0 else ""} {s(max_sube_med, 2)}. Lo que mejora la situación ya no es el precio sino
la porción, la mezcla de segundos y, sobre todo, el turno noche. Dos de esas palancas descansan en supuestos del
barrido: cuánta clientela se pierde con una porción más chica y la noche tipo de 30 platos.

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/decisiones.pdf}}
\caption{{Utilidad del mes hoy y con la mejor decisión, en el peor de tres supuestos de demanda. En amarillo, lo
mejor que se logra sin abrir de noche.}}\label{{fig:decisiones}}
\end{{figure}}

El turno noche aparece en la mejor decisión de todos los negocios. Hay que tomarlo con cuidado: el modelo usa
una noche tipo ---30 platos a S/~12--- igual para todos, y la demanda nocturna de cada local es justamente lo
que menos se conoce. Lo que el barrido sí establece es que, si esa demanda existe, la noche rinde mucho porque
el alquiler ya está pagado. La distancia entre el punto amarillo y el azul es el valor de averiguarlo con un
piloto.

\subsection{{Prueba de estrés}}\label{{sec:estres}}

La última pregunta es la del año malo deliberado: ¿qué pasa si llega un golpe? Cada negocio se sometió a seis
golpes por separado ---clientela $-$15\,\%, insumos $+$20\,\%, IGV de 18\,\%, sueldos $+$10\,\%, alquiler
$+$25\,\% y un competidor que obliga a bajar S/~1--- y a todos juntos (\figura{{fig:estres}}).

{sup_estres()}
\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/estres.pdf}}
\caption{{Utilidad del mes (miles de soles) de cada negocio frente a cada golpe; la última columna los suma
todos.}}\label{{fig:estres}}
\end{{figure}}

Solo {len(sobreviven)} de los {NN} negocios siguen ganando con todos los golpes juntos: {lista_neg(sobreviven)}.
Los golpes que más daño hacen son los de insumos y el del competidor que obliga a bajar el precio; el alza de
sueldos y la del alquiler, en cambio, se absorben. La fonda familiar resiste por la misma razón que en la
simulación de riesgo: no tiene planilla que pagar cuando las ventas caen. {"" if not rc else f"Candela, con los datos actuales, ya pierde antes del golpe; el de insumos le quita otros {s(rc['base']['utilidad_media'] - golpe(rc, 'insumos'))} al mes y el del competidor {s(rc['base']['utilidad_media'] - golpe(rc, 'competidor'))}: son los dos frentes que más le conviene vigilar."}

{"" if not sr else rf"""\subsection{{¿Cuánto dependen las conclusiones de los supuestos?}}\label{{sec:supuestos}}

Los restaurantes tipo son números razonados, no observados: nadie midió el plato del puesto de mercado ni la
venta del exitoso. Un hallazgo que solo vale con esos números exactos es una opinión; uno que vale aunque los
números se equivoquen es una conclusión. Para separarlos, el cálculo se repitió {n(sr['n'])} veces moviendo al
azar, y por separado para cada negocio, todos sus números dentro de rangos razonables: el precio
±{p(sr['rangos']['precio'], 0)}, la venta ±{p(sr['rangos']['q'], 0)}, los insumos ±{p(sr['rangos']['insumos'], 0)},
el alquiler ±{p(sr['rangos']['alquiler_mes'], 0)}, los sueldos ±{p(sr['rangos']['sueldos'], 0)} y el gas y la luz
±{p(sr['rangos']['balones'], 0)}. El \cuadro{{tab:supuestos}} cuenta en qué parte de esos sorteos se cumple cada
hallazgo: se sostiene si se cumple en nueve de cada diez o más, es probable entre siete y nueve, y no es
concluyente por debajo.

{sup_sorteos()}
\begin{{table}}[H]
\centering\small
\caption{{Parte de los {n(sr['n'])} sorteos en que se cumple cada hallazgo.}}\label{{tab:supuestos}}
\begin{{tabularx}}{{\textwidth}}{{Xrl}}
\toprule
Hallazgo & Se cumple & Veredicto \\
\midrule
{tabla_supuestos()}
\bottomrule
\end{{tabularx}}
\end{{table}}

Los hallazgos centrales del ensayo resisten: quién trabaja decide el resultado, el inversor ausente pierde en todos
los sorteos y la noche mejora al local que la abre. Dos lecturas, en cambio, no son concluyentes y conviene
citarlas con cuidado. Que la familia cobre menos que el mínimo por hora depende de supuestos que nadie ha medido
---cuánto vende, cuánto trabaja---: está cerca del límite y cae a uno u otro lado. Y que Candela cubra sus costos
sin IGV es una moneda al aire: el local está tan cerca del equilibrio que un error pequeño en cualquiera de sus
números lo cambia, lo cual es en sí mismo un dato sobre su fragilidad.

\begin{{table}}[H]
\centering\small
\caption{{Lugar de cada negocio por lo que se lleva la casa al mes: hoy, el rango en nueve de cada diez sorteos,
cuántas veces repite su lugar y cuántas veces no pierde.}}\label{{tab:lugares}}
\begin{{tabularx}}{{\textwidth}}{{Xrrrr}}
\toprule
Negocio & Hoy & Rango & Repite & No pierde \\
\midrule
{tabla_lugares()}
\bottomrule
\end{{tabularx}}
\end{{table}}

El orden tiene puntas firmes y un medio móvil (\cuadro{{tab:lugares}}). El exitoso es siempre el primero y el
inversor ausente casi siempre el último, pero los negocios del medio ---el puesto de mercado, día y noche, la familia y
el propietario que cocina--- cambian de lugar entre sí con facilidad: la diferencia entre ellos es menor que el error de
los supuestos. Leído así, el catálogo no dice cuál de esas cuatro fondas es mejor; dice que las cuatro ganan y
que ganan por razones distintas.
"""}

\subsection{{Lo que el modelo deja ver}}

Más allá de los números de cada caso, el modelo permite hacer preguntas que en la operación diaria no se
hacen. Las que siguen cambian la manera de pensar el negocio. Una advertencia vale para todas: el personal crece
por personas, no de a poco ---un local que vende 71 menús necesita dos mozos y uno que vende 69, uno---, y esos
escalones explican saltos que parecen extraños en cualquier cifra calculada con la planilla automática.

{sup_deja_ver()}
\subsubsection{{El trabajo que no se cobra}}\label{{sec:trabajo}}

La utilidad de una fonda familiar se calcula sin descontar el trabajo de quienes no tienen sueldo, o se pagan
menos de lo que costaría contratarlos. Para que ese trabajo se vea, el estudio usa un segundo indicador de
rentabilidad: la \emph{{utilidad económica}}. Le resta a lo que se lleva la casa lo que valdría su trabajo a precio
de mercado ---el sueldo de una cocinera, un ayudante, un mozo o un administrador de Juliaca por las horas que de
verdad trabajan, con el recargo de ley por las horas extra--- y lo que rendiría la inversión en otro lado, al
15\,\% anual del flujo. Si la utilidad económica es negativa, el negocio no gana: vive de un subsidio de la familia
que lo atiende. Las horas son supuestos razonados (60 por semana para quien cocina, de 20 a 40 para quien solo
administra) y están en el \cuadro{{tab:trabajo}}.

{sup_trabajo()}
\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/trabajo_hora.pdf}}
\caption{{Lo que cobra por hora la gente de la casa (barra) frente a lo que valdría esa hora si se contratara a
alguien (raya) y al sueldo mínimo por hora.}}\label{{fig:trabajo_hora}}
\end{{figure}}

\begin{{table}}[H]
\centering\footnotesize
\caption{{El trabajo de la casa a precio de mercado, en soles al mes. ``Cobra'': parte del valor de su trabajo que
la casa de verdad se lleva.}}\label{{tab:trabajo}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xrrrrrr}}
\toprule
Negocio & Horas/semana & Se lleva & Su trabajo & Capital & Utilidad económica & Cobra \\
\midrule
{tabla_trabajo()}
\bottomrule
\end{{tabularx}}
\end{{table}}

La \figura{{fig:trabajo_hora}} muestra la primera lectura. El propietario que cocina, con 60 horas a la semana, se
lleva {s(tr_('Propietario que cocina', 'por_hora'), 2)} por hora, cuando contratar a una cocinera para esas mismas horas
costaría {s(tr_('Propietario que cocina', 'mercado_por_hora'), 2)}: cobra {n(tr_('Propietario que cocina', 'parte_cobrada'), 1)} veces su
trabajo, porque además del sueldo se queda con el margen del negocio. El negocio familiar sin sueldos, en el mismo local,
no: entre los tres reciben {s(tr_('Familiar sin sueldos', 'por_hora'), 2)} por hora frente a
{s(tr_('Familiar sin sueldos', 'mercado_por_hora'), 2)} de mercado, el {p(tr_('Familiar sin sueldos', 'parte_cobrada'))} de lo que
valdría su trabajo, por debajo del sueldo mínimo por hora. La fonda en casa propia queda justo en el valor de su
trabajo: su propietario gana lo que ganaría como empleado. Y en el inversor, el pequeño en Nuevo RUS y Candela, quien
pone el trabajo de dueño casi no cobra nada por él{"" if 'Candela (datos del POS)' not in trab else rf""" ---en Candela, con las
{n(trab['Candela (datos del POS)']['casa'][0]['horas_semana'] if trab['Candela (datos del POS)']['casa'] else 0)} horas semanales que se le suponen al dueño para compras, caja y
administración, la cuenta es peor: si paga IGV sobre toda la venta, pone su trabajo y además pierde plata"""}.

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/trabajo_economica.pdf}}
\caption{{Lo que se lleva la casa (gris) y la utilidad económica, ya descontado el valor de mercado de su trabajo
y el del capital (color).}}\label{{fig:trabajo_economica}}
\end{{figure}}

La \figura{{fig:trabajo_economica}} cambia el orden de los negocios. Por lo que se lleva la casa, el negocio familiar
sin sueldos es de las que más ganan ({s(tr_('Familiar sin sueldos', 'ingreso'))} al mes); por utilidad económica queda en
{s(tr_('Familiar sin sueldos', 'utilidad_economica'))}: lo que muestra la caja es, casi entero, su propio trabajo. Que quede
por encima o por debajo del valor de mercado no es concluyente{"" if parte_de("La familia recibe menos") is None else " (queda por debajo en el " + p(parte_de("La familia recibe menos")) + " de los sorteos)"}; lo que sí se
sostiene es que cada uno de sus integrantes se lleva menos de la mitad que el propietario que cocina solo. Con la
utilidad económica como medida, solo {y_lista([("la " if corto(t['nombre']).startswith(("Fonda",)) else "el ") + corto(t['nombre'])[:1].lower() + corto(t['nombre'])[1:] for t in sorted(trab.values(), key=lambda t: -t['utilidad_economica']) if t['utilidad_economica'] > 100])}
son negocios rentables en sentido estricto: pagan a su gente lo que vale y todavía les sobra. Ese es el indicador
que debería mirar quien compara una fonda con un empleo: la pregunta no es si el negocio deja plata, sino si
deja más que lo que la misma gente ganaría trabajando para otro.

{"" if not capac else rf"""\subsubsection{{¿Alcanza la gente para lo que se vende?}}\label{{sec:capacidad}}

El modelo arma la planilla a partir de la venta ---más menús, más gente---, pero no se pregunta lo contrario: si
la gente que tiene un negocio alcanza para lo que vende. Candela da la medida. Con tres personas en cocina y tres
mozos aguanta hasta unos S/~1\,100 al día a S/~11, cerca de 100 menús; con dos mozos también, pero sobreexigidos.
Eso es unos 33 menús por persona en cocina y hasta 50 por mozo en su tope. El experimento aplica esa productividad
a todos los negocios: cuenta quiénes están en cocina y en salón al mediodía (incluida la gente de la casa), calcula
cuánto aguantan y, si les falta alguien, le suma su sueldo a la cuenta.

{sup_capacidad()}
\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/capacidad.pdf}}
\caption{{Menús al día que aguanta la gente de cada negocio con la productividad observada en Candela (barra)
y los que vende (punto).}}\label{{fig:capacidad}}
\end{{figure}}

\begin{{table}}[H]
\centering\footnotesize
\caption{{La gente frente a la venta. ``Aguanta'': menús al día con unos 33 por persona en cocina y 50 por mozo, y qué
pone el límite. ``Ajustada'': la utilidad del mes sumando el sueldo de quien falta.}}\label{{tab:capacidad}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xrcrlrr}}
\toprule
Negocio & Vende & Gente & Aguanta & Falta & Utilidad & Ajustada \\
\midrule
{tabla_capacidad()}
\bottomrule
\end{{tabularx}}
\end{{table}}

La \figura{{fig:capacidad}} y el \cuadro{{tab:capacidad}} muestran dos grupos. A
{len([c for c in capac.values() if c['costo_falta'] > 0])} negocios les falta gente para lo que se les supone que venden. El inversor que
supervisa es el caso que importa para Candela: la planilla automática le pone dos personas en cocina para
{n(capac['Inversor que supervisa']['q'])} menús, que con la productividad de Candela sacan unos
{n(capac['Inversor que supervisa']['tope_cocina'])}. Con el ayudante que le falta, su utilidad pasa de
{s(capac['Inversor que supervisa']['utilidad'])} a {s(capac['Inversor que supervisa']['utilidad_ajustada'])}: buena parte de su
ventaja sobre Candela era gente que la cuenta no pagaba. El exitoso, con {n(capac['Exitoso (referencia compuesta)']['q'])}
menús, necesitaría {capac['Exitoso (referencia compuesta)']['falta_cocina'] + capac['Exitoso (referencia compuesta)']['falta_salon']}
personas más a ese ritmo; el puesto de mercado, con un solo puesto de atención para {n(capac['Puesto de mercado informal']['q'])}
menús, también queda corto, aunque en un mostrador se despacha más rápido que en mesa y su falta está exagerada. El
propietario que cocina y el negocio familiar, con un solo mozo para {n(capac['Propietario que cocina']['q'])} menús, quedan
apenas sobre el tope: o contratan a alguien más o trabajan sobreexigidos, que es otra forma del trabajo no
cobrado de la sección anterior.
{"" if 'Candela (datos del POS)' not in capac else rf"""
Candela está en el otro grupo. Con {capac['Candela (datos del POS)']['cocina']} en cocina y {capac['Candela (datos del POS)']['salon']} en
salón aguanta {n(capac['Candela (datos del POS)']['tope'])} menús y vende {n(capac['Candela (datos del POS)']['q'])}: tiene sitio
para {n(capac['Candela (datos del POS)']['holgura'])} menús más al día sin contratar a nadie. Venderlos a S/~11 le dejaría
{s(capac['Candela (datos del POS)']['valor_holgura'])} más al mes, porque la planilla, el alquiler y el gas ya están pagados y
cada menú extra solo cuesta sus insumos. Esa es la respuesta a por qué rinde menos que el inversor: no le falta
capacidad, le sobra. Paga a la gente de un local de {n(capac['Candela (datos del POS)']['tope'])} menús y vende {n(capac['Candela (datos del POS)']['q'])}. Su cuello de botella no es la cocina
sino la demanda del mediodía, y lo que más la acercaría al inversor es llenar esa capacidad (pensionistas,
pedidos para llevar, convenios con oficinas) antes que mover el precio; si la demanda no crece, la otra salida
es ordenar la cocina para trabajar con una persona menos (\seccion{{sec:cocina}})."""}

Una advertencia: los 33 menús por persona son los de la cocina de Candela tal como trabaja hoy. La planilla
automática del modelo supone hasta 80 por persona, propio de cocinas grandes con estaciones y todo picado de
antemano. La distancia entre esas dos cifras depende de cómo se organiza la cocina, que es el tema de la
\seccion{{sec:cocina}}.

"""}
\subsubsection{{La trampa del Nuevo RUS}}

La \figura{{fig:nrus}} sigue a un local chico a medida que crece. Mientras vende hasta {nr.get('q_tope')}
menús diarios cabe en el Nuevo RUS: no cobra IGV y paga una cuota fija. Al pasar el tope de S/~96 mil al año
tiene que cambiar de régimen y empezar a cobrar IGV, y su utilidad cae de golpe de {s(nr.get('nrus_tope', 0))}
a {s(nr.get('rer_justo_despues', 0))} al mes. Para volver a ganar lo mismo que antes del salto tiene que llegar a
unos {nr.get('q_recupera')} menús diarios. El régimen castiga el crecimiento justo en el tramo en que un negocio
chico intenta despegar; no es raro que muchos prefieran quedarse chicos, declarar menos de lo que venden o salir de
la formalidad (\seccion{{sec:evidencia}}).

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/nrus.pdf}}
\caption{{Un local chico que crece: utilidad después de impuestos en el Nuevo RUS (hasta su tope) y en el RER.
La flecha es el salto al pasar el tope.}}\label{{fig:nrus}}
\end{{figure}}

\subsubsection{{Desde cuántas cenas conviene la noche}}

El barrido mostró que la noche mejora a todos los negocios; la pregunta práctica es desde qué volumen. Si la
noche exige un equipo propio, conviene desde unos {noche_u['Inversor que supervisa']['umbral']} platos por noche
en el local promedio{"" if not cand else f" (y {noche_u['Candela (datos del POS)']['umbral']} en Candela)"}. Si la
atienden las mismas personas del día ---el propietario, la familia---, conviene desde
{umbral_familiar} platos por noche: casi cualquier venta.
Pero esa cuenta no cobra las horas extra de esas personas; es el mismo trabajo no pagado de la sección
anterior, ahora de noche. La decisión honesta compara las cenas que se venderían con el costo de un equipo
nocturno, aunque al principio lo cubra la familia.

\subsubsection{{¿Casa propia o local alquilado?}}

Muchas fondas abren en la casa de la familia y no pagan alquiler. La pregunta es si eso las hace más rentables
que un local alquilado. El modelo la responde traduciendo el alquiler a menús: el local del propietario que cocina
paga S/~1\,200, que equivalen a vender {n(next(a['menus'] for a in hz['alquiler'] if a['nombre'] == 'Propietario que cocina'))}
menús diarios; el del inversor, S/~2\,200, equivale a {n(next(a['menus'] for a in hz['alquiler'] if a['nombre'].startswith('Inversor')))}.
Abrir en casa conviene mientras la casa pierda menos clientes que esos menús. La fonda en casa propia del
catálogo, con 45 menús a S/~9, deja {s(casos['Fonda en casa propia']['ingreso_dueno'])} al mes a su propietario, frente a
{s(dc['ingreso_dueno'])} del propietario que cocina en un local alquilado con 60 menús a S/~10: el paso de la calle vale
más que el alquiler que se ahorra. Dos costos escondidos completan la cuenta. Primero, la casa tiene un costo
de oportunidad: el espacio podría alquilarse. Segundo, la luz, el agua y el gas se mezclan con los del hogar, y
el negocio parece más barato de lo que es.

{"" if not co else rf"""\subsection{{La organización de la cocina}}\label{{sec:cocina}}

Muchas fondas cocinan como se cocina en casa: cada quien se encarga de sus platos de principio a fin y todo
empieza en crudo la misma mañana ---las arvejas sin desvainar, la papa sin pelar, la cebolla entera---. La
hipótesis de esta sección es que organizarse de otra forma rinde más con la misma gente, y que eso depende de la
organización y no de la formalidad: una fonda familiar puede organizarse igual que un restaurante con planilla.
Para ponerla a prueba se usa la simulación descrita en la \seccion{{sec:sim_cocina}}, con las cuatro formas de
trabajar y los supuestos de los cuadros~\ref{{tab:prep}} a~\ref{{tab:servicio}}.

\subsubsection{{Cinco días de cocina}}

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth,height=0.78\textheight,keepaspectratio]{{fig/gantt.pdf}}
\caption{{Un día de cocina para {n(co['q'])} menús en cada organización. Cada fila es una persona; las barras, el
trabajo según su puesto, y la raya fina, el tiempo en que la olla cocina sola. Con mise en place, la tarde deja lista la
mañana siguiente. La gente entra lo justo para tener todo listo un cuarto de hora antes del almuerzo.}}\label{{fig:gantt}}
\end{{figure}}

La \figura{{fig:gantt}} muestra un día con la venta actual de Candela. En la cocina doméstica, tres personas
necesitan {n((gd['listo'] - gd['inicio']) / 60, 1)} horas de mañana y {n(gd['trabajo_manana'] / 60, 1)} horas-persona de
trabajo antes del almuerzo; pelar la papa, solo eso, se lleva
{n(next(t for t in co['tareas'] if t['id'] == 'papa')['var'] * co['q'] / 100 / 60, 1)} horas. \emph{{Por bloques}}, el trabajo baja a
{n(gb['trabajo_manana'] / 60, 1)} horas-persona ---es el tiempo fijo de preparar una vez en lugar de tres--- y la
mañana a {n((gb['listo'] - gb['inicio']) / 60, 1)} horas. Con \emph{{mise en place}}, {n(gm3['trabajo_tarde'] / 60, 1)}
horas-persona pasan a la tarde anterior y la mañana se reduce a {n((gm3['listo'] - gm3['inicio']) / 60, 1)} horas, casi
todas de cocción. El trabajo total casi no cambia: lo que cambia es \emph{{cuándo}} se hace. Y \emph{{por estaciones}}
el reparto queda ordenado por puestos, con el de verduras como el más cargado.

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/cola.pdf}}
\caption{{Minutos que espera por su plato el cliente que llega en cada momento del almuerzo, con {n(co['q'])} menús al
día y los pedidos repartidos como en el POS de Candela.}}\label{{fig:cola}}
\end{{figure}}

El almuerzo es la otra mitad. El {p(punta)} de los pedidos del día llega entre la 1 menos cuarto y las dos menos
cuarto, y en esa hora la cocina tiene que despachar a su máximo ritmo (\figura{{fig:cola}}). Con tres personas
trabajando como en casa, Candela atiende sus {n(co['q'])} menús sin colas; con dos, la espera llega a
{n(cola_('domestico', 2)['espera_maxima'])} minutos en la hora punta ---el colapso que Candela conoce---. Por bloques
baja a {n(cola_('bloques', 2)['espera_maxima'])}, con mise en place a {n(cola_('mise', 2)['espera_maxima'])} y por
estaciones a {n(cola_('estaciones', 2)['espera_maxima'])}: con dos puestos fijos para tres trabajos, uno queda sobrecargado.

\subsubsection{{Cuántos menús aguanta cada organización}}

\begin{{table}}[H]
\centering\small
\caption{{Menús al día que aguanta la cocina según cómo trabaja y cuánta gente tiene, y horas-persona al día que pasa en
el local con {n(co['q'])} menús y tres personas. Entre paréntesis, lo que pone el límite: la mañana o el almuerzo.}}\label{{tab:org}}
\begin{{tabular}}{{lrrrr}}
\toprule
Organización & 2 personas & 3 personas & 4 personas & Horas-persona (3) \\
\midrule
{tabla_org()}
\bottomrule
\end{{tabular}}
\end{{table}}

El \cuadro{{tab:org}} resume el experimento. Con tres personas, la cocina doméstica aguanta
{n(cap_('domestico', 3)['tope'])} menús; por bloques, {n(cap_('bloques', 3)['tope'])}; con mise en place,
{n(cap_('mise', 3)['tope'])}, y por estaciones, {n(cap_('estaciones', 3)['tope'])}: de unos {n(cap_('domestico', 3)['tope'] / 3)}
menús por persona a {n(cap_('estaciones', 3)['tope'] / 3)}. El salto grande es el del mise en place, porque saca la
preparación de la mañana y el desorden del almuerzo. Las estaciones suman poco y solo con tres personas, cuando cada
puesto tiene a alguien; con dos o con cuatro, un puesto fijo deja a alguien sobrecargado o esperando. Es una forma de
ordenar el almuerzo, no un reemplazo del mise en place. La doméstica tiene además un techo propio: como cada persona
hace sus platos, agregar gente no acorta la mañana, y con cuatro personas ya no es el almuerzo sino la mañana la que
limita.

El orden de las organizaciones no depende de qué tan rápida sea la gente. Con una cocina un 40\,\% más rápida
que la supuesta, tres personas aguantan {n(vel_(0.6, 'topes', 'domestico'))} menús en doméstico y
{n(vel_(0.6, 'topes', 'mise'))} con mise en place ---igual que antes, porque el límite sigue siendo el almuerzo---; con
una un 50\,\% más lenta, {n(vel_(1.5, 'topes', 'domestico'))} y {n(vel_(1.5, 'topes', 'mise'))}. La velocidad de la
gente mueve las cifras cuando la mañana es el límite; la ventaja de organizarse se mantiene en todos los casos.

\subsubsection{{Dónde se ahorra en cada negocio}}

El mismo experimento se repitió para todos los negocios, cada uno con su venta y su gente (\cuadro{{tab:org_neg}}).
Para cada organización se buscó la menor cantidad de personas en cocina que tiene todo listo a tiempo y atiende la hora
punta sin pasar los {co['servicio']['espera_maxima']} minutos de espera; el ahorro compara su planilla de cocina ---con
las horas extra si la jornada pasa de ocho--- con la de la cocina doméstica.

\begin{{table}}[H]
\centering\footnotesize
\caption{{Organización de la cocina en cada negocio: personas en cocina que necesita para su venta con cada forma de
trabajar, el mayor ahorro al mes frente a la doméstica (planilla con horas extra) y los menús que aguantaría con la
gente que tiene hoy, en doméstico y con mise en place. ``--'': ninguna cantidad de gente alcanza.}}\label{{tab:org_neg}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}Xrrccccrrr}}
\toprule
& & & \multicolumn{{4}}{{c}}{{Necesita}} & & \multicolumn{{2}}{{c}}{{Aguanta}} \\
\cmidrule(lr){{4-7}}\cmidrule(lr){{9-10}}
Negocio & Vende & Tiene & Dom. & Bloq. & Mise & Est. & Ahorro & Dom. & Mise \\
\midrule
{tabla_org_negocios()}
\bottomrule
\end{{tabularx}}
\end{{table}}

La lectura cambia según el tamaño. En los negocios que ya trabajan con lo mínimo
---{y_lista([corto(f['nombre']).lower() for f in orgs if f['modos']['domestico']['necesita'] and not any((f['modos'][m]['ahorro'] or 0) > 0 for m in NOMBRE_ORG)])}---,
organizarse no ahorra gente: la necesitan igual para el almuerzo. Ahí el mise en place
cuesta, porque la tarde alarga el día y se paga como sobretiempo; lo que compra es capacidad para crecer sin
contratar. En los demás, agrupar o adelantar la preparación permite trabajar con una persona menos de la que
exigiría la cocina doméstica y ahorrar unos {s(min(x for x in ahorros_pos))} a {s(max(x for x in ahorros_pos))} al mes, aun pagando las horas
extra. Y en los de mucho volumen ---el puesto de mercado, el exitoso--- la cocina doméstica ni siquiera es posible:
cuando cada uno hace su plato, la mañana no alcanza con ninguna cantidad de gente.
{"" if not org_c else rf"""
En Candela, con {org_c['cocina']} personas en cocina para {n(org_c['q'])} menús, la cocina doméstica necesita a las tres.
{'Por bloques' if org_c['modos']['bloques']['necesita'] < org_c['cocina'] else 'Con mise en place'} alcanzan
{min(org_c['modos'][m]['necesita'] for m in ('bloques', 'mise'))}, con jornadas de
{n(org_c['modos'][mejor_c]['horas'], 1)} horas, y el ahorro neto sería de unos \textbf{{{s(org_c['modos'][mejor_c]['ahorro'])} al
mes}}. Con las tres personas, en cambio, el mise en place le daría sitio para {n(org_c['modos']['mise']['tope'])} menús al
día: es la misma conclusión de la \seccion{{sec:capacidad}} vista desde la cocina. Lo que le falta a Candela no es
gente sino clientes, y organizarse la deja elegir entre trabajar con menos o tener con qué crecer."""}

\subsubsection{{Qué falta medir}}

Las velocidades salen del dueño de Candela, de una tabla de la industria y de estimaciones; las cantidades de cebolla y
ajo, de un supuesto; y lo que la organización recorta del desorden del almuerzo es el supuesto más fuerte de la sección.
Lo medido es cuándo llegan los pedidos y cuántos menús aguanta Candela hoy. Dos o tres mañanas cronometradas en su
cocina ---a qué hora entra cada persona, qué hace, cuánto le toma y a qué hora está todo listo--- reemplazarían los
cuadros~\ref{{tab:prep}} y~\ref{{tab:coccion}} por datos propios. Y probar una semana trabajando por bloques, con la
misma gente, contestaría la pregunta de fondo con un experimento de verdad.

"""}
\subsection{{El largo plazo: diez años y cuatro regímenes}}

Los supuestos del flujo (tasa, inflación, ajuste de precio, regímenes) están en el \anexo{{sec:anexo}}.

La \figura{{fig:flujo}} sigue la caja acumulada de siete negocios desde la inversión inicial hasta 2035.
Las líneas se separan pronto y no se vuelven a cruzar: el que empieza ganando sigue ganando, y el que
empieza perdiendo no se recupera solo con el tiempo, porque la inflación de costos y el sueldo mínimo suben
al ritmo del precio y el IGV de 2027--2028 empuja hacia abajo.

\begin{{figure}}[H]
\centering
\includegraphics[width=0.9\textwidth]{{fig/flujo.pdf}}
\caption{{Caja acumulada después de la inversión, régimen de cada caso. Las líneas verticales marcan los saltos
del IGV.}}\label{{fig:flujo}}
\end{{figure}}

El régimen tributario cambia la cuenta de manera decisiva (\figura{{fig:regimenes}}). Con los mismos
supuestos, el inversor tendría un VAN de {s(reg(inv, 'informal')['van'])} en la informalidad y de
{s(reg(inv, 'mype')['van'])} en el régimen MYPE. La diferencia no es la renta ---a estos niveles de utilidad
el impuesto a la renta es pequeño--- sino el IGV y las cargas laborales. Por eso la formalización de una
fonda es, ante todo, una decisión sobre el IGV: a 10.5\,\% es soportable; a 18\,\% exige vender bastante más
o cobrar más. El Nuevo RUS aparece atractivo en el gráfico para varios casos, pero con barras rayadas: ninguno
de ellos cabe en su tope de ventas.

\begin{{figure}}[H]
\centering
\includegraphics[width=0.94\textwidth]{{fig/regimenes.pdf}}
\caption{{VAN a diez años según el régimen. Rayado: el negocio supera el tope de ventas del régimen y no
podría acogerse a él.}}\label{{fig:regimenes}}
\end{{figure}}

Hay una lectura menos evidente en la fila de la familia. Formalizada, su VAN se vuelve negativo
({s(reg(fam, 'mype')['van'])} en el régimen MYPE): al pasar a planilla, la ley obliga a pagar al menos el
sueldo mínimo a quienes antes trabajaban sin cobrar. La informalidad de la fonda familiar no es solo evasión
de impuestos; es la forma jurídica de un acuerdo familiar que la ley laboral no reconoce.

\subsection{{Registro de experimentos}}\label{{sec:experimentos}}

Cada variación de este estudio es un experimento: se fija todo, se cambia una cosa y se mira qué pasa. El
\cuadro{{tab:experimentos}} los reúne con la pregunta que contestan, lo que se varió, el resultado y un
veredicto. Donde el resultado depende de los números supuestos de los restaurantes tipo, el veredicto sale de
los sorteos de la \seccion{{sec:supuestos}}. Las conclusiones del ensayo son las filas que se sostienen; las
demás quedan como preguntas abiertas.

\begin{{table}}[H]
\centering\footnotesize
\caption{{Registro de experimentos: pregunta, qué se varió, resultado y veredicto.}}\label{{tab:experimentos}}
\renewcommand{{\arraystretch}}{{1.08}}\scriptsize
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{r>{{\raggedright\arraybackslash}}p{{0.2\textwidth}}>{{\raggedright\arraybackslash}}p{{0.2\textwidth}}>{{\raggedright\arraybackslash}}X>{{\raggedright\arraybackslash}}p{{0.15\textwidth}}}}
\toprule
& Pregunta & Qué se varió & Resultado & Veredicto \\
\midrule
{tabla_experimentos()}
\bottomrule
\end{{tabularx}}
\end{{table}}

\section{{Discusión}}

Los {NN} negocios cuentan una sola historia desde ángulos distintos. En todos los casos los insumos se llevan
alrededor de la mitad de la venta neta. Eso hace del costo del plato el renglón más grande, pero no un dato
fijo: la mezcla de segundos, la porción y las compras lo mueven lo bastante como para decidir un negocio de
margen fino ---es lo que separa al puesto de mercado y la palanca principal de Candela---. Aun así, lo que más
distingue a un negocio de otro son tres decisiones:

\begin{{enumerate}}[leftmargin=1.4em]
\item \textbf{{Quién pone el trabajo.}} La fonda rentable en provincia es, en su forma más común, el empleo de
su propietario o de su familia. Un local que contrata a todos necesita volúmenes de ciudad grande o precios que la
clientela local no paga; uno que además terceriza la gestión necesita más del doble del volumen. Antes de
abrir, la pregunta útil no es ``¿es rentable el menú?'' sino ``¿quién va a estar en la cocina y en la caja?''.
\item \textbf{{Cuántos menús por cada sol de alquiler.}} El volumen diluye los costos fijos, y el turno noche
multiplica las horas que rinde el mismo local. Una ubicación con flujo de gente vale más que una ubicación
barata.
\item \textbf{{Cómo se paga el IGV.}} La formalidad cuesta, y el calendario la encarece: el 2028 es un horizonte
cercano para quien invierte hoy. Los planes a diez años deberían suponer un IGV de 18\,\% salvo que una nueva
ley diga lo contrario.
\end{{enumerate}}

La simulación de la cocina agrega una cuarta decisión, que no depende de la formalidad ni del local:
\emph{{cómo se organiza el trabajo}}. Una cocina que prepara de una vez lo que usan varios platos y adelanta a la
tarde lo que aguanta rinde un tercio más con la misma gente. No ahorra horas ---las cambia de momento---, pero
permite elegir entre trabajar con una persona menos o crecer sin contratar. Es la palanca más barata del
estudio: no cuesta plata, cuesta orden.

El exitoso confirma la regla por el otro lado: gana mucho porque vende mucho, no porque su plato sea más
barato ni su cocina más eficiente. Su riesgo es el de cualquier negocio grande: necesita años para llenarse,
más inversión y una administración que el dueño ya no puede hacer solo.

\subsection{{Los hallazgos frente a la evidencia}}\label{{sec:evidencia}}

Un modelo puede ser coherente y estar equivocado. Para saber cuánto de lo encontrado se sostiene fuera del
modelo, se buscó evidencia publicada sobre cada hallazgo principal: no para adornarlo, sino para ver si lo
confirma, lo matiza o lo contradice. El \cuadro{{tab:evidencia}} resume el resultado; los párrafos que siguen lo
explican. Donde no se encontró nada sólido, se dice.

\begin{{table}}[H]
\centering\footnotesize
\caption{{Los hallazgos del estudio frente a la evidencia publicada.}}\label{{tab:evidencia}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}p{{0.25\textwidth}}>{{\raggedright\arraybackslash}}X>{{\raggedright\arraybackslash}}p{{0.14\textwidth}}}}
\toprule
Hallazgo & Lo que dice la evidencia & Veredicto \\
\midrule
Gana el trabajo, no el capital & Los independientes urbanos del Perú ganan cerca de la mitad que los asalariados; el INEI encuentra que la microempresa sobrevive gracias al trabajo familiar no remunerado; los experimentos con microempresas muestran que el capital sí rinde, pero que la mayoría de dueños se parece más a un asalariado que a un empresario & confirma, con matiz \\
La clientela de un local es muy sensible al precio ($\varepsilon\approx2.4$) & La comida fuera de casa como categoría tiene 0.8; la de restaurantes con servicio, cerca de 2; la de una marca o un puesto individual, entre 2 y 4 & confirma el orden de magnitud \\
El precio lo fija la referencia de la cuadra & Prensa de 2026: un menú que subió de S/~10 a S/~12 frente a vecinos de S/~6--8 perdió buena parte de su clientela; pero cuando el costo sube para todos, el índice de precios del menú sube para todos & confirma, con matiz \\
Margen fino y apalancamiento alto & La utilidad mediana de los restaurantes en EE.~UU. es de 3 a 4\,\% de la venta; uno de cada cuatro independientes cierra el primer año & confirma \\
Insumos de 40 a 57\,\% de la venta & En restaurantes de EE.~UU. y en guías peruanas, 30 a 35\,\% & difiere; se explica \\
El IGV reducido y su calendario & Tasas confirmadas por ley; el MEF sostiene que la rebaja no formalizó & confirma \\
El tope del Nuevo RUS castiga crecer & Los negocios reaccionan al tope, pero sobre todo declarando menos & matiza \\
Organizar la cocina da capacidad & En comedores, preparar fuera del servicio sube las comidas por hora-hombre de 20 a 25\,\%; agrupar en lotes puede ahorrar horas & confirma; matiza las horas \\
La hora punta decide la capacidad & En un comedor peruano, la cola se forma en los primeros 20 minutos aunque el promedio parezca holgado & confirma \\
Cocinar en altura cuesta más & Las cocinas a gas pierden 0.56\,\% de potencia por cada 100~m; no hay mediciones de gas por plato & confirma la dirección \\
\bottomrule
\end{{tabularx}}
\end{{table}}

\paragraph{{El trabajo y el capital.}} La tesis central del capítulo ---que la fonda rentable es, sobre todo, el
empleo de su dueño o de su familia--- tiene respaldo directo en el Perú. Un estudio del INEI con la ENAHO describe
las unidades de menos de cinco trabajadores como negocios para los que ``la abundancia del trabajo familiar no
remunerado parece ser el medio que permite la sobrevivencia'', algunos ``con nula capacidad de generar
excedentes'' (Gamero, 2012). Los independientes urbanos ganaban en promedio unos S/~930 al mes entre 2017 y
2021, cerca del sueldo mínimo de entonces, y los trabajadores de alojamiento y restaurantes, el 65\,\% del ingreso
medio del país. Fuera del Perú, la literatura sobre microempresas llega a lo mismo: la mayoría de sus dueños se
parece más a un asalariado que a un empresario, y abaratar su registro no los hace crecer (La~Porta y Shleifer,
2014). Hay un matiz importante: los experimentos que regalan capital a microempresas encuentran retornos altos al
capital adicional (de~Mel, McKenzie y Woodruff, 2008). Lo que el estudio sostiene, entonces, no es que el capital
no rinda, sino que en una fonda el excedente que queda \emph{{después de pagar el trabajo}} es chico, y que el
inversor que paga todo el trabajo a precio de mercado compite contra hogares que no lo hacen.

\paragraph{{El precio.}} La sensibilidad de {n(pc['elasticidad_ajuste'], 1) if pc else "2.4"} que muestra la historia de Candela parece alta
frente a la elasticidad de la comida fuera de casa como categoría, que un metaanálisis de 160 estudios ubica en
0.81 (Andreyeva, Long y Brownell, 2010). Pero no se mide lo mismo: cuando todos los locales suben a la vez, el
cliente no tiene adónde ir; cuando sube uno solo, se va a la cuadra de al lado. Por eso la elasticidad de un
restaurante con servicio en Estados Unidos ronda 2 (Okrent y Alston, 2012) y la de una marca individual, 2.6 en
promedio (Bijmolt, van Heerde y Pieters, 2005). Un 2.4 para un local de menú con competencia cerca es plausible.
La prensa de 2026 muestra el mecanismo: en un mercado de Lima, un menú que subió de S/~10 a S/~12 por el precio
del gas, con locales vecinos a S/~6--8, perdió buena parte de su clientela según sus propios comerciantes. Y
muestra también el límite del argumento: cuando el costo sube para todos, la referencia se mueve, y el índice de
precios del menú en Lima subió 11\,\% en 2022. Dos advertencias sobre la cifra de Candela: sus tres precios son
de épocas distintas, y entre ellas el resto de los menús de la ciudad también subió, de modo que la sensibilidad
frente a la competencia podría ser mayor que la medida; y es un solo local.

\paragraph{{La estructura de costos.}} El margen fino del modelo coincide con lo que se mide en otras partes: la
utilidad antes de impuestos mediana de los restaurantes de Estados Unidos es de 2.8\,\% en los de servicio completo y
4\,\% en los de servicio rápido (National Restaurant Association, 2025), y uno de cada cuatro restaurantes
independientes cierra en su primer año (Parsa y otros, 2005). La composición de los costos, en cambio, es distinta:
el modelo pone los insumos en 40 a 57\,\% de la venta neta, cuando en restaurantes de Estados Unidos rondan el
30--35\,\% y las guías comerciales peruanas proponen lo mismo. La diferencia tiene explicación: el menú popular
vende un plato completo con proteína a un precio bajo y sin bebidas de alto margen, y su personal pesa mucho menos
que en un restaurante con planilla ---en la fonda familiar, casi nada---. Pero es una diferencia que conviene
verificar con la Encuesta Económica Anual del INEI para restaurantes, que tiene la estructura de costos del sector
y este estudio no ha procesado.

\paragraph{{La formalidad.}} Las tasas del IGV de restaurantes que usa el modelo están en la ley: 8\,\% de IGV más
2.5\,\% de impuesto de promoción municipal en 2026 y 12\,\% más 3\,\% en 2027 (Leyes 32219 y 32387); para 2028 no hay
tasa especial. El propio MEF ha sostenido que la rebaja no formalizó a nadie y que su beneficio se concentró en los
restaurantes que más venden, y un experimento en el Cercado de Lima encontró que solo una de cada cuatro
microempresas informales aceptaba un incentivo para sacar su licencia, por los costos que vienen después (GRADE,
2012). Ambos datos refuerzan la lectura del estudio: a los precios del menú, la formalidad no es un trámite sino un
costo que muchos negocios no pueden pagar. Sobre el Nuevo RUS, la evidencia matiza: cuando en 2017 se eliminaron
sus categorías más altas, la mitad de los negocios afectados pasó a \emph{{declarar}} ventas menores en lugar de cambiar
de régimen (Azuero, Bosch y Lagomarsino). La ``trampa'' del tope existe, pero su efecto más visible no es que los
negocios dejen de crecer sino que dejen de declarar lo que crecen.

\paragraph{{La cocina.}} No hay estudios de productividad de fondas ni de menús, así que la comparación es con
análogos. En comedores escolares de hasta cien raciones, una cocina convencional produce de 8 a 10 comidas por
hora-hombre, y una que recibe parte del trabajo ya hecho, de 10 a 12 (Institute of Child Nutrition, 2014): de 20 a
25\,\% más, del mismo orden que lo que el modelo atribuye al mise en place. Sobre las horas, la evidencia está
dividida: en hospitales, cambiar a sistemas de producción anticipada no redujo costos laborales (Greathouse y otros,
1989), pero en un restaurante japonés cocinar por lotes sí redujo horas, a cambio de desacoplar el trabajo de la
demanda y con un periodo de aprendizaje de unos dos meses en que la cocina rindió menos (Shimmura y otros, 2017,
2018). La conclusión del estudio ---el mise en place compra capacidad, no horas--- vale para mover la misma tarea
a otra hora; agrupar tareas iguales probablemente ahorra algo más de lo que el modelo calcula. La importancia de la
hora punta tiene un ejemplo cercano: en el comedor de una universidad de Huaraz, el servicio parecía holgado con
el promedio del almuerzo, pero en los primeros veinte minutos llegaba seis veces más gente de la que podía atender y
se formaban colas de más de ochenta personas. Y la altura cuesta: las cocinas a gas probadas entre 2\,300 y 4\,150
metros pierden 0.56\,\% de potencia por cada 100~m, unos 20\,\% en Juliaca, aunque no hay mediciones de cuánto gas
más gasta un plato.

Lo que queda sin contraste externo es justamente lo más propio del estudio: los números de Candela, la sensibilidad de
la clientela de Juliaca y la productividad de su cocina. Para esos tres, la única evidencia posible es la que el
propio local puede generar: la que proponen las recomendaciones.

\subsection{{La paradoja del inversor}}

Visto desde afuera, el menú parece un buen negocio: todos los días hay clientela, la caja se mueve en
efectivo y la inversión es modesta. El modelo explica por qué esa impresión engaña a quien solo pone capital.
Lo que la fonda familiar muestra como utilidad es, en buena parte, el sueldo de sus integrantes; quien compra
esos mismos trabajos en el mercado laboral descubre que el margen se lo llevaba la familia. El inversor no
compite contra otro inversor: compite contra hogares que aceptan cobrar menos que el mínimo por su tiempo. Por
eso, en una plaza como Juliaca, la inversión que no trae su propio trabajo necesita algo que el hogar no tiene:
escala, un precio más alto sostenido por una marca o un segundo turno que reparta los costos fijos.

\subsection{{¿Está barato el menú?}}

Una versión anterior de este ensayo concluía que sí: con una clientela supuesta poco sensible, casi todos los
negocios ganaban subiendo el precio. La historia de Candela desmiente ese supuesto, y la explicación de fondo
sobrevive con más fuerza. El precio del menú no lo fija el costo sino la referencia: el cliente compara con la
pizarra de la cuadra, y la cuadra la marcan locales informales que no pagan IGV ni cargas y que, como se vio,
cobran su trabajo por debajo del mínimo. Cuando hay un sustituto a una cuadra, cada sol de más se pierde en
clientes; una sensibilidad cercana a 2.4 es justamente lo que se espera de un precio fijado por la referencia. El
menú no está barato respecto de lo que el cliente aguanta: está barato respecto de lo que cuesta producirlo con
sueldos y tributos en regla. Un local formal que acepta ese precio hereda un subsidio que no puede pagar. La
salida no es subir la pizarra ---la referencia castiga al que se sale de ella--- sino separarse de la
comparación: segundos con recargo, platos que no tengan equivalente en la cuadra, servicio más rápido para el
trabajador con poco tiempo.

\subsection{{Formalidad y política pública}}

Los resultados ayudan a entender por qué la formalización avanza tan despacio en el sector. Para el negocio
chico, el Nuevo RUS es un techo que castiga crecer; para el mediano, el IGV de restaurantes subirá de 10.5\,\% a
15\,\% y, sin una ley nueva, a 18\,\%; para la fonda familiar, formalizarse obliga a pagar sueldos que hoy no
existen. Cada uno de esos tramos hace racional quedarse afuera. Una política que quiera formalizar el menú
tendría que suavizar los saltos ---un tránsito gradual entre regímenes, una tasa de IGV que no suba de golpe---
antes que endurecer la fiscalización, porque el modelo sugiere que, a los precios actuales, una parte del
sector simplemente no cabe en la formalidad.

\subsection{{El valor de saber}}

El análisis de sensibilidad y el barrido coinciden en qué datos mueven más las conclusiones: la reacción de la
clientela al precio, la demanda nocturna y, para un local concreto, su alquiler y su planilla. Ninguno es caro de
averiguar. Un alza de medio sol medida durante dos semanas estima la elasticidad mejor que cualquier supuesto;
un piloto de tres noches por semana mide la demanda nocturna; el alquiler y la planilla ya los conoce el dueño.
Antes de invertir en cualquier cambio grande, conviene invertir en esas tres mediciones.

\section{{Recomendaciones}}

Para Candela, en orden de impacto:

\begin{{enumerate}}[leftmargin=1.4em]
\item \textbf{{Bajar el costo del plato antes que tocar el precio.}} Los insumos se llevan más de la mitad de la
venta neta. Pesar durante una semana las porciones de los cinco segundos más vendidos, comprar la proteína por
volumen y servir más segundos de pollo, chancho o pasta que de res ataca el renglón más grande sin que la
clientela lo note: cada segundo de res que se cambia ahorra entre S/~0.50 y S/~1.50.
\item \textbf{{Dejar el precio en S/~11 y probar un especial a S/~15.}} Con la sensibilidad que muestra su
historia, subir o bajar el menú apenas cambia la utilidad, y bajarlo devuelve a la cocina al colapso de los S/~10. Lo
que sí vale la pena medir es la otra punta: un segundo especial a S/~15 junto al menú de siempre, para saber cuánta
gente paga más por un plato mejor ahora que el local ya es conocido.
\item \textbf{{Dejar el IGV para su propio análisis.}} Candela emite boleta solo cuando se la piden, así que el IGV
que de verdad paga está entre los dos extremos de este estudio: entre dejarle {s(pc['sin_igv'] + 1500)} al dueño y
perder {s(-(cand['utilidad_mes'] + 1500))} al mes. Cuánto se acerca a uno u otro depende de una situación tributaria
que este estudio no revisa y que conviene ver aparte, con un contador.
\item \textbf{{Llenar la capacidad que ya se paga.}} La cocina y el salón aguantan unos 100 menús y se venden
74. Pensionistas, pedidos para llevar o convenios con oficinas cercanas convierten esa holgura en utilidad, porque
cada menú extra solo cuesta sus insumos.
\item \textbf{{Probar una semana trabajando por bloques.}} Preparar de una vez lo que usan varios platos ---toda la
cebolla, toda la papa--- y, si alcanza la tarde, dejar listo lo que aguanta para el día siguiente. Con la misma gente
da holgura en la hora punta; con una persona menos, ahorra planilla. Medir antes y después a qué hora está todo
listo y cuánto espera la gente en la hora punta.
\item \textbf{{Cuidar el alquiler de conocido.}} Vale S/~1\,000 al mes. Un contrato por escrito con plazo
largo lo protege.
\item \textbf{{Ponerle precio al trabajo del dueño.}} Hoy el dueño hace las compras y administra sin que el negocio
le pague. Cualquier mejora debería medirse por cuánto le deja a él, no solo por si el local cubre sus costos.
\item \textbf{{Prepararse para el IGV de 2027.}} El paso a 15\,\% le quita unos S/~0.40 por menú. Llegar a ese año
con el costo del plato ya ajustado es la forma de absorberlo sin subir el precio.
\end{{enumerate}}

\section{{Limitaciones y próximos pasos}}

El modelo es tan bueno como sus datos, y varios son todavía supuestos. Los precios de menú fuera de Lima,
Cusco y Puno son estimados; los restaurantes tipo son construcciones razonadas, no locales observados; el
exitoso es una referencia compuesta; la simulación supone que las variables se mueven de forma
independiente; el flujo no arrastra pérdidas tributarias ni asigna valor residual al local al décimo año; las
elasticidades de demanda de los restaurantes tipo, el efecto de la porción y la noche tipo del barrido son
supuestos. La sensibilidad de Candela sale de tres precios en tres épocas distintas ---la apertura,
con su arranque, y dos cambios de precio que coincidieron con otros cambios---, y debería confirmarse con una
prueba controlada. En Candela, las recetas se calibraron con las notas de compra y las cantidades semanales que
declara el dueño, no con un pesaje sistemático, y el IGV que de verdad paga no se conoce, porque emite boleta
solo cuando se la piden.

La simulación de la cocina usa velocidades estimadas para
casi todas las tareas, supone las cantidades de cebolla y ajo que las recetas no registran y supone cuánto
recorta la organización del desorden del almuerzo; sus cifras indican órdenes de magnitud y la dirección del
efecto, no un pronóstico. Las ciudades, por último, se trataron con una base de precios y costos que la
investigación posterior matizó: el gas cuesta más que en la base, la altura alarga la cocción y gasta más gas, y
los sueldos de la sierra son más bajos que los de la costa; ese análisis queda para una parte propia del estudio.

Tres pasos cerrarían la mayor parte de esa incertidumbre: un \emph{{sondeo de pizarras}} por zona en Juliaca
(precio, segundos ofrecidos y conteo de comensales), la \emph{{sincronización automática}} de ventas y recetas
desde el sistema de Candela al estudio, y un \emph{{pesaje}} de una semana de las porciones de los cinco
segundos más vendidos.

\section{{Conclusiones}}\label{{sec:conclusiones}}

La pregunta del ensayo era quién gana con un menú y por qué. La respuesta corta es que en una fonda de provincia
gana el trabajo, no el capital, y que lo que separa a un negocio de otro es menos su cocina que su organización:
quién trabaja y cuánto se le paga, cuántos menús logra vender por cada sol de local, cómo paga el IGV y cómo
reparte el trabajo de la cocina. Cada conclusión lleva, cuando depende de números supuestos, la parte de los
sorteos en que se sostiene (\seccion{{sec:supuestos}}).

\begin{{enumerate}}[leftmargin=1.4em]
\item \textbf{{En una fonda de provincia gana el trabajo, no el capital.}} El propietario que cocina se lleva
{s(dc['ingreso_dueno'])} al mes y la familia que no se cobra sueldos {s(fam['ingreso_dueno'])}; el inversor que
contrata a todos apenas cubre costos ({s(inv['utilidad_mes'])}) y el inversor ausente, que terceriza hasta las
compras, pierde {s(-aus['utilidad_mes'])} al mes{sorteos_txt("El propietario que cocina se lleva más que el inversor")}.
\item \textbf{{A los mismos precios, el orden lo da quién paga el trabajo.}} {"" if not mp else rf"A S/~10, la familia necesita {eq_('Familiar sin sueldos', 10)} menús al día para no perder; el propietario que cocina, {eq_('Propietario que cocina', 10)}; el inversor que supervisa, {eq_('Inversor que supervisa', 10)}, y el inversor ausente, {eq_('Inversor ausente', 10)}. A S/~7, ningún negocio con planilla contratada y en regla cubre sus costos con ninguna cantidad de menús."}
\item \textbf{{Con la misma venta, el precio mínimo lo fija quién paga el trabajo.}} {"" if not mv else rf"A 60 menús, la familia no pierde cobrando {s(vpmin_('Familiar sin sueldos', 60), 2)}; el propietario, {s(vpmin_('Propietario que cocina', 60), 2)}; el inversor que supervisa necesita {s(vpmin_('Inversor que supervisa', 60), 2)}, y el ausente {s(vpmin_('Inversor ausente', 60), 2)}. Por eso la pizarra de la cuadra la marcan los que no pagan el trabajo, y el volumen la acerca pero no la cierra."}
\item \textbf{{Ganar no siempre es mérito de la organización.}} {"" if not fac else rf"""Al repartir la diferencia
de cada negocio con el propietario que cocina, el exitoso debe casi todo a su local y su venta
({s(ap('Exitoso (referencia compuesta)', 'local'))} al mes) y el puesto de mercado a un plato barato de hacer
({s(ap('Puesto de mercado informal', 'insumos'))}), no a su volumen ({s(ap('Puesto de mercado informal', 'local'))}). """}En
el mismo local, el orden lo decide quién trabaja y cómo se le paga.
\item \textbf{{Abrir de noche reparte el alquiler.}} El mismo inversor pasa de {s(inv['utilidad_mes'])} a
{s(dyn['utilidad_mes'])} al mes y su probabilidad de pérdida cae de {p(inv['mc']['prob_perdida'])} a
{p(dyn['mc']['prob_perdida'])}.
\item \textbf{{El calendario del IGV es el riesgo más seguro del sector.}} En 2028, sin una nueva ley, la tasa
de los restaurantes pasa de 10.5\,\% a 18\,\%: el equilibrio de Lima sube de {ciud['lima']['eq_2026']} a
{ciud['lima']['eq_2028']} menús diarios y el de Puno de {ciud['puno']['eq_2026']} a {ciud['puno']['eq_2028']}.
\item \textbf{{El precio es la palanca más sensible en todos los casos.}} Un 10\,\% de precio mueve la
utilidad más que cualquier otra variable; en el inversor promedio, basta que el precio baje
{p(abs(inv['quiebres']['precio']), 1)} para que pierda.
\item \textbf{{Con la clientela que se midió en Juliaca, subir el precio no paga.}} Si se supone una clientela poco
sensible, casi todos los negocios deberían subir S/~3; con la sensibilidad que muestra la historia de Candela
({n(pc['elasticidad_ajuste'], 1) if pc else "2.4"}), la mejor decisión deja el precio donde está o lo sube a lo más
{s(max_sube_med, 2)}. La mejora tiene que venir del costo, la mezcla de platos o más horas de venta.
\item \textbf{{Solo {len(sobreviven)} de {NN} negocios resisten todos los golpes juntos}} (clientela, insumos,
IGV, sueldos, alquiler y competencia): {lista_neg(sobreviven)}.
\item \textbf{{La fonda familiar gana porque su trabajo no se cobra.}} En el mismo local que el propietario que cocina,
cada uno de sus tres integrantes se lleva menos de la mitad que él solo{sorteos_txt("Cada integrante de la familia")}.
Descontado su trabajo a precio de mercado, su utilidad económica queda cerca de cero
({s(trab['Familiar sin sueldos']['utilidad_economica']) if trab else ''}): lo que muestra la caja es, casi entero, su propio sueldo.

\item \textbf{{El Nuevo RUS castiga crecer.}} Al pasar su tope, un local chico pierde {s(nr['nrus_tope'] - nr['rer_justo_despues'])}
al mes de golpe y necesita llegar a unos {nr['q_recupera']} menús diarios para recuperarse.
{candela_resumen}
\item \textbf{{Candela no necesita más gente: le falta clientela.}} Con la productividad que muestra su cocina,
su equipo aguanta unos {n(capac['Candela (datos del POS)']['tope']) if 'Candela (datos del POS)' in capac else 100} menús y vende
{n(cand['q']) if cand else 74}; llenar esa capacidad le dejaría unos
{s(capac['Candela (datos del POS)']['valor_holgura']) if 'Candela (datos del POS)' in capac and capac['Candela (datos del POS)']['valor_holgura'] else 'S/~2 900'}
más al mes, porque la planilla y el local ya están pagados.
{"" if not co else rf"\item \textbf{{{{Organizar la cocina rinde más que contratar.}}}} Con tres personas, la cocina doméstica aguanta {n(cap_('domestico', 3)['tope'])} menús; por bloques, {n(cap_('bloques', 3)['tope'])}, y con mise en place, {n(cap_('mise', 3)['tope'])}. El mise en place no ahorra horas, las cambia de momento; donde la cocina doméstica obliga a tener una persona de más, organizarse ahorra entre {s(min(ahorros_pos))} y {s(max(ahorros_pos))} al mes{'' if not org_c else ', y en Candela unos ' + s(org_c['modos'][mejor_c]['ahorro'])}. El resultado no depende de la formalidad sino de la organización."}
\end{{enumerate}}

Para Candela, el estudio deja tres lecciones. Su clientela es sensible al precio, así que la mejora no está en la
pizarra sino en el costo del plato y en llenar la capacidad que ya paga. Su cocina, organizada por bloques o con
mise en place, podría atender lo mismo con menos gente o crecer sin contratar. Y su resultado final depende de
una situación tributaria que este estudio deja abierta. Más allá de Candela, la conclusión de fondo es que una
fonda se puede analizar como cualquier empresa: con un modelo explícito, supuestos a la vista y experimentos que
dicen qué conclusiones resisten. Lo que falta para cerrar las preguntas abiertas no es teoría sino medición: un
sondeo de pizarras, unas mañanas cronometradas en la cocina y una semana de prueba de cada cambio.

\clearpage
\part{{Las ciudades}}\label{{cap:ciudades}}

\section{{Por qué un capítulo aparte}}

El capítulo~1 comparó negocios dentro de una misma ciudad para que la plaza no confundiera el efecto de la
organización. Este capítulo hace lo contrario: deja fijo el negocio y cambia la ciudad. Es un análisis distinto,
con sus propias preguntas ---cuánto cuesta producir un menú en cada plaza, cuánto se puede cobrar y qué tan
difícil es cocinar en altura--- y con datos más débiles, porque los precios y costos por ciudad casi no se
publican. Por eso va separado: lo que aquí se concluye no debe mezclarse con las conclusiones sobre la
organización de los negocios.

El capítulo está en construcción. Presenta el mapa de equilibrios del estudio de ciudades, resume lo que la
investigación posterior encontró y deja planteado lo que falta medir antes de sacar conclusiones firmes.

\section{{El mapa: doce ciudades}}\label{{sec:mapa}}

El \cuadro{{tab:ciudades}} y la \figura{{fig:ciudades}} resumen el equilibrio de un local de menú
popular formal en cada ciudad, con el precio de su pizarra, cinco balones de gas al mes y sin sueldo del
dueño. Es la referencia del estudio de ciudades, reproducida exactamente por el motor.

{sup_ciudades()}
\begin{{table}}[H]
\centering\small
\caption{{Equilibrio en menús diarios por ciudad. Formal salvo la última columna.}}\label{{tab:ciudades}}
\begin{{tabular}}{{lrlrrrrr}}
\toprule
& & & \multicolumn{{3}}{{c}}{{Formal, sin sueldo del dueño}} & Con sueldo & Informal \\
\cmidrule(lr){{4-6}}
Ciudad & Precio & Dato & 2026 & 2027 & 2028 & 2026 & 2026 \\
\midrule
{tabla_ciudades(d['ciudades'])}
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth]{{fig/ciudades.pdf}}
\caption{{Menús diarios para no perder en 2026, local formal frente a informal (mismo local, sin IGV ni cargas
laborales).}}\label{{fig:ciudades}}
\end{{figure}}

Tres lecturas sobresalen. Primero, el rango es amplio: de {ciud['lima']['eq_2026']} menús en Lima a
{ciud['juliaca']['eq_2026']} en Juliaca, donde el precio estimado de la base (S/~8) resultó bajo. La base lo
deriva del ingreso de la ciudad; en Candela se cobra S/~11 ---y se cobró S/~10 durante un año--- sin perder la
clientela del todo. Con ese precio, la fila \emph{{Juliaca (observado)}} baja el equilibrio a
{ciud['juliaca_obs']['eq_2026']} menús: de la peor ciudad del mapa pasa al puesto
{1 + sum(1 for c in d['ciudades'] if c['id'] != 'juliaca_obs' and c['id'] != 'juliaca' and c['eq_2026'] < ciud['juliaca_obs']['eq_2026'])}
de {len(d['ciudades']) - 1}, porque combina un precio de ciudad intermedia con sueldos y alquileres de provincia. Es un
solo local y no un sondeo, así que la cifra estimada se deja en la base, pero la lectura de Juliaca como la plaza
más difícil del país dependía de ese supuesto. Que Candela necesite muchos más menús que este local de referencia
no se debe a la plaza sino a su planilla, como muestra la \seccion{{sec:candela}}. Segundo, la informalidad compra entre
{min(c['eq_2026'] - c['eq_informal'] for c in d['ciudades'])} y {max(c['eq_2026'] - c['eq_informal'] for c in d['ciudades'])}
menús diarios de holgura: es la diferencia entre no pagar IGV ni cargas laborales y pagarlas. Tercero, el
sueldo del dueño es un costo real aunque no salga de la caja: contarlo agrega entre
{min(c['eq_con_sueldo'] - c['eq_2026'] for c in d['ciudades'])} y {max(c['eq_con_sueldo'] - c['eq_2026'] for c in d['ciudades'])}
menús al equilibrio.

\begin{{figure}}[H]
\centering
\includegraphics[width=0.66\textwidth]{{fig/igv.pdf}}
\caption{{Equilibrio formal según el año. *El 18\,\% de 2028 es un supuesto: la tasa especial de
restaurantes vence en 2027.}}\label{{fig:igv}}
\end{{figure}}

El calendario tributario empeora el mapa de manera desigual (\figura{{fig:igv}}). El paso del IGV de
10.5\,\% a 18\,\% le quita a un menú de S/~10 unos 60 céntimos de ingreso neto. Donde el margen por plato es
amplio, como en Lima, el equilibrio apenas se mueve; donde es fino, el mismo cambio dispara el volumen
necesario. El efecto es convexo: castiga más a quien menos margen tiene.



\section{{Lo que encontró la investigación posterior}}\label{{sec:investigacion_ciudades}}

Una revisión de fuentes públicas (MINEM, INEI, mercados mayoristas, prensa y avisos; el detalle y las direcciones
están en \texttt{{estudio/investigacion/ciudades.md}}) matiza varios supuestos del mapa. El cuadro~\ref{{tab:investigacion}}
los resume con su grado de confianza.

\begin{{table}}[H]
\centering\footnotesize
\caption{{Hallazgos de la investigación por ciudad y cómo cambiarían el mapa. Confianza: A, fuente oficial; B, prensa
o agregador con datos declarados; C, avisos sueltos; Est., cálculo propio.}}\label{{tab:investigacion}}
\setlength{{\tabcolsep}}{{3pt}}
\begin{{tabularx}}{{\textwidth}}{{>{{\raggedright\arraybackslash}}p{{0.2\textwidth}}>{{\raggedright\arraybackslash}}Xc>{{\raggedright\arraybackslash}}p{{0.26\textwidth}}}}
\toprule
Tema & Hallazgo & Conf. & Efecto en el mapa \\
\midrule
Verduras en la sierra & La papa y la cebolla de Juliaca y Puno cuestan lo mismo que en el mayorista de Lima; lo que viene de la costa o de la selva (arroz, limón, pollo) cuesta más arriba & B & Los insumos de Juliaca y Puno suben un poco; no bajan \\
Gas & El balón ya cuesta entre 10\,\% y 25\,\% más que en la base; por departamento, de $-1$\,\% (Junín) a $+42$\,\% (Loreto) frente a Lima & A & Más costo fijo en todas las plazas, más en Loreto y el sur \\
Altura & El agua hierve a 92\,°C en Arequipa, 89\,°C en Cusco y Huancayo y 87\,°C en Juliaca y Puno: las cocciones duran más y gastan más gas & Est. & Gas $+$35--60\,\% en Juliaca sin olla a presión, $+$10--20\,\% con ella \\
Sueldos & El ingreso laboral promedio de Juliaca es 46\,\% menor que el de Lima; Cusco es la excepción por el turismo & A & Planilla más barata en la sierra, no más cara \\
Precio del menú & El menú ejecutivo coincide con la base en $\pm$S/~2; del menú popular no hay dato observado en siete ciudades & B & Sigue siendo la variable más débil \\
Alquiler & Trujillo parece sobrestimado (avisos de S/~18--28 por m² frente a 45 en la base) & C & Equilibrio de Trujillo más bajo \\
Competencia & Hay datos de empresas de restaurantes por región, no por ciudad; la informalidad del rubro es de 75\,\% en el país & A & Sin dato para modelar la competencia por plaza \\
\bottomrule
\end{{tabularx}}
\end{{table}}

Dos ideas que parecían naturales no se sostienen. La primera, que en la sierra las verduras son mucho más baratas:
para un restaurante urbano no lo son, y lo que se trae de lejos es más caro. La segunda, que cocinar en altura
exige pagar más: es más difícil y más lento, pero los sueldos de la sierra son más bajos que los de la costa. Lo
que sí cambia con la altura es el gas y el tiempo de cocina, dos costos que el mapa hoy no distingue.

\section{{Lo que falta para cerrar el capítulo}}

Cuatro trabajos convertirían este capítulo en un análisis comparable al primero:
\begin{{enumerate}}[leftmargin=1.4em]
\item \textbf{{Actualizar la base}} con el gas por departamento, los insumos que suben en la sierra, los sueldos por
ciudad y los alquileres corregidos.
\item \textbf{{Un factor de altura}} para el gas y para los tiempos de cocción, que ya usa la simulación de la cocina del
capítulo~1 para Juliaca.
\item \textbf{{La competencia como tope de precio}}: cuántos locales hay cerca y a cuánto venden, para modelar cuánto
se puede cobrar en cada plaza en lugar de suponerlo.
\item \textbf{{Un sondeo de pizarras}} en Juliaca y en dos o tres ciudades más: precio, segundos ofrecidos y conteo de
comensales. Es la única forma de tener el precio del menú popular donde hoy es una estimación.
\end{{enumerate}}

El mismo método sirve más allá del menú. Las chicharronerías, las pollerías de pollo frito, las cevicherías o el
carrito sanguchero de la esquina ---la ``tía veneno''--- son negocios de comida igual de comunes, con otra mezcla de
costos: menos platos y más proteína, otro horario, otro local o ninguno. Con sus recetas, su planilla y su venta,
el motor del capítulo~1 puede compararlos con el menú, y es una extensión natural para un capítulo siguiente.

\section{{Conclusiones del capítulo}}

\begin{{itemize}}[leftmargin=1.2em]
{"" if 'juliaca_obs' not in ciud else rf"""\item \textbf{{Juliaca no es la plaza más difícil del país.}} Con el precio estimado de la base (S/~8) lo parecía:
{ciud['juliaca']['eq_2026']} menús diarios para no perder. Con el que se cobra en Candela (S/~11) el equilibrio baja a
{ciud['juliaca_obs']['eq_2026']} y queda entre las mejores plazas del mapa; falta confirmarlo con más locales."""}
\item \textbf{{El costo del menú es casi nacional; el precio y algunos costos fijos, no.}} Las verduras de mercado
cuestan parecido en todas partes; el gas, la altura y el sueldo separan a las plazas más que el plato.
\item \textbf{{El calendario del IGV pesa distinto en cada ciudad.}} Donde el margen por plato es fino, el paso a 18\,\%
dispara el volumen necesario: es la misma convexidad que se vio en los negocios, ahora entre plazas.
\end{{itemize}}

\clearpage
\section*{{Referencias}}
\addcontentsline{{toc}}{{section}}{{Referencias}}

\begin{{itemize}}[leftmargin=1.2em,label={{}}]
\item Andreyeva, T., Long, M. W. y Brownell, K. D. (2010). The impact of food prices on consumption: a systematic review of research on the price elasticity of demand for food. \emph{{American Journal of Public Health}}, 100(2), 216--222.
\item Azuero, R., Bosch, M. y Lagomarsino, B. (s.~f.). [Estudio sobre la eliminación de categorías del Nuevo RUS en 2017 con datos de SUNAT]. Documento de trabajo, BID. \url{{http://rodrigoazuero.com/files/rmt.pdf}}
\item Bijmolt, T. H. A., van Heerde, H. J. y Pieters, R. G. M. (2005). New empirical generalizations on the determinants of price elasticity. \emph{{Journal of Marketing Research}}, 42(2), 141--156.
\item Chayanov, A. V. (1925/1974). \emph{{La organización de la unidad económica campesina}}. Buenos Aires: Nueva Visión.
\item de Mel, S., McKenzie, D. y Woodruff, C. (2008). Returns to capital in microenterprises: evidence from a field experiment. \emph{{Quarterly Journal of Economics}}, 123(4), 1329--1372.
\item De Soto, H. (1986). \emph{{El otro sendero: la revolución informal}}. Lima: El Barranco.
\item Escoffier, A. (1903). \emph{{Le guide culinaire}}. París: Flammarion.
\item Gamero, J. (2012). [Investigación sobre el empleo y el trabajo familiar no remunerado en la microempresa, con la ENAHO 2009]. Lima: INEI. \url{{https://www.inei.gob.pe/media/MenuRecursivo/investigaciones/investigacion-final-julio-gamero.pdf}}
\item GRADE (2012). El impacto de la licencia municipal en el desempeño de las microempresas en el Cercado de Lima. Lima: Grupo de Análisis para el Desarrollo. \url{{https://grade.org.pe/en/publicaciones/1133-el-impacto-de-la-licencia-municipal-en-el-desempeno-de-las-microempresas-en-el-cercado-de-lima}}
\item Greathouse, K. R. y otros (1989). Comparison of conventional, cook-chill, and cook-freeze foodservice systems. \emph{{Journal of the American Dietetic Association}}, 89(11).
\item Institute of Child Nutrition (2014). \emph{{Meals per labor hour (MPLH)}}. Serie de indicadores clave. \url{{https://theicn.org/resources/1569/key-performance-indicators-mini-series/118698/kpi-mini-series-meals-per-labor-hour-mplh.pdf}}
\item Kahneman, D. y Tversky, A. (1979). Prospect theory: an analysis of decision under risk. \emph{{Econometrica}}, 47(2), 263--291.
\item Kelley, J. E. y Walker, M. R. (1959). Critical-path planning and scheduling. \emph{{Proceedings of the Eastern Joint Computer Conference}}, 160--173.
\item La Porta, R. y Shleifer, A. (2014). Informality and development. \emph{{Journal of Economic Perspectives}}, 28(3), 109--126.
\item Little, J. D. C. (1961). A proof for the queuing formula $L=\lambda W$. \emph{{Operations Research}}, 9(3), 383--387.
\item Loayza, N. (2007). \emph{{Causas y consecuencias de la informalidad en el Perú}}. Documento de trabajo, Banco Central de Reserva del Perú.
\item National Restaurant Association (2025). \emph{{Restaurant Operations Data Abstract}} (año fiscal 2024).
\item Okrent, A. y Alston, J. (2012). \emph{{The Demand for Disaggregated Food-Away-from-Home and Food-at-Home Products in the United States}}. Economic Research Report 139, USDA.
\item Parsa, H. G., Self, J. T., Njite, D. y King, T. (2005). Why restaurants fail. \emph{{Cornell Hotel and Restaurant Administration Quarterly}}, 46(3), 304--322.
\item Shapley, L. S. (1953). A value for $n$-person games. En H. W. Kuhn y A. W. Tucker (eds.), \emph{{Contributions to the Theory of Games II}}, 307--317. Princeton University Press.
\item Shimmura, T. y otros (2017). [Rediseño de la distribución de una cocina de restaurante guiado por simulación]. \emph{{Procedia CIRP}}, 62. \url{{https://hdl.handle.net/20.500.14094/90004434}}
\item Shimmura, T. y otros (2018). [Cambios en el proceso de cocina y productividad de un restaurante de servicio completo]. \emph{{International Journal of Automation Technology}}, 12(4). \url{{https://doi.org/10.20965/ijat.2018.p0449}}
\item Smith, A. (1776). \emph{{An Inquiry into the Nature and Causes of the Wealth of Nations}}. Londres: W. Strahan y T. Cadell.
\item Thaler, R. (1985). Mental accounting and consumer choice. \emph{{Marketing Science}}, 4(3), 199--214.
\item Wald, A. (1945). Statistical decision functions which minimize the maximum risk. \emph{{Annals of Mathematics}}, 46(2), 265--280.
\end{{itemize}}
Las fuentes de los datos (leyes, precios, sueldos, alquileres) están en el \anexo{{sec:fuentes}}; las de las
velocidades de cocina y de la investigación por ciudad, en la carpeta \texttt{{estudio/investigacion}} del proyecto.

\appendix
{"" if not d["casos"] else rf"""\section{{Utilidad por precio y venta de cada negocio}}\label{{sec:anexo_matrices}}

Este anexo repite para cada negocio el mapa que la \figura{{fig:matriz}} muestra para Candela: la utilidad del mes, en
miles de soles, para precios de S/~2 menos a S/~2 más que el suyo y para ventas del 50 al 150\,\% de la de hoy, con su
planilla, su alquiler, sus insumos y su régimen. El recuadro marca la situación de hoy; el verde, ganancia, y el rojo,
pérdida. La utilidad es la del negocio, sin sumar el sueldo del dueño cuando el modelo le asigna uno.

{mapas_anexo()}
\clearpage
"""}
{"" if not estados else rf"""\section{{Estados de resultados anuales}}\label{{sec:anexo_estados}}

Como apoyo visual, este anexo presenta el estado de resultados de un año completo de cada negocio, con el local
ya lleno: el mes del modelo multiplicado por doce, con los números del \cuadro{{tab:entradas}}, el IGV de 2026
y el impuesto del régimen de cada uno (en el MYPE, la renta descuenta la depreciación de la inversión a diez años).
Los porcentajes son sobre la venta sin IGV. La \figura{{fig:estados}} resume cada estado en una cascada.

\begin{{figure}}[H]
\centering
\includegraphics[width=\textwidth,height=0.78\textheight,keepaspectratio]{{fig/estados.pdf}}
\caption{{De la venta sin IGV a lo que queda después de impuestos, en un año lleno de cada negocio (miles de soles).
En verde lo que queda; en rojo, la pérdida.}}\label{{fig:estados}}
\end{{figure}}

{anexo_estados()}
\clearpage
"""}
\section{{Supuestos del modelo}}\label{{sec:anexo}}

\begin{{itemize}}[leftmargin=1.2em]
\item Días de atención: 26 al mes (ajustable por escenario). Merma general: 5\,\%. Descartables: S/~0.20 por menú
popular y S/~0.35 por ejecutivo. Otros gastos fijos: S/~400 al mes. Sueldo del dueño, cuando se cuenta:
S/~1\,500.
\item Personal automático: un cocinero, un ayudante adicional cada 80 menús (55 en ejecutivo) y un mozo cada 70
(40 en ejecutivo). Formal: sueldo no menor al mínimo (cocinero, al menos 6\,\% sobre el mínimo) y costo de
empleador de 1.05 veces el sueldo (microempresa).
\item IGV de restaurantes: 10.5\,\% (2026), 15\,\% (2027), 18\,\% desde 2028 (supuesto). Sueldo mínimo: S/~1\,230
(2026), S/~1\,300 (2027--2028) y luego +3.7\,\% anual (supuesto: saltos de 9--10\,\% cada 2--3 años).
\item Regímenes: informal (sin IGV, renta ni cargas), Nuevo RUS (cuota de S/~20 o S/~50, sin IGV, tope de S/~96 mil
al año), RER (1.5\,\% de los ingresos netos, tope de S/~525 mil) y MYPE (10\,\% de la renta hasta 15 UIT y
29.5\,\% por encima, con la inversión depreciada a diez años).
\item Flujo: tasa de descuento de 15\,\%, inflación de costos de 2.5\,\% anual, precio ajustado al mismo ritmo en
saltos de S/~0.50, sin valor residual.
\item Simulación: 2\,000 años por caso; volumen lognormal (desvío 20\,\%), insumos normales (8\,\% anual), precio
triangular en el rango de la ciudad (o $\pm$4\,\% si es dato propio) y, en ciudades con historial de paros,
pérdida de 2 a 8 semanas con su probabilidad anual.
\end{{itemize}}

\section{{Fuentes del conjunto de datos}}\label{{sec:fuentes}}

{{\small
\begin{{itemize}}[leftmargin=1.2em,itemsep=0.2ex]
{fuentes(d['fuentes'])}
\item Restaurantes tipo y referencia compuesta: \texttt{{estudio/data/arquetipos.json}}. MINCETUR, perfil de
franquicias gastronómicas. \url{{https://cdn.www.gob.pe/uploads/document/file/410029/07586-perfil_-franquicias-gastronomicas-ru.pdf}}
\end{{itemize}}
}}

\end{{document}}
"""


def compilar(tex: str) -> Path:
    archivo = SALIDA / "ensayo.tex"
    archivo.write_text(tex, encoding="utf-8")
    for _ in range(2):  # dos pasadas: índice y referencias
        r = subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", archivo.name], cwd=SALIDA,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stdout[-3000:])
    return SALIDA / "ensayo.pdf"


def main() -> None:
    d = mod_datos.generar()
    figuras.generar(d)
    pdf = compilar(construir(d))
    print(pdf)


if __name__ == "__main__":
    main()
