"""Pedido por voz: kill switch, endpoints, logs y sinónimos."""
import json

import pytest


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
        lambda texto, contexto: (
            {
                "personas": [],
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
    from app.services.voice import construir_system, contexto_de_hoy

    client.put("/api/menu/today", json={"platos": [{
        "id": menu_ejemplo["Chicha morada"], "nombre": "Chicha morada",
        "categoria": "bebida", "precio": 3.5, "activo_hoy": True,
        "sinonimos": ["chichita"],
    }]}, headers=admin_headers)

    contexto = contexto_de_hoy(db)
    assert contexto["platos"] == [{
        "id": menu_ejemplo["Chicha morada"], "nombre": "Chicha morada",
        "precio": 3.5, "sinonimos": ["chichita"],
    }]
    system = construir_system(contexto)
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


# ---------- Menús por persona ----------

@pytest.fixture()
def menu_voz(db):
    """Menú S/ 11: sopa (se puede quitar) o ensalada → lomo o pollo."""
    from app.models import MenuAlternativa, MenuPlantilla, MenuTiempo, Plato

    platos = {n: Plato(nombre=n, categoria=c, precio=10.0, activo_hoy=True, en_catalogo=True,
                       sinonimos=json.dumps(s))
              for n, c, s in [
                  ("Caldo de gallina", "entrada", ["caldito"]),
                  ("Ensalada", "entrada", []),
                  ("Lomo saltado", "fondo", ["lomito"]),
                  ("Pollo al horno", "fondo", []),
                  ("Chicha morada", "bebida", []),
              ]}
    db.add_all(platos.values())
    db.flush()
    plantilla = MenuPlantilla(nombre="Menú del día", precio=11.0, activo_hoy=True, en_catalogo=True)
    t1 = MenuTiempo(orden=1, rotulo="Entrada", obligatorio=False, descuento_si_se_quita=1.0)
    t1.alternativas = [MenuAlternativa(plato_id=platos["Caldo de gallina"].id),
                       MenuAlternativa(plato_id=platos["Ensalada"].id)]
    t2 = MenuTiempo(orden=2, rotulo="Segundo", obligatorio=True)
    t2.alternativas = [MenuAlternativa(plato_id=platos["Lomo saltado"].id),
                       MenuAlternativa(plato_id=platos["Pollo al horno"].id)]
    plantilla.tiempos = [t1, t2]
    db.add(plantilla)
    db.commit()
    return {"menu_id": plantilla.id, **{n: p.id for n, p in platos.items()}}


def test_prompt_lista_menus_con_tiempos_y_sinonimos(db, menu_voz):
    from app.services.voice import construir_system, contexto_de_hoy

    system = construir_system(contexto_de_hoy(db))
    assert f"MENÚ id: {menu_voz['menu_id']}" in system
    assert "Tiempo 1: Entrada — se puede quitar" in system
    assert "Tiempo 2: Segundo\n" in system  # obligatorio: no se ofrece quitarlo
    assert f"plato_id: {menu_voz['Lomo saltado']} | Lomo saltado" in system
    assert '"lomito"' in system and '"caldito"' in system


def test_depurar_valida_cada_persona_contra_su_menu(db, menu_voz):
    from app.services.voice import _depurar, contexto_de_hoy

    m = menu_voz
    contexto = contexto_de_hoy(db)
    crudo = {
        "personas": [
            # Bien: caldo + lomo para Juan, para llevar, todo junto
            {"menu_id": m["menu_id"], "cantidad": 1,
             "elecciones": [{"tiempo_orden": 1, "plato_id": m["Caldo de gallina"]},
                            {"tiempo_orden": 2, "plato_id": m["Lomo saltado"]}],
             "sin": [], "empaque": "taper", "entrega": "junto", "nombre": " Juan ", "nota": ""},
            # Sin sopa (se puede) y "sin segundo" (obligatorio: se ignora);
            # el lomo puesto en el tiempo 1 no es alternativa de ahí: fuera
            {"menu_id": m["menu_id"], "cantidad": 2,
             "elecciones": [{"tiempo_orden": 1, "plato_id": m["Lomo saltado"]},
                            {"tiempo_orden": 2, "plato_id": m["Pollo al horno"]}],
             "sin": [1, 2], "empaque": "maleta", "entrega": "auto", "nombre": "", "nota": "sin cebolla"},
            # Menú que no existe
            {"menu_id": 999, "cantidad": 1, "elecciones": [], "sin": [],
             "empaque": "mesa", "entrega": "auto", "nombre": "", "nota": ""},
        ],
        "items": [{"plato_id": m["Chicha morada"], "cantidad": 1},
                  {"plato_id": 999, "cantidad": 1}],
        "no_encontrados": ["ceviche"],
        "notas": "",
    }
    r = _depurar(crudo, contexto)
    assert r["personas"] == [
        {"menu_id": m["menu_id"], "cantidad": 1,
         "elecciones": {1: m["Caldo de gallina"], 2: m["Lomo saltado"]}, "sin": [],
         "empaque": "taper", "entrega": "junto", "nombre": "Juan", "nota": ""},
        {"menu_id": m["menu_id"], "cantidad": 2,
         "elecciones": {2: m["Pollo al horno"]}, "sin": [1],
         "empaque": "mesa", "entrega": None, "nombre": "", "nota": "sin cebolla"},
    ]
    assert r["items"] == [{"plato_id": m["Chicha morada"], "cantidad": 1}]
    assert r["no_encontrados"] == ["ceviche", "menú 999", "999"]


def test_endpoint_devuelve_personas_con_nombres(client, admin_headers, menu_voz, monkeypatch):
    from app.services import voice

    m = menu_voz
    activar_voz(client, admin_headers)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(voice, "transcribir", lambda b, n="a": "un caldito con lomito y otro sin sopa con pollo")
    monkeypatch.setattr(voice, "interpretar", lambda texto, contexto: (voice._depurar({
        "personas": [
            {"menu_id": m["menu_id"], "cantidad": 1,
             "elecciones": [{"tiempo_orden": 1, "plato_id": m["Caldo de gallina"]},
                            {"tiempo_orden": 2, "plato_id": m["Lomo saltado"]}],
             "sin": [], "empaque": "mesa", "entrega": "auto", "nombre": "", "nota": ""},
            {"menu_id": m["menu_id"], "cantidad": 1,
             "elecciones": [{"tiempo_orden": 2, "plato_id": m["Pollo al horno"]}],
             "sin": [1], "empaque": "mesa", "entrega": "auto", "nombre": "", "nota": ""},
        ],
        "items": [], "no_encontrados": [], "notas": "",
    }, contexto), 0.001))

    r = client.post("/api/voice/order", files={"audio": ("a.webm", b"x", "audio/webm")},
                    data={"duracion_seg": "4"})
    assert r.status_code == 200
    personas = r.json()["personas"]
    assert [p["menu_nombre"] for p in personas] == ["Menú del día", "Menú del día"]
    assert [[e["nombre"] for e in p["elecciones"]] for p in personas] == [
        ["Caldo de gallina", "Lomo saltado"], ["Pollo al horno"],
    ]
    assert personas[1]["sin_rotulos"] == ["Entrada"]
    assert personas[0]["elecciones"][0] == {
        "tiempo_orden": 1, "rotulo": "Entrada", "plato_id": m["Caldo de gallina"], "nombre": "Caldo de gallina",
    }


def test_interpretar_usa_respaldo_y_esfuerzo_bajo(db, menu_voz, monkeypatch):
    """La llamada real: modelo actual, respaldo por si el modelo declina,
    esfuerzo bajo, herramienta estricta y el menú en el system cacheado."""
    import anthropic

    from app.services import voice

    llamadas = {}

    class Bloque:
        type = "tool_use"
        name = "registrar_pedido"
        input = {"personas": [], "items": [], "no_encontrados": [], "notas": "nada"}

    class Uso:
        input_tokens, output_tokens = 100, 20
        cache_read_input_tokens, cache_creation_input_tokens = 0, 0

    class Respuesta:
        stop_reason = "tool_use"
        content = [Bloque()]
        usage = Uso()

    class Mensajes:
        def create(self, **kw):
            llamadas.update(kw)
            return Respuesta()

    class Cliente:
        def __init__(self, **kw):
            self.beta = type("B", (), {"messages": Mensajes()})()

    monkeypatch.setattr(anthropic, "Anthropic", Cliente)
    resultado, costo = voice.interpretar("hola", voice.contexto_de_hoy(db))
    assert resultado["notas"] == "nada" and costo > 0
    assert llamadas["model"] == "claude-opus-5-5"
    assert llamadas["fallbacks"] == "default"
    assert llamadas["betas"] == ["server-side-fallback-2026-07-01"]
    assert llamadas["output_config"] == {"effort": "low"}
    assert "tool_choice" not in llamadas  # este modelo no acepta forzar la herramienta
    assert llamadas["tools"][0]["strict"] is True
    assert "MENÚ id:" in llamadas["system"][0]["text"]
