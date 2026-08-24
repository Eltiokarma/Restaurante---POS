import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import Cancelacion, ahora_lima, hoy_lima

router = APIRouter(prefix="/api/cancellations", tags=["cancellations"])


class ItemCancelado(BaseModel):
    nombre: str
    precio: float
    cantidad: int


class CancelacionIn(BaseModel):
    items: list[ItemCancelado] = Field(min_length=1)
    total: float


@router.post("", status_code=201)
def registrar(payload: CancelacionIn, db: Session = Depends(get_db)):
    """Log de pedidos cancelados durante la ventana de 30s (para análisis
    del dueño). No toca la tabla de órdenes."""
    ahora = ahora_lima()
    c = Cancelacion(
        fecha=ahora.date(),
        hora=ahora.strftime("%H:%M:%S"),
        items_json=json.dumps([i.model_dump() for i in payload.items], ensure_ascii=False),
        total=round(payload.total, 2),
    )
    db.add(c)
    db.commit()
    return {"ok": True}


@router.get("/today", dependencies=[Depends(requiere_admin)])
def de_hoy(db: Session = Depends(get_db)):
    cancelaciones = db.scalars(
        select(Cancelacion).where(Cancelacion.fecha == hoy_lima()).order_by(Cancelacion.id)
    ).all()
    return {
        "cancelaciones": [
            {
                "id": c.id,
                "fecha": c.fecha.isoformat(),
                "hora": c.hora,
                "items": json.loads(c.items_json),
                "total": c.total,
            }
            for c in cancelaciones
        ]
    }
