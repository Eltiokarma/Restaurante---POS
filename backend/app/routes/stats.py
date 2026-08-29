"""Resumen de ventas para el dueño: hoy, semana o rango histórico."""
import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import Cancelacion, Orden, OrdenItem, hoy_lima

router = APIRouter(
    prefix="/api/stats", tags=["stats"], dependencies=[Depends(requiere_admin)]
)

MAX_DIAS_RANGO = 366


def _validar_rango(desde: date, hasta: date) -> None:
    if desde > hasta:
        raise HTTPException(status_code=422, detail="'desde' no puede ser posterior a 'hasta'")
    if (hasta - desde).days >= MAX_DIAS_RANGO:
        raise HTTPException(status_code=422, detail=f"El rango máximo es de {MAX_DIAS_RANGO} días")


def _resumen(db: Session, desde: date, hasta: date) -> dict:
    todas = db.scalars(
        select(Orden).where(Orden.fecha >= desde, Orden.fecha <= hasta)
    ).all()
    # Las anuladas (caja) no cuentan como venta
    ordenes = [o for o in todas if o.estado != "anulada"]
    num_anuladas = len(todas) - len(ordenes)
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
        .where(Orden.fecha >= desde, Orden.fecha <= hasta, Orden.estado != "anulada")
        .group_by(OrdenItem.nombre_snapshot)
        .order_by(func.sum(OrdenItem.cantidad).desc())
    ).all()
    ventas_por_plato = [
        {"nombre": nombre, "cantidad": int(cantidad), "total": round(total, 2)}
        for nombre, cantidad, total in filas
    ]

    # Ventas por día (para el resumen semanal/histórico)
    por_dia: dict[str, dict] = {}
    for o in ordenes:
        clave = o.fecha.isoformat()
        acumulado = por_dia.setdefault(clave, {"fecha": clave, "ordenes": 0, "total": 0.0})
        acumulado["ordenes"] += 1
        acumulado["total"] += o.total
    ventas_por_dia = [
        {**d, "total": round(d["total"], 2)} for _, d in sorted(por_dia.items())
    ]

    # Órdenes por hora agregadas en el rango (para ver la hora punta)
    por_hora: dict[str, int] = {}
    for o in ordenes:
        hora = o.hora[:2]
        por_hora[hora] = por_hora.get(hora, 0) + 1
    ordenes_por_hora = [{"hora": h, "cantidad": c} for h, c in sorted(por_hora.items())]

    cancelaciones = db.scalars(
        select(Cancelacion).where(Cancelacion.fecha >= desde, Cancelacion.fecha <= hasta)
    ).all()
    num_cancelaciones = len(cancelaciones)
    total_cancelado = round(sum(c.total for c in cancelaciones), 2)
    intentos = num_ordenes + num_cancelaciones
    tasa_cancelacion = round(num_cancelaciones / intentos, 3) if intentos else 0.0

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "num_ordenes": num_ordenes,
        "total_vendido": total_vendido,
        "duracion_promedio_seg": duracion_promedio,
        "ventas_por_plato": ventas_por_plato,
        "ventas_por_dia": ventas_por_dia,
        "ordenes_por_hora": ordenes_por_hora,
        "num_cancelaciones": num_cancelaciones,
        "total_cancelado": total_cancelado,
        "tasa_cancelacion": tasa_cancelacion,
        "num_anuladas": num_anuladas,
    }


@router.get("/today")
def resumen_de_hoy(db: Session = Depends(get_db)):
    hoy = hoy_lima()
    return {"fecha": hoy.isoformat(), **_resumen(db, hoy, hoy)}


@router.get("/range")
def resumen_de_rango(
    desde: date = Query(...),
    hasta: date = Query(...),
    db: Session = Depends(get_db),
):
    """Resumen de un rango de fechas, p. ej. la semana o el mes."""
    _validar_rango(desde, hasta)
    return _resumen(db, desde, hasta)


@router.get("/export")
def exportar_csv(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Ventas en CSV (una fila por item de orden), para abrir en Excel.

    Sin parámetros exporta el día de hoy; con ``desde``/``hasta`` exporta
    el rango completo.
    """
    hoy = hoy_lima()
    desde = desde or hoy
    hasta = hasta or desde
    _validar_rango(desde, hasta)

    filas = db.execute(
        select(Orden, OrdenItem)
        .join(OrdenItem, OrdenItem.orden_id == Orden.id)
        .where(Orden.fecha >= desde, Orden.fecha <= hasta)
        .order_by(Orden.fecha, Orden.numero_orden_dia)
    ).all()

    buffer = io.StringIO()
    # Separador ";" y BOM: así Excel en español lo abre en columnas directamente
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([
        "fecha", "orden", "hora", "estado", "servicio", "origen", "pago", "plato",
        "empaque", "cantidad", "precio_unitario", "subtotal", "total_orden", "duracion_seg",
    ])
    for orden, item in filas:
        writer.writerow([
            orden.fecha.isoformat(),
            orden.numero_orden_dia,
            orden.hora,
            orden.estado,
            orden.tipo_servicio,
            orden.origen,
            orden.metodo_pago or "",
            item.nombre_snapshot,
            item.empaque,
            item.cantidad,
            f"{item.precio_snapshot:.2f}",
            f"{item.precio_snapshot * item.cantidad:.2f}",
            f"{orden.total:.2f}",
            orden.duracion_seg if orden.duracion_seg is not None else "",
        ])

    nombre = (
        f"ventas-{desde.isoformat()}.csv"
        if desde == hasta
        else f"ventas-{desde.isoformat()}-a-{hasta.isoformat()}.csv"
    )
    contenido = "\ufeff" + buffer.getvalue()  # BOM: Excel detecta UTF-8
    return StreamingResponse(
        iter([contenido]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


def rango_ultimos_dias(dias: int) -> tuple[date, date]:
    """Utilidad para tests y consumidores: [hoy - (dias-1), hoy]."""
    hoy = hoy_lima()
    return hoy - timedelta(days=dias - 1), hoy
