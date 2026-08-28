"""Tests offline de las métricas de evaluación."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from services.interpreter import cargar_menu
from services.metricas import comparar_interpretacion, costo_whisper, parsear_esperado, wer


def menu():
    return cargar_menu(BASE / "menu.json")


# ---------- WER ----------

def test_wer_identico_es_cero():
    assert wer("dos lomos y una chicha", "dos lomos y una chicha") == 0.0


def test_wer_ignora_mayusculas_tildes_y_puntuacion():
    assert wer("¿Un ají de gallina, porfa!", "un aji de gallina porfa") == 0.0


def test_wer_cuenta_sustituciones():
    # 1 palabra mal de 5 => 0.2
    assert wer("dos lomos y una chicha", "dos logos y una chicha") == 0.2


def test_wer_transcripcion_vacia():
    assert wer("dos lomos", "") == 1.0
    assert wer("", "") == 0.0


# ---------- Parseo del pedido esperado ----------

def test_parsear_formato_estandar():
    esperado, no_resueltos = parsear_esperado("2x lomo saltado, 1x chicha", menu())
    assert esperado == {"lomo": 2, "chicha": 1}
    assert no_resueltos == []


def test_parsear_sinonimos_y_cantidad_implicita():
    esperado, _ = parsear_esperado("sequito y 2 chichitas... no, 2x chichita", menu())
    # "sequito" sin número = 1; sinónimos resueltos por menú
    assert esperado["seco"] == 1
    assert esperado["chicha"] >= 2


def test_parsear_no_resuelto_se_reporta():
    esperado, no_resueltos = parsear_esperado("1x ceviche", menu())
    assert esperado == {}
    assert no_resueltos == ["1x ceviche"]


# ---------- Comparación de interpretación ----------

def test_match_exacto():
    items = [{"plato_id": "lomo", "cantidad": 2}, {"plato_id": "chicha", "cantidad": 1}]
    assert comparar_interpretacion(items, {"lomo": 2, "chicha": 1}) == "sí"


def test_match_parcial_por_cantidad():
    items = [{"plato_id": "lomo", "cantidad": 1}, {"plato_id": "chicha", "cantidad": 1}]
    assert comparar_interpretacion(items, {"lomo": 2, "chicha": 1}) == "parcial"


def test_match_no():
    items = [{"plato_id": "aji", "cantidad": 1}]
    assert comparar_interpretacion(items, {"lomo": 2}) == "no"


def test_match_vacios_es_si():
    assert comparar_interpretacion([], {}) == "sí"


# ---------- Costos ----------

def test_costo_whisper():
    assert costo_whisper(60) == 0.006
    assert costo_whisper(None) is None
