"""Equipo con perfiles (pedido del dueño): cada persona entra con su PIN y
el rol limita lo delicado. Con el interruptor apagado nada cambia."""
import base64
from datetime import timedelta

from tests.test_impresion import activar_modo_puente


def _persona(client, admin_headers, nombre, rol, pin):
    r = client.post("/api/equipo", json={"nombre": nombre, "rol": rol, "pin": pin}, headers=admin_headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _entrar(client, uid, pin):
    r = client.post("/api/equipo/entrar", json={"usuario_id": uid, "pin": pin})
    assert r.status_code == 200, r.text
    return {"X-Usuario-Token": r.json()["token"]}


def _equipo(client, admin_headers):
    """Admin (Dueño), cajera (Rosa) y mozo (Luis), con el equipo encendido."""
    ids = {
        "dueno": _persona(client, admin_headers, "Dueño", "admin", "9999"),
        "rosa": _persona(client, admin_headers, "Rosa", "cajero", "1111"),
        "luis": _persona(client, admin_headers, "Luis", "mozo", "2222"),
    }
    client.put("/api/config", json={"equipo_activo": True}, headers=admin_headers)
    return ids, {
        "dueno": _entrar(client, ids["dueno"], "9999"),
        "rosa": _entrar(client, ids["rosa"], "1111"),
        "luis": _entrar(client, ids["luis"], "2222"),
    }


def _pedido(client, menu_ejemplo, headers=None, **extra):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}], **extra,
    }, headers=headers or {})
    return r


def test_crear_y_editar_personas_solo_admin(client, admin_headers):
    assert client.post("/api/equipo", json={"nombre": "X", "rol": "mozo", "pin": "1234"}).status_code == 401
    assert client.post("/api/equipo", json={"nombre": "X", "rol": "chef", "pin": "1234"},
                       headers=admin_headers).status_code == 422
    assert client.post("/api/equipo", json={"nombre": "X", "rol": "mozo", "pin": "12"},
                       headers=admin_headers).status_code == 422
    uid = _persona(client, admin_headers, "Rosa", "cajero", "1111")
    # Dos "Rosa" activas confundirían el "¿Quién eres?"
    assert client.post("/api/equipo", json={"nombre": "rosa", "rol": "mozo", "pin": "1234"},
                       headers=admin_headers).status_code == 409
    client.put(f"/api/equipo/{uid}", json={"rol": "mozo", "pin": "4321"}, headers=admin_headers)
    assert client.post("/api/equipo/entrar", json={"usuario_id": uid, "pin": "1111"}).status_code == 403
    assert client.post("/api/equipo/entrar", json={"usuario_id": uid, "pin": "4321"}).json()["usuario"]["rol"] == "mozo"
    # Desactivada: no sale en "¿Quién eres?" ni puede entrar
    client.put(f"/api/equipo/{uid}", json={"activo": False}, headers=admin_headers)
    assert client.get("/api/equipo/quienes").json()["personas"] == []
    assert client.post("/api/equipo/entrar", json={"usuario_id": uid, "pin": "4321"}).status_code == 404


def test_cinco_pin_malos_bloquean(client, admin_headers):
    uid = _persona(client, admin_headers, "Luis", "mozo", "2222")
    for _ in range(5):
        assert client.post("/api/equipo/entrar", json={"usuario_id": uid, "pin": "0000"}).status_code == 403
    # Ni con el PIN bueno: hay que esperar
    assert client.post("/api/equipo/entrar", json={"usuario_id": uid, "pin": "2222"}).status_code == 429


def test_sesion_yo_y_token_falso(client, admin_headers):
    uid = _persona(client, admin_headers, "Luis", "mozo", "2222")
    headers = _entrar(client, uid, "2222")
    assert client.get("/api/equipo/yo", headers=headers).json()["nombre"] == "Luis"
    assert client.get("/api/equipo/yo", headers={"X-Usuario-Token": f"u{uid}.1.abc"}).status_code == 401
    # Desactivar corta la sesión al toque
    client.put(f"/api/equipo/{uid}", json={"activo": False}, headers=admin_headers)
    assert client.get("/api/equipo/yo", headers=headers).status_code == 401


def test_apagado_todo_como_antes(client, admin_headers, menu_ejemplo):
    _persona(client, admin_headers, "Luis", "mozo", "2222")
    assert _pedido(client, menu_ejemplo).status_code == 201
    assert client.post("/api/caja/abrir", json={"monto_apertura": 50}).status_code == 201


def test_encendido_pide_sesion_y_firma_el_pedido(client, admin_headers, menu_ejemplo):
    _, s = _equipo(client, admin_headers)
    assert _pedido(client, menu_ejemplo).status_code == 401
    r = _pedido(client, menu_ejemplo, s["luis"])
    assert r.status_code == 201
    assert r.json()["orden"]["tomado_por"] == "Luis"
    # Cocina avanza estados sin sesión (no inicia sesión)
    orden = r.json()["orden"]["id"]
    assert client.patch(f"/api/orders/{orden}/status", json={"estado": "preparando"}).status_code == 200


def test_mozo_no_entra_a_la_caja(client, admin_headers):
    _, s = _equipo(client, admin_headers)
    assert client.post("/api/caja/abrir", json={"monto_apertura": 50}, headers=s["luis"]).status_code == 403
    assert client.post("/api/caja/abrir", json={"monto_apertura": 50}, headers=s["rosa"]).status_code == 201
    # La sesión del panel de admin (contraseña) vale como admin
    assert client.post("/api/caja/cerrar", json={"monto_contado": 50}, headers=admin_headers).status_code == 200


def test_pago_del_mozo_lo_levanta_la_caja(client, db, admin_headers, menu_ejemplo):
    activar_modo_puente(db)
    _, s = _equipo(client, admin_headers)
    orden = _pedido(client, menu_ejemplo, s["luis"], pago="pagado", metodo_pago="efectivo").json()["orden"]
    assert orden["pago_pendiente"] is True and orden["metodo_mozo"] == "efectivo"
    assert orden["metodo_pago"] is None
    # La plata la tiene el mozo: el cajón no se abre con su comanda
    trabajo = client.get("/api/print/cola").json()["trabajos"][0]
    assert not base64.b64decode(trabajo["datos_b64"]).startswith(b"\x1bp")
    # El mozo no puede levantarlo; la cajera sí
    pago = {"metodo_pago": "yape"}
    assert client.patch(f"/api/orders/{orden['id']}/pago", json=pago, headers=s["luis"]).status_code == 403
    assert client.patch(f"/api/orders/{orden['id']}/pago", json=pago, headers=s["rosa"]).status_code == 200
    hoy = client.get("/api/orders/today").json()["ordenes"][0]
    assert hoy["pago_pendiente"] is False and hoy["metodo_mozo"] is None and hoy["metodo_pago"] == "yape"
    acciones = client.get("/api/equipo/acciones", headers=admin_headers).json()["acciones"]
    assert acciones[0]["accion"] == "levantar_pago" and acciones[0]["usuario"] == "Rosa"
    assert "dijo efectivo, entró yape" in acciones[0]["detalle"]


def test_cajero_anula_libre_solo_el_primer_minuto(client, db, admin_headers, menu_ejemplo):
    from app.models import Orden

    ids, s = _equipo(client, admin_headers)
    reciente = _pedido(client, menu_ejemplo, s["rosa"]).json()["orden"]["id"]
    assert client.patch(f"/api/orders/{reciente}/status", json={"estado": "anulada"},
                        headers=s["rosa"]).status_code == 200

    viejo = _pedido(client, menu_ejemplo, s["rosa"]).json()["orden"]["id"]
    orden = db.get(Orden, viejo)
    orden.created_at = orden.created_at - timedelta(seconds=90)
    db.commit()
    ruta = f"/api/orders/{viejo}/anular"
    assert client.post(ruta, json={"motivo": "duplicado"}, headers=s["rosa"]).status_code == 428
    malo = {**s["rosa"], "X-Autoriza": f"{ids['dueno']}:0000"}
    assert client.post(ruta, json={"motivo": "duplicado"}, headers=malo).status_code == 428
    # Una cajera no autoriza (solo un admin)
    otra = {**s["rosa"], "X-Autoriza": f"{ids['rosa']}:1111"}
    assert client.post(ruta, json={"motivo": "duplicado"}, headers=otra).status_code == 428
    bueno = {**s["rosa"], "X-Autoriza": f"{ids['dueno']}:9999"}
    assert client.post(ruta, json={"motivo": "duplicado"}, headers=bueno).status_code == 200
    acciones = client.get("/api/equipo/acciones", headers=admin_headers).json()["acciones"]
    assert [(a["accion"], a["usuario"], a["autorizo"]) for a in acciones] == [
        ("anular", "Rosa", "Dueño"), ("anular", "Rosa", ""),
    ]


def test_mozo_quita_platos_solo_con_autorizacion(client, admin_headers, menu_ejemplo):
    ids, s = _equipo(client, admin_headers)
    orden = client.post("/api/orders", json={"items": [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1},
        {"plato_id": menu_ejemplo["Chicha morada"], "cantidad": 1},
    ]}, headers=s["luis"]).json()["orden"]
    chicha = next(i for i in orden["items"] if i["nombre"] == "Chicha morada")
    ruta = f"/api/orders/{orden['id']}/items/{chicha['id']}"
    assert client.delete(ruta, headers=s["luis"]).status_code == 428
    assert client.delete(ruta, headers={**s["luis"], "X-Autoriza": f"{ids['dueno']}:9999"}).status_code == 200
    # Agregar, en cambio, lo hace directo
    agregar = {"items": [{"plato_id": menu_ejemplo["Chicha morada"], "cantidad": 1}]}
    assert client.post(f"/api/orders/{orden['id']}/agregar", json=agregar, headers=s["luis"]).status_code == 200


def test_lo_delicado_de_la_caja_pide_autorizacion(client, admin_headers):
    ids, s = _equipo(client, admin_headers)
    client.post("/api/caja/abrir", json={"monto_apertura": 50}, headers=s["rosa"])
    egreso = client.post("/api/caja/egresos", json={"monto": 5, "concepto": "Hielo"}, headers=s["rosa"])
    assert egreso.status_code == 201, egreso.text
    ruta = f"/api/caja/egresos/{egreso.json()['egresos'][0]['id']}"
    assert client.delete(ruta, headers=s["rosa"]).status_code == 428
    assert client.delete(ruta, headers=s["dueno"]).status_code == 200
    assert client.post("/api/orders/pending-print/clear", headers=s["rosa"]).status_code == 428
