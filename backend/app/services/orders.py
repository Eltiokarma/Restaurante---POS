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
    origen: str = "tactil",
) -> Orden:
    """Crea una orden confirmada (tras la ventana de cancelación).

    ``items`` es una lista de {"plato_id", "cantidad", "empaque"?}.
    Nombre y precio se toman de la BD en el momento de crear la orden
    (snapshot), no del payload del cliente. ``duracion_seg`` es cuánto
    demoró el cliente en armar y confirmar (lo mide la terminal).

    El tipo de servicio de la orden se deriva de los empaques: todo
    "mesa" = sala; nada "mesa" = llevar; mezcla = mixto.
    """
    with _lock_creacion:
        return _crear_orden(db, items, duracion_seg, origen)


def _tipo_servicio_de(empaques: list[str]) -> str:
    en_mesa = [e == "mesa" for e in empaques]
    if all(en_mesa):
        return "sala"
    if not any(en_mesa):
        return "llevar"
    return "mixto"


def _crear_orden(
    db: Session, items: list[dict], duracion_seg: int | None, origen: str
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
        tipo_servicio=_tipo_servicio_de([i.get("empaque", "mesa") for i in items]),
        origen=origen,
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
                empaque=item.get("empaque", "mesa"),
            )
        )

    if not orden.items:
        raise ValueError("La orden no tiene items")

    orden.total = round(total, 2)
    db.add(orden)

    # Kardex: descuenta insumos según las recetas (si los platos las tienen)
    from .inventario import consumir_por_orden

    consumir_por_orden(db, orden)

    db.commit()
    db.refresh(orden)
    return orden
