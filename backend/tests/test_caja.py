"""Apertura/cierre de caja y tipo de servicio de las órdenes."""


def crear_orden(client, menu_ejemplo, tipo_servicio=None, cantidad=1):
    payload = {"items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": cantidad}]}
    if tipo_servicio is not None:
        payload["tipo_servicio"] = tipo_servicio
    return client.post("/api/orders", json=payload)


# ---------- Tipo de servicio ----------

def test_tipo_servicio_default_sala(client, menu_ejemplo):
    r = crear_orden(client, menu_ejemplo)
    assert r.json()["orden"]["tipo_servicio"] == "sala"


def test_tipo_servicio_llevar_y_mixto(client, menu_ejemplo):
    assert crear_orden(client, menu_ejemplo, "llevar").json()["orden"]["tipo_servicio"] == "llevar"
    assert crear_orden(client, menu_ejemplo, "mixto").json()["orden"]["tipo_servicio"] == "mixto"


def test_tipo_servicio_invalido_es_422(client, menu_ejemplo):
    assert crear_orden(client, menu_ejemplo, "delivery").status_code == 422


def test_tipo_servicio_en_csv(client, admin_headers, menu_ejemplo):
    crear_orden(client, menu_ejemplo, "llevar")
    r = client.get("/api/stats/export", headers=admin_headers)
    assert "servicio" in r.text.splitlines()[0]
    assert ";llevar;" in r.text


# ---------- Apertura y cierre de caja ----------

def test_estado_inicial_sin_abrir(client):
    data = client.get("/api/caja/hoy").json()
    assert data == {"abierta": False, "cerrada": False, "total_vendido": 0}


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
