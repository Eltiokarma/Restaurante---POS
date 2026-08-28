"""Resumen del día y export CSV para el dueño."""


def preparar_dia(client, menu_ejemplo):
    lomo, chicha = menu_ejemplo["Lomo saltado"], menu_ejemplo["Chicha morada"]
    client.post("/api/orders", json={
        "items": [{"plato_id": lomo, "cantidad": 2}], "duracion_seg": 60,
    })
    client.post("/api/orders", json={
        "items": [{"plato_id": lomo, "cantidad": 1}, {"plato_id": chicha, "cantidad": 2}],
        "duracion_seg": 120,
    })
    client.post("/api/cancellations", json={
        "items": [{"nombre": "Lomo saltado", "precio": 15.0, "cantidad": 1}], "total": 15.0,
    })


def test_resumen_de_hoy(client, admin_headers, menu_ejemplo):
    preparar_dia(client, menu_ejemplo)
    data = client.get("/api/stats/today", headers=admin_headers).json()

    assert data["num_ordenes"] == 2
    assert data["total_vendido"] == 52.0  # 30 + 15 + 7
    assert data["duracion_promedio_seg"] == 90

    ventas = {v["nombre"]: v for v in data["ventas_por_plato"]}
    assert ventas["Lomo saltado"] == {"nombre": "Lomo saltado", "cantidad": 3, "total": 45.0}
    assert ventas["Chicha morada"]["cantidad"] == 2

    assert data["num_cancelaciones"] == 1
    assert data["total_cancelado"] == 15.0
    assert data["tasa_cancelacion"] == round(1 / 3, 3)

    assert sum(h["cantidad"] for h in data["ordenes_por_hora"]) == 2


def test_resumen_dia_vacio(client, admin_headers):
    data = client.get("/api/stats/today", headers=admin_headers).json()
    assert data["num_ordenes"] == 0
    assert data["total_vendido"] == 0
    assert data["duracion_promedio_seg"] is None
    assert data["ventas_por_plato"] == []
    assert data["tasa_cancelacion"] == 0.0


def test_duracion_es_opcional_y_acotada(client, admin_headers, menu_ejemplo):
    lomo = menu_ejemplo["Lomo saltado"]
    # Sin duración: válido
    r = client.post("/api/orders", json={"items": [{"plato_id": lomo, "cantidad": 1}]})
    assert r.status_code == 201
    # Fuera de rango: rechazada
    r = client.post("/api/orders", json={
        "items": [{"plato_id": lomo, "cantidad": 1}], "duracion_seg": 99999,
    })
    assert r.status_code == 422

    data = client.get("/api/stats/today", headers=admin_headers).json()
    assert data["duracion_promedio_seg"] is None  # ninguna orden la trajo


def test_export_csv(client, admin_headers, menu_ejemplo):
    preparar_dia(client, menu_ejemplo)
    r = client.get("/api/stats/export", headers=admin_headers)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "ventas-" in r.headers["content-disposition"]

    lineas = r.text.lstrip("﻿").strip().split("\n")
    assert lineas[0].startswith("fecha;orden;hora;estado;plato")
    assert len(lineas) == 4  # cabecera + 3 items (2+1 órdenes con 1 y 2 items)
    assert "Lomo saltado" in r.text


def test_stats_requieren_admin(client):
    assert client.get("/api/stats/today").status_code == 401
    assert client.get("/api/stats/export").status_code == 401
    assert client.get("/api/stats/range?desde=2026-01-01&hasta=2026-01-07").status_code == 401


# ---------- Resumen por rango (semanal/histórico) ----------


def insertar_orden_pasada(db, dias_atras, numero, total, platos):
    """Inserta una orden histórica directamente en la BD."""
    from datetime import timedelta

    from app.models import Orden, OrdenItem, hoy_lima

    orden = Orden(
        numero_orden_dia=numero,
        fecha=hoy_lima() - timedelta(days=dias_atras),
        hora="12:30:00",
        total=total,
        estado="entregado",
        impreso=True,
    )
    for nombre, precio, cantidad in platos:
        orden.items.append(
            OrdenItem(nombre_snapshot=nombre, precio_snapshot=precio, cantidad=cantidad)
        )
    db.add(orden)
    db.commit()


def test_resumen_de_rango_agrupa_por_dia(client, admin_headers, db, menu_ejemplo):
    from app.models import hoy_lima
    from datetime import timedelta

    insertar_orden_pasada(db, 2, 1, 30.0, [("Lomo saltado", 15.0, 2)])
    insertar_orden_pasada(db, 1, 1, 15.0, [("Lomo saltado", 15.0, 1)])
    insertar_orden_pasada(db, 1, 2, 7.0, [("Chicha morada", 3.5, 2)])
    preparar_dia(client, menu_ejemplo)  # 2 órdenes de hoy (52.0) + 1 cancelación

    hoy = hoy_lima()
    desde = (hoy - timedelta(days=6)).isoformat()
    data = client.get(
        f"/api/stats/range?desde={desde}&hasta={hoy.isoformat()}", headers=admin_headers
    ).json()

    assert data["num_ordenes"] == 5
    assert data["total_vendido"] == 104.0  # 30 + 22 + 52

    dias = {d["fecha"]: d for d in data["ventas_por_dia"]}
    assert len(dias) == 3
    assert dias[(hoy - timedelta(days=1)).isoformat()] == {
        "fecha": (hoy - timedelta(days=1)).isoformat(), "ordenes": 2, "total": 22.0,
    }

    ventas = {v["nombre"]: v for v in data["ventas_por_plato"]}
    assert ventas["Lomo saltado"]["cantidad"] == 6  # 2 + 1 + 3 de hoy


def test_rango_invalido(client, admin_headers):
    r = client.get("/api/stats/range?desde=2026-02-01&hasta=2026-01-01", headers=admin_headers)
    assert r.status_code == 422
    r = client.get("/api/stats/range?desde=2020-01-01&hasta=2026-01-01", headers=admin_headers)
    assert r.status_code == 422


def test_export_csv_por_rango(client, admin_headers, db, menu_ejemplo):
    from app.models import hoy_lima
    from datetime import timedelta

    insertar_orden_pasada(db, 1, 1, 15.0, [("Lomo saltado", 15.0, 1)])
    preparar_dia(client, menu_ejemplo)

    hoy = hoy_lima()
    desde = (hoy - timedelta(days=6)).isoformat()
    r = client.get(
        f"/api/stats/export?desde={desde}&hasta={hoy.isoformat()}", headers=admin_headers
    )
    assert r.status_code == 200
    assert f"ventas-{desde}-a-{hoy.isoformat()}.csv" in r.headers["content-disposition"]
    lineas = r.text.lstrip("﻿").strip().split("\n")
    assert len(lineas) == 5  # cabecera + 1 histórica + 3 items de hoy
    # Orden cronológico: la histórica primero
    assert lineas[1].startswith((hoy - timedelta(days=1)).isoformat())
