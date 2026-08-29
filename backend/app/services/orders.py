"""Lógica de creación de órdenes.

Punto clave: el número de orden es un correlativo POR DÍA (la orden #1, #2...
de hoy) y se calcula dentro de la misma transacción que inserta la orden.
"""
import threading

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Orden, OrdenItem, Plato, ahora_lima

# Serializa la asignación del correlativo del día: sin esto, dos
# confirmaciones simultáneas (p. ej. dos terminales) podrían leer el mismo
# máximo y crear dos órdenes con el mismo número.
_lock_creacion = threading.Lock()


class PlatoNoDisponible(Exception):
    def __init__(self, nombre: str):
        self.nombre = nombre
        super().__init__(f"Plato no disponible: {nombre}")


def crear_orden(
    db: Session,
    items: list[dict],
    duracion_seg: int | None = None,
    tipo_servicio: str = "sala",
) -> Orden:
    """Crea una orden confirmada (tras la ventana de cancelación).

    ``items`` es una lista de {"plato_id": int, "cantidad": int}.
    Nombre y precio se toman de la BD en el momento de crear la orden
    (snapshot), no del payload del cliente. ``duracion_seg`` es cuánto
    demoró el cliente en armar y confirmar (lo mide la terminal).
    """
    with _lock_creacion:
        return _crear_orden(db, items, duracion_seg, tipo_servicio)


def _crear_orden(
    db: Session, items: list[dict], duracion_seg: int | None, tipo_servicio: str
) -> Orden:
    ahora = ahora_lima()
    hoy = ahora.date()

    ultimo = db.execute(
        select(func.max(Orden.numero_orden_dia)).where(Orden.fecha == hoy)
    ).scalar()
    numero = (ultimo or 0) + 1

    orden = Orden(
        numero_orden_dia=numero,
        fecha=hoy,
        hora=ahora.strftime("%H:%M:%S"),
        total=0.0,
        estado="pendiente",
        duracion_seg=duracion_seg,
        tipo_servicio=tipo_servicio,
    )

    total = 0.0
    for item in items:
        plato = db.get(Plato, item["plato_id"])
        if plato is None or not plato.activo_hoy:
            raise PlatoNoDisponible(plato.nombre if plato else f"id {item['plato_id']}")
        cantidad = int(item["cantidad"])
        if cantidad <= 0:
            continue
        total += plato.precio * cantidad
        orden.items.append(
            OrdenItem(
                plato_id=plato.id,
                nombre_snapshot=plato.nombre,
                precio_snapshot=plato.precio,
                cantidad=cantidad,
            )
        )

    if not orden.items:
        raise ValueError("La orden no tiene items")

    orden.total = round(total, 2)
    db.add(orden)
    db.commit()
    db.refresh(orden)
    return orden
