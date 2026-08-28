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
