"""Bases pregrabadas del kardex: despensa de fonda y recetas sugeridas."""
from app.data.fonda_base import INSUMOS_BASE, RECETAS_BASE, buscar_receta_base, insumo_base


def test_toda_receta_base_usa_insumos_catalogados():
    faltan = {i for items in RECETAS_BASE.values() for i, _ in items if insumo_base(i) is None}
    assert faltan == set()
    assert all(c > 0 for items in RECETAS_BASE.values() for _, c in items)
    assert all(costo > 0 for _, _, costo, _ in INSUMOS_BASE)


def test_busqueda_por_nombre_de_plato():
    assert buscar_receta_base("Seco de res con frejoles")[0] == "seco de res"
    assert buscar_receta_base("Bistec a lo pobre")[0] == "bistec a lo pobre"  # gana la más larga
    assert buscar_receta_base("AJI DE GALLINA")[0] == "ají de gallina"          # sin tildes/mayúsculas
    assert buscar_receta_base("Lomo fino al jugo") is None


def test_cargar_despensa_no_duplica(client, admin_headers, db):
    from app.models import Insumo

    db.add(Insumo(nombre="arroz", unidad="saco", stock_actual=3.0))  # ya existe, distinto formato
    db.commit()

    r = client.post("/api/insumos/base/cargar", headers=admin_headers)
    assert r.status_code == 200
    assert "Arroz" not in r.json()["creados"] and len(r.json()["creados"]) == len(INSUMOS_BASE) - 1

    # Segunda vez: nada nuevo, y el arroz original quedó intacto
    assert client.post("/api/insumos/base/cargar", headers=admin_headers).json()["creados"] == []
    insumos = client.get("/api/insumos", headers=admin_headers).json()["insumos"]
    arroz = next(i for i in insumos if i["nombre"] == "arroz")
    assert arroz["unidad"] == "saco" and arroz["stock_actual"] == 3.0
    assert len(insumos) == len(INSUMOS_BASE)
    # Los creados traen costo referencial y mínimo sugerido, con stock 0
    papa = next(i for i in insumos if i["nombre"] == "Papa blanca")
    assert papa["costo_unitario"] == 2.5 and papa["stock_minimo"] == 10 and papa["stock_actual"] == 0


def test_receta_sugerida_crea_insumos_faltantes(client, admin_headers, menu_ejemplo):
    plato_id = menu_ejemplo["Lomo saltado"]
    sugerida = client.get(f"/api/insumos/recetas/{plato_id}/sugerida", headers=admin_headers).json()
    assert sugerida["encontrada"] and sugerida["base"] == "lomo saltado"
    assert all(not i["existe"] for i in sugerida["items"])  # despensa vacía

    r = client.post(f"/api/insumos/recetas/{plato_id}/sugerida", headers=admin_headers)
    assert r.status_code == 200
    receta = r.json()
    nombres = {i["insumo"] for i in receta["items"]}
    assert {"Carne de res (bistec)", "Papa blanca", "Arroz"} <= nombres
    assert receta["costo_porcion"] > 0  # con los costos referenciales ya hay margen visible

    # Los insumos se crearon solo los necesarios (no toda la despensa)
    insumos = client.get("/api/insumos", headers=admin_headers).json()["insumos"]
    assert len(insumos) == len(receta["items"])
    # Y una venta ya descuenta stock según esa receta
    client.post("/api/orders", json={"items": [{"plato_id": plato_id, "cantidad": 2}]})
    carne = next(i for i in client.get("/api/insumos", headers=admin_headers).json()["insumos"]
                 if i["nombre"] == "Carne de res (bistec)")
    assert carne["stock_actual"] == -0.3  # 2 × 0.15 kg, en rojo hasta que compre


def test_receta_sugerida_sin_coincidencia(client, admin_headers, db):
    from app.models import Plato

    plato = Plato(nombre="Especial de la casa", categoria="fondo", precio=20.0,
                  activo_hoy=True, en_catalogo=True)
    db.add(plato)
    db.commit()
    assert client.get(f"/api/insumos/recetas/{plato.id}/sugerida",
                      headers=admin_headers).json()["encontrada"] is False
    r = client.post(f"/api/insumos/recetas/{plato.id}/sugerida", headers=admin_headers)
    assert r.status_code == 404 and "ármala a mano" in r.json()["detail"]


def test_base_requiere_admin(client):
    assert client.get("/api/insumos/base").status_code == 401
    assert client.post("/api/insumos/base/cargar").status_code == 401
