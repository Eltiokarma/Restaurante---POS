"""Menú encadenado (Fase 5, §1): el menú como unidad de venta con tiempos.

Puntos clave: el precio vive en el MENÚ (no doble cobro), los tiempos con
una sola alternativa vienen incluidos, y "una entrada más" se cobra al
precio_extra configurado del tiempo (S/ 3 aunque dentro del menú la
entrada vaya casi regalada).
"""
import pytest

from app.models import MenuAlternativa, MenuPlantilla, MenuTiempo, Plato, hoy_lima


@pytest.fixture()
def fonda(db):
    """Platos + plantilla 'Menú del día' S/ 11: entrada o sopa (extra S/ 3)
    → segundo → refresco (única opción, incluido)."""
    platos = {
        "Sopa criolla": Plato(nombre="Sopa criolla", categoria="entrada", precio=6.0,
                              activo_hoy=True, en_catalogo=True),
        "Papa a la huancaína": Plato(nombre="Papa a la huancaína", categoria="entrada",
                                     precio=6.0, activo_hoy=True, en_catalogo=True),
        "Asado con puré": Plato(nombre="Asado con puré", categoria="fondo", precio=10.0,
                                activo_hoy=True, en_catalogo=True),
        "Tallarín rojo": Plato(nombre="Tallarín rojo", categoria="fondo", precio=10.0,
                               activo_hoy=True, en_catalogo=True),
        "Bistec frito": Plato(nombre="Bistec frito", categoria="fondo", precio=12.0,
                              activo_hoy=True, en_catalogo=True, sale_al_momento=True),
        "Chicha morada": Plato(nombre="Chicha morada", categoria="bebida", precio=3.5,
                               activo_hoy=True, en_catalogo=True),
    }
    db.add_all(platos.values())
    db.flush()

    plantilla = MenuPlantilla(nombre="Menú del día", precio=11.0,
                              activo_hoy=True, en_catalogo=True)
    t1 = MenuTiempo(orden=1, rotulo="Entrada o sopa", obligatorio=True, precio_extra=3.0)
    t1.alternativas = [
        MenuAlternativa(plato_id=platos["Sopa criolla"].id),
        MenuAlternativa(plato_id=platos["Papa a la huancaína"].id),
    ]
    t2 = MenuTiempo(orden=2, rotulo="Segundo", obligatorio=True)
    t2.alternativas = [
        MenuAlternativa(plato_id=platos["Asado con puré"].id),
        MenuAlternativa(plato_id=platos["Tallarín rojo"].id),
        MenuAlternativa(plato_id=platos["Bistec frito"].id, recargo=2.0),
    ]
    t3 = MenuTiempo(orden=3, rotulo="Refresco", obligatorio=True)
    t3.alternativas = [MenuAlternativa(plato_id=platos["Chicha morada"].id)]
    plantilla.tiempos = [t1, t2, t3]
    db.add(plantilla)
    db.commit()

    return {
        "menu_id": plantilla.id,
        "platos": {nombre: p.id for nombre, p in platos.items()},
    }


def pedir_menu(client, fonda, **kwargs):
    base = {
        "menu_id": fonda["menu_id"],
        "cantidad": 1,
        "elecciones": {
            "1": fonda["platos"]["Sopa criolla"],
            "2": fonda["platos"]["Asado con puré"],
        },
        "entrega": None,  # se saca abajo
    }
    base.pop("entrega")
    base.update(kwargs.pop("menu", {}))
    payload = {"menus": [base], "entrega": "separado", **kwargs}
    return client.post("/api/orders", json=payload)


def test_menu_today_expone_menus(client, fonda):
    data = client.get("/api/menu/today").json()
    assert len(data["menus"]) == 1
    menu = data["menus"][0]
    assert menu["nombre"] == "Menú del día" and menu["precio"] == 11.0
    rotulos = [t["rotulo"] for t in menu["tiempos"]]
    assert rotulos == ["Entrada o sopa", "Segundo", "Refresco"]
    # El refresco tiene UNA alternativa: la terminal lo muestra como incluido
    assert len(menu["tiempos"][2]["alternativas"]) == 1
    assert menu["tiempos"][0]["precio_extra"] == 3.0
    # El bistec expone su recargo y que sale al momento
    bistec = next(a for a in menu["tiempos"][1]["alternativas"] if a["nombre"] == "Bistec frito")
    assert bistec["recargo"] == 2.0 and bistec["sale_al_momento"] is True


def test_total_sin_doble_cobro(client, fonda):
    r = pedir_menu(client, fonda)
    assert r.status_code == 201
    orden = r.json()["orden"]
    # Se cobra el MENÚ (11.00), no la suma de los platos (6+10+3.5)
    assert orden["total"] == 11.0
    assert orden["items"] == []  # nada a la carta
    menu = orden["menus"][0]
    assert menu["precio"] == 11.0 and menu["subtotal"] == 11.0
    nombres = [i["nombre"] for i in menu["items"]]
    # El refresco entró solo (única alternativa = incluido)
    assert nombres == ["Sopa criolla", "Asado con puré", "Chicha morada"]
    assert all(i["precio"] == 0.0 for i in menu["items"])


def test_entrada_extra_al_precio_configurado(client, fonda):
    r = pedir_menu(client, fonda, menu={
        "extras": [{"tiempo_orden": 1, "plato_id": fonda["platos"]["Papa a la huancaína"],
                    "cantidad": 1}],
    })
    assert r.status_code == 201
    orden = r.json()["orden"]
    assert orden["total"] == 14.0  # 11 del menú + 3 de la entrada extra
    extra = next(i for i in orden["menus"][0]["items"] if i["es_extra"])
    assert extra["nombre"] == "Papa a la huancaína" and extra["precio"] == 3.0


def test_extra_de_tiempo_sin_precio_configurado_es_422(client, fonda):
    r = pedir_menu(client, fonda, menu={
        "extras": [{"tiempo_orden": 2, "plato_id": fonda["platos"]["Tallarín rojo"],
                    "cantidad": 1}],
    })
    assert r.status_code == 422
    assert "extra" in r.json()["detail"].lower()


def test_recargo_de_alternativa(client, fonda):
    r = pedir_menu(client, fonda, menu={
        "elecciones": {"1": fonda["platos"]["Sopa criolla"],
                       "2": fonda["platos"]["Bistec frito"]},
    })
    assert r.status_code == 201
    orden = r.json()["orden"]
    assert orden["total"] == 13.0  # 11 + 2 de recargo del bistec
    bistec = next(i for i in orden["menus"][0]["items"] if i["nombre"] == "Bistec frito")
    assert bistec["precio"] == 2.0


def test_plato_al_momento_en_menu_rechaza_junto(client, fonda):
    r = pedir_menu(client, fonda, menu={
        "elecciones": {"1": fonda["platos"]["Sopa criolla"],
                       "2": fonda["platos"]["Bistec frito"]},
    }, entrega="junto")
    assert r.status_code == 422
    assert "Bistec frito" in r.json()["detail"]


def test_eleccion_fuera_de_alternativas_es_422(client, fonda):
    r = pedir_menu(client, fonda, menu={
        "elecciones": {"1": fonda["platos"]["Tallarín rojo"],  # un segundo de entrada: no
                       "2": fonda["platos"]["Asado con puré"]},
    })
    assert r.status_code == 422


def test_tiempo_obligatorio_sin_eleccion_es_422(client, fonda):
    r = pedir_menu(client, fonda, menu={
        "elecciones": {"1": fonda["platos"]["Sopa criolla"]},  # falta el segundo
    })
    assert r.status_code == 422
    assert "Segundo" in r.json()["detail"]


def test_menu_desactivado_es_409(client, db, fonda):
    plantilla = db.get(MenuPlantilla, fonda["menu_id"])
    plantilla.activo_hoy = False
    db.commit()
    assert pedir_menu(client, fonda).status_code == 409


def test_plato_elegido_agotado_es_409(client, db, fonda):
    db.get(Plato, fonda["platos"]["Asado con puré"]).activo_hoy = False
    db.commit()
    r = pedir_menu(client, fonda)
    assert r.status_code == 409


def test_refresco_agotado_esconde_el_menu(client, db, fonda):
    # El único refresco se agota: el tiempo obligatorio queda vacío y el
    # menú deja de ofrecerse (y de venderse)
    db.get(Plato, fonda["platos"]["Chicha morada"]).activo_hoy = False
    db.commit()
    assert client.get("/api/menu/today").json()["menus"] == []
    assert pedir_menu(client, fonda).status_code == 409


def test_menu_y_carta_juntos(client, fonda):
    r = client.post("/api/orders", json={
        "menus": [{
            "menu_id": fonda["menu_id"], "cantidad": 1,
            "elecciones": {"1": fonda["platos"]["Sopa criolla"],
                           "2": fonda["platos"]["Asado con puré"]},
        }],
        "items": [{"plato_id": fonda["platos"]["Chicha morada"], "cantidad": 1}],
        "entrega": "separado",
    })
    assert r.status_code == 201
    orden = r.json()["orden"]
    assert orden["total"] == 14.5  # 11 del menú + 3.50 de la chicha a la carta
    assert len(orden["items"]) == 1 and orden["items"][0]["precio"] == 3.5


def test_dos_menus_multiplican(client, fonda):
    r = pedir_menu(client, fonda, menu={"cantidad": 2})
    orden = r.json()["orden"]
    assert orden["total"] == 22.0
    assert all(i["cantidad"] == 2 for i in orden["menus"][0]["items"] if not i["es_extra"])


def test_empaque_del_menu_deriva_servicio(client, fonda):
    r = pedir_menu(client, fonda, menu={"empaque": "taper"})
    assert r.json()["orden"]["tipo_servicio"] == "llevar"


def test_snapshot_de_precio_del_menu(client, db, fonda):
    pedir_menu(client, fonda)
    plantilla = db.get(MenuPlantilla, fonda["menu_id"])
    plantilla.precio = 99.0
    db.commit()
    hoy = client.get("/api/orders/today").json()
    assert hoy["ordenes"][0]["menus"][0]["precio"] == 11.0
    assert hoy["total_vendido"] == 11.0


def test_orden_sin_items_ni_menus_es_422(client, fonda):
    assert client.post("/api/orders", json={"items": [], "menus": []}).status_code == 422


def test_stats_y_csv_incluyen_el_menu(client, admin_headers, fonda):
    pedir_menu(client, fonda, menu={
        "extras": [{"tiempo_orden": 1, "plato_id": fonda["platos"]["Sopa criolla"],
                    "cantidad": 1}],
    })
    stats = client.get("/api/stats/today", headers=admin_headers).json()
    menu = next(v for v in stats["ventas_por_plato"] if v["nombre"] == "Menú del día")
    assert menu["cantidad"] == 1 and menu["total"] == 11.0
    assert stats["total_vendido"] == 14.0

    csv_texto = client.get("/api/stats/export", headers=admin_headers).text
    lineas = csv_texto.splitlines()
    assert ";menu;" in lineas[0]
    assert any(";Menú del día;Menú del día;" in l for l in lineas)  # la línea del menú
    assert any("Sopa criolla (extra)" in l for l in lineas)


def test_crud_de_plantillas_requiere_admin(client, fonda):
    assert client.get("/api/menu/plantillas").status_code == 401
    assert client.put("/api/menu/plantillas", json={"plantillas": []}).status_code == 401


def test_crud_de_plantillas(client, admin_headers, fonda):
    data = client.get("/api/menu/plantillas", headers=admin_headers).json()
    assert len(data["plantillas"]) == 1

    # Editar precio y quitar el tiempo del refresco
    plantilla = data["plantillas"][0]
    payload = {"plantillas": [{
        "id": plantilla["id"],
        "nombre": "Menú ejecutivo",
        "precio": 12.5,
        "activo_hoy": True,
        "tiempos": [
            {"rotulo": t["rotulo"], "obligatorio": t["obligatorio"],
             "precio_extra": t["precio_extra"],
             "alternativas": [{"plato_id": a["plato_id"], "recargo": a["recargo"]}
                              for a in t["alternativas"]]}
            for t in plantilla["tiempos"][:2]
        ],
    }]}
    r = client.put("/api/menu/plantillas", json=payload, headers=admin_headers)
    assert r.status_code == 200
    editada = r.json()["plantillas"][0]
    assert editada["nombre"] == "Menú ejecutivo" and editada["precio"] == 12.5
    assert len(editada["tiempos"]) == 2

    hoy = client.get("/api/menu/today").json()
    assert hoy["menus"][0]["nombre"] == "Menú ejecutivo"

    # Lista vacía = retirar del catálogo: desaparece de la terminal
    r = client.put("/api/menu/plantillas", json={"plantillas": []}, headers=admin_headers)
    assert r.json()["plantillas"] == []
    assert client.get("/api/menu/today").json()["menus"] == []


def test_historico_sobrevive_a_borrar_la_plantilla(client, admin_headers, db, fonda):
    orden_id = pedir_menu(client, fonda).json()["orden"]["id"]
    client.put("/api/menu/plantillas", json={"plantillas": []}, headers=admin_headers)
    hoy = client.get("/api/orders/today").json()
    assert hoy["ordenes"][0]["menus"][0]["nombre"] == "Menú del día"
    assert hoy["total_vendido"] == 11.0
