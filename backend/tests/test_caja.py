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

    # Y abrir de nuevo el mismo día sigue bloqueado (un registro por día)
    assert client.post("/api/caja/abrir", json={"monto_apertura": 50}).status_code == 409


def test_reabrir_sin_caja_o_sin_cierre_es_409(client):
    assert client.post("/api/caja/reabrir").status_code == 409
    assert client.put("/api/caja/apertura", json={"monto_apertura": 50}).status_code == 409
    client.post("/api/caja/abrir", json={"monto_apertura": 100})
    assert client.post("/api/caja/reabrir").status_code == 409  # aún no está cerrada
