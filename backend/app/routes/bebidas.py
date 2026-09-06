"""Lista fija de bebidas embotelladas (gaseosas) que vende la caja.

No son platos: no pasan por cocina ni por el menú del día. La caja las
agrega a una orden ya creada (POST /api/orders/{id}/bebidas) y cada una
puede descontar botellas del kardex vía su insumo ligado.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import Bebida, Insumo

router = APIRouter(prefix="/api/bebidas", tags=["bebidas"])


def _a_dict(b: Bebida) -> dict:
    return {
        "id": b.id,
        "nombre": b.nombre,
        "precio": b.precio,
        "activa": b.activa,
        "insumo_id": b.insumo_id,
    }


@router.get("")
def listar_bebidas(db: Session = Depends(get_db)):
    """Todas las bebidas (la caja usa las activas; el admin las ve todas)."""
    bebidas = db.scalars(select(Bebida).order_by(Bebida.nombre)).all()
    return {"bebidas": [_a_dict(b) for b in bebidas]}


class BebidaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    precio: float = Field(gt=0)


def _insumo_para(db: Session, nombre: str) -> Insumo:
    """Insumo que descuenta el kardex: se reusa por nombre o se crea en
    "unidad" con costo 0 (se aprende de la primera compra)."""
    limpio = nombre.strip()
    existente = db.scalars(select(Insumo)).all()
    for i in existente:
        if i.nombre.strip().lower() == limpio.lower():
            return i
    insumo = Insumo(nombre=limpio, unidad="unidad", stock_actual=0.0,
                    stock_minimo=0.0, costo_unitario=0.0)
    db.add(insumo)
    db.flush()
    return insumo


@router.post("", dependencies=[Depends(requiere_admin)], status_code=201)
def crear_bebida(payload: BebidaIn, db: Session = Depends(get_db)):
    nombre = payload.nombre.strip()
    repetida = any(
        b.nombre.strip().lower() == nombre.lower()
        for b in db.scalars(select(Bebida)).all()
    )
    if repetida:
        raise HTTPException(status_code=409, detail=f'"{nombre}" ya está en la lista')
    insumo = _insumo_para(db, nombre)
    bebida = Bebida(nombre=nombre, precio=round(payload.precio, 2), insumo_id=insumo.id)
    db.add(bebida)
    db.commit()
    return _a_dict(bebida)


class BebidaPatch(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    precio: float | None = Field(default=None, gt=0)
    activa: bool | None = None


@router.patch("/{bebida_id}", dependencies=[Depends(requiere_admin)])
def editar_bebida(bebida_id: int, payload: BebidaPatch, db: Session = Depends(get_db)):
    bebida = db.get(Bebida, bebida_id)
    if bebida is None:
        raise HTTPException(status_code=404, detail="Bebida no encontrada")
    if payload.nombre is not None:
        bebida.nombre = payload.nombre.strip()
    if payload.precio is not None:
        bebida.precio = round(payload.precio, 2)
    if payload.activa is not None:
        bebida.activa = payload.activa
    db.commit()
    return _a_dict(bebida)


@router.delete("/{bebida_id}", dependencies=[Depends(requiere_admin)])
def borrar_bebida(bebida_id: int, db: Session = Depends(get_db)):
    """Se borra de la lista; lo ya vendido no cambia (los items guardan
    snapshot) y el insumo del kardex queda por si se recrea."""
    bebida = db.get(Bebida, bebida_id)
    if bebida is None:
        raise HTTPException(status_code=404, detail="Bebida no encontrada")
    db.delete(bebida)
    db.commit()
    return {"borrada": True}
