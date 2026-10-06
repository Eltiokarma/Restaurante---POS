"""Presa de pollo y cambio de proteína por 2 huevos fritos: van en el
plato (detalle) y salen en la comanda; sin elegir no se imprime nada."""
import base64

from app.models import Config, MenuAlternativa, MenuPlantilla, MenuTiempo, Plato


def _local(db):
    platos = {
        "Caldo": Plato(nombre="Caldo", categoria="entrada", precio=5, activo_hoy=True),
        "Arroz con Pollo": Plato(nombre="Arroz con Pollo", categoria="fondo", precio=10, activo_hoy=True),
        "Trucha": Plato(nombre="Trucha", categoria="fondo", precio=10, activo_hoy=True),
    }
    db.add_all(platos.values())
    db.flush()
    menu = MenuPlantilla(nombre="Menú", precio=11, activo_hoy=True)
    t1 = MenuTiempo(orden=1, rotulo="Entrada", obligatorio=True, descuento_si_se_quita=1)
    t1.alternativas = [MenuAlternativa(plato_id=platos["Caldo"].id)]
    t2 = MenuTiempo(orden=2, rotulo="Segundo", obligatorio=True)
    t2.alternativas = [MenuAlternativa(plato_id=platos["Arroz con Pollo"].id),
                       MenuAlternativa(plato_id=platos["Trucha"].id)]
    menu.tiempos = [t1, t2]
    db.add(menu)
    db.add(Config(clave="modo_impresion", valor="puente"))
    db.add(Config(clave="impresora_ip", valor="192.168.1.77"))
    db.commit()
    return menu.id, {n: p.id for n, p in platos.items()}


def _persona(menu_id, segundo, variante=None):
    return {"menu_id": menu_id, "cantidad": 1, "elecciones": {"2": segundo},
            "variantes": {"2": variante} if variante else {}}


def test_presa_y_huevo_en_la_comanda(client, db):
    menu_id, p = _local(db)
    r = client.post("/api/orders", json={"menus": [
        _persona(menu_id, p["Arroz con Pollo"], {"presa": "pierna"}),
        _persona(menu_id, p["Trucha"], {"huevo": True, "coccion": "inglesa"}),
        _persona(menu_id, p["Arroz con Pollo"], {"huevo": True}),
        _persona(menu_id, p["Arroz con Pollo"]),
    ]})
    assert r.status_code == 201, r.text
    orden = r.json()["orden"]
    assert orden["total"] == 44  # el huevo no cambia el precio
    detalles = [i["detalle"] for m in orden["menus"] for i in m["items"] if i["nombre"] != "Caldo"]
    assert detalles == ["PIERNA", "2 HUEVOS A LA INGLESA EN VEZ DE CARNE", "2 HUEVOS FRITOS EN VEZ DE CARNE", ""]

    comanda = base64.b64decode(client.get("/api/print/cola").json()["trabajos"][0]["datos_b64"]).decode("cp850")
    assert "Arroz con Pollo -> PIERNA" in comanda
    assert "2 HUEVOS A LA INGLESA EN VEZ DE CARNE" in comanda
    assert "1 x Arroz con Pollo\n" in comanda  # sin elegir presa: nada extra


def test_variantes_invalidas(client, db):
    menu_id, p = _local(db)
    # Presa a un plato sin pollo
    r = client.post("/api/orders", json={"menus": [_persona(menu_id, p["Trucha"], {"presa": "ala"})]})
    assert r.status_code == 422
    # Cocción sin huevo
    r = client.post("/api/orders", json={"menus": [_persona(menu_id, p["Arroz con Pollo"], {"coccion": "inglesa"})]})
    assert r.status_code == 422
    # Presa que no existe
    r = client.post("/api/orders", json={"menus": [_persona(menu_id, p["Arroz con Pollo"], {"presa": "cola"})]})
    assert r.status_code == 422
