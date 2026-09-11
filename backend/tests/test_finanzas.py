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


def test_egresos_con_categoria_y_desgloses(client, admin_headers, menu_ejemplo):
    client.post("/api/caja/abrir", json={"monto_apertura": 100})
    client.post("/api/caja/egresos",
                json={"concepto": "Lejía y esponjas", "monto": 12.0, "categoria": "limpieza"})
    client.post("/api/caja/egresos",
                json={"concepto": "Perejil del mercado", "monto": 5.0, "categoria": "hierbas"})
    # Sin categoría cae en "otros" (egresos viejos también, por la migración)
    r = client.post("/api/caja/egresos", json={"concepto": "Taxi", "monto": 8.0})
    assert r.status_code == 201
    assert {e["categoria"] for e in r.json()["egresos"]} == {"limpieza", "hierbas", "otros"}

    r = client.post("/api/orders", json={"items": [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1, "nota": ""},
    ]})
    orden = r.json()["orden"]
    client.patch(f"/api/orders/{orden['id']}/pago", json={"metodo_pago": "yape"})

    datos = client.get("/api/finanzas/resumen?dias=7", headers=admin_headers).json()
    por_cat = {e["categoria"]: e["monto"] for e in datos["egresos_por_categoria"]}
    assert por_cat == {"limpieza": 12.0, "hierbas": 5.0, "otros": 8.0}
    assert datos["entradas_por_metodo"].get("yape") == orden["total"]


def test_flujo_agrupado(client, admin_headers, menu_ejemplo, db):
    from datetime import timedelta
    from app.models import hoy_lima

    r = client.post("/api/orders", json={"items": [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1, "nota": ""},
    ]})
    assert r.status_code == 201
    hoy = hoy_lima()

    r = client.get("/api/finanzas/flujo?agrupar=dia", headers=admin_headers).json()
    assert r["agrupar"] == "dia" and len(r["filas"]) == 30
    assert r["filas"][-1]["entro"] > 0  # la venta de hoy

    r = client.get("/api/finanzas/flujo?agrupar=semana", headers=admin_headers).json()
    assert len(r["filas"]) >= 26  # 26 semanas (27 si la ventana corta una)
    lunes = hoy - timedelta(days=hoy.weekday())
    assert r["filas"][-1]["etiqueta"] == f"Sem {lunes.day:02d}/{lunes.month:02d}"
    assert r["filas"][-1]["entro"] > 0

    r = client.get("/api/finanzas/flujo?agrupar=mes", headers=admin_headers).json()
    assert r["filas"][-1]["entro"] > 0 and len(r["filas"]) in (12, 13)

    r = client.get("/api/finanzas/flujo?agrupar=anio", headers=admin_headers).json()
    assert r["filas"][-1]["etiqueta"] == str(hoy.year)
    assert r["filas"][-1]["entro"] > 0

    r = client.get("/api/finanzas/flujo?agrupar=rarisimo", headers=admin_headers)
    assert r.status_code == 422


def test_venta_manual_de_un_dia_pasado(client, admin_headers, menu_ejemplo, db):
    """El cuaderno del dueño entra al sistema: órdenes fechadas en SU día,
    una por método con el monto declarado, líneas al ranking y kardex
    descontado en esa fecha."""
    from datetime import timedelta
    from app.models import MovimientoInsumo, hoy_lima
    from sqlalchemy import select

    # Receta para que la venta manual descuente kardex
    r = client.post("/api/insumos", json={"nombre": "Arroz", "unidad": "kg",
                                          "costo_unitario": 4.0}, headers=admin_headers)
    insumo_id = r.json()["id"]
    client.put(f"/api/insumos/recetas/{menu_ejemplo['Lomo saltado']}",
               json={"items": [{"insumo_id": insumo_id, "cantidad": 0.12}]},
               headers=admin_headers)

    ayer = hoy_lima() - timedelta(days=1)
    r = client.post("/api/finanzas/ventas-manuales", json={
        "fecha": ayer.isoformat(),
        "efectivo": 601.5, "yape": 247.0,
        "lineas": [
            {"nombre": "Lomo saltado", "cantidad": 25},
            {"nombre": "Táper", "cantidad": 18, "precio": 1.0},
        ],
    }, headers=admin_headers)
    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["total"] == 848.5
    assert [o["metodo_pago"] for o in datos["ordenes"]] == ["efectivo", "yape"]
    assert [o["numero"] for o in datos["ordenes"]] == [1, 2]
    assert datos["lineas_ligadas_al_catalogo"] == 1 and datos["lineas_libres"] == 1

    # El flujo y el desglose por método ven la venta EN ese día
    flujo = client.get("/api/finanzas/flujo?agrupar=dia", headers=admin_headers).json()
    fila_ayer = next(f for f in flujo["filas"] if f["desde"] == ayer.isoformat())
    assert fila_ayer["entro"] == 848.5
    resumen = client.get("/api/finanzas/resumen?dias=7", headers=admin_headers).json()
    assert resumen["entradas_por_metodo"]["efectivo"] == 601.5
    assert resumen["entradas_por_metodo"]["yape"] == 247.0

    # El kardex consumió FECHADO en ayer: 25 × 0.12 kg de arroz
    mov = db.scalars(select(MovimientoInsumo).where(
        MovimientoInsumo.tipo == "consumo")).all()
    assert len(mov) == 1 and mov[0].fecha == ayer
    assert round(mov[0].cantidad, 2) == -3.0

    # Línea sin catálogo y sin precio → 422; fecha futura → 422
    r = client.post("/api/finanzas/ventas-manuales", json={
        "fecha": ayer.isoformat(), "efectivo": 10,
        "lineas": [{"nombre": "Cosa inventada", "cantidad": 1}],
    }, headers=admin_headers)
    assert r.status_code == 422 and "catálogo" in r.json()["detail"]
    r = client.post("/api/finanzas/ventas-manuales", json={
        "fecha": (hoy_lima() + timedelta(days=1)).isoformat(), "efectivo": 10,
    }, headers=admin_headers)
    assert r.status_code == 422


def test_tablero(client, admin_headers, menu_ejemplo):
    """El tablero devuelve, de una sola llamada, los números grandes, la
    venta por día, qué día de la semana vende más, los platos que más
    salen y los insumos ya clasificados por ABC."""
    r = client.post("/api/insumos", json={"nombre": "Carne", "unidad": "kg",
                                          "costo_unitario": 20.0}, headers=admin_headers)
    caro = r.json()["id"]
    r = client.post("/api/insumos", json={"nombre": "Sal", "unidad": "kg",
                                          "costo_unitario": 1.0}, headers=admin_headers)
    barato = r.json()["id"]
    client.put(f"/api/insumos/recetas/{menu_ejemplo['Lomo saltado']}", json={"items": [
        {"insumo_id": caro, "cantidad": 0.2}, {"insumo_id": barato, "cantidad": 0.01},
    ]}, headers=admin_headers)

    r = client.post("/api/orders", json={"items": [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 3, "nota": ""},
    ]})
    venta = r.json()["orden"]["total"]

    d = client.get("/api/finanzas/tablero?dias=30", headers=admin_headers).json()
    assert d["dias"] == 30 and len(d["por_dia"]) == 30
    assert d["kpis"]["ventas"] == venta
    assert d["kpis"]["dias_con_venta"] == 1
    assert d["kpis"]["promedio_dia"] == venta
    assert d["kpis"]["mejor_dia"]["ventas"] == venta
    # Costo: 3 × (0.2 kg × 20 + 0.01 × 1) = 12.03
    assert d["kpis"]["costo_insumos"] == 12.03
    assert d["kpis"]["margen_pct"] == round((venta - 12.03) / venta * 100, 1)

    # Qué día de la semana vende más: hoy tiene el promedio, los otros 0
    con_venta = [x for x in d["por_dia_semana"] if x["veces"] > 0]
    assert len(con_venta) == 1 and con_venta[0]["promedio"] == venta
    assert len(d["por_dia_semana"]) == 7

    # Los platos que más salen
    assert d["top_platos"][0]["nombre"] == "Lomo saltado"
    assert d["top_platos"][0]["cantidad"] == 3

    # ABC: la carne se lleva el grueso del gasto (A), la sal es la cola
    por_nombre = {i["nombre"]: i for i in d["insumos"]}
    assert por_nombre["Carne"]["clase_abc"] == "A"
    assert por_nombre["Carne"]["pct_valor"] > 99.0
    assert por_nombre["Sal"]["clase_abc"] in ("B", "C")
    assert por_nombre["Sal"]["pct_acumulado"] == 100.0

    assert client.get("/api/finanzas/tablero?dias=3", headers=admin_headers).status_code == 422
