"""Menús guardados por día: guardar el de hoy y recargarlo otro día."""


def armar_menu_de_hoy(client, admin_headers):
    r = client.put("/api/menu/today", json={"platos": [
        {"nombre": "Sopa", "categoria": "entrada", "precio": 6.0},
        {"nombre": "Ají de gallina", "categoria": "fondo", "precio": 13.0},
    ]}, headers=admin_headers)
    platos = {p["nombre"]: p["id"] for p in r.json()["platos"]}
    client.put("/api/menu/plantillas", json={"plantillas": [{
        "nombre": "Menú del día", "precio": 11.0, "activo_hoy": True,
        "tiempos": [
            {"rotulo": "Entrada", "alternativas": [{"plato_id": platos["Sopa"]}]},
            {"rotulo": "Segundo", "alternativas": [{"plato_id": platos["Ají de gallina"]}]},
        ],
    }]}, headers=admin_headers)
    return platos


def test_guardar_y_cargar_menu(client, admin_headers):
    armar_menu_de_hoy(client, admin_headers)

    r = client.post("/api/menu/guardados", json={"nombre": "Jueves"}, headers=admin_headers)
    assert r.status_code == 201
    guardado = r.json()["guardados"][0]
    assert guardado["nombre"] == "Jueves" and guardado["cuantos_platos"] == 2
    assert "Sopa" in guardado["resumen"]

    # Otro día se carga un menú distinto: la plantilla queda sin
    # alternativas activas y no se vende ningún menú
    client.put("/api/menu/today", json={"platos": [
        {"nombre": "Lomo saltado", "categoria": "fondo", "precio": 15.0},
    ]}, headers=admin_headers)
    assert client.get("/api/menu/today").json()["menus"] == []

    # Cargar "Jueves" restaura platos Y plantilla con un toque
    r = client.post(f"/api/menu/guardados/{guardado['id']}/cargar", headers=admin_headers)
    data = r.json()
    assert {p["nombre"] for p in data["platos"]} == {"Sopa", "Ají de gallina"}
    assert len(data["menus"]) == 1 and data["menus"][0]["nombre"] == "Menú del día"
    rotulos = [t["rotulo"] for t in data["menus"][0]["tiempos"]]
    assert rotulos == ["Entrada", "Segundo"]


def test_guardar_mismo_nombre_actualiza(client, admin_headers):
    platos = armar_menu_de_hoy(client, admin_headers)
    client.post("/api/menu/guardados", json={"nombre": "Lunes"}, headers=admin_headers)

    # El mismo nombre (aunque cambie mayúsculas) actualiza, no duplica
    client.put("/api/menu/today", json={"platos": [
        {"id": platos["Sopa"], "nombre": "Sopa", "categoria": "entrada", "precio": 6.0},
    ]}, headers=admin_headers)
    r = client.post("/api/menu/guardados", json={"nombre": "lunes"}, headers=admin_headers)
    guardados = r.json()["guardados"]
    assert len(guardados) == 1 and guardados[0]["cuantos_platos"] == 1


def test_guardar_sin_platos_es_422(client, admin_headers):
    r = client.post("/api/menu/guardados", json={"nombre": "Vacío"}, headers=admin_headers)
    assert r.status_code == 422


def test_borrar_menu_guardado(client, admin_headers):
    armar_menu_de_hoy(client, admin_headers)
    r = client.post("/api/menu/guardados", json={"nombre": "Martes"}, headers=admin_headers)
    guardado_id = r.json()["guardados"][0]["id"]
    r = client.delete(f"/api/menu/guardados/{guardado_id}", headers=admin_headers)
    assert r.json()["guardados"] == []
    # Cargar uno borrado avisa claro
    assert client.post(
        f"/api/menu/guardados/{guardado_id}/cargar", headers=admin_headers
    ).status_code == 404


def test_guardados_requieren_admin(client):
    assert client.get("/api/menu/guardados").status_code == 401
    assert client.post("/api/menu/guardados", json={"nombre": "X"}).status_code == 401
    assert client.post("/api/menu/guardados/1/cargar").status_code == 401
    assert client.delete("/api/menu/guardados/1").status_code == 401
