"""Pedido por voz: kill switch, endpoints, logs y sinónimos."""
import json


def activar_voz(client, admin_headers):
    r = client.put("/api/config", json={"voz_habilitada": True}, headers=admin_headers)
    assert r.status_code == 200


def test_voz_apagada_por_defecto(client):
    data = client.get("/api/config").json()
    assert data["voz_habilitada"] is False
    assert data["voz_disponible"] is False


def test_toggle_pero_sin_claves_no_disponible(client, admin_headers, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    activar_voz(client, admin_headers)
    data = client.get("/api/config").json()
    assert data["voz_habilitada"] is True
    assert data["voz_disponible"] is False  # sin claves, el botón no aparece

    r = client.post("/api/voice/order", files={"audio": ("a.webm", b"xx", "audio/webm")})
    assert r.status_code == 503


def test_voz_apagada_rechaza_pedidos(client):
    r = client.post("/api/voice/order", files={"audio": ("a.webm", b"xx", "audio/webm")})
    assert r.status_code == 503
    assert "apagado" in r.json()["detail"]


def test_pipeline_completo_simulado(client, admin_headers, menu_ejemplo, monkeypatch):
    """Con transcripción e interpretación simuladas, el endpoint resuelve
    items contra el menú real de la BD y registra el log."""
    from app.services import voice

    activar_voz(client, admin_headers)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(voice, "transcribir", lambda b, n="a": "dos lomitos y un ceviche porfa")
    monkeypatch.setattr(
        voice, "interpretar",
        lambda texto, menu: (
            {
                "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 2}],
                "no_encontrados": ["ceviche"],
                "notas": "",
            },
            0.001,
        ),
    )

    r = client.post(
        "/api/voice/order",
        files={"audio": ("a.webm", b"audio-falso", "audio/webm")},
        data={"duracion_seg": "3.5"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["transcripcion"].startswith("dos lomitos")
    assert data["items_resueltos"] == [{
        "plato_id": menu_ejemplo["Lomo saltado"], "nombre": "Lomo saltado",
        "precio": 15.0, "cantidad": 2,
    }]
    assert data["no_encontrados"] == ["ceviche"]

    # El log quedó como pendiente y se puede marcar aceptado
    log_id = data["log_id"]
    r = client.patch(f"/api/voice/logs/{log_id}", json={"resultado": "aceptado"})
    assert r.status_code == 200

    panel = client.get("/api/voice/logs/today", headers=admin_headers).json()
    assert panel["metricas"]["total"] == 1
    assert panel["metricas"]["pct_aceptado"] == 100.0
    assert panel["metricas"]["costo_dia_usd"] > 0
    assert panel["logs"][0]["transcripcion"].startswith("dos lomitos")


def test_resultado_invalido_y_log_inexistente(client, admin_headers):
    assert client.patch("/api/voice/logs/999", json={"resultado": "aceptado"}).status_code == 404


def test_panel_voz_requiere_admin(client):
    assert client.get("/api/voice/logs/today").status_code == 401


def test_error_de_voz_da_mensaje_amable(client, admin_headers, menu_ejemplo, monkeypatch):
    from app.services import voice

    activar_voz(client, admin_headers)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")

    def falla(b, n="a"):
        raise voice.VozError("No te escuché bien, intenta de nuevo o usa los botones")

    monkeypatch.setattr(voice, "transcribir", falla)
    r = client.post("/api/voice/order", files={"audio": ("a.webm", b"x", "audio/webm")})
    assert r.status_code == 502
    assert "usa los botones" in r.json()["detail"]


# ---------- Sinónimos en el menú ----------

def test_sinonimos_se_guardan_y_devuelven(client, admin_headers, menu_ejemplo):
    payload = {"platos": [{
        "id": menu_ejemplo["Lomo saltado"], "nombre": "Lomo saltado",
        "categoria": "fondo", "precio": 15.0, "activo_hoy": True,
        "sinonimos": ["lomito", "saltado", "  "],
    }]}
    r = client.put("/api/menu/today", json=payload, headers=admin_headers)
    plato = next(p for p in r.json()["platos"] if p["nombre"] == "Lomo saltado")
    assert plato["sinonimos"] == ["lomito", "saltado"]  # el vacío se limpia


def test_menu_para_interprete_sale_de_la_bd(client, admin_headers, menu_ejemplo, db):
    from app.services.voice import construir_system, menu_activo_con_sinonimos

    client.put("/api/menu/today", json={"platos": [{
        "id": menu_ejemplo["Chicha morada"], "nombre": "Chicha morada",
        "categoria": "bebida", "precio": 3.5, "activo_hoy": True,
        "sinonimos": ["chichita"],
    }]}, headers=admin_headers)

    menu = menu_activo_con_sinonimos(db)
    assert menu == [{
        "id": menu_ejemplo["Chicha morada"], "nombre": "Chicha morada",
        "precio": 3.5, "sinonimos": ["chichita"],
    }]
    system = construir_system(menu)
    assert "chichita" in system and f'id: {menu_ejemplo["Chicha morada"]}' in system


# ---------- Origen de la orden ----------

def test_origen_de_orden(client, menu_ejemplo):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
        "origen": "voz",
    })
    assert r.json()["orden"]["origen"] == "voz"
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
    })
    assert r.json()["orden"]["origen"] == "tactil"
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
        "origen": "telepatia",
    })
    assert r.status_code == 422
