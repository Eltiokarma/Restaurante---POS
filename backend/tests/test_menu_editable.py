"""Menú editable: quitar tiempos con descuento y agregados (+presa…)."""
import base64

import pytest

from app.models import (
    MenuAgregado, MenuAlternativa, MenuPlantilla, MenuTiempo, Plato,
)


@pytest.fixture()
def fonda(db):
    """Plantilla S/ 11 con sopa (quitar descuenta S/ 1) y agregados."""
    platos = {
        "Sopa criolla": Plato(nombre="Sopa criolla", categoria="entrada", precio=6.0,
                              activo_hoy=True, en_catalogo=True),
        "Asado con puré": Plato(nombre="Asado con puré", categoria="fondo", precio=10.0,
                                activo_hoy=True, en_catalogo=True),
        "Chicha morada": Plato(nombre="Chicha morada", categoria="bebida", precio=3.5,
                               activo_hoy=True, en_catalogo=True),
    }
    db.add_all(platos.values())
    db.flush()

    plantilla = MenuPlantilla(nombre="Menú del día", precio=11.0,
                              activo_hoy=True, en_catalogo=True)
    t1 = MenuTiempo(orden=1, rotulo="Sopa", obligatorio=True,
                    precio_extra=3.0, descuento_si_se_quita=1.0)
    t1.alternativas = [MenuAlternativa(plato_id=platos["Sopa criolla"].id)]
    t2 = MenuTiempo(orden=2, rotulo="Segundo", obligatorio=True)
    t2.alternativas = [MenuAlternativa(plato_id=platos["Asado con puré"].id)]
    t3 = MenuTiempo(orden=3, rotulo="Refresco", obligatorio=True)
    t3.alternativas = [MenuAlternativa(plato_id=platos["Chicha morada"].id)]
    plantilla.tiempos = [t1, t2, t3]
    db.add(plantilla)

    presa = MenuAgregado(nombre="Presa", precio=4.0, orden=1)
    arroz = MenuAgregado(nombre="Arroz", precio=1.5, orden=2, activo=False)  # apagado
    db.add_all([presa, arroz])
    db.commit()
    return {
        "menu_id": plantilla.id,
        "platos": {n: p.id for n, p in platos.items()},
        "presa_id": presa.id,
        "arroz_id": arroz.id,
    }


def pedir(client, fonda, **menu):
    base = {"menu_id": fonda["menu_id"], "cantidad": 1}
    base.update(menu)
    return client.post("/api/orders", json={"menus": [base], "entrega": "separado"})


def test_sin_sopa_descuenta_y_no_manda_la_sopa_a_cocina(client, fonda):
    r = pedir(client, fonda, omitidos=[1])
    assert r.status_code == 201
    orden = r.json()["orden"]
    assert orden["total"] == 10.0  # 11 − 1 de descuento

    menu = orden["menus"][0]
    assert menu["omitidos"] == [{"rotulo": "Sopa", "descuento": 1.0}]
    assert menu["subtotal"] == 10.0
    nombres = [i["nombre"] for i in menu["items"]]
    assert "Sopa criolla" not in nombres and "Asado con puré" in nombres


def test_agregados_suman_y_van_como_item(client, fonda):
    r = pedir(client, fonda, agregados=[{"agregado_id": fonda["presa_id"], "cantidad": 2}])
    assert r.status_code == 201
    orden = r.json()["orden"]
    assert orden["total"] == 19.0  # 11 + 2 presas × 4

    presa = next(i for i in orden["menus"][0]["items"] if i["nombre"] == "Presa")
    assert presa["es_agregado"] is True and presa["cantidad"] == 2 and presa["precio"] == 4.0
    assert orden["menus"][0]["subtotal"] == 19.0


def test_menu_por_dos_con_todo(client, fonda):
    r = pedir(client, fonda, cantidad=2, omitidos=[1],
              agregados=[{"agregado_id": fonda["presa_id"], "cantidad": 1}])
    # (11 − 1) × 2 + 4 = 24: el descuento es por unidad, el agregado por porción
    assert r.status_code == 201 and r.json()["orden"]["total"] == 24.0


def test_validaciones(client, fonda):
    # Quitar un tiempo que no existe
    assert pedir(client, fonda, omitidos=[9]).status_code == 422
    # Quitar y elegir a la vez el mismo tiempo
    r = pedir(client, fonda, omitidos=[1],
              elecciones={"1": fonda["platos"]["Sopa criolla"]})
    assert r.status_code == 422 and "a la vez" in r.json()["detail"]
    # Agregado apagado o inexistente
    assert pedir(client, fonda,
                 agregados=[{"agregado_id": fonda["arroz_id"], "cantidad": 1}]).status_code == 422
    assert pedir(client, fonda,
                 agregados=[{"agregado_id": 999, "cantidad": 1}]).status_code == 422


def test_descuento_mayor_que_el_menu_es_422(client, db, fonda):
    tiempo = db.scalars(
        __import__("sqlalchemy").select(MenuTiempo).where(MenuTiempo.orden == 1)
    ).first()
    tiempo.descuento_si_se_quita = 99.0
    db.commit()
    r = pedir(client, fonda, omitidos=[1])
    assert r.status_code == 422 and "negativo" in r.json()["detail"]


def test_descuento_negativo_no_se_compensa_con_agregados(client, db, fonda):
    """La guarda es por unidad de menú: un agregado no la esquiva."""
    tiempo = db.scalars(
        __import__("sqlalchemy").select(MenuTiempo).where(MenuTiempo.orden == 1)
    ).first()
    tiempo.descuento_si_se_quita = 99.0
    db.commit()
    r = pedir(client, fonda, omitidos=[1],
              agregados=[{"agregado_id": fonda["presa_id"], "cantidad": 25}])
    assert r.status_code == 422 and "negativo" in r.json()["detail"]


def test_despacho_parcial_conserva_la_marca_de_agregado(client, fonda):
    """Tachar 1 de 2 presas parte el ítem: ambas mitades siguen siendo
    agregados (cocina y ticket las destacan como +N PRESA)."""
    r = pedir(client, fonda, agregados=[{"agregado_id": fonda["presa_id"], "cantidad": 2}])
    assert r.status_code == 201

    r = client.post("/api/orders/despachar-bulk", json={
        "lineas": [{"plato_nombre": "Presa", "cantidad": 1}], "estado_destino": "listo",
    })
    assert r.status_code == 200
    items = client.get("/api/orders/today").json()["ordenes"][0]["menus"][0]["items"]
    presas = [i for i in items if i["nombre"] == "Presa"]
    assert sorted((p["cantidad"], p["estado"]) for p in presas) == [(1, "listo"), (1, "pendiente")]
    assert all(p["es_agregado"] for p in presas)


def test_menu_today_trae_descuento_y_agregados(client, fonda):
    menus = client.get("/api/menu/today").json()["menus"]
    assert menus[0]["tiempos"][0]["descuento_si_se_quita"] == 1.0
    # Solo los agregados activos
    assert menus[0]["agregados"] == [{"id": fonda["presa_id"], "nombre": "Presa", "precio": 4.0}]


def test_crud_de_agregados(client, admin_headers):
    assert client.get("/api/menu/agregados").status_code == 401

    r = client.put("/api/menu/agregados", headers=admin_headers, json={"agregados": [
        {"nombre": "Presa", "precio": 4.0},
        {"nombre": "Huevo frito", "precio": 2.0, "activo": False},
    ]})
    assert r.status_code == 200
    lista = r.json()["agregados"]
    assert [a["nombre"] for a in lista] == ["Presa", "Huevo frito"]

    # Editar precio y borrar el resto mandando la lista nueva
    r = client.put("/api/menu/agregados", headers=admin_headers, json={"agregados": [
        {"id": lista[0]["id"], "nombre": "Presa", "precio": 5.0},
    ]})
    lista = r.json()["agregados"]
    assert lista == [{"id": lista[0]["id"], "nombre": "Presa", "precio": 5.0, "activo": True}]


def test_ticket_escpos_con_sin_sopa_y_agregado(client, db, fonda):
    from app.models import Config

    db.add(Config(clave="modo_impresion", valor="puente"))
    db.add(Config(clave="impresora_ip", valor="192.168.1.77"))
    db.commit()

    r = pedir(client, fonda, omitidos=[1],
              agregados=[{"agregado_id": fonda["presa_id"], "cantidad": 1}])
    assert r.status_code == 201

    trabajo = client.get("/api/print/cola").json()["trabajos"][0]
    datos = base64.b64decode(trabajo["datos_b64"])
    assert b"** SIN SOPA **" in datos and b"-1.00" in datos
    assert b"** +1 PRESA **" in datos and b"4.00" in datos
    assert b"10.00" in datos     # menú con el descuento aplicado
    # La comanda impresa no lleva TOTAL ni bebidas
    assert b"TOTAL" not in datos
    assert "Chicha morada".encode("cp850") not in datos


def test_csv_marca_lo_quitado_y_los_agregados(client, admin_headers, fonda):
    pedir(client, fonda, omitidos=[1],
          agregados=[{"agregado_id": fonda["presa_id"], "cantidad": 1}])
    texto = client.get("/api/stats/export", headers=admin_headers).content.decode("utf-8-sig")
    assert "sin Sopa" in texto
    assert "Presa (agregado)" in texto
    linea_menu = next(l for l in texto.splitlines() if ";Menú del día;Menú del día;" in l)
    assert ";10.00;" in linea_menu  # precio unitario ya con descuento


def test_resumen_descuenta_lo_quitado(client, admin_headers, fonda):
    pedir(client, fonda, omitidos=[1])
    ventas = client.get("/api/stats/today", headers=admin_headers).json()["ventas_por_plato"]
    menu = next(v for v in ventas if v["nombre"] == "Menú del día")
    assert menu["total"] == 10.0


def test_empaque_por_tiempo_del_menu(client, fonda):
    """La señora de la mesa: la sopa para tomar ahí, el segundo en lonchera."""
    r = pedir(client, fonda,
              empaque="mesa",
              empaques={"2": "lonchera"},
              agregados=[{"agregado_id": fonda["presa_id"], "cantidad": 1}])
    assert r.status_code == 201
    orden = r.json()["orden"]

    items = {i["nombre"]: i for i in orden["menus"][0]["items"]}
    assert items["Sopa criolla"]["empaque"] == "mesa"
    assert items["Asado con puré"]["empaque"] == "lonchera"
    assert items["Presa"]["empaque"] == "mesa"      # agregado: empaque general
    assert orden["tipo_servicio"] == "mixto"        # parte mesa, parte llevar

    # Empaque inventado o tiempo inexistente: 422
    assert pedir(client, fonda, empaques={"2": "maletin"}).status_code == 422
    assert pedir(client, fonda, empaques={"9": "taper"}).status_code == 422


def test_taper_cuesta_un_sol_mas(client, db, admin_headers, fonda, menu_ejemplo):
    """Regla del dueño: cada porción en táper suma S/ 1 como línea de cobro."""
    from app.models import Config

    db.add(Config(clave="precio_taper", valor="1"))
    db.commit()

    # Menú con el segundo en táper + 2 lomos a la carta en táper
    r = client.post("/api/orders", json={
        "menus": [{"menu_id": fonda["menu_id"], "cantidad": 1, "empaques": {"2": "taper"}}],
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 2, "empaque": "taper"}],
        "entrega": "separado",
    })
    assert r.status_code == 201
    orden = r.json()["orden"]
    # 11 (menú) + 30 (2 lomos) + 3 táperes × S/ 1
    assert orden["total"] == 44.0

    cargo = next(i for i in orden["items"] if i["nombre"] == "Táper")
    assert cargo["es_cargo"] is True and cargo["cantidad"] == 3
    assert cargo["estado"] == "entregado"    # cocina no lo prepara ni lo espera
    # La orden sigue "pendiente": el cargo no adelanta el estado de cocina
    assert orden["estado"] == "pendiente"

    # Sin la config, el táper no cobra (comportamiento de siempre)
    db.delete(db.get(Config, "precio_taper")); db.commit()
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1, "empaque": "taper"}],
    })
    assert r.json()["orden"]["total"] == 15.0
    assert all(i["nombre"] != "Táper" for i in r.json()["orden"]["items"])


def test_config_de_empaques_y_precio_taper(client, admin_headers):
    config = client.get("/api/config").json()
    assert config["precio_taper"] == 0
    assert config["empaques_ofrecidos"] == ["mesa", "taper", "bolsa", "lonchera"]

    r = client.put("/api/config", json={
        "precio_taper": 1, "empaques_ofrecidos": ["taper", "maletin"],
    }, headers=admin_headers)
    datos = r.json()
    assert datos["precio_taper"] == 1
    # mesa siempre va; lo inventado se descarta
    assert datos["empaques_ofrecidos"] == ["mesa", "taper"]


def test_los_items_dicen_su_categoria(client, fonda):
    """Cocina esconde las bebidas: cada ítem dice de qué categoría es."""
    r = pedir(client, fonda, agregados=[{"agregado_id": fonda["presa_id"], "cantidad": 1}])
    assert r.status_code == 201

    orden = client.get("/api/orders/today").json()["ordenes"][0]
    categorias = {i["nombre"]: i["categoria"] for i in orden["menus"][0]["items"]}
    assert categorias["Chicha morada"] == "bebida"
    assert categorias["Asado con puré"] == "fondo"
    assert categorias["Presa"] is None  # agregado: no es plato del catálogo
