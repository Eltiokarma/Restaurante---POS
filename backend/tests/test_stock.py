"""Cuántos quedan de cada entrada y segundo: lo pone la caja, se descuenta
con lo vendido hoy y es solo aviso (nunca bloquea la venta)."""
from datetime import timedelta

from app.models import Plato, hoy_lima
from tests.test_menu_encadenado import fonda  # noqa: F401  (fixture)


def _stock(client, plato_id):
    return next(s for s in client.get("/api/menu/today").json()["stock"] if s["plato_id"] == plato_id)


def test_quedan_se_descuenta_y_puede_ir_a_negativo(client, fonda):
    sopa = fonda["platos"]["Sopa criolla"]
    asado = fonda["platos"]["Asado con puré"]
    assert _stock(client, sopa)["stock"] is None  # sin contar: no se muestra cuenta

    r = client.patch(f"/api/menu/platos/{sopa}/stock", json={"stock": 2})
    assert r.status_code == 200
    assert next(s for s in r.json()["stock"] if s["plato_id"] == sopa)["quedan"] == 2

    r = client.post("/api/orders", json={"menus": [
        {"menu_id": fonda["menu_id"], "cantidad": 3, "elecciones": {"1": sopa, "2": asado}},
    ]})
    assert r.status_code == 201  # sin stock igual se vende: solo es aviso
    s = _stock(client, sopa)
    assert (s["stock"], s["vendidos"], s["quedan"]) == (2, 3, -1)

    # Anulada no cuenta
    client.patch(f"/api/orders/{r.json()['orden']['id']}/status", json={"estado": "anulada"})
    assert _stock(client, sopa)["quedan"] == 2

    # Dejar de contar
    client.patch(f"/api/menu/platos/{sopa}/stock", json={"stock": None})
    assert _stock(client, sopa)["quedan"] is None


def test_el_stock_de_ayer_no_vale_hoy(client, db, fonda):
    sopa = db.get(Plato, fonda["platos"]["Sopa criolla"])
    sopa.stock_hoy = 10
    sopa.stock_fecha = hoy_lima() - timedelta(days=1)
    db.commit()
    assert _stock(client, sopa.id)["stock"] is None
    # …pero queda de sugerencia para la caja (pedido del dueño)
    s = _stock(client, sopa.id)
    assert (s["sugerido"], s["sugerido_fecha"]) == (10, (hoy_lima() - timedelta(days=1)).isoformat())

    # Al poner el de hoy ya no hace falta sugerir
    client.patch(f"/api/menu/platos/{sopa.id}/stock", json={"stock": 12})
    s = _stock(client, sopa.id)
    assert (s["stock"], s["sugerido"]) == (12, None)
