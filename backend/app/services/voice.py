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

MODELO_INTERPRETE = os.getenv("MODELO_INTERPRETE", "claude-opus-5-5")
# Si el modelo declina (clasificadores de seguridad), el servidor reintenta
# solo en el modelo de respaldo recomendado: un falso positivo no tumba la voz
BETA_RESPALDO = "server-side-fallback-2026-07-01"
TIMEOUT_WHISPER_S = 10
TIMEOUT_CLAUDE_S = 15

# Costos aproximados para el panel del admin (USD)
PRECIO_WHISPER_POR_MIN_USD = 0.006
PRECIOS_CLAUDE_POR_MTOK_USD = {
    "claude-opus-5-5": (4.00, 0.20, 5.00, 20.00),  # entrada, cache lect., cache escr., salida
    "claude-opus-5": (5.00, 0.50, 6.25, 25.00),
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


# Estructura de salida. Desde los tickets por persona la terminal vende
# MENÚS: cada persona es un menú con su entrada/segundo, lo que no quiere
# ("sin sopa"), el empaque, la entrega y su nombre. `items` queda para lo
# suelto de la carta (bebidas, un plato aparte).
# Sin minimum/maximum: el modo estricto no los admite; _depurar() acota.
EMPAQUES = ["mesa", "taper", "bolsa", "lonchera"]
ENTREGAS = ["auto", "junto", "separado"]

TOOL_REGISTRAR_PEDIDO = {
    "name": "registrar_pedido",
    "description": (
        "Registra la interpretación del pedido hablado del cliente. "
        "Llámala SIEMPRE, exactamente una vez, incluso si no se entendió nada "
        "(en ese caso con listas vacías y una nota)."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "personas": {
                "type": "array",
                "description": "Un elemento por cada menú pedido (cada persona). Varias personas "
                               "idénticas pueden ir en un solo elemento con cantidad > 1",
                "items": {
                    "type": "object",
                    "properties": {
                        "menu_id": {"type": "integer", "description": "El id exacto del menú"},
                        "cantidad": {"type": "integer", "description": "Cuántas personas piden exactamente esto (1 a 20)"},
                        "elecciones": {
                            "type": "array",
                            "description": "Solo los tiempos que el cliente nombró; lo no dicho se omite",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "tiempo_orden": {"type": "integer"},
                                    "plato_id": {"type": "integer"},
                                },
                                "required": ["tiempo_orden", "plato_id"],
                                "additionalProperties": False,
                            },
                        },
                        "sin": {
                            "type": "array",
                            "description": "tiempo_orden de los tiempos que NO quiere (\"sin sopa\", \"solo segundo\")",
                            "items": {"type": "integer"},
                        },
                        "empaque": {
                            "type": "string", "enum": EMPAQUES,
                            "description": "mesa = come acá; taper/bolsa/lonchera = para llevar",
                        },
                        "entrega": {
                            "type": "string", "enum": ENTREGAS,
                            "description": "junto = todo junto; separado = por tiempos; auto si no lo dijo",
                        },
                        "nombre": {"type": "string", "description": "Nombre de la persona si lo dijo; si no, vacío"},
                        "nota": {"type": "string", "description": "Pedido especial (\"sin cebolla\"); si no, vacío"},
                    },
                    "required": ["menu_id", "cantidad", "elecciones", "sin", "empaque", "entrega", "nombre", "nota"],
                    "additionalProperties": False,
                },
            },
            "items": {
                "type": "array",
                "description": "Platos sueltos de la CARTA (bebidas o platos fuera de un menú)",
                "items": {
                    "type": "object",
                    "properties": {
                        "plato_id": {"type": "integer", "description": "El id exacto del plato en la carta"},
                        "cantidad": {"type": "integer", "description": "1 a 20"},
                    },
                    "required": ["plato_id", "cantidad"],
                    "additionalProperties": False,
                },
            },
            "no_encontrados": {
                "type": "array",
                "description": "Cosas que el cliente pidió pero NO están hoy, tal como las dijo",
                "items": {"type": "string"},
            },
            "notas": {
                "type": "string",
                "description": "Ambigüedades o dudas; cadena vacía si no hay",
            },
        },
        "required": ["personas", "items", "no_encontrados", "notas"],
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


def contexto_de_hoy(db: Session) -> dict:
    """Lo que el intérprete puede vender hoy: la carta y los menús.

    Los menús salen de la misma función que la terminal (solo alternativas
    disponibles); a cada alternativa se le pegan los sinónimos del plato.
    """
    from ..routes.menu import _menus_activos

    platos = menu_activo_con_sinonimos(db)
    sinonimos = {p["id"]: p["sinonimos"] for p in platos}
    menus = _menus_activos(db)
    for menu in menus:
        for tiempo in menu["tiempos"]:
            for alt in tiempo["alternativas"]:
                alt["sinonimos"] = sinonimos.get(alt["plato_id"], [])
    return {"platos": platos, "menus": menus}


def _comillas(sinonimos: list[str]) -> str:
    return ", ".join(f'"{s}"' for s in sinonimos) or "—"


def construir_system(contexto: dict) -> str:
    # TODO: pegar aquí el prompt validado en la Fase 2 (voz-lab) cuando
    # existan los números de resultados.csv.
    bloques_menu = []
    for menu in contexto["menus"]:
        lineas = [f'MENÚ id: {menu["id"]} | {menu["nombre"]} (S/ {menu["precio"]:.2f})']
        for t in menu["tiempos"]:
            quitable = "" if t["obligatorio"] else " — se puede quitar"
            lineas.append(f'  Tiempo {t["orden"]}: {t["rotulo"]}{quitable}')
            for a in t["alternativas"]:
                lineas.append(
                    f'    - plato_id: {a["plato_id"]} | {a["nombre"]}'
                    f' | también le dicen: {_comillas(a["sinonimos"])}'
                )
        bloques_menu.append("\n".join(lineas))
    menus_texto = "\n\n".join(bloques_menu) or "(hoy no hay menús)"

    carta_texto = "\n".join(
        f'- id: {p["id"]} | {p["nombre"]} (S/ {p["precio"]:.2f}) | también le dicen: {_comillas(p["sinonimos"])}'
        for p in contexto["platos"]
    ) or "(vacía)"

    return f"""Eres el intérprete de pedidos de un restaurante de menú peruano. Recibes la \
transcripción (imperfecta, viene de audio) de lo que un cliente dijo y la conviertes en un \
pedido estructurado. Responde SIEMPRE llamando a la herramienta registrar_pedido, \
exactamente una vez, sin texto aparte.

MENÚS DE HOY (lo principal: cada persona pide un menú y elige un plato por tiempo):
{menus_texto}

CARTA DE HOY (platos sueltos; usa su id solo para lo que NO va dentro de un menú):
{carta_texto}

CÓMO ARMAR EL PEDIDO:
- Cada persona es un elemento de "personas" con el menu_id. "Dos menús, uno con caldo y \
lomo y otro con ensalada y ají de gallina" son DOS personas. Personas idénticas pueden ir \
juntas con cantidad ("tres menús con sopa y pollo" = una persona con cantidad 3).
- Si nombra platos de entrada o segundo, eso es un menú aunque no diga la palabra \
"menú": "un caldo y un lomo" = 1 persona con esa entrada y ese segundo. Si hay dudas de \
cómo se agrupan, una entrada y un segundo forman una persona, en el orden en que los dijo.
- En "elecciones" pon SOLO los tiempos que el cliente nombró, con el plato_id de ESE \
tiempo. Lo que no dijo se deja fuera: el cliente lo elige después en la pantalla.
- "Sin sopa", "sin entrada", "solo segundo", "solo la sopa" → el tiempo que no quiere va \
en "sin" (solo si dice que se puede quitar).
- Si hay un solo menú hoy, usa ese. Si hay varios y no queda claro cuál, elige el que \
tenga los platos que nombró y anota la duda en notas.
- Empaque: "para llevar", "en táper" → taper; "en bolsa" → bolsa; "en lonchera" → \
lonchera; si no dice nada o "para comer acá" → mesa.
- Entrega: "todo junto", "junto" → junto; "por tiempos", "primero la sopa", "separado" \
→ separado; si no lo dice → auto.
- Nombre: "uno para Juan", "el de María" → nombre de esa persona; si no, vacío.
- Pedidos especiales de esa persona ("sin cebolla", "bien cocido") van en su nota.
- Bebidas y lo que solo existe en la carta van en "items".

REGLAS DE INTERPRETACIÓN:
- Español peruano coloquial: diminutivos y apócopes son normales ("caldito", "lomito", \
"chichita" = chicha morada, "agüita" o "refresquito" = refresco).
- Números en palabras o cifras: "dos", "2", "un par de" = 2. Sin número, es 1.
- Muletillas y cortesía: ignora "este...", "eh", "me da", "porfa", "señorita".
- Correcciones a mitad de frase: vale la ÚLTIMA intención. "un lomo... no, mejor pollo".
- Errores de audio: si una palabra suena a un plato de hoy ("logo saltado"), asume el \
más parecido y anótalo en notas.
- Lo que NO esté hoy va en no_encontrados, tal como lo dijeron. NUNCA lo conviertas en \
otro plato.
- Si no hay ningún pedido en la transcripción, devuelve todo vacío con una nota.

Usa siempre los id numéricos exactos de arriba."""


def interpretar(texto: str, contexto: dict) -> tuple[dict, float | None]:
    """Interpreta la transcripción. Devuelve (resultado, costo_usd_estimado)."""
    import anthropic

    try:
        client = anthropic.Anthropic(timeout=TIMEOUT_CLAUDE_S)
        response = client.beta.messages.create(
            model=MODELO_INTERPRETE,
            max_tokens=8000,
            # Extraer un pedido es tarea corta: esfuerzo bajo = respuesta rápida
            output_config={"effort": "low"},
            betas=[BETA_RESPALDO],
            fallbacks="default",
            system=[{
                "type": "text",
                "text": construir_system(contexto),
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
            return _depurar(dict(block.input), contexto), _costo_claude(response.usage)

    raise VozError("No pude entender el pedido, usa los botones por favor",
                   "la respuesta no llamó a registrar_pedido")


def _entero(valor) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _depurar(resultado: dict, contexto: dict) -> dict:
    """Defensa final: ids inexistentes o cantidades inválidas no pasan.

    Un plato elegido tiene que ser alternativa de ESE tiempo de ESE menú;
    solo se quita un tiempo que se puede quitar; lo dudoso se descarta
    (el cliente lo completa con los dedos) en vez de inventarlo.
    """
    menus = {m["id"]: m for m in contexto["menus"]}
    ids_carta = {p["id"] for p in contexto["platos"]}
    extranos: list[str] = []

    personas = []
    for persona in resultado.get("personas", []):
        menu = menus.get(_entero(persona.get("menu_id")))
        cantidad = _entero(persona.get("cantidad")) or 1
        if menu is None or not 0 < cantidad <= 20:
            extranos.append(f"menú {persona.get('menu_id', '?')}")
            continue
        tiempos = {t["orden"]: t for t in menu["tiempos"]}
        sin = sorted({
            o for o in (_entero(x) for x in persona.get("sin", []))
            if o in tiempos and not tiempos[o]["obligatorio"]
        })
        elecciones: dict[int, int] = {}
        for e in persona.get("elecciones", []):
            orden, plato_id = _entero(e.get("tiempo_orden")), _entero(e.get("plato_id"))
            tiempo = tiempos.get(orden)
            if tiempo is None or orden in sin:
                continue
            if any(a["plato_id"] == plato_id for a in tiempo["alternativas"]):
                elecciones[orden] = plato_id
        empaque = persona.get("empaque")
        entrega = persona.get("entrega")
        personas.append({
            "menu_id": menu["id"],
            "cantidad": cantidad,
            "elecciones": elecciones,
            "sin": sin,
            "empaque": empaque if empaque in EMPAQUES else "mesa",
            "entrega": entrega if entrega in ("junto", "separado") else None,
            "nombre": str(persona.get("nombre") or "").strip()[:40],
            "nota": str(persona.get("nota") or "").strip()[:200],
        })

    items = []
    for item in resultado.get("items", []):
        plato_id, cantidad = _entero(item.get("plato_id")), _entero(item.get("cantidad"))
        if plato_id in ids_carta and cantidad is not None and 0 < cantidad <= 20:
            items.append({"plato_id": plato_id, "cantidad": cantidad})
        else:
            extranos.append(str(item.get("plato_id", "?")))
    return {
        "personas": personas,
        "items": items,
        "no_encontrados": list(resultado.get("no_encontrados", [])) + extranos,
        "notas": resultado.get("notas", ""),
    }


def resolver_personas(personas: list[dict], contexto: dict) -> list[dict]:
    """Nombres para la pantalla de verificación ("Menú · Caldo + Lomo")."""
    menus = {m["id"]: m for m in contexto["menus"]}
    salida = []
    for p in personas:
        menu = menus[p["menu_id"]]
        tiempos = {t["orden"]: t for t in menu["tiempos"]}
        platos = []
        for orden, plato_id in sorted(p["elecciones"].items()):
            alt = next(a for a in tiempos[orden]["alternativas"] if a["plato_id"] == plato_id)
            platos.append({"tiempo_orden": orden, "rotulo": tiempos[orden]["rotulo"],
                           "plato_id": plato_id, "nombre": alt["nombre"]})
        salida.append({
            **p,
            # JSON no tiene claves enteras: el frontend recibe la lista
            "elecciones": platos,
            "menu_nombre": menu["nombre"],
            "precio": menu["precio"],
            "sin_rotulos": [tiempos[o]["rotulo"] for o in p["sin"]],
        })
    return salida


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
    """Pipeline completo: transcribir + interpretar + resolver contra lo de hoy.

    Devuelve (transcripcion, resultado, items_resueltos, personas_resueltas,
    latencia_ms, costo_usd).
    """
    inicio = time.perf_counter()
    transcripcion = transcribir(audio_bytes, nombre)

    contexto = contexto_de_hoy(db)
    if not contexto["platos"] and not contexto["menus"]:
        raise VozError("Todavía no hay menú cargado, pregunta en caja por favor")

    resultado, costo_claude = interpretar(transcripcion, contexto)
    latencia_ms = round((time.perf_counter() - inicio) * 1000)

    por_id = {p["id"]: p for p in contexto["platos"]}
    items_resueltos = [
        {
            "plato_id": i["plato_id"],
            "nombre": por_id[i["plato_id"]]["nombre"],
            "precio": por_id[i["plato_id"]]["precio"],
            "cantidad": i["cantidad"],
        }
        for i in resultado["items"]
    ]
    personas = resolver_personas(resultado["personas"], contexto)
    costo_total = costo_whisper(duracion_s) + (costo_claude or 0)
    return (transcripcion, resultado, items_resueltos, personas,
            latencia_ms, round(costo_total, 6))
