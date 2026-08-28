"""Grabadora web: graba audios de prueba desde el navegador.

Uso (desde voz-lab/, con el entorno virtual activado):

    uvicorn grabadora_web:app --host 0.0.0.0 --port 8001

Luego abre http://localhost:8001 en la laptop del local. Cada audio se
guarda en audios/NNN.webm junto con su ground truth (lo que realmente
dijo el cliente), el pedido esperado y notas de contexto, en
audios/metadata.csv.

Nota sobre celulares: el micrófono en el navegador solo funciona en
"orígenes seguros". http://localhost sí califica (la laptop); una IP
como http://192.168.1.50:8001 NO, salvo que actives en el Chrome del
celular chrome://flags/#unsafely-treat-insecure-origin-as-secure con
esa URL. Para la prueba, la laptop en el mostrador es suficiente.
"""
import csv
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

BASE = Path(__file__).resolve().parent
AUDIOS_DIR = BASE / "audios"
METADATA = AUDIOS_DIR / "metadata.csv"

app = FastAPI(title="Grabadora de audios — banco de pruebas de voz")


def contar_audios() -> int:
    if not AUDIOS_DIR.exists():
        return 0
    return len([p for p in AUDIOS_DIR.iterdir() if p.suffix in (".webm", ".wav", ".ogg")])


def siguiente_nombre(extension: str) -> Path:
    numeros = [
        int(p.stem) for p in AUDIOS_DIR.iterdir()
        if p.stem.isdigit() and p.suffix in (".webm", ".wav", ".ogg")
    ] if AUDIOS_DIR.exists() else []
    n = max(numeros) + 1 if numeros else 1
    return AUDIOS_DIR / f"{n:03d}{extension}"


@app.post("/api/guardar")
async def guardar(
    audio: UploadFile = File(...),
    ground_truth_texto: str = Form(""),
    pedido_esperado: str = Form(""),
    notas: str = Form(""),
    duracion_seg: float = Form(0.0),
):
    AUDIOS_DIR.mkdir(exist_ok=True)
    extension = ".webm" if "webm" in (audio.content_type or "") else ".ogg" if "ogg" in (audio.content_type or "") else ".wav"
    destino = siguiente_nombre(extension)
    destino.write_bytes(await audio.read())

    nuevo = not METADATA.exists()
    with open(METADATA, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        if nuevo:
            writer.writerow([
                "archivo", "fecha_hora", "duracion_seg",
                "ground_truth_texto", "pedido_esperado", "notas",
            ])
        writer.writerow([
            destino.name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            f"{duracion_seg:.1f}",
            ground_truth_texto.strip(),
            pedido_esperado.strip(),
            notas.strip(),
        ])

    return {"archivo": destino.name, "total": contar_audios()}


@app.get("/api/contador")
def contador():
    return {"total": contar_audios()}


@app.get("/", response_class=HTMLResponse)
def pagina():
    return PAGINA_HTML


PAGINA_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grabadora de pedidos</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: #faf7f2; color: #2b2b2b;
         display: flex; justify-content: center; padding: 24px; }
  main { width: min(560px, 100%); display: flex; flex-direction: column; gap: 16px; }
  h1 { font-size: 1.5rem; }
  .contador { color: #77705f; font-size: 1.05rem; }
  button { font-family: inherit; font-size: 1.3rem; font-weight: 700; border: none;
           border-radius: 14px; min-height: 80px; cursor: pointer; }
  #btn-grabar { background: #c62828; color: #fff; }
  #btn-grabar.grabando { background: #2b2b2b; }
  #btn-guardar { background: #2e7d32; color: #fff; }
  button:disabled { background: #c9c1b8; cursor: default; }
  audio { width: 100%; }
  label { display: flex; flex-direction: column; gap: 4px; font-weight: 600; font-size: 0.95rem; }
  input, textarea { font-family: inherit; font-size: 1rem; padding: 12px;
                    border: 2px solid #ddd3c6; border-radius: 10px; }
  .estado { min-height: 1.4em; font-weight: 700; }
  .estado.ok { color: #2e7d32; } .estado.error { color: #c62828; }
  .oculto { display: none; }
</style>
</head>
<body>
<main>
  <h1>🎤 Grabadora de pedidos de prueba</h1>
  <div class="contador">Audios guardados: <strong id="total">…</strong> (meta: 30)</div>

  <button id="btn-grabar">🎤 Grabar</button>

  <div id="revision" class="oculto">
    <p style="margin-bottom:8px"><strong>Escucha y verifica:</strong></p>
    <audio id="reproductor" controls></audio>
    <label style="margin-top:12px">¿Qué dijo realmente el cliente? (ground truth)
      <textarea id="ground-truth" rows="2" placeholder="dos lomitos y una chichita porfa"></textarea>
    </label>
    <label style="margin-top:10px">Pedido correcto esperado
      <input id="esperado" placeholder="2x lomo saltado, 1x chicha">
    </label>
    <label style="margin-top:10px">Notas de contexto (opcional)
      <input id="notas" placeholder="mucho ruido de fondo / cliente mayor / habló rápido">
    </label>
    <button id="btn-guardar" style="margin-top:12px; width:100%">💾 Guardar audio</button>
    <button id="btn-descartar" style="margin-top:8px; width:100%; min-height:56px; background:#efe8de">Descartar y grabar otro</button>
  </div>

  <div id="estado" class="estado"></div>
</main>
<script>
let mediaRecorder = null, chunks = [], blob = null, inicioGrabacion = 0, duracionSeg = 0;

const $ = (id) => document.getElementById(id);
const estado = (msg, clase = "") => { $("estado").textContent = msg; $("estado").className = "estado " + clase; };

async function actualizarContador() {
  try {
    const r = await fetch("/api/contador");
    $("total").textContent = (await r.json()).total;
  } catch { $("total").textContent = "?"; }
}

$("btn-grabar").onclick = async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = () => {
      duracionSeg = (Date.now() - inicioGrabacion) / 1000;
      blob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
      $("reproductor").src = URL.createObjectURL(blob);
      $("revision").classList.remove("oculto");
      $("btn-grabar").textContent = "🎤 Grabar";
      $("btn-grabar").classList.remove("grabando");
      stream.getTracks().forEach((t) => t.stop());
      estado(`Grabado (${duracionSeg.toFixed(1)} s). Escucha, anota y guarda.`);
    };
    inicioGrabacion = Date.now();
    mediaRecorder.start();
    $("btn-grabar").textContent = "⏹ Detener";
    $("btn-grabar").classList.add("grabando");
    $("revision").classList.add("oculto");
    estado("Grabando… habla el pedido.");
  } catch (e) {
    estado("No se pudo acceder al micrófono: " + e.message, "error");
  }
};

$("btn-guardar").onclick = async () => {
  if (!blob) return;
  const datos = new FormData();
  datos.append("audio", blob, "audio.webm");
  datos.append("ground_truth_texto", $("ground-truth").value);
  datos.append("pedido_esperado", $("esperado").value);
  datos.append("notas", $("notas").value);
  datos.append("duracion_seg", duracionSeg.toFixed(1));
  try {
    const r = await fetch("/api/guardar", { method: "POST", body: datos });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    estado(`✔ Guardado como ${j.archivo}`, "ok");
    $("total").textContent = j.total;
    blob = null;
    $("revision").classList.add("oculto");
    ["ground-truth", "esperado", "notas"].forEach((id) => $(id).value = "");
  } catch (e) {
    estado("No se pudo guardar: " + e.message, "error");
  }
};

$("btn-descartar").onclick = () => {
  blob = null;
  $("revision").classList.add("oculto");
  estado("Descartado. Graba de nuevo.");
};

actualizarContador();
</script>
</body>
</html>"""
