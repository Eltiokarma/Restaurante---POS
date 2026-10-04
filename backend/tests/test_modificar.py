"""Cambios a una orden ya registrada: devolver la sopa, pasar a táper,
sumar o quitar personas y gaseosas. El total se recalcula desde cero y
cocina recibe un ticket de CAMBIO con solo lo que cambió."""
import base64

import pytest

from app.models import (
    Bebida, Cancelacion, Config, MenuAlternativa, MenuPlantilla, MenuTiempo, Plato, TicketBebida,
)


@pytest.fixture()
def local(db):
    """Menú S/ 11 (sopa quitable con S/ 1 de descuento), táper a S/ 1,
    una gaseosa y modo puente (los cambios van a la cola)."""
    platos = {
        "Sopa criolla": Plato(nombre="Sopa criolla", categoria="entrada", precio=6.0,
                              activo_hoy=True, en_catalogo=True),
        "Causa": Plato(nombre="Causa", categoria="entrada", precio=6.0,
                       activo_hoy=True, en_catalogo=True),
        "Lomo saltado": Plato(nombre="Lomo saltado", categoria="fondo", precio=10.0,
                              activo_hoy=True, en_catalogo=True),
        "Trucha": Plato(nombre="Trucha", categoria="fondo", precio=10.0,
                        activo_hoy=True, en_catalogo=True),
    }
    db.add_all(platos.values())
    db.flush()
    plantilla = MenuPlantilla(nombre="Menú del día", precio=11.0, activo_hoy=True, en_catalogo=True)
    t1 = MenuTiempo(orden=1, rotulo="Entrada", obligatorio=True, descuento_si_se_quita=1.0)
    t1.alternativas = [MenuAlternativa(plato_id=platos["Sopa criolla"].id),
                       MenuAlternativa(plato_id=platos["Causa"].id)]
    t2 = MenuTiempo(orden=2, rotulo="Segundo", obligatorio=True)
    t2.alternativas = [MenuAlternativa(plato_id=platos["Lomo saltado"].id),
                       MenuAlternativa(plato_id=platos["Trucha"].id, recargo=1.0)]
    plantilla.tiempos = [t1, t2]
    db.add(plantilla)
    inca = Bebida(nombre="Inca Kola personal", precio=2.5)
    db.add(inca)
    db.add(Config(clave="precio_taper", valor="1"))
    db.add(Config(clave="modo_impresion", valor="puente"))
    db.add(Config(clave="impresora_ip", valor="192.168.1.77"))
    db.commit()
    return {"menu_id": plantilla.id, "inca": inca.id, **{n: p.id for n, p in platos.items()}}


def persona(local, entrada=None, segundo=None, sin=None, nombre=""):
    elecciones = {}
    if entrada:
        elecciones["1"] = local[entrada]
    if segundo:
        elecciones["2"] = local[segundo]
    return {"menu_id": local["menu_id"], "cantidad": 1, "elecciones": elecciones,
            "omitidos": sin or [], "nombre_persona": nombre}


def crear(client, local, *personas, **extra):
    r = client.post("/api/orders", json={"menus": list(personas), **extra})
    assert r.status_code == 201, r.text
    orden = r.json()["orden"]
    # La comanda original ya salió: en la cola solo queda lo nuevo
    client.post(f"/api/orders/{orden['id']}/printed")
    return orden


def cambios_en_cola(client) -> list[str]:
    return [
        base64.b64decode(t["datos_b64"]).decode("cp850")
        for t in client.get("/api/print/cola").json()["trabajos"] if t["tipo"] == "bebida"
    ]


def test_devolver_la_sopa_quitada(client, local, db):
    orden = crear(client, local, persona(local, segundo="Lomo saltado", sin=[1], nombre="Rosa"))
    assert orden["total"] == 10.0  # solo segundo
    om = orden["menus"][0]
    r = client.post(f"/api/orders/{orden['id']}/menus/{om['id']}/devolver",
                    json={"tiempo_orden": 1, "plato_id": local["Sopa criolla"]})
    assert r.status_code == 200, r.text
    nueva = r.json()["orden"]
    assert nueva["total"] == 11.0
    assert nueva["menus"][0]["omitidos"] == []
    assert "Sopa criolla" in [i["nombre"] for i in nueva["menus"][0]["items"]]
    assert r.json()["ticket_cambio"]["total"] == 1.0
    (ticket,) = cambios_en_cola(client)
    assert "CAMBIO" in ticket and "AGREGAR: Sopa criolla (ROSA)" in ticket
    assert "Nuevo total: S/ 11.00" in ticket


def test_devolver_sin_elegir_queda_pendiente(client, local):
    orden = crear(client, local, persona(local, segundo="Lomo saltado", sin=[1]))
    om = orden["menus"][0]
    r = client.post(f"/api/orders/{orden['id']}/menus/{om['id']}/devolver", json={"tiempo_orden": 1})
    nueva = r.json()["orden"]
    assert nueva["total"] == 11.0
    assert nueva["menus"][0]["pendientes"] == ["Entrada"]


def test_pasar_a_taper_y_volver(client, local):
    orden = crear(client, local, persona(local, "Sopa criolla", "Lomo saltado"))
    lomo = next(i for i in orden["menus"][0]["items"] if i["nombre"] == "Lomo saltado")
    r = client.patch(f"/api/orders/{orden['id']}/items/{lomo['id']}/empaque", json={"empaque": "taper"})
    nueva = r.json()["orden"]
    assert nueva["total"] == 12.0  # +1 del táper
    assert any(i["nombre"] == "Táper" and i["cantidad"] == 1 for i in nueva["items"])
    assert nueva["tipo_servicio"] == "mixto"
    assert "Lomo saltado -> TAPER" in cambios_en_cola(client)[0]

    r = client.patch(f"/api/orders/{orden['id']}/items/{lomo['id']}/empaque", json={"empaque": "mesa"})
    nueva = r.json()["orden"]
    assert nueva["total"] == 11.0
    assert not any(i["nombre"] == "Táper" for i in nueva["items"])
    assert nueva["tipo_servicio"] == "sala"


def test_agregar_persona_y_gaseosa_vuelve_a_cocina(client, local, db):
    orden = crear(client, local, persona(local, "Sopa criolla", "Lomo saltado"))
    # Cocina ya despachó todo
    for item in orden["menus"][0]["items"]:
        client.patch(f"/api/orders/items/{item['id']}/status", json={"estado": "entregado"})
    r = client.post(f"/api/orders/{orden['id']}/agregar", json={
        "menus": [persona(local, "Causa", "Trucha", nombre="Ana")],
        "bebidas": [{"bebida_id": local["inca"], "cantidad": 2}],
    })
    assert r.status_code == 200, r.text
    nueva = r.json()["orden"]
    assert nueva["total"] == 11.0 + 12.0 + 5.0  # trucha con recargo + 2 gaseosas
    assert len(nueva["menus"]) == 2
    assert nueva["estado"] == "pendiente"  # lo nuevo vuelve a cocina
    ticket = cambios_en_cola(client)[0]
    assert "AGREGAR: Causa (ANA)" in ticket and "AGREGAR: Trucha (ANA)" in ticket
    assert "AGREGAR: Inca Kola personal" in ticket


def test_quitar_persona_y_gaseosa_queda_en_cancelaciones(client, local, db):
    orden = crear(client, local,
                  persona(local, "Sopa criolla", "Lomo saltado"),
                  persona(local, "Causa", "Trucha", nombre="Ana"),
                  bebidas=[{"bebida_id": local["inca"], "cantidad": 1}])
    assert orden["total"] == 11.0 + 12.0 + 2.5
    ana = next(m for m in orden["menus"] if m["nombre_persona"] == "Ana")
    r = client.delete(f"/api/orders/{orden['id']}/menus/{ana['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["orden"]["total"] == 13.5
    gaseosa = next(i for i in r.json()["orden"]["items"] if i["nombre"] == "Inca Kola personal")
    r = client.delete(f"/api/orders/{orden['id']}/items/{gaseosa['id']}")
    assert r.json()["orden"]["total"] == 11.0
    assert db.query(Cancelacion).count() == 2
    assert "QUITAR: Causa, Trucha (ANA)" in cambios_en_cola(client)[0]

    # La última persona no se quita: eso es anular la orden
    unica = r.json()["orden"]["menus"][0]
    assert client.delete(f"/api/orders/{orden['id']}/menus/{unica['id']}").status_code == 409


def test_plato_del_menu_no_se_quita_suelto(client, local):
    orden = crear(client, local, persona(local, "Sopa criolla", "Lomo saltado"),
                  persona(local, "Causa", "Trucha"))
    lomo = next(i for i in orden["menus"][0]["items"] if i["nombre"] == "Lomo saltado")
    assert client.delete(f"/api/orders/{orden['id']}/items/{lomo['id']}").status_code == 409


def test_anulada_no_se_modifica(client, local):
    orden = crear(client, local, persona(local, "Sopa criolla", "Lomo saltado"))
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})
    r = client.post(f"/api/orders/{orden['id']}/agregar",
                    json={"bebidas": [{"bebida_id": local["inca"], "cantidad": 1}]})
    assert r.status_code == 409


def test_modo_terminal_no_encola_pero_devuelve_el_ticket(client, local, db):
    db.query(Config).filter(Config.clave == "modo_impresion").update({"valor": "terminal"})
    db.commit()
    orden = crear(client, local, persona(local, "Sopa criolla", "Lomo saltado"))
    r = client.post(f"/api/orders/{orden['id']}/agregar",
                    json={"bebidas": [{"bebida_id": local["inca"], "cantidad": 1}]})
    assert r.json()["ticket_cambio"]["items"][0]["nombre"] == "AGREGAR: Inca Kola personal"
    assert db.query(TicketBebida).count() == 0


def test_cada_ticket_de_cambio_dice_su_propio_total(client, local):
    orden = crear(client, local, persona(local, "Sopa criolla", "Lomo saltado"))
    lomo = next(i for i in orden["menus"][0]["items"] if i["nombre"] == "Lomo saltado")
    client.patch(f"/api/orders/{orden['id']}/items/{lomo['id']}/empaque", json={"empaque": "taper"})
    client.post(f"/api/orders/{orden['id']}/agregar",
                json={"bebidas": [{"bebida_id": local["inca"], "cantidad": 1}]})
    primero, segundo = cambios_en_cola(client)
    assert "Nuevo total: S/ 12.00" in primero
    assert "Nuevo total: S/ 14.50" in segundo
