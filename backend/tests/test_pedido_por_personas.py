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
