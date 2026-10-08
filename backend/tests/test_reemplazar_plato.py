"""Admin → Mantenimiento: cambiar un plato ya vendido por otro (se vendió
"Ensalada de Palta" y era camote) sin tocar la plata ni imprimir nada."""
from app.models import Orden, Plato
from tests.test_menu_encadenado import fonda  # noqa: F401  (fixture)


def test_reemplaza_el_plato_sin_cambiar_la_plata(client, db, fonda, admin_headers):
    p = fonda["platos"]
    camote = Plato(nombre="Camote Rebosado", categoria="entrada", precio=6.0,
                   activo_hoy=False, en_catalogo=True)
    db.add(camote)
    db.commit()
    for _ in range(2):
        client.post("/api/orders", json={"menus": [{
            "menu_id": fonda["menu_id"], "cantidad": 2,
            "elecciones": {"1": p["Papa a la huancaína"], "2": p["Asado con puré"]},
        }]})
    totales = [o.total for o in db.query(Orden).all()]

    # Sin token no
    assert client.post("/api/mantenimiento/reemplazar-plato",
                       json={"de_plato_id": p["Papa a la huancaína"], "a_plato_id": camote.id}
                       ).status_code == 401

    antes = client.get("/api/mantenimiento/platos-vendidos", headers=admin_headers).json()["platos"]
    assert {"nombre": "Papa a la huancaína", "cantidad": 4, "pedidos": 2} | {
        "plato_id": p["Papa a la huancaína"]} in antes

    r = client.post("/api/mantenimiento/reemplazar-plato", headers=admin_headers,
                    json={"de_plato_id": p["Papa a la huancaína"], "a_plato_id": camote.id})
    assert r.status_code == 200
    assert (r.json()["porciones"], r.json()["pedidos"]) == (4, 2)
    nombres = {f["nombre"] for f in r.json()["platos"]}
    assert "Camote Rebosado" in nombres and "Papa a la huancaína" not in nombres

    db.expire_all()
    assert [o.total for o in db.query(Orden).all()] == totales  # la plata no cambia
    items = [i for o in db.query(Orden).all() for i in o.items if i.plato_id == camote.id]
    assert len(items) == 2 and all(i.nombre_snapshot == "Camote Rebosado" for i in items)
    assert all(i.precio_snapshot == 0 for i in items)  # el precio cobrado se queda
    # No imprime nada: no hay tickets de cambio
    from app.models import TicketBebida
    assert db.query(TicketBebida).count() == 0


def test_mismo_plato_no(client, fonda, admin_headers):
    papa = fonda["platos"]["Papa a la huancaína"]
    r = client.post("/api/mantenimiento/reemplazar-plato", headers=admin_headers,
                    json={"de_plato_id": papa, "a_plato_id": papa})
    assert r.status_code == 422
