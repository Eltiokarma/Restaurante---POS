"""Insumos, recetas y kardex (todo protegido con admin)."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..data.fonda_base import INSUMOS_BASE, RECETAS_BASE, buscar_receta_base, insumo_base, normalizar
from ..models import Insumo, MovimientoInsumo, Plato, RecetaItem, hoy_lima
from ..services.inventario import registrar_ajuste, registrar_compra, registrar_merma

router = APIRouter(
    prefix="/api/insumos", tags=["insumos"], dependencies=[Depends(requiere_admin)]
)


class InsumoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    unidad: str = Field(min_length=1, max_length=20)
    costo_unitario: float = Field(default=0.0, ge=0)
    # Avisar cuando el stock baje de aquí; 0 = sin aviso
    stock_minimo: float = Field(default=0.0, ge=0)


class InsumoUpdate(BaseModel):
    nombre: str | None = None
    unidad: str | None = None
    activo: bool | None = None
    stock_minimo: float | None = Field(default=None, ge=0)


class MovimientoIn(BaseModel):
    tipo: str  # compra | merma | ajuste
    cantidad: float = Field(gt=-100_000, lt=100_000)
    costo_total: float | None = Field(default=None, ge=0)
    nota: str = ""


def _bajo_minimo(i: Insumo) -> bool:
    """Se está acabando: hay aviso configurado y el stock ya lo alcanzó."""
    return i.activo and i.stock_minimo > 0 and i.stock_actual <= i.stock_minimo


def _insumo_a_dict(i: Insumo) -> dict:
    return {
        "id": i.id,
        "nombre": i.nombre,
        "unidad": i.unidad,
        "stock_actual": round(i.stock_actual, 3),
        "stock_minimo": round(i.stock_minimo, 3),
        "bajo_minimo": _bajo_minimo(i),
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
        # Para el aviso "se te están acabando 3 cosas" del admin
        "por_agotarse": [i.nombre for i in insumos if _bajo_minimo(i)],
    }


@router.post("", status_code=201)
def crear(payload: InsumoIn, db: Session = Depends(get_db)):
    insumo = Insumo(
        nombre=payload.nombre.strip(),
        unidad=payload.unidad.strip(),
        costo_unitario=payload.costo_unitario,
        stock_minimo=payload.stock_minimo,
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
        # costo_total = 0 corrompería el costo promedio en silencio
        if payload.cantidad <= 0 or payload.costo_total is None or payload.costo_total <= 0:
            raise HTTPException(
                status_code=422,
                detail="Una compra necesita cantidad > 0 y el costo total pagado (> 0)",
            )
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

class RecetaItemIn(BaseModel):
    insumo_id: int
    cantidad: float = Field(gt=0, le=10_000)


class RecetaIn(BaseModel):
    items: list[RecetaItemIn] = Field(default_factory=list)


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

    desconocidos = [
        item.insumo_id for item in payload.items if db.get(Insumo, item.insumo_id) is None
    ]
    if desconocidos:
        raise HTTPException(status_code=422, detail=f"Insumos inexistentes: {desconocidos}")

    for ri in db.scalars(select(RecetaItem).where(RecetaItem.plato_id == plato_id)).all():
        db.delete(ri)
    for item in payload.items:
        db.add(RecetaItem(plato_id=plato_id, insumo_id=item.insumo_id, cantidad=item.cantidad))
    db.commit()
    return receta_de(plato_id, db)


# ---------- Bases pregrabadas (despensa y recetas de fonda) ----------


def _insumo_por_nombre(db: Session, nombre: str) -> Insumo | None:
    objetivo = normalizar(nombre)
    for insumo in db.scalars(select(Insumo)).all():
        if normalizar(insumo.nombre) == objetivo:
            return insumo
    return None


def _crear_desde_base(db: Session, nombre: str) -> Insumo | None:
    """Crea el insumo con los datos de la base (unidad, costo referencial,
    mínimo sugerido). Devuelve el existente si ya estaba."""
    existente = _insumo_por_nombre(db, nombre)
    if existente is not None:
        return existente
    fila = insumo_base(nombre)
    if fila is None:
        return None
    nombre_base, unidad, costo, minimo = fila
    insumo = Insumo(nombre=nombre_base, unidad=unidad, costo_unitario=costo,
                    stock_minimo=minimo)
    db.add(insumo)
    db.flush()
    return insumo


@router.get("/base")
def base_disponible(db: Session = Depends(get_db)):
    """Qué trae la base pregrabada y qué de eso ya existe en la despensa."""
    return {
        "insumos": [
            {"nombre": n, "unidad": u, "costo_referencial": c, "stock_minimo": m,
             "existe": _insumo_por_nombre(db, n) is not None}
            for n, u, c, m in INSUMOS_BASE
        ],
        "platos_con_receta": sorted(RECETAS_BASE.keys()),
    }


@router.post("/base/cargar")
def cargar_despensa_base(db: Session = Depends(get_db)):
    """Crea de golpe la despensa típica de fonda (solo lo que falte).

    Todo queda con stock 0, costo referencial y mínimo sugerido: el dueño
    ajusta lo que quiera después. Nada se duplica ni se sobreescribe.
    """
    creados = []
    for nombre, *_ in INSUMOS_BASE:
        if _insumo_por_nombre(db, nombre) is None:
            _crear_desde_base(db, nombre)
            creados.append(nombre)
    db.commit()
    return {"creados": creados, "total": len(INSUMOS_BASE)}


@router.get("/recetas/{plato_id}/sugerida")
def receta_sugerida(plato_id: int, db: Session = Depends(get_db)):
    """La receta base que coincide con el nombre del plato (si hay)."""
    plato = db.get(Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    encontrada = buscar_receta_base(plato.nombre)
    if encontrada is None:
        return {"plato_id": plato_id, "encontrada": False, "base": None, "items": []}
    clave, items = encontrada
    return {
        "plato_id": plato_id,
        "encontrada": True,
        "base": clave,
        "items": [
            {
                "insumo": nombre,
                "unidad": (insumo_base(nombre) or (nombre, "", 0, 0))[1],
                "cantidad": cantidad,
                "existe": _insumo_por_nombre(db, nombre) is not None,
            }
            for nombre, cantidad in items
        ],
    }


@router.post("/recetas/{plato_id}/sugerida")
def aplicar_receta_sugerida(plato_id: int, db: Session = Depends(get_db)):
    """Pone la receta base al plato, creando los insumos que falten.

    Reemplaza la receta que tuviera: es un punto de partida editable.
    """
    plato = db.get(Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    encontrada = buscar_receta_base(plato.nombre)
    if encontrada is None:
        raise HTTPException(
            status_code=404,
            detail=f"No hay receta base para \"{plato.nombre}\": ármala a mano abajo.",
        )
    _, items = encontrada
    for ri in db.scalars(select(RecetaItem).where(RecetaItem.plato_id == plato_id)).all():
        db.delete(ri)
    for nombre, cantidad in items:
        insumo = _crear_desde_base(db, nombre)
        if insumo is not None:
            db.add(RecetaItem(plato_id=plato_id, insumo_id=insumo.id, cantidad=cantidad))
    db.commit()
    return receta_de(plato_id, db)
