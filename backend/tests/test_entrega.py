"""Entrega junto/separado y platos que salen al momento (Fase 5, §2)."""


def marcar_al_momento(client, admin_headers, menu_ejemplo, nombre="Lomo saltado"):
    client.put("/api/menu/today", json={"platos": [{
        "id": menu_ejemplo[nombre], "nombre": nombre, "categoria": "fondo",
        "precio": 15.0, "activo_hoy": True, "sale_al_momento": True,
    }]}, headers=admin_headers)


def test_sale_al_momento_se_guarda_y_expone(client, admin_headers, menu_ejemplo):
    marcar_al_momento(client, admin_headers, menu_ejemplo)
    platos = client.get("/api/menu/today").json()["platos"]
    lomo = next(p for p in platos if p["nombre"] == "Lomo saltado")
    assert lomo["sale_al_momento"] is True


def test_entrega_default_junto(client, menu_ejemplo):
    r = client.post("/api/orders", json={"items": [
        {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1},
    ]})
    assert r.json()["orden"]["entrega"] == "junto"


def test_plato_al_momento_rechaza_junto(client, admin_headers, menu_ejemplo):
    marcar_al_momento(client, admin_headers, menu_ejemplo)
    r = client.post("/api/orders", json={
        "items": [
            {"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1},
            {"plato_id": menu_ejemplo["Chicha morada"], "cantidad": 1},
        ],
        "entrega": "junto",
    })
    assert r.status_code == 422
    assert "Lomo saltado" in r.json()["detail"]
    assert "Separado" in r.json()["detail"]

    # Separado sí pasa
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
        "entrega": "separado",
    })
    assert r.status_code == 201
    assert r.json()["orden"]["entrega"] == "separado"


def test_sin_platos_al_momento_acepta_ambas(client, menu_ejemplo):
    for entrega in ("junto", "separado"):
        r = client.post("/api/orders", json={
            "items": [{"plato_id": menu_ejemplo["Chicha morada"], "cantidad": 1}],
            "entrega": entrega,
        })
        assert r.status_code == 201


def test_entrega_invalida_es_422(client, menu_ejemplo):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
        "entrega": "volando",
    })
    assert r.status_code == 422


def test_caja_corrige_entrega_con_la_misma_regla(client, admin_headers, menu_ejemplo):
    orden_id = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
    }).json()["orden"]["id"]

    r = client.patch(f"/api/orders/{orden_id}/entrega", json={"entrega": "separado"})
    assert r.json()["entrega"] == "separado"

    # Si el plato pasa a "al momento", volver a junto se rechaza
    marcar_al_momento(client, admin_headers, menu_ejemplo)
    r = client.patch(f"/api/orders/{orden_id}/entrega", json={"entrega": "junto"})
    assert r.status_code == 422


def test_entrega_en_csv(client, admin_headers, menu_ejemplo):
    client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
        "entrega": "separado",
    })
    r = client.get("/api/stats/export", headers=admin_headers)
    assert ";entrega;" in r.text.splitlines()[0]
    assert ";separado;" in r.text
