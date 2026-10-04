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
    monkeypatch.setattr(voice, "transcribir", lambda b, n="a", pista="": "dos lomitos y un ceviche porfa")
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

    def falla(b, n="a", pista=""):
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
    assert "Tiempo 1: Entrada — sin él: -S/ 1.00" in system
    assert "Tiempo 2: Segundo\n" in system  # quitarlo no descuenta: no se anuncia
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
            # Sin entrada y sin segundo a la vez = sin nada: se ignora;
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
         "empaque": "taper", "empaques": {}, "espera": [], "agregados": [],
         "entrega": "junto", "nombre": "Juan", "nota": ""},
        {"menu_id": m["menu_id"], "cantidad": 2,
         "elecciones": {2: m["Pollo al horno"]}, "sin": [],
         "empaque": "mesa", "empaques": {}, "espera": [], "agregados": [],
         "entrega": None, "nombre": "", "nota": "sin cebolla"},
    ]
    assert r["items"] == [{"plato_id": m["Chicha morada"], "cantidad": 1}]
    assert r["no_encontrados"] == ["ceviche", "menú 999", "999"]


def test_endpoint_devuelve_personas_con_nombres(client, admin_headers, menu_voz, monkeypatch):
    from app.services import voice

    m = menu_voz
    activar_voz(client, admin_headers)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setattr(voice, "transcribir", lambda b, n="a", pista="": "un caldito con lomito y otro sin sopa con pollo")
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
        "tiempo_orden": 1, "rotulo": "Entrada", "plato_id": m["Caldo de gallina"],
        "nombre": "Caldo de gallina", "empaque": None, "espera": False,
    }


def test_interpretar_con_openai_json_estricto(db, menu_voz, monkeypatch):
    """La llamada real: gpt-6-luna por la Responses API con el menú en las
    instrucciones (prefijo fijo, cacheable) y salida JSON estricta."""
    import openai

    from app.services import voice

    llamadas = {}

    class Detalle:
        cached_tokens = 1500

    class Uso:
        input_tokens, output_tokens = 2000, 200
        input_tokens_details = Detalle()

    class Respuesta:
        status = "completed"
        output_text = json.dumps({"personas": [], "items": [], "no_encontrados": [], "notas": "nada"})
        usage = Uso()

    class Respuestas:
        def create(self, **kw):
            llamadas.update(kw)
            return Respuesta()

    class Cliente:
        def __init__(self, **kw):
            self.responses = Respuestas()

    monkeypatch.setattr(openai, "OpenAI", Cliente)
    resultado, costo = voice.interpretar("hola", voice.contexto_de_hoy(db))
    assert resultado["notas"] == "nada"
    # 500 sin caché × 0.10 + 1500 en caché × 0.01 + 200 × 0.50 (por millón)
    assert costo == pytest.approx((500 * 0.10 + 1500 * 0.01 + 200 * 0.50) / 1_000_000)
    assert llamadas["model"] == "gpt-6-luna"
    assert llamadas["reasoning"] == {"effort": "low"}
    formato = llamadas["text"]["format"]
    assert formato["type"] == "json_schema" and formato["strict"] is True
    assert "MENÚ id:" in llamadas["instructions"] and llamadas["input"] == "hola"
    assert llamadas["store"] is False


def test_respuesta_sin_json_da_mensaje_amable(db, menu_voz, monkeypatch):
    import openai

    from app.services import voice

    class Respuesta:
        status = "incomplete"
        output_text = ""
        usage = None

    class Cliente:
        def __init__(self, **kw):
            self.responses = type("R", (), {"create": lambda self, **kw: Respuesta()})()

    monkeypatch.setattr(openai, "OpenAI", Cliente)
    with pytest.raises(voice.VozError) as e:
        voice.interpretar("hola", voice.contexto_de_hoy(db))
    assert "usa los botones" in e.value.mensaje_cliente


def test_esquema_cumple_el_modo_estricto():
    """Modo estricto: todo objeto cierra sus propiedades y las exige
    todas; sin mínimos/máximos (no los admite)."""
    from app.services.voice import FORMATO_PEDIDO

    def revisar(nodo):
        if isinstance(nodo, dict):
            assert not {"minimum", "maximum", "minLength", "maxLength"} & nodo.keys()
            if nodo.get("type") == "object":
                assert nodo["additionalProperties"] is False
                assert set(nodo["required"]) == set(nodo["properties"])
            for v in nodo.values():
                revisar(v)
        elif isinstance(nodo, list):
            for v in nodo:
                revisar(v)

    revisar(FORMATO_PEDIDO["schema"])


def test_transcripcion_lleva_los_platos_de_hoy_como_pista(db, menu_voz):
    from app.services.voice import contexto_de_hoy, pista_de_vocabulario

    pista = pista_de_vocabulario(contexto_de_hoy(db))
    assert "Caldo de gallina" in pista and "caldito" in pista and "Menú del día" in pista


def test_diagnostico_muestra_el_error_real(client, admin_headers, menu_voz, monkeypatch):
    from app.services import voice

    assert client.post("/api/voice/diagnostico").status_code == 401

    def falla(texto, contexto):
        raise voice.VozError("No te escuché bien", "Error code: 401 - Incorrect API key")

    monkeypatch.setattr(voice, "interpretar", falla)
    r = client.post("/api/voice/diagnostico", data={"texto": "un caldo"}, headers=admin_headers)
    assert r.status_code == 200
    paso = r.json()["interpretacion"]
    assert paso["ok"] is False and "Incorrect API key" in paso["error"]


def test_empaque_propio_de_un_plato(db, menu_voz):
    """"Tres sopas en bolsa y tres lomos en táper": UNA persona ×3 con la
    sopa en bolsa y el lomo en táper; "igual" no crea excepción."""
    from app.services.voice import _depurar, contexto_de_hoy

    m = menu_voz
    r = _depurar({
        "personas": [{
            "menu_id": m["menu_id"], "cantidad": 3,
            "elecciones": [
                {"tiempo_orden": 1, "plato_id": m["Caldo de gallina"], "empaque": "bolsa"},
                {"tiempo_orden": 2, "plato_id": m["Lomo saltado"], "empaque": "igual"},
            ],
            "sin": [], "empaque": "taper", "entrega": "auto", "nombre": "", "nota": "",
        }],
        "items": [], "no_encontrados": [], "notas": "",
    }, contexto_de_hoy(db))
    assert r["personas"][0]["empaques"] == {1: "bolsa"}
    assert r["personas"][0]["empaque"] == "taper"


def test_transcripcion_que_repite_la_pista_no_es_un_pedido(monkeypatch):
    """Con audio casi mudo el modelo devolvía la pista ("Pedido en un
    restaurante peruano. Platos de hoy: …") como si fuera lo dicho."""
    import openai

    from app.services import voice

    pista = "Pedido en un restaurante peruano. Platos de hoy: Chairito, Locro"

    class Transcripciones:
        def create(self, **kw):
            return type("T", (), {"text": pista + ", Menú del día"})()

    class Cliente:
        def __init__(self, **kw):
            self.audio = type("A", (), {"transcriptions": Transcripciones()})()

    monkeypatch.setattr(openai, "OpenAI", Cliente)
    with pytest.raises(voice.VozError) as e:
        voice.transcribir(b"x", "a.webm", pista)
    assert "Casi no te escuché" in e.value.mensaje_cliente


@pytest.fixture()
def extras_voz(db, menu_voz):
    """Gaseosas, mesas y un agregado ("Huevo frito") para el menú de voz."""
    from app.models import Bebida, MenuAgregado, Mesa

    inca = Bebida(nombre="Inca Kola personal", precio=2.5)
    litro = Bebida(nombre="Inca Kola 1 L", precio=5.0)
    mesa = Mesa(nombre="2 B")
    huevo = MenuAgregado(nombre="Huevo frito", precio=3.0, orden=1)
    db.add_all([inca, litro, mesa, huevo])
    db.commit()
    return {**menu_voz, "inca": inca.id, "litro": litro.id, "mesa": mesa.id, "huevo": huevo.id}


def test_prompt_trae_gaseosas_mesas_y_agregados(db, extras_voz):
    from app.services.voice import construir_system, contexto_de_hoy, pista_de_vocabulario

    contexto = contexto_de_hoy(db)
    system = construir_system(contexto)
    assert f"bebida_id: {extras_voz['inca']} | Inca Kola personal" in system
    assert '"2 B"' in system
    assert f"agregado_id: {extras_voz['huevo']} | Huevo frito" in system
    assert "Inca Kola personal" in pista_de_vocabulario(contexto)


def test_depurar_gaseosas_mesa_agregados_y_espera(db, extras_voz):
    from app.services.voice import _depurar, contexto_de_hoy

    m = extras_voz
    r = _depurar({
        "personas": [{
            "menu_id": m["menu_id"], "cantidad": 1,
            "elecciones": [
                {"tiempo_orden": 1, "plato_id": m["Caldo de gallina"], "empaque": "igual", "espera": False},
                {"tiempo_orden": 2, "plato_id": m["Lomo saltado"], "empaque": "igual", "espera": True},
            ],
            "sin": [], "empaque": "mesa", "entrega": "auto", "nombre": "", "nota": "",
            "agregados": [{"agregado_id": m["huevo"], "cantidad": 1}, {"agregado_id": 999, "cantidad": 1}],
        }],
        "items": [],
        "gaseosas": [{"bebida_id": m["inca"], "cantidad": 2}, {"bebida_id": 999, "cantidad": 1}],
        "mesa": "2b",
        "no_encontrados": [], "notas": "",
    }, contexto_de_hoy(db))
    persona = r["personas"][0]
    assert persona["espera"] == [2]
    assert persona["agregados"] == [{"agregado_id": m["huevo"], "cantidad": 1}]
    assert r["gaseosas"] == [{"bebida_id": m["inca"], "cantidad": 2}]
    assert r["mesa_id"] == m["mesa"]  # "2b" = "2 B"
    assert "gaseosa 999" in r["no_encontrados"]


def test_endpoint_devuelve_gaseosas_y_mesa(client, admin_headers, extras_voz, monkeypatch):
    from app.services import voice

    m = extras_voz
    activar_voz(client, admin_headers)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setattr(voice, "transcribir", lambda b, n="a", pista="": "un lomo y una inca para la 2B")
    monkeypatch.setattr(voice, "interpretar", lambda texto, contexto: (voice._depurar({
        "personas": [], "items": [],
        "gaseosas": [{"bebida_id": m["inca"], "cantidad": 1}],
        "mesa": "2 B", "no_encontrados": [], "notas": "",
    }, contexto), 0.0))
    r = client.post("/api/voice/order", files={"audio": ("a.webm", b"x", "audio/webm")})
    data = r.json()
    assert data["gaseosas"] == [{"bebida_id": m["inca"], "cantidad": 1, "nombre": "Inca Kola personal", "precio": 2.5}]
    assert data["mesa"] == {"id": m["mesa"], "nombre": "2 B"}


def test_voz_puede_quitar_un_tiempo_obligatorio(db, menu_voz):
    """"Solo segundo" con la entrada obligatoria: obligatorio significa que
    si no se nombra queda "SIN ELEGIR", no que no se pueda quitar."""
    from app.models import MenuTiempo
    from app.services.voice import _depurar, contexto_de_hoy

    for t in db.query(MenuTiempo).all():
        t.obligatorio = True
    db.commit()
    r = _depurar({
        "personas": [{
            "menu_id": menu_voz["menu_id"], "cantidad": 1,
            "elecciones": [{"tiempo_orden": 2, "plato_id": menu_voz["Lomo saltado"],
                            "empaque": "igual", "espera": False}],
            "sin": [1], "empaque": "mesa", "entrada": "auto", "entrega": "auto",
            "nombre": "", "nota": "", "agregados": [],
        }],
        "items": [], "gaseosas": [], "mesa": "", "no_encontrados": [], "notas": "",
    }, contexto_de_hoy(db))
    assert r["personas"][0]["sin"] == [1]


def test_pedido_corto_con_nombre_de_plato_no_es_eco(monkeypatch):
    """"Bistec frito" está en la pista, pero es un pedido de verdad."""
    import openai

    from app.services import voice

    class Transcripciones:
        def create(self, **kw):
            return type("T", (), {"text": "Bistec frito"})()

    class Cliente:
        def __init__(self, **kw):
            self.audio = type("A", (), {"transcriptions": Transcripciones()})()

    monkeypatch.setattr(openai, "OpenAI", Cliente)
    pista = "Pedido en un restaurante peruano. Platos de hoy: Bistec frito, Chairito"
    assert voice.transcribir(b"x", "a.webm", pista) == "Bistec frito"
