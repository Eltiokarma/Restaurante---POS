"""Inventario: consumo automático por ventas y movimientos de kardex.

Cada orden confirmada descuenta insumos según la receta de sus platos
(si la tienen). Anular la orden devuelve EXACTAMENTE lo consumido (se
lee de los movimientos registrados, no de la receta vigente — que pudo
cambiar). El stock puede quedar negativo (la cocina no se detiene por
el sistema); el admin lo ve en rojo y lo corrige con un ajuste.

Todos los cambios de stock pasan por un lock: dos movimientos
simultáneos (una compra del admin y una anulación de caja, por
ejemplo) no se pisan entre sí.
"""
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Insumo, MovimientoInsumo, Orden, RecetaItem, ahora_lima

# Serializa el read-modify-write de stock_actual (mismo criterio que el
# lock del correlativo en services/orders.py)
_lock_inventario = threading.Lock()


def _registrar(db: Session, insumo: Insumo, tipo: str, delta: float,
               referencia: str, costo_total: float | None = None,
               orden_id: int | None = None) -> None:
    ahora = ahora_lima()
    insumo.stock_actual = round(insumo.stock_actual + delta, 4)
    db.add(MovimientoInsumo(
        insumo_id=insumo.id,
        fecha=ahora.date(),
        hora=ahora.strftime("%H:%M:%S"),
        tipo=tipo,
        cantidad=round(delta, 4),
        costo_total=costo_total,
        referencia=referencia,
        orden_id=orden_id,
    ))


def consumir_por_orden(db: Session, orden: Orden) -> None:
    """Descuenta insumos según las recetas de los platos de la orden."""
    with _lock_inventario:
        referencia = f"orden #{orden.numero_orden_dia:03d}"
        for item in orden.items:
            if item.plato_id is None:
                continue
            receta = db.scalars(
                select(RecetaItem).where(RecetaItem.plato_id == item.plato_id)
            ).all()
            for ri in receta:
                insumo = db.get(Insumo, ri.insumo_id)
                if insumo is None:
                    continue
                _registrar(db, insumo, "consumo", -ri.cantidad * item.cantidad,
                           referencia, orden_id=orden.id)


def consumir_directo(db: Session, insumo: Insumo, cantidad: float,
                     referencia: str, orden_id: int | None = None) -> None:
    """Consumo sin receta (bebidas embotelladas: 1 venta = N botellas).

    Ligado a la orden: anularla lo devuelve igual que a los platos,
    porque revertir_por_orden netea TODOS los movimientos de la orden."""
    with _lock_inventario:
        _registrar(db, insumo, "consumo", -abs(cantidad), referencia, orden_id=orden_id)


def revertir_por_orden(db: Session, orden: Orden) -> None:
    """Devuelve el stock que ESTA orden tiene consumido según el kardex.

    Suma todos los movimientos ligados a la orden (consumos y
    reversiones previas): lo pendiente de devolver es el neto. Una
    orden sin movimientos (anterior al kardex, o de platos sin receta)
    no devuelve nada.
    """
    with _lock_inventario:
        movimientos = db.scalars(
            select(MovimientoInsumo).where(MovimientoInsumo.orden_id == orden.id)
        ).all()
        neto_por_insumo: dict[int, float] = {}
        for m in movimientos:
            neto_por_insumo[m.insumo_id] = neto_por_insumo.get(m.insumo_id, 0.0) + m.cantidad

        referencia = f"anulación orden #{orden.numero_orden_dia:03d}"
        for insumo_id, neto in neto_por_insumo.items():
            pendiente = round(-neto, 4)  # consumido neto (negativo) → a devolver
            if pendiente == 0:
                continue
            insumo = db.get(Insumo, insumo_id)
            if insumo is not None:
                _registrar(db, insumo, "ajuste", pendiente, referencia, orden_id=orden.id)


def registrar_compra(db: Session, insumo: Insumo, cantidad: float,
                     costo_total: float, nota: str = "") -> None:
    """Compra: sube el stock y recalcula el costo unitario promedio."""
    with _lock_inventario:
        stock_previo = max(insumo.stock_actual, 0.0)
        valor_previo = stock_previo * insumo.costo_unitario
        nuevo_stock = stock_previo + cantidad
        if nuevo_stock > 0:
            insumo.costo_unitario = round((valor_previo + costo_total) / nuevo_stock, 4)
        _registrar(db, insumo, "compra", cantidad, nota or "compra", costo_total)


def registrar_merma(db: Session, insumo: Insumo, cantidad: float, nota: str = "") -> None:
    with _lock_inventario:
        _registrar(db, insumo, "merma", -abs(cantidad), nota or "merma")


def registrar_ajuste(db: Session, insumo: Insumo, stock_objetivo: float, nota: str = "") -> None:
    """Conteo físico: lleva el stock al valor contado, registrando el delta."""
    with _lock_inventario:
        delta = round(stock_objetivo - insumo.stock_actual, 4)
        if delta != 0:
            _registrar(db, insumo, "ajuste", delta, nota or "conteo físico")
