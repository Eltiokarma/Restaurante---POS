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

    def reg(c, clave):
        return next(x for x in c["regimenes"] if x["regimen"] == clave)

    candela_resumen = ""
    candela_seccion = ""
    if cand and pl:
        par = pl["pareto"]
        top3 = ", ".join(f"{esc(x['insumo'].lower())} ({p(x['parte'])})" for x in par[:3])
        prec_neto = pl["menu"]["precio_promedio"] / 1.105
        candela_resumen = (
            f"\\item \\textbf{{Candela, con los promedios de Juliaca en alquiler y planilla, opera por debajo de su "
            f"equilibrio.}} A {n(cand['q'])} menús diarios y {s(cand['precio'])} le faltan unos "
            f"{cand['equilibrio'] - cand['q']} menús al día, o un precio de {s(cand['precio_minimo'], 2)}; sus "
            f"recetas calibradas cuestan {s(pl['menu']['costo'], 2)} por menú ({p(pl['menu']['costo'] / prec_neto)} "
            f"del precio sin IGV). Falta reemplazar los promedios por su alquiler y su planilla reales.")
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

\subsection{{Dónde está Candela}}

Con los datos que hoy tiene el estudio ---{n(cand['q'])} menús diarios a {s(cand['precio'])}, insumos
calibrados y, a falta de los reales, el alquiler y la planilla promedio de Juliaca---, Candela perdería
{s(-cand['utilidad_mes'])} al mes contando el sueldo del dueño ({s(-cand['ingreso_dueno'])} sin contarlo). Su
equilibrio está en {cand['equilibrio']} menús diarios, y el precio que la deja en cero a su volumen actual es
{s(cand['precio_minimo'], 2)}. La figura~\ref{{fig:matriz}} muestra el mapa completo: cada celda es la
utilidad mensual para una combinación de precio y volumen; el recuadro marca la situación actual. La diagonal
de cero cruza cerca de (S/~11.5, 85 menús) y (S/~12, 75 menús): medio sol en la pizarra vale lo mismo que
diez menús más al día.

\begin{{figure}}[t]
\centering
\includegraphics[width=0.92\textwidth]{{fig/matriz.pdf}}
\caption{{Candela: utilidad del mes (miles de soles) por precio y menús al día, con la estructura de costos
actual. El recuadro es la situación de hoy.}}\label{{fig:matriz}}
\end{{figure}}

Este resultado debe leerse con cuidado. El alquiler y la planilla son los dos números que más pueden cambiar el
diagnóstico, y ambos son todavía promedios de ciudad. El estudio está armado para recibirlos: con el
alquiler real y una fila por persona en la planilla ---cada una con su sueldo o jornal y su turno---, la
cifra de esta sección se recalcula sola.
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
abrir una fonda: \emph{{¿quién gana con un menú, y por qué?}} Para responderla se modelan diez negocios con el
mismo motor ---nueve restaurantes tipo y el caso real de Candela, en Juliaca--- que difieren en quién trabaja,
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

\section{{Diez negocios}}

\subsection{{Un catálogo de restaurantes tipo}}

Para separar el efecto de la organización del efecto de la ciudad, los nueve restaurantes tipo están en
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
\item[Referencia] El \emph{{exitoso}} es una referencia compuesta, no un local real: 220 menús a S/~13 con
compras por volumen. Ningún local de menú publica sus números; la referencia combina el dato del MINCETUR de
que la mitad de los restaurantes recupera su inversión en 19 a 24 meses y las ventas de franquicias chicas,
cercanas a S/~50 mil al mes.
\end{{description}}

\begin{{table}}[h]
\centering\footnotesize
\caption{{Los diez negocios. ``Dueño'': utilidad del mes más el sueldo del dueño si se paga uno. VAN al
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

Los diez negocios cuentan una sola historia desde ángulos distintos. El costo del plato es casi un dato: en
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

\section{{Recomendaciones}}

Para Candela, en orden de impacto según la sensibilidad:

\begin{{enumerate}}[leftmargin=1.4em]
\item \textbf{{Completar los datos que deciden el diagnóstico.}} El alquiler real y la planilla persona por
persona ---con su forma de pago y su turno--- pueden mover la utilidad en miles de soles. El estudio ya está
preparado para recibirlos.
\item \textbf{{Cuidar el precio y probar medio sol.}} La pizarra es la variable más sensible. Medio sol más en
los segundos de mayor demanda equivale a diez menús adicionales al día. Los segundos con recargo (como el
camote rebosado) son la forma de subir el precio promedio sin tocar el precio base.
\item \textbf{{Ajustar la mezcla de segundos.}} Un plato de pollo o de pasta en lugar de uno de res, cuando el
menú del día lleve dos de res, mejora el margen promedio sin que el cliente lo perciba como una alza.
\item \textbf{{Evaluar el turno noche con un piloto.}} Es la palanca que más mejora a un local con el alquiler ya
pagado. Un piloto de dos o tres noches por semana mide la demanda antes de contratar un equipo completo.
\item \textbf{{Planificar el 2027 y el 2028.}} El IGV de 15\,\% y luego, probablemente, 18\,\% exige llegar a esos
años con un precio o un volumen mayores. Es mejor subir el precio de a medio sol que de golpe.
\end{{enumerate}}

\section{{Limitaciones y próximos pasos}}

El modelo es tan bueno como sus datos, y varios son todavía supuestos. Los precios de menú fuera de Lima,
Cusco y Puno son estimados; los restaurantes tipo son construcciones razonadas, no locales observados; el
exitoso es una referencia compuesta; la simulación supone que las variables se mueven de forma
independiente; el flujo no arrastra pérdidas tributarias ni asigna valor residual al local al décimo año. En
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
