"""Reporte de consumo del kardex: qué se usó, se compró y se perdió."""
from app.services.consumo import rango_por_defecto


def preparar(client, db, admin_headers, menu_ejemplo):
    """Un insumo con receta, una compra y una venta de 2 platos."""
    from app.models import Insumo, RecetaItem

    pollo = Insumo(nombre="Pollo", unidad="kg", costo_unitario=10.0, stock_minimo=2.0)
    db.add(pollo)
    db.commit()
    db.add(RecetaItem(plato_id=menu_ejemplo["Lomo saltado"], insumo_id=pollo.id, cantidad=0.25))
    db.commit()

    # Compra: 10 kg por S/ 120 (el costo promedio pasa a 12)
    client.post(f"/api/insumos/{pollo.id}/movimientos", headers=admin_headers,
                json={"tipo": "compra", "cantidad": 10, "costo_total": 120, "nota": "mercado"})
    # Venta de 2 lomos: descuenta 0.5 kg
    client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 2}],
    })
    return pollo


def test_consumo_suma_compras_ventas_y_mermas(client, db, admin_headers, menu_ejemplo):
    pollo = preparar(client, db, admin_headers, menu_ejemplo)
    client.post(f"/api/insumos/{pollo.id}/movimientos", headers=admin_headers,
                json={"tipo": "merma", "cantidad": 1, "nota": "se malogró"})

    datos = client.get("/api/insumos/consumo", headers=admin_headers).json()
    desde, hasta = rango_por_defecto()
    assert datos["desde"] == desde.isoformat() and datos["hasta"] == hasta.isoformat()
    assert datos["dias"] == 7

    fila = next(f for f in datos["insumos"] if f["nombre"] == "Pollo")
    assert fila["comprado"] == 10 and fila["comprado_soles"] == 120
    assert fila["consumido"] == 0.5 and fila["consumido_soles"] == 6.0   # 0.5 kg × S/ 12
    assert fila["merma"] == 1 and fila["merma_soles"] == 12.0
    assert fila["stock_actual"] == 8.5                                    # 10 − 0.5 − 1
    assert fila["dias_stock"] == 119.0                                    # 8.5 ÷ (0.5/7)
    assert fila["bajo_minimo"] is False

    assert datos["gasto_compras"] == 120 and datos["valor_consumo"] == 6.0
    assert datos["valor_mermas"] == 12.0
    assert sum(d["soles"] for d in datos["por_dia"]) == 6.0
    assert len(datos["por_dia"]) == 7 and datos["por_dia"][-1]["fecha"] == hasta.isoformat()


def test_anular_una_orden_devuelve_el_consumo(client, db, admin_headers, menu_ejemplo):
    """La devolución se registra como ajuste ligado a la orden: no infla el consumo."""
    preparar(client, db, admin_headers, menu_ejemplo)
    orden = client.get("/api/orders/today").json()["ordenes"][0]
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})

    datos = client.get("/api/insumos/consumo", headers=admin_headers).json()
    fila = next(f for f in datos["insumos"] if f["nombre"] == "Pollo")
    assert fila["consumido"] == 0 and fila["consumido_soles"] == 0
    assert fila["ajuste"] == 0          # la devolución no es un conteo físico
    assert fila["dias_stock"] is None   # sin consumo no se proyecta
    assert datos["valor_consumo"] == 0


def test_anular_lo_consumido_antes_del_rango_no_deja_negativos(client, db, admin_headers, menu_ejemplo):
    """El consumo se descuenta hasta cero: "se usó -0.5 kg" no diría nada."""
    from datetime import timedelta

    from app.models import MovimientoInsumo, hoy_lima

    preparar(client, db, admin_headers, menu_ejemplo)
    # El consumo queda fuera del rango; la devolución, dentro
    anterior = db.scalars(
        __import__("sqlalchemy").select(MovimientoInsumo).where(MovimientoInsumo.tipo == "consumo")
    ).first()
    anterior.fecha = hoy_lima() - timedelta(days=20)
    db.commit()
    orden = client.get("/api/orders/today").json()["ordenes"][0]
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})

    datos = client.get("/api/insumos/consumo", headers=admin_headers).json()
    fila = next(f for f in datos["insumos"] if f["nombre"] == "Pollo")
    assert fila["consumido"] == 0 and fila["consumido_soles"] == 0
    assert datos["valor_consumo"] == 0
    assert all(d["soles"] >= 0 for d in datos["por_dia"])


def test_conteo_fisico_va_en_su_columna(client, db, admin_headers, menu_ejemplo):
    pollo = preparar(client, db, admin_headers, menu_ejemplo)
    client.post(f"/api/insumos/{pollo.id}/movimientos", headers=admin_headers,
                json={"tipo": "ajuste", "cantidad": 9, "nota": "conteo del lunes"})

    fila = next(
        f for f in client.get("/api/insumos/consumo", headers=admin_headers).json()["insumos"]
        if f["nombre"] == "Pollo"
    )
    assert fila["ajuste"] == -0.5       # había 9.5, se contaron 9
    assert fila["consumido"] == 0.5     # el conteo no toca el consumo
    assert fila["stock_actual"] == 9


def test_avisa_lo_que_se_esta_acabando(client, db, admin_headers, menu_ejemplo):
    pollo = preparar(client, db, admin_headers, menu_ejemplo)
    client.post(f"/api/insumos/{pollo.id}/movimientos", headers=admin_headers,
                json={"tipo": "ajuste", "cantidad": 1, "nota": "casi vacío"})

    datos = client.get("/api/insumos/consumo", headers=admin_headers).json()
    assert datos["por_agotarse"] == ["Pollo"]
    assert next(f for f in datos["insumos"] if f["nombre"] == "Pollo")["bajo_minimo"] is True


def test_rango_sin_movimientos_y_validaciones(client, admin_headers):
    datos = client.get(
        "/api/insumos/consumo?desde=2020-01-01&hasta=2020-01-07", headers=admin_headers
    ).json()
    assert datos["insumos"] == [] and datos["gasto_compras"] == 0
    assert datos["valor_consumo"] == 0 and len(datos["por_dia"]) == 7

    assert client.get("/api/insumos/consumo?desde=2024-05-10&hasta=2024-05-01",
                      headers=admin_headers).status_code == 422
    assert client.get("/api/insumos/consumo?desde=2020-01-01&hasta=2024-01-01",
                      headers=admin_headers).status_code == 422
    assert client.get("/api/insumos/consumo").status_code == 401


def test_csv_para_excel(client, db, admin_headers, menu_ejemplo):
    preparar(client, db, admin_headers, menu_ejemplo)
    desde, hasta = rango_por_defecto()

    r = client.get(f"/api/insumos/consumo.csv?desde={desde}&hasta={hasta}", headers=admin_headers)
    assert r.status_code == 200
    assert f'filename="consumo-{desde}-a-{hasta}.csv"' in r.headers["content-disposition"]

    texto = r.content.decode("utf-8")
    assert texto.startswith("﻿")                 # BOM: Excel detecta UTF-8
    lineas = texto.lstrip("﻿").splitlines()
    assert lineas[0].split(";")[:4] == ["insumo", "unidad", "se_uso", "costo_de_lo_usado"]
    assert lineas[1].startswith("Pollo;kg;0.5;6.0;10.0;120.0")
    assert "TOTAL compras (S/);120.0" in texto

    assert client.get("/api/insumos/consumo.csv").status_code == 401
