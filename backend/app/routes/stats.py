"""Resumen del día para el dueño: ventas, platos, cancelaciones y tiempos."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import Cancelacion, Orden, OrdenItem, hoy_lima

router = APIRouter(
    prefix="/api/stats", tags=["stats"], dependencies=[Depends(requiere_admin)]
)


@router.get("/today")
def resumen_de_hoy(db: Session = Depends(get_db)):
    hoy = hoy_lima()

    ordenes = db.scalars(select(Orden).where(Orden.fecha == hoy)).all()
    num_ordenes = len(ordenes)
    total_vendido = round(sum(o.total for o in ordenes), 2)

    duraciones = [o.duracion_seg for o in ordenes if o.duracion_seg is not None]
    duracion_promedio = round(sum(duraciones) / len(duraciones)) if duraciones else None

    # Ventas por plato (sobre los snapshots, así el histórico es fiel)
    filas = db.execute(
        select(
            OrdenItem.nombre_snapshot,
            func.sum(OrdenItem.cantidad),
            func.sum(OrdenItem.cantidad * OrdenItem.precio_snapshot),
        )
        .join(Orden, OrdenItem.orden_id == Orden.id)
        .where(Orden.fecha == hoy)
        .group_by(OrdenItem.nombre_snapshot)
        .order_by(func.sum(OrdenItem.cantidad).desc())
    ).all()
    ventas_por_plato = [
        {"nombre": nombre, "cantidad": int(cantidad), "total": round(total, 2)}
        for nombre, cantidad, total in filas
    ]

    # Órdenes por hora del día (para ver la hora punta)
    por_hora: dict[str, int] = {}
    for o in ordenes:
        hora = o.hora[:2]
        por_hora[hora] = por_hora.get(hora, 0) + 1
    ordenes_por_hora = [
        {"hora": h, "cantidad": c} for h, c in sorted(por_hora.items())
    ]

    cancelaciones = db.scalars(select(Cancelacion).where(Cancelacion.fecha == hoy)).all()
    num_cancelaciones = len(cancelaciones)
    total_cancelado = round(sum(c.total for c in cancelaciones), 2)
    intentos = num_ordenes + num_cancelaciones
    tasa_cancelacion = round(num_cancelaciones / intentos, 3) if intentos else 0.0

    return {
        "fecha": hoy.isoformat(),
        "num_ordenes": num_ordenes,
        "total_vendido": total_vendido,
        "duracion_promedio_seg": duracion_promedio,
        "ventas_por_plato": ventas_por_plato,
        "ordenes_por_hora": ordenes_por_hora,
        "num_cancelaciones": num_cancelaciones,
        "total_cancelado": total_cancelado,
        "tasa_cancelacion": tasa_cancelacion,
    }


@router.get("/export")
def exportar_csv(db: Session = Depends(get_db)):
    """Ventas de hoy en CSV (una fila por item de orden), para abrir en Excel."""
    hoy = hoy_lima()
    filas = db.execute(
        select(Orden, OrdenItem)
        .join(OrdenItem, OrdenItem.orden_id == Orden.id)
        .where(Orden.fecha == hoy)
        .order_by(Orden.numero_orden_dia)
    ).all()

    buffer = io.StringIO()
    # Separador ";" y BOM: así Excel en español lo abre en columnas directamente
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([
        "fecha", "orden", "hora", "estado", "plato", "cantidad",
        "precio_unitario", "subtotal", "total_orden", "duracion_seg",
    ])
    for orden, item in filas:
        writer.writerow([
            orden.fecha.isoformat(),
            orden.numero_orden_dia,
            orden.hora,
            orden.estado,
            item.nombre_snapshot,
            item.cantidad,
            f"{item.precio_snapshot:.2f}",
            f"{item.precio_snapshot * item.cantidad:.2f}",
            f"{orden.total:.2f}",
            orden.duracion_seg if orden.duracion_seg is not None else "",
        ])

    contenido = "\ufeff" + buffer.getvalue()  # BOM: Excel detecta UTF-8
    return StreamingResponse(
        iter([contenido]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="ventas-{hoy.isoformat()}.csv"'
        },
    )
