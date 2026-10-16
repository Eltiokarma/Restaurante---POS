"""Base de datos del estudio: ciudades, zonas, parámetros con su fuente y
escenarios guardados.

Funciona con `DATABASE_URL` (Postgres en Railway) o, sin ella, con un
SQLite local (`estudio.db`). Es una base APARTE de la del POS: el estudio
nunca escribe en los datos del local.

Regla del brief: ninguna cifra sin fuente o sin marca. Cada parámetro dice
su `origen`: observado | estimado | supuesto | sondeo | propio.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from sqlalchemy import (
    JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .modelo import Local, cargar_dataset

ORIGENES = ("observado", "estimado", "supuesto", "sondeo", "propio")
TIPOS_ZONA = ("mercado", "centro", "universidad", "barrio", "otro")


class Base(DeclarativeBase):
    pass


class Ciudad(Base):
    __tablename__ = "ciudades"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    confianza: Mapped[str | None] = mapped_column(String(20))
    notas: Mapped[str | None] = mapped_column(Text)
    riesgo_nota: Mapped[str | None] = mapped_column(Text)


class Zona(Base):
    """La unidad de análisis baja de ciudad a zona (mercado, centro…)."""
    __tablename__ = "zonas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ciudad_id: Mapped[str] = mapped_column(ForeignKey("ciudades.id"))
    nombre: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[str] = mapped_column(String(20), default="otro")
    notas: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("ciudad_id", "nombre"),)


class Parametro(Base):
    """Una cifra con su procedencia. `ambito`: nacional | riesgo |
    cocina_central | ciudad | zona. `segmento`: popular | ejecutivo | None."""
    __tablename__ = "parametros"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ambito: Mapped[str] = mapped_column(String(20))
    ciudad_id: Mapped[str | None] = mapped_column(ForeignKey("ciudades.id"))
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zonas.id"))
    segmento: Mapped[str | None] = mapped_column(String(12))
    clave: Mapped[str] = mapped_column(String(60))
    valor: Mapped[float | None] = mapped_column(Float)
    rango_min: Mapped[float | None] = mapped_column(Float)
    rango_max: Mapped[float | None] = mapped_column(Float)
    origen: Mapped[str] = mapped_column(String(12))
    fuente: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[date | None] = mapped_column(Date)
    confianza: Mapped[str | None] = mapped_column(String(20))
    __table_args__ = (UniqueConstraint("ambito", "ciudad_id", "zona_id", "segmento", "clave"),)


class Fuente(Base):
    __tablename__ = "fuentes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tema: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)


class EscenarioGuardado(Base):
    __tablename__ = "escenarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    datos: Mapped[dict] = mapped_column(JSON)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def motor_bd(url: str | None = None):
    url = url or os.getenv("DATABASE_URL") or "sqlite:///estudio.db"
    # Railway entrega postgres://…; SQLAlchemy 2 quiere postgresql+psycopg://
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    # pre_ping: Railway corta conexiones ociosas; sin esto la primera
    # consulta tras un rato devuelve 500
    return create_engine(url, pool_pre_ping=True)


# ---------- Siembra desde dataset.json ----------

FUENTE_DATASET = "dataset.json (sesión de investigación 15-oct-2026; detalle en docs/research_notes)"
FECHA_DATASET = date(2026, 10, 15)
# Campos de ciudad que van por segmento
POR_SEGMENTO = {"precio": "precio_{}", "insumos": "insumos_{}"}
NUMERICOS_CIUDAD = (
    "sueldo_cocinero", "sueldo_ayudante", "sueldo_mozo", "alquiler_mes", "alquiler_m2", "gas_balon45",
    "servicios_mes", "poblacion", "ingreso_promedio", "pobreza_pct", "informalidad_pct",
    "restaurantes_por_mil", "riesgo_conflicto_anual",
)


def sembrar(session: Session, data: dict | None = None) -> None:
    """Carga (o recarga) el dataset. Idempotente: borra lo sembrado de
    `dataset.json` y lo vuelve a poner; lo que vino de sondeo o es propio
    NO se toca."""
    data = data or cargar_dataset()
    for p in session.scalars(select(Parametro).where(Parametro.fuente == FUENTE_DATASET)).all():
        session.delete(p)
    session.flush()

    def param(**kw):
        kw.setdefault("fuente", FUENTE_DATASET)
        kw.setdefault("fecha", FECHA_DATASET)
        session.add(Parametro(**kw))

    for bloque in ("nacional", "riesgo", "cocina_central"):
        conf = "baja" if bloque == "cocina_central" else None
        origen = "estimado" if bloque in ("riesgo", "cocina_central") else "observado"
        for clave, valor in data[bloque].items():
            if isinstance(valor, (int, float)):
                param(ambito=bloque, clave=clave, valor=float(valor), origen=origen, confianza=conf)

    for c in data["ciudades"]:
        ciudad = session.get(Ciudad, c["id"]) or Ciudad(id=c["id"])
        ciudad.nombre, ciudad.confianza = c["nombre"], c.get("confianza")
        ciudad.notas, ciudad.riesgo_nota = c.get("notas"), c.get("riesgo_nota")
        session.add(ciudad)
        estimados = set(c.get("est_campos") or [])
        for seg in ("popular", "ejecutivo"):
            precio = f"precio_{seg}"
            rango = c.get(f"{precio}_rango") or [None, None]
            param(ambito="ciudad", ciudad_id=c["id"], segmento=seg, clave="precio", valor=c[precio],
                  rango_min=rango[0], rango_max=rango[1],
                  origen="observado" if c.get(f"{precio}_fuente") == "observado" else "estimado",
                  confianza=c.get("confianza"))
            insumos = f"insumos_{seg}"
            param(ambito="ciudad", ciudad_id=c["id"], segmento=seg, clave="insumos", valor=c[insumos],
                  origen="estimado" if insumos in estimados else "observado", confianza=c.get("confianza"))
        for clave in NUMERICOS_CIUDAD:
            if c.get(clave) is None:
                continue
            param(ambito="ciudad", ciudad_id=c["id"], clave=clave, valor=float(c[clave]),
                  origen="estimado" if clave in estimados else "observado", confianza=c.get("confianza"))

    session.query(Fuente).delete()
    for f in data["fuentes"]:
        session.add(Fuente(tema=f["tema"], url=f["url"]))
    session.commit()


def crear_y_sembrar(url: str | None = None):
    engine = motor_bd(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        sembrar(s)
    return engine


# ---------- Leer un local desde la base ----------

def _valores(session: Session, ambito: str, **filtro) -> dict:
    q = select(Parametro).where(Parametro.ambito == ambito)
    for k, v in filtro.items():
        q = q.where(getattr(Parametro, k) == v)
    return {p.clave: p for p in session.scalars(q).all()}


def local_desde_bd(session: Session, ciudad_id: str, segmento: str = "popular",
                   zona_id: int | None = None) -> Local:
    """Local de una ciudad (y zona, si la hay: lo de la zona manda sobre lo
    de la ciudad). Los parámetros `propio`/`sondeo` mandan sobre los demás
    porque se cargan en el ámbito más específico."""
    general = _valores(session, "ciudad", ciudad_id=ciudad_id, segmento=None)
    por_seg = _valores(session, "ciudad", ciudad_id=ciudad_id, segmento=segmento)
    if zona_id is not None:
        general.update(_valores(session, "zona", zona_id=zona_id, segmento=None))
        por_seg.update(_valores(session, "zona", zona_id=zona_id, segmento=segmento))
    precio = por_seg["precio"]
    return Local(
        id=ciudad_id,
        precio=precio.valor,
        pmin=precio.rango_min if precio.rango_min is not None else precio.valor,
        pmax=precio.rango_max if precio.rango_max is not None else precio.valor,
        insumos=por_seg["insumos"].valor,
        alquiler_mes=general["alquiler_mes"].valor,
        sueldo_cocinero=general["sueldo_cocinero"].valor,
        sueldo_ayudante=general["sueldo_ayudante"].valor,
        sueldo_mozo=general["sueldo_mozo"].valor,
        gas_balon45=general["gas_balon45"].valor,
        servicios_mes=general["servicios_mes"].valor,
        riesgo_conflicto_anual=general["riesgo_conflicto_anual"].valor
        if "riesgo_conflicto_anual" in general else 0.0,
        precio_propio=precio.origen in ("propio", "sondeo"),
    )


def bloque(session: Session, ambito: str) -> dict:
    """nacional / riesgo / cocina_central como dict (como en dataset.json)."""
    return {k: p.valor for k, p in _valores(session, ambito).items()}


if __name__ == "__main__":
    crear_y_sembrar()
    print("Base creada y sembrada desde dataset.json")
    print(json.dumps({"url": str(motor_bd().url).split("@")[-1]}))
