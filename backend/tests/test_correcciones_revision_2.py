"""Correcciones de la revisión de código de la sesión (los que tocan backend).

Cada test reproduce el problema que se encontró, para que no vuelva.
"""
from app.models import Config, Plato


def crear(client, plato_id, cantidad=1):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": plato_id, "cantidad": cantidad}],
    })
    assert r.status_code == 201
    return r.json()["orden"]


def estados_de(client, orden_id):
    hoy = client.get("/api/orders/today").json()
    orden = next(o for o in hoy["ordenes"] if o["id"] == orden_id)
    return sorted((i["estado"], i["cantidad"]) for i in orden["items"])


def test_avanzar_la_orden_no_retrocede_lo_ya_despachado(client, menu_ejemplo):
    """El bug: cocina tachaba 2 asados como listos y luego tocaba "empezar a
    preparar" en la tarjeta; esas 2 porciones volvían a la cola y se
    cocinaban dos veces."""
    orden = crear(client, menu_ejemplo["Lomo saltado"], cantidad=3)

    # Cocina tacha 2 porciones como entregadas desde "Por salir"
    client.post("/api/orders/despachar-bulk", json={
        "estado_destino": "entregado",
        "lineas": [{"plato_nombre": "Lomo saltado", "cantidad": 2}],
    })
    assert estados_de(client, orden["id"]) == [("entregado", 2), ("pendiente", 1)]

    # Ahora avanza la ORDEN completa a preparando
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "preparando"})

    # Las 2 entregadas siguen entregadas; solo avanza la que estaba atrás
    assert estados_de(client, orden["id"]) == [("entregado", 2), ("preparando", 1)]


def test_avanzar_la_orden_sigue_arrastrando_hacia_adelante(client, menu_ejemplo):
    orden = crear(client, menu_ejemplo["Lomo saltado"], cantidad=2)
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "listo"})
    assert estados_de(client, orden["id"]) == [("listo", 2)]


def test_el_ticket_de_prueba_espera_a_confirmarse(client, admin_headers, db):
    """El bug: la cola consumía el ticket de prueba al servirlo. Si la
    impresora no respondía — el caso que el botón sirve para diagnosticar —
    el trabajo se perdía y no salía nunca."""
    db.add(Config(clave="modo_impresion", valor="puente"))
    db.commit()
    client.post("/api/print/prueba", headers=admin_headers)

    # Se puede pedir la cola varias veces sin perder el trabajo
    for _ in range(3):
        trabajos = client.get("/api/print/cola").json()["trabajos"]
        assert [t["tipo"] for t in trabajos] == ["prueba"]

    # Recién al confirmar sale de la cola
    assert client.post("/api/print/prueba/impresa").json() == {"confirmada": True}
    assert client.get("/api/print/cola").json()["trabajos"] == []


def test_confirmar_prueba_sin_nada_encolado_no_falla(client):
    assert client.post("/api/print/prueba/impresa").status_code == 200


def test_bulk_a_preparando_solo_toma_lo_pendiente(client, menu_ejemplo):
    """Documenta el límite que la pantalla ahora respeta: el backend no
    retrocede estados, así que a "preparando" solo pueden pasar las
    porciones que siguen pendientes."""
    crear(client, menu_ejemplo["Lomo saltado"], cantidad=4)
    client.post("/api/orders/despachar-bulk", json={
        "estado_destino": "preparando",
        "lineas": [{"plato_nombre": "Lomo saltado", "cantidad": 3}],
    })
    # Quedan 4 por salir pero solo 1 sin empezar: pedir 4 a preparando falla
    r = client.post("/api/orders/despachar-bulk", json={
        "estado_destino": "preparando",
        "lineas": [{"plato_nombre": "Lomo saltado", "cantidad": 4}],
    })
    assert r.status_code == 409
    # Pedir esa 1 sí funciona (es lo que la pantalla ofrece ahora)
    r = client.post("/api/orders/despachar-bulk", json={
        "estado_destino": "preparando",
        "lineas": [{"plato_nombre": "Lomo saltado", "cantidad": 1}],
    })
    assert r.status_code == 200
    # Y a "listo" sí se pueden tachar las 4 de una
    r = client.post("/api/orders/despachar-bulk", json={
        "estado_destino": "listo",
        "lineas": [{"plato_nombre": "Lomo saltado", "cantidad": 4}],
    })
    assert r.status_code == 200


def test_menu_incompleto_responde_422_con_mensaje_util(client, db, menu_ejemplo):
    """La terminal muestra este texto tal cual: tiene que explicar qué falta."""
    from app.models import MenuAlternativa, MenuPlantilla, MenuTiempo

    plantilla = MenuPlantilla(nombre="Menú del día", precio=11.0,
                              activo_hoy=True, en_catalogo=True)
    t1 = MenuTiempo(orden=1, rotulo="Entrada", obligatorio=True)
    t1.alternativas = [
        MenuAlternativa(plato_id=menu_ejemplo["Lomo saltado"]),
        MenuAlternativa(plato_id=menu_ejemplo["Chicha morada"]),
    ]
    t2 = MenuTiempo(orden=2, rotulo="Segundo", obligatorio=True)
    t2.alternativas = [
        MenuAlternativa(plato_id=menu_ejemplo["Lomo saltado"]),
        MenuAlternativa(plato_id=menu_ejemplo["Chicha morada"]),
    ]
    plantilla.tiempos = [t1, t2]
    db.add(plantilla)
    db.commit()

    r = client.post("/api/orders", json={"menus": [{
        "menu_id": plantilla.id, "cantidad": 1,
        "elecciones": {"1": menu_ejemplo["Lomo saltado"]},  # falta el segundo
    }]})
    assert r.status_code == 422
    assert "Segundo" in r.json()["detail"] and "Menú del día" in r.json()["detail"]
