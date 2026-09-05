"""Apertura y cierre de caja.

Flujo: al empezar el servicio, el cajero abre la caja con el fondo
inicial (sencillo para vueltos). Al terminar, cuenta el efectivo y
cierra: el sistema calcula lo esperado (fondo + ventas del tramo) y la
diferencia. Puede haber VARIAS cajas en un mismo día (turnos): cerrada
una, se puede abrir la siguiente, y cada una cuadra solo con las ventas
de su tramo del día. El cierre se puede corregir re-cerrando.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import CierreCaja, Orden, ahora_lima, hoy_lima

router = APIRouter(prefix="/api/caja", tags=["caja"])


class AperturaIn(BaseModel):
    monto_apertura: float = Field(ge=0, le=10_000)
    notas: str = ""


class CierreIn(BaseModel):
    monto_contado: float = Field(ge=0, le=100_000)
    notas: str = ""


def _ventas_de_hoy(db: Session, desde_id: int | None = None) -> dict:
    """Ventas del día desglosadas por método de pago.

    `desde_id` acota a las órdenes posteriores a una caja anterior del
    día (turnos): así cada caja cuadra solo con las ventas de su tramo y
    ninguna venta queda fuera. None = todo el día (la primera caja).

    Una orden sin método registrado se asume EFECTIVO (comportamiento
    histórico: si la caja no usa los botones de cobro, el cierre sigue
    cuadrando como antes).
    """
    ordenes = [
        o for o in db.scalars(select(Orden).where(Orden.fecha == hoy_lima())).all()
        if o.estado != "anulada" and (desde_id is None or o.id > desde_id)
    ]
    efectivo = sum(o.total for o in ordenes if o.metodo_pago in (None, "efectivo"))
    tarjeta = sum(o.total for o in ordenes if o.metodo_pago == "tarjeta")
    yape = sum(o.total for o in ordenes if o.metodo_pago == "yape")
    return {
        "total_vendido": round(efectivo + tarjeta + yape, 2),
        "ventas_efectivo": round(efectivo, 2),
        "ventas_tarjeta": round(tarjeta, 2),
        "ventas_yape": round(yape, 2),
        "sin_registrar": sum(1 for o in ordenes if o.metodo_pago is None),
    }


def _a_dict(registro: CierreCaja | None, ventas: dict, turno: int = 1) -> dict:
    base = {"abierta": False, "cerrada": False, "ventas_despues_del_cierre": False, **ventas}
    if registro is None:
        return base

    cerrada = registro.hora_cierre is not None
    if cerrada:
        # Con la caja cerrada se muestra el SNAPSHOT del cierre (lo que se
        # cuadró), no las ventas vivas: así los números son consistentes
        # con la diferencia guardada. Si llegaron ventas después, se avisa
        # para que el cajero corrija el conteo (re-cerrar).
        base.update({
            "total_vendido": registro.total_sistema or 0.0,
            # Cierres anteriores a la migración: todo su total fue efectivo
            "ventas_efectivo": (
                registro.ventas_efectivo
                if registro.ventas_efectivo is not None
                else (registro.total_sistema or 0.0)
            ),
            "ventas_tarjeta": registro.ventas_tarjeta or 0.0,
            "ventas_yape": registro.ventas_yape or 0.0,
            "ventas_despues_del_cierre": round(ventas["total_vendido"], 2)
            != round(registro.total_sistema or 0.0, 2),
        })

    # Descuadre con signo y magnitud SEPARADOS (§4): el cliente lo muestra
    # como cifra grande sin reconstruir el signo
    descuadre = None
    if registro.diferencia is not None:
        descuadre = {
            "tipo": (
                "exacta" if registro.diferencia == 0
                else "sobra" if registro.diferencia > 0
                else "falta"
            ),
            "monto": round(abs(registro.diferencia), 2),
        }

    return {
        **base,
        "abierta": not cerrada,
        "cerrada": cerrada,
        "turno": turno,
        "fecha": registro.fecha.isoformat(),
        "hora_apertura": registro.hora_apertura,
        "monto_apertura": registro.monto_apertura,
        "hora_cierre": registro.hora_cierre,
        "monto_contado": registro.monto_contado,
        "total_sistema": registro.total_sistema,
        "diferencia": registro.diferencia,
        "descuadre": descuadre,
        "notas": registro.notas,
    }


def _registros_de_hoy(db: Session) -> list[CierreCaja]:
    return list(db.scalars(
        select(CierreCaja).where(CierreCaja.fecha == hoy_lima()).order_by(CierreCaja.id)
    ))


def _turno_actual(db: Session) -> tuple[CierreCaja | None, int]:
    """La caja vigente del día (la última) y su número de turno.

    Las cajas anteriores ya quedaron cuadradas: su tramo termina donde
    empieza el de la siguiente (desde_orden_id).
    """
    registros = _registros_de_hoy(db)
    if not registros:
        return None, 0
    return registros[-1], len(registros)


@router.get("/hoy")
def estado_de_hoy(db: Session = Depends(get_db)):
    registro, turno = _turno_actual(db)
    desde_id = registro.desde_orden_id if registro is not None else None
    return _a_dict(registro, _ventas_de_hoy(db, desde_id), turno)


@router.post("/abrir", status_code=201)
def abrir(payload: AperturaIn, db: Session = Depends(get_db)):
    ultimo, turnos = _turno_actual(db)
    if ultimo is not None and ultimo.hora_cierre is None:
        raise HTTPException(
            status_code=409, detail="La caja ya está abierta; ciérrala antes de abrir otra"
        )
    ahora = ahora_lima()
    # Segunda caja del día en adelante: lo vendido hasta ahora quedó
    # cuadrado en la anterior; esta arranca desde la última orden del día
    desde_id = None
    if ultimo is not None:
        desde_id = db.scalar(
            select(func.max(Orden.id)).where(Orden.fecha == hoy_lima())
        )
    registro = CierreCaja(
        fecha=ahora.date(),
        desde_orden_id=desde_id,
        hora_apertura=ahora.strftime("%H:%M:%S"),
        monto_apertura=round(payload.monto_apertura, 2),
        notas=payload.notas.strip(),
    )
    db.add(registro)
    db.commit()
    return _a_dict(registro, _ventas_de_hoy(db, desde_id), turnos + 1)


@router.post("/cerrar")
def cerrar(payload: CierreIn, db: Session = Depends(get_db)):
    """Cierra la caja del día. El conteo de efectivo se cuadra SOLO contra
    el efectivo esperado (fondo + ventas en efectivo del tramo); tarjeta y
    Yape se reportan aparte. Re-cerrar actualiza el conteo (corrección)."""
    registro, turno = _turno_actual(db)
    if registro is None:
        raise HTTPException(status_code=409, detail="La caja de hoy no está abierta todavía")

    ventas = _ventas_de_hoy(db, registro.desde_orden_id)
    esperado_efectivo = round(registro.monto_apertura + ventas["ventas_efectivo"], 2)
    registro.hora_cierre = ahora_lima().strftime("%H:%M:%S")
    registro.monto_contado = round(payload.monto_contado, 2)
    registro.total_sistema = ventas["total_vendido"]
    registro.ventas_efectivo = ventas["ventas_efectivo"]
    registro.ventas_tarjeta = ventas["ventas_tarjeta"]
    registro.ventas_yape = ventas["ventas_yape"]
    registro.diferencia = round(registro.monto_contado - esperado_efectivo, 2)
    if payload.notas.strip():
        registro.notas = payload.notas.strip()
    db.commit()
    return _a_dict(registro, ventas, turno)


class FondoIn(BaseModel):
    monto_apertura: float = Field(ge=0, le=10_000)


@router.post("/reabrir")
def reabrir(db: Session = Depends(get_db)):
    """Deshace el cierre del día: la caja queda abierta otra vez.

    Para el caso real del local: se cerró por error (o en una demo) y hay
    que seguir operando el día normal. Las ventas nunca se tocan; solo se
    borra el conteo, que se vuelve a hacer al cierre de verdad. Con varias
    cajas en el día, se reabre la última."""
    registro, turno = _turno_actual(db)
    if registro is None:
        raise HTTPException(status_code=409, detail="La caja de hoy no está abierta todavía")
    if registro.hora_cierre is None:
        raise HTTPException(status_code=409, detail="La caja de hoy no está cerrada")
    registro.hora_cierre = None
    registro.monto_contado = None
    registro.total_sistema = None
    registro.ventas_efectivo = None
    registro.ventas_tarjeta = None
    registro.ventas_yape = None
    registro.diferencia = None
    db.commit()
    return _a_dict(registro, _ventas_de_hoy(db, registro.desde_orden_id), turno)


@router.put("/apertura")
def corregir_fondo(payload: FondoIn, db: Session = Depends(get_db)):
    """Corrige el fondo inicial de la caja de hoy (abierta o cerrada).

    Si ya se cerró, el descuadre se recalcula con el fondo nuevo sobre el
    snapshot del cierre (el conteo hecho no se pierde)."""
    registro, turno = _turno_actual(db)
    if registro is None:
        raise HTTPException(status_code=409, detail="La caja de hoy no está abierta todavía")
    registro.monto_apertura = round(payload.monto_apertura, 2)
    if registro.hora_cierre is not None and registro.monto_contado is not None:
        esperado_efectivo = round(
            registro.monto_apertura + (registro.ventas_efectivo or 0.0), 2
        )
        registro.diferencia = round(registro.monto_contado - esperado_efectivo, 2)
    db.commit()
    return _a_dict(registro, _ventas_de_hoy(db, registro.desde_orden_id), turno)


@router.get("/historial", dependencies=[Depends(requiere_admin)])
def historial(db: Session = Depends(get_db)):
    """Últimos 30 cierres, para el admin. Un día con varias cajas sale
    con una fila por caja, numeradas por turno."""
    registros = db.scalars(
        select(CierreCaja).order_by(CierreCaja.fecha.desc(), CierreCaja.id.desc()).limit(30)
    ).all()
    # Número de turno dentro de su día (1 = la primera caja de esa fecha)
    pares = db.execute(
        select(CierreCaja.fecha, CierreCaja.id)
        .where(CierreCaja.fecha.in_({r.fecha for r in registros}))
    ).all()
    turno_de: dict[int, int] = {}
    visto: dict = {}
    for fecha, id_ in sorted(pares):
        visto[fecha] = visto.get(fecha, 0) + 1
        turno_de[id_] = visto[fecha]
    return {"cierres": [
        _a_dict(r, {
            "total_vendido": r.total_sistema or 0.0,
            # Cierres previos a la migración (columnas NULL): por la
            # semántica histórica, todo su total fue efectivo
            "ventas_efectivo": (
                r.ventas_efectivo if r.ventas_efectivo is not None else (r.total_sistema or 0.0)
            ),
            "ventas_tarjeta": r.ventas_tarjeta or 0.0,
            "ventas_yape": r.ventas_yape or 0.0,
            "sin_registrar": 0,
        }, turno_de.get(r.id, 1))
        for r in registros
    ]}
