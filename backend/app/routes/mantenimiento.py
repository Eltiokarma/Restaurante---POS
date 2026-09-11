"""Mantenimiento del sistema: empezar limpio antes de abrir al público.

Después de las pruebas queda basura en la base (pedidos falsos, cierres de
caja de prueba, movimientos de kardex). Si se abre el local así, el Resumen
y el cierre del primer día real salen contaminados. Este módulo borra SOLO
el movimiento y conserva la configuración del local.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import (
    Cancelacion,
    CierreCaja,
    EgresoCaja,
    Insumo,
    MovimientoInsumo,
    Orden,
    OrdenItem,
    OrdenMenu,
    TandaLog,
    TicketBebida,
    VozLog,
)

router = APIRouter(
    prefix="/api/mantenimiento", tags=["mantenimiento"],
    dependencies=[Depends(requiere_admin)],
)

# El dueño tiene que escribirlo tal cual: es un borrado sin vuelta atrás
PALABRA_CONFIRMACION = "BORRAR"


class ReinicioIn(BaseModel):
    confirmacion: str
    # True = además deja el stock de todos los insumos en 0 para arrancar
    # con un conteo físico real (el kardex se borra igual)
    reiniciar_stock: bool = True


@router.get("/datos")
def resumen_de_datos(db: Session = Depends(get_db)):
    """Qué hay hoy en la base, para que el admin sepa qué va a borrar."""
    return {
        "ordenes": db.scalar(select(func.count()).select_from(Orden)) or 0,
        "cancelaciones": db.scalar(select(func.count()).select_from(Cancelacion)) or 0,
        "cierres_caja": db.scalar(select(func.count()).select_from(CierreCaja)) or 0,
        "movimientos_kardex": db.scalar(select(func.count()).select_from(MovimientoInsumo)) or 0,
        "voz_logs": db.scalar(select(func.count()).select_from(VozLog)) or 0,
    }


@router.post("/reiniciar")
def reiniciar_datos(payload: ReinicioIn, db: Session = Depends(get_db)):
    """Borra el movimiento y deja el local listo para su primer día real.

    SE BORRA: órdenes (con sus ítems y menús vendidos), cancelaciones,
    aperturas y cierres de caja, kardex y logs de voz.
    SE CONSERVA: platos, menús encadenados, mesas, insumos, recetas y toda
    la configuración — o sea, nada de lo que costó configurar.
    """
    if payload.confirmacion.strip().upper() != PALABRA_CONFIRMACION:
        raise HTTPException(
            status_code=422,
            detail=f'Para borrar hay que escribir "{PALABRA_CONFIRMACION}" tal cual.',
        )

    borrado = resumen_de_datos(db)

    # Los ítems y menús vendidos van primero: cuelgan de las órdenes
    db.execute(delete(OrdenItem))
    db.execute(delete(OrdenMenu))
    db.execute(delete(Orden))
    db.execute(delete(Cancelacion))
    db.execute(delete(CierreCaja))
    db.execute(delete(MovimientoInsumo))
    db.execute(delete(VozLog))

    if payload.reiniciar_stock:
        # Sin kardex, el stock que quedaba no tiene respaldo: se parte de
        # cero y el dueño carga su conteo físico como primer movimiento
        for insumo in db.scalars(select(Insumo)).all():
            insumo.stock_actual = 0.0

    db.commit()
    return {"borrado": borrado, "stock_reiniciado": payload.reiniciar_stock}


class BorrarDiaIn(BaseModel):
    fecha: date
    confirmacion: str


@router.post("/borrar-dia")
def borrar_un_dia(payload: BorrarDiaIn, db: Session = Depends(get_db)):
    """Borra el movimiento de UN día: el de las pruebas, sin tocar el resto.

    "Reiniciar" borra todo y sirve antes de abrir; esto sirve después,
    cuando entre días reales quedó un día de prueba. Se va todo lo de ese
    día — órdenes con sus ítems y menús, tickets de gaseosas, tandas,
    cancelaciones, la caja y sus egresos — y el kardex se deshace: lo que
    esas órdenes consumieron vuelve al stock, sin dejar movimientos
    fantasma.
    """
    if payload.confirmacion.strip().upper() != PALABRA_CONFIRMACION:
        raise HTTPException(
            status_code=422,
            detail=f'Para borrar hay que escribir "{PALABRA_CONFIRMACION}" tal cual.',
        )
    fecha = payload.fecha
    ordenes = db.scalars(select(Orden).where(Orden.fecha == fecha)).all()
    ids = [o.id for o in ordenes]

    # El kardex se deshace: cada movimiento aplicó un delta al stock, así
    # que restarlo lo devuelve. Van los de ESE día y los ligados a sus
    # órdenes (una anulación posterior queda fechada en otro día).
    condiciones = [MovimientoInsumo.fecha == fecha]
    if ids:
        condiciones.append(MovimientoInsumo.orden_id.in_(ids))
    movimientos = db.scalars(select(MovimientoInsumo).where(or_(*condiciones))).all()
    for mov in movimientos:
        insumo = db.get(Insumo, mov.insumo_id)
        if insumo is not None:
            insumo.stock_actual = round(insumo.stock_actual - mov.cantidad, 4)
        db.delete(mov)

    if ids:
        db.execute(delete(TicketBebida).where(TicketBebida.orden_id.in_(ids)))
        db.execute(delete(OrdenItem).where(OrdenItem.orden_id.in_(ids)))
        db.execute(delete(OrdenMenu).where(OrdenMenu.orden_id.in_(ids)))
        db.execute(delete(Orden).where(Orden.id.in_(ids)))

    cierres = db.scalars(select(CierreCaja).where(CierreCaja.fecha == fecha)).all()
    borrado = {
        "fecha": fecha.isoformat(),
        "ordenes": len(ids),
        "ventas": round(sum(o.total for o in ordenes if o.estado != "anulada"), 2),
        "movimientos_kardex": len(movimientos),
        "cierres_caja": len(cierres),
        "egresos": db.scalar(
            select(func.count()).select_from(EgresoCaja).where(EgresoCaja.fecha == fecha)
        ) or 0,
        "cancelaciones": db.scalar(
            select(func.count()).select_from(Cancelacion).where(Cancelacion.fecha == fecha)
        ) or 0,
        "tandas": db.scalar(
            select(func.count()).select_from(TandaLog).where(TandaLog.fecha == fecha)
        ) or 0,
    }
    db.execute(delete(EgresoCaja).where(EgresoCaja.fecha == fecha))
    db.execute(delete(CierreCaja).where(CierreCaja.fecha == fecha))
    db.execute(delete(Cancelacion).where(Cancelacion.fecha == fecha))
    db.execute(delete(TandaLog).where(TandaLog.fecha == fecha))
    db.commit()
    return {"borrado": borrado}
