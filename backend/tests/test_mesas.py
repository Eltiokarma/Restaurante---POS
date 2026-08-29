"""Mesas, candado de caja abierta e historial por fecha."""
from datetime import timedelta


def crear_mesa(client, admin_headers, nombre):
    r = client.post("/api/mesas", json={"nombre": nombre}, headers=admin_headers)
    assert r.status_code == 201
    return r.json()["id"]


def crear_orden(client, menu_ejemplo, mesa_ids=None):
    payload = {"items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}]}
    if mesa_ids is not None:
        payload["mesa_ids"] = mesa_ids
    return client.post("/api/orders", json=payload)


# ---------- Candado: sin apertura de caja no se vende ----------

def test_venta_bloqueada_sin_abrir_caja(client, admin_headers, menu_ejemplo):
    client.put("/api/config", json={"exigir_caja_abierta": True}, headers=admin_headers)
    r = crear_orden(client, menu_ejemplo)
    assert r.status_code == 409
    assert "caja" in r.json()["detail"].lower()

    client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    assert crear_orden(client, menu_ejemplo).status_code == 201


def test_candado_desactivable(client, admin_headers, menu_ejemplo):
    client.put("/api/config", json={"exigir_caja_abierta": False}, headers=admin_headers)
    assert crear_orden(client, menu_ejemplo).status_code == 201


def test_caja_cerrada_sigue_permitiendo_vender(client, admin_headers, menu_ejemplo):
    """El candado exige APERTURA; tras el cierre la venta tardía se permite
    (y el aviso de 'ventas después del cierre' ya la delata)."""
    client.put("/api/config", json={"exigir_caja_abierta": True}, headers=admin_headers)
    client.post("/api/caja/abrir", json={"monto_apertura": 50.0})
    client.post("/api/caja/cerrar", json={"monto_contado": 50.0})
    assert crear_orden(client, menu_ejemplo).status_code == 201


# ---------- Mesas ----------

def test_configuracion_de_mesas(client, admin_headers):
    mesa_id = crear_mesa(client, admin_headers, "Mesa 1")
    # Renombrar y desactivar
    r = client.put(f"/api/mesas/{mesa_id}", json={"nombre": "Mesa 1B", "activa": False},
                   headers=admin_headers)
    assert r.json() == {"id": mesa_id, "nombre": "Mesa 1B", "activa": False}
    # CRUD requiere admin; el listado no (lo usa la caja)
    assert client.post("/api/mesas", json={"nombre": "X"}).status_code == 401
    assert client.get("/api/mesas").status_code == 200


def test_asignar_combinar_y_liberar(client, admin_headers, menu_ejemplo):
    m1 = crear_mesa(client, admin_headers, "Mesa 1")
    m2 = crear_mesa(client, admin_headers, "Mesa 2")
    m3 = crear_mesa(client, admin_headers, "Mesa 3")

    # Ticket creado desde caja con mesas COMBINADAS 1+2
    r = crear_orden(client, menu_ejemplo, mesa_ids=[m1, m2])
    assert r.json()["orden"]["mesas"] == ["Mesa 1", "Mesa 2"]

    estado = {m["nombre"]: m for m in client.get("/api/mesas").json()["mesas"]}
    assert estado["Mesa 1"]["ocupada"] and estado["Mesa 2"]["ocupada"]
    assert not estado["Mesa 3"]["ocupada"]

    # Liberar la mesa 1 libera el ticket completo (las combinadas se van juntas)
    client.post(f"/api/mesas/{m1}/liberar")
    estado = {m["nombre"]: m for m in client.get("/api/mesas").json()["mesas"]}
    assert not estado["Mesa 1"]["ocupada"] and not estado["Mesa 2"]["ocupada"]


def test_asignar_mesa_despues_de_crear(client, admin_headers, menu_ejemplo):
    m1 = crear_mesa(client, admin_headers, "Mesa 1")
    orden_id = crear_orden(client, menu_ejemplo).json()["orden"]["id"]

    r = client.patch(f"/api/orders/{orden_id}/mesas", json={"mesa_ids": [m1]})
    assert r.json()["mesas"] == ["Mesa 1"]
    assert client.get("/api/mesas").json()["mesas"][0]["ocupada"] is True

    # Quitar la asignación con lista vacía
    client.patch(f"/api/orders/{orden_id}/mesas", json={"mesa_ids": []})
    assert client.get("/api/mesas").json()["mesas"][0]["ocupada"] is False


def test_mesa_inactiva_o_inexistente_es_422(client, admin_headers, menu_ejemplo):
    m1 = crear_mesa(client, admin_headers, "Mesa 1")
    client.put(f"/api/mesas/{m1}", json={"activa": False}, headers=admin_headers)
    assert crear_orden(client, menu_ejemplo, mesa_ids=[m1]).status_code == 422
    assert crear_orden(client, menu_ejemplo, mesa_ids=[999]).status_code == 422


def test_anular_desocupa_la_mesa(client, admin_headers, menu_ejemplo):
    m1 = crear_mesa(client, admin_headers, "Mesa 1")
    orden_id = crear_orden(client, menu_ejemplo, mesa_ids=[m1]).json()["orden"]["id"]
    client.patch(f"/api/orders/{orden_id}/status", json={"estado": "anulada"})
    assert client.get("/api/mesas").json()["mesas"][0]["ocupada"] is False


# ---------- Historial por fecha ----------

def test_ordenes_de_cualquier_dia(client, db, menu_ejemplo):
    from app.models import Orden, hoy_lima

    ayer = hoy_lima() - timedelta(days=1)
    db.add(Orden(numero_orden_dia=1, fecha=ayer, hora="12:00:00", total=25.0,
                 estado="entregado", impreso=True))
    db.commit()
    crear_orden(client, menu_ejemplo)

    de_ayer = client.get(f"/api/orders/of-day?fecha={ayer.isoformat()}").json()
    assert de_ayer["fecha"] == ayer.isoformat()
    assert len(de_ayer["ordenes"]) == 1 and de_ayer["total_vendido"] == 25.0

    de_hoy = client.get("/api/orders/today").json()
    assert len(de_hoy["ordenes"]) == 1 and de_hoy["total_vendido"] == 15.0
