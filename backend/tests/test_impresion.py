"""Modo de impresión "puente": cola ESC/POS para la impresora de red."""
import base64

from app.models import Config


def activar_modo_puente(db, ip="192.168.1.77"):
    db.add(Config(clave="modo_impresion", valor="puente"))
    db.add(Config(clave="impresora_ip", valor=ip))
    db.commit()


def crear_orden(client, menu_ejemplo):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 2,
                   "nota": "sin ají"}],
    })
    assert r.status_code == 201
    return r.json()["orden"]


def test_modo_puente_encola_las_ordenes(client, db, menu_ejemplo):
    activar_modo_puente(db)
    orden = crear_orden(client, menu_ejemplo)

    cola = client.get("/api/print/cola").json()
    assert cola["impresora"] == {"ip": "192.168.1.77", "puerto": 9100}
    assert len(cola["trabajos"]) == 1
    trabajo = cola["trabajos"][0]
    assert trabajo["tipo"] == "orden" and trabajo["orden_id"] == orden["id"]

    datos = base64.b64decode(trabajo["datos_b64"])
    assert datos.startswith(b"\x1b@")            # inicializar impresora
    assert b"ORDEN #001" in datos
    assert "sin ají".encode("cp850") in datos     # tildes en CP850, no UTF-8
    assert b"\x1dV\x42" in datos                  # corte de papel

    # El puente confirma la impresión y la cola queda vacía
    client.post(f"/api/orders/{orden['id']}/printed")
    assert client.get("/api/print/cola").json()["trabajos"] == []


def test_modo_terminal_no_encola(client, menu_ejemplo):
    crear_orden(client, menu_ejemplo)  # modo por defecto: terminal
    assert client.get("/api/print/cola").json()["trabajos"] == []


def test_anulada_sale_de_la_cola(client, db, menu_ejemplo):
    activar_modo_puente(db)
    orden = crear_orden(client, menu_ejemplo)
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})
    assert client.get("/api/print/cola").json()["trabajos"] == []


def test_ticket_de_prueba_requiere_admin_y_se_consume(client, admin_headers):
    assert client.post("/api/print/prueba").status_code == 401

    r = client.post("/api/print/prueba", headers=admin_headers)
    assert r.json() == {"encolada": True}

    cola = client.get("/api/print/cola").json()
    tipos = [t["tipo"] for t in cola["trabajos"]]
    assert tipos == ["prueba"]
    datos = base64.b64decode(cola["trabajos"][0]["datos_b64"])
    assert b"PRUEBA OK" in datos

    # Se sirve UNA vez: el siguiente ciclo del puente ya no la ve
    assert client.get("/api/print/cola").json()["trabajos"] == []


def test_ticket_escpos_con_menu_encadenado(client, db, menu_ejemplo):
    from app.models import MenuAlternativa, MenuPlantilla, MenuTiempo

    activar_modo_puente(db)
    plantilla = MenuPlantilla(nombre="Menú del día", precio=11.0,
                              activo_hoy=True, en_catalogo=True)
    tiempo = MenuTiempo(orden=1, rotulo="Segundo", obligatorio=True, precio_extra=3.0)
    tiempo.alternativas = [MenuAlternativa(plato_id=menu_ejemplo["Lomo saltado"])]
    plantilla.tiempos = [tiempo]
    db.add(plantilla)
    db.commit()

    r = client.post("/api/orders", json={"menus": [{
        "menu_id": plantilla.id, "cantidad": 1,
        "extras": [{"tiempo_orden": 1, "plato_id": menu_ejemplo["Lomo saltado"],
                    "cantidad": 1}],
    }], "entrega": "separado"})
    assert r.status_code == 201

    cola = client.get("/api/print/cola").json()
    datos = base64.b64decode(cola["trabajos"][0]["datos_b64"])
    assert "Menú del día".encode("cp850") in datos
    assert b"(EXTRA)" in datos
    assert b"TOTAL" in datos and b"14.00" in datos


def test_config_de_impresora(client, admin_headers):
    config = client.get("/api/config").json()
    assert config["impresora_ip"] == "" and config["impresora_puerto"] == 9100
    r = client.put("/api/config", json={
        "impresora_ip": "10.0.0.5", "impresora_puerto": 9100, "impresora_columnas": 48,
        "modo_impresion": "puente",
    }, headers=admin_headers)
    datos = r.json()
    assert datos["impresora_ip"] == "10.0.0.5"
    assert datos["impresora_columnas"] == 48
    assert datos["modo_impresion"] == "puente"
