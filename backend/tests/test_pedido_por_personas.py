"""Pedido por personas (cada menú = una persona): entrega por menú, platos
"va a esperar", lo sin elegir en la comanda y el menú del día desde caja."""
from app.models import Orden
from app.services.escpos import render_orden
from tests.test_menu_encadenado import fonda  # noqa: F401  (fixture)


def _menu(fonda, segundo="Asado con puré", **extra):
    return {
        "menu_id": fonda["menu_id"], "cantidad": 1,
        "elecciones": {"1": fonda["platos"]["Sopa criolla"], "2": fonda["platos"][segundo]},
        **extra,
    }


def test_entrega_por_persona(client, fonda):
    # El bistec sale al momento: SOLO esa persona tiene que ir por tiempos
    r = client.post("/api/orders", json={"entrega": "junto", "menus": [
        _menu(fonda, "Bistec frito"),
        _menu(fonda),
    ]})
    assert r.status_code == 422

    r = client.post("/api/orders", json={"entrega": "junto", "menus": [
        _menu(fonda, "Bistec frito", entrega="separado"),
        _menu(fonda, entrega="junto"),
    ]})
    assert r.status_code == 201
    assert [m["entrega"] for m in r.json()["orden"]["menus"]] == ["separado", "junto"]


def test_entrega_invalida_por_menu(client, fonda):
    r = client.post("/api/orders", json={"menus": [_menu(fonda, entrega="volando")]})
    assert r.status_code == 422


def test_menu_sin_entrega_hereda_la_de_la_orden(client, fonda):
    r = client.post("/api/orders", json={"entrega": "separado", "menus": [_menu(fonda)]})
    assert r.json()["orden"]["menus"][0]["entrega"] == "separado"


def test_plato_va_a_esperar(client, fonda):
    r = client.post("/api/orders", json={"menus": [_menu(fonda, espera=[2])]})
    assert r.status_code == 201
    items = {i["tiempo_orden"]: i["espera"] for i in r.json()["orden"]["menus"][0]["items"]}
    assert items[2] is True and items[1] is False


def test_lo_que_espera_no_entra_a_la_tanda(client, fonda):
    client.post("/api/orders", json={"menus": [_menu(fonda, espera=[2])]})
    tandas = client.get("/api/orders/tandas").json()["tandas"]
    nombres = {p["nombre"] for t in tandas for p in t["platos"]}
    assert "Sopa criolla" in nombres
    assert "Asado con puré" not in nombres


def test_comanda_impresa_dice_espera_sin_elegir_y_entregas(client, db, fonda):
    client.post("/api/orders", json={"entrega": "junto", "menus": [
        _menu(fonda, espera=[2]),
        {"menu_id": fonda["menu_id"], "cantidad": 1,
         "elecciones": {"1": fonda["platos"]["Sopa criolla"]}, "entrega": "separado"},
    ]})
    orden = db.query(Orden).one()
    texto = render_orden(orden, {"nombre": "Fonda"}).decode("cp850", errors="ignore")
    assert "(ESPERA)" in texto
    assert "SEGUNDO SIN ELEGIR" in texto
    assert "ENTREGA: 1 JUNTO / 1 POR TIEMPOS" in texto


def test_caja_escoge_el_menu_del_dia_sin_admin(client, fonda):
    datos = client.get("/api/menu/caja").json()
    plantilla = datos["plantillas"][0]
    segundos = plantilla["tiempos"][1]["alternativas"]
    assert all(a["activo_hoy"] for a in segundos)

    # Sacar el tallarín de hoy: desaparece de las alternativas vendibles
    r = client.patch(f"/api/menu/platos/{fonda['platos']['Tallarín rojo']}/hoy",
                     json={"activo_hoy": False})
    assert r.status_code == 200
    hoy = client.get("/api/menu/today").json()["menus"][0]
    assert "Tallarín rojo" not in [a["nombre"] for a in hoy["tiempos"][1]["alternativas"]]

    # Apagar el menú entero y volverlo a prender
    client.patch(f"/api/menu/plantillas/{fonda['menu_id']}/hoy", json={"activo_hoy": False})
    assert client.get("/api/menu/today").json()["menus"] == []
    client.patch(f"/api/menu/plantillas/{fonda['menu_id']}/hoy", json={"activo_hoy": True})
    assert len(client.get("/api/menu/today").json()["menus"]) == 1

    assert client.patch("/api/menu/platos/9999/hoy", json={"activo_hoy": True}).status_code == 404


def test_caja_carga_un_menu_guardado(client, admin_headers, fonda):
    client.post("/api/menu/guardados", json={"nombre": "Lunes"}, headers=admin_headers)
    guardado = client.get("/api/menu/caja").json()["guardados"][0]
    client.patch(f"/api/menu/platos/{fonda['platos']['Tallarín rojo']}/hoy",
                 json={"activo_hoy": False})
    r = client.post(f"/api/menu/caja/guardados/{guardado['id']}/cargar")
    assert r.status_code == 200
    hoy = client.get("/api/menu/today").json()["menus"][0]
    assert "Tallarín rojo" in [a["nombre"] for a in hoy["tiempos"][1]["alternativas"]]


def test_nombre_de_la_persona_sale_en_la_comanda(client, db, fonda):
    r = client.post("/api/orders", json={"menus": [
        _menu(fonda, nombre_persona="  Juan "),
        {"menu_id": fonda["menu_id"], "cantidad": 1,
         "elecciones": {"1": fonda["platos"]["Sopa criolla"]}, "nombre_persona": "Ana"},
    ]})
    assert r.status_code == 201
    assert [m["nombre_persona"] for m in r.json()["orden"]["menus"]] == ["Juan", "Ana"]
    orden = db.query(Orden).one()
    texto = render_orden(orden, {"nombre": "Fonda"}).decode("cp850", errors="ignore")
    assert "Asado con puré (JUAN)" in texto
    assert "SEGUNDO SIN ELEGIR (ANA)" in texto


def test_nombre_demasiado_largo_se_rechaza(client, fonda):
    r = client.post("/api/orders", json={"menus": [_menu(fonda, nombre_persona="x" * 41)]})
    assert r.status_code == 422


def test_cierre_viejo_no_sale_por_el_puente(client, db):
    """Un cierre de hace semanas (el puente estuvo apagado) no se imprime
    de la nada: se descarta de la cola. El de hoy sí sale."""
    from datetime import timedelta

    from app.models import CierreCaja, Config, hoy_lima
    from app.routes.impresion import CLAVE_CIERRE

    viejo = CierreCaja(fecha=hoy_lima() - timedelta(days=20), hora_apertura="08:00:00",
                       monto_apertura=0, hora_cierre="21:00:00")
    db.add(viejo)
    db.commit()
    db.add(Config(clave=CLAVE_CIERRE, valor=str(viejo.id)))
    db.commit()
    trabajos = client.get("/api/print/cola").json()["trabajos"]
    assert [t for t in trabajos if t["tipo"] == "cierre"] == []

    hoy = CierreCaja(fecha=hoy_lima(), hora_apertura="08:00:00", monto_apertura=0,
                     hora_cierre="21:00:00")
    db.add(hoy)
    db.commit()
    db.get(Config, CLAVE_CIERRE).valor = str(hoy.id)
    db.commit()
    trabajos = client.get("/api/print/cola").json()["trabajos"]
    assert [t["tipo"] for t in trabajos] == ["cierre"]


def test_elegir_despues_lo_que_quedo_sin_elegir(client, fonda):
    r = client.post("/api/orders", json={"entrega": "junto", "menus": [{
        "menu_id": fonda["menu_id"], "cantidad": 1,
        "elecciones": {"1": fonda["platos"]["Sopa criolla"]},
    }]})
    orden = r.json()["orden"]
    om = orden["menus"][0]
    assert om["pendientes"] == ["Segundo"]
    total_antes = orden["total"]

    # El bistec tiene recargo S/ 2 y sale al momento
    r = client.post(f"/api/orders/{orden['id']}/menus/{om['id']}/elegir",
                    json={"tiempo_orden": 2, "plato_id": fonda["platos"]["Bistec frito"]})
    assert r.status_code == 200
    despues = r.json()
    menu = despues["menus"][0]
    assert menu["pendientes"] == []
    assert "Bistec frito" in [i["nombre"] for i in menu["items"]]
    assert despues["total"] == round(total_antes + 2.0, 2)
    assert menu["entrega"] == "separado"  # al momento: esa persona va por tiempos

    # Elegir otra vez el mismo tiempo ya no se puede
    r = client.post(f"/api/orders/{orden['id']}/menus/{om['id']}/elegir",
                    json={"tiempo_orden": 2, "plato_id": fonda["platos"]["Tallarín rojo"]})
    assert r.status_code == 409


def test_elegir_fuera_de_las_opciones_se_rechaza(client, fonda):
    r = client.post("/api/orders", json={"menus": [{
        "menu_id": fonda["menu_id"], "cantidad": 1,
        "elecciones": {"1": fonda["platos"]["Sopa criolla"]},
    }]})
    orden = r.json()["orden"]
    om = orden["menus"][0]
    r = client.post(f"/api/orders/{orden['id']}/menus/{om['id']}/elegir",
                    json={"tiempo_orden": 2, "plato_id": fonda["platos"]["Chicha morada"]})
    assert r.status_code == 422


def test_soltar_lo_que_espera_lo_manda_a_la_tanda(client, fonda):
    r = client.post("/api/orders", json={"menus": [_menu(fonda, espera=[2])]})
    item = next(i for i in r.json()["orden"]["menus"][0]["items"] if i["tiempo_orden"] == 2)
    nombres = lambda: {p["nombre"] for t in client.get("/api/orders/tandas").json()["tandas"] for p in t["platos"]}  # noqa: E731
    assert "Asado con puré" not in nombres()
    assert client.post(f"/api/orders/items/{item['id']}/soltar").status_code == 200
    assert "Asado con puré" in nombres()


def test_tiempos_por_persona_en_la_comanda(client, db, fonda):
    client.post("/api/orders", json={"entrega": "junto", "menus": [
        _menu(fonda, "Bistec frito", entrega="separado"),
        _menu(fonda, entrega="junto"),
    ]})
    orden = db.query(Orden).one()
    texto = render_orden(orden, {"nombre": "Fonda"}).decode("cp850", errors="ignore")
    assert "Bistec frito (TIEMPOS)" in texto
    assert "Asado con puré (TIEMPOS)" not in texto


def test_dos_comandas_salen_dos_veces_por_el_puente(client, fonda):
    from app.models import Config

    r = client.post("/api/orders", json={"menus": [_menu(fonda)], "copias": 2})
    assert r.status_code == 201
    orden = r.json()["orden"]
    assert orden["copias"] == 2
    # En modo puente la orden queda en cola; sus bytes van dos veces
    import base64

    from app.db import SessionLocal

    db = SessionLocal()
    db.merge(Config(clave="modo_impresion", valor="puente"))
    db.commit()
    db.close()
    client.post(f"/api/orders/{orden['id']}/reprint")  # vuelve a la cola…
    trabajo = next(t for t in client.get("/api/print/cola").json()["trabajos"] if t["tipo"] == "orden")
    una = base64.b64decode(trabajo["datos_b64"])
    assert una.count(b"ORDEN #") == 1  # …y la reimpresión sale UNA vez

    r = client.post("/api/orders", json={"menus": [_menu(fonda)], "copias": 2})
    trabajos = [t for t in client.get("/api/print/cola").json()["trabajos"] if t["tipo"] == "orden"]
    nueva = next(t for t in trabajos if t["orden_id"] == r.json()["orden"]["id"])
    assert base64.b64decode(nueva["datos_b64"]).count(b"ORDEN #") == 2


def test_copias_fuera_de_rango_se_rechaza(client, fonda):
    assert client.post("/api/orders", json={"menus": [_menu(fonda)], "copias": 5}).status_code == 422
