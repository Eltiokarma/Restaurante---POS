"""Insumos, recetas y kardex (todo protegido con admin)."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import Insumo, MovimientoInsumo, Plato, RecetaItem, hoy_lima
from ..services.inventario import registrar_ajuste, registrar_compra, registrar_merma

router = APIRouter(
    prefix="/api/insumos", tags=["insumos"], dependencies=[Depends(requiere_admin)]
)


class InsumoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    unidad: str = Field(min_length=1, max_length=20)
    costo_unitario: float = Field(default=0.0, ge=0)


class InsumoUpdate(BaseModel):
    nombre: str | None = None
    unidad: str | None = None
    activo: bool | None = None


class MovimientoIn(BaseModel):
    tipo: str  # compra | merma | ajuste
    cantidad: float = Field(gt=-100_000, lt=100_000)
    costo_total: float | None = Field(default=None, ge=0)
    nota: str = ""


def _insumo_a_dict(i: Insumo) -> dict:
    return {
        "id": i.id,
        "nombre": i.nombre,
        "unidad": i.unidad,
        "stock_actual": round(i.stock_actual, 3),
        "costo_unitario": round(i.costo_unitario, 4),
        "valor": round(max(i.stock_actual, 0) * i.costo_unitario, 2),
        "activo": i.activo,
    }


@router.get("")
def listar(db: Session = Depends(get_db)):
    insumos = db.scalars(select(Insumo).order_by(Insumo.nombre)).all()
    return {
        "insumos": [_insumo_a_dict(i) for i in insumos],
        "valor_inventario": round(
            sum(max(i.stock_actual, 0) * i.costo_unitario for i in insumos), 2
        ),
    }


@router.post("", status_code=201)
def crear(payload: InsumoIn, db: Session = Depends(get_db)):
    insumo = Insumo(
        nombre=payload.nombre.strip(),
        unidad=payload.unidad.strip(),
        costo_unitario=payload.costo_unitario,
    )
    db.add(insumo)
    db.commit()
    return _insumo_a_dict(insumo)


@router.put("/{insumo_id}")
def actualizar(insumo_id: int, payload: InsumoUpdate, db: Session = Depends(get_db)):
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(insumo, campo, valor.strip() if isinstance(valor, str) else valor)
    db.commit()
    return _insumo_a_dict(insumo)


@router.post("/{insumo_id}/movimientos", status_code=201)
def registrar_movimiento(insumo_id: int, payload: MovimientoIn, db: Session = Depends(get_db)):
    insumo = db.get(Insumo, insumo_id)
    if insumo is None:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")

    if payload.tipo == "compra":
        if payload.cantidad <= 0 or payload.costo_total is None:
            raise HTTPException(status_code=422, detail="Una compra necesita cantidad > 0 y costo_total")
        registrar_compra(db, insumo, payload.cantidad, payload.costo_total, payload.nota)
    elif payload.tipo == "merma":
        if payload.cantidad <= 0:
            raise HTTPException(status_code=422, detail="La merma necesita cantidad > 0")
        registrar_merma(db, insumo, payload.cantidad, payload.nota)
    elif payload.tipo == "ajuste":
        # cantidad = stock contado físicamente (el sistema registra el delta)
        registrar_ajuste(db, insumo, payload.cantidad, payload.nota)
    else:
        raise HTTPException(status_code=422, detail=f"Tipo inválido: {payload.tipo}")

    db.commit()
    return _insumo_a_dict(insumo)


@router.get("/kardex")
def kardex(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    insumo_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    hoy = hoy_lima()
    desde = desde or hoy - timedelta(days=6)
    hasta = hasta or hoy

    consulta = (
        select(MovimientoInsumo, Insumo.nombre, Insumo.unidad)
        .join(Insumo, MovimientoInsumo.insumo_id == Insumo.id)
        .where(MovimientoInsumo.fecha >= desde, MovimientoInsumo.fecha <= hasta)
        .order_by(MovimientoInsumo.id.desc())
        .limit(500)
    )
    if insumo_id is not None:
        consulta = consulta.where(MovimientoInsumo.insumo_id == insumo_id)

    return {"movimientos": [
        {
            "id": m.id,
            "fecha": m.fecha.isoformat(),
            "hora": m.hora,
            "insumo": nombre,
            "unidad": unidad,
            "tipo": m.tipo,
            "cantidad": m.cantidad,
            "costo_total": m.costo_total,
            "referencia": m.referencia,
        }
        for m, nombre, unidad in db.execute(consulta).all()
    ]}


# ---------- Recetas ----------

class RecetaIn(BaseModel):
    items: list[dict] = Field(default_factory=list)  # [{insumo_id, cantidad}]


@router.get("/recetas/{plato_id}")
def receta_de(plato_id: int, db: Session = Depends(get_db)):
    if db.get(Plato, plato_id) is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    items = db.scalars(select(RecetaItem).where(RecetaItem.plato_id == plato_id)).all()
    costo = 0.0
    detalle = []
    for ri in items:
        insumo = db.get(Insumo, ri.insumo_id)
        if insumo is None:
            continue
        costo += ri.cantidad * insumo.costo_unitario
        detalle.append({
            "insumo_id": ri.insumo_id,
            "insumo": insumo.nombre,
            "unidad": insumo.unidad,
            "cantidad": ri.cantidad,
        })
    return {"plato_id": plato_id, "items": detalle, "costo_porcion": round(costo, 2)}


@router.put("/recetas/{plato_id}")
def guardar_receta(plato_id: int, payload: RecetaIn, db: Session = Depends(get_db)):
    """Reemplaza la receta completa del plato."""
    if db.get(Plato, plato_id) is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    for ri in db.scalars(select(RecetaItem).where(RecetaItem.plato_id == plato_id)).all():
        db.delete(ri)
    for item in payload.items:
        insumo = db.get(Insumo, int(item.get("insumo_id", 0)))
        cantidad = float(item.get("cantidad", 0))
        if insumo is None or cantidad <= 0:
            continue
        db.add(RecetaItem(plato_id=plato_id, insumo_id=insumo.id, cantidad=cantidad))
    db.commit()
    return receta_de(plato_id, db)
