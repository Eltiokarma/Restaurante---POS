"""Grabadora de audios de prueba.

Uso (desde voz-lab/, con el entorno virtual activado):

    python grabadora.py

Flujo por cada audio: Enter para empezar a grabar → el cliente habla →
Enter para parar → se guarda audios/NNN.wav y se anota (opcional) qué
se dijo y qué pedido se esperaba, en audios/metadata.csv.

Grabación manual a propósito: sin detección de silencio ni streaming
(suficiente para capturar el set de pruebas).
"""
import csv
import queue
from datetime import datetime
from pathlib import Path

try:
    import sounddevice as sd
    import soundfile as sf
except OSError as e:
    raise SystemExit(
        "No se pudo acceder al audio del sistema. En Windows suele bastar con "
        "tener un micrófono conectado; en Linux instala libportaudio2.\n"
        f"Detalle: {e}"
    )

AUDIOS_DIR = Path(__file__).resolve().parent / "audios"
FRECUENCIA = 16_000  # 16 kHz mono: lo que Whisper espera; archivos livianos


def siguiente_nombre() -> Path:
    existentes = sorted(AUDIOS_DIR.glob("[0-9][0-9][0-9].wav"))
    n = int(existentes[-1].stem) + 1 if existentes else 1
    return AUDIOS_DIR / f"{n:03d}.wav"


def grabar(destino: Path) -> float:
    """Graba hasta que el usuario pulse Enter. Devuelve la duración en segundos."""
    cola: queue.Queue = queue.Queue()

    def callback(indata, frames, time, status):
        cola.put(indata.copy())

    with sf.SoundFile(destino, "w", samplerate=FRECUENCIA, channels=1, subtype="PCM_16"):
        pass  # crea el archivo vacío para detectar problemas de permisos temprano

    frames_totales = 0
    with sf.SoundFile(destino, "w", samplerate=FRECUENCIA, channels=1, subtype="PCM_16") as archivo:
        with sd.InputStream(samplerate=FRECUENCIA, channels=1, callback=callback):
            input("🎙️  GRABANDO… habla el pedido y pulsa Enter para parar.")
        while not cola.empty():
            bloque = cola.get()
            archivo.write(bloque)
            frames_totales += len(bloque)

    return frames_totales / FRECUENCIA


def anotar_metadata(archivo: Path, esperado_texto: str, esperado_items: str) -> None:
    ruta_csv = AUDIOS_DIR / "metadata.csv"
    nuevo = not ruta_csv.exists()
    with open(ruta_csv, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        if nuevo:
            writer.writerow(["archivo", "fecha_hora", "esperado_texto", "esperado_items"])
        writer.writerow([
            archivo.name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            esperado_texto,
            esperado_items,
        ])


def main() -> None:
    AUDIOS_DIR.mkdir(exist_ok=True)
    print("Grabadora de audios de prueba — Ctrl+C para salir.\n")
    print("Consejo: varía ruido de fondo, distancia al micrófono y forma de hablar.\n")

    while True:
        destino = siguiente_nombre()
        input(f"[{destino.name}] Pulsa Enter para EMPEZAR a grabar…")
        duracion = grabar(destino)
        print(f"   Guardado {destino.name} ({duracion:.1f} s)")

        esperado_texto = input("   ¿Qué dijo el cliente? (opcional, Enter para saltar): ").strip()
        esperado_items = input(
            "   Pedido esperado, ej. 2xlomo,1xchicha (opcional): "
        ).strip()
        anotar_metadata(destino, esperado_texto, esperado_items)
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nListo. Audios en voz-lab/audios/")
