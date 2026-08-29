"""Menores de la Fase 5 §4: cintillo de anulada, descuadre separado y
fotos de plato."""
import io


def crear_orden(client, menu_ejemplo, nombre="Lomo saltado"):
    r = client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo[nombre], "cantidad": 1}],
    })
    assert r.status_code == 201
    return r.json()["orden"]


# ---------- Cintillo de anulada (cocina la muestra 60 s) ----------


def test_anulada_trae_hace_cuantos_segundos(client, menu_ejemplo):
    orden = crear_orden(client, menu_ejemplo)
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})

    hoy = client.get("/api/orders/today").json()
    anulada = next(o for o in hoy["ordenes"] if o["id"] == orden["id"])
    assert anulada["estado"] == "anulada"
    # Calculado en el servidor: recién anulada, segundos ≈ 0
    assert anulada["anulada_hace_seg"] is not None
    assert 0 <= anulada["anulada_hace_seg"] < 5

    # Las no anuladas no llevan el campo con valor
    activa = crear_orden(client, menu_ejemplo)
    hoy = client.get("/api/orders/today").json()
    assert next(o for o in hoy["ordenes"] if o["id"] == activa["id"])["anulada_hace_seg"] is None


def test_desanular_limpia_el_cintillo(client, menu_ejemplo):
    orden = crear_orden(client, menu_ejemplo)
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "anulada"})
    client.patch(f"/api/orders/{orden['id']}/status", json={"estado": "pendiente"})

    hoy = client.get("/api/orders/today").json()
    de_vuelta = next(o for o in hoy["ordenes"] if o["id"] == orden["id"])
    assert de_vuelta["estado"] == "pendiente"
    assert de_vuelta["anulada_hace_seg"] is None


# ---------- Descuadre con signo y magnitud separados ----------


def test_descuadre_viene_separado(client, menu_ejemplo):
    client.post("/api/caja/abrir", json={"monto_apertura": 50})
    crear_orden(client, menu_ejemplo)  # 15.00 en efectivo (sin método = efectivo)

    # Faltan 5: esperado 65, contado 60
    r = client.post("/api/caja/cerrar", json={"monto_contado": 60}).json()
    assert r["diferencia"] == -5.0
    assert r["descuadre"] == {"tipo": "falta", "monto": 5.0}

    # Sobran 2.50
    r = client.post("/api/caja/cerrar", json={"monto_contado": 67.5}).json()
    assert r["descuadre"] == {"tipo": "sobra", "monto": 2.5}

    # Exacto
    r = client.post("/api/caja/cerrar", json={"monto_contado": 65}).json()
    assert r["descuadre"] == {"tipo": "exacta", "monto": 0.0}


def test_caja_abierta_sin_descuadre(client):
    client.post("/api/caja/abrir", json={"monto_apertura": 50})
    assert client.get("/api/caja/hoy").json()["descuadre"] is None


# ---------- Fotos de plato ----------

# PNG de 1×1 válido (bytes mínimos)
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8ffff3f0005fe02fea72d1e480000000049454e44ae426082"
)


def subir_foto(client, plato_id, headers, contenido=PNG_1PX, tipo="image/png"):
    return client.post(
        f"/api/menu/platos/{plato_id}/foto",
        files={"archivo": ("foto.png", io.BytesIO(contenido), tipo)},
        headers=headers,
    )


def test_subir_foto_requiere_admin(client, menu_ejemplo):
    r = subir_foto(client, menu_ejemplo["Lomo saltado"], headers={})
    assert r.status_code == 401


def test_subir_servir_y_quitar_foto(client, admin_headers, menu_ejemplo):
    plato_id = menu_ejemplo["Lomo saltado"]
    r = subir_foto(client, plato_id, admin_headers)
    assert r.status_code == 200
    nombre = r.json()["foto"]
    assert nombre.startswith(f"plato-{plato_id}-") and nombre.endswith(".png")

    # La terminal la ve en el menú del día y la puede cargar sin auth
    platos = client.get("/api/menu/today").json()["platos"]
    lomo = next(p for p in platos if p["id"] == plato_id)
    assert lomo["foto"] == nombre
    r = client.get(f"/api/menu/fotos/{nombre}")
    assert r.status_code == 200
    assert r.content == PNG_1PX

    # Reemplazar cambia el nombre (adiós caché) y la vieja deja de servirse
    r2 = subir_foto(client, plato_id, admin_headers)
    nombre2 = r2.json()["foto"]
    assert nombre2 != nombre
    assert client.get(f"/api/menu/fotos/{nombre}").status_code == 404

    # Quitar la foto la borra del plato y del disco
    r = client.delete(f"/api/menu/platos/{plato_id}/foto", headers=admin_headers)
    assert r.json()["foto"] is None
    assert client.get(f"/api/menu/fotos/{nombre2}").status_code == 404


def test_foto_valida_tipo_y_nombre(client, admin_headers, menu_ejemplo):
    r = subir_foto(client, menu_ejemplo["Lomo saltado"], admin_headers,
                   contenido=b"hola", tipo="text/plain")
    assert r.status_code == 422
    # Nada de escaparse de la carpeta de fotos: solo se sirven nombres con
    # la forma exacta plato-<id>-<ts>.<ext> (un nombre con "/" ni siquiera
    # llega a esta ruta)
    assert client.get("/api/menu/fotos/cualquiera.png").status_code == 404
    assert client.get("/api/menu/fotos/..pos.db").status_code == 404
    r = client.get("/api/menu/fotos/..%2Fpos.db")
    assert b"SQLite" not in r.content[:100]  # jamás la base de datos


def test_foto_se_sirve_sin_pin(client, admin_headers, menu_ejemplo, monkeypatch):
    plato_id = menu_ejemplo["Lomo saltado"]
    nombre = subir_foto(client, plato_id, admin_headers).json()["foto"]

    monkeypatch.setenv("PIN_LOCAL", "1234")
    # El resto de la API exige PIN…
    assert client.get("/api/menu/today").status_code == 401
    # …pero el <img> de la foto carga igual (no puede mandar headers)
    assert client.get(f"/api/menu/fotos/{nombre}").status_code == 200
