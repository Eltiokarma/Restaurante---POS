"""Ninguna clase del frontend puede parecer un anuncio.

Le pasó al dueño: la barra lateral del admin no aparecía en su PC y sí en
el celular. La clase se llamaba `ad-rail` ("ad" por admin) y EasyList —la
lista de filtros que usan TODOS los bloqueadores de publicidad— trae la
regla genérica `##.ad-rail`, más de mil reglas que empiezan con `.ad-` y
otras tantas para "sponsor", "promo" y compañía. El bloqueador le borraba
el menú de navegación entero.
"""
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"

# Prefijos que los bloqueadores borran de cualquier página
PELIGROSOS = re.compile(
    r"\b(ad|ads|adv|advert|advertisement|anuncio|sponsor|sponsored|promo|popup)[-_]",
    re.IGNORECASE,
)


def _clases_de_css(texto: str) -> set[str]:
    return set(re.findall(r"\.([a-zA-Z][\w-]*)", texto))


def _clases_de_tsx(texto: str) -> set[str]:
    clases: set[str] = set()
    for bloque in re.findall(r"className=[\"{`]([^\"}`]*)", texto):
        clases.update(p for p in bloque.split() if re.fullmatch(r"[a-zA-Z][\w-]*", p))
    return clases


def test_ninguna_clase_parece_un_anuncio():
    if not FRONTEND.is_dir():
        pytest.skip("sin código del frontend")

    sospechosas: dict[str, set[str]] = {}
    for archivo in [*FRONTEND.rglob("*.css"), *FRONTEND.rglob("*.tsx")]:
        texto = archivo.read_text(encoding="utf-8")
        clases = _clases_de_css(texto) if archivo.suffix == ".css" else _clases_de_tsx(texto)
        malas = {c for c in clases if PELIGROSOS.match(c)}
        if malas:
            sospechosas[archivo.name] = malas

    assert not sospechosas, (
        "Estas clases las borra cualquier bloqueador de publicidad "
        f"(EasyList trae ##.ad-rail y miles más): {sospechosas}. "
        "Usa otro prefijo, por ejemplo fd- de fonda."
    )
