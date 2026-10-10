"""Anular desde la terminal (se arrepintió o era duplicado) con mini
voucher, el próximo número de ticket y el PIN del cajón."""
import base64

from tests.test_impresion import activar_modo_puente


def _pedido(client, menu_ejemplo, **extra):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}], **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()["orden"]


def _cola(client):
    return client.get("/api/print/cola").json()["trabajos"]


def test_siguiente_numero(client, menu_ejemplo):
    assert client.get("/api/orders/siguiente-numero").json() == {"numero": 1}
    _pedido(client, menu_ejemplo)
    _pedido(client, menu_ejemplo)
    assert client.get("/api/orders/siguiente-numero").json() == {"numero": 3}


def test_anular_pagado_con_voucher(client, db, menu_ejemplo):
    activar_modo_puente(db)
    orden = _pedido(client, menu_ejemplo, pago="pagado", metodo_pago="yape")
    client.post(f"/api/orders/{orden['id']}/printed")

    r = client.post(f"/api/orders/{orden['id']}/anular", json={"motivo": "arrepentido"})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["orden"]["estado"] == "anulada"
    assert datos["orden"]["motivo_anulacion"] == "arrepentido"
    assert datos["devolver"] == orden["total"]

    voucher = [t for t in _cola(client) if t["tipo"] == "bebida"]
    assert len(voucher) == 1
    texto = base64.b64decode(voucher[0]["datos_b64"]).decode("cp850", errors="ignore")
    assert "ANULADO" in texto and f"Orden #{orden['numero_orden_dia']:03d}" in texto
    assert "SE ARREPINTIO" in texto and "DEVOLVER S/" in texto and "Yape" in texto
    # La comanda de la orden anulada ya no sale
    assert not [t for t in _cola(client) if t["tipo"] == "orden"]

    # No cuenta como venta y no se anula dos veces
    assert client.get("/api/caja/hoy").json()["total_vendido"] == 0
    assert client.post(f"/api/orders/{orden['id']}/anular", json={"motivo": "duplicado"}).status_code == 409


def test_anular_duplicado_sin_pagar_y_motivo_invalido(client, db, menu_ejemplo):
    activar_modo_puente(db)
    orden = _pedido(client, menu_ejemplo, pago="pendiente")
    assert client.post(f"/api/orders/{orden['id']}/anular", json={"motivo": "porque si"}).status_code == 422
    r = client.post(f"/api/orders/{orden['id']}/anular", json={"motivo": "duplicado"})
    assert r.json()["devolver"] == 0
    voucher = next(t for t in _cola(client) if t["tipo"] == "bebida")
    texto = base64.b64decode(voucher["datos_b64"]).decode("cp850", errors="ignore")
    assert "PEDIDO DUPLICADO" in texto and "nada que devolver" in texto


def test_pin_del_cajon(client, db, admin_headers):
    activar_modo_puente(db)
    # Sin PIN configurado abre como siempre
    assert client.post("/api/print/gaveta").json() == {"encolada": True}
    client.post("/api/print/prueba/impresa")

    r = client.put("/api/config", json={"pin_gaveta": "1234"}, headers=admin_headers)
    publica = client.get("/api/config").json()
    assert publica["gaveta_con_pin"] is True and "1234" not in str(publica)
    assert client.post("/api/print/gaveta").status_code == 403
    assert client.post("/api/print/gaveta", json={"pin": "9999"}).status_code == 403
    assert client.post("/api/print/gaveta", json={"pin": "1234"}).json() == {"encolada": True}
    # "Probar cajón" del admin no pide PIN
    assert client.post("/api/print/gaveta", headers=admin_headers).status_code == 200

    # Un PIN raro no se guarda; vacío lo quita
    client.put("/api/config", json={"pin_gaveta": "12a"}, headers=admin_headers)
    assert client.post("/api/print/gaveta", json={"pin": "1234"}).status_code == 200
    client.put("/api/config", json={"pin_gaveta": ""}, headers=admin_headers)
    assert client.get("/api/config").json()["gaveta_con_pin"] is False
