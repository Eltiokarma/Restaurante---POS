"""Cocina por bulks (§3): estado por ítem y tachar desde "Por salir".

Puntos clave: la cascada va de la orden más antigua a la más nueva, un
ítem se parte si se tachan menos porciones de las que tiene (el total de
la orden no cambia), el bulk mixto es todo o nada, y ordenes.estado es la
caché derivada = el mínimo de sus ítems.
"""
import pytest

from app.models import Insumo, Plato, RecetaItem


@pytest.fixture()
def cocina(db):
    platos = [
        Plato(nombre="Asado con puré", categoria="fondo", precio=10.0,
              activo_hoy=True, en_catalogo=True),
        Plato(nombre="Tallarín rojo", categoria="fondo", precio=10.0,
              activo_hoy=True, en_catalogo=True),
        Plato(nombre="Sopa criolla", categoria="entrada", precio=6.0,
              activo_hoy=True, en_catalogo=True),
    ]
    db.add_all(platos)
    db.commit()
    return {p.nombre: p.id for p in platos}


def crear(client, items):
    r = client.post("/api/orders", json={"items": items})
    assert r.status_code == 201
    return r.json()["orden"]


def despachar(client, lineas, destino="listo"):
    return client.post("/api/orders/despachar-bulk",
                       json={"estado_destino": destino, "lineas": lineas})


def items_de(client, orden_id):
    hoy = client.get("/api/orders/today").json()
    orden = next(o for o in hoy["ordenes"] if o["id"] == orden_id)
    return orden


def test_despacho_parcial_parte_el_item(client, cocina):
    orden = crear(client, [{"plato_id": cocina["Asado con puré"], "cantidad": 5}])

    r = despachar(client, [{"plato_nombre": "Asado con puré", "cantidad": 3}])
    assert r.status_code == 200
    cambiadas = r.json()["ordenes"]
    assert [o["id"] for o in cambiadas] == [orden["id"]]

    despues = items_de(client, orden["id"])
    estados = sorted((i["estado"], i["cantidad"]) for i in despues["items"])
    assert estados == [("listo", 3), ("pendiente", 2)]
    # El ítem partido no altera el total ni el estado derivado
    assert despues["total"] == orden["total"] == 50.0
    assert despues["estado"] == "pendiente"


def test_cascada_por_antiguedad(client, cocina):
    primera = crear(client, [{"plato_id": cocina["Asado con puré"], "cantidad": 2}])
    segunda = crear(client, [{"plato_id": cocina["Asado con puré"], "cantidad": 3}])

    r = despachar(client, [{"plato_nombre": "Asado con puré", "cantidad": 4}])
    assert r.status_code == 200

    # La más antigua sale completa; la nueva queda a medias
    assert items_de(client, primera["id"])["estado"] == "listo"
    despues = items_de(client, segunda["id"])
    assert despues["estado"] == "pendiente"
    assert sorted((i["estado"], i["cantidad"]) for i in despues["items"]) == [
        ("listo", 2), ("pendiente", 1),
    ]


def test_bulk_mixto_es_todo_o_nada(client, cocina):
    orden = crear(client, [
        {"plato_id": cocina["Asado con puré"], "cantidad": 2},
        {"plato_id": cocina["Tallarín rojo"], "cantidad": 1},
    ])

    r = despachar(client, [
        {"plato_nombre": "Asado con puré", "cantidad": 2},
        {"plato_nombre": "Tallarín rojo", "cantidad": 5},  # no alcanza
    ])
    assert r.status_code == 409
    assert "Tallarín rojo" in r.json()["detail"]

    # Nada cambió: ni siquiera los asados que sí alcanzaban
    despues = items_de(client, orden["id"])
    assert all(i["estado"] == "pendiente" for i in despues["items"])

    # El mixto válido sí avanza todo junto
    r = despachar(client, [
        {"plato_nombre": "Asado con puré", "cantidad": 2},
        {"plato_nombre": "Tallarín rojo", "cantidad": 1},
    ])
    assert r.status_code == 200
    assert items_de(client, orden["id"])["estado"] == "listo"


def test_estado_derivado_es_el_minimo(client, cocina):
    orden = crear(client, [
        {"plato_id": cocina["Asado con puré"], "cantidad": 1},
        {"plato_id": cocina["Sopa criolla"], "cantidad": 1},
    ])
    despachar(client, [{"plato_nombre": "Asado con puré", "cantidad": 1}])
    assert items_de(client, orden["id"])["estado"] == "pendiente"

    despachar(client, [{"plato_nombre": "Sopa criolla", "cantidad": 1}])
    assert items_de(client, orden["id"])["estado"] == "listo"


def test_no_retrocede_ni_cuenta_lo_avanzado(client, cocina):
    orden = crear(client, [{"plato_id": cocina["Asado con puré"], "cantidad": 2}])
    despachar(client, [{"plato_nombre": "Asado con puré", "cantidad": 2}])

    # Ya están listos: mandarlos a "preparando" no encuentra porciones
    r = despachar(client, [{"plato_nombre": "Asado con puré", "cantidad": 1}],
                  destino="preparando")
    assert r.status_code == 409
    assert items_de(client, orden["id"])["estado"] == "listo"


def test_avanzar_la_orden_arrastra_los_items(client, cocina):
    orden = crear(client, [{"plato_id": cocina["Asado con puré"], "cantidad": 2}])
    r = client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "entregado"})
    assert r.status_code == 200
    despues = items_de(client, orden["id"])
    assert all(i["estado"] == "entregado" for i in despues["items"])


def test_items_de_menu_tambien_se_tachan(client, db, cocina):
    from app.models import MenuAlternativa, MenuPlantilla, MenuTiempo

    plantilla = MenuPlantilla(nombre="Menú del día", precio=11.0,
                              activo_hoy=True, en_catalogo=True)
    t1 = MenuTiempo(orden=1, rotulo="Entrada", obligatorio=True)
    t1.alternativas = [MenuAlternativa(plato_id=cocina["Sopa criolla"])]
    t2 = MenuTiempo(orden=2, rotulo="Segundo", obligatorio=True)
    t2.alternativas = [MenuAlternativa(plato_id=cocina["Asado con puré"])]
    plantilla.tiempos = [t1, t2]
    db.add(plantilla)
    db.commit()

    r = client.post("/api/orders", json={
        "menus": [{"menu_id": plantilla.id, "cantidad": 2}], "entrega": "separado",
    })
    orden = r.json()["orden"]

    r = despachar(client, [{"plato_nombre": "Sopa criolla", "cantidad": 2}])
    assert r.status_code == 200
    despues = items_de(client, orden["id"])
    sopa = next(i for i in despues["menus"][0]["items"] if i["nombre"] == "Sopa criolla")
    assert sopa["estado"] == "listo"
    assert despues["estado"] == "pendiente"  # el segundo sigue pendiente
    assert despues["total"] == 22.0


def test_anular_tras_split_devuelve_stock_exacto(client, db, cocina, admin_headers):
    insumo = Insumo(nombre="Carne", unidad="kg", stock_actual=10.0, costo_unitario=20.0)
    db.add(insumo)
    db.flush()
    db.add(RecetaItem(plato_id=cocina["Asado con puré"], insumo_id=insumo.id, cantidad=0.25))
    db.commit()

    orden = crear(client, [{"plato_id": cocina["Asado con puré"], "cantidad": 4}])
    db.refresh(insumo)
    assert insumo.stock_actual == 9.0  # 4 × 0.25

    despachar(client, [{"plato_nombre": "Asado con puré", "cantidad": 3}])  # parte el ítem
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})
    db.refresh(insumo)
    assert insumo.stock_actual == 10.0  # devuelve EXACTO lo consumido


def test_validaciones_del_bulk(client, cocina):
    r = despachar(client, [{"plato_nombre": "Asado con puré", "cantidad": 1}],
                  destino="volando")
    assert r.status_code == 422
    r = despachar(client, [{"plato_nombre": "Asado con puré", "cantidad": 1}],
                  destino="pendiente")
    assert r.status_code == 422
    r = client.post("/api/orders/despachar-bulk", json={
        "estado_destino": "listo", "lineas": [{"cantidad": 1}],
    })
    assert r.status_code == 422


def test_config_ventana_de_tanda(client, admin_headers):
    assert client.get("/api/config").json()["cocina_bulk_min"] == 10
    r = client.put("/api/config", json={"cocina_bulk_min": 15}, headers=admin_headers)
    assert r.json()["cocina_bulk_min"] == 15
