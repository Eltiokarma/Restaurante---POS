"""Evaluación del pipeline de voz: Whisper (transcripción) + Claude (interpretación).

Uso (desde voz-lab/, con .env configurado):

    python evaluar.py                        # pipeline completo sobre audios/*.wav
    python evaluar.py --solo-interpretacion  # SOLO re-corre Claude sobre las
                                             # transcripciones ya guardadas (no
                                             # vuelve a pagar Whisper) — para
                                             # iterar el prompt rápido y barato

Salidas:
- transcripciones/NNN.txt   (una por audio, reutilizables entre corridas)
- resultados.csv            (audio; transcripción; items; no_encontrados; notas)
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from services.interpreter import InterpretacionFallida, cargar_menu, interpretar

BASE = Path(__file__).resolve().parent
AUDIOS_DIR = BASE / "audios"
TRANS_DIR = BASE / "transcripciones"
RESULTADOS = BASE / "resultados.csv"

load_dotenv(BASE / ".env")


def transcribir(ruta_audio: Path) -> str:
    """Transcribe un audio con Whisper (API de OpenAI)."""
    from openai import OpenAI  # import aquí: --solo-interpretacion no lo necesita

    client = OpenAI()
    with open(ruta_audio, "rb") as f:
        respuesta = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="es",
        )
    return respuesta.text.strip()


def cargar_esperados() -> dict[str, str]:
    """Lee audios/metadata.csv (si existe) para mostrar el pedido esperado al lado."""
    ruta = AUDIOS_DIR / "metadata.csv"
    if not ruta.exists():
        return {}
    with open(ruta, encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f, delimiter=";"))
    return {fila["archivo"]: fila.get("esperado_items", "") for fila in filas}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--solo-interpretacion",
        action="store_true",
        help="No llama a Whisper: usa las transcripciones ya guardadas",
    )
    parser.add_argument("--menu", default=str(BASE / "menu.json"))
    parser.add_argument("--modelo", default=None, help="Modelo de Claude (default: MODELO_INTERPRETE o claude-opus-5)")
    args = parser.parse_args()

    menu = cargar_menu(args.menu)
    TRANS_DIR.mkdir(exist_ok=True)
    esperados = cargar_esperados()

    audios = sorted(AUDIOS_DIR.glob("*.wav"))
    if args.solo_interpretacion:
        fuentes = sorted(TRANS_DIR.glob("*.txt"))
        if not fuentes:
            sys.exit("No hay transcripciones guardadas todavía; corre primero sin --solo-interpretacion.")
    elif not audios:
        sys.exit("No hay audios en voz-lab/audios/. Graba algunos con: python grabadora.py")
    else:
        fuentes = []
        for audio in audios:
            destino = TRANS_DIR / f"{audio.stem}.txt"
            if not destino.exists():
                print(f"🎧 Transcribiendo {audio.name}…")
                destino.write_text(transcribir(audio), encoding="utf-8")
            fuentes.append(destino)

    cliente_claude = anthropic.Anthropic()
    filas = []
    tokens_entrada = tokens_salida = tokens_cacheados = 0

    for fuente in fuentes:
        transcripcion = fuente.read_text(encoding="utf-8").strip()
        print(f"🧠 Interpretando {fuente.stem}: “{transcripcion}”")
        try:
            resultado, usage = interpretar(transcripcion, menu, cliente_claude, args.modelo)
            error = ""
            tokens_entrada += usage.input_tokens
            tokens_salida += usage.output_tokens
            tokens_cacheados += usage.cache_read_input_tokens or 0
        except (InterpretacionFallida, anthropic.APIError) as e:
            resultado = {"items": [], "no_encontrados": [], "notas": ""}
            error = str(e)

        items_legible = ", ".join(f'{i["cantidad"]}x{i["plato_id"]}' for i in resultado["items"])
        filas.append({
            "audio": fuente.stem,
            "transcripcion": transcripcion,
            "items": items_legible,
            "items_json": json.dumps(resultado["items"], ensure_ascii=False),
            "no_encontrados": ", ".join(resultado["no_encontrados"]),
            "notas": resultado["notas"],
            "esperado": esperados.get(f"{fuente.stem}.wav", ""),
            "error": error,
        })

    with open(RESULTADOS, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(filas[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(filas)

    con_error = sum(1 for f in filas if f["error"])
    con_faltantes = sum(1 for f in filas if f["no_encontrados"])
    print(f"\n✅ {len(filas)} transcripciones interpretadas → {RESULTADOS.name}")
    print(f"   Con platos fuera de menú: {con_faltantes} · Con error: {con_error}")
    print(
        f"   Tokens Claude — entrada: {tokens_entrada:,} (cacheados: {tokens_cacheados:,}) "
        f"· salida: {tokens_salida:,}"
    )
    print("   Revisa resultados.csv en Excel y compara con la columna 'esperado'.")


if __name__ == "__main__":
    main()
