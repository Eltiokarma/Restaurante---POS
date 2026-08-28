from datetime import datetime, date
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

LIMA = ZoneInfo("America/Lima")


def ahora_lima() -> datetime:
    return datetime.now(LIMA)


def hoy_lima() -> date:
    return ahora_lima().date()


class Plato(Base):
    __tablename__ = "platos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    categoria: Mapped[str] = mapped_column(String(30), nullable=False)  # entrada | fondo | bebida | postre
    precio: Mapped[float] = mapped_column(Float, nullable=False)
    activo_hoy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    en_catalogo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Última fecha en la que el plato formó parte del menú del día.
    # Permite el botón "Cargar menú de ayer" en el admin.
    ultima_vez_activo: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)


class Orden(Base):
    __tablename__ = "ordenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Correlativo que reinicia cada día: la orden #1, #2, ... de hoy
    numero_orden_dia: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[str] = mapped_column(String(8), nullable=False)  # "HH:MM:SS"
    total: Mapped[float] = mapped_column(Float, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default="pendiente", nullable=False
    )  # pendiente | preparando | listo | entregado
    # False = en cola de la estación de impresión (/ticketera). En modo
    # "terminal" se marca True al crearse porque la propia terminal imprime.
    impreso: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Segundos desde que el cliente empezó el pedido hasta que lo confirmó
    # (lo mide y envía la terminal; None en órdenes antiguas o si no llegó)
    duracion_seg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)

    items: Mapped[list["OrdenItem"]] = relationship(
        back_populates="orden", cascade="all, delete-orphan"
    )


class OrdenItem(Base):
    __tablename__ = "orden_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes.id"), nullable=False)
    plato_id: Mapped[int | None] = mapped_column(ForeignKey("platos.id"), nullable=True)
    # Snapshot: si mañana cambia el precio del plato, la orden histórica no se altera
    nombre_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    precio_snapshot: Mapped[float] = mapped_column(Float, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)

    orden: Mapped[Orden] = relationship(back_populates="items")


class Cancelacion(Base):
    __tablename__ = "cancelaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[str] = mapped_column(String(8), nullable=False)
    items_json: Mapped[str] = mapped_column(Text, nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)


class Config(Base):
    __tablename__ = "config"

    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(Text, nullable=False)


CONFIG_DEFAULTS: dict[str, str] = {
    "nombre_local": "Mi Restaurante",
    "direccion": "",
    "ruc": "",
    "ventana_cancelacion_seg": "30",
    "timeout_inactividad_seg": "90",
    # "terminal": la pantalla donde pide el cliente imprime (PC con impresora)
    # "estacion": imprime la PC que tenga abierta /ticketera (tablets como terminal)
    "modo_impresion": "terminal",
}
