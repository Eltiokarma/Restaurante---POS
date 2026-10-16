"""Gráficas del ensayo (PDF vectorial, misma tipografía que el texto)."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

SALIDA = Path(__file__).resolve().parent / "salida"
FIG = SALIDA / "fig"

# Paleta (orden fijo) y tinta
AZUL, NARANJA, AGUA, AMARILLO, MAGENTA, VERDE, VIOLETA, ROJO = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
PERDIDA = "#c2372f"
TINTA, TINTA2, GRILLA = "#1b1b1a", "#5b5a56", "#e6e4de"
ANCHO = 6.3  # pulgadas: el ancho de texto del documento

for f in Path("/usr/share/texmf/fonts/opentype/public/lm").glob("lmroman*.otf"):
    font_manager.fontManager.addfont(str(f))
plt.rcParams.update({
    "font.family": "Latin Modern Roman", "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9.5,
    "axes.edgecolor": TINTA2, "axes.labelcolor": TINTA, "xtick.color": TINTA2, "ytick.color": TINTA2,
    "text.color": TINTA, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "axes.grid": False, "legend.frameon": False,
    "pdf.fonttype": 3, "figure.dpi": 150,
})


def soles(v: float, pos=None) -> str:
    a = abs(v)
    if a >= 1e6:
        s = f"{a / 1e6:.1f} M".replace(".0 M", " M")
    elif a >= 10000:
        s = f"{a / 1000:,.0f} mil"
    elif a >= 1000:
        s = f"{a / 1000:,.1f} mil".replace(".0 mil", " mil")
    else:
        s = f"{a:,.0f}"
    return ("−" if v < 0 else "") + "S/ " + s


def miles(v: float, pos=None) -> str:
    return ("−" if v < 0 else "") + f"{abs(v) / 1000:g}"


def pct(v: float, pos=None) -> str:
    return f"{v * 100:.0f} %"


def corto(nombre: str) -> str:
    return (nombre.replace(" (referencia compuesta)", "").replace(" (todo tercerizado)", "")
            .replace(" (promedio)", "").replace(" (datos del POS)", ""))


def guardar(fig, nombre: str) -> None:
    fig.savefig(FIG / f"{nombre}.pdf", bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def grilla_x(ax):
    ax.xaxis.grid(True, color=GRILLA, linewidth=0.6)
    ax.set_axisbelow(True)


def todos(d: dict) -> list[dict]:
    return d["casos"] + ([d["candela"]] if d.get("candela") else [])


# ---------------------------------------------------------------- ciudades

def fig_ciudades(d):
    cs = d["ciudades"]
    fig, ax = plt.subplots(figsize=(ANCHO, 3.4))
    y = range(len(cs))
    ax.barh([i + 0.2 for i in y], [c["eq_2026"] for c in cs], height=0.38, color=AZUL, label="Formal (IGV 10.5 %)")
    ax.barh([i - 0.2 for i in y], [c["eq_informal"] for c in cs], height=0.38, color=NARANJA, label="Informal")
    for i, c in enumerate(cs):
        ax.text(c["eq_2026"] + 2, i + 0.2, str(c["eq_2026"]), va="center", fontsize=8, color=TINTA2)
        ax.text(c["eq_informal"] + 2, i - 0.2, str(c["eq_informal"]), va="center", fontsize=8, color=TINTA2)
    ax.set_yticks(list(y), [f"{c['nombre'].replace(' Metropolitana', '')} (S/ {c['precio']:g})" for c in cs])
    ax.invert_yaxis()
    ax.set_xlabel("Menús al día para no perder")
    grilla_x(ax)
    ax.legend(loc="upper right")
    guardar(fig, "ciudades")


def fig_igv(d):
    cs = [c for c in d["ciudades"] if c["id"] in ("lima", "arequipa", "cusco", "puno", "juliaca")]
    fig, ax = plt.subplots(figsize=(ANCHO * 0.62, 2.6))
    colores = [AZUL, NARANJA, AGUA, VIOLETA, ROJO]
    for c, col in zip(cs, colores):
        ys = [c["eq_2026"], c["eq_2027"], c["eq_2028"]]
        ax.plot([2026, 2027, 2028], ys, color=col, lw=2, marker="o", ms=4)
        ax.text(2028.08, ys[-1], f"{c['nombre'].replace(' Metropolitana', '')} {ys[-1]}", va="center",
                fontsize=8.5, color=TINTA)
    ax.set_xticks([2026, 2027, 2028], ["2026\nIGV 10.5 %", "2027\nIGV 15 %", "2028\nIGV 18 %*"])
    ax.set_xlim(2025.85, 2028.75)
    ax.set_ylabel("Menús al día para no perder")
    ax.yaxis.grid(True, color=GRILLA, lw=0.6)
    guardar(fig, "igv")


# ---------------------------------------------------------------- casos

def fig_ingreso(d):
    cs = sorted(todos(d), key=lambda c: c["ingreso_dueno"])
    fig, ax = plt.subplots(figsize=(ANCHO, 3.3))
    vals = [c["ingreso_dueno"] for c in cs]
    cols = [PERDIDA if v < 0 else (NARANJA if c["nombre"].startswith("Candela") else AZUL) for v, c in zip(vals, cs)]
    ax.barh(range(len(cs)), vals, color=cols, height=0.62)
    ax.axvline(0, color=TINTA2, lw=0.8)
    for i, v in enumerate(vals):
        if v < -2000:  # dentro de la barra, para no pisar el nombre
            ax.text(v / 2, i, soles(v), va="center", ha="center", fontsize=8.5, color="white")
        else:
            ax.text(v + (400 if v >= 0 else -400), i, soles(v), va="center", ha="left" if v >= 0 else "right",
                    fontsize=8.5, color=TINTA)
    ax.set_yticks(range(len(cs)), [corto(c["nombre"]) for c in cs])
    ax.xaxis.set_major_formatter(FuncFormatter(soles))
    ax.set_xlabel("Utilidad del mes + sueldo del dueño (si se paga uno)")
    lo, hi = min(vals), max(vals)
    ax.set_xlim(lo * 1.35 if lo < 0 else 0, hi * 1.18)
    grilla_x(ax)
    guardar(fig, "ingreso")


def fig_estructura(d):
    cs = sorted(todos(d), key=lambda c: -c["estructura"]["utilidad"])
    partes = [("insumos", "Insumos", AMARILLO), ("personal", "Personal", AZUL), ("alquiler", "Alquiler", VIOLETA),
              ("gas", "Gas", NARANJA), ("otros", "Luz, agua y otros", "#9a988f")]
    fig, ax = plt.subplots(figsize=(ANCHO, 3.5))
    for i, c in enumerate(cs):
        x = 0.0
        for clave, _, col in partes:
            v = c["estructura"][clave]
            ax.barh(i, v, left=x, color=col, height=0.62, edgecolor="white", linewidth=0.8)
            if v >= 0.07:
                ax.text(x + v / 2, i, f"{v * 100:.0f}", ha="center", va="center", fontsize=7.5,
                        color="white" if col in (AZUL, VIOLETA) else TINTA)
            x += v
        u = c["estructura"]["utilidad"]
        ax.text(max(x, 1) + 0.015, i, f"{'utilidad' if u >= 0 else 'pérdida'} {abs(u) * 100:.0f} %", va="center",
                fontsize=8, color=VERDE if u >= 0 else PERDIDA)
    ax.axvline(1, color=TINTA, lw=0.9, ls=(0, (3, 2)))
    ax.text(1, -0.85, "100 % de la venta sin IGV", ha="center", fontsize=8, color=TINTA2)
    ax.set_yticks(range(len(cs)), [corto(c["nombre"]) for c in cs])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(pct))
    ax.set_xlim(0, 1.55)
    ax.legend(handles=[Patch(color=col, label=nombre) for _, nombre, col in partes], ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=8.5, handlelength=1, columnspacing=1)
    guardar(fig, "estructura")


def fig_riesgo(d):
    cs = sorted(todos(d), key=lambda c: c["mc"]["p50"])
    fig, ax = plt.subplots(figsize=(ANCHO, 3.5))
    datos = [c["mc"]["muestras"] for c in cs]
    bp = ax.boxplot(datos, orientation="horizontal", whis=(5, 95), showfliers=False, patch_artist=True, widths=0.55,
                    medianprops={"color": TINTA, "lw": 1.2}, whiskerprops={"color": TINTA2, "lw": 0.8},
                    capprops={"color": TINTA2, "lw": 0.8})
    for caja, c in zip(bp["boxes"], cs):
        caja.set_facecolor(NARANJA if c["nombre"].startswith("Candela") else AZUL)
        caja.set_alpha(0.75)
        caja.set_edgecolor("white")
    ax.axvline(0, color=PERDIDA, lw=0.9)
    for i, c in enumerate(cs, start=1):
        ax.text(1.02, i, f"{c['mc']['prob_perdida'] * 100:.0f} %", transform=ax.get_yaxis_transform(), va="center",
                fontsize=8.5, color=PERDIDA if c["mc"]["prob_perdida"] >= 0.3 else TINTA2)
    ax.text(1.02, len(cs) + 0.75, "P(pérdida)", transform=ax.get_yaxis_transform(), fontsize=8, color=TINTA2)
    ax.set_yticks(range(1, len(cs) + 1), [corto(c["nombre"]) for c in cs])
    ax.xaxis.set_major_formatter(FuncFormatter(soles))
    ax.set_xlabel("Utilidad de un año simulado (2 000 años por caso; caja = P25–P75, bigotes = P5–P95)")
    grilla_x(ax)
    guardar(fig, "riesgo")


def fig_quiebres(d):
    cs = todos(d)
    variables = [("precio", "Precio"), ("q", "Menús/día"), ("insumos", "Insumos"), ("sueldos", "Sueldos"),
                 ("alquiler_mes", "Alquiler"), ("dias", "Días"), ("gas", "Gas")]
    fig, ax = plt.subplots(figsize=(ANCHO, 3.6))
    cmap = LinearSegmentedColormap.from_list("holgura", ["#f3d2c4", "#fbf0d6", "#e3f1e7", "#9fd3b2"])
    for i, c in enumerate(cs):
        pierde = c["utilidad_mes"] < 0
        for j, (k, _) in enumerate(variables):
            x = c["quiebres"].get(k)
            if pierde:
                color, texto = "#f6c9c2", ("falta " + f"{abs(x) * 100:.0f} %" if x is not None else "no alcanza")
            elif x is None:
                color, texto = "#9fd3b2", "sobra"
            else:
                color = cmap(min(abs(x), 0.6) / 0.6)
                texto = ("↓ " if x < 0 else "↑ ") + f"{abs(x) * 100:.0f} %"
            ax.add_patch(plt.Rectangle((j, i), 0.96, 0.92, color=color, lw=0))
            ax.text(j + 0.48, i + 0.46, texto, ha="center", va="center", fontsize=7.6,
                    color=PERDIDA if pierde else TINTA)
    ax.set_xlim(0, len(variables))
    ax.set_ylim(len(cs), 0)
    ax.set_xticks([j + 0.48 for j in range(len(variables))], [n for _, n in variables])
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.46 for i in range(len(cs))], [corto(c["nombre"]) for c in cs])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    guardar(fig, "quiebres")


def fig_tornados(d):
    elegidos = [c for c in todos(d) if c["nombre"].startswith(("Candela", "Dueña", "Exitoso"))]
    fig, axs = plt.subplots(1, len(elegidos), figsize=(ANCHO, 2.6), sharey=False)
    for ax, c in zip(axs, elegidos):
        filas = c["tornado"][:6][::-1]
        base = filas[0]["base"]
        for i, f in enumerate(filas):
            ax.barh(i, f["abajo"] - base, left=base, color=NARANJA, height=0.6)
            ax.barh(i, f["arriba"] - base, left=base, color=AZUL, height=0.6)
        ax.axvline(base, color=TINTA, lw=0.8)
        ax.set_yticks(range(len(filas)), [f["nombre"].replace("Luz, agua e internet", "Luz y agua") for f in filas],
                      fontsize=8)
        ax.set_title(corto(c["nombre"]), fontsize=9.5)
        ax.xaxis.set_major_formatter(FuncFormatter(miles))
        ax.tick_params(axis="x", labelsize=7.5)
        ax.locator_params(axis="x", nbins=4)
        ax.set_xlabel("utilidad del mes (miles de S/)", fontsize=7.5)
        grilla_x(ax)
    fig.legend(handles=[Patch(color=NARANJA, label="el número baja 10 %"), Patch(color=AZUL, label="sube 10 %")],
               loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.08), fontsize=8.5)
    fig.tight_layout(w_pad=1.2)
    guardar(fig, "tornados")


def fig_flujo(d):
    nombres = ("Dueña que cocina", "Familia sin sueldos", "Inversor (promedio)", "Puesto de mercado informal",
               "Día y noche", "Ejecutivo en el centro")
    cs = [c for c in d["casos"] if c["nombre"] in nombres] + ([d["candela"]] if d.get("candela") else [])
    colores = [AZUL, AGUA, VIOLETA, AMARILLO, VERDE, MAGENTA, NARANJA]
    fig, ax = plt.subplots(figsize=(ANCHO, 3.1))
    finales = []
    for c, col in zip(cs, colores):
        xs = [2025] + [a["anio"] for a in c["flujo"]["anios"]]
        ys = [-c["inversion"]] + [a["acumulado"] for a in c["flujo"]["anios"]]
        ax.plot(xs, ys, color=col, lw=1.8)
        finales.append([ys[-1], corto(c["nombre"]), col])
    # rótulos al final sin pisarse (separación mínima en unidades del eje)
    lo, hi = ax.get_ylim()
    sep = (hi - lo) * 0.055
    finales.sort(key=lambda f: f[0])
    for i in range(1, len(finales)):
        finales[i][0] = max(finales[i][0], finales[i - 1][0] + sep)
    for y, nombre, col in finales:
        ax.text(2035.15, y, nombre, va="center", fontsize=8, color=TINTA)
    ax.axhline(0, color=TINTA2, lw=0.8)
    for x, t in ((2027, "IGV 15 %"), (2028, "IGV 18 %")):
        ax.axvline(x, color=GRILLA, lw=0.8, ls=(0, (2, 2)))
        ax.text(x + (-0.06 if x == 2027 else 0.06), hi, t, fontsize=7.5, color=TINTA2, va="top",
                ha="right" if x == 2027 else "left")
    ax.set_xticks(range(2025, 2036), ["inicio"] + [str(a) for a in range(2026, 2036)], fontsize=8)
    ax.set_xlim(2024.8, 2037.6)
    ax.yaxis.set_major_formatter(FuncFormatter(soles))
    ax.set_ylabel("Caja acumulada (después de la inversión)")
    ax.yaxis.grid(True, color=GRILLA, lw=0.6)
    guardar(fig, "flujo")


def fig_regimenes(d):
    cs = [c for c in todos(d) if c["nombre"].startswith(("Dueña", "Inversor", "Exitoso", "Candela", "Día y noche"))]
    regs = [("informal", "Informal", NARANJA), ("nuevo_rus", "Nuevo RUS", AMARILLO), ("rer", "RER", AGUA),
            ("mype", "MYPE", AZUL)]
    fig, ax = plt.subplots(figsize=(ANCHO, 2.9))
    w = 0.2
    for j, (clave, nombre, col) in enumerate(regs):
        xs, ys, hatch = [], [], []
        for i, c in enumerate(cs):
            r = next(x for x in c["regimenes"] if x["regimen"] == clave)
            xs.append(i + (j - 1.5) * w)
            ys.append(r["van"])
            hatch.append(bool(r["alertas"]))
        barras = ax.bar(xs, ys, width=w * 0.92, color=col, label=nombre)
        for b, h in zip(barras, hatch):
            if h:
                b.set_hatch("////")
                b.set_alpha(0.45)
    ax.axhline(0, color=TINTA2, lw=0.8)
    ax.set_xticks(range(len(cs)), [corto(c["nombre"]) for c in cs], fontsize=8.5)
    ax.yaxis.set_major_formatter(FuncFormatter(soles))
    ax.set_ylabel("VAN a 10 años (15 %)")
    ax.yaxis.grid(True, color=GRILLA, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(ncol=4, loc="upper left", fontsize=8.5)
    guardar(fig, "regimenes")


def fig_matriz(d):
    c = d.get("candela") or next(x for x in d["casos"] if x["nombre"].startswith("Inversor"))
    m = c["matriz"]
    fig, ax = plt.subplots(figsize=(ANCHO, 3.3))
    vmax = max(abs(v) for fila in m["utilidad"] for v in fila)
    cmap = LinearSegmentedColormap.from_list("div", ["#c2372f", "#f4f2ec", "#1f8a4c"])
    ax.imshow(m["utilidad"], cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
    for i, fila in enumerate(m["utilidad"]):
        for j, v in enumerate(fila):
            ax.text(j, i, f"{v / 1000:+.1f}", ha="center", va="center", fontsize=7.3,
                    color="white" if abs(v) > vmax * 0.6 else TINTA)
    ax.set_xticks(range(len(m["precios"])), [f"{p:.2f}".rstrip("0").rstrip(".") for p in m["precios"]], fontsize=8)
    ax.set_yticks(range(len(m["volumenes"])), m["volumenes"], fontsize=8)
    ax.set_xlabel("Precio del menú (S/)")
    ax.set_ylabel("Menús al día")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    jp = min(range(len(m["precios"])), key=lambda j: abs(m["precios"][j] - c["precio"]))
    iq = min(range(len(m["volumenes"])), key=lambda i: abs(m["volumenes"][i] - c["q"]))
    ax.add_patch(plt.Rectangle((jp - 0.5, iq - 0.5), 1, 1, fill=False, ec=TINTA, lw=1.4))
    guardar(fig, "matriz")


def fig_platos(d):
    p = d.get("platos")
    if not p:
        return
    seg = [x for x in p["platos"] if x["tipo"] == "segundo" and x["clase"] and x["popularidad"]]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(ANCHO, 3.2), gridspec_kw={"width_ratios": [1.15, 1]})
    colores = {"estrella": VERDE, "caballo": AZUL, "rompecabezas": AMARILLO, "perro": PERDIDA}
    for x in seg:
        a1.scatter(x["popularidad"] * 100, x["margen"], s=24, color=colores[x["clase"]], edgecolor="white", lw=0.6,
                   zorder=3)
    top = sorted(seg, key=lambda x: -x["popularidad"])[:6]
    for k, x in enumerate(top, start=1):
        a1.annotate(str(k), (x["popularidad"] * 100, x["margen"]), xytext=(0, 7), textcoords="offset points",
                    fontsize=7, ha="center", color=TINTA, fontweight="bold")
    clave = "   ".join(f"{k}. {x['nombre'].split(' con ')[0]}" for k, x in enumerate(top, start=1))
    fig.text(0.02, -0.04, "Más vendidos: " + clave, fontsize=7, color=TINTA2, wrap=True)
    if seg:
        a1.axvline(seg[0]["umbral_popularidad"] * 100, color=TINTA2, lw=0.7, ls=(0, (3, 2)))
        a1.axhline(seg[0]["margen_promedio"], color=TINTA2, lw=0.7, ls=(0, (3, 2)))
    for k, n in (("estrella", "Estrella"), ("caballo", "Caballito"), ("rompecabezas", "Rompecabezas"),
                 ("perro", "Perro")):
        a1.scatter([], [], color=colores[k], label=n, s=20)
    a1.legend(fontsize=7.5, loc="upper right", handletextpad=0.2)
    a1.set_xlabel("Parte de las ventas de segundos (%)")
    a1.set_ylabel("Margen por menú (S/)")
    a1.set_title("Ingeniería de menú", fontsize=9.5)
    par = p["pareto"][:10][::-1]
    a2.barh(range(len(par)), [x["parte"] * 100 for x in par], color=AMARILLO, height=0.65)
    for i, x in enumerate(par):
        a2.text(x["parte"] * 100 + 0.4, i, f"{x['parte'] * 100:.0f} %", va="center", fontsize=7.5)
    a2.set_yticks(range(len(par)), [x["insumo"] for x in par], fontsize=7.5)
    a2.set_xlabel("Parte del gasto semanal en insumos")
    a2.set_title("En qué se va la plata", fontsize=9.5)
    a2.set_xlim(0, max(x["parte"] for x in par) * 100 * 1.25)
    fig.tight_layout(w_pad=1.5)
    guardar(fig, "platos")


def generar(d: dict | None = None) -> None:
    d = d or json.loads((SALIDA / "datos.json").read_text(encoding="utf-8"))
    FIG.mkdir(parents=True, exist_ok=True)
    for f in (fig_ciudades, fig_igv, fig_ingreso, fig_estructura, fig_riesgo, fig_quiebres, fig_tornados, fig_flujo,
              fig_regimenes, fig_matriz, fig_platos):
        f(d)


if __name__ == "__main__":
    generar()
    print(sorted(p.name for p in FIG.glob("*.pdf")))
