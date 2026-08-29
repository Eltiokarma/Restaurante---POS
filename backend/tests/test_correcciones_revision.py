"""Regresiones de la revisión de código de la Fase 4."""


def crear_insumo(client, admin_headers, nombre="Papa", unidad="kg"):
    r = client.post("/api/insumos", json={"nombre": nombre, "unidad": unidad},
                    headers=admin_headers)
    return r.json()["id"]


def crear_orden(client, menu_ejemplo, cantidad=1):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": cantidad}],
    })
    return r.json()["orden"]["id"]


def test_compra_con_costo_cero_es_422(client, admin_headers):
    """Una compra a costo 0 corrompería el costo promedio en silencio."""
    insumo = crear_insumo(client, admin_headers)
    client.post(f"/api/insumos/{insumo}/movimientos", json={
        "tipo": "compra", "cantidad": 10, "costo_total": 50.0,
    }, headers=admin_headers)

    r = client.post(f"/api/insumos/{insumo}/movimientos", json={
        "tipo": "compra", "cantidad": 10, "costo_total": 0,
    }, headers=admin_headers)
    assert r.status_code == 422

    # El costo promedio quedó intacto (5.0, no 2.5)
    insumos = client.get("/api/insumos", headers=admin_headers).json()["insumos"]
    assert insumos[0]["costo_unitario"] == 5.0


def test_anular_devuelve_lo_consumido_aunque_cambie_la_receta(client, admin_headers, menu_ejemplo):
    papa = crear_insumo(client, admin_headers)
    client.post(f"/api/insumos/{papa}/movimientos", json={
        "tipo": "compra", "cantidad": 10, "costo_total": 20.0,
    }, headers=admin_headers)
    lomo = menu_ejemplo["Lomo saltado"]
    client.put(f"/api/insumos/recetas/{lomo}", json={
        "items": [{"insumo_id": papa, "cantidad": 0.3}],
    }, headers=admin_headers)

    orden_id = crear_orden(client, menu_ejemplo)  # consume 0.3 → stock 9.7

    # El admin corrige la receta DESPUÉS de la venta
    client.put(f"/api/insumos/recetas/{lomo}", json={
        "items": [{"insumo_id": papa, "cantidad": 0.5}],
    }, headers=admin_headers)

    # Anular debe devolver los 0.3 consumidos, no los 0.5 de la receta nueva
    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})
    insumos = client.get("/api/insumos", headers=admin_headers).json()["insumos"]
    assert insumos[0]["stock_actual"] == 10.0


def test_anular_orden_sin_movimientos_no_inyecta_stock(client, admin_headers, menu_ejemplo):
    """Órdenes anteriores al kardex (o de platos sin receta) no devuelven nada."""
    papa = crear_insumo(client, admin_headers)
    client.post(f"/api/insumos/{papa}/movimientos", json={
        "tipo": "compra", "cantidad": 10, "costo_total": 20.0,
    }, headers=admin_headers)

    orden_id = crear_orden(client, menu_ejemplo)  # el lomo no tiene receta aquí
    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})

    insumos = client.get("/api/insumos", headers=admin_headers).json()["insumos"]
    assert insumos[0]["stock_actual"] == 10.0
    kardex = client.get("/api/insumos/kardex", headers=admin_headers).json()["movimientos"]
    assert all(not m["referencia"].startswith("anulación") for m in kardex)


def test_reanular_no_duplica_la_devolucion(client, admin_headers, menu_ejemplo):
    papa = crear_insumo(client, admin_headers)
    client.post(f"/api/insumos/{papa}/movimientos", json={
        "tipo": "compra", "cantidad": 10, "costo_total": 20.0,
    }, headers=admin_headers)
    lomo = menu_ejemplo["Lomo saltado"]
    client.put(f"/api/insumos/recetas/{lomo}", json={
        "items": [{"insumo_id": papa, "cantidad": 0.3}],
    }, headers=admin_headers)

    orden_id = crear_orden(client, menu_ejemplo)
    # anular → des-anular → volver a anular: el stock debe terminar en 10
    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})
    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "pendiente"})
    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})

    insumos = client.get("/api/insumos", headers=admin_headers).json()["insumos"]
    assert insumos[0]["stock_actual"] == 10.0


def test_caja_cerrada_muestra_snapshot_y_avisa_ventas_posteriores(client, menu_ejemplo):
    client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    crear_orden(client, menu_ejemplo)  # 15 efectivo
    client.post("/api/caja/cerrar", json={"monto_contado": 65.0})

    estado = client.get("/api/caja/hoy").json()
    assert estado["diferencia"] == 0.0
    assert estado["ventas_despues_del_cierre"] is False

    # Llega una venta después del cierre: el snapshot no cambia, pero avisa
    crear_orden(client, menu_ejemplo)
    estado = client.get("/api/caja/hoy").json()
    assert estado["ventas_efectivo"] == 15.0  # snapshot del cierre, no lo vivo
    assert estado["ventas_despues_del_cierre"] is True

    # Re-cerrar corrige y apaga el aviso
    client.post("/api/caja/cerrar", json={"monto_contado": 80.0})
    estado = client.get("/api/caja/hoy").json()
    assert estado["diferencia"] == 0.0
    assert estado["ventas_despues_del_cierre"] is False


def test_historial_cierres_antiguos_asume_efectivo(client, admin_headers, menu_ejemplo, db):
    """Cierres previos a la migración (ventas_* NULL) reportan su total como efectivo."""
    from datetime import timedelta

    from app.models import CierreCaja, hoy_lima

    db.add(CierreCaja(
        fecha=hoy_lima() - timedelta(days=3), hora_apertura="08:00:00",
        monto_apertura=50.0, hora_cierre="15:00:00", monto_contado=850.0,
        total_sistema=800.0, diferencia=0.0,
    ))
    db.commit()

    cierres = client.get("/api/caja/historial", headers=admin_headers).json()["cierres"]
    antiguo = cierres[0]
    assert antiguo["ventas_efectivo"] == 800.0
    assert antiguo["ventas_tarjeta"] == 0.0


def test_receta_con_payload_invalido_es_422(client, admin_headers, menu_ejemplo):
    lomo = menu_ejemplo["Lomo saltado"]
    # insumo_id no numérico → 422 (antes 500)
    r = client.put(f"/api/insumos/recetas/{lomo}", json={
        "items": [{"insumo_id": "abc", "cantidad": 1}],
    }, headers=admin_headers)
    assert r.status_code == 422
    # cantidad <= 0 → 422
    papa = crear_insumo(client, admin_headers)
    r = client.put(f"/api/insumos/recetas/{lomo}", json={
        "items": [{"insumo_id": papa, "cantidad": 0}],
    }, headers=admin_headers)
    assert r.status_code == 422
    # insumo inexistente → 422 con detalle, no descarte silencioso
    r = client.put(f"/api/insumos/recetas/{lomo}", json={
        "items": [{"insumo_id": 9999, "cantidad": 1}],
    }, headers=admin_headers)
    assert r.status_code == 422
    assert "9999" in r.json()["detail"]
