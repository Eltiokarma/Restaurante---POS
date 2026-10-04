"""Pedido por voz (Fase 3): OpenAI transcribe y OpenAI interpreta.

La voz es SOLO otra manera de llenar el carrito. El resultado de este
módulo se muestra en la pantalla de verificación táctil del frontend y
recién ahí (con confirmación de dedos, nunca de voz) entra al carrito.
Todo lo posterior (resumen, ventana, ticket, cocina) no cambia.

Proveedor elegido por costo (decisión del dueño): todo en OpenAI, una
sola cuenta y una sola clave. Transcripción con gpt-4o-mini-transcribe
(con los platos del día como pista de vocabulario) e interpretación con
gpt-6-luna en salida JSON estricta. ~US$ 0.001 por pedido.
"""
import json
import os
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Plato

MODELO_TRANSCRIPCION = os.getenv("MODELO_TRANSCRIPCION", "gpt-4o-mini-transcribe")
MODELO_INTERPRETE = os.getenv("MODELO_INTERPRETE", "gpt-6-luna")
# Razonamiento corto: el pedido es una extracción, no un problema difícil;
# "none" responde más rápido, "medium" acierta más en frases enredadas
ESFUERZO_INTERPRETE = os.getenv("ESFUERZO_INTERPRETE", "low")
TIMEOUT_TRANSCRIPCION_S = 10
TIMEOUT_INTERPRETE_S = 15

# Costos aproximados para el panel del admin (USD, precios de OpenAI)
PRECIOS_TRANSCRIPCION_POR_MIN_USD = {
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-4o-transcribe": 0.006,
    "whisper-1": 0.006,
}
PRECIOS_INTERPRETE_POR_MTOK_USD = {
    # entrada, entrada en caché, salida
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5-nano": (0.05, 0.005, 0.40),
}


class VozError(Exception):
    """Error tipado para que el frontend muestre un mensaje amable."""

    def __init__(self, mensaje_cliente: str, detalle: str = ""):
        self.mensaje_cliente = mensaje_cliente
        super().__init__(detalle or mensaje_cliente)


def claves_configuradas() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def transcribir(audio_bytes: bytes, nombre_archivo: str = "audio.webm",
                pista: str = "") -> str:
    """Pasa el audio a texto (español). `pista`: los platos de hoy, para
    que "chairito" o "cau cau" salgan bien escritos. Timeout 10s."""
    import openai
    from openai import OpenAI

    try:
        client = OpenAI(timeout=TIMEOUT_TRANSCRIPCION_S)
        respuesta = client.audio.transcriptions.create(
            model=MODELO_TRANSCRIPCION,
            file=(nombre_archivo, audio_bytes),
            language="es",
            prompt=pista,
        )
        texto = respuesta.text.strip()
    except openai.OpenAIError as e:
        raise VozError("No te escuché bien, intenta de nuevo o usa los botones", str(e))
    # Con audio casi mudo (se cortó, nadie habló) el modelo a veces "repite"
    # la pista en vez de transcribir: eso no es un pedido
    if not texto or (pista and texto[:40].lower() in pista.lower()):
        raise VozError("Casi no te escuché. Habla fuerte y claro, o usa los botones.",
                       f"transcripción vacía o eco de la pista: {texto[:60]!r}")
    return texto


# Estructura de salida. Desde los tickets por persona la terminal vende
# MENÚS: cada persona es un menú con su entrada/segundo, lo que no quiere
# ("sin sopa"), el empaque, la entrega y su nombre. `items` queda para lo
# suelto de la carta (bebidas, un plato aparte).
# Sin minimum/maximum: el modo estricto no los admite; _depurar() acota.
EMPAQUES = ["mesa", "taper", "bolsa", "lonchera"]
ENTREGAS = ["auto", "junto", "separado"]

FORMATO_PEDIDO = {
    "type": "json_schema",
    "name": "pedido",
    "description": "La interpretación del pedido hablado del cliente",
    "strict": True,
    "schema": {
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
                                    "empaque": {
                                        "type": "string", "enum": [*EMPAQUES, "igual"],
                                        "description": "Si ESTE plato va distinto (\"la sopa en bolsa\"); "
                                                       "si no, igual",
                                    },
                                    "espera": {
                                        "type": "boolean",
                                        "description": "true si este plato sale DESPUÉS (\"el segundo "
                                                       "más tarde\", \"todavía no\")",
                                    },
                                },
                                "required": ["tiempo_orden", "plato_id", "empaque", "espera"],
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
                        "agregados": {
                            "type": "array",
                            "description": "Extras de la lista AGREGADOS (\"con un huevo frito\", \"una carne más\")",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "agregado_id": {"type": "integer"},
                                    "cantidad": {"type": "integer"},
                                },
                                "required": ["agregado_id", "cantidad"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["menu_id", "cantidad", "elecciones", "sin", "empaque", "entrega",
                                 "nombre", "nota", "agregados"],
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
            "gaseosas": {
                "type": "array",
                "description": "Gaseosas de la lista GASEOSAS",
                "items": {
                    "type": "object",
                    "properties": {
                        "bebida_id": {"type": "integer"},
                        "cantidad": {"type": "integer"},
                    },
                    "required": ["bebida_id", "cantidad"],
                    "additionalProperties": False,
                },
            },
            "mesa": {
                "type": "string",
                "description": "Nombre EXACTO de la mesa de la lista MESAS si la dijo; si no, vacío",
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
        "required": ["personas", "items", "gaseosas", "mesa", "no_encontrados", "notas"],
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
    from ..models import Bebida, Mesa

    menus = _menus_activos(db)
    for menu in menus:
        for tiempo in menu["tiempos"]:
            for alt in tiempo["alternativas"]:
                alt["sinonimos"] = sinonimos.get(alt["plato_id"], [])
    gaseosas = [
        {"id": b.id, "nombre": b.nombre, "precio": b.precio}
        for b in db.scalars(select(Bebida).where(Bebida.activa == True).order_by(Bebida.nombre))  # noqa: E712
    ]
    mesas = [
        {"id": m.id, "nombre": m.nombre}
        for m in db.scalars(select(Mesa).where(Mesa.activa == True).order_by(Mesa.nombre))  # noqa: E712
    ]
    return {"platos": platos, "menus": menus, "gaseosas": gaseosas, "mesas": mesas}


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
        if menu["agregados"]:
            lineas.append("  AGREGADOS de este menú (extras que se suman a la persona):")
            for ag in menu["agregados"]:
                lineas.append(f'    - agregado_id: {ag["id"]} | {ag["nombre"]} (+S/ {ag["precio"]:.2f})')
        bloques_menu.append("\n".join(lineas))
    menus_texto = "\n\n".join(bloques_menu) or "(hoy no hay menús)"

    carta_texto = "\n".join(
        f'- id: {p["id"]} | {p["nombre"]} (S/ {p["precio"]:.2f}) | también le dicen: {_comillas(p["sinonimos"])}'
        for p in contexto["platos"]
    ) or "(vacía)"
    gaseosas_texto = "\n".join(
        f'- bebida_id: {g["id"]} | {g["nombre"]} (S/ {g["precio"]:.2f})'
        for g in contexto.get("gaseosas", [])
    ) or "(no hay)"
    mesas_texto = ", ".join(f'"{m["nombre"]}"' for m in contexto.get("mesas", [])) or "(no hay)"

    return f"""Eres el intérprete de pedidos de un restaurante de menú peruano. Recibes la \
transcripción (imperfecta, viene de audio) de lo que un cliente dijo y la conviertes en un \
pedido estructurado: responde SOLO con el JSON del pedido.

MENÚS DE HOY (lo principal: cada persona pide un menú y elige un plato por tiempo):
{menus_texto}

CARTA DE HOY (platos sueltos; usa su id solo para lo que NO va dentro de un menú):
{carta_texto}

GASEOSAS (van en "gaseosas", nunca en items):
{gaseosas_texto}

MESAS del local (para "mesa"):
{mesas_texto}

CÓMO ARMAR EL PEDIDO:
- Cada persona es un elemento de "personas" con el menu_id. "Dos menús, uno con caldo y \
lomo y otro con ensalada y ají de gallina" son DOS personas. Personas idénticas pueden ir \
juntas con cantidad ("tres menús con sopa y pollo" = una persona con cantidad 3).
- Si nombra platos de entrada o segundo, eso es un menú aunque no diga la palabra \
"menú": "un caldo y un lomo" = 1 persona con esa entrada y ese segundo. Una entrada y un \
segundo forman UNA persona, en el orden en que los dijo: NUNCA hagas una persona solo con \
entradas y otra solo con segundos.
- Mismas cantidades se emparejan: "tres sopas en bolsa y tres lomos en táper" = 3 personas \
(una con cantidad 3), cada una con sopa y lomo; la sopa con empaque bolsa y el lomo con \
empaque taper. "Dos sopas y un lomo" = 2 personas: una con sopa y lomo, otra solo con sopa.
- Si un plato que nombró no está hoy, la persona igual va (con lo que sí hay) y el plato \
va en no_encontrados.
- En "elecciones" pon SOLO los tiempos que el cliente nombró, con el plato_id de ESE \
tiempo. Lo que no dijo se deja fuera: el cliente lo elige después en la pantalla.
- "Sin sopa", "sin entrada", "solo segundo", "solo la sopa" → el tiempo que no quiere va \
en "sin" (solo si dice que se puede quitar).
- Si hay un solo menú hoy, usa ese. Si hay varios y no queda claro cuál, elige el que \
tenga los platos que nombró y anota la duda en notas.
- Empaque de la persona: "para llevar", "en táper" → taper; "en bolsa" → bolsa; "en lonchera" → \
lonchera; si no dice nada o "para comer acá" → mesa. Si un plato va distinto que el \
resto de esa persona, ponlo en el empaque de esa elección; si no, "igual".
- Entrega: "todo junto", "junto" → junto; "por tiempos", "primero la sopa", "separado" \
→ separado; si no lo dice → auto.
- Nombre: "uno para Juan", "el de María" → nombre de esa persona; si no, vacío.
- Pedidos especiales de esa persona ("sin cebolla", "bien cocido") van en su nota.
- Lo que solo existe en la carta va en "items".
- Gaseosas: "una Inca Kola", "dos Coca Colas de litro" → "gaseosas" con el bebida_id de \
la lista. Sin tamaño dicho ("una Inca"), la personal. Una gaseosa que no está en la lista va \
en no_encontrados.
- Extras: "con un huevo frito", "una carne más", "con su refresco" → "agregados" de ESA \
persona con el agregado_id de su menú (no en la nota). Si no está en la lista, a la nota.
- Después: "la sopa ahora y el segundo después", "el segundo todavía no", "el segundo me \
lo traes luego" → ese plato con espera true. Si dice el plato, va elegido; si solo dice \
"el segundo después" sin nombrarlo, no lo elijas (queda por elegir).
- Mesa: "para la mesa 2B", "estamos en la 3A" → "mesa" con el nombre EXACTO de la lista \
(ignora mayúsculas y espacios: "dos be" = "2 B"). Si no dice mesa, vacío.

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
    import openai
    from openai import OpenAI

    try:
        client = OpenAI(timeout=TIMEOUT_INTERPRETE_S)
        response = client.responses.create(
            model=MODELO_INTERPRETE,
            # El menú va primero y fijo: OpenAI cachea ese prefijo solo
            instructions=construir_system(contexto),
            input=texto,
            text={"format": FORMATO_PEDIDO},
            reasoning={"effort": ESFUERZO_INTERPRETE},
            max_output_tokens=4000,
            prompt_cache_key="voz-pedido",
            store=False,
        )
    except openai.OpenAIError as e:
        raise VozError("No te escuché bien, intenta de nuevo o usa los botones", str(e))

    try:
        crudo = json.loads(response.output_text)
    except (TypeError, ValueError) as e:
        # Respuesta cortada, rechazada o vacía: que el cliente use los botones
        raise VozError("No pude entender el pedido, usa los botones por favor",
                       f"respuesta sin JSON ({response.status}): {e}")
    return _depurar(crudo, contexto), _costo_interprete(response.usage)


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
        empaque = persona.get("empaque")
        empaque = empaque if empaque in EMPAQUES else "mesa"
        elecciones: dict[int, int] = {}
        empaques: dict[int, str] = {}
        espera: list[int] = []
        for e in persona.get("elecciones", []):
            orden, plato_id = _entero(e.get("tiempo_orden")), _entero(e.get("plato_id"))
            tiempo = tiempos.get(orden)
            if tiempo is None or orden in sin:
                continue
            if any(a["plato_id"] == plato_id for a in tiempo["alternativas"]):
                elecciones[orden] = plato_id
                # Empaque propio del plato ("la sopa en bolsa") si difiere
                propio = e.get("empaque")
                if propio in EMPAQUES and propio != empaque:
                    empaques[orden] = propio
                if e.get("espera") is True:
                    espera.append(orden)
        entrega = persona.get("entrega")
        personas.append({
            "menu_id": menu["id"],
            "cantidad": cantidad,
            "elecciones": elecciones,
            "sin": sin,
            "empaque": empaque,
            "empaques": empaques,
            "espera": sorted(espera),
            "agregados": _agregados_validos(persona.get("agregados", []), menu),
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
    gaseosas_ids = {g["id"] for g in contexto.get("gaseosas", [])}
    gaseosas = []
    for g in resultado.get("gaseosas", []):
        bebida_id, cantidad = _entero(g.get("bebida_id")), _entero(g.get("cantidad"))
        if bebida_id in gaseosas_ids and cantidad is not None and 0 < cantidad <= 20:
            gaseosas.append({"bebida_id": bebida_id, "cantidad": cantidad})
        else:
            extranos.append(f"gaseosa {g.get('bebida_id', '?')}")

    return {
        "personas": personas,
        "items": items,
        "gaseosas": gaseosas,
        "mesa_id": _mesa_por_nombre(str(resultado.get("mesa") or ""), contexto.get("mesas", [])),
        "no_encontrados": list(resultado.get("no_encontrados", [])) + extranos,
        "notas": resultado.get("notas", ""),
    }


def _normalizar_mesa(nombre: str) -> str:
    return "".join(nombre.lower().split())


def _mesa_por_nombre(dicha: str, mesas: list[dict]) -> int | None:
    """La mesa dicha ("2b", "2 B") contra los nombres reales; sin match, None."""
    buscada = _normalizar_mesa(dicha)
    if not buscada:
        return None
    return next((m["id"] for m in mesas if _normalizar_mesa(m["nombre"]) == buscada), None)


def _agregados_validos(crudos: list, menu: dict) -> list[dict]:
    ids = {a["id"] for a in menu.get("agregados", [])}
    salida = []
    for a in crudos:
        agregado_id, cantidad = _entero(a.get("agregado_id")), _entero(a.get("cantidad"))
        if agregado_id in ids and cantidad is not None and 0 < cantidad <= 10:
            salida.append({"agregado_id": agregado_id, "cantidad": cantidad})
    return salida


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
                           "plato_id": plato_id, "nombre": alt["nombre"],
                           "empaque": p["empaques"].get(orden),
                           "espera": orden in p["espera"]})
        salida.append({
            **p,
            # JSON no tiene claves enteras: el frontend recibe la lista
            "elecciones": platos,
            "menu_nombre": menu["nombre"],
            "precio": menu["precio"],
            "sin_rotulos": [tiempos[o]["rotulo"] for o in p["sin"]],
            "agregados": [
                {**a, "nombre": next(x["nombre"] for x in menu["agregados"] if x["id"] == a["agregado_id"])}
                for a in p["agregados"]
            ],
        })
    return salida


def _costo_interprete(usage) -> float | None:
    precios = PRECIOS_INTERPRETE_POR_MTOK_USD.get(MODELO_INTERPRETE)
    if precios is None or usage is None:
        return None
    entrada, en_cache, salida = precios
    cacheados = getattr(usage.input_tokens_details, "cached_tokens", 0) or 0
    return (
        (usage.input_tokens - cacheados) * entrada
        + cacheados * en_cache
        + usage.output_tokens * salida
    ) / 1_000_000


def costo_transcripcion(duracion_s: float | None) -> float:
    por_minuto = PRECIOS_TRANSCRIPCION_POR_MIN_USD.get(MODELO_TRANSCRIPCION, 0.006)
    return ((duracion_s or 0) / 60) * por_minuto


def pista_de_vocabulario(contexto: dict) -> str:
    """Los nombres de hoy (y cómo les dicen) para la transcripción."""
    nombres: list[str] = []
    for p in contexto["platos"]:
        nombres += [p["nombre"], *p["sinonimos"]]
    for m in contexto["menus"]:
        nombres.append(m["nombre"])
    nombres += [g["nombre"] for g in contexto.get("gaseosas", [])]
    vistos = list(dict.fromkeys(n for n in nombres if n))
    return "Pedido en un restaurante peruano. Platos de hoy: " + ", ".join(vistos)[:800]


def procesar_audio(db: Session, audio_bytes: bytes, nombre: str, duracion_s: float | None):
    """Pipeline completo: transcribir + interpretar + resolver contra lo de hoy.

    Devuelve (transcripcion, resultado, items_resueltos, personas_resueltas,
    extras {gaseosas, mesa}, latencia_ms, costo_usd).
    """
    inicio = time.perf_counter()
    contexto = contexto_de_hoy(db)
    if not contexto["platos"] and not contexto["menus"]:
        raise VozError("Todavía no hay menú cargado, pregunta en caja por favor")

    transcripcion = transcribir(audio_bytes, nombre, pista_de_vocabulario(contexto))
    resultado, costo_interprete = interpretar(transcripcion, contexto)
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
    gaseosas_por_id = {g["id"]: g for g in contexto["gaseosas"]}
    extras = {
        "gaseosas": [
            {**g, "nombre": gaseosas_por_id[g["bebida_id"]]["nombre"],
             "precio": gaseosas_por_id[g["bebida_id"]]["precio"]}
            for g in resultado.get("gaseosas", [])
        ],
        "mesa": next(
            ({"id": m["id"], "nombre": m["nombre"]} for m in contexto["mesas"] if m["id"] == resultado.get("mesa_id")),
            None,
        ),
    }
    costo_total = costo_transcripcion(duracion_s) + (costo_interprete or 0)
    return (transcripcion, resultado, items_resueltos, personas, extras,
            latencia_ms, round(costo_total, 6))
