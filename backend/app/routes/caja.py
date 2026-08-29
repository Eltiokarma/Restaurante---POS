"""Apertura y cierre de caja del día.

Flujo: al empezar el servicio, el cajero abre la caja con el fondo
inicial (sencillo para vueltos). Al terminar, cuenta el efectivo y
cierra: el sistema calcula lo esperado (fondo + ventas del día) y la
diferencia. Un registro por día; el cierre se puede corregir re-cerrando.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import CierreCaja, Orden, ahora_lima, hoy_lima

router = APIRouter(prefix="/api/caja", tags=["caja"])


class AperturaIn(BaseModel):
    monto_apertura: float = Field(ge=0, le=10_000)
    notas: str = ""


class CierreIn(BaseModel):
    monto_contado: float = Field(ge=0, le=100_000)
    notas: str = ""


def _ventas_de_hoy(db: Session) -> float:
    ordenes = db.scalars(select(Orden).where(Orden.fecha == hoy_lima())).all()
    return round(sum(o.total for o in ordenes if o.estado != "anulada"), 2)


def _a_dict(registro: CierreCaja | None, total_vendido: float) -> dict:
    if registro is None:
        return {"abierta": False, "cerrada": False, "total_vendido": total_vendido}
    return {
        "abierta": registro.hora_cierre is None,
        "cerrada": registro.hora_cierre is not None,
        "fecha": registro.fecha.isoformat(),
        "hora_apertura": registro.hora_apertura,
        "monto_apertura": registro.monto_apertura,
        "hora_cierre": registro.hora_cierre,
        "monto_contado": registro.monto_contado,
        "total_sistema": registro.total_sistema,
        "diferencia": registro.diferencia,
        "notas": registro.notas,
        "total_vendido": total_vendido,
    }


def _registro_de_hoy(db: Session) -> CierreCaja | None:
    return db.scalar(select(CierreCaja).where(CierreCaja.fecha == hoy_lima()))


@router.get("/hoy")
def estado_de_hoy(db: Session = Depends(get_db)):
    return _a_dict(_registro_de_hoy(db), _ventas_de_hoy(db))


@router.post("/abrir", status_code=201)
def abrir(payload: AperturaIn, db: Session = Depends(get_db)):
    if _registro_de_hoy(db) is not None:
        raise HTTPException(status_code=409, detail="La caja de hoy ya fue abierta")
    ahora = ahora_lima()
    registro = CierreCaja(
        fecha=ahora.date(),
        hora_apertura=ahora.strftime("%H:%M:%S"),
        monto_apertura=round(payload.monto_apertura, 2),
        notas=payload.notas.strip(),
    )
    db.add(registro)
    db.commit()
    return _a_dict(registro, _ventas_de_hoy(db))


@router.post("/cerrar")
def cerrar(payload: CierreIn, db: Session = Depends(get_db)):
    """Cierra la caja del día. Re-cerrar actualiza el conteo (corrección)."""
    registro = _registro_de_hoy(db)
    if registro is None:
        raise HTTPException(status_code=409, detail="La caja de hoy no está abierta todavía")

    total_vendido = _ventas_de_hoy(db)
    esperado = round(registro.monto_apertura + total_vendido, 2)
    registro.hora_cierre = ahora_lima().strftime("%H:%M:%S")
    registro.monto_contado = round(payload.monto_contado, 2)
    registro.total_sistema = total_vendido
    registro.diferencia = round(registro.monto_contado - esperado, 2)
    if payload.notas.strip():
        registro.notas = payload.notas.strip()
    db.commit()
    return _a_dict(registro, total_vendido)


@router.get("/historial", dependencies=[Depends(requiere_admin)])
def historial(db: Session = Depends(get_db)):
    """Últimos 30 cierres, para el admin."""
    registros = db.scalars(
        select(CierreCaja).order_by(CierreCaja.fecha.desc()).limit(30)
    ).all()
    return {"cierres": [_a_dict(r, r.total_sistema or 0.0) for r in registros]}
