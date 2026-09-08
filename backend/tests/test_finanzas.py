"""Finanzas: costos fijos, planilla y el resumen financiero del dueño."""


def test_finanzas_requiere_admin(client):
    assert client.get("/api/finanzas/fijos").status_code == 401
    assert client.get("/api/finanzas/resumen").status_code == 401


def test_crud_costos_fijos_y_planilla(client, admin_headers):
    r = client.post("/api/finanzas/costos-fijos",
                    json={"nombre": "Alquiler", "monto_mensual": 1500},
                    headers=admin_headers)
    assert r.status_code == 201
    r = client.post("/api/finanzas/costos-fijos",
                    json={"nombre": "Luz y agua", "monto_mensual": 300},
                    headers=admin_headers)
    fijos = r.json()
    assert fijos["total_costos_mes"] == 1800.0

    r = client.post("/api/finanzas/planilla",
                    json={"nombre": "Rosa", "rol": "Cocina", "sueldo_mensual": 1200},
                    headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["total_planilla_mes"] == 1200.0

    # Editar y "borrar" (se apaga, no se pierde)
    luz = next(c for c in fijos["costos"] if c["nombre"] == "Luz y agua")
    r = client.put(f"/api/finanzas/costos-fijos/{luz['id']}",
                   json={"nombre": "Luz, agua e internet", "monto_mensual": 380},
                   headers=admin_headers)
    assert r.json()["total_costos_mes"] == 1880.0
    r = client.delete(f"/api/finanzas/costos-fijos/{luz['id']}", headers=admin_headers)
    assert r.json()["total_costos_mes"] == 1500.0

    rosa = r.json()["trabajadores"][0]
    r = client.delete(f"/api/finanzas/planilla/{rosa['id']}", headers=admin_headers)
    assert r.json()["total_planilla_mes"] == 0.0

    # Montos en cero o negativos no valen (un fijo de S/ 0 es no tenerlo)
    r = client.post("/api/finanzas/costos-fijos",
                    json={"nombre": "Nada", "monto_mensual": 0},
                    headers=admin_headers)
    assert r.status_code == 422


def test_resumen_financiero(client, admin_headers, menu_ejemplo):
    # Fijos del mes: 900 + 600 = 1500 -> S/ 50 por día
    client.post("/api/finanzas/costos-fijos",
                json={"nombre": "Alquiler", "monto_mensual": 900}, headers=admin_headers)
    client.post("/api/finanzas/planilla",
                json={"nombre": "Rosa", "rol": "Cocina", "sueldo_mensual": 600},
                headers=admin_headers)

    # Venta de hoy: 2 lomos (el fixture los tiene a S/ 15)
    r = client.post("/api/orders", json={"items": [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 2, "nota": ""},
    ]})
    assert r.status_code == 201
    venta = r.json()["orden"]["total"]

    # Una compra de insumos y un egreso del cajón, hoy
    r = client.post("/api/insumos", json={"nombre": "Arroz", "unidad": "kg",
                                          "costo_unitario": 4.0}, headers=admin_headers)
    insumo_id = r.json()["id"]
    r = client.post(f"/api/insumos/{insumo_id}/movimientos",
                    json={"tipo": "compra", "cantidad": 10, "costo_total": 40.0},
                    headers=admin_headers)
    assert r.status_code == 201
    client.post("/api/caja/abrir", json={"monto_apertura": 100})
    r = client.post("/api/caja/egresos", json={"concepto": "Gas", "monto": 25.0})
    assert r.status_code == 201

    datos = client.get("/api/finanzas/resumen?dias=7", headers=admin_headers).json()
    assert datos["ventas"] == venta
    assert datos["compras_insumos"] == 40.0
    assert datos["egresos_caja"] == 25.0
    assert datos["costos_fijos_mes"] == 900.0 and datos["planilla_mes"] == 600.0
    assert datos["fijos_periodo"] == 350.0            # 1500/30 * 7 días

    # Sin recetas no hay consumo teórico: utilidad = ventas - fijos
    assert datos["costo_insumos"] == 0.0
    assert datos["utilidad_estimada"] == round(venta - 350.0, 2)
    assert datos["margen_pct"] == 100.0
    assert datos["venta_diaria_necesaria"] == 50.0    # 1500/30 al margen 100%
    assert datos["promedio_venta_dia"] == venta       # un solo día con venta

    # El flujo diario de hoy junta las tres platas
    hoy = datos["por_dia"][-1]
    assert hoy["entro"] == venta and hoy["egresos"] == 25.0 and hoy["compras"] == 40.0

    # La cobertura avisa qué tan confiable es el costo de insumos
    assert datos["cobertura_recetas"]["con_receta"] == 0
    assert datos["cobertura_recetas"]["activos"] > 0
