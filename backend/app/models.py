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
    # Sinónimos para el pedido por voz (JSON: ["lomito", "saltado"]).
    # Se editan en admin; son la herramienta de mejora continua de la voz.
    sinonimos: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
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
    # sala | llevar | mixto — cómo se sirve el pedido (sale en ticket y cocina)
    tipo_servicio: Mapped[str] = mapped_column(String(10), default="sala", nullable=False)
    # tactil | voz | mixto — cómo se armó el carrito (para comparar canales)
    origen: Mapped[str] = mapped_column(String(10), default="tactil", nullable=False)
    # efectivo | tarjeta | yape — lo registra la caja al cobrar.
    # None = sin registrar (el cierre lo asume efectivo, comportamiento histórico)
    metodo_pago: Mapped[str | None] = mapped_column(String(10), nullable=True)
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
    # mesa | taper | bolsa | lonchera — en qué se sirve ESTE plato
    # (cocina necesita saberlo por plato, no por orden)
    empaque: Mapped[str] = mapped_column(String(10), default="mesa", nullable=False)

    orden: Mapped[Orden] = relationship(back_populates="items")


class Cancelacion(Base):
    __tablename__ = "cancelaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[str] = mapped_column(String(8), nullable=False)
    items_json: Mapped[str] = mapped_column(Text, nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)


class VozLog(Base):
    """Log de cada intento de pedido por voz (solo texto, nunca el audio).

    Es el tablero de decisión de la voz: % aceptado sin corrección,
    % corregido, % descartado, latencias y costo del día.
    """

    __tablename__ = "voz_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[str] = mapped_column(String(8), nullable=False)
    transcripcion: Mapped[str] = mapped_column(Text, nullable=False)
    interpretacion_json: Mapped[str] = mapped_column(Text, nullable=False)
    # pendiente (recién interpretado) | aceptado | corregido | descartado
    resultado: Mapped[str] = mapped_column(String(12), default="pendiente", nullable=False)
    latencia_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_duracion_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    costo_usd: Mapped[float | None] = mapped_column(Float, nullable=True)


class CierreCaja(Base):
    """Apertura y cierre de caja del día: fondo inicial, conteo final y
    diferencia contra lo que el sistema dice que se vendió."""

    __tablename__ = "cierres_caja"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    hora_apertura: Mapped[str] = mapped_column(String(8), nullable=False)
    monto_apertura: Mapped[float] = mapped_column(Float, nullable=False)
    hora_cierre: Mapped[str | None] = mapped_column(String(8), nullable=True)
    monto_contado: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_sistema: Mapped[float | None] = mapped_column(Float, nullable=True)
    diferencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Desglose por método al momento del cierre (el esperado en caja
    # cuadra SOLO contra el efectivo)
    ventas_efectivo: Mapped[float | None] = mapped_column(Float, nullable=True)
    ventas_tarjeta: Mapped[float | None] = mapped_column(Float, nullable=True)
    ventas_yape: Mapped[float | None] = mapped_column(Float, nullable=True)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Insumo(Base):
    """Insumo de cocina (papa, arroz, carne…) con stock y costo promedio."""

    __tablename__ = "insumos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)  # kg, g, l, ml, unidad…
    stock_actual: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    costo_unitario: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)


class RecetaItem(Base):
    """Receta: cuánto insumo consume UNA porción de un plato."""

    __tablename__ = "receta_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plato_id: Mapped[int] = mapped_column(ForeignKey("platos.id"), nullable=False)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id"), nullable=False)
    cantidad: Mapped[float] = mapped_column(Float, nullable=False)  # en la unidad del insumo


class MovimientoInsumo(Base):
    """Kardex: cada entrada/salida de un insumo, con auditoría.

    ``cantidad`` es el delta con signo aplicado al stock: compra +5,
    consumo -1.2, merma -0.5, ajuste ±.
    """

    __tablename__ = "movimientos_insumo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[str] = mapped_column(String(8), nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # compra | consumo | merma | ajuste
    cantidad: Mapped[float] = mapped_column(Float, nullable=False)
    costo_total: Mapped[float | None] = mapped_column(Float, nullable=True)  # solo compras
    referencia: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # Orden que originó el movimiento (consumo/reversión). Permite anular
    # devolviendo EXACTAMENTE lo consumido, aunque la receta haya cambiado.
    orden_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes.id"), nullable=True)


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
    # Kill switch del pedido por voz: apagado por defecto hasta validar la
    # Fase 2 (además requiere OPENAI_API_KEY y ANTHROPIC_API_KEY en .env)
    "voz_habilitada": "0",
}
