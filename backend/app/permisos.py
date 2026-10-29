"""Qué puede hacer cada perfil del equipo (pedido del dueño).

Con `equipo_activo` apagado nada de esto aplica: el sistema funciona como
siempre (el PIN del local abre todo). Encendido, cada persona entra con su
PIN y su rol decide:

- "si": lo hace directo.
- "autoriza": lo hace solo si un admin pone su PIN en ese momento (el
  frontend reintenta con el header X-Autoriza: "<id del admin>:<PIN>").
- sin entrada: no puede (403).

El admin puede todo; la sesión de admin del panel (contraseña) también.
Cocina, la ticketera y el puente no inician sesión: sus acciones (avanzar
estados, imprimir) siguen abiertas con el PIN del local.
"""
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .auth import (
    anotar_intento_pin, leer_token_equipo, pin_correcto, requiere_admin, segundos_bloqueado,
)
from .db import get_db
from .models import AccionEquipo, Config, Orden, Usuario, ahora_lima

ROLES = ("admin", "cajero", "mozo")

PERMISOS: dict[str, dict[str, str]] = {
    # Armar y corregir pedidos: agregar platos o gaseosas, mesa, entrega,
    # empaque, elegir lo pendiente, reimprimir el ticket
    "pedidos": {"cajero": "si", "mozo": "si"},
    # Quitar una persona o un plato de un pedido ya confirmado
    "quitar_plato": {"cajero": "si", "mozo": "autoriza"},
    # Anular el pedido entero. El cajero lo hace sin PIN solo en los
    # primeros ANULAR_LIBRE_SEG (un duplicado recién hecho)
    "anular": {"cajero": "autoriza", "mozo": "autoriza"},
    # La caja: cobrar, vuelto, falta pagar, mesas, abrir/cerrar caja,
    # egresos, cajón, menú del día y stock
    "caja": {"cajero": "si"},
    # Lo que mueve plata ya contada: borrar un egreso, reabrir la caja,
    # corregir el fondo, dar una deuda por perdida, descartar la cola de
    # impresión
    "caja_delicado": {"cajero": "autoriza"},
}

ANULAR_LIBRE_SEG = 60


@dataclass
class Actor:
    """Quién está pidiendo: una persona del equipo, el panel de admin o
    nadie (dispositivo con solo el PIN del local)."""
    equipo_activo: bool
    usuario: Usuario | None = None
    panel_admin: bool = False
    autoriza: str = ""

    @property
    def rol(self) -> str | None:
        if self.panel_admin:
            return "admin"
        return self.usuario.rol if self.usuario else None

    @property
    def nombre(self) -> str:
        if self.usuario:
            return self.usuario.nombre
        return "Admin" if self.panel_admin else ""


def equipo_activo(db: Session) -> bool:
    registro = db.get(Config, "equipo_activo")
    return registro is not None and registro.valor in ("1", "true", "True")


def actor_actual(
    x_usuario_token: str = Header(default=""),
    x_admin_token: str = Header(default=""),
    x_autoriza: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Actor:
    actor = Actor(equipo_activo=equipo_activo(db), autoriza=x_autoriza)
    if x_usuario_token:
        uid = leer_token_equipo(x_usuario_token)
        usuario = db.get(Usuario, uid) if uid is not None else None
        if usuario is not None and usuario.activo:
            actor.usuario = usuario
    if x_admin_token:
        try:
            requiere_admin(x_admin_token)
            actor.panel_admin = True
        except HTTPException:
            pass
    return actor


def _verificar_autorizacion(db: Session, valor: str) -> Usuario:
    """X-Autoriza: "<id>:<PIN>" de un admin activo. 428 si falta o no vale."""
    try:
        uid_texto, pin = valor.split(":", 1)
        admin = db.get(Usuario, int(uid_texto))
    except ValueError:
        admin = None
        pin = ""
    if admin is None or not admin.activo or admin.rol != "admin":
        raise HTTPException(status_code=428, detail="Necesita la autorización de un administrador")
    espera = segundos_bloqueado(admin.id)
    if espera:
        raise HTTPException(status_code=429, detail=f"Demasiados intentos: espera {espera // 60 + 1} min")
    acerto = pin_correcto(pin, admin.pin_hash)
    anotar_intento_pin(admin.id, acerto)
    if not acerto:
        raise HTTPException(status_code=428, detail="PIN de administrador incorrecto")
    return admin


def exigir(
    actor: Actor,
    permiso: str,
    db: Session,
    *,
    registrar: str = "",
    orden_id: int | None = None,
    detalle: str = "",
    libre: bool = False,
) -> None:
    """Corta con 401/403/428 si el actor no puede. Con `registrar`, deja
    la acción en el registro del equipo (quién y quién autorizó).
    `libre`: la regla del caso lo deja pasar sin autorización."""
    if not actor.equipo_activo:
        return
    autorizo: Usuario | None = None
    rol = actor.rol
    if rol is None:
        raise HTTPException(status_code=401, detail="Sesión del equipo requerida: entra con tu nombre")
    if rol != "admin":
        nivel = PERMISOS[permiso].get(rol)
        if nivel is None:
            raise HTTPException(status_code=403, detail="Tu perfil no puede hacer esto")
        if nivel == "autoriza" and not libre:
            autorizo = _verificar_autorizacion(db, actor.autoriza)
    if registrar:
        db.add(AccionEquipo(
            accion=registrar,
            usuario_id=actor.usuario.id if actor.usuario else None,
            usuario=actor.nombre,
            autorizo_id=autorizo.id if autorizo else None,
            autorizo=autorizo.nombre if autorizo else "",
            orden_id=orden_id,
            detalle=detalle[:200],
        ))


def anular_libre(actor: Actor, orden: Orden) -> bool:
    """El cajero anula sin PIN un pedido de hace menos de un minuto."""
    if actor.rol != "cajero":
        return False
    creada = orden.created_at
    ahora = ahora_lima()
    if creada.tzinfo is None:
        ahora = ahora.replace(tzinfo=None)
    return (ahora - creada).total_seconds() <= ANULAR_LIBRE_SEG
