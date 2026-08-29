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


def _ventas_de_hoy(db: Session) -> dict:
    """Ventas del día desglosadas por método de pago.

    Una orden sin método registrado se asume EFECTIVO (comportamiento
    histórico: si la caja no usa los botones de cobro, el cierre sigue
    cuadrando como antes).
    """
    ordenes = [
        o for o in db.scalars(select(Orden).where(Orden.fecha == hoy_lima())).all()
        if o.estado != "anulada"
    ]
    efectivo = sum(o.total for o in ordenes if o.metodo_pago in (None, "efectivo"))
    tarjeta = sum(o.total for o in ordenes if o.metodo_pago == "tarjeta")
    yape = sum(o.total for o in ordenes if o.metodo_pago == "yape")
    return {
        "total_vendido": round(efectivo + tarjeta + yape, 2),
        "ventas_efectivo": round(efectivo, 2),
        "ventas_tarjeta": round(tarjeta, 2),
        "ventas_yape": round(yape, 2),
        "sin_registrar": sum(1 for o in ordenes if o.metodo_pago is None),
    }


def _a_dict(registro: CierreCaja | None, ventas: dict) -> dict:
    base = {"abierta": False, "cerrada": False, "ventas_despues_del_cierre": False, **ventas}
    if registro is None:
        return base

    cerrada = registro.hora_cierre is not None
    if cerrada:
        # Con la caja cerrada se muestra el SNAPSHOT del cierre (lo que se
        # cuadró), no las ventas vivas: así los números son consistentes
        # con la diferencia guardada. Si llegaron ventas después, se avisa
        # para que el cajero corrija el conteo (re-cerrar).
        base.update({
            "total_vendido": registro.total_sistema or 0.0,
            # Cierres anteriores a la migración: todo su total fue efectivo
            "ventas_efectivo": (
                registro.ventas_efectivo
                if registro.ventas_efectivo is not None
                else (registro.total_sistema or 0.0)
            ),
            "ventas_tarjeta": registro.ventas_tarjeta or 0.0,
            "ventas_yape": registro.ventas_yape or 0.0,
            "ventas_despues_del_cierre": round(ventas["total_vendido"], 2)
            != round(registro.total_sistema or 0.0, 2),
        })

    return {
        **base,
        "abierta": not cerrada,
        "cerrada": cerrada,
        "fecha": registro.fecha.isoformat(),
        "hora_apertura": registro.hora_apertura,
        "monto_apertura": registro.monto_apertura,
        "hora_cierre": registro.hora_cierre,
        "monto_contado": registro.monto_contado,
        "total_sistema": registro.total_sistema,
        "diferencia": registro.diferencia,
        "notas": registro.notas,
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
    """Cierra la caja del día. El conteo de efectivo se cuadra SOLO contra
    el efectivo esperado (fondo + ventas en efectivo); tarjeta y Yape se
    reportan aparte. Re-cerrar actualiza el conteo (corrección)."""
    registro = _registro_de_hoy(db)
    if registro is None:
        raise HTTPException(status_code=409, detail="La caja de hoy no está abierta todavía")

    ventas = _ventas_de_hoy(db)
    esperado_efectivo = round(registro.monto_apertura + ventas["ventas_efectivo"], 2)
    registro.hora_cierre = ahora_lima().strftime("%H:%M:%S")
    registro.monto_contado = round(payload.monto_contado, 2)
    registro.total_sistema = ventas["total_vendido"]
    registro.ventas_efectivo = ventas["ventas_efectivo"]
    registro.ventas_tarjeta = ventas["ventas_tarjeta"]
    registro.ventas_yape = ventas["ventas_yape"]
    registro.diferencia = round(registro.monto_contado - esperado_efectivo, 2)
    if payload.notas.strip():
        registro.notas = payload.notas.strip()
    db.commit()
    return _a_dict(registro, ventas)


@router.get("/historial", dependencies=[Depends(requiere_admin)])
def historial(db: Session = Depends(get_db)):
    """Últimos 30 cierres, para el admin."""
    registros = db.scalars(
        select(CierreCaja).order_by(CierreCaja.fecha.desc()).limit(30)
    ).all()
    return {"cierres": [
        _a_dict(r, {
            "total_vendido": r.total_sistema or 0.0,
            # Cierres previos a la migración (columnas NULL): por la
            # semántica histórica, todo su total fue efectivo
            "ventas_efectivo": (
                r.ventas_efectivo if r.ventas_efectivo is not None else (r.total_sistema or 0.0)
            ),
            "ventas_tarjeta": r.ventas_tarjeta or 0.0,
            "ventas_yape": r.ventas_yape or 0.0,
            "sin_registrar": 0,
        })
        for r in registros
    ]}
