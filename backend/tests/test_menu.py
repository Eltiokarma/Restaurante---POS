"""Menú del día, catálogo y "cargar menú de ayer"."""
from datetime import timedelta

from app.models import Plato, hoy_lima


def test_menu_today_solo_activos(client, menu_ejemplo):
    data = client.get("/api/menu/today").json()
    nombres = [p["nombre"] for p in data["platos"]]
    assert "Lomo saltado" in nombres and "Chicha morada" in nombres
    assert "Seco de res" not in nombres  # agotado


def test_put_menu_requiere_admin(client):
    r = client.put("/api/menu/today", json={"platos": []})
    assert r.status_code == 401
    r = client.put("/api/menu/today", json={"platos": []}, headers={"X-Admin-Token": "basura"})
    assert r.status_code == 401


def test_put_menu_crea_actualiza_y_desactiva(client, admin_headers, menu_ejemplo):
    payload = {
        "platos": [
            # Actualiza precio del lomo y lo mantiene activo
            {"id": menu_ejemplo["Lomo saltado"], "nombre": "Lomo saltado", "categoria": "fondo",
             "precio": 16.0, "activo_hoy": True},
            # Plato nuevo
            {"nombre": "Mazamorra morada", "categoria": "postre", "precio": 4.0, "activo_hoy": True},
        ]
    }
    r = client.put("/api/menu/today", json=payload, headers=admin_headers)
    assert r.status_code == 200
    activos = {p["nombre"]: p for p in r.json()["platos"]}

    assert activos["Lomo saltado"]["precio"] == 16.0
    assert "Mazamorra morada" in activos
    # La chicha no vino en la lista: queda desactivada para hoy
    assert "Chicha morada" not in activos


def test_catalogo_conserva_platos_desactivados(client, admin_headers, menu_ejemplo):
    catalogo = client.get("/api/menu/catalog", headers=admin_headers).json()
    nombres = [p["nombre"] for p in catalogo["platos"]]
    assert "Seco de res" in nombres  # agotado pero en catálogo


def test_menu_anterior(client, admin_headers, db):
    ayer = hoy_lima() - timedelta(days=1)
    db.add_all([
        Plato(nombre="Ají de gallina", categoria="fondo", precio=13.0, activo_hoy=False,
              en_catalogo=True, ultima_vez_activo=ayer),
        Plato(nombre="Sopa criolla", categoria="entrada", precio=6.0, activo_hoy=False,
              en_catalogo=True, ultima_vez_activo=ayer - timedelta(days=3)),
    ])
    db.commit()

    data = client.get("/api/menu/previous", headers=admin_headers).json()
    assert data["fecha"] == ayer.isoformat()
    # Solo el menú del último día de servicio, no todo el histórico
    assert [p["nombre"] for p in data["platos"]] == ["Ají de gallina"]


def test_menu_anterior_sin_historial(client, admin_headers):
    data = client.get("/api/menu/previous", headers=admin_headers).json()
    assert data == {"fecha": None, "platos": []}
