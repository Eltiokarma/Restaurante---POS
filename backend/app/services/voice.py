"""Pedido por voz (Fase 3): Whisper transcribe, Claude interpreta.

La voz es SOLO otra manera de llenar el carrito. El resultado de este
módulo se muestra en la pantalla de verificación táctil del frontend y
recién ahí (con confirmación de dedos, nunca de voz) entra al carrito.
Todo lo posterior (resumen, ventana, ticket, cocina) no cambia.

El diseño del intérprete es el validado en el banco de pruebas de la
Fase 2 (voz-lab/services/interpreter.py). Los marcadores TODO indican
dónde pegar el prompt refinado y los sinónimos aprendidos cuando
existan los números de la Fase 2.
"""
import json
import os
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Plato

MODELO_INTERPRETE = os.getenv("MODELO_INTERPRETE", "claude-opus-5")
TIMEOUT_WHISPER_S = 10
TIMEOUT_CLAUDE_S = 15

# Costos aproximados para el panel del admin (USD)
PRECIO_WHISPER_POR_MIN_USD = 0.006
PRECIOS_CLAUDE_POR_MTOK_USD = {
    "claude-opus-5": (5.00, 0.50, 6.25, 25.00),   # entrada, cache lect., cache escr., salida
    "claude-sonnet-5": (2.00, 0.20, 2.50, 10.00),
    "claude-haiku-4-5": (1.00, 0.10, 1.25, 5.00),
}


class VozError(Exception):
    """Error tipado para que el frontend muestre un mensaje amable."""

    def __init__(self, mensaje_cliente: str, detalle: str = ""):
        self.mensaje_cliente = mensaje_cliente
        super().__init__(detalle or mensaje_cliente)


def claves_configuradas() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and bool(os.getenv("ANTHROPIC_API_KEY"))


def transcribir(audio_bytes: bytes, nombre_archivo: str = "audio.webm") -> str:
    """Transcribe el audio con Whisper (whisper-1, español). Timeout 10s."""
    import openai
    from openai import OpenAI

    try:
        client = OpenAI(timeout=TIMEOUT_WHISPER_S)
        respuesta = client.audio.transcriptions.create(
            model="whisper-1",
            file=(nombre_archivo, audio_bytes),
            language="es",
        )
        return respuesta.text.strip()
    except openai.APITimeoutError as e:
        raise VozError("No te escuché bien, intenta de nuevo o usa los botones", str(e))
    except openai.OpenAIError as e:
        raise VozError("No te escuché bien, intenta de nuevo o usa los botones", str(e))


# Estructura de salida: la misma del banco de pruebas de Fase 2
TOOL_REGISTRAR_PEDIDO = {
    "name": "registrar_pedido",
    "description": (
        "Registra la interpretación del pedido hablado del cliente. "
        "Llámala SIEMPRE, exactamente una vez, incluso si no se entendió nada "
        "(en ese caso con items vacío y una nota)."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "Platos pedidos que SÍ están en el menú de hoy",
                "items": {
                    "type": "object",
                    "properties": {
                        "plato_id": {"type": "integer", "description": "El id exacto del plato en el menú"},
                        "cantidad": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["plato_id", "cantidad"],
                    "additionalProperties": False,
                },
            },
            "no_encontrados": {
                "type": "array",
                "description": "Cosas que el cliente pidió pero NO están en el menú de hoy, tal como las dijo",
                "items": {"type": "string"},
            },
            "notas": {
                "type": "string",
                "description": "Ambigüedades o dudas; cadena vacía si no hay",
            },
        },
        "required": ["items", "no_encontrados", "notas"],
        "additionalProperties": False,
    },
}


def menu_activo_con_sinonimos(db: Session) -> list[dict]:
    """El menú del día CON sinónimos, desde la BD (no de un JSON estático)."""
    platos = db.scalars(select(Plato).where(Plato.activo_hoy == True)).all()  # noqa: E712
    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "precio": p.precio,
            "sinonimos": json.loads(p.sinonimos or "[]"),
        }
        for p in platos
    ]


def construir_system(menu: list[dict]) -> str:
    # TODO: pegar aquí el prompt validado en la Fase 2 (voz-lab) cuando
    # existan los números de resultados.csv. Mientras tanto, esta es la
    # versión base del banco de pruebas.
    lineas = []
    for plato in menu:
        sinonimos = ", ".join(f'"{s}"' for s in plato["sinonimos"]) or "—"
        lineas.append(
            f'- id: {plato["id"]} | {plato["nombre"]} (S/ {plato["precio"]:.2f})'
            f" | también le dicen: {sinonimos}"
        )
    menu_texto = "\n".join(lineas)

    return f"""Eres el intérprete de pedidos de un restaurante de menú peruano. Recibes la \
transcripción (imperfecta, viene de audio) de lo que un cliente dijo y debes convertirla \
en un pedido estructurado llamando a la herramienta registrar_pedido exactamente una vez.

MENÚ DE HOY (los únicos platos que existen):
{menu_texto}

REGLAS DE INTERPRETACIÓN:
- Español peruano coloquial: "uno de lomo" = 1 lomo saltado; "chichita" = chicha morada; \
"agüita" o "refresquito" = refresco. Diminutivos y apócopes son normales.
- Cantidad implícita: si nombra un plato sin número ("me da lomo"), la cantidad es 1.
- Números en palabras o cifras: "dos", "2", "un par de" = 2.
- Pedidos múltiples en una frase: "dos lomos y una chicha" son dos items.
- Muletillas y cortesía: ignora "este...", "eh", "me da", "porfa", "señorita".
- Correcciones a mitad de frase: vale la ÚLTIMA intención. "un lomo... no, mejor dos" = 2.
- Errores de audio: si una palabra suena a un plato del menú ("logo saltado"), asume el \
más parecido y anótalo en notas.
- Lo que NO esté en el menú de hoy va en no_encontrados, tal como lo dijeron. NUNCA lo \
conviertas en otro plato.
- Si no hay ningún pedido en la transcripción, devuelve todo vacío con una nota.

Usa siempre los id numéricos exactos del menú."""


def interpretar(texto: str, menu: list[dict]) -> tuple[dict, float | None]:
    """Interpreta la transcripción. Devuelve (resultado, costo_usd_estimado)."""
    import anthropic

    try:
        client = anthropic.Anthropic(timeout=TIMEOUT_CLAUDE_S)
        response = client.messages.create(
            model=MODELO_INTERPRETE,
            max_tokens=8000,
            system=[{
                "type": "text",
                "text": construir_system(menu),
                # El menú es estable durante el servicio: se cachea
                "cache_control": {"type": "ephemeral"},
            }],
            tools=[TOOL_REGISTRAR_PEDIDO],
            messages=[{"role": "user", "content": texto}],
        )
    except anthropic.APIError as e:
        raise VozError("No te escuché bien, intenta de nuevo o usa los botones", str(e))

    if response.stop_reason == "refusal":
        raise VozError("No pude entender el pedido, usa los botones por favor")

    for block in response.content:
        if block.type == "tool_use" and block.name == "registrar_pedido":
            return _depurar(dict(block.input), menu), _costo_claude(response.usage)

    raise VozError("No pude entender el pedido, usa los botones por favor",
                   "la respuesta no llamó a registrar_pedido")


def _depurar(resultado: dict, menu: list[dict]) -> dict:
    """Defensa final: ids inexistentes o cantidades inválidas no pasan."""
    ids_validos = {p["id"] for p in menu}
    items, extranos = [], []
    for item in resultado.get("items", []):
        try:
            plato_id, cantidad = int(item.get("plato_id")), int(item.get("cantidad", 0))
        except (TypeError, ValueError):
            extranos.append(str(item))
            continue
        if plato_id in ids_validos and 0 < cantidad <= 20:
            items.append({"plato_id": plato_id, "cantidad": cantidad})
        else:
            extranos.append(str(item.get("plato_id", "?")))
    return {
        "items": items,
        "no_encontrados": list(resultado.get("no_encontrados", [])) + extranos,
        "notas": resultado.get("notas", ""),
    }


def _costo_claude(usage) -> float | None:
    precios = PRECIOS_CLAUDE_POR_MTOK_USD.get(MODELO_INTERPRETE)
    if precios is None:
        return None
    entrada, cache_lect, cache_escr, salida = precios
    return (
        usage.input_tokens * entrada
        + (usage.cache_read_input_tokens or 0) * cache_lect
        + (usage.cache_creation_input_tokens or 0) * cache_escr
        + usage.output_tokens * salida
    ) / 1_000_000


def costo_whisper(duracion_s: float | None) -> float:
    return ((duracion_s or 0) / 60) * PRECIO_WHISPER_POR_MIN_USD


def procesar_audio(db: Session, audio_bytes: bytes, nombre: str, duracion_s: float | None):
    """Pipeline completo: transcribir + interpretar + resolver contra el menú.

    Devuelve (transcripcion, resultado, items_resueltos, latencia_ms, costo_usd).
    """
    inicio = time.perf_counter()
    transcripcion = transcribir(audio_bytes, nombre)

    menu = menu_activo_con_sinonimos(db)
    if not menu:
        raise VozError("Todavía no hay menú cargado, pregunta en caja por favor")

    resultado, costo_claude = interpretar(transcripcion, menu)
    latencia_ms = round((time.perf_counter() - inicio) * 1000)

    por_id = {p["id"]: p for p in menu}
    items_resueltos = [
        {
            "plato_id": i["plato_id"],
            "nombre": por_id[i["plato_id"]]["nombre"],
            "precio": por_id[i["plato_id"]]["precio"],
            "cantidad": i["cantidad"],
        }
        for i in resultado["items"]
    ]
    costo_total = costo_whisper(duracion_s) + (costo_claude or 0)
    return transcripcion, resultado, items_resueltos, latencia_ms, round(costo_total, 6)
