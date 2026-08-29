"""Mesas del local: configuración (admin), ocupación y liberación (caja).

La ocupación no se guarda: se calcula desde las órdenes del día — una
mesa está ocupada si algún ticket de hoy (no anulado y no liberado) la
tiene asignada. Combinar mesas = un ticket con varias mesas.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import Mesa, Orden, hoy_lima

router = APIRouter(prefix="/api/mesas", tags=["mesas"])


class MesaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=40)


class MesaUpdate(BaseModel):
    nombre: str | None = None
    activa: bool | None = None


def ocupacion_de_hoy(db: Session) -> dict[int, list[int]]:
    """{mesa_id: [números de orden que la ocupan]} para el día de hoy."""
    ordenes = db.scalars(
        select(Orden).where(
            Orden.fecha == hoy_lima(),
            Orden.estado != "anulada",
            Orden.mesa_liberada == False,  # noqa: E712
        )
    ).all()
    ocupacion: dict[int, list[int]] = {}
    for o in ordenes:
        for mesa_id in json.loads(o.mesa_ids or "[]"):
            ocupacion.setdefault(mesa_id, []).append(o.numero_orden_dia)
    return ocupacion


@router.get("")
def listar(db: Session = Depends(get_db)):
    mesas = db.scalars(select(Mesa).order_by(Mesa.id)).all()
    ocupacion = ocupacion_de_hoy(db)
    return {"mesas": [
        {
            "id": m.id,
            "nombre": m.nombre,
            "activa": m.activa,
            "ocupada": bool(ocupacion.get(m.id)),
            "ordenes": sorted(ocupacion.get(m.id, [])),
        }
        for m in mesas
    ]}


@router.post("", status_code=201, dependencies=[Depends(requiere_admin)])
def crear(payload: MesaIn, db: Session = Depends(get_db)):
    mesa = Mesa(nombre=payload.nombre.strip())
    db.add(mesa)
    db.commit()
    return {"id": mesa.id, "nombre": mesa.nombre, "activa": mesa.activa}


@router.put("/{mesa_id}", dependencies=[Depends(requiere_admin)])
def actualizar(mesa_id: int, payload: MesaUpdate, db: Session = Depends(get_db)):
    mesa = db.get(Mesa, mesa_id)
    if mesa is None:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")
    if payload.nombre is not None:
        mesa.nombre = payload.nombre.strip()
    if payload.activa is not None:
        mesa.activa = payload.activa
    db.commit()
    return {"id": mesa.id, "nombre": mesa.nombre, "activa": mesa.activa}


@router.post("/{mesa_id}/liberar")
def liberar(mesa_id: int, db: Session = Depends(get_db)):
    """Libera la mesa: marca liberados TODOS los tickets de hoy que la
    ocupan (si un ticket combinaba varias mesas, se liberan juntas)."""
    if db.get(Mesa, mesa_id) is None:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")

    ordenes = db.scalars(
        select(Orden).where(
            Orden.fecha == hoy_lima(),
            Orden.estado != "anulada",
            Orden.mesa_liberada == False,  # noqa: E712
        )
    ).all()
    liberadas = 0
    for o in ordenes:
        if mesa_id in json.loads(o.mesa_ids or "[]"):
            o.mesa_liberada = True
            liberadas += 1
    db.commit()
    return {"mesa_id": mesa_id, "tickets_liberados": liberadas}
