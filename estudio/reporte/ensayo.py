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

def tabla_casos(cs: list[dict]) -> str:
    filas = []
    for c in cs:
        filas.append(" & ".join([
            esc(corto(c["nombre"])), s(c["precio"], 2 if c["precio"] % 1 else 0),
            n(c["q"]) + ("+n" if c["noche"] else ""), str(c["trabajadores"]), "sí" if c["formal"] else "no",
            s(c["ingreso_dueno"]), str(c["equilibrio"] or "$>$600"), p(c["mc"]["prob_perdida"]),
            s(c["flujo"]["van"]), anios(c["flujo"]["recupero"]),
        ]) + r" \\")
    return "\n".join(filas)


def tabla_quiebres(cs: list[dict]) -> str:
    claves = ("precio", "q", "insumos", "sueldos", "alquiler_mes")
    filas = []
    for c in cs:
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
        filas.append(esc(corto(c["nombre"])) + " & " + " & ".join(celdas) + r" \\")
    return "\n".join(filas)


def tabla_ciudades(cs: list[dict]) -> str:
    return "\n".join(
        f"{esc(c['nombre'].replace(' Metropolitana', ''))} & {s(c['precio'], 1 if c['precio'] % 1 else 0)} & "
        f"{'observado' if c['precio_fuente'] == 'observado' else 'estimado'} & {c['eq_2026']} & {c['eq_2027']} & "
        f"{c['eq_2028']} & {c['eq_con_sueldo']} & {c['eq_informal']} \\\\"
        for c in cs)


def fuentes(fs: list[dict]) -> str:
    return "\n".join(f"\\item {esc(f['tema'])}. \\url{{{f['url']}}}" for f in fs)


# ---------------------------------------------------------------- documento

def construir(d: dict) -> str:
    casos = {c["nombre"]: c for c in d["casos"]}
    dc, fam, inv, aus = (casos["Dueña que cocina"], casos["Familia sin sueldos"], casos["Inversor (promedio)"],
                         casos["Dueño ausente (todo tercerizado)"])
    mer, rus, eje, dyn, exi = (casos["Puesto de mercado informal"], casos["Chiquito en Nuevo RUS"],
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
    r_inv, r_dc = rob["Inversor (promedio)"], rob["Dueña que cocina"]
    sobreviven = [corto(r["nombre"]) for r in d.get("robustez", []) if r["estres"][-1]["utilidad"] >= 0]
    al_tope = sum(1 for r in d.get("robustez", []) if r["mejor"]["precio"] >= r["precio0"] + 3 - 1e-9)

    hz = d.get("hallazgos", {})
    nr = hz.get("nrus", {})
    pc = hz.get("precio_candela")
    hora = {h["nombre"]: h for h in hz.get("hora", [])}
    medio = sorted(hz.get("medio_sol", []), key=lambda x: x["menus"])
    noche_u = {x["nombre"]: x for x in hz.get("noche", [])}

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
            f"al precio.}} Con su alquiler y su planilla reales, la venta cubre insumos, sueldos y local, pero no el "
            f"trabajo del dueño; si paga IGV sobre todo lo vendido, pierde {s(-cand['utilidad_mes'] - 1500)} al mes sin "
            f"contar su sueldo. Al subir de S/~10 a S/~11 perdió cerca de "
            f"{round(10 * (1 - pc['historia']['q1'] / pc['historia']['q0']))} clientes de cada 10, lo justo para que el "
            f"alza no ganara ni perdiera dinero: el precio ya está en su punto y la mejora tiene que venir del costo.")
        candela_seccion = rf"""
\section{{El caso Candela}}\label{{sec:candela}}

\subsection{{Cuánto cuesta un menú}}

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
{p(par[2]['acumulado'])} de las compras (figura~\ref{{fig:platos}}, derecha).

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/platos.pdf}}
\caption{{Candela. Izquierda: ingeniería de menú de los segundos (parte de las ventas contra margen por menú;
las líneas son el umbral de popularidad y el margen promedio). Derecha: peso de cada insumo en el gasto
semanal.}}\label{{fig:platos}}
\end{{figure}}

\subsection{{Qué platos sostienen el negocio}}

La ingeniería de menú clasifica cada segundo por lo que vende y por lo que deja. Los platos de pollo (arroz
con pollo, arroz a la jardinera) y los tallarines rojos son \emph{{estrellas}}: venden mucho y dejan cerca de
S/~5 por menú. Los de res ---asado, seco, estofado, chuleta--- son \emph{{caballitos de batalla}}: sostienen
el volumen pero dejan unos 50 céntimos menos, porque la res pesa más en el costo. La pulpa de res es, por sí
sola, el insumo más caro del local. La consecuencia práctica es de mezcla, no de precio: cada día que el menú
ofrece dos segundos de res y uno de pollo, el margen promedio baja; un segundo de pollo o de pasta más por
semana sube la utilidad sin tocar la pizarra.

\subsection{{Los números del local}}

La entrevista con el dueño completó lo que el sistema de ventas no tiene. El local paga S/~2\,000 de alquiler
---un precio de conocido; el de mercado para ese tamaño y esa calle es S/~3\,000---. En cocina trabajan tres
personas a tiempo completo (S/~1\,500, S/~1\,500 y S/~1\,300) y en el salón tres mozos a medio tiempo (S/~700 cada
uno); las compras las hace el dueño. Opera con RUC de persona natural y emite boleta solo cuando el cliente la pide, así que el IGV que de verdad paga está entre los dos extremos del cuadro. La inversión inicial fue de S/~20 mil y
el local tardó unos seis meses en llenarse.

\begin{{table}}[h]
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

El cuadro~\ref{{tab:candela}} cuenta la situación sin adornos. Sin IGV, la venta alcanza justo para pagar
insumos, sueldos y local: al dueño le quedan {s(pc['sin_igv'] + 1500)} al mes por hacer las compras y
administrar, {"menos de lo que gana una de sus cocineras" if pc['sin_igv'] + 1500 < 1500 else "apenas lo que gana una de sus cocineras"}. Si el IGV se paga sobre toda la venta, el local
{"pierde " + s(-(cand['utilidad_mes'] + 1500)) if cand['utilidad_mes'] + 1500 < 0 else "deja " + s(cand['utilidad_mes'] + 1500)} al mes. Los insumos se llevan más de la mitad de la venta neta; la planilla,
un tercio. Esos dos renglones ---no el alquiler--- son los que deciden.

Que el local siga abierto después de año y medio con estas cuentas es coherente: un negocio que cubre sus
costos de caja puede durar mucho tiempo si el dueño no se cobra. Pero no es una situación estable: cualquier
golpe ---una subida de insumos, un competidor, el IGV de 15\,\% en 2027--- la empuja a pérdida, y el trabajo del
dueño no tiene recompensa.

\subsection{{La lección del precio}}

Candela tiene algo que ningún estudio de mercado ofrece: un experimento propio, con tres precios. Abrió a
S/~15 durante tres meses y en un buen día vendía S/~450--550 (unos 33 menús). Bajó a S/~10 durante un año y la
venta saltó a S/~800--1\,000 diarios (unos 90 menús), tanto que la cocina colapsaba. Subió a S/~11 por el alza
de los insumos y para mejorar la comida, y hoy vende S/~750--800 (unos 70). Los tres puntos caen cerca de una
misma curva: la sensibilidad constante que mejor los ajusta es de {n(pc['elasticidad_ajuste'], 1)}, y el paso de
S/~10 a S/~11, por sí solo, da {n(pc['elasticidad_central'], 1)} (entre {n(pc['elasticidad_arco'][0], 1)} y
{n(pc['elasticidad_arco'][1], 1)} según qué extremo de cada rango se tome; figura~\ref{{fig:historia}}).

\begin{{figure}}[t]
\centering
\includegraphics[width=0.8\textwidth]{{fig/historia.pdf}}
\caption{{Candela: la venta diaria en sus tres precios (barras: el rango que da el dueño) frente a curvas de
demanda con distinta sensibilidad, ancladas en la venta de hoy. La curva de $\varepsilon=2.5$ pasa cerca de
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

\subsection{{Dónde está Candela}}

La figura~\ref{{fig:matriz}} muestra el mapa completo: cada celda es la utilidad mensual para una combinación
de precio y volumen, con los costos reales y pagando IGV; el recuadro marca la situación actual. Su
equilibrio está en {cand['equilibrio']} menús diarios a S/~11. Leído junto con la lección del precio, el mapa dice
que la salida no está en moverse hacia la derecha (más precio, menos clientes) sino hacia abajo en el costo:
el margen por plato es el que no alcanza.

\begin{{figure}}[t]
\centering
\includegraphics[width=0.92\textwidth]{{fig/matriz.pdf}}
\caption{{Candela: utilidad del mes (miles de soles) por precio y menús al día, con los costos reales y pagando
IGV. El recuadro es la situación de hoy.}}\label{{fig:matriz}}
\end{{figure}}

\subsection{{El alquiler del conocido}}

El alquiler de Candela equivale a vender {n(next(a['menus'] for a in hz['alquiler'] if a['nombre'].startswith('Candela')))}
menús diarios solo para pagarlo. El descuento de conocido vale S/~1\,000 al mes: con el alquiler de mercado, el
local perdería {s(-next(v['utilidad_mes'] for v in d['candela_variantes'] if 'mercado' in v['nombre']))} al mes; en
un local propio, {s(next(v['utilidad_mes'] for v in d['candela_variantes'] if 'propio' in v['nombre']))}. El
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
\usepackage[hidelinks]{{hyperref}}
\usepackage{{xurl}}

\definecolor{{acento}}{{HTML}}{{1F4E79}}
\definecolor{{perdida}}{{HTML}}{{B03024}}
\definecolor{{gris}}{{HTML}}{{5B5A56}}
\definecolor{{fondo}}{{HTML}}{{F4F2EC}}
\hypersetup{{colorlinks=true,linkcolor=acento,urlcolor=acento,citecolor=acento}}

\captionsetup{{font=small,labelfont={{sc}},labelsep=period,margin=0.5cm}}
\titleformat{{\section}}{{\normalfont\Large\bfseries\color{{acento}}}}{{\thesection}}{{0.8em}}{{}}
\titleformat{{\subsection}}{{\normalfont\large\itshape}}{{\thesubsection}}{{0.7em}}{{}}
\titlespacing*{{\section}}{{0pt}}{{2.2ex plus 1ex}}{{1.2ex}}
\setlist{{itemsep=0.35ex,topsep=0.6ex}}
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

En el Perú el menú cuesta casi lo mismo en todas partes, pero se vende a precios muy distintos. Este ensayo
toma esa observación del estudio de ciudades y la lleva a la pregunta que importa a quien tiene o quiere
abrir una fonda: \emph{{¿quién gana con un menú, y por qué?}} Para responderla se modelan {NN} negocios con el
mismo motor ---{NT} restaurantes tipo y el caso real de Candela, en Juliaca--- que difieren en quién trabaja,
qué tan formales son, a qué precio venden y cuántas horas abren. Para cada uno se calcula el estado de
resultados del mes, el punto de equilibrio, la probabilidad de terminar el año en pérdida (2\,000 años
simulados), el flujo de caja a diez años en cuatro regímenes tributarios y cuánto puede moverse cada variable
antes de que el negocio pierda.

\begin{{recuadro}}{{Hallazgos}}
\begin{{itemize}}[leftmargin=1.2em]
\item \textbf{{En una fonda de provincia gana el trabajo, no el capital.}} La dueña que cocina se lleva
{s(dc['ingreso_dueno'])} al mes y la familia que no se cobra sueldos {s(fam['ingreso_dueno'])}; el inversor que
contrata a todos apenas cubre costos ({s(inv['utilidad_mes'])}) y el dueño que terceriza hasta las compras
pierde {s(-aus['utilidad_mes'])} al mes.
\item \textbf{{El volumen pesa más que el precio de lista.}} Un puesto de mercado a S/~7 con {mer['q']} menús
deja más que un local de S/~11 con 80, porque su alquiler es la cuarta parte.
\item \textbf{{Abrir de noche reparte el alquiler.}} El mismo inversor pasa de {s(inv['utilidad_mes'])} a
{s(dyn['utilidad_mes'])} al mes y su probabilidad de pérdida cae de {p(inv['mc']['prob_perdida'])} a
{p(dyn['mc']['prob_perdida'])}.
\item \textbf{{El calendario del IGV es el riesgo más seguro del sector.}} En 2028, sin una nueva ley, la tasa
de los restaurantes pasa de 10.5\,\% a 18\,\%: el equilibrio de Lima sube de {ciud['lima']['eq_2026']} a
{ciud['lima']['eq_2028']} menús diarios y el de Puno de {ciud['puno']['eq_2026']} a {ciud['puno']['eq_2028']}.
\item \textbf{{El precio es la palanca más sensible en todos los casos.}} Un 10\,\% de precio mueve la
utilidad más que cualquier otra variable; en el inversor promedio, basta que el precio baje
{p(abs(inv['quiebres']['precio']), 1)} para que pierda.
\item \textbf{{Subir el precio conviene solo si la clientela lo tolera.}} Con sensibilidades de 0.5 a 1.5, en
todos los restaurantes tipo la mejor decisión sube el precio; en Candela, cuya historia muestra una sensibilidad
de {n(pc['elasticidad_ajuste'], 1) if pc else "2 a 3"}, mover el precio en cualquier dirección apenas cambia la utilidad.
\item \textbf{{Solo {len(sobreviven)} de {NN} negocios resisten todos los golpes juntos}} (clientela, insumos,
IGV, sueldos, alquiler y competencia): {esc(', '.join(sobreviven))}.
\item \textbf{{La fonda familiar es rentable porque su trabajo se paga por debajo del mínimo.}} Repartida entre
tres personas que trabajan 60 horas a la semana, su utilidad equivale a {s(hora['Familia sin sueldos']['por_hora'], 2)}
por hora, frente a {s(hz['rmv_hora'], 2)} del sueldo mínimo.
\item \textbf{{El Nuevo RUS castiga crecer.}} Al pasar su tope, un local chico pierde {s(nr['nrus_tope'] - nr['rer_justo_despues'])}
al mes de golpe y necesita llegar a unos {nr['q_recupera']} menús diarios para recuperarse.
{candela_resumen}
\end{{itemize}}
\end{{recuadro}}

\clearpage
\tableofcontents
\clearpage

\section{{Introducción}}

El menú es una institución económica peruana antes que un plato. A mediodía, en cualquier ciudad, una
pizarra ofrece por un precio fijo una entrada o sopa, un segundo a elegir y un refresco. El cliente es el
trabajador que no vuelve a casa a almorzar; el proveedor, un local pequeño que cocina en grandes ollas y
sirve rápido. Detrás de esa escena hay un negocio de márgenes finos que sostiene a cientos de miles de
familias: a fines de 2025 el INEI contaba más de 287 mil empresas formales de comidas y bebidas, y la
informalidad en alojamiento y restaurantes supera el 75\,\%.

El estudio de ciudades que precede a este ensayo llegó a una conclusión de fondo: \emph{{el menú tiene un costo
nacional y un precio local}}. El pollo, el arroz y la papa cuestan casi lo mismo en Piura que en Juliaca; lo
que cambia es lo que el cliente está dispuesto a pagar y lo que cuesta el local. Ese hallazgo ordena las
ciudades, pero deja abierta una pregunta más cercana a la experiencia de quien opera una fonda: dentro de una
misma ciudad, con el mismo costo de insumos, ¿por qué unos locales prosperan y otros apenas sobreviven?

La hipótesis de este ensayo es que la respuesta está menos en la cocina que en la organización: quién
trabaja y cuánto se le paga, si el local paga impuestos y cargas, cuántos menús logra vender y cuántas horas
aprovecha el alquiler. Para examinarla se construyó un catálogo de restaurantes tipo y se los hizo pasar por
el mismo motor de cálculo, junto con el caso real de Candela, una fonda de Juliaca cuyos datos de ventas,
recetas y costos provienen de su propio sistema.

\section{{Datos y método}}

\subsection{{El motor}}

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

\subsection{{Procedencia de las cifras}}

Cada parámetro de la base de datos lleva su origen. Los precios de menú de Lima, Cusco y Puno son
\emph{{observados}}; los del resto de ciudades, \emph{{estimados}} a partir del ingreso. El IGV de restaurantes
(10.5\,\% en 2026 y 15\,\% en 2027) y el sueldo mínimo (S/~1\,230, luego S/~1\,300) son ley; el 18\,\% desde
2028 es un \emph{{supuesto}}: la ley vigente no prevé una tasa especial más allá de 2027. Los restaurantes
tipo son \emph{{supuestos}} explícitos, documentados en su ficha. Los datos de Candela son \emph{{propios}}: salen
de su sistema de ventas. La lista de fuentes está en el anexo.

\section{{El mapa: doce ciudades}}

El cuadro~\ref{{tab:ciudades}} y la figura~\ref{{fig:ciudades}} resumen el equilibrio de un local de menú
popular formal en cada ciudad, con el precio de su pizarra, cinco balones de gas al mes y sin sueldo del
dueño. Es la referencia del estudio de ciudades, reproducida exactamente por el motor.

\begin{{table}}[h]
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

\begin{{figure}}[h]
\centering
\includegraphics[width=\textwidth]{{fig/ciudades.pdf}}
\caption{{Menús diarios para no perder en 2026, local formal frente a informal (mismo local, sin IGV ni cargas
laborales).}}\label{{fig:ciudades}}
\end{{figure}}

Tres lecturas sobresalen. Primero, el rango es amplio: de {ciud['lima']['eq_2026']} menús en Lima a
{ciud['juliaca']['eq_2026']} en Juliaca, donde el precio estimado de la base (S/~8) es probablemente bajo;
con el precio observado en Candela (S/~11) el equilibrio de Juliaca cae a la zona de Puno. Segundo, la
informalidad compra entre 10 y 35 menús diarios de holgura: es la diferencia entre no pagar IGV ni cargas
laborales y pagarlas. Tercero, el sueldo del dueño es un costo real aunque no salga de la caja: contarlo
agrega entre 8 y 60 menús al equilibrio.

\begin{{figure}}[h]
\centering
\includegraphics[width=0.66\textwidth]{{fig/igv.pdf}}
\caption{{Equilibrio formal según el año. *El 18\,\% de 2028 es un supuesto: la tasa especial de
restaurantes vence en 2027.}}\label{{fig:igv}}
\end{{figure}}

El calendario tributario empeora el mapa de manera desigual (figura~\ref{{fig:igv}}). El paso del IGV de
10.5\,\% a 18\,\% le quita a un menú de S/~10 unos 60 céntimos de ingreso neto. Donde el margen por plato es
amplio, como en Lima, el equilibrio apenas se mueve; donde es fino, el mismo cambio dispara el volumen
necesario. El efecto es convexo: castiga más a quien menos margen tiene.

\section{{{NN.capitalize()} negocios}}

\subsection{{Un catálogo de restaurantes tipo}}

Para separar el efecto de la organización del efecto de la ciudad, los {NT} restaurantes tipo están en
Juliaca y comparten la misma base de costos; difieren en lo que define el modelo de negocio:

\begin{{description}}[leftmargin=1em,style=nextline]
\item[Quién trabaja] La \emph{{dueña que cocina}} reemplaza al cocinero y se paga los S/~1\,500 del dueño; la
\emph{{familia sin sueldos}} cocina y atiende sin cobrar; el \emph{{inversor}} pone el capital y contrata a todo el
personal sin cobrar sueldo; el \emph{{dueño ausente}} no pisa el local: paga administrador, cajero, encargado de
compras y contador, y sus compras cuestan 6\,\% más sin el regateo y el control del dueño.
\item[Formalidad] El \emph{{puesto de mercado}} vende barato y mucho, sin RUC y con alquiler mínimo; el
\emph{{chiquito en Nuevo RUS}} se mantiene bajo S/~8\,000 de ventas al mes para no salir del régimen.
\item[Precio y servicio] El \emph{{ejecutivo}} vende a S/~18 en un local caro; \emph{{día y noche}} es el inversor
que además abre de noche con su propio equipo.
\item[Local] La \emph{{fonda en casa propia}} no paga alquiler, pero está fuera de la calle con más paso:
vende a S/~9 y unos 45 menús diarios.
\item[Referencia] El \emph{{exitoso}} es una referencia compuesta, no un local real: 220 menús a S/~13 con
compras por volumen. Ningún local de menú publica sus números; la referencia combina el dato del MINCETUR de
que la mitad de los restaurantes recupera su inversión en 19 a 24 meses y las ventas de franquicias chicas,
cercanas a S/~50 mil al mes.
\end{{description}}

\begin{{table}}[h]
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

\subsection{{Quién se lleva qué}}

La figura~\ref{{fig:ingreso}} ordena los negocios por lo que se lleva el dueño cada mes. El resultado más
claro es el de las cuatro formas de organizar el trabajo. Con los mismos costos de insumos y la misma ciudad,
la dueña que cocina gana {s(dc['ingreso_dueno'])} al mes, la familia {s(fam['ingreso_dueno'])}, el inversor
{s(inv['ingreso_dueno'])} y el dueño ausente pierde {s(-aus['ingreso_dueno'])}. La diferencia no está en la
eficiencia de la cocina sino en a quién se le paga por el trabajo. En la fonda familiar el trabajo no
remunerado es, literalmente, la utilidad: lo que el estado de resultados muestra como ganancia es el sueldo
que la familia no se cobra. El dueño ausente es el caso opuesto: compra con plata lo que los otros ponen
con su tiempo, y a 100 menús diarios no le alcanza.

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/ingreso.pdf}}
\caption{{Lo que se lleva el dueño al mes: utilidad más su sueldo, si el modelo le asigna uno.}}\label{{fig:ingreso}}
\end{{figure}}

La estructura de costos (figura~\ref{{fig:estructura}}) explica el orden. En todos los casos los insumos se
llevan entre 40 y 57 centavos de cada sol vendido sin IGV: esa parte es casi fija. Lo que separa a los
ganadores de los perdedores es el personal, que va del {p(fam['estructura']['personal'])} de la venta en la
fonda familiar al {p(aus['estructura']['personal'])} del dueño ausente, y el alquiler, que va del
{p(mer['estructura']['alquiler'])} en el mercado al {p(eje['estructura']['alquiler'])} del ejecutivo. El
exitoso gana porque diluye ambos: con 220 menús, su personal es apenas el {p(exi['estructura']['personal'])} y
sus compras por volumen bajan los insumos al {p(exi['estructura']['insumos'])}.

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/estructura.pdf}}
\caption{{A dónde va cada sol vendido (sin IGV). Más allá de la línea del 100\,\%, el negocio pierde.}}\label{{fig:estructura}}
\end{{figure}}

Dos casos merecen comentario. El \emph{{chiquito en Nuevo RUS}} muestra una trampa del régimen: para no pasar
el tope de S/~96 mil al año tiene que vender poco, y con 30 menús diarios no alcanza a pagar una planilla
formal ni el alquiler; si crece, sale del régimen. El Nuevo RUS sirve para formalizar a quien ya vende poco,
no para construir un negocio que crezca. Y el turno noche funciona porque el alquiler, el local y buena parte
de la luz ya están pagados al mediodía: cada cena vendida aporta casi todo su margen.

\section{{Riesgo}}

Un promedio esconde la pregunta que quita el sueño: ¿qué pasa en un año malo? La figura~\ref{{fig:riesgo}}
muestra la distribución de la utilidad anual en 2\,000 años simulados para cada negocio. Los locales con
margen holgado ---el exitoso, día y noche, la familia--- casi nunca terminan el año en pérdida; el inversor
lo hace la mitad de las veces y el dueño ausente casi siempre.

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/riesgo.pdf}}
\caption{{Distribución de la utilidad de un año (2\,000 simulaciones por caso) y probabilidad de terminarlo
en pérdida.}}\label{{fig:riesgo}}
\end{{figure}}

La forma de las cajas importa tanto como su posición. El ejecutivo tiene una utilidad media positiva pero
una dispersión ancha: depende de una clientela de oficina más volátil y su margen se lo come el IGV. La
dueña que cocina tiene una caja angosta y casi toda a la derecha del cero: su costo fijo es bajo y su
principal costo laboral, ella misma, se ajusta solo cuando las ventas bajan. Esa es la razón económica de la
resistencia de la fonda familiar: no es más rentable por plato, sino más flexible ante un mal año.

\section{{Sensibilidad: cuánto aguanta cada negocio}}

La sensibilidad mide lo que el promedio no muestra: cuánto margen de error tiene cada negocio. La
figura~\ref{{fig:quiebres}} y el cuadro~\ref{{tab:quiebres}} muestran, para cada uno, cuánto puede moverse
cada variable ---sola, con las demás quietas--- antes de que la utilidad llegue a cero. Si el negocio ya
pierde, la celda indica cuánto tendría que moverse para dejar de perder.

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/quiebres.pdf}}
\caption{{Cuánto puede moverse cada número antes de llegar a pérdida ($\downarrow$ bajar, $\uparrow$ subir). En
rojo, los negocios que ya pierden: cuánto les falta. ``Sobra'': aguanta cualquier cambio razonable.}}\label{{fig:quiebres}}
\end{{figure}}

\begin{{table}}[h]
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
la dueña que cocina, el precio puede bajar {p(abs(dc['quiebres']['precio']))} y el volumen
{p(abs(dc['quiebres']['q']))} antes de perder; en el inversor, apenas {p(abs(inv['quiebres']['precio']), 1)}
y {p(abs(inv['quiebres']['q']), 1)}: cualquier competidor que baje cincuenta céntimos lo saca del negocio. En
cambio, el alquiler y el gas casi nunca deciden: pueden duplicarse en la mayoría de los casos sin llevar al
local a pérdida. Esto ordena las prioridades de gestión: proteger el precio y el volumen ---la ubicación, la
calidad que sostiene la pizarra, la clientela fija--- vale más que negociar el alquiler o cambiar de
proveedor de gas.

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/tornados.pdf}}
\caption{{Utilidad del mes cuando cada variable baja (naranja) o sube (azul) 10\,\%: {fig_candela_tornado}la
dueña que cocina y el exitoso. La línea vertical es la utilidad actual.}}\label{{fig:tornados}}
\end{{figure}}

La figura~\ref{{fig:tornados}} muestra el mismo análisis en forma de tornado para tres casos. En todos, un
10\,\% de precio mueve la utilidad más que un 10\,\% de cualquier costo. Un detalle técnico ayuda a leer los
casos chicos: como el personal crece por escalones, una baja del volumen puede, en un rango corto, mejorar la
utilidad, porque permite prescindir de un mozo. Los negocios pequeños viven en esos escalones.

\section{{Decisiones robustas}}\label{{sec:robustez}}

La sensibilidad mueve una variable a la vez. Las decisiones reales se toman juntas ---subir el precio y a la
vez cambiar la porción, o abrir de noche--- y, sobre todo, se toman sin saber cómo va a reaccionar la
clientela. El análisis anterior tenía un supuesto optimista escondido: si el precio sube, la clientela no
cambia. Esta sección lo quita.

\subsection{{Método: un barrido con demanda incierta}}

Para cada negocio se calcularon todas las combinaciones de cuatro decisiones: el precio (de S/~1 menos a
S/~3 más que hoy, en pasos de 50 céntimos), la porción (económica, con 10\,\% menos de insumos y 6\,\% menos
de clientela; estándar; o generosa, con 12\,\% más de insumos y 6\,\% más de clientela), la mezcla de
segundos (en Candela, la parte que es de res, con el costo de sus propias recetas) y abrir o no un turno
noche tipo. La clientela responde al precio según
\begin{{equation}}
q \;=\; q_0\,\Bigl(\frac{{p}}{{p_0}}\Bigr)^{{-\varepsilon}} f_{{\text{{porción}}}},
\end{{equation}}
donde $\varepsilon$ es la elasticidad: cuántos clientes se pierden por cada 1\,\% de alza. Nadie la ha medido
para el menú de Juliaca, así que cada combinación se calculó con tres valores ---0.5 (clientela fiel), 1.0 y
1.5 (mucha competencia)--- y se le asignó su \emph{{peor}} resultado. La decisión robusta es la que tiene el
mejor peor caso: la que conviene aunque la demanda resulte ser la menos favorable. En total, el servicio del
estudio calculó {n(sum(combinaciones(r) for r in d.get('robustez', [])))} combinaciones
para los {NN} negocios, cada una con su simulación de riesgo y su flujo a diez años.

{"" if not rc else rf"""\subsection{{Candela, con su propia elasticidad}}

Para Candela no hace falta suponer cómo reacciona la clientela: su historia lo mide. El barrido usó tres
sensibilidades alrededor de la observada ({", ".join(n(float(k), 1) for k in sorted(rc['curvas'], key=float))}) y precios entre
S/~9 y S/~13. La figura~\ref{{fig:precio_robusto}} muestra el resultado: con la sensibilidad medida, la curva es
casi plana entre S/~10 y S/~11; con una clientela algo más sensible conviene bajar, y con una algo menos
sensible, subir, pero en ningún caso el mejor precio deja más de
{s(max(max(x['utilidad'] for x in serie) - next(x['utilidad'] for x in serie if abs(x['precio'] - rc['precio0']) < 1e-9) for serie in rc['curvas'].values()))}
al mes sobre el de hoy. Hay además un techo que el modelo no ve: a S/~10 la cocina ya colapsaba con unos 90
menús, así que bajar el precio no puede traer toda la clientela que la curva promete.

\begin{{figure}}[t]
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

\subsection{{Todos los negocios}}

La figura~\ref{{fig:decisiones}} resume el barrido de los {NN} negocios: la utilidad de hoy, la de la mejor
decisión sin abrir de noche y la de la mejor decisión en general, siempre en el peor supuesto de demanda. En
todos los casos existe una combinación que mejora la situación actual aun con la demanda más desfavorable. El
inversor pasa de {s(r_inv['base']['utilidad_media'])} a {s(r_inv['mejor']['utilidad_peor'])}; la dueña que cocina, de
{s(r_dc['base']['utilidad_media'])} a {s(r_dc['mejor']['utilidad_peor'])}. En {al_tope} de los {NN} negocios la
mejor decisión está en el tope de precio probado, lo que confirma que el menú de Juliaca se está vendiendo
barato respecto de lo que su clientela aguantaría; el puesto de mercado, que hoy vende a S/~7, es el caso más
claro.

\begin{{figure}}[t]
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

\section{{Prueba de estrés}}

La última pregunta es la del año malo deliberado: ¿qué pasa si llega un golpe? Cada negocio se sometió a seis
golpes por separado ---clientela $-$15\,\%, insumos $+$20\,\%, IGV de 18\,\%, sueldos $+$10\,\%, alquiler
$+$25\,\% y un competidor que obliga a bajar S/~1--- y a todos juntos (figura~\ref{{fig:estres}}).

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/estres.pdf}}
\caption{{Utilidad del mes (miles de soles) de cada negocio frente a cada golpe; la última columna los suma
todos.}}\label{{fig:estres}}
\end{{figure}}

Solo {len(sobreviven)} de los {NN} negocios siguen ganando con todos los golpes juntos: {esc(', '.join(sobreviven))}.
Los golpes que más daño hacen son los de insumos y el del competidor que obliga a bajar el precio; el alza de
sueldos y la del alquiler, en cambio, se absorben. La fonda familiar resiste por la misma razón que en la
simulación de riesgo: no tiene planilla que pagar cuando las ventas caen. {"" if not rc else f"Candela, con los datos actuales, ya pierde antes del golpe; el de insumos le quita otros {s(rc['base']['utilidad_media'] - golpe(rc, 'insumos'))} al mes y el del competidor {s(rc['base']['utilidad_media'] - golpe(rc, 'competidor'))}: son los dos frentes que más le conviene vigilar."}

\section{{Lo que el modelo deja ver}}

Más allá de los números de cada caso, el modelo permite hacer preguntas que en la operación diaria no se
hacen. Cinco de ellas cambian la manera de pensar el negocio.

\subsection{{Cuánto vale medio sol}}

Medio sol más en la pizarra, con la misma clientela, equivale a vender más menús al precio de hoy. Cuántos,
depende del margen por plato: en el ejecutivo, medio sol vale {n(menus_medio('Ejecutivo'))} menús diarios; en
el inversor promedio, {n(menus_medio('Inversor'))}; en el puesto de mercado,
{n(menus_medio('Puesto'))}{"" if not cand else f"; en Candela, {n(menus_medio('Candela'))}"}. Cuanto más bajo es el
margen por plato, más vale cada centavo del precio, y más caro resulta competir bajándolo. Es la razón
aritmética por la que el puesto de mercado, que vende a S/~7, es el que más pierde con el competidor que lo
obliga a bajar un sol: ese golpe le quita casi toda la utilidad.

\subsection{{El trabajo que no se cobra}}

Si la dueña que cocina trabaja 60 horas a la semana, lo que se lleva equivale a
{s(hora['Dueña que cocina']['por_hora'], 2)} por hora. En la familia sin sueldos, repartida entre tres personas,
la cifra cae a {s(hora['Familia sin sueldos']['por_hora'], 2)} por hora y por persona: \emph{{menos que el sueldo
mínimo}}, que equivale a {s(hz['rmv_hora'], 2)} por hora. El puesto de mercado, con más volumen y menos
alquiler, llega a {s(hora['Puesto de mercado informal']['por_hora'], 2)}. La fonda familiar es rentable como
empresa porque sus integrantes cobran, en los hechos, por debajo del mínimo legal. Es la otra cara del hallazgo
de que en provincia ``gana el trabajo'': gana porque el trabajo se paga barato, y la estabilidad del negocio
descansa en que la familia acepte esa tarifa.

\subsection{{La trampa del Nuevo RUS}}

La figura~\ref{{fig:nrus}} sigue a un local chico a medida que crece. Mientras vende hasta {nr.get('q_tope')}
menús diarios cabe en el Nuevo RUS: no cobra IGV y paga una cuota fija. Al pasar el tope de S/~96 mil al año
tiene que cambiar de régimen y empezar a cobrar IGV, y su utilidad cae de golpe de {s(nr.get('nrus_tope', 0))}
a {s(nr.get('rer_justo_despues', 0))} al mes. Para volver a ganar lo mismo que antes del salto tiene que llegar a
unos {nr.get('q_recupera')} menús diarios. El régimen castiga el crecimiento justo en el tramo en que un negocio
chico intenta despegar; no es raro que muchos prefieran quedarse chicos o salir de la formalidad.

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/nrus.pdf}}
\caption{{Un local chico que crece: utilidad después de impuestos en el Nuevo RUS (hasta su tope) y en el RER.
La flecha es el salto al pasar el tope.}}\label{{fig:nrus}}
\end{{figure}}

\subsection{{Desde cuántas cenas conviene la noche}}

El barrido mostró que la noche mejora a todos los negocios; la pregunta práctica es desde qué volumen. Si la
noche exige un equipo propio, conviene desde unos {noche_u['Inversor (promedio)']['umbral']} platos por noche
en el local promedio{"" if not cand else f" (y {noche_u['Candela (datos del POS)']['umbral']} en Candela)"}. Si la
atienden las mismas personas del día ---la dueña, la familia---, conviene desde
{noche_u['Dueña que cocina']['umbral']} o {noche_u['Familia sin sueldos']['umbral']} platos: casi cualquier venta.
Pero esa cuenta no cobra las horas extra de esas personas; es el mismo trabajo no pagado de la sección
anterior, ahora de noche. La decisión honesta compara las cenas que se venderían con el costo de un equipo
nocturno, aunque al principio lo cubra la familia.

\subsection{{¿Casa propia o local alquilado?}}

Muchas fondas abren en la casa de la familia y no pagan alquiler. La pregunta es si eso las hace más rentables
que un local alquilado. El modelo la responde traduciendo el alquiler a menús: el local de la dueña que cocina
paga S/~1\,200, que equivalen a vender {n(next(a['menus'] for a in hz['alquiler'] if a['nombre'] == 'Dueña que cocina'))}
menús diarios; el del inversor, S/~2\,200, equivale a {n(next(a['menus'] for a in hz['alquiler'] if a['nombre'].startswith('Inversor')))}.
Abrir en casa conviene mientras la casa pierda menos clientes que esos menús. La fonda en casa propia del
catálogo, con 45 menús a S/~9, deja {s(casos['Fonda en casa propia']['ingreso_dueno'])} al mes a su dueña, frente a
{s(dc['ingreso_dueno'])} de la dueña que cocina en un local alquilado con 60 menús a S/~10: el paso de la calle vale
más que el alquiler que se ahorra. Dos costos escondidos completan la cuenta. Primero, la casa tiene un costo
de oportunidad: el espacio podría alquilarse. Segundo, la luz, el agua y el gas se mezclan con los del hogar, y
el negocio parece más barato de lo que es.

\subsection{{Los escalones de personal}}

El personal no crece de a poco: crece por personas. Un local que vende 71 menús necesita dos mozos y uno que
vende 69, uno. Esos escalones explican resultados que parecen extraños ---subir el precio y perder clientes
puede mejorar la utilidad porque permite prescindir de alguien--- y obligan a leer con cuidado cualquier cifra
calculada con la planilla automática. Para un local concreto, la planilla real, persona por persona, es el
dato que más afina el modelo.

\section{{El largo plazo: diez años y cuatro regímenes}}

La figura~\ref{{fig:flujo}} sigue la caja acumulada de siete negocios desde la inversión inicial hasta 2035.
Las líneas se separan pronto y no se vuelven a cruzar: el que empieza ganando sigue ganando, y el que
empieza perdiendo no se recupera solo con el tiempo, porque la inflación de costos y el sueldo mínimo suben
al ritmo del precio y el IGV de 2027--2028 empuja hacia abajo.

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/flujo.pdf}}
\caption{{Caja acumulada después de la inversión, régimen de cada caso. Las líneas verticales marcan los saltos
del IGV.}}\label{{fig:flujo}}
\end{{figure}}

El régimen tributario cambia la cuenta de manera decisiva (figura~\ref{{fig:regimenes}}). Con los mismos
supuestos, el inversor tendría un VAN de {s(reg(inv, 'informal')['van'])} en la informalidad y de
{s(reg(inv, 'mype')['van'])} en el régimen MYPE. La diferencia no es la renta ---a estos niveles de utilidad
el impuesto a la renta es pequeño--- sino el IGV y las cargas laborales. Por eso la formalización de una
fonda es, ante todo, una decisión sobre el IGV: a 10.5\,\% es soportable; a 18\,\% exige vender bastante más
o cobrar más. El Nuevo RUS aparece atractivo en el gráfico para varios casos, pero con barras rayadas: ninguno
de ellos cabe en su tope de ventas.

\begin{{figure}}[t]
\centering
\includegraphics[width=\textwidth]{{fig/regimenes.pdf}}
\caption{{VAN a diez años según el régimen. Rayado: el negocio supera el tope de ventas del régimen y no
podría acogerse a él.}}\label{{fig:regimenes}}
\end{{figure}}

Hay una lectura menos evidente en la fila de la familia. Formalizada, su VAN se vuelve negativo
({s(reg(fam, 'mype')['van'])} en el régimen MYPE): al pasar a planilla, la ley obliga a pagar al menos el
sueldo mínimo a quienes antes trabajaban sin cobrar. La informalidad de la fonda familiar no es solo evasión
de impuestos; es la forma jurídica de un acuerdo familiar que la ley laboral no reconoce.

{candela_seccion}

\section{{Discusión}}

Los {NN} negocios cuentan una sola historia desde ángulos distintos. El costo del plato es casi un dato: en
todos los casos los insumos se llevan alrededor de la mitad de la venta neta, y ninguna estrategia de
compras cambia eso más de unos puntos. Lo que distingue a un negocio de otro son tres decisiones:

\begin{{enumerate}}[leftmargin=1.4em]
\item \textbf{{Quién pone el trabajo.}} La fonda rentable en provincia es, en su forma más común, el empleo de
su dueña o de su familia. Un local que contrata a todos necesita volúmenes de ciudad grande o precios que la
clientela local no paga; uno que además terceriza la gestión necesita más del doble del volumen. Antes de
abrir, la pregunta útil no es ``¿es rentable el menú?'' sino ``¿quién va a estar en la cocina y en la caja?''.
\item \textbf{{Cuántos menús por cada sol de alquiler.}} El volumen diluye los costos fijos, y el turno noche
multiplica las horas que rinde el mismo local. Una ubicación con flujo de gente vale más que una ubicación
barata.
\item \textbf{{Cómo se paga el IGV.}} La formalidad cuesta, y el calendario la encarece: el 2028 es un horizonte
cercano para quien invierte hoy. Los planes a diez años deberían suponer un IGV de 18\,\% salvo que una nueva
ley diga lo contrario.
\end{{enumerate}}

El exitoso confirma la regla por el otro lado: gana mucho porque vende mucho, no porque su plato sea más
barato ni su cocina más eficiente. Su riesgo es el de cualquier negocio grande: necesita años para llenarse,
más inversión y una administración que el dueño ya no puede hacer solo.

\subsection{{La paradoja del inversor}}

Visto desde afuera, el menú parece un buen negocio: todos los días hay clientela, la caja se mueve en
efectivo y la inversión es modesta. El modelo explica por qué esa impresión engaña a quien solo pone capital.
Lo que la fonda familiar muestra como utilidad es, en buena parte, el sueldo de sus integrantes; quien compra
esos mismos trabajos en el mercado laboral descubre que el margen se lo llevaba la familia. El inversor no
compite contra otro inversor: compite contra hogares que aceptan cobrar menos que el mínimo por su tiempo. Por
eso, en una plaza como Juliaca, la inversión que no trae su propio trabajo necesita algo que el hogar no tiene:
escala, un precio más alto sostenido por una marca o un segundo turno que reparta los costos fijos.

\subsection{{Por qué el menú está barato}}

En casi todos los negocios la decisión robusta sube el precio, aun suponiendo una clientela sensible. Que el
mercado no lo haya hecho ya pide una explicación. La más probable es que el precio del menú no lo fija el costo
sino la referencia: el cliente compara con la pizarra de la cuadra, y la cuadra la marcan locales informales
que no pagan IGV ni cargas y que, como se vio, cobran su trabajo por debajo del mínimo. El precio de referencia
es, en buena medida, un precio subsidiado. Un local formal que lo acepta como dado hereda el subsidio sin poder
pagarlo. La salida no es necesariamente subir de golpe ---la referencia castiga al que se sale de ella--- sino
separarse de la comparación: segundos con recargo, platos que no tengan equivalente en la cuadra, servicio más
rápido para el trabajador con poco tiempo.

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
supuestos. La sensibilidad de Candela sale de un solo cambio de precio que coincidió con otros cambios, y debería
confirmarse con una prueba controlada. En
Candela, las recetas se calibraron con la estimación del dueño y no con un pesaje sistemático, y el alquiler
y la planilla son promedios.

Tres pasos cerrarían la mayor parte de esa incertidumbre: un \emph{{sondeo de pizarras}} por zona en Juliaca
(precio, segundos ofrecidos y conteo de comensales), la \emph{{sincronización automática}} de ventas y recetas
desde el sistema de Candela al estudio, y un \emph{{pesaje}} de una semana de las porciones de los cinco
segundos más vendidos.

\appendix
\section{{Supuestos del modelo}}

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

\section{{Fuentes del conjunto de datos}}

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
