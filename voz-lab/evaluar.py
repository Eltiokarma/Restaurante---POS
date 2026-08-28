"""Evaluación del pipeline de voz: Whisper (transcripción) + Claude (interpretación).

Uso (desde voz-lab/, con .env configurado):

    python evaluar.py --menu menu.json       # pipeline completo sobre audios/
    python evaluar.py --solo-interpretacion  # SOLO re-corre Claude sobre las
                                             # transcripciones ya guardadas (no
                                             # vuelve a pagar Whisper) — para
                                             # iterar el prompt rápido y barato

Mide POR SEPARADO la transcripción (WER contra el ground truth anotado) y
la interpretación (match contra el pedido esperado), para saber dónde
falla el pipeline: micrófono/ruido (Whisper) o prompt (Claude).

Salidas: transcripciones/NNN.txt (+ NNN.meta.json con latencia/costo),
resultados.csv y un reporte resumen en consola.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from services.interpreter import (
    MODELO_DEFAULT, InterpretacionFallida, cargar_menu, interpretar,
)
from services.metricas import (
    comparar_interpretacion, costo_claude, costo_whisper, parsear_esperado, wer,
)

BASE = Path(__file__).resolve().parent
AUDIOS_DIR = BASE / "audios"
TRANS_DIR = BASE / "transcripciones"
RESULTADOS = BASE / "resultados.csv"
EXTENSIONES_AUDIO = (".wav", ".webm", ".ogg")
UMBRAL_WER = 0.10  # transcripción "correcta" si WER < 10%

load_dotenv(BASE / ".env")


def transcribir(ruta_audio: Path) -> tuple[str, float]:
    """Transcribe con Whisper. Devuelve (texto, latencia_ms)."""
    from openai import OpenAI  # import aquí: --solo-interpretacion no lo necesita

    client = OpenAI()
    inicio = time.perf_counter()
    with open(ruta_audio, "rb") as f:
        respuesta = client.audio.transcriptions.create(
            model="whisper-1", file=f, language="es",
        )
    latencia_ms = (time.perf_counter() - inicio) * 1000
    return respuesta.text.strip(), latencia_ms


def cargar_metadata() -> dict[str, dict]:
    """audios/metadata.csv → {stem: {ground_truth_texto, pedido_esperado, ...}}."""
    ruta = AUDIOS_DIR / "metadata.csv"
    if not ruta.exists():
        return {}
    with open(ruta, encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f, delimiter=";"))
    return {Path(fila["archivo"]).stem: fila for fila in filas}


def duracion_de(stem: str, metadata: dict[str, dict], ruta_audio: Path | None) -> float | None:
    """Duración en segundos: de la metadata (la anota la grabadora) o del wav."""
    anotada = metadata.get(stem, {}).get("duracion_seg", "")
    if anotada:
        try:
            return float(anotada)
        except ValueError:
            pass
    if ruta_audio is not None and ruta_audio.suffix == ".wav":
        try:
            import soundfile as sf

            info = sf.info(ruta_audio)
            return info.frames / info.samplerate
        except Exception:
            pass
    return None


def obtener_transcripciones(solo_interpretacion: bool, metadata: dict[str, dict]) -> list[Path]:
    """Asegura transcripciones/NNN.txt (+ .meta.json) y devuelve la lista."""
    TRANS_DIR.mkdir(exist_ok=True)

    if solo_interpretacion:
        fuentes = sorted(TRANS_DIR.glob("*.txt"))
        if not fuentes:
            sys.exit("No hay transcripciones guardadas; corre primero sin --solo-interpretacion.")
        return fuentes

    audios = sorted(p for p in AUDIOS_DIR.glob("*") if p.suffix in EXTENSIONES_AUDIO)
    if not audios:
        sys.exit(
            "No hay audios en voz-lab/audios/. Graba con la página web "
            "(uvicorn grabadora_web:app --port 8001) o con python grabadora.py"
        )

    fuentes = []
    for audio in audios:
        destino = TRANS_DIR / f"{audio.stem}.txt"
        meta = TRANS_DIR / f"{audio.stem}.meta.json"
        if not destino.exists():
            print(f"🎧 Transcribiendo {audio.name}…")
            texto, latencia_ms = transcribir(audio)
            destino.write_text(texto, encoding="utf-8")
            meta.write_text(json.dumps({
                "latencia_ms": round(latencia_ms),
                "costo_usd": costo_whisper(duracion_de(audio.stem, metadata, audio)),
            }), encoding="utf-8")
        fuentes.append(destino)
    return fuentes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solo-interpretacion", action="store_true",
                        help="No llama a Whisper: usa las transcripciones ya guardadas")
    parser.add_argument("--menu", default=str(BASE / "menu.json"))
    parser.add_argument("--modelo", default=None,
                        help="Modelo de Claude (default: MODELO_INTERPRETE o claude-opus-5)")
    args = parser.parse_args()

    import os
    modelo = args.modelo or os.getenv("MODELO_INTERPRETE", MODELO_DEFAULT)
    menu = cargar_menu(args.menu)
    metadata = cargar_metadata()
    fuentes = obtener_transcripciones(args.solo_interpretacion, metadata)

    cliente_claude = anthropic.Anthropic()
    filas = []

    for fuente in fuentes:
        stem = fuente.stem
        transcripcion = fuente.read_text(encoding="utf-8").strip()
        anotado = metadata.get(stem, {})
        print(f"🧠 Interpretando {stem}: “{transcripcion}”")

        # Interpretación con Claude (con latencia)
        inicio = time.perf_counter()
        try:
            resultado, usage = interpretar(transcripcion, menu, cliente_claude, modelo)
            latencia_claude_ms = round((time.perf_counter() - inicio) * 1000)
            costo_c = costo_claude(usage, modelo)
            error = ""
        except (InterpretacionFallida, anthropic.APIError) as e:
            resultado = {"items": [], "no_encontrados": [], "notas": ""}
            latencia_claude_ms, costo_c, error = None, None, str(e)

        # Métrica 1: transcripción (WER contra ground truth, si se anotó)
        ground_truth = anotado.get("ground_truth_texto", "").strip()
        valor_wer = round(wer(ground_truth, transcripcion), 3) if ground_truth else None

        # Métrica 2: interpretación (match contra el pedido esperado, si se anotó)
        texto_esperado = anotado.get("pedido_esperado", "").strip()
        if texto_esperado:
            esperado, no_resueltos = parsear_esperado(texto_esperado, menu)
            match = comparar_interpretacion(resultado["items"], esperado)
            if no_resueltos:
                print(f"   ⚠ No pude parsear del esperado: {no_resueltos} (revisa la anotación)")
        else:
            match = ""

        # Latencia y costo de Whisper (guardados al transcribir)
        meta_ruta = TRANS_DIR / f"{stem}.meta.json"
        meta = json.loads(meta_ruta.read_text(encoding="utf-8")) if meta_ruta.exists() else {}
        costo_w = meta.get("costo_usd")
        costo_total = (costo_w or 0) + (costo_c or 0) if (costo_w or costo_c) else None

        filas.append({
            "archivo": stem,
            "transcripcion_whisper": transcripcion,
            "ground_truth_texto": ground_truth,
            "wer": valor_wer if valor_wer is not None else "",
            "pedido_interpretado": ", ".join(
                f'{i["cantidad"]}x{i["plato_id"]}' for i in resultado["items"]
            ),
            "pedido_esperado": texto_esperado,
            "match_interpretacion": match,
            "no_encontrados": ", ".join(resultado["no_encontrados"]),
            "notas_claude": resultado["notas"],
            "notas_captura": anotado.get("notas", ""),
            "latencia_whisper_ms": meta.get("latencia_ms", ""),
            "latencia_claude_ms": latencia_claude_ms if latencia_claude_ms is not None else "",
            "costo_estimado_usd": f"{costo_total:.5f}" if costo_total is not None else "",
            "error": error,
        })

    with open(RESULTADOS, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(filas[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(filas)

    imprimir_reporte(filas)


def imprimir_reporte(filas: list[dict]) -> None:
    n = len(filas)
    con_wer = [f for f in filas if f["wer"] != ""]
    con_match = [f for f in filas if f["match_interpretacion"]]

    trans_ok = sum(1 for f in con_wer if f["wer"] < UMBRAL_WER)
    interp_exacta = sum(1 for f in con_match if f["match_interpretacion"] == "sí")
    interp_parcial = sum(1 for f in con_match if f["match_interpretacion"] == "parcial")

    # Atribución de fallas: texto malo = Whisper; texto bueno con pedido malo = Claude
    fallas_whisper = sum(1 for f in con_wer if f["wer"] >= UMBRAL_WER)
    fallas_claude = sum(
        1 for f in filas
        if f["wer"] != "" and f["wer"] < UMBRAL_WER
        and f["match_interpretacion"] in ("no", "parcial")
    )

    latencias = [
        f["latencia_whisper_ms"] + f["latencia_claude_ms"]
        for f in filas
        if isinstance(f["latencia_whisper_ms"], (int, float))
        and isinstance(f["latencia_claude_ms"], (int, float))
    ]
    costos = [float(f["costo_estimado_usd"]) for f in filas if f["costo_estimado_usd"]]
    fallidos = [
        f["archivo"] for f in filas
        if f["error"] or f["match_interpretacion"] in ("no", "parcial")
    ]

    def pct(parte: int, total: int) -> str:
        return f"{parte}/{total} ({parte / total * 100:.0f}%)" if total else "sin datos anotados"

    print(f"\n=== RESULTADOS ({n} audios) ===")
    print(f"Transcripción correcta (WER < {UMBRAL_WER:.0%}): {pct(trans_ok, len(con_wer))}")
    print(f"Interpretación correcta (exacta): {pct(interp_exacta, len(con_match))}")
    print(f"Interpretación parcial: {interp_parcial}/{len(con_match) or 0}")
    print(f"Fallas de Whisper (texto malo): {fallas_whisper}")
    print(f"Fallas de Claude (texto bueno, pedido malo): {fallas_claude}")
    if latencias:
        print(f"Latencia promedio total: {sum(latencias) / len(latencias) / 1000:.1f} s")
    if costos:
        print(f"Costo promedio por pedido: ${sum(costos) / len(costos):.4f}")
    if fallidos:
        print(f"---\nAudios fallidos (revisar): {', '.join(fallidos)}")
    print(f"---\nDetalle completo en {RESULTADOS.name} (ábrelo en Excel).")


if __name__ == "__main__":
    main()
