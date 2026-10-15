"""Servicio del estudio en Railway (separado del POS).

Al arrancar crea las tablas y siembra el dataset en la base Postgres del
estudio por la dirección INTERNA de Railway (`DATABASE_URL`), así la base
no necesita acceso público. Todo, salvo `/salud`, pide el token del
estudio (`ESTUDIO_TOKEN`, header `X-Token`): los números de Candela que se
carguen aquí son privados.
"""
from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from motor import Escenario, equilibrio, precio_minimo, simular
from motor.bd import (
    ORIGENES, TIPOS_ZONA, Base, Ciudad, Parametro, Zona, bloque, local_desde_bd, motor_bd, sembrar,
)
from motor.modelo import modelo

ENGINE = motor_bd()


@asynccontextmanager
async def ciclo(_app: FastAPI):
    Base.metadata.create_all(ENGINE)
    with Session(ENGINE) as s:
        sembrar(s)  # idempotente: no toca lo de sondeo ni lo propio
    yield


app = FastAPI(title="Estudio de rentabilidad del menú", lifespan=ciclo)


def sesion():
    with Session(ENGINE) as s:
        yield s


def requiere_token(x_token: str = Header(default="")) -> None:
    esperado = os.getenv("ESTUDIO_TOKEN", "")
    if not esperado:
        raise HTTPException(status_code=503, detail="Falta configurar ESTUDIO_TOKEN en el servicio")
    if not hmac.compare_digest(x_token.encode(), esperado.encode()):
        raise HTTPException(status_code=401, detail="Token del estudio inválido")


@app.get("/salud")
def salud(s: Session = Depends(sesion)):
    """Sin datos sensibles: solo si la base responde y cuánto tiene."""
    return {
        "ok": True,
        "ciudades": s.scalar(select(func.count()).select_from(Ciudad)),
        "parametros": s.scalar(select(func.count()).select_from(Parametro)),
        "base": ENGINE.dialect.name,
    }


PROTEGIDO = [Depends(requiere_token)]


@app.get("/ciudades", dependencies=PROTEGIDO)
def ciudades(s: Session = Depends(sesion)):
    return [{"id": c.id, "nombre": c.nombre, "confianza": c.confianza}
            for c in s.scalars(select(Ciudad).order_by(Ciudad.nombre)).all()]


@app.get("/parametros", dependencies=PROTEGIDO)
def parametros(ciudad: str | None = None, ambito: str | None = None, s: Session = Depends(sesion)):
    q = select(Parametro)
    if ciudad:
        q = q.where(Parametro.ciudad_id == ciudad)
    if ambito:
        q = q.where(Parametro.ambito == ambito)
    return [
        {k: getattr(p, k) for k in ("id", "ambito", "ciudad_id", "zona_id", "segmento", "clave", "valor",
                                    "rango_min", "rango_max", "origen", "fuente", "url", "fecha", "confianza")}
        for p in s.scalars(q.order_by(Parametro.ambito, Parametro.ciudad_id, Parametro.clave)).all()
    ]


class ZonaIn(BaseModel):
    ciudad_id: str
    nombre: str = Field(min_length=1, max_length=80)
    tipo: str = "otro"
    notas: str | None = None


@app.post("/zonas", dependencies=PROTEGIDO, status_code=201)
def crear_zona(z: ZonaIn, s: Session = Depends(sesion)):
    if s.get(Ciudad, z.ciudad_id) is None:
        raise HTTPException(status_code=404, detail="Ciudad no encontrada")
    if z.tipo not in TIPOS_ZONA:
        raise HTTPException(status_code=422, detail=f"Tipo de zona: {', '.join(TIPOS_ZONA)}")
    zona = Zona(**z.model_dump())
    s.add(zona)
    s.commit()
    return {"id": zona.id, **z.model_dump()}


class ParametroIn(BaseModel):
    """Cargar una cifra de sondeo o propia (p. ej. el precio en el centro
    de Juliaca, o el alquiler real de Candela). Las del dataset se cargan
    solas al arrancar."""
    ambito: str = Field(pattern="^(ciudad|zona)$")
    ciudad_id: str | None = None
    zona_id: int | None = None
    segmento: str | None = Field(default=None, pattern="^(popular|ejecutivo)$")
    clave: str = Field(min_length=1, max_length=60)
    valor: float
    rango_min: float | None = None
    rango_max: float | None = None
    origen: str
    fuente: str = Field(min_length=1)
    url: str | None = None
    fecha: date | None = None
    confianza: str | None = None


@app.post("/parametros", dependencies=PROTEGIDO, status_code=201)
def cargar_parametro(p: ParametroIn, s: Session = Depends(sesion)):
    if p.origen not in ("sondeo", "propio", "observado", "supuesto"):
        raise HTTPException(status_code=422, detail="Origen: sondeo, propio, observado o supuesto")
    clave = dict(ambito=p.ambito, ciudad_id=p.ciudad_id, zona_id=p.zona_id, segmento=p.segmento, clave=p.clave)
    existente = s.scalar(select(Parametro).filter_by(**clave))
    if existente is None:
        existente = Parametro(**clave)
        s.add(existente)
    for k, v in p.model_dump().items():
        setattr(existente, k, v)
    existente.fecha = p.fecha or date.today()
    s.commit()
    return {"id": existente.id}


class EscenarioIn(BaseModel):
    ciudad_id: str
    zona_id: int | None = None
    segmento: str = Field(default="popular", pattern="^(popular|ejecutivo)$")
    anio: int = Field(default=2026, ge=2026, le=2028)
    formal: bool = True
    balones: float = Field(default=5, ge=0, le=40)
    sueldo_dueno: bool = True
    q: float = Field(default=100, ge=5, le=600)  # menús/día de referencia
    precio: float | None = Field(default=None, gt=0)  # corrige el precio solo para esta corrida


@app.post("/calcular", dependencies=PROTEGIDO)
def calcular(e: EscenarioIn, s: Session = Depends(sesion)):
    """Equilibrio, frontera de precio, estado de resultados a q y Monte Carlo."""
    if s.get(Ciudad, e.ciudad_id) is None:
        raise HTTPException(status_code=404, detail="Ciudad no encontrada")
    local = local_desde_bd(s, e.ciudad_id, e.segmento, e.zona_id)
    if e.precio is not None:
        local = local.con(precio=e.precio, precio_propio=True)
    esc = Escenario(segmento=e.segmento, anio=e.anio, formal=e.formal, balones=e.balones,
                    sueldo_dueno=e.sueldo_dueno)
    nacional, riesgo = bloque(s, "nacional"), bloque(s, "riesgo")
    m = modelo(local, e.q, esc, nacional)
    mc = simular(local, esc, nacional, riesgo, q_ref=e.q)
    return {
        "local": {k: getattr(local, k) for k in ("precio", "pmin", "pmax", "insumos", "alquiler_mes",
                                                  "sueldo_cocinero", "sueldo_ayudante", "sueldo_mozo",
                                                  "gas_balon45", "servicios_mes", "precio_propio")},
        "equilibrio_menus_dia": equilibrio(local, esc, nacional),
        "precio_minimo_a_q": round(precio_minimo(local, e.q, esc, nacional), 2),
        "mes_a_q": {"ventas": round(m.ventas, 2), "fijos": round(m.fijos, 2), "utilidad": round(m.util, 2),
                    "margen": round(m.margen, 4), "cocina": m.cocina, "mozos": m.mozos},
        "anio_montecarlo": {"prob_perdida": mc.prob_perdida, "p10": round(mc.p10), "p50": round(mc.p50),
                            "p90": round(mc.p90)},
    }


__all__ = ["app", "ORIGENES"]
