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

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from motor import Escenario, equilibrio, precio_minimo, simular
from motor.bd import (
    ORIGENES, TIPOS_ZONA, Base, Ciudad, EscenarioGuardado, Parametro, Zona, bloque, local_desde_bd,
    motor_bd, sembrar,
)
from motor.flujo import NOMBRE_REGIMEN, REGIMENES, SUPUESTOS, Supuestos, comparar_regimenes, flujo_caja
from motor.modelo import modelo

WEB = Path(__file__).resolve().parent / "web" / "dist"

ENGINE = motor_bd()


@asynccontextmanager
async def ciclo(_app: FastAPI):
    Base.metadata.create_all(ENGINE)
    with Session(ENGINE) as s:
        sembrar(s)  # idempotente: no toca lo de sondeo ni lo propio
    yield


app = FastAPI(title="Estudio de rentabilidad del menú", lifespan=ciclo)
api = APIRouter(prefix="/api")


def sesion():
    with Session(ENGINE) as s:
        yield s


def requiere_token(x_token: str = Header(default="")) -> None:
    esperado = os.getenv("ESTUDIO_TOKEN", "")
    if not esperado:
        raise HTTPException(status_code=503, detail="Falta configurar ESTUDIO_TOKEN en el servicio")
    if not hmac.compare_digest(x_token.encode(), esperado.encode()):
        raise HTTPException(status_code=401, detail="Token del estudio inválido")


@api.get("/salud")
def salud(s: Session = Depends(sesion)):
    """Sin datos sensibles: solo si la base responde y cuánto tiene."""
    return {
        "ok": True,
        "ciudades": s.scalar(select(func.count()).select_from(Ciudad)),
        "parametros": s.scalar(select(func.count()).select_from(Parametro)),
        "base": ENGINE.dialect.name,
    }


PROTEGIDO = [Depends(requiere_token)]


@api.get("/ciudades", dependencies=PROTEGIDO)
def ciudades(s: Session = Depends(sesion)):
    zonas: dict[str, list] = {}
    for z in s.scalars(select(Zona).order_by(Zona.nombre)).all():
        zonas.setdefault(z.ciudad_id, []).append({"id": z.id, "nombre": z.nombre, "tipo": z.tipo})
    return [{"id": c.id, "nombre": c.nombre, "confianza": c.confianza, "zonas": zonas.get(c.id, [])}
            for c in s.scalars(select(Ciudad).order_by(Ciudad.nombre)).all()]


@api.get("/parametros", dependencies=PROTEGIDO)
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


@api.post("/zonas", dependencies=PROTEGIDO, status_code=201)
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


@api.post("/parametros", dependencies=PROTEGIDO, status_code=201)
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


CORREGIBLES = ("insumos", "alquiler_mes", "sueldo_cocinero", "sueldo_ayudante", "sueldo_mozo",
               "gas_balon45", "servicios_mes")


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
    # Correcciones de esta corrida (las barras del panel); no se guardan
    insumos: float | None = Field(default=None, gt=0)
    alquiler_mes: float | None = Field(default=None, ge=0)
    sueldo_cocinero: float | None = Field(default=None, ge=0)
    sueldo_ayudante: float | None = Field(default=None, ge=0)
    sueldo_mozo: float | None = Field(default=None, ge=0)
    gas_balon45: float | None = Field(default=None, ge=0)
    servicios_mes: float | None = Field(default=None, ge=0)


def _armar(e: EscenarioIn, s: Session):
    if s.get(Ciudad, e.ciudad_id) is None:
        raise HTTPException(status_code=404, detail="Ciudad no encontrada")
    local = local_desde_bd(s, e.ciudad_id, e.segmento, e.zona_id)
    if e.precio is not None:
        local = local.con(precio=e.precio, precio_propio=True)
    cambios = {k: getattr(e, k) for k in CORREGIBLES if getattr(e, k) is not None}
    if cambios:
        local = local.con(**cambios)
    esc = Escenario(segmento=e.segmento, anio=e.anio, formal=e.formal, balones=e.balones,
                    sueldo_dueno=e.sueldo_dueno)
    return local, esc, bloque(s, "nacional")


@api.post("/calcular", dependencies=PROTEGIDO)
def calcular(e: EscenarioIn, s: Session = Depends(sesion)):
    """Equilibrio, frontera de precio, estado de resultados a q, Monte Carlo
    y la curva de utilidad por volumen (para el gráfico)."""
    local, esc, nacional = _armar(e, s)
    riesgo = bloque(s, "riesgo")
    m = modelo(local, e.q, esc, nacional)
    mc = simular(local, esc, nacional, riesgo, q_ref=e.q)
    tope = int(max(200, e.q * 2))
    curva = [{"q": q, "utilidad": round(modelo(local, q, esc, nacional).util)}
             for q in range(5, tope + 1, 5)]
    return {
        "local": {k: getattr(local, k) for k in ("precio", "pmin", "pmax", "insumos", "alquiler_mes",
                                                  "sueldo_cocinero", "sueldo_ayudante", "sueldo_mozo",
                                                  "gas_balon45", "servicios_mes", "precio_propio")},
        "equilibrio_menus_dia": equilibrio(local, esc, nacional),
        "precio_minimo_a_q": round(precio_minimo(local, e.q, esc, nacional), 2),
        "mes_a_q": {"ventas": round(m.ventas, 2), "fijos": round(m.fijos, 2), "utilidad": round(m.util, 2),
                    "margen": round(m.margen, 4), "cocina": m.cocina, "mozos": m.mozos,
                    "costo_variable_menu": round(m.var_u, 2), "precio_sin_igv": round(m.p_net, 2),
                    "personal": round(m.personal, 2), "alquiler": round(m.alquiler, 2), "gas": round(m.gas, 2)},
        "anio_montecarlo": {"prob_perdida": mc.prob_perdida, "p10": round(mc.p10), "p50": round(mc.p50),
                            "p90": round(mc.p90)},
        "curva": curva,
    }


class FlujoIn(EscenarioIn):
    inversion: float = Field(default=30_000, ge=0)
    meses_arranque: int = Field(default=6, ge=0, le=36)
    arranque_desde: float = Field(default=0.4, ge=0.05, le=1)
    crecimiento_q: float = Field(default=0.0, ge=-0.2, le=0.3)
    inflacion: float = Field(default=0.025, ge=-0.05, le=0.3)
    alza_precio: float = Field(default=0.025, ge=-0.05, le=0.3)
    alza_rmv: float = Field(default=0.037, ge=0, le=0.3)
    tasa_descuento: float = Field(default=0.15, ge=0, le=1)
    regimen: str = Field(default="mype", pattern="^(" + "|".join(REGIMENES) + ")$")


@api.post("/flujo", dependencies=PROTEGIDO)
def flujo(e: FlujoIn, s: Session = Depends(sesion)):
    """Flujo de caja a 10 años del régimen elegido y la comparación de los
    cuatro regímenes con los mismos supuestos."""
    local, esc, nacional = _armar(e, s)
    sup = Supuestos(anio_inicio=2026, inversion=e.inversion, q=e.q, meses_arranque=e.meses_arranque,
                    arranque_desde=e.arranque_desde, crecimiento_q=e.crecimiento_q, inflacion=e.inflacion,
                    alza_precio=e.alza_precio, alza_rmv=e.alza_rmv, tasa_descuento=e.tasa_descuento,
                    regimen=e.regimen)
    fl = flujo_caja(local, esc, nacional, sup)
    return {
        "regimen": fl.regimen, "nombre": NOMBRE_REGIMEN[fl.regimen],
        "anios": [asdict(a) for a in fl.anios],
        "van": fl.van, "tir": fl.tir, "recupero": fl.recupero, "recupero_descontado": fl.recupero_descontado,
        "alertas": fl.alertas, "comparacion": comparar_regimenes(local, esc, nacional, sup),
        "supuestos": SUPUESTOS,
    }


class GuardadoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    datos: dict


@api.get("/escenarios", dependencies=PROTEGIDO)
def escenarios(s: Session = Depends(sesion)):
    return [{"id": g.id, "nombre": g.nombre, "datos": g.datos, "creado": g.creado.isoformat()}
            for g in s.scalars(select(EscenarioGuardado).order_by(EscenarioGuardado.nombre)).all()]


@api.post("/escenarios", dependencies=PROTEGIDO, status_code=201)
def guardar_escenario(g: GuardadoIn, s: Session = Depends(sesion)):
    """Guarda (o reemplaza, si ya existe el nombre) un juego de barras."""
    existente = s.scalar(select(EscenarioGuardado).where(EscenarioGuardado.nombre == g.nombre))
    if existente is None:
        existente = EscenarioGuardado(nombre=g.nombre)
        s.add(existente)
    existente.datos = g.datos
    s.commit()
    return {"id": existente.id}


@api.delete("/escenarios/{id_}", dependencies=PROTEGIDO, status_code=204)
def borrar_escenario(id_: int, s: Session = Depends(sesion)):
    g = s.get(EscenarioGuardado, id_)
    if g is not None:
        s.delete(g)
        s.commit()


app.include_router(api)

# El panel (React) se sirve desde el mismo servicio: sin Vercel ni CORS
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="panel")


__all__ = ["app", "ORIGENES"]
