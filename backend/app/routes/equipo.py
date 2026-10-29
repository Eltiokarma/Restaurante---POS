"""Equipo con perfiles (pedido del dueño): quién es quién y su sesión.

- El admin crea a las personas (nombre, rol, PIN) en Admin → Equipo.
- En la tablet, "¿Quién eres?": se toca el nombre y se pone el PIN.
- Nadie se borra: se desactiva (el registro guarda quién hizo qué).
"""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import (
    anotar_intento_pin, cifrar_pin, emitir_token_equipo, leer_token_equipo, pin_correcto,
    requiere_admin, segundos_bloqueado,
)
from ..db import get_db
from ..models import AccionEquipo, Usuario, hoy_lima
from ..permisos import ROLES, equipo_activo

router = APIRouter(prefix="/api/equipo", tags=["equipo"])


def _pin_valido(pin: str) -> str:
    pin = pin.strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        raise HTTPException(status_code=422, detail="El PIN va de 4 a 6 números")
    return pin


def _a_dict(u: Usuario) -> dict:
    return {"id": u.id, "nombre": u.nombre, "rol": u.rol, "activo": u.activo}


# ---------- para la tablet (sin admin) ----------

@router.get("/quienes")
def quienes(db: Session = Depends(get_db)):
    """Los nombres para "¿Quién eres?" (sin PIN, claro) y si el equipo
    está encendido."""
    personas = db.scalars(
        select(Usuario).where(Usuario.activo == True).order_by(Usuario.nombre)  # noqa: E712
    ).all()
    return {"activo": equipo_activo(db), "personas": [_a_dict(u) for u in personas]}


class EntrarIn(BaseModel):
    usuario_id: int
    pin: str = Field(max_length=12)


@router.post("/entrar")
def entrar(payload: EntrarIn, db: Session = Depends(get_db)):
    usuario = db.get(Usuario, payload.usuario_id)
    if usuario is None or not usuario.activo:
        raise HTTPException(status_code=404, detail="Esa persona no está en el equipo")
    espera = segundos_bloqueado(usuario.id)
    if espera:
        raise HTTPException(status_code=429, detail=f"Demasiados intentos: espera {espera // 60 + 1} min")
    acerto = pin_correcto(payload.pin.strip(), usuario.pin_hash)
    anotar_intento_pin(usuario.id, acerto)
    if not acerto:
        raise HTTPException(status_code=403, detail="PIN incorrecto")
    return {"token": emitir_token_equipo(usuario.id), "usuario": _a_dict(usuario)}


@router.get("/yo")
def yo(x_usuario_token: str = Header(default=""), db: Session = Depends(get_db)):
    """¿La sesión guardada en la tablet sigue valiendo?"""
    uid = leer_token_equipo(x_usuario_token)
    usuario = db.get(Usuario, uid) if uid is not None else None
    if usuario is None or not usuario.activo:
        raise HTTPException(status_code=401, detail="Sesión del equipo vencida")
    return _a_dict(usuario)


# ---------- Admin → Equipo ----------

class PersonaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    rol: str
    pin: str


class PersonaCambio(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    rol: str | None = None
    pin: str | None = None
    activo: bool | None = None


@router.get("", dependencies=[Depends(requiere_admin)])
def listar(db: Session = Depends(get_db)):
    personas = db.scalars(select(Usuario).order_by(Usuario.activo.desc(), Usuario.nombre)).all()
    return {"activo": equipo_activo(db), "personas": [_a_dict(u) for u in personas]}


def _nombre_libre(db: Session, nombre: str, menos_id: int | None = None) -> None:
    # Dos "Rosa" en "¿Quién eres?" serían un lío
    for u in db.scalars(select(Usuario).where(Usuario.activo == True)).all():  # noqa: E712
        if u.id != menos_id and u.nombre.strip().lower() == nombre.strip().lower():
            raise HTTPException(status_code=409, detail=f"Ya hay alguien llamado {u.nombre}")


@router.post("", dependencies=[Depends(requiere_admin)], status_code=201)
def crear(payload: PersonaIn, db: Session = Depends(get_db)):
    if payload.rol not in ROLES:
        raise HTTPException(status_code=422, detail=f"Rol inválido: {payload.rol}")
    _nombre_libre(db, payload.nombre)
    usuario = Usuario(
        nombre=payload.nombre.strip(), rol=payload.rol, pin_hash=cifrar_pin(_pin_valido(payload.pin)),
    )
    db.add(usuario)
    db.commit()
    return _a_dict(usuario)


@router.put("/{usuario_id}", dependencies=[Depends(requiere_admin)])
def cambiar(usuario_id: int, payload: PersonaCambio, db: Session = Depends(get_db)):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Esa persona no está en el equipo")
    if payload.rol is not None and payload.rol not in ROLES:
        raise HTTPException(status_code=422, detail=f"Rol inválido: {payload.rol}")
    if payload.nombre is not None:
        _nombre_libre(db, payload.nombre, usuario.id)
        usuario.nombre = payload.nombre.strip()
    if payload.activo is True and not usuario.activo:
        _nombre_libre(db, usuario.nombre, usuario.id)
    if payload.rol is not None:
        usuario.rol = payload.rol
    if payload.pin:
        usuario.pin_hash = cifrar_pin(_pin_valido(payload.pin))
    if payload.activo is not None:
        usuario.activo = payload.activo
    db.commit()
    return _a_dict(usuario)


@router.get("/acciones", dependencies=[Depends(requiere_admin)])
def acciones(fecha: date | None = Query(default=None), db: Session = Depends(get_db)):
    """Lo delicado de un día: quién anuló, quitó, levantó o reabrió, y
    quién lo autorizó."""
    dia = fecha or hoy_lima()
    desde = datetime.combine(dia, time.min)
    hasta = datetime.combine(dia, time.max)
    filas = db.scalars(
        select(AccionEquipo)
        .where(AccionEquipo.creado_en >= desde, AccionEquipo.creado_en <= hasta)
        .order_by(AccionEquipo.id.desc())
    ).all()
    return {
        "fecha": dia.isoformat(),
        "acciones": [
            {
                "id": a.id, "hora": a.creado_en.strftime("%H:%M"), "accion": a.accion,
                "usuario": a.usuario, "autorizo": a.autorizo, "orden_id": a.orden_id,
                "detalle": a.detalle,
            }
            for a in filas
        ],
    }
