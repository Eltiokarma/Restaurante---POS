"""Órdenes: correlativo diario, snapshot de precios, estados y totales."""
from datetime import timedelta

from app.models import Orden, Plato, hoy_lima


def crear_orden(client, items):
    return client.post("/api/orders", json={"items": items})


def test_correlativo_diario_incrementa(client, menu_ejemplo):
    r1 = crear_orden(client, [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}])
    r2 = crear_orden(client, [{"plato_id": menu_ejemplo["Chicha morada"], "cantidad": 2}])
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["orden"]["numero_orden_dia"] == 1
    assert r2.json()["orden"]["numero_orden_dia"] == 2


def test_correlativo_reinicia_cada_dia(client, db, menu_ejemplo):
    # Una orden de "ayer" con número alto no debe afectar el correlativo de hoy
    ayer = hoy_lima() - timedelta(days=1)
    db.add(Orden(numero_orden_dia=47, fecha=ayer, hora="12:00:00", total=10.0,
                 estado="entregado", impreso=True))
    db.commit()

    r = crear_orden(client, [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}])
    assert r.json()["orden"]["numero_orden_dia"] == 1


def test_total_y_snapshot_de_precios(client, db, menu_ejemplo):
    r = crear_orden(client, [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 2},
        {"plato_id": menu_ejemplo["Chicha morada"], "cantidad": 1},
    ])
    orden = r.json()["orden"]
    assert orden["total"] == 33.5

    # Si el precio del plato cambia después, la orden histórica no se altera
    plato = db.get(Plato, menu_ejemplo["Lomo saltado"])
    plato.precio = 99.0
    db.commit()

    hoy = client.get("/api/orders/today").json()
    item = next(i for i in hoy["ordenes"][0]["items"] if i["nombre"] == "Lomo saltado")
    assert item["precio"] == 15.0
    assert hoy["total_vendido"] == 33.5


def test_plato_agotado_devuelve_409(client, menu_ejemplo):
    r = crear_orden(client, [{"plato_id": menu_ejemplo["Seco de res"], "cantidad": 1}])
    assert r.status_code == 409
    assert "Seco de res" in r.json()["detail"]


def test_orden_vacia_o_invalida_es_422(client, menu_ejemplo):
    assert client.post("/api/orders", json={"items": []}).status_code == 422
    assert crear_orden(client, [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 0}]).status_code == 422


def test_avance_de_estado(client, menu_ejemplo):
    orden_id = crear_orden(client, [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}]).json()["orden"]["id"]

    for estado in ["preparando", "listo", "entregado"]:
        r = client.patch(f"/api/orders/{orden_id}/status", json={"estado": estado})
        assert r.status_code == 200 and r.json()["estado"] == estado

    assert client.patch(f"/api/orders/{orden_id}/status", json={"estado": "volando"}).status_code == 422
    assert client.patch("/api/orders/9999/status", json={"estado": "listo"}).status_code == 404


def test_orders_today_solo_muestra_hoy(client, db, menu_ejemplo):
    ayer = hoy_lima() - timedelta(days=1)
    db.add(Orden(numero_orden_dia=1, fecha=ayer, hora="11:00:00", total=50.0,
                 estado="entregado", impreso=True))
    db.commit()
    crear_orden(client, [{"plato_id": menu_ejemplo["Chicha morada"], "cantidad": 1}])

    data = client.get("/api/orders/today").json()
    assert len(data["ordenes"]) == 1
    assert data["total_vendido"] == 3.5
