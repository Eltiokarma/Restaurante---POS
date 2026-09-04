"""Reporte de consumo del kardex: qué se usó, se compró y se perdió.

Responde la pregunta del dueño al cerrar la semana: "¿en qué se me fue la
plata y qué se me está acabando?". Agrega los movimientos del rango por
insumo y los valoriza con el costo promedio VIGENTE del insumo (no el
histórico de cada compra): es una aproximación suficiente para decidir
compras y detectar mermas raras, no un costeo contable.

Ojo con las anulaciones: devolver el stock de una orden anulada se
registra como "ajuste" ligado a esa orden, así que el consumo real del
rango es (consumos) menos (esas devoluciones). Los ajustes por conteo
físico —los que no vienen de una orden— van en su propia columna.
"""
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Insumo, MovimientoInsumo, hoy_lima

MAX_DIAS_RANGO = 366


def rango_por_defecto() -> tuple[date, date]:
    """Últimos 7 días (incluye hoy), en zona horaria de Lima."""
    hoy = hoy_lima()
    return hoy - timedelta(days=6), hoy


def _dias_stock(stock: float, consumido: float, dias: int) -> float | None:
    """Para cuántos días alcanza el stock al ritmo de consumo del rango."""
    if consumido <= 0 or dias <= 0:
        return None  # sin consumo no se puede proyectar
    return round(max(stock, 0.0) / (consumido / dias), 1)


def resumen(db: Session, desde: date, hasta: date) -> dict:
    """Consumo, compras, mermas y conteos por insumo dentro del rango."""
    dias = (hasta - desde).days + 1
    de_orden = MovimientoInsumo.orden_id.is_not(None)

    # Un solo SELECT agrupado: insumo × tipo × (viene de una orden o no)
    filas = db.execute(
        select(
            MovimientoInsumo.insumo_id,
            MovimientoInsumo.tipo,
            de_orden.label("de_orden"),
            func.sum(MovimientoInsumo.cantidad),
            func.sum(MovimientoInsumo.costo_total),
        )
        .where(MovimientoInsumo.fecha >= desde, MovimientoInsumo.fecha <= hasta)
        .group_by(MovimientoInsumo.insumo_id, MovimientoInsumo.tipo, de_orden)
    ).all()

    acumulado: dict[int, dict[str, float]] = {}
    for insumo_id, tipo, viene_de_orden, cantidad, costo in filas:
        datos = acumulado.setdefault(
            insumo_id,
            {"consumido": 0.0, "comprado": 0.0, "comprado_soles": 0.0,
             "merma": 0.0, "ajuste": 0.0},
        )
        cantidad = float(cantidad or 0.0)
        if tipo == "consumo":
            datos["consumido"] += -cantidad          # los consumos son negativos
        elif tipo == "compra":
            datos["comprado"] += cantidad
            datos["comprado_soles"] += float(costo or 0.0)
        elif tipo == "merma":
            datos["merma"] += -cantidad
        elif tipo == "ajuste":
            if viene_de_orden:
                datos["consumido"] -= cantidad       # devolución por anulación
            else:
                datos["ajuste"] += cantidad          # conteo físico, con signo

    insumos = {i.id: i for i in db.scalars(select(Insumo)).all()}
    detalle = []
    for insumo_id, datos in acumulado.items():
        insumo = insumos.get(insumo_id)
        if insumo is None:
            continue
        # Nunca negativo: si en el rango cae la anulación de una orden que se
        # consumió ANTES, lo devuelto se descuenta hasta cero, no más allá
        # (un "se usó -0.5 kg" no significaría nada para el dueño).
        consumido = round(max(datos["consumido"], 0.0), 3)
        merma = round(datos["merma"], 3)
        detalle.append({
            "id": insumo.id,
            "nombre": insumo.nombre,
            "unidad": insumo.unidad,
            "consumido": consumido,
            "consumido_soles": round(consumido * insumo.costo_unitario, 2),
            "comprado": round(datos["comprado"], 3),
            "comprado_soles": round(datos["comprado_soles"], 2),
            "merma": merma,
            "merma_soles": round(merma * insumo.costo_unitario, 2),
            "ajuste": round(datos["ajuste"], 3),
            "stock_actual": round(insumo.stock_actual, 3),
            "bajo_minimo": bajo_minimo(insumo),
            "dias_stock": _dias_stock(insumo.stock_actual, consumido, dias),
        })
    detalle.sort(key=lambda d: (-d["consumido_soles"], d["nombre"]))

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "dias": dias,
        "gasto_compras": round(sum(d["comprado_soles"] for d in detalle), 2),
        "valor_consumo": round(sum(d["consumido_soles"] for d in detalle), 2),
        "valor_mermas": round(sum(d["merma_soles"] for d in detalle), 2),
        "por_agotarse": [i.nombre for i in insumos.values() if bajo_minimo(i)],
        "por_dia": _consumo_por_dia(db, desde, hasta, insumos),
        "insumos": detalle,
    }


def _consumo_por_dia(db: Session, desde: date, hasta: date,
                     insumos: dict[int, Insumo]) -> list[dict]:
    """Soles consumidos por día (días sin movimiento salen en cero)."""
    de_orden = MovimientoInsumo.orden_id.is_not(None)
    filas = db.execute(
        select(
            MovimientoInsumo.fecha,
            MovimientoInsumo.insumo_id,
            func.sum(MovimientoInsumo.cantidad),
        )
        .where(
            MovimientoInsumo.fecha >= desde,
            MovimientoInsumo.fecha <= hasta,
            (MovimientoInsumo.tipo == "consumo") | de_orden,
        )
        .group_by(MovimientoInsumo.fecha, MovimientoInsumo.insumo_id)
    ).all()

    soles: dict[date, float] = {}
    for fecha, insumo_id, cantidad in filas:
        insumo = insumos.get(insumo_id)
        if insumo is None:
            continue
        soles[fecha] = soles.get(fecha, 0.0) + -float(cantidad or 0.0) * insumo.costo_unitario

    dias = (hasta - desde).days + 1
    return [
        {
            "fecha": (desde + timedelta(days=n)).isoformat(),
            # Un día con más devoluciones que consumos vale cero, no negativo
            "soles": round(max(soles.get(desde + timedelta(days=n), 0.0), 0.0), 2),
        }
        for n in range(dias)
    ]


def bajo_minimo(insumo: Insumo) -> bool:
    """Se está acabando: hay aviso configurado y el stock ya lo alcanzó."""
    return insumo.activo and insumo.stock_minimo > 0 and insumo.stock_actual <= insumo.stock_minimo
