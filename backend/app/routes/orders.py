from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from datetime import datetime, time

from ..db import get_db
from ..models import LIMA, Config, Orden, ahora_lima, hoy_lima
from ..services.orders import PlatoNoDisponible, crear_orden

router = APIRouter(prefix="/api/orders", tags=["orders"])

ESTADOS = ["pendiente", "preparando", "listo", "entregado"]


class ItemIn(BaseModel):
    plato_id: int
    cantidad: int = Field(gt=0, le=50)


class OrdenIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1)


class EstadoIn(BaseModel):
    estado: str


def _minutos_espera(orden: Orden) -> float:
    """Minutos desde que se creó la orden, calculados en el servidor para no
    depender del reloj ni la zona horaria del dispositivo de cocina."""
    h, m, s = (int(x) for x in orden.hora.split(":"))
    creada = datetime.combine(orden.fecha, time(h, m, s), tzinfo=LIMA)
    return max(0.0, (ahora_lima() - creada).total_seconds() / 60)


def _orden_a_dict(orden: Orden) -> dict:
    return {
        "id": orden.id,
        "numero_orden_dia": orden.numero_orden_dia,
        "fecha": orden.fecha.isoformat(),
        "hora": orden.hora,
        "total": orden.total,
        "estado": orden.estado,
        "minutos_espera": round(_minutos_espera(orden), 1),
        "items": [
            {
                "nombre": i.nombre_snapshot,
                "precio": i.precio_snapshot,
                "cantidad": i.cantidad,
                "subtotal": round(i.precio_snapshot * i.cantidad, 2),
            }
            for i in orden.items
        ],
    }


@router.post("", status_code=201)
def crear(payload: OrdenIn, db: Session = Depends(get_db)):
    """Guarda la orden YA CONFIRMADA (después de la ventana de cancelación).

    Devuelve el número de orden del día y los datos del local para imprimir
    el ticket.
    """
    try:
        orden = crear_orden(db, [i.model_dump() for i in payload.items])
    except PlatoNoDisponible as e:
        raise HTTPException(status_code=409, detail=f"'{e.nombre}' ya no está disponible")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    config = {c.clave: c.valor for c in db.scalars(select(Config)).all()}
    return {
        "orden": _orden_a_dict(orden),
        "local": {
            "nombre": config.get("nombre_local", ""),
            "direccion": config.get("direccion", ""),
            "ruc": config.get("ruc", ""),
        },
    }


@router.get("/today")
def ordenes_de_hoy(db: Session = Depends(get_db)):
    """Órdenes de hoy, para la vista de cocina y el admin."""
    ordenes = db.scalars(
        select(Orden)
        .options(selectinload(Orden.items))
        .where(Orden.fecha == hoy_lima())
        .order_by(Orden.numero_orden_dia)
    ).all()
    total_vendido = round(sum(o.total for o in ordenes), 2)
    return {
        "ordenes": [_orden_a_dict(o) for o in ordenes],
        "total_vendido": total_vendido,
    }


@router.patch("/{orden_id}/status")
def cambiar_estado(orden_id: int, payload: EstadoIn, db: Session = Depends(get_db)):
    if payload.estado not in ESTADOS:
        raise HTTPException(status_code=422, detail=f"Estado inválido: {payload.estado}")
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    orden.estado = payload.estado
    db.commit()
    return {"id": orden.id, "estado": orden.estado}
