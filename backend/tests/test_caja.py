"""Apertura/cierre de caja y tipo de servicio de las órdenes."""


def crear_orden(client, menu_ejemplo, cantidad=1, empaque=None):
    item = {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": cantidad}
    if empaque is not None:
        item["empaque"] = empaque
    return client.post("/api/orders", json={"items": [item]})


# ---------- Empaque por plato y tipo de servicio derivado ----------

def test_empaque_default_mesa_y_servicio_sala(client, menu_ejemplo):
    orden = crear_orden(client, menu_ejemplo).json()["orden"]
    assert orden["items"][0]["empaque"] == "mesa"
    assert orden["tipo_servicio"] == "sala"


def test_empaque_taper_deriva_llevar(client, menu_ejemplo):
    orden = crear_orden(client, menu_ejemplo, empaque="taper").json()["orden"]
    assert orden["items"][0]["empaque"] == "taper"
    assert orden["tipo_servicio"] == "llevar"


def test_mezcla_de_empaques_deriva_mixto(client, menu_ejemplo):
    r = client.post("/api/orders", json={"items": [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1, "empaque": "mesa"},
        {"plato_id": menu_ejemplo["Chicha morada"], "cantidad": 1, "empaque": "bolsa"},
    ]})
    orden = r.json()["orden"]
    assert orden["tipo_servicio"] == "mixto"
    empaques = {i["nombre"]: i["empaque"] for i in orden["items"]}
    assert empaques == {"Lomo saltado": "mesa", "Chicha morada": "bolsa"}


def test_empaque_invalido_es_422(client, menu_ejemplo):
    assert crear_orden(client, menu_ejemplo, empaque="caja-china").status_code == 422


def test_empaque_en_csv(client, admin_headers, menu_ejemplo):
    crear_orden(client, menu_ejemplo, empaque="lonchera")
    r = client.get("/api/stats/export", headers=admin_headers)
    assert "empaque" in r.text.splitlines()[0]
    assert ";lonchera;" in r.text


# ---------- Apertura y cierre de caja ----------

def test_estado_inicial_sin_abrir(client):
    data = client.get("/api/caja/hoy").json()
    assert data["abierta"] is False and data["cerrada"] is False
    assert data["total_vendido"] == 0 and data["ventas_efectivo"] == 0


def test_flujo_apertura_y_cierre(client, menu_ejemplo):
    r = client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    assert r.status_code == 201
    assert r.json()["abierta"] is True

    # Ventas del día: una orden de 15 y una anulada que no cuenta
    crear_orden(client, menu_ejemplo)
    anulada = crear_orden(client, menu_ejemplo, cantidad=2).json()["orden"]["id"]
    client.patch(f"/api/orders/{anulada}/status", json={"estado": "anulada"})

    # Cierre: contado 66 vs esperado 65 (50 fondo + 15 ventas) → sobra 1
    r = client.post("/api/caja/cerrar", json={"monto_contado": 66.0})
    data = r.json()
    assert data["cerrada"] is True
    assert data["total_sistema"] == 15.0
    assert data["diferencia"] == 1.0

    estado = client.get("/api/caja/hoy").json()
    assert estado["cerrada"] is True and estado["diferencia"] == 1.0


def test_doble_apertura_es_409(client):
    client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    assert client.post("/api/caja/abrir", json={"monto_apertura": 80.0}).status_code == 409


def test_cerrar_sin_abrir_es_409(client):
    assert client.post("/api/caja/cerrar", json={"monto_contado": 100.0}).status_code == 409


def test_recerrar_corrige_el_conteo(client, menu_ejemplo):
    client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    crear_orden(client, menu_ejemplo)
    client.post("/api/caja/cerrar", json={"monto_contado": 60.0})   # faltante -5
    r = client.post("/api/caja/cerrar", json={"monto_contado": 65.0})  # corrección
    assert r.json()["diferencia"] == 0.0


def test_historial_requiere_admin(client, admin_headers):
    assert client.get("/api/caja/historial").status_code == 401
    client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    client.post("/api/caja/cerrar", json={"monto_contado": 50.0})
    data = client.get("/api/caja/historial", headers=admin_headers).json()
    assert len(data["cierres"]) == 1


def test_reabrir_y_corregir_fondo(client, menu_ejemplo):
    """El caso real: abrió de prueba, cerró por error, y el día sigue."""
    client.post("/api/caja/abrir", json={"monto_apertura": 600})
    client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
    })
    # Cierra por error con 0 contado: descuadre feo
    r = client.post("/api/caja/cerrar", json={"monto_contado": 0})
    assert r.json()["descuadre"] == {"tipo": "falta", "monto": 615.0}

    # Reabrir deshace el cierre; las ventas siguen intactas
    r = client.post("/api/caja/reabrir")
    datos = r.json()
    assert datos["abierta"] is True and datos["cerrada"] is False
    assert datos["hora_cierre"] is None and datos["descuadre"] is None
    assert datos["total_vendido"] == 15.0

    # Corregir el fondo de prueba (600 → 100) y cerrar de verdad
    r = client.put("/api/caja/apertura", json={"monto_apertura": 100})
    assert r.json()["monto_apertura"] == 100.0
    r = client.post("/api/caja/cerrar", json={"monto_contado": 115})
    assert r.json()["descuadre"] == {"tipo": "exacta", "monto": 0.0}

    # Corregir el fondo con la caja YA cerrada recalcula el descuadre
    r = client.put("/api/caja/apertura", json={"monto_apertura": 110})
    assert r.json()["descuadre"] == {"tipo": "falta", "monto": 10.0}


def test_varias_cajas_el_mismo_dia(client, admin_headers, menu_ejemplo):
    """Cerrada una caja se puede abrir la siguiente (turnos), y cada una
    cuadra solo con las ventas de su tramo del día."""
    # Turno 1: fondo 50, una venta de 15, cierre exacto
    client.post("/api/caja/abrir", json={"monto_apertura": 50})
    crear_orden(client, menu_ejemplo)
    r = client.post("/api/caja/cerrar", json={"monto_contado": 65})
    assert r.json()["descuadre"] == {"tipo": "exacta", "monto": 0.0}

    # Abrir de nuevo el mismo día: caja 2 arranca limpia, sin arrastrar
    # las ventas ya cuadradas del turno 1
    r = client.post("/api/caja/abrir", json={"monto_apertura": 80})
    assert r.status_code == 201
    datos = r.json()
    assert datos["abierta"] is True and datos["turno"] == 2
    assert datos["total_vendido"] == 0.0

    # Con la caja 2 abierta, abrir otra más sí está bloqueado
    assert client.post("/api/caja/abrir", json={"monto_apertura": 10}).status_code == 409

    # Venta del turno 2 y cierre: cuadra solo con SU venta (80 + 30)
    crear_orden(client, menu_ejemplo, cantidad=2)
    r = client.post("/api/caja/cerrar", json={"monto_contado": 110})
    datos = r.json()
    assert datos["descuadre"] == {"tipo": "exacta", "monto": 0.0}
    assert datos["total_sistema"] == 30.0 and datos["turno"] == 2

    # El historial del admin muestra las dos cajas del día, numeradas
    cierres = client.get("/api/caja/historial", headers=admin_headers).json()["cierres"]
    assert [(c["turno"], c["total_sistema"]) for c in cierres] == [(2, 30.0), (1, 15.0)]


def test_egresos_bajan_el_esperado(client, menu_ejemplo):
    """Salió plata del cajón (gas, verduras): el cierre lo descuenta."""
    # Sin caja abierta no hay de dónde sacar plata
    r = client.post("/api/caja/egresos", json={"concepto": "gas", "monto": 20})
    assert r.status_code == 409

    client.post("/api/caja/abrir", json={"monto_apertura": 100})
    crear_orden(client, menu_ejemplo)  # venta de 15
    client.post("/api/caja/egresos", json={"concepto": "balón de gas", "monto": 20})
    r = client.post("/api/caja/egresos", json={"concepto": "verduras", "monto": 5.5})
    assert r.status_code == 201 and r.json()["total"] == 25.5
    assert client.get("/api/caja/hoy").json()["egresos"] == 25.5

    # Borrar un egreso equivocado (con la caja abierta sí se puede)
    egreso_gas = r.json()["egresos"][0]["id"]
    r = client.delete(f"/api/caja/egresos/{egreso_gas}")
    assert r.json()["total"] == 5.5

    # Cierre: esperado = 100 de fondo + 15 de ventas − 5.50 de egresos
    r = client.post("/api/caja/cerrar", json={"monto_contado": 109.5})
    datos = r.json()
    assert datos["descuadre"] == {"tipo": "exacta", "monto": 0.0}
    assert datos["egresos"] == 5.5

    # Cerrada la caja, el egreso ya entró al cuadre: no se borra
    quedado = client.get("/api/caja/egresos").json()["egresos"][0]["id"]
    assert client.delete(f"/api/caja/egresos/{quedado}").status_code == 409

    # La caja siguiente arranca sin egresos arrastrados
    client.post("/api/caja/abrir", json={"monto_apertura": 50})
    assert client.get("/api/caja/egresos").json() == {"egresos": [], "total": 0.0}


def test_cierre_imprime_resumen_en_modo_puente(client, db, menu_ejemplo):
    import base64

    from app.models import Config

    db.add(Config(clave="modo_impresion", valor="puente"))
    db.add(Config(clave="impresora_ip", valor="192.168.1.77"))
    db.commit()

    client.post("/api/caja/abrir", json={"monto_apertura": 50})
    orden = crear_orden(client, menu_ejemplo).json()["orden"]
    client.post(f"/api/orders/{orden['id']}/printed")
    client.post("/api/caja/egresos", json={"concepto": "gas", "monto": 20})
    # Esperado 50 + 15 − 20 = 45; contado 40 → faltan 5
    client.post("/api/caja/cerrar", json={"monto_contado": 40})

    cola = client.get("/api/print/cola").json()
    trabajo = next(t for t in cola["trabajos"] if t["tipo"] == "cierre")
    datos = base64.b64decode(trabajo["datos_b64"])
    assert b"CIERRE DE CAJA" in datos
    assert b"gas" in datos and b"-20.00" in datos
    assert b"45.00" in datos and b"FALTAN 5.00" in datos

    # Espera en cola hasta que quien imprime confirme
    assert any(t["tipo"] == "cierre" for t in client.get("/api/print/cola").json()["trabajos"])
    client.post("/api/print/cierre/impresa")
    assert all(t["tipo"] != "cierre" for t in client.get("/api/print/cola").json()["trabajos"])


def test_falta_pagar_y_falta_vuelto_en_el_cuadre(client, menu_ejemplo):
    """El caso que descuadraba la caja: un ticket salió sin pagar y otro
    pagó con billete grande y se le debe vuelto."""
    client.post("/api/caja/abrir", json={"monto_apertura": 100})
    crear_orden(client, menu_ejemplo)  # 15, pagada normal (se asume efectivo)
    fiada = crear_orden(client, menu_ejemplo).json()["orden"]
    con_billete = crear_orden(client, menu_ejemplo).json()["orden"]

    r = client.patch(f"/api/orders/{fiada['id']}/pago-pendiente", json={"pendiente": True})
    assert r.json()["pago_pendiente"] is True
    r = client.patch(f"/api/orders/{con_billete['id']}/vuelto", json={"pago_con": 50})
    assert r.json()["vuelto_pendiente"] == 35.0

    estado = client.get("/api/caja/hoy").json()
    assert estado["por_cobrar"] == 15.0
    assert estado["vueltos_pendientes"] == 35.0

    # Efectivo real en el cajón: 100 fondo + 15 pagada + 50 del billete = 165
    # (fórmula: 100 + 45 de ventas efectivo − 15 sin pagar + 35 de vuelto)
    r = client.post("/api/caja/cerrar", json={"monto_contado": 165})
    assert r.json()["descuadre"] == {"tipo": "exacta", "monto": 0.0}

    # Se resuelven: cobra la fiada y entrega el vuelto → esperado 145
    client.post("/api/caja/reabrir")
    client.patch(f"/api/orders/{fiada['id']}/pago", json={"metodo_pago": "efectivo"})
    client.patch(f"/api/orders/{con_billete['id']}/vuelto", json={"pago_con": None})
    estado = client.get("/api/caja/hoy").json()
    assert estado["por_cobrar"] == 0.0 and estado["vueltos_pendientes"] == 0.0
    r = client.post("/api/caja/cerrar", json={"monto_contado": 145})
    assert r.json()["descuadre"] == {"tipo": "exacta", "monto": 0.0}


def test_vuelto_insuficiente_y_cobro_levanta_la_marca(client, menu_ejemplo):
    client.post("/api/caja/abrir", json={"monto_apertura": 0})
    orden = crear_orden(client, menu_ejemplo).json()["orden"]
    # Pagó menos que el total: no es un vuelto, es un error
    r = client.patch(f"/api/orders/{orden['id']}/vuelto", json={"pago_con": 10})
    assert r.status_code == 422

    # Marcada "falta pagar", cobrar la levanta solo
    client.patch(f"/api/orders/{orden['id']}/pago-pendiente", json={"pendiente": True})
    assert client.get("/api/caja/hoy").json()["por_cobrar"] == 15.0
    client.patch(f"/api/orders/{orden['id']}/pago", json={"metodo_pago": "yape"})
    datos = client.get("/api/orders/today").json()["ordenes"][0]
    assert datos["pago_pendiente"] is False
    assert client.get("/api/caja/hoy").json()["por_cobrar"] == 0.0

    # Pagar exacto no deja vuelto pendiente
    r = client.patch(f"/api/orders/{orden['id']}/vuelto", json={"pago_con": 15})
    assert r.json()["vuelto_pendiente"] is None


def test_reabrir_sin_caja_o_sin_cierre_es_409(client):
    assert client.post("/api/caja/reabrir").status_code == 409
    assert client.put("/api/caja/apertura", json={"monto_apertura": 50}).status_code == 409
    client.post("/api/caja/abrir", json={"monto_apertura": 100})
    assert client.post("/api/caja/reabrir").status_code == 409  # aún no está cerrada
