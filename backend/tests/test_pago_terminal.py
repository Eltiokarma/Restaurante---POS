""""Pagó efectivo / Yape / mixto" en la terminal: el método queda en la
orden, sale en la precuenta, el cajón no se abre con Yape y el mixto lo
desglosa la caja después (cuánto fue por Yape)."""
import base64

from tests.test_caja import crear_orden
from tests.test_impresion import activar_modo_puente

PULSO_PIN2 = b"\x1bp\x00\x19\xfa"


def _pedido(client, menu_ejemplo, metodo):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
        "pago": "pagado", "metodo_pago": metodo,
    })
    assert r.status_code == 201
    return r.json()["orden"]


def test_metodo_de_la_terminal_queda_en_la_orden_y_la_precuenta(client, db, menu_ejemplo):
    activar_modo_puente(db)
    efectivo = _pedido(client, menu_ejemplo, "efectivo")
    yape = _pedido(client, menu_ejemplo, "yape")
    mixto = _pedido(client, menu_ejemplo, "mixto")
    assert (efectivo["metodo_pago"], yape["metodo_pago"], mixto["metodo_pago"]) == ("efectivo", "yape", "mixto")
    assert mixto["pago_yape"] is None  # el monto lo pone la caja

    datos = {t["orden_id"]: base64.b64decode(t["datos_b64"])
             for t in client.get("/api/print/cola").json()["trabajos"]}
    texto = {k: v.decode("cp850", errors="ignore") for k, v in datos.items()}
    assert "EFECTIVO - TOTAL PAGADO S/" in texto[efectivo["id"]]
    assert "YAPE - TOTAL PAGADO S/" in texto[yape["id"]]
    assert "EFECTIVO+YAPE - TOTAL PAGADO S/" in texto[mixto["id"]]
    # Con Yape no entra billete: el cajón no se abre
    assert datos[efectivo["id"]].startswith(PULSO_PIN2)
    assert datos[mixto["id"]].startswith(PULSO_PIN2)
    assert PULSO_PIN2 not in datos[yape["id"]]


def test_metodo_invalido_o_sin_pagar(client, menu_ejemplo):
    item = [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}]
    r = client.post("/api/orders", json={"items": item, "pago": "pagado", "metodo_pago": "tarjeta"})
    assert r.status_code == 422
    # "No pagó" no registra método aunque llegue uno
    debe = client.post("/api/orders", json={"items": item, "pago": "pendiente", "metodo_pago": "yape"}).json()["orden"]
    assert debe["metodo_pago"] is None and debe["pago_pendiente"] is True


def test_precuenta_angosta_pone_el_metodo_en_su_renglon(client, db, menu_ejemplo):
    from app.models import Orden
    from app.services.escpos import render_precuenta

    orden_id = _pedido(client, menu_ejemplo, "mixto")["id"]
    orden = db.get(Orden, orden_id)
    db.refresh(orden)
    texto = render_precuenta(orden, {}, 32).decode("cp850", errors="ignore")
    assert "PAGO: EFECTIVO+YAPE" in texto
    for renglon in texto.replace("\x1bM\x01", "").split("\n"):
        limpio = "".join(c for c in renglon if c.isprintable())
        assert len(limpio) <= (32 * 12) // 9 + 2


def test_mixto_se_desglosa_en_caja(client, menu_ejemplo):
    client.post("/api/caja/abrir", json={"monto_apertura": 100})
    orden = _pedido(client, menu_ejemplo, "mixto")
    total = orden["total"]
    estado = client.get("/api/caja/hoy").json()
    # Sin desglosar: todo como efectivo, con aviso
    assert estado["mixto_sin_desglose"] == 1
    assert estado["ventas_efectivo"] == total and estado["ventas_yape"] == 0

    r = client.patch(f"/api/orders/{orden['id']}/pago", json={"metodo_pago": "mixto", "monto_yape": 10})
    assert r.status_code == 200 and r.json()["pago_yape"] == 10
    estado = client.get("/api/caja/hoy").json()
    assert estado["mixto_sin_desglose"] == 0
    assert estado["ventas_yape"] == 10
    assert estado["ventas_efectivo"] == round(total - 10, 2)
    assert estado["total_vendido"] == total

    # El Yape de un mixto no puede ser todo ni nada
    for monto in (0, total, total + 5):
        r = client.patch(f"/api/orders/{orden['id']}/pago", json={"metodo_pago": "mixto", "monto_yape": monto})
        assert r.status_code == 422
    # Cambiar a otro método borra el desglose
    client.patch(f"/api/orders/{orden['id']}/pago", json={"metodo_pago": "yape"})
    assert client.get("/api/caja/hoy").json()["ventas_yape"] == total


def test_mixto_en_finanzas(client, admin_headers, menu_ejemplo):
    orden = _pedido(client, menu_ejemplo, "mixto")
    client.patch(f"/api/orders/{orden['id']}/pago", json={"metodo_pago": "mixto", "monto_yape": 10})
    crear_orden(client, menu_ejemplo)
    r = client.get("/api/finanzas/resumen", headers=admin_headers)
    assert r.status_code == 200, r.text
    entradas = r.json()["entradas_por_metodo"]
    assert entradas["yape"] == 10
    assert "mixto" not in entradas
