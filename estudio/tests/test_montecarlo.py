"""El motor en Python da EXACTAMENTE lo mismo que la calculadora HTML
(`prototipos/rentabilidad-ciudades.html`): equilibrio y Monte Carlo en 96
combinaciones (12 ciudades × segmento × año × formal/informal, con sueldo
del dueño, 5 balones, q de referencia 100 popular / 60 ejecutivo).

`referencia_prototipo.json` se generó corriendo el JavaScript del
prototipo con Node; si el prototipo cambia, se regenera."""
import json
from pathlib import Path

import pytest

from motor import Escenario, cargar_dataset, equilibrio, local_de_ciudad, simular

DATA = cargar_dataset()
CIUDAD = {c["id"]: c for c in DATA["ciudades"]}
REF = json.loads((Path(__file__).parent / "referencia_prototipo.json").read_text())


@pytest.mark.parametrize("clave", sorted(REF))
def test_igual_que_el_prototipo(clave):
    ciudad, seg, anio, formal = clave.split("|")
    esc = Escenario(segmento="popular" if seg == "pop" else "ejecutivo", anio=int(anio),
                    formal=formal == "1", balones=5, sueldo_dueno=True)
    local = local_de_ciudad(CIUDAD[ciudad], esc.segmento)
    assert equilibrio(local, esc, DATA["nacional"]) == REF[clave]["be"]
    r = simular(local, esc, DATA["nacional"], DATA["riesgo"], q_ref=100 if seg == "pop" else 60)
    esperado = REF[clave]["sim"]
    assert r.prob_perdida == pytest.approx(esperado["loss"])
    for p in ("p10", "p50", "p90"):
        assert getattr(r, p) == pytest.approx(esperado[p], rel=1e-9, abs=1e-6)
