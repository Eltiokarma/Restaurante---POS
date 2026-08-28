"""Tests offline del intérprete (sin llamar a la API)."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from services.interpreter import TOOL_REGISTRAR_PEDIDO, _depurar, cargar_menu, construir_system


def menu():
    return cargar_menu(BASE / "menu.json")


def test_menu_carga_y_tiene_sinonimos():
    m = menu()
    ids = [p["id"] for p in m["platos"]]
    assert "lomo" in ids and "chicha" in ids
    lomo = next(p for p in m["platos"] if p["id"] == "lomo")
    assert "lomito" in lomo["sinonimos"]


def test_system_prompt_incluye_menu_y_reglas():
    texto = construir_system(menu())
    assert "id: lomo" in texto
    assert "chichita" in texto  # sinónimos presentes
    assert "registrar_pedido" in texto
    assert "no_encontrados" in texto
    # Reglas clave de coloquialismos y correcciones
    assert "ÚLTIMA intención" in texto
    assert "cantidad es 1" in texto


def test_tool_schema_es_estricto_y_valido():
    schema = TOOL_REGISTRAR_PEDIDO["input_schema"]
    assert TOOL_REGISTRAR_PEDIDO["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"items", "no_encontrados", "notas"}
    item = schema["properties"]["items"]["items"]
    assert set(item["required"]) == {"plato_id", "cantidad"}
    json.dumps(schema)  # serializable


def test_depurar_mueve_ids_desconocidos_a_no_encontrados():
    crudo = {
        "items": [
            {"plato_id": "lomo", "cantidad": 2},
            {"plato_id": "ceviche", "cantidad": 1},  # no existe en el menú
            {"plato_id": "chicha", "cantidad": 0},   # cantidad inválida
        ],
        "no_encontrados": ["inca kola"],
        "notas": "",
    }
    limpio = _depurar(crudo, menu())
    assert limpio["items"] == [{"plato_id": "lomo", "cantidad": 2}]
    assert "inca kola" in limpio["no_encontrados"]
    assert "ceviche" in limpio["no_encontrados"]


def test_depurar_tolera_respuesta_incompleta():
    limpio = _depurar({}, menu())
    assert limpio == {"items": [], "no_encontrados": [], "notas": ""}
