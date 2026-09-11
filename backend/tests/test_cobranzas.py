"""Pagos pendientes de otros días, incobrables y descuadres.

El dueño lo dijo así: "sin cobrar suele ser un pago futuro que necesita
ser levantado desde el sistema; -43 puede ser una mesa que se fue sin
pagar o también un pagaré futuro; exceso de 98 se considera un ingreso
extra con la categoría de descuadre, hay negativo y positivo".
"""
from datetime import timedelta


def _orden(client, menu_ejemplo, cantidad=1):
    return client.post("/api/orders", json={"items": [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": cantidad},
    ]}).json()["orden"]


def _atrasar(db, orden_id, dias):
    """Manda una orden a un día anterior (simula la venta del martes que
    se cobra el jueves)."""
    from app.models import Orden
    o = db.get(Orden, orden_id)
    o.fecha = o.fecha - timedelta(days=dias)
    db.commit()
    return o.fecha


# ---------- Lo que está debiendo ----------

def test_por_cobrar_lista_los_pendientes_de_cualquier_dia(client, db, menu_ejemplo):
    vieja = _orden(client, menu_ejemplo, 2)          # 30
    hoy = _orden(client, menu_ejemplo, 1)            # 15
    client.patch(f"/api/orders/{vieja['id']}/pago-pendiente", json={"pendiente": True})
    client.patch(f"/api/orders/{hoy['id']}/pago-pendiente", json={"pendiente": True})
    _atrasar(db, vieja["id"], 3)

    d = client.get("/api/orders/por-cobrar").json()
    assert d["total_pendiente"] == 45.0
    assert [f["dias"] for f in d["pendientes"]] == [3, 0]


def test_cobrar_una_venta_vieja_entra_al_cajon_de_hoy(client, db, admin_headers, menu_ejemplo):
    """La venta sigue contada en SU día; el billete entra hoy."""
    vieja = _orden(client, menu_ejemplo, 2)          # 30
    client.patch(f"/api/orders/{vieja['id']}/pago-pendiente", json={"pendiente": True})
    fecha_vieja = _atrasar(db, vieja["id"], 2)

    client.post("/api/caja/abrir", json={"monto_apertura": 100.0})
    r = client.post(f"/api/orders/{vieja['id']}/cobrar", json={"metodo_pago": "efectivo"})
    assert r.status_code == 200 and r.json()["cobranza_registrada"] is True

    # Ya no debe nada
    assert client.get("/api/orders/por-cobrar").json()["total_pendiente"] == 0.0

    # El cierre de hoy espera esos 30 de más (fondo 100 + 30 cobrados)
    cierre = client.post("/api/caja/cerrar", json={"monto_contado": 130.0}).json()
    assert cierre["diferencia"] == 0.0

    # Y la venta no se contó dos veces: sigue en su día
    tablero = client.get("/api/finanzas/tablero?desde={}&hasta={}".format(
        fecha_vieja, fecha_vieja), headers=admin_headers).json()
    assert tablero["kpis"]["ventas"] == 30.0
    assert tablero["kpis"]["otros_ingresos"] == 0.0
    assert tablero["kpis"]["cobranzas"] == 0.0   # la cobranza cayó hoy, no ese día


def test_cobrar_por_yape_no_toca_el_cajon(client, db, menu_ejemplo):
    vieja = _orden(client, menu_ejemplo, 2)
    client.patch(f"/api/orders/{vieja['id']}/pago-pendiente", json={"pendiente": True})
    _atrasar(db, vieja["id"], 1)
    client.post("/api/caja/abrir", json={"monto_apertura": 100.0})
    client.post(f"/api/orders/{vieja['id']}/cobrar", json={"metodo_pago": "yape"})
    cierre = client.post("/api/caja/cerrar", json={"monto_contado": 100.0}).json()
    assert cierre["diferencia"] == 0.0


def test_incobrable_deja_el_neto_en_cero(client, db, admin_headers, menu_ejemplo):
    """La mesa se fue sin pagar: la venta quedó contada, así que se anota
    el gasto del mismo monto y el día no muestra ganancia fantasma."""
    orden = _orden(client, menu_ejemplo, 2)          # 30
    client.patch(f"/api/orders/{orden['id']}/pago-pendiente", json={"pendiente": True})

    r = client.post(f"/api/orders/{orden['id']}/incobrable")
    assert r.status_code == 200 and r.json()["monto"] == 30.0
    assert client.get("/api/orders/por-cobrar").json()["total_pendiente"] == 0.0

    resumen = client.get("/api/finanzas/resumen?dias=7", headers=admin_headers).json()
    assert resumen["ventas"] == 30.0
    categorias = {c["categoria"]: c["monto"] for c in resumen["egresos_por_categoria"]}
    assert categorias["incobrable"] == 30.0
    assert resumen["por_dia"][-1]["entro"] == 30.0
    assert resumen["por_dia"][-1]["egresos"] == 30.0

    # Repetirlo no duplica el gasto
    client.post(f"/api/orders/{orden['id']}/incobrable")
    resumen = client.get("/api/finanzas/resumen?dias=7", headers=admin_headers).json()
    categorias = {c["categoria"]: c["monto"] for c in resumen["egresos_por_categoria"]}
    assert categorias["incobrable"] == 30.0


# ---------- Descuadre: sobra o falta al cerrar ----------

def test_el_sobrante_del_cierre_queda_como_ingreso_de_descuadre(
        client, admin_headers, menu_ejemplo):
    client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    _orden(client, menu_ejemplo, 1)                  # 15
    cierre = client.post("/api/caja/cerrar", json={"monto_contado": 98.0}).json()
    assert cierre["descuadre"] == {"tipo": "sobra", "monto": 33.0}

    movimientos = client.get("/api/finanzas/movimientos", headers=admin_headers).json()
    descuadres = [m for m in movimientos["movimientos"] if m["categoria"] == "descuadre"]
    assert len(descuadres) == 1
    assert descuadres[0]["tipo"] == "entra" and descuadres[0]["monto"] == 33.0
    assert descuadres[0]["automatico"] is True
    assert movimientos["total_entra"] == 33.0

    # Re-cerrar corrige el conteo: el descuadre se reemplaza, no se acumula
    client.post("/api/caja/cerrar", json={"monto_contado": 60.0})
    movimientos = client.get("/api/finanzas/movimientos", headers=admin_headers).json()
    descuadres = [m for m in movimientos["movimientos"] if m["categoria"] == "descuadre"]
    assert len(descuadres) == 1
    assert descuadres[0]["tipo"] == "sale" and descuadres[0]["monto"] == 5.0

    # Un cierre exacto no deja movimiento
    client.post("/api/caja/cerrar", json={"monto_contado": 65.0})
    movimientos = client.get("/api/finanzas/movimientos", headers=admin_headers).json()
    assert [m for m in movimientos["movimientos"] if m["categoria"] == "descuadre"] == []


# ---------- Movimientos anotados a mano ----------

def test_anotar_movimiento_de_otro_dia_y_borrarlo(client, admin_headers, menu_ejemplo):
    from app.models import hoy_lima
    ayer = (hoy_lima() - timedelta(days=1)).isoformat()

    r = client.post("/api/finanzas/movimientos", json={
        "fecha": ayer, "tipo": "entra", "concepto": "Exceso en el cajón",
        "monto": 98.0, "categoria": "descuadre"}, headers=admin_headers)
    assert r.status_code == 201
    client.post("/api/finanzas/movimientos", json={
        "fecha": ayer, "tipo": "sale", "concepto": "Mesa que se fue sin pagar",
        "monto": 43.0, "categoria": "incobrable"}, headers=admin_headers)

    d = client.get("/api/finanzas/movimientos", headers=admin_headers).json()
    assert d["total_entra"] == 98.0 and d["total_sale"] == 43.0

    flujo = {f["desde"]: f for f in client.get(
        "/api/finanzas/flujo?agrupar=dia", headers=admin_headers).json()["filas"]}
    assert flujo[ayer]["entro"] == 98.0
    assert flujo[ayer]["egresos"] == 43.0

    resumen = client.get("/api/finanzas/resumen?dias=7", headers=admin_headers).json()
    assert resumen["otros_ingresos"] == 98.0
    assert resumen["ventas"] == 0.0          # un descuadre no es una venta
    ingresos = {c["categoria"]: c["monto"] for c in resumen["ingresos_por_categoria"]}
    assert ingresos["descuadre"] == 98.0

    borrado = client.delete(
        f"/api/finanzas/movimientos/{d['movimientos'][0]['id']}", headers=admin_headers)
    assert borrado.status_code == 200 and len(borrado.json()["movimientos"]) == 1


def test_movimientos_requieren_admin(client):
    assert client.get("/api/finanzas/movimientos").status_code == 401


def test_no_se_anota_un_movimiento_del_futuro(client, admin_headers):
    from app.models import hoy_lima
    manana = (hoy_lima() + timedelta(days=1)).isoformat()
    r = client.post("/api/finanzas/movimientos", json={
        "fecha": manana, "tipo": "entra", "concepto": "x", "monto": 10.0,
        "categoria": "otros"}, headers=admin_headers)
    assert r.status_code == 422
