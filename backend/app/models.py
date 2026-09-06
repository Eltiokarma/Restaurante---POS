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
    # Nombre de archivo de la foto del plato (vive en <carpeta de la BD>/fotos;
    # en Railway eso es el volumen /data). None = sin foto.
    foto: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # True = se prepara al momento (bistec frito): no puede salir "todo
    # junto" con el resto del pedido
    sale_al_momento: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Cuántas porciones entran por tanda (sartén/olla): una tanda de 9
    # chuletas con capacidad 6 se muestra "6 + 3". 0 = sin límite.
    capacidad_tanda: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)


class MenuPlantilla(Base):
    """El menú como unidad de venta: "Menú del día S/ 11". El precio vive
    AQUÍ, no en los platos que lo componen (ver docs/ESPEC-FONDA-BACKEND.md §1)."""

    __tablename__ = "menu_plantillas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    precio: Mapped[float] = mapped_column(Float, nullable=False)
    activo_hoy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    en_catalogo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)

    tiempos: Mapped[list["MenuTiempo"]] = relationship(
        back_populates="menu", cascade="all, delete-orphan", order_by="MenuTiempo.orden"
    )


class MenuTiempo(Base):
    """Un eslabón de la cadena del menú: entrada/sopa → segundo → refresco."""

    __tablename__ = "menu_tiempos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menu_plantillas.id"), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 entrada, 2 segundo, 3 refresco…
    rotulo: Mapped[str] = mapped_column(String(60), nullable=False)  # "Entrada o sopa"
    obligatorio: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Precio de UNA porción ADICIONAL de este tiempo pedida junto con el
    # menú ("una entrada más" a S/ 3 aunque dentro del menú vaya a S/ 1).
    # 0 = no se ofrecen porciones extra de este tiempo.
    precio_extra: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Cuánto BAJA el menú si el cliente quita este tiempo ("sin sopa").
    # 0 = quitarlo no descuenta (decisión del dueño: sí descuenta un poco,
    # el monto lo pone él por tiempo en el editor de plantillas).
    descuento_si_se_quita: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    menu: Mapped[MenuPlantilla] = relationship(back_populates="tiempos")
    alternativas: Mapped[list["MenuAlternativa"]] = relationship(
        back_populates="tiempo", cascade="all, delete-orphan"
    )


class MenuAlternativa(Base):
    """Un plato que puede ocupar un tiempo del menú (con recargo opcional)."""

    __tablename__ = "menu_alternativas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tiempo_id: Mapped[int] = mapped_column(ForeignKey("menu_tiempos.id"), nullable=False)
    plato_id: Mapped[int] = mapped_column(ForeignKey("platos.id"), nullable=False)
    recargo: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0 = sin costo extra

    tiempo: Mapped[MenuTiempo] = relationship(back_populates="alternativas")


class MenuAgregado(Base):
    """Porción suelta que se suma a un menú: + presa, + refresco, + arroz…

    No es un plato de la carta: es un componente con su precio propio.
    ``menu_id`` NULL = se ofrece con todos los menús (el caso normal)."""

    __tablename__ = "menu_agregados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_id: Mapped[int | None] = mapped_column(ForeignKey("menu_plantillas.id"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    precio: Mapped[float] = mapped_column(Float, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# Agregados con los que arranca una instalación (editables en Admin →
# Menú del día); precios acordados con el dueño el 2026-09-04
AGREGADOS_INICIALES = [
    ("Presa", 4.0), ("Refresco", 1.5), ("Arroz", 1.5), ("Ensalada", 2.0), ("Guarnición", 2.0),
]


class MenuGuardado(Base):
    """Un menú del día guardado con nombre ("Lunes", "Jueves de caldo"):
    snapshot de los platos activos y las plantillas, para recargarlo con
    un toque otro día. Guardar con el mismo nombre lo actualiza."""

    __tablename__ = "menus_guardados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    datos_json: Mapped[str] = mapped_column(Text, nullable=False)
    actualizado: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)


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
    # "Falta pagar": el ticket salió pero la plata aún no entró al cajón.
    # "Falta vuelto": pagó de más y se le debe el vuelto. Los dos afectan
    # el efectivo esperado del cierre hasta que se resuelven — antes se
    # llevaban de memoria y descuadraban la caja.
    pago_pendiente: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vuelto_pendiente: Mapped[float | None] = mapped_column(Float, nullable=True)
    # junto | separado — cómo sale el pedido: todo en una entrega, o por
    # tiempos (la sopa primero, el segundo cuando esté)
    entrega: Mapped[str] = mapped_column(String(10), default="junto", nullable=False)
    # Mesas asignadas al ticket (JSON de ids). Varias = mesas combinadas.
    mesa_ids: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # True cuando la caja liberó las mesas de este ticket (clientes se fueron)
    mesa_liberada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Cuándo se anuló (cintillo "no preparar" en cocina los primeros 60 s).
    # Des-anular la limpia.
    anulada_en: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)

    items: Mapped[list["OrdenItem"]] = relationship(
        back_populates="orden", cascade="all, delete-orphan"
    )
    menus: Mapped[list["OrdenMenu"]] = relationship(
        back_populates="orden", cascade="all, delete-orphan"
    )


class OrdenMenu(Base):
    """Un menú vendido dentro de una orden. El precio cobrado es el del
    MENÚ (snapshot); los platos elegidos son OrdenItems ligados a este
    registro con precio 0 (o el recargo/extra), para no cobrar dos veces."""

    __tablename__ = "orden_menus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes.id"), nullable=False)
    # Nullable: si la plantilla se borra, el histórico queda con el snapshot
    menu_id: Mapped[int | None] = mapped_column(ForeignKey("menu_plantillas.id"), nullable=True)
    nombre_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    precio_snapshot: Mapped[float] = mapped_column(Float, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    nota: Mapped[str] = mapped_column(String(150), default="", nullable=False)
    # Tiempos que el cliente quitó ("sin sopa"): JSON de
    # [{"tiempo_orden", "rotulo", "descuento"}] — snapshot, con el
    # descuento POR UNIDAD de menú que se aplicó al cobrar
    omitidos_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    orden: Mapped[Orden] = relationship(back_populates="menus")
    items: Mapped[list["OrdenItem"]] = relationship(back_populates="orden_menu")

    def omitidos(self) -> list[dict]:
        import json

        return json.loads(self.omitidos_json or "[]")

    @property
    def descuento_omitidos(self) -> float:
        """Descuento POR UNIDAD por los tiempos quitados."""
        return sum(o["descuento"] for o in self.omitidos())

    @property
    def precio_cobrado(self) -> float:
        """Precio por unidad realmente cobrado (snapshot − descuentos)."""
        return self.precio_snapshot - self.descuento_omitidos


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
    # Pedido especial del cliente: "sin frijoles", "con un huevo frito"…
    nota: Mapped[str] = mapped_column(String(150), default="", nullable=False)
    # NULL = venta a la carta (comportamiento histórico). Presente = el ítem
    # es el plato elegido (o una porción extra) de ese menú vendido: su
    # precio_snapshot es 0.0, el recargo o el precio de la porción extra —
    # nunca el precio de carta, porque el precio ya está en el menú.
    orden_menu_id: Mapped[int | None] = mapped_column(ForeignKey("orden_menus.id"), nullable=True)
    tiempo_orden: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # True = porción adicional pedida junto al menú ("una entrada más")
    es_extra: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True = agregado del menú ("+1 presa"): no es plato de carta
    # (plato_id NULL) y su snapshot viene de menu_agregados
    es_agregado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True = línea de cobro (ej. "Táper × 3"): entra al total y al ticket,
    # pero cocina no la prepara (nace en estado "entregado")
    es_cargo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Estado POR ÍTEM (§3): la cocina cocina por bulks (4 asados de un
    # toque), no ticket por ticket. ordenes.estado queda como caché
    # derivada = el estado MÍNIMO de sus ítems (ver services/cocina.py).
    estado: Mapped[str] = mapped_column(
        String(20), default="pendiente", nullable=False
    )  # pendiente | preparando | listo | entregado

    orden: Mapped[Orden] = relationship(back_populates="items")
    orden_menu: Mapped[OrdenMenu | None] = relationship(back_populates="items")


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
    """Apertura y cierre de una caja: fondo inicial, conteo final y
    diferencia contra lo que el sistema dice que se vendió. Puede haber
    varias en un mismo día (turnos): cada una cuadra su tramo."""

    __tablename__ = "cierres_caja"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    # Las ventas de esta caja son las órdenes del día con id MAYOR a este
    # (NULL = todas: la primera caja del día también cuadra lo vendido
    # antes de abrirla, como siempre fue).
    desde_orden_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    # Snapshot al cierre del total de egresos del turno (None = cierre
    # anterior a la función de egresos, o caja aún abierta)
    egresos: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Snapshot al cierre de los tickets con pago pendiente (plata que no
    # entró) y de los vueltos por dar (plata de más en el cajón)
    por_cobrar: Mapped[float | None] = mapped_column(Float, nullable=True)
    vueltos_pendientes: Mapped[float | None] = mapped_column(Float, nullable=True)
    notas: Mapped[str] = mapped_column(Text, default="", nullable=False)


class EgresoCaja(Base):
    """Plata que sale del cajón durante el turno (gas, verduras, un
    encargo): baja el efectivo esperado al cierre de SU caja."""

    __tablename__ = "egresos_caja"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cierre_id: Mapped[int] = mapped_column(ForeignKey("cierres_caja.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[str] = mapped_column(String(8), nullable=False)
    concepto: Mapped[str] = mapped_column(String(120), nullable=False)
    monto: Mapped[float] = mapped_column(Float, nullable=False)


class Bebida(Base):
    """Bebida embotellada de la lista fija de caja (Inca Kola 500 ml…).

    No es un plato: no pasa por cocina ni por el menú del día. Se agrega
    a una orden YA creada desde caja y se cobra al precio de esta lista
    (el item guarda snapshot, como todo). Si tiene insumo ligado, cada
    venta descuenta botellas del kardex."""

    __tablename__ = "bebidas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    precio: Mapped[float] = mapped_column(Float, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Insumo (unidad "unidad") que descuenta el kardex; NULL = sin kardex
    insumo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)


class TicketBebida(Base):
    """Ticket chico de SOLO las gaseosas agregadas a una orden.

    Pedido del dueño: al añadir gaseosas desde caja no se reimprime el
    ticket de toda la mesa, sale solo este comprobante. Espera en la cola
    de impresión (modo puente/estación) hasta que se confirme impreso."""

    __tablename__ = "tickets_bebida"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes.id"), nullable=False)
    # [{"nombre", "precio", "cantidad"}, …] — snapshot de lo agregado
    detalle_json: Mapped[str] = mapped_column(Text, nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)
    impreso: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TandaLog(Base):
    """Snapshot de cada tanda despachada: el dato de entrenamiento del
    futuro orquestador IA (composición, cuándo se empezó, cuándo salió)."""

    __tablename__ = "tanda_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    # {"orden_ids": [...], "tickets": [...], "platos": [...]} al momento de empezar
    composicion_json: Mapped[str] = mapped_column(Text, nullable=False)
    hora_inicio: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hora_listo: Mapped[str | None] = mapped_column(String(8), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)


class Mesa(Base):
    """Mesa del local. La ocupación se calcula desde las órdenes del día."""

    __tablename__ = "mesas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(40), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=ahora_lima, nullable=False)


class Insumo(Base):
    """Insumo de cocina (papa, arroz, carne…) con stock y costo promedio."""

    __tablename__ = "insumos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)  # kg, g, l, ml, unidad…
    stock_actual: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Aviso "se está acabando": con stock_actual <= stock_minimo el admin lo
    # resalta. 0 = sin alerta configurada para ese insumo.
    stock_minimo: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
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
    # "puente": el puente de impresión del local (scripts/puente_impresion.py)
    #           manda ESC/POS directo a la impresora de red — para tablets +
    #           servidor en la nube (Railway), sin drivers ni diálogos
    "modo_impresion": "terminal",
    # Impresora térmica de red (modo "puente"): IP en la red del local,
    # puerto RAW (9100 en casi todas) y ancho en columnas (48 u 42 según
    # el modelo de 80 mm)
    "impresora_ip": "",
    "impresora_puerto": "9100",
    "impresora_columnas": "42",
    # Kill switch del pedido por voz: apagado por defecto hasta validar la
    # Fase 2 (además requiere OPENAI_API_KEY y ANTHROPIC_API_KEY en .env)
    "voz_habilitada": "0",
    # Si está en 1, no se pueden registrar ventas hasta abrir la caja del
    # día con su fondo inicial
    "exigir_caja_abierta": "1",
    # Si está en 1, la terminal del cliente muestra SOLO los menús (pedido
    # del dueño: repetir abajo los platos sueltos confundía). La caja
    # siempre ve la carta completa.
    "terminal_solo_menus": "1",
    # Cuánto cuesta CADA porción que sale en táper (0 = el táper es gratis).
    # Se cobra como línea "Táper × N" en la orden; regla del dueño:
    # "táper cuesta un sol más".
    "precio_taper": "0",
    # Qué empaques se ofrecen en las pantallas (mesa siempre va).
    # El dueño de hoy: "bolsa y lonchera no".
    "empaques_ofrecidos": "mesa,taper,bolsa,lonchera",
    # Ventana de la tanda en cocina (minutos): "Por salir" resalta cuántas
    # porciones pertenecen a la tanda actual (la orden activa más antigua
    # + los pedidos que llegaron en los siguientes X minutos). 0 = apagado.
    "cocina_bulk_min": "10",
    # Tablero de tandas en /cocina (pre-orquestador). Decisión del dueño
    # (2026-09-06): la tanda cierra con LO QUE SE LLENE PRIMERO — la
    # ventana de minutos (cocina_bulk_min) o el tope de tickets.
    "cocina_tandas": "1",
    # Tope de tickets por tanda (0 = sin tope, manda solo la ventana)
    "cocina_tanda_max_tickets": "4",
}
