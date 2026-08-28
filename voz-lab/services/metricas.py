"""Métricas de evaluación: WER de transcripción y match de interpretación.

Separar estas dos medidas es el corazón del experimento: si el WER es
alto, el problema es micrófono/ruido (Whisper); si el WER es bajo pero
el pedido sale mal, el problema es el prompt de interpretación (Claude).
"""
import re
import unicodedata


def _normalizar(texto: str) -> list[str]:
    """Minúsculas, sin tildes ni puntuación → lista de palabras."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w\s]", " ", texto)
    return texto.split()


def wer(referencia: str, hipotesis: str) -> float:
    """Word Error Rate aproximado: distancia de edición a nivel de palabra
    entre lo que realmente se dijo y lo que transcribió Whisper."""
    ref = _normalizar(referencia)
    hip = _normalizar(hipotesis)
    if not ref:
        return 0.0 if not hip else 1.0

    # Levenshtein clásico por palabras
    anterior = list(range(len(hip) + 1))
    for i, palabra_ref in enumerate(ref, 1):
        actual = [i]
        for j, palabra_hip in enumerate(hip, 1):
            costo = 0 if palabra_ref == palabra_hip else 1
            actual.append(min(
                anterior[j] + 1,        # borrado
                actual[j - 1] + 1,      # inserción
                anterior[j - 1] + costo # sustitución
            ))
        anterior = actual
    return anterior[-1] / len(ref)


def parsear_esperado(texto: str, menu: dict) -> tuple[dict[str, int], list[str]]:
    """Parsea el pedido esperado anotado a mano ("2x lomo saltado, 1x chicha")
    a {plato_id: cantidad}, resolviendo nombres y sinónimos del menú.

    Devuelve también lo que no se pudo resolver (para avisar en el reporte).
    """
    indice: dict[str, str] = {}
    for plato in menu["platos"]:
        claves = [plato["id"], plato["nombre"]] + list(plato.get("sinonimos", []))
        for clave in claves:
            indice[" ".join(_normalizar(clave))] = plato["id"]

    esperado: dict[str, int] = {}
    no_resueltos: list[str] = []
    for parte in re.split(r"[,;+]| y ", texto):
        parte = parte.strip()
        if not parte:
            continue
        m = re.match(r"^(\d+)\s*x?\s*(.+)$", parte)
        cantidad, nombre = (int(m.group(1)), m.group(2)) if m else (1, parte)
        clave = " ".join(_normalizar(nombre))
        if clave in indice:
            plato_id = indice[clave]
            esperado[plato_id] = esperado.get(plato_id, 0) + cantidad
        else:
            # Intento parcial: alguna palabra del nombre coincide con un sinónimo
            plato_id = next(
                (indice[p] for p in _normalizar(nombre) if p in indice), None
            )
            if plato_id:
                esperado[plato_id] = esperado.get(plato_id, 0) + cantidad
            else:
                no_resueltos.append(parte)
    return esperado, no_resueltos


def comparar_interpretacion(items: list[dict], esperado: dict[str, int]) -> str:
    """"sí" (match exacto de items+cantidades), "parcial" (algo coincide) o "no"."""
    interpretado = {i["plato_id"]: i["cantidad"] for i in items}
    if interpretado == esperado:
        return "sí"
    aciertos = sum(
        1 for plato_id, cant in esperado.items() if interpretado.get(plato_id) == cant
    )
    coincidencia_platos = len(set(interpretado) & set(esperado))
    return "parcial" if (aciertos or coincidencia_platos) else "no"


# Costos aproximados (USD) para el costo_estimado_usd del CSV
PRECIO_WHISPER_POR_MIN = 0.006
PRECIOS_CLAUDE_POR_MTOK = {
    # modelo: (entrada, lectura de caché, escritura de caché, salida)
    "claude-opus-5": (5.00, 0.50, 6.25, 25.00),
    "claude-sonnet-5": (2.00, 0.20, 2.50, 10.00),
    "claude-haiku-4-5": (1.00, 0.10, 1.25, 5.00),
}


def costo_whisper(duracion_seg: float | None) -> float | None:
    if duracion_seg is None:
        return None
    return (duracion_seg / 60) * PRECIO_WHISPER_POR_MIN


def costo_claude(usage, modelo: str) -> float | None:
    precios = PRECIOS_CLAUDE_POR_MTOK.get(modelo)
    if precios is None:
        return None
    entrada, cache_lectura, cache_escritura, salida = precios
    return (
        usage.input_tokens * entrada
        + (usage.cache_read_input_tokens or 0) * cache_lectura
        + (usage.cache_creation_input_tokens or 0) * cache_escritura
        + usage.output_tokens * salida
    ) / 1_000_000
