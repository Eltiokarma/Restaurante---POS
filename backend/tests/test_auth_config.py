"""Login de admin, validez de tokens y configuración."""
import time

from app import auth


def test_login_correcto_e_incorrecto(client):
    assert client.post("/api/admin/login", json={"password": "mala"}).status_code == 401
    r = client.post("/api/admin/login", json={"password": "testpass"})
    assert r.status_code == 200 and "." in r.json()["token"]


def test_token_invalido_y_expirado(client):
    protegido = "/api/menu/catalog"
    assert client.get(protegido).status_code == 401
    assert client.get(protegido, headers={"X-Admin-Token": "no-es-un-token"}).status_code == 401

    # Token con firma válida pero emitido hace más de 12 horas
    ts_viejo = str(int(time.time()) - auth.TOKEN_TTL_SECONDS - 60)
    vencido = f"{ts_viejo}.{auth._firmar(ts_viejo)}"
    assert client.get(protegido, headers={"X-Admin-Token": vencido}).status_code == 401


def test_config_defaults(client):
    data = client.get("/api/config").json()
    assert data["ventana_cancelacion_seg"] == 30
    assert data["timeout_inactividad_seg"] == 90
    assert data["modo_impresion"] == "terminal"


def test_config_actualiza_y_persiste(client, admin_headers):
    r = client.put(
        "/api/config",
        json={"nombre_local": "El Buen Sabor", "ruc": "20123456789", "ventana_cancelacion_seg": 20},
        headers=admin_headers,
    )
    assert r.status_code == 200

    data = client.get("/api/config").json()
    assert data["nombre_local"] == "El Buen Sabor"
    assert data["ventana_cancelacion_seg"] == 20
    # Lo no enviado conserva su valor
    assert data["timeout_inactividad_seg"] == 90


def test_put_config_requiere_admin(client):
    assert client.put("/api/config", json={"nombre_local": "X"}).status_code == 401


def test_modo_impresion_invalido_se_normaliza(client, admin_headers):
    client.put("/api/config", json={"modo_impresion": "nube"}, headers=admin_headers)
    assert client.get("/api/config").json()["modo_impresion"] == "terminal"
