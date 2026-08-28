"""Intérprete de pedidos hablados con Claude (tool use).

Este es el MISMO diseño que usará el POS en la Fase 3: recibe la
transcripción de lo que dijo el cliente y el menú del día, y devuelve
la estructura {"items": [...], "no_encontrados": [...], "notas": ""}.
Lo aprendido iterando aquí (prompt, sinónimos, casos borde) se
transfiere directo.
"""
import json
import os
from pathlib import Path

import anthropic

MODELO_DEFAULT = "claude-opus-5"

# Estructura de salida: idéntica a la que consumirá el carrito del POS
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
                        "plato_id": {"type": "string", "description": "El id exacto del plato en el menú"},
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
                "description": "Ambigüedades o dudas que un humano debería revisar; cadena vacía si no hay",
            },
        },
        "required": ["items", "no_encontrados", "notas"],
        "additionalProperties": False,
    },
}


class InterpretacionFallida(Exception):
    pass


def cargar_menu(ruta: str | Path) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def construir_system(menu: dict) -> str:
    """System prompt con el menú del día completo y sinónimos por plato.

    Es estable durante toda una corrida de evaluación: se cachea con
    prompt caching, así iterar sobre muchos audios sale más barato.
    """
    lineas_menu = []
    for plato in menu["platos"]:
        sinonimos = ", ".join(f'"{s}"' for s in plato.get("sinonimos", []))
        lineas_menu.append(
            f'- id: {plato["id"]} | {plato["nombre"]} (S/ {plato["precio"]:.2f})'
            f" | también le dicen: {sinonimos}"
        )
    menu_texto = "\n".join(lineas_menu)

    return f"""Eres el intérprete de pedidos de un restaurante de menú peruano. Recibes la \
transcripción (imperfecta, viene de audio) de lo que un cliente dijo en el mostrador y \
debes convertirla en un pedido estructurado llamando a la herramienta registrar_pedido \
exactamente una vez.

MENÚ DE HOY (los únicos platos que existen):
{menu_texto}

REGLAS DE INTERPRETACIÓN:
- Español peruano coloquial: "uno de lomo" = 1 lomo saltado; "un seco" = 1 seco de res; \
"chichita" = chicha morada; "agüita" o "refresquito" = refresco del día. Los diminutivos \
y apócopes son normalísimos.
- Cantidad implícita: si nombra un plato sin número ("me da lomo", "un ají"), la cantidad es 1.
- Números en palabras o cifras: "dos", "2", "un par de" = 2; "tres" = 3.
- Pedidos múltiples en una frase: "dos lomos y una chicha" son dos items.
- Muletillas y cortesía: ignora "este...", "eh", "me da", "porfa", "por favor", "señorita", \
"joven" — no cambian el pedido.
- Correcciones a mitad de frase: vale la ÚLTIMA intención. "un lomo... no, mejor dos" = 2 \
lomos. "una chicha... mejor no" = sin chicha.
- La transcripción puede traer errores de audio: si una palabra suena a un plato del menú \
("logo saltado", "ceco"), asume el plato más parecido y anótalo en notas.
- Lo que pidan y NO esté en el menú de hoy ("ceviche", "inca kola") va en no_encontrados, \
escrito tal como lo dijeron. NUNCA lo conviertas en otro plato.
- Si algo queda genuinamente ambiguo (¿"dos" se refería a qué plato?), decide lo más \
razonable y explica la duda en notas.
- Si la transcripción no contiene ningún pedido, devuelve items y no_encontrados vacíos \
con una nota.

Usa siempre los id exactos del menú (columna "id")."""


def _depurar(resultado: dict, menu: dict) -> dict:
    """Defensa final: un plato_id que no exista en el menú pasa a no_encontrados."""
    ids_validos = {p["id"] for p in menu["platos"]}
    items, extranos = [], []
    for item in resultado.get("items", []):
        if item.get("plato_id") in ids_validos and int(item.get("cantidad", 0)) > 0:
            items.append({"plato_id": item["plato_id"], "cantidad": int(item["cantidad"])})
        else:
            extranos.append(str(item.get("plato_id", "?")))
    return {
        "items": items,
        "no_encontrados": list(resultado.get("no_encontrados", [])) + extranos,
        "notas": resultado.get("notas", ""),
    }


def interpretar(
    transcripcion: str,
    menu: dict,
    client: anthropic.Anthropic | None = None,
    modelo: str | None = None,
) -> tuple[dict, object]:
    """Interpreta una transcripción. Devuelve (resultado, usage).

    ``usage`` sirve para sumar tokens y estimar el costo de la corrida.
    """
    client = client or anthropic.Anthropic()
    modelo = modelo or os.getenv("MODELO_INTERPRETE", MODELO_DEFAULT)

    response = client.messages.create(
        model=modelo,
        max_tokens=8000,
        system=[{
            "type": "text",
            "text": construir_system(menu),
            # El menú no cambia durante la corrida: se cachea para abaratar
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[TOOL_REGISTRAR_PEDIDO],
        messages=[{"role": "user", "content": transcripcion}],
    )

    if response.stop_reason == "refusal":
        raise InterpretacionFallida("El modelo declinó la solicitud")

    for block in response.content:
        if block.type == "tool_use" and block.name == "registrar_pedido":
            return _depurar(dict(block.input), menu), response.usage

    raise InterpretacionFallida("La respuesta no llamó a registrar_pedido")
