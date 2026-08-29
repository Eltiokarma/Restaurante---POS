"""Inventario: consumo automático por ventas y movimientos de kardex.

Cada orden confirmada descuenta insumos según la receta de sus platos
(si la tienen). Anular la orden devuelve el stock. El stock puede
quedar negativo (la cocina no se detiene por el sistema); el admin lo
ve en rojo y lo corrige con un ajuste.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Insumo, MovimientoInsumo, Orden, RecetaItem, ahora_lima


def _registrar(db: Session, insumo: Insumo, tipo: str, delta: float,
               referencia: str, costo_total: float | None = None) -> None:
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
    ))


def consumir_por_orden(db: Session, orden: Orden) -> None:
    """Descuenta insumos según las recetas de los platos de la orden."""
    _mover_por_orden(db, orden, signo=-1, tipo="consumo",
                     referencia=f"orden #{orden.numero_orden_dia:03d}")


def revertir_por_orden(db: Session, orden: Orden) -> None:
    """Devuelve el stock consumido (orden anulada)."""
    _mover_por_orden(db, orden, signo=+1, tipo="ajuste",
                     referencia=f"anulación orden #{orden.numero_orden_dia:03d}")


def _mover_por_orden(db: Session, orden: Orden, signo: int, tipo: str, referencia: str) -> None:
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
            _registrar(db, insumo, tipo, signo * ri.cantidad * item.cantidad, referencia)


def registrar_compra(db: Session, insumo: Insumo, cantidad: float,
                     costo_total: float, nota: str = "") -> None:
    """Compra: sube el stock y recalcula el costo unitario promedio."""
    stock_previo = max(insumo.stock_actual, 0.0)
    valor_previo = stock_previo * insumo.costo_unitario
    nuevo_stock = stock_previo + cantidad
    if nuevo_stock > 0:
        insumo.costo_unitario = round((valor_previo + costo_total) / nuevo_stock, 4)
    _registrar(db, insumo, "compra", cantidad, nota or "compra", costo_total)


def registrar_merma(db: Session, insumo: Insumo, cantidad: float, nota: str = "") -> None:
    _registrar(db, insumo, "merma", -abs(cantidad), nota or "merma")


def registrar_ajuste(db: Session, insumo: Insumo, stock_objetivo: float, nota: str = "") -> None:
    """Conteo físico: lleva el stock al valor contado, registrando el delta."""
    delta = round(stock_objetivo - insumo.stock_actual, 4)
    if delta != 0:
        _registrar(db, insumo, "ajuste", delta, nota or "conteo físico")
