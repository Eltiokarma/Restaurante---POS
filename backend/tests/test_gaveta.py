"""Cajón de dinero (puerto DK de la impresora): se abre con "OK y pagó" y
con el botón "Abrir cajón" de la caja, solo en modo puente."""
import base64

from tests.test_impresion import activar_modo_puente

PULSO_PIN2 = b"\x1bp\x00\x19\xfa"
PULSO_PIN5 = b"\x1bp\x01\x19\xfa"


def _pedido(client, menu_ejemplo, pago):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}], "pago": pago,
    })
    assert r.status_code == 201
    return r.json()["orden"]["id"]


def _trabajos(client):
    return client.get("/api/print/cola").json()["trabajos"]


def test_ok_y_pago_abre_el_cajon(client, db, menu_ejemplo):
    activar_modo_puente(db)
    pagado = _pedido(client, menu_ejemplo, "pagado")
    debe = _pedido(client, menu_ejemplo, "pendiente")
    sin_dato = _pedido(client, menu_ejemplo, None)
    datos = {t["orden_id"]: base64.b64decode(t["datos_b64"]) for t in _trabajos(client)}
    assert datos[pagado].startswith(PULSO_PIN2)  # al empezar a salir el papel
    assert PULSO_PIN2 not in datos[debe] and PULSO_PIN2 not in datos[sin_dato]


def test_pin_5_y_sin_cajon(client, db, admin_headers, menu_ejemplo):
    activar_modo_puente(db)
    client.put("/api/config", json={"gaveta": "pin5"}, headers=admin_headers)
    assert client.get("/api/config").json()["gaveta"] == "pin5"
    orden = _pedido(client, menu_ejemplo, "pagado")
    assert base64.b64decode(_trabajos(client)[0]["datos_b64"]).startswith(PULSO_PIN5)
    client.post(f"/api/orders/{orden}/printed")

    client.put("/api/config", json={"gaveta": "no"}, headers=admin_headers)
    _pedido(client, menu_ejemplo, "pagado")
    assert b"\x1bp" not in base64.b64decode(_trabajos(client)[0]["datos_b64"])
    assert client.post("/api/print/gaveta").json() == {"encolada": False}

    # Un valor raro no se guarda
    client.put("/api/config", json={"gaveta": "pin9"}, headers=admin_headers)
    assert client.get("/api/config").json()["gaveta"] == "no"


def test_boton_abrir_cajon(client, db):
    activar_modo_puente(db)
    assert client.post("/api/print/gaveta").json() == {"encolada": True}
    trabajos = _trabajos(client)
    # Viaja como "prueba" para que la app ya instalada lo atienda; sin papel
    assert [(t["tipo"], t["numero"]) for t in trabajos] == [("prueba", "CAJON")]
    datos = base64.b64decode(trabajos[0]["datos_b64"])
    assert datos == b"\x1b@" + PULSO_PIN2 and b"\x1dV" not in datos
    client.post("/api/print/prueba/impresa")
    assert _trabajos(client) == []


def test_cajon_espera_a_la_prueba_de_verdad(client, db, admin_headers):
    activar_modo_puente(db)
    client.post("/api/print/gaveta")
    client.post("/api/print/prueba", headers=admin_headers)
    assert [t["numero"] for t in _trabajos(client)] == ["PRUEBA"]
    client.post("/api/print/prueba/impresa")  # confirma la prueba
    assert [t["numero"] for t in _trabajos(client)] == ["CAJON"]
    client.post("/api/print/prueba/impresa")  # y luego el cajón
    assert _trabajos(client) == []


def test_sin_modo_puente_no_hay_cajon(client):
    assert client.post("/api/print/gaveta").json() == {"encolada": False}
    assert _trabajos(client) == []
