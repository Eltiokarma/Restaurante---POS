"""Caja → Menú del día: sumar un plato de otro día al menú de hoy (pedido
del dueño: "el asado del jueves, hoy sábado")."""
import json

from app.models import MenuAlternativa, MenuGuardado, MenuPlantilla, MenuTiempo, Plato


def _menu(db):
    """Menú de hoy (sopa + bistec) y un "Jueves" guardado con el asado (+S/ 1)."""
    sopa = Plato(nombre="Sopa de casa", categoria="entrada", precio=0, activo_hoy=True, en_catalogo=True)
    bistec = Plato(nombre="Bistec", categoria="fondo", precio=0, activo_hoy=True, en_catalogo=True)
    asado = Plato(nombre="Asado de carne", categoria="fondo", precio=0, activo_hoy=False, en_catalogo=True)
    causa = Plato(nombre="Causa", categoria="entrada", precio=0, activo_hoy=False, en_catalogo=True)
    db.add_all([sopa, bistec, asado, causa])
    db.flush()
    menu = MenuPlantilla(nombre="Menú del día", precio=11, activo_hoy=True, en_catalogo=True)
    entrada = MenuTiempo(orden=1, rotulo="Entrada")
    entrada.alternativas.append(MenuAlternativa(plato_id=sopa.id, recargo=0))
    segundo = MenuTiempo(orden=2, rotulo="Segundo")
    segundo.alternativas.append(MenuAlternativa(plato_id=bistec.id, recargo=0))
    menu.tiempos += [entrada, segundo]
    db.add(menu)
    db.add(MenuGuardado(nombre="Jueves", datos_json=json.dumps({
        "platos": [asado.id],
        "plantillas": [{"nombre": "Menú del día", "precio": 11, "tiempos": [
            {"rotulo": "Segundo", "alternativas": [{"plato_id": asado.id, "recargo": 1.0}]},
        ]}],
    })))
    db.commit()
    return menu.id, {"asado": asado.id, "causa": causa.id}


def test_el_asado_del_jueves_entra_hoy(client, db):
    menu_id, ids = _menu(db)
    para_agregar = client.get("/api/menu/caja").json()["para_agregar"]
    asado = next(p for p in para_agregar if p["plato_id"] == ids["asado"])
    assert asado["dias"] == ["Jueves"] and asado["recargo"] == 1.0

    r = client.post(f"/api/menu/caja/plantillas/{menu_id}/agregar",
                    json={"plato_id": ids["asado"], "recargo": asado["recargo"]})
    assert r.status_code == 200, r.text
    segundo = next(t for t in r.json()["plantillas"][0]["tiempos"] if t["rotulo"] == "Segundo")
    nuevo = next(a for a in segundo["alternativas"] if a["plato_id"] == ids["asado"])
    assert nuevo["activo_hoy"] is True and nuevo["recargo"] == 1.0
    # El cliente ya lo ve en el menú de hoy
    hoy = client.get("/api/menu/today").json()
    assert any(a["plato_id"] == ids["asado"] for m in hoy["menus"] for t in m["tiempos"] for a in t["alternativas"])

    # Una entrada va con las entradas; repetir no la duplica
    for _ in range(2):
        r = client.post(f"/api/menu/caja/plantillas/{menu_id}/agregar", json={"plato_id": ids["causa"]})
    entrada = next(t for t in r.json()["plantillas"][0]["tiempos"] if t["rotulo"] == "Entrada")
    assert [a["plato_id"] for a in entrada["alternativas"]].count(ids["causa"]) == 1
