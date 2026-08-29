"""Configuración compartida de los tests.

Las variables de entorno se fijan ANTES de importar la app, porque el
engine de SQLAlchemy se crea al importar app.db. Cada test corre contra
una base limpia (drop_all + create_all sobre un archivo temporal).
"""
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="pos-tests-")
os.environ["DATABASE_PATH"] = os.path.join(_TMP_DIR, "test.db")
os.environ["ADMIN_PASSWORD"] = "testpass"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app

PASSWORD = "testpass"


@pytest.fixture(autouse=True)
def base_limpia():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # El candado de apertura de caja (default de producción: encendido) se
    # apaga para los tests; los del candado lo encienden explícitamente
    from app.models import Config

    db = SessionLocal()
    db.add(Config(clave="exigir_caja_abierta", valor="0"))
    db.commit()
    db.close()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture()
def admin_headers(client):
    token = client.post("/api/admin/login", json={"password": PASSWORD}).json()["token"]
    return {"X-Admin-Token": token}


@pytest.fixture()
def menu_ejemplo(db):
    """Dos platos activos y uno agotado; devuelve {nombre: id}."""
    from app.models import Plato, hoy_lima

    platos = [
        Plato(nombre="Lomo saltado", categoria="fondo", precio=15.0, activo_hoy=True,
              en_catalogo=True, ultima_vez_activo=hoy_lima()),
        Plato(nombre="Chicha morada", categoria="bebida", precio=3.5, activo_hoy=True,
              en_catalogo=True, ultima_vez_activo=hoy_lima()),
        Plato(nombre="Seco de res", categoria="fondo", precio=14.0, activo_hoy=False,
              en_catalogo=True),
    ]
    db.add_all(platos)
    db.commit()
    return {p.nombre: p.id for p in platos}
