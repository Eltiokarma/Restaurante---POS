"""Despacho por bulks (§3): tachar porciones desde "Por salir".

La cocina cocina 4 asados de un toque, no ticket por ticket. Un bulk
avanza N porciones de un plato al estado destino EN CASCADA: de la orden
más antigua a la más nueva. Si una orden tiene más porciones de las que
se tachan, el ítem se PARTE en dos (las tachadas y las que quedan), así
el total de la orden no cambia jamás.

``ordenes.estado`` es una caché derivada: el estado MÍNIMO de sus ítems
(una orden con un plato listo y otro pendiente sigue pendiente). La
decisión está anotada en el registro de decisiones del ROADMAP.
"""
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Orden, OrdenItem, hoy_lima

# pendiente < preparando < listo < entregado (nunca se retrocede en bulk)
RANGO_ESTADO = {"pendiente": 0, "preparando": 1, "listo": 2, "entregado": 3}

# Serializa los despachos (dos pantallas de cocina tachando a la vez)
_lock_despacho = threading.Lock()


class BulkInsuficiente(Exception):
    """Se pidió tachar más porciones de las que quedan por avanzar."""

    def __init__(self, nombre: str, pedidas: int, disponibles: int):
        self.nombre = nombre
        self.pedidas = pedidas
        self.disponibles = disponibles
        super().__init__(f"{nombre}: se pidió {pedidas}, quedan {disponibles}")


def recalcular_estado_orden(orden: Orden) -> None:
    """ordenes.estado = mínimo de sus ítems. Una anulada no se toca."""
    if orden.estado == "anulada" or not orden.items:
        return
    orden.estado = min(orden.items, key=lambda i: RANGO_ESTADO[i.estado]).estado


def _coincide(item: OrdenItem, linea: dict) -> bool:
    if linea.get("plato_id") is not None:
        return item.plato_id == linea["plato_id"]
    return item.nombre_snapshot == linea.get("plato_nombre")


def _partir_item(orden: Orden, item: OrdenItem, cantidad: int, estado: str) -> None:
    """Parte un ítem: ``cantidad`` porciones pasan al estado nuevo, el
    resto queda como estaba. Mismos snapshots: el total no se altera."""
    item.cantidad -= cantidad
    orden.items.append(OrdenItem(
        plato_id=item.plato_id,
        nombre_snapshot=item.nombre_snapshot,
        precio_snapshot=item.precio_snapshot,
        cantidad=cantidad,
        empaque=item.empaque,
        nota=item.nota,
        orden_menu_id=item.orden_menu_id,
        tiempo_orden=item.tiempo_orden,
        es_extra=item.es_extra,
        estado=estado,
    ))


def despachar_bulk(db: Session, lineas: list[dict], estado_destino: str) -> list[Orden]:
    """Avanza porciones al estado destino en cascada por antigüedad.

    ``lineas`` es [{"plato_nombre" | "plato_id", "cantidad"}]; varias
    líneas en una llamada = bulk mixto ("2 y 2"), TODO o nada: si alguna
    línea no alcanza, no cambia nada (BulkInsuficiente antes del commit).
    Devuelve las órdenes que cambiaron, para refrescar sin esperar el poll.
    """
    with _lock_despacho:
        rango_destino = RANGO_ESTADO[estado_destino]
        ordenes = db.scalars(
            select(Orden)
            .options(selectinload(Orden.items))
            .where(Orden.fecha == hoy_lima(), Orden.estado != "anulada")
            .order_by(Orden.numero_orden_dia)
        ).all()

        cambiadas: dict[int, Orden] = {}
        for linea in lineas:
            restante = int(linea["cantidad"])
            pedidas = restante
            for orden in ordenes:
                if restante <= 0:
                    break
                # Copia: partir un ítem agrega a orden.items en plena vuelta
                for item in list(orden.items):
                    if restante <= 0:
                        break
                    if not _coincide(item, linea):
                        continue
                    if RANGO_ESTADO[item.estado] >= rango_destino:
                        continue
                    if item.cantidad <= restante:
                        restante -= item.cantidad
                        item.estado = estado_destino
                    else:
                        _partir_item(orden, item, restante, estado_destino)
                        restante = 0
                    cambiadas[orden.id] = orden
            if restante > 0:
                nombre = linea.get("plato_nombre") or f"plato id {linea.get('plato_id')}"
                # Nada se commiteó: la sesión se descarta y el bulk es atómico
                raise BulkInsuficiente(nombre, pedidas, pedidas - restante)

        for orden in cambiadas.values():
            recalcular_estado_orden(orden)
        db.commit()
        return list(cambiadas.values())
