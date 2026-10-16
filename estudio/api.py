"""Servicio del estudio en Railway (separado del POS).

Al arrancar crea las tablas y siembra el dataset en la base Postgres del
estudio por la dirección INTERNA de Railway (`DATABASE_URL`), así la base
no necesita acceso público. Todo, salvo `/salud`, pide el token del
estudio (`ESTUDIO_TOKEN`, header `X-Token`): los números de Candela que se
carguen aquí son privados.
"""
from __future__ import annotations

import hmac
import json
import os
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from dataclasses import asdict, replace
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from motor import Escenario, equilibrio, precio_minimo, simular
from motor.barrido import (
    GOLPES, NOMBRE_CALIDAD, SUPUESTOS as SUPUESTOS_BARRIDO, Factores, barrido, curvas_precio, estres,
    mezcla_desde_analisis, resumen,
)
from motor.bd import (
    Corrida, ORIGENES, TIPOS_ZONA, Base, Ciudad, EscenarioGuardado, Insumo, Parametro, Plato, RecetaItem, Zona, bloque,
    local_desde_bd, motor_bd, sembrar,
)
from motor.flujo import NOMBRE_REGIMEN, REGIMENES, SUPUESTOS, Supuestos, comparar_regimenes, flujo_caja
from motor.modelo import AREAS, MODALIDADES, TURNOS, Noche, Trabajador, modelo
from motor.personal import calendario_pagos
from motor.recetas import TIPOS, InsumoR, PlatoR, analizar
from motor.sensibilidad import matriz, quiebres, tornado

WEB = Path(__file__).resolve().parent / "web" / "dist"
ARQUETIPOS = Path(__file__).resolve().parent / "data" / "arquetipos.json"


def sembrar_arquetipos(s: Session) -> None:
    """Los restaurantes tipo del catálogo, como escenarios guardados. Solo
    agrega los que faltan: si alguien editó uno, no se pisa."""
    existentes = set(s.scalars(select(EscenarioGuardado.nombre)).all())
    for a in json.loads(ARQUETIPOS.read_text(encoding="utf-8")):
        if a["nombre"] not in existentes:
            s.add(EscenarioGuardado(nombre=a["nombre"], datos=a["datos"]))
    s.commit()

ENGINE = motor_bd()


@asynccontextmanager
async def ciclo(_app: FastAPI):
    Base.metadata.create_all(ENGINE)
    with Session(ENGINE) as s:
        sembrar(s)  # idempotente: no toca lo de sondeo ni lo propio
        sembrar_arquetipos(s)
        # Lo que estaba corriendo cuando se reinició el servicio no va a terminar
        for c in s.scalars(select(Corrida).where(Corrida.estado.in_(("pendiente", "corriendo")))).all():
            c.estado = "interrumpida"
        s.commit()
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


class TrabajadorIn(BaseModel):
    puesto: str = Field(min_length=1, max_length=60)
    monto: float = Field(ge=0)  # sueldo del mes o jornal del día
    modalidad: str = Field(default="mensual", pattern="^(" + "|".join(MODALIDADES) + ")$")
    cantidad: int = Field(default=1, ge=0, le=50)
    area: str = Field(default="cocina", pattern="^(" + "|".join(AREAS) + ")$")
    dias: float | None = Field(default=None, ge=0, le=31)
    turno: str = Field(default="dia", pattern="^(" + "|".join(TURNOS) + ")$")


class NocheIn(BaseModel):
    q: float = Field(default=30, ge=0, le=600)
    precio: float = Field(default=12, gt=0)
    insumos: float = Field(default=4.5, gt=0)
    dias: float | None = Field(default=None, ge=1, le=31)
    balones: float = Field(default=2, ge=0, le=40)
    servicios: float = Field(default=150, ge=0)


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
    dias: float = Field(default=26, ge=1, le=31)  # días que abre al mes
    planilla: list[TrabajadorIn] = Field(default_factory=list, max_length=40)  # vacía: automática
    noche: NocheIn | None = None  # turno noche; None: solo de día


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
                    sueldo_dueno=e.sueldo_dueno, dias=e.dias,
                    planilla=tuple(Trabajador(**t.model_dump()) for t in e.planilla),
                    noche=Noche(**e.noche.model_dump()) if e.noche else None)
    return local, esc, bloque(s, "nacional")


def _equipo_dia(local, q, esc, nacional) -> tuple[int, int]:
    m = modelo(local, q, replace(esc, noche=None), nacional)
    return m.cocina, m.mozos


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
                    "personal": round(m.personal, 2), "alquiler": round(m.alquiler, 2), "gas": round(m.gas, 2),
                    "ventas_dia": round(m.ventas - m.ventas_noche, 2), "ventas_noche": round(m.ventas_noche, 2),
                    "platos_noche_mes": round(m.q_mes_noche), "contrib_noche": round(m.contrib_noche, 2),
                    "contrib_dia": round(m.contrib_u, 2)},
        "anio_montecarlo": {"prob_perdida": mc.prob_perdida, "p10": round(mc.p10), "p50": round(mc.p50),
                            "p90": round(mc.p90)},
        "curva": curva,
        "pagos": calendario_pagos(local, esc, nacional, *_equipo_dia(local, e.q, esc, nacional)),
    }


class SensibilidadIn(EscenarioIn):
    delta: float = Field(default=0.10, gt=0, le=0.5)


@api.post("/sensibilidad", dependencies=PROTEGIDO)
def sensibilidad(e: SensibilidadIn, s: Session = Depends(sesion)):
    """Qué mueve más la utilidad, cuánto aguanta cada número antes de perder
    y la tabla precio × menús/día."""
    local, esc, nacional = _armar(e, s)
    return {
        "tornado": tornado(local, esc, e.q, nacional, e.delta),
        "quiebres": quiebres(local, esc, e.q, nacional),
        "matriz": matriz(local, esc, e.q, nacional),
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


# ---------- Recetas: insumos, platos y análisis ----------

class InsumoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    unidad: str = Field(default="kg", min_length=1, max_length=20)
    precio: float = Field(ge=0)
    merma: float = Field(default=0, ge=0, lt=0.95)
    categoria: str | None = Field(default=None, max_length=30)


def _insumo_dict(i: Insumo) -> dict:
    return {"id": i.id, "nombre": i.nombre, "unidad": i.unidad, "precio": i.precio, "merma": i.merma,
            "categoria": i.categoria, "actualizado": i.actualizado.isoformat() if i.actualizado else None}


@api.get("/insumos", dependencies=PROTEGIDO)
def insumos(s: Session = Depends(sesion)):
    return [_insumo_dict(i) for i in s.scalars(select(Insumo).order_by(Insumo.nombre)).all()]


def _nombre_libre(s: Session, modelo_bd, nombre: str, propio: int | None = None):
    otro = s.scalar(select(modelo_bd).where(func.lower(modelo_bd.nombre) == nombre.strip().lower()))
    if otro is not None and otro.id != propio:
        raise HTTPException(status_code=409, detail=f"Ya existe “{otro.nombre}”")


@api.post("/insumos", dependencies=PROTEGIDO, status_code=201)
def crear_insumo(i: InsumoIn, s: Session = Depends(sesion)):
    _nombre_libre(s, Insumo, i.nombre)
    ins = Insumo(**{**i.model_dump(), "nombre": i.nombre.strip()}, actualizado=date.today())
    s.add(ins)
    s.commit()
    return _insumo_dict(ins)


@api.put("/insumos/{id_}", dependencies=PROTEGIDO)
def editar_insumo(id_: int, i: InsumoIn, s: Session = Depends(sesion)):
    ins = s.get(Insumo, id_)
    if ins is None:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")
    _nombre_libre(s, Insumo, i.nombre, id_)
    for k, v in i.model_dump().items():
        setattr(ins, k, v.strip() if k == "nombre" else v)
    ins.actualizado = date.today()
    s.commit()
    return _insumo_dict(ins)


@api.delete("/insumos/{id_}", dependencies=PROTEGIDO, status_code=204)
def borrar_insumo(id_: int, s: Session = Depends(sesion)):
    usado = s.scalar(select(func.count()).select_from(RecetaItem).where(RecetaItem.insumo_id == id_))
    if usado:
        raise HTTPException(status_code=409, detail=f"Lo usan {usado} receta(s): quítalo de ellas primero")
    ins = s.get(Insumo, id_)
    if ins is not None:
        s.delete(ins)
        s.commit()


class ItemIn(BaseModel):
    insumo_id: int
    cantidad: float = Field(gt=0)


class PlatoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    tipo: str = Field(default="segundo", pattern="^(" + "|".join(TIPOS) + ")$")
    porciones: float = Field(default=1, gt=0)
    precio: float | None = Field(default=None, gt=0)
    vendidos: float | None = Field(default=None, ge=0)
    notas: str | None = None
    items: list[ItemIn] = Field(default_factory=list, max_length=60)


def _plato_dict(p: Plato, items: list[RecetaItem]) -> dict:
    return {"id": p.id, "nombre": p.nombre, "tipo": p.tipo, "porciones": p.porciones, "precio": p.precio,
            "vendidos": p.vendidos, "notas": p.notas,
            "items": [{"insumo_id": it.insumo_id, "cantidad": it.cantidad} for it in items]}


def _items_por_plato(s: Session) -> dict[int, list[RecetaItem]]:
    salida: dict[int, list[RecetaItem]] = {}
    for it in s.scalars(select(RecetaItem).order_by(RecetaItem.id)).all():
        salida.setdefault(it.plato_id, []).append(it)
    return salida


@api.get("/platos", dependencies=PROTEGIDO)
def platos(s: Session = Depends(sesion)):
    items = _items_por_plato(s)
    return [_plato_dict(p, items.get(p.id, [])) for p in s.scalars(select(Plato).order_by(Plato.tipo, Plato.nombre)).all()]


def _guardar_plato(s: Session, plato: Plato, p: PlatoIn) -> dict:
    ids = {it.insumo_id for it in p.items}
    if ids and len(s.scalars(select(Insumo.id).where(Insumo.id.in_(ids))).all()) != len(ids):
        raise HTTPException(status_code=422, detail="La receta usa un insumo que no existe")
    for k, v in p.model_dump(exclude={"items"}).items():
        setattr(plato, k, v.strip() if k == "nombre" else v)
    s.add(plato)
    s.flush()
    for viejo in s.scalars(select(RecetaItem).where(RecetaItem.plato_id == plato.id)).all():
        s.delete(viejo)
    nuevos = [RecetaItem(plato_id=plato.id, insumo_id=it.insumo_id, cantidad=it.cantidad) for it in p.items]
    s.add_all(nuevos)
    s.commit()
    return _plato_dict(plato, nuevos)


@api.post("/platos", dependencies=PROTEGIDO, status_code=201)
def crear_plato(p: PlatoIn, s: Session = Depends(sesion)):
    _nombre_libre(s, Plato, p.nombre)
    return _guardar_plato(s, Plato(), p)


@api.put("/platos/{id_}", dependencies=PROTEGIDO)
def editar_plato(id_: int, p: PlatoIn, s: Session = Depends(sesion)):
    plato = s.get(Plato, id_)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    _nombre_libre(s, Plato, p.nombre, id_)
    return _guardar_plato(s, plato, p)


@api.delete("/platos/{id_}", dependencies=PROTEGIDO, status_code=204)
def borrar_plato(id_: int, s: Session = Depends(sesion)):
    for it in s.scalars(select(RecetaItem).where(RecetaItem.plato_id == id_)).all():
        s.delete(it)
    plato = s.get(Plato, id_)
    if plato is not None:
        s.delete(plato)
    s.commit()


@api.get("/platos/analisis", dependencies=PROTEGIDO)
def analisis_platos(igv: float = 10.5, formal: bool = True, s: Session = Depends(sesion)):
    """Costo por porción, costo del menú, margen, % de costo, clase de
    ingeniería de menú y peso de cada insumo."""
    ins = [InsumoR(i.id, i.nombre, i.unidad, i.precio, i.merma) for i in s.scalars(select(Insumo)).all()]
    items = _items_por_plato(s)
    pls = [PlatoR(p.id, p.nombre, p.tipo, p.porciones, p.precio, p.vendidos,
                  tuple((it.insumo_id, it.cantidad) for it in items.get(p.id, [])))
           for p in s.scalars(select(Plato)).all()]
    return analizar(ins, pls, igv, formal)


# ---------- Comparar negocios ----------

class CompararIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=20)


def _desde_guardado(datos: dict, s: Session):
    """Local, escenario, bloque nacional, supuestos del flujo y el FlujoIn de
    un escenario guardado (igual que si se abriera en el panel)."""
    e = FlujoIn(**{**datos.get("escenario", {}), **datos.get("supuestos", {})})
    local, esc, nacional = _armar(e, s)
    sup = Supuestos(anio_inicio=2026, inversion=e.inversion, q=e.q, meses_arranque=e.meses_arranque,
                    arranque_desde=e.arranque_desde, crecimiento_q=e.crecimiento_q, inflacion=e.inflacion,
                    alza_precio=e.alza_precio, alza_rmv=e.alza_rmv, tasa_descuento=e.tasa_descuento,
                    regimen=e.regimen)
    return local, esc, nacional, sup, e


def _metricas(datos: dict, s: Session) -> dict:
    local, esc, nacional, sup, e = _desde_guardado(datos, s)
    m = modelo(local, e.q, esc, nacional)
    mc = simular(local, esc, nacional, bloque(s, "riesgo"), q_ref=e.q)
    fl = flujo_caja(local, esc, nacional, sup)
    netas = m.ventas_netas or 1
    insumos = (m.var_u * m.q_mes + (m.p_net_noche - m.contrib_noche) * m.q_mes_noche)
    trabajadores = (sum(t.cantidad for t in esc.planilla) if esc.planilla else m.cocina + m.mozos)
    sueldo = 1500 if e.sueldo_dueno else 0
    return {
        "ventas_mes": round(m.ventas), "utilidad_mes": round(m.util), "margen": round(m.margen, 4),
        "ingreso_dueno_mes": round(m.util + sueldo),
        "equilibrio": equilibrio(local, esc, nacional),
        "precio_minimo": round(precio_minimo(local, e.q, esc, nacional), 2),
        "prob_perdida": mc.prob_perdida, "anio_malo": round(mc.p10), "anio_tipico": round(mc.p50),
        "personal_pct": round(m.personal / netas, 4), "insumos_pct": round(insumos / netas, 4),
        "alquiler_pct": round(m.alquiler / netas, 4), "trabajadores": trabajadores,
        "precio": local.precio, "menus_dia": e.q, "formal": e.formal, "noche": e.noche is not None,
        "regimen": NOMBRE_REGIMEN[e.regimen], "inversion": e.inversion,
        "van": fl.van, "tir": fl.tir, "recupero": fl.recupero, "alertas": fl.alertas,
        # Sensibilidad del caso: cuánto aguanta cada número y qué lo mueve más
        "quiebres": {q["variable"]: q["cambio"] for q in quiebres(local, esc, e.q, nacional)},
        "tornado": [{"variable": t["variable"], "nombre": t["nombre"], "rango": t["rango"]}
                    for t in tornado(local, esc, e.q, nacional, 0.10)],
    }


@api.post("/comparar", dependencies=PROTEGIDO)
def comparar(c: CompararIn, s: Session = Depends(sesion)):
    """Las mismas métricas para varios escenarios guardados, lado a lado."""
    salida = []
    for g in s.scalars(select(EscenarioGuardado).where(EscenarioGuardado.id.in_(c.ids))).all():
        try:
            metricas = _metricas(g.datos or {}, s)
        except Exception as err:  # un escenario viejo o incompleto no tumba la comparación
            salida.append({"id": g.id, "nombre": g.nombre, "error": str(err)[:200]})
            continue
        salida.append({"id": g.id, "nombre": g.nombre, "ficha": (g.datos or {}).get("ficha"), **metricas})
    orden = {i: k for k, i in enumerate(c.ids)}
    return sorted(salida, key=lambda x: orden.get(x["id"], 0))


# ---------- Corridas: cálculos largos que el servicio hace solo ----------

class FactoresIn(BaseModel):
    precio: list[float] | None = Field(default=None, max_length=15)  # cambios en soles
    calidad: list[str] | None = None
    mezcla: list[float] | None = Field(default=None, max_length=6)  # parte de segundos de res
    noche: list[bool] | None = None
    elasticidad: list[float] | None = Field(default=None, max_length=6)


class CorridaIn(BaseModel):
    tipo: str = Field(pattern="^(decisiones|decisiones_todos|estres)$")
    escenario_id: int | None = None  # decisiones
    ids: list[int] | None = None  # estrés (vacío: todos)
    factores: FactoresIn | None = None
    # Mezcla de segundos desde las recetas cargadas: solo tiene sentido para el
    # negocio dueño de esas recetas (Candela), no para los restaurantes tipo
    usar_recetas: bool = False


TOPE_COMBINACIONES = 20_000


def _correr(corrida_id: int) -> None:
    """Se ejecuta en un hilo aparte; abre su propia sesión."""
    with Session(ENGINE) as s:
        c = s.get(Corrida, corrida_id)
        c.estado = "corriendo"
        s.commit()
        cfg = c.config
        riesgo = bloque(s, "riesgo")

        def avance(x: float) -> None:
            c.progreso = round(x, 3)
            s.commit()

        try:
            if c.tipo == "decisiones":
                g = s.get(EscenarioGuardado, cfg["escenario_id"])
                local, esc, nacional, sup, e = _desde_guardado(g.datos or {}, s)
                mezcla = None
                if cfg.get("usar_recetas"):
                    mezcla = mezcla_desde_analisis(analisis_platos(10.5, True, s))
                f = Factores(**{k: v for k, v in (cfg.get("factores") or {}).items() if v})
                if mezcla and not (cfg.get("factores") or {}).get("mezcla"):
                    f.mezcla = sorted({0.25, mezcla.parte_actual, 0.75})
                if not mezcla:
                    f.mezcla = [None]
                c.total = f.total()
                s.commit()
                r = barrido(local, esc, e.q, nacional, riesgo, sup, f, mezcla, avance)
                c.resultado = {"base_nombre": g.nombre, "q0": e.q, "precio0": local.precio,
                               "factores": {"precio": f.precio, "calidad": f.calidad, "mezcla": f.mezcla,
                                            "noche": f.noche, "elasticidad": f.elasticidad},
                               **r, "curvas": curvas_precio(r)}
            elif c.tipo == "decisiones_todos":
                gs = s.scalars(select(EscenarioGuardado).order_by(EscenarioGuardado.nombre)).all()
                if cfg.get("ids"):
                    gs = [g for g in gs if g.id in cfg["ids"]]
                mezcla_propia = mezcla_desde_analisis(analisis_platos(10.5, True, s)) if cfg.get("usar_recetas") else None
                f0 = Factores()
                c.total = len(gs) * f0.total() * 3
                s.commit()
                negocios = []
                for k, g in enumerate(gs):
                    try:
                        local, esc, nacional, sup, e = _desde_guardado(g.datos or {}, s)
                        # las recetas cargadas son de Candela: solo a ella se le prueba la mezcla
                        mz = mezcla_propia if (mezcla_propia and g.nombre.startswith("Candela")) else None
                        f = Factores(mezcla=sorted({0.25, mz.parte_actual, 0.75}) if mz else [None])
                        r = barrido(local, esc, e.q, nacional, riesgo, sup, f, mz,
                                    lambda x, k=k: avance((k + x) / len(gs)))
                        negocios.append({"id": g.id, "nombre": g.nombre, "precio0": local.precio, "q0": e.q,
                                         "categoria": ((g.datos or {}).get("ficha") or {}).get("categoria"),
                                         **resumen(r)})
                    except Exception as err:
                        negocios.append({"id": g.id, "nombre": g.nombre, "error": str(err)[:200]})
                f0d = Factores()
                c.resultado = {"negocios": negocios, "supuestos": SUPUESTOS_BARRIDO,
                               "factores": {"precio": f0d.precio, "calidad": f0d.calidad, "noche": f0d.noche,
                                            "elasticidad": f0d.elasticidad}}
            else:
                q = select(EscenarioGuardado).order_by(EscenarioGuardado.nombre)
                if cfg.get("ids"):
                    q = q.where(EscenarioGuardado.id.in_(cfg["ids"]))
                gs = s.scalars(q).all()
                c.total = len(gs) * len(GOLPES)
                s.commit()
                filas = []
                for k, g in enumerate(gs):
                    try:
                        local, esc, nacional, _sup, e = _desde_guardado(g.datos or {}, s)
                        filas.append({"id": g.id, "nombre": g.nombre,
                                      "categoria": ((g.datos or {}).get("ficha") or {}).get("categoria"),
                                      "golpes": estres(local, esc, e.q, nacional, riesgo)})
                    except Exception as err:  # un escenario incompleto no tumba la corrida
                        filas.append({"id": g.id, "nombre": g.nombre, "error": str(err)[:200]})
                    avance((k + 1) / len(gs))
                c.resultado = {"golpes": [{"clave": k, "nombre": n} for k, n in GOLPES], "negocios": filas}
            c.estado, c.progreso = "lista", 1.0
        except Exception as err:
            c.estado, c.error = "error", str(err)[:500]
        c.terminado = datetime.now(timezone.utc).replace(tzinfo=None)
        s.commit()


def _corrida_dict(c: Corrida, con_resultado: bool = False) -> dict:
    d = {"id": c.id, "nombre": c.nombre, "tipo": c.tipo, "estado": c.estado, "progreso": c.progreso,
         "total": c.total, "error": c.error, "creado": c.creado.isoformat(),
         "terminado": c.terminado.isoformat() if c.terminado else None}
    if con_resultado:
        d["config"], d["resultado"] = c.config, c.resultado
    return d


@api.post("/corridas", dependencies=PROTEGIDO, status_code=201)
def crear_corrida(ci: CorridaIn, s: Session = Depends(sesion)):
    """Lanza un cálculo largo en segundo plano. Se consulta con GET."""
    if s.scalar(select(func.count()).select_from(Corrida).where(Corrida.estado == "corriendo")):
        raise HTTPException(status_code=409, detail="Ya hay una corrida en marcha; espera a que termine")
    if ci.tipo == "decisiones":
        g = s.get(EscenarioGuardado, ci.escenario_id) if ci.escenario_id else None
        if g is None:
            raise HTTPException(status_code=404, detail="Elige un escenario guardado")
        if ci.factores and ci.factores.calidad and not set(ci.factores.calidad) <= set(NOMBRE_CALIDAD):
            raise HTTPException(status_code=422, detail="Calidad: economica, estandar o generosa")
        f = Factores(**{k: v for k, v in (ci.factores.model_dump() if ci.factores else {}).items() if v})
        if f.total() * 3 > TOPE_COMBINACIONES:
            raise HTTPException(status_code=422, detail="Demasiadas combinaciones: reduce los niveles")
        nombre = f"Decisiones · {g.nombre}"
    elif ci.tipo == "decisiones_todos":
        nombre = "Decisiones · todos los negocios"
    else:
        nombre = "Prueba de estrés · " + ("todos los negocios" if not ci.ids else f"{len(ci.ids)} negocios")
    c = Corrida(nombre=nombre, tipo=ci.tipo, config=ci.model_dump(), estado="pendiente")
    s.add(c)
    s.commit()
    threading.Thread(target=_correr, args=(c.id,), daemon=True).start()
    return _corrida_dict(c)


@api.get("/corridas", dependencies=PROTEGIDO)
def corridas(s: Session = Depends(sesion)):
    return [_corrida_dict(c) for c in s.scalars(select(Corrida).order_by(Corrida.id.desc()).limit(50)).all()]


@api.get("/corridas/{id_}", dependencies=PROTEGIDO)
def corrida(id_: int, s: Session = Depends(sesion)):
    c = s.get(Corrida, id_)
    if c is None:
        raise HTTPException(status_code=404, detail="Corrida no encontrada")
    return _corrida_dict(c, con_resultado=True)


@api.delete("/corridas/{id_}", dependencies=PROTEGIDO, status_code=204)
def borrar_corrida(id_: int, s: Session = Depends(sesion)):
    c = s.get(Corrida, id_)
    if c is not None and c.estado != "corriendo":
        s.delete(c)
        s.commit()


app.include_router(api)

# El panel (React) se sirve desde el mismo servicio: sin Vercel ni CORS
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="panel")


__all__ = ["app", "ORIGENES"]
