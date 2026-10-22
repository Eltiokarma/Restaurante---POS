"""Autoservicio criollo: planilla por puesto según la venta."""
import pytest

from motor import autoservicio as au
from motor import cargar_dataset, modelo

NAC = cargar_dataset()["nacional"]


@pytest.fixture(scope="module")
def equipos():
    return au.equipos()


def test_la_gente_no_baja_cuando_sube_la_venta(equipos):
    personas = [sum(t.cantidad for t in au.escenario(q, eq=equipos(q))[1].planilla) for q in (40, 80, 150, 200, 300)]
    assert personas == sorted(personas)


def test_planilla_cuadra_con_la_cocina(equipos):
    """Jefe, cocineros, despacho y lavado son la gente del almuerzo; el turno
    tarde se suma aparte."""
    for q in (40, 100, 150, 300):
        e = equipos(q)
        filas = au.planilla(e)
        cocina = sum(t.cantidad for t in filas if t.area == "cocina")
        assert cocina == e["cocina"] + au.turno_tarde(e)
        assert any(t.puesto == "Cajero" for t in filas)
        assert not any(t.area == "salon" for t in filas)  # sin mozos


def test_turnos_de_ocho_horas(equipos):
    h = au.horarios(equipos(150))
    for turno in ("temprano", "tarde"):
        entra, sale = h[turno]
        assert sale - entra <= 8 * 60


def test_el_almuerzo_no_colapsa(equipos):
    cfg = au.cargar()
    for q in cfg["volumenes"]:
        assert equipos(q)["servicio"]["aguanta"]


def test_equilibrio_baja_con_el_precio(equipos):
    eqs = [au.equilibrio(p, NAC, equipos) for p in (10, 11, 12, 13, 15, 18)]
    assert all(e is not None for e in eqs)
    assert eqs == sorted(eqs, reverse=True)
    q = eqs[3]  # a S/ 13
    assert au.utilidad(q, 13, NAC, equipos) >= 0 > au.utilidad(q - 5, 13, NAC, equipos)


def test_precio_minimo_deja_utilidad_cero(equipos):
    pm = au.precio_minimo(150, NAC, equipos)
    assert abs(au.utilidad(150, pm, NAC, equipos)) < 1


def test_datos_como_un_caso_mas():
    from reporte.datos import armar
    d = au.datos()
    local, esc, _sup, q = armar(d)
    assert q == au.cargar()["q"] and esc.formal and not esc.sueldo_dueno
    assert modelo(local, q, esc, NAC).util == pytest.approx(au.utilidad(q, local.precio, NAC, au.equipos()))


def test_con_mozos_usa_mozos_y_menos_insumos():
    loc, esc = au.escenario_mozos(150)
    assert any(t.puesto == "Mozo" for t in esc.planilla)
    assert loc.insumos < au.local_de(au.cargar()).insumos  # sin táper
