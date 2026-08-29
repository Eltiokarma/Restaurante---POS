import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import Plato, hoy_lima

router = APIRouter(prefix="/api/menu", tags=["menu"])

CATEGORIAS = ["entrada", "fondo", "bebida", "postre"]


class PlatoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    categoria: str
    precio: float
    activo_hoy: bool
    sale_al_momento: bool = False
    sinonimos: list[str] = []

    @field_validator("sinonimos", mode="before")
    @classmethod
    def _desde_json(cls, v):
        # En BD viven como texto JSON; hacia afuera siempre como lista
        if isinstance(v, str):
            try:
                return json.loads(v or "[]")
            except json.JSONDecodeError:
                return []
        return v or []


class PlatoIn(BaseModel):
    id: int | None = None
    nombre: str = Field(min_length=1, max_length=120)
    categoria: str
    precio: float = Field(gt=0)
    activo_hoy: bool = True
    sale_al_momento: bool = False
    sinonimos: list[str] = Field(default_factory=list, max_length=30)


class MenuUpdate(BaseModel):
    platos: list[PlatoIn]


@router.get("/today")
def menu_de_hoy(db: Session = Depends(get_db)):
    platos = db.scalars(
        select(Plato).where(Plato.activo_hoy == True).order_by(Plato.categoria, Plato.nombre)  # noqa: E712
    ).all()
    return {
        "categorias": CATEGORIAS,
        "platos": [PlatoOut.model_validate(p).model_dump() for p in platos],
    }


@router.put("/today", dependencies=[Depends(requiere_admin)])
def actualizar_menu(payload: MenuUpdate, db: Session = Depends(get_db)):
    """Reemplaza el menú del día.

    Platos con id se actualizan; sin id se crean (y quedan en el catálogo).
    Todo plato que no venga en la lista se desactiva para hoy.
    """
    hoy = hoy_lima()
    ids_activos: set[int] = set()

    for p in payload.platos:
        if p.categoria not in CATEGORIAS:
            p.categoria = "fondo"
        sinonimos_json = json.dumps(
            [s.strip() for s in p.sinonimos if s.strip()], ensure_ascii=False
        )
        if p.id is not None:
            plato = db.get(Plato, p.id)
            if plato is None:
                continue
            plato.nombre = p.nombre
            plato.categoria = p.categoria
            plato.precio = round(p.precio, 2)
            plato.activo_hoy = p.activo_hoy
            plato.sale_al_momento = p.sale_al_momento
            plato.sinonimos = sinonimos_json
        else:
            plato = Plato(
                nombre=p.nombre,
                categoria=p.categoria,
                precio=round(p.precio, 2),
                activo_hoy=p.activo_hoy,
                en_catalogo=True,
                sale_al_momento=p.sale_al_momento,
                sinonimos=sinonimos_json,
            )
            db.add(plato)
            db.flush()
        if plato.activo_hoy:
            plato.ultima_vez_activo = hoy
        ids_activos.add(plato.id)

    for plato in db.scalars(select(Plato).where(Plato.activo_hoy == True)).all():  # noqa: E712
        if plato.id not in ids_activos:
            plato.activo_hoy = False

    db.commit()
    return menu_de_hoy(db)


@router.get("/catalog", dependencies=[Depends(requiere_admin)])
def catalogo(db: Session = Depends(get_db)):
    platos = db.scalars(
        select(Plato).where(Plato.en_catalogo == True).order_by(Plato.categoria, Plato.nombre)  # noqa: E712
    ).all()
    return {"platos": [PlatoOut.model_validate(p).model_dump() for p in platos]}


@router.get("/previous", dependencies=[Depends(requiere_admin)])
def menu_anterior(db: Session = Depends(get_db)):
    """Platos del último día de servicio anterior a hoy ("menú de ayer")."""
    hoy = hoy_lima()
    ultima_fecha = db.scalars(
        select(Plato.ultima_vez_activo)
        .where(Plato.ultima_vez_activo != None, Plato.ultima_vez_activo < hoy)  # noqa: E711
        .order_by(Plato.ultima_vez_activo.desc())
        .limit(1)
    ).first()
    if ultima_fecha is None:
        return {"fecha": None, "platos": []}
    platos = db.scalars(
        select(Plato)
        .where(Plato.ultima_vez_activo == ultima_fecha)
        .order_by(Plato.categoria, Plato.nombre)
    ).all()
    return {
        "fecha": ultima_fecha.isoformat(),
        "platos": [PlatoOut.model_validate(p).model_dump() for p in platos],
    }
