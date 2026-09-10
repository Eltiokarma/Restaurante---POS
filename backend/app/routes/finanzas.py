"""Finanzas del negocio, en el idioma del dueño.

Junta lo que el sistema ya sabe (ventas, egresos del cajón, compras y
consumo del kardex) con lo que solo el dueño sabe (costos fijos del mes
y planilla) y responde las tres preguntas que importan:

- ¿Cuánta plata entró y salió cada día? (flujo de caja)
- ¿Estoy ganando o perdiendo? (utilidad estimada del período)
- ¿Cuánto tengo que vender al día para no perder? (punto de equilibrio)

La utilidad usa el CONSUMO TEÓRICO de insumos (recetas × ventas): si
pocas recetas están armadas, el resumen lo avisa con la cobertura.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import (
    CostoFijo, EgresoCaja, MovimientoInsumo, Orden, Plato, RecetaItem,
    Trabajador, hoy_lima,
)
from ..services import consumo as servicio_consumo

router = APIRouter(
    prefix="/api/finanzas", tags=["finanzas"], dependencies=[Depends(requiere_admin)]
)

DIAS_DEL_MES = 30  # prorrateo simple: un mes de fonda son ~30 días


class CostoFijoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    monto_mensual: float = Field(gt=0, le=1_000_000)


class TrabajadorIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    rol: str = Field(default="", max_length=60)
    sueldo_mensual: float = Field(gt=0, le=1_000_000)


def _costo_a_dict(c: CostoFijo) -> dict:
    return {"id": c.id, "nombre": c.nombre, "monto_mensual": round(c.monto_mensual, 2)}


def _trabajador_a_dict(t: Trabajador) -> dict:
    return {"id": t.id, "nombre": t.nombre, "rol": t.rol,
            "sueldo_mensual": round(t.sueldo_mensual, 2)}


def _fijos(db: Session) -> dict:
    costos = db.scalars(
        select(CostoFijo).where(CostoFijo.activo == True).order_by(CostoFijo.nombre)  # noqa: E712
    ).all()
    planilla = db.scalars(
        select(Trabajador).where(Trabajador.activo == True).order_by(Trabajador.nombre)  # noqa: E712
    ).all()
    return {
        "costos": [_costo_a_dict(c) for c in costos],
        "trabajadores": [_trabajador_a_dict(t) for t in planilla],
        "total_costos_mes": round(sum(c.monto_mensual for c in costos), 2),
        "total_planilla_mes": round(sum(t.sueldo_mensual for t in planilla), 2),
    }


# ---------- Costos fijos ----------

@router.get("/fijos")
def leer_fijos(db: Session = Depends(get_db)):
    return _fijos(db)


@router.post("/costos-fijos", status_code=201)
def crear_costo(payload: CostoFijoIn, db: Session = Depends(get_db)):
    db.add(CostoFijo(nombre=payload.nombre.strip(), monto_mensual=payload.monto_mensual))
    db.commit()
    return _fijos(db)


@router.put("/costos-fijos/{costo_id}")
def editar_costo(costo_id: int, payload: CostoFijoIn, db: Session = Depends(get_db)):
    costo = db.get(CostoFijo, costo_id)
    if costo is None or not costo.activo:
        raise HTTPException(status_code=404, detail="Ese costo fijo ya no existe")
    costo.nombre = payload.nombre.strip()
    costo.monto_mensual = payload.monto_mensual
    db.commit()
    return _fijos(db)


@router.delete("/costos-fijos/{costo_id}")
def borrar_costo(costo_id: int, db: Session = Depends(get_db)):
    costo = db.get(CostoFijo, costo_id)
    if costo is not None:
        costo.activo = False  # se apaga, no se borra (histórico simple)
        db.commit()
    return _fijos(db)


# ---------- Planilla ----------

@router.post("/planilla", status_code=201)
def crear_trabajador(payload: TrabajadorIn, db: Session = Depends(get_db)):
    db.add(Trabajador(
        nombre=payload.nombre.strip(), rol=payload.rol.strip(),
        sueldo_mensual=payload.sueldo_mensual,
    ))
    db.commit()
    return _fijos(db)


@router.put("/planilla/{trabajador_id}")
def editar_trabajador(trabajador_id: int, payload: TrabajadorIn, db: Session = Depends(get_db)):
    t = db.get(Trabajador, trabajador_id)
    if t is None or not t.activo:
        raise HTTPException(status_code=404, detail="Ese trabajador ya no está en la planilla")
    t.nombre = payload.nombre.strip()
    t.rol = payload.rol.strip()
    t.sueldo_mensual = payload.sueldo_mensual
    db.commit()
    return _fijos(db)


@router.delete("/planilla/{trabajador_id}")
def borrar_trabajador(trabajador_id: int, db: Session = Depends(get_db)):
    t = db.get(Trabajador, trabajador_id)
    if t is not None:
        t.activo = False
        db.commit()
    return _fijos(db)


# ---------- El resumen financiero ----------

@router.get("/resumen")
def resumen_financiero(
    dias: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db),
):
    hasta = hoy_lima()
    desde = hasta - timedelta(days=dias - 1)

    # Plata que ENTRÓ: ventas por día (anuladas fuera)
    ventas_por_dia = dict(db.execute(
        select(Orden.fecha, func.sum(Orden.total))
        .where(Orden.fecha >= desde, Orden.fecha <= hasta, Orden.estado != "anulada")
        .group_by(Orden.fecha)
    ).all())

    # Plata que SALIÓ: egresos del cajón + compras de insumos, por día
    egresos_por_dia = dict(db.execute(
        select(EgresoCaja.fecha, func.sum(EgresoCaja.monto))
        .where(EgresoCaja.fecha >= desde, EgresoCaja.fecha <= hasta)
        .group_by(EgresoCaja.fecha)
    ).all())
    compras_por_dia = dict(db.execute(
        select(MovimientoInsumo.fecha, func.sum(MovimientoInsumo.costo_total))
        .where(MovimientoInsumo.fecha >= desde, MovimientoInsumo.fecha <= hasta,
               MovimientoInsumo.tipo == "compra")
        .group_by(MovimientoInsumo.fecha)
    ).all())

    por_dia = []
    for n in range(dias):
        fecha = desde + timedelta(days=n)
        por_dia.append({
            "fecha": fecha.isoformat(),
            "entro": round(float(ventas_por_dia.get(fecha) or 0.0), 2),
            "egresos": round(float(egresos_por_dia.get(fecha) or 0.0), 2),
            "compras": round(float(compras_por_dia.get(fecha) or 0.0), 2),
        })

    ventas = round(sum(d["entro"] for d in por_dia), 2)
    egresos = round(sum(d["egresos"] for d in por_dia), 2)
    compras = round(sum(d["compras"] for d in por_dia), 2)
    dias_con_venta = sum(1 for d in por_dia if d["entro"] > 0)

    # Costo de insumos: el consumo TEÓRICO valorizado (recetas × ventas)
    kardex = servicio_consumo.resumen(db, desde, hasta)
    costo_insumos = kardex["valor_consumo"]
    mermas = kardex["valor_mermas"]

    fijos = _fijos(db)
    fijos_mes = round(fijos["total_costos_mes"] + fijos["total_planilla_mes"], 2)
    fijos_dia = fijos_mes / DIAS_DEL_MES
    fijos_periodo = round(fijos_dia * dias, 2)

    utilidad = round(ventas - costo_insumos - mermas - fijos_periodo, 2)
    margen_pct = round((ventas - costo_insumos) / ventas * 100, 1) if ventas > 0 else None

    # Punto de equilibrio: cuánto hay que vender AL DÍA para cubrir los
    # fijos, al margen del período. Sin margen no hay cálculo honesto.
    venta_diaria_necesaria = None
    if margen_pct is not None and margen_pct > 0:
        venta_diaria_necesaria = round(fijos_dia / (margen_pct / 100), 2)
    promedio_venta_dia = round(ventas / dias_con_venta, 2) if dias_con_venta else 0.0

    # Salidas del cajón agrupadas por categoría (para el análisis)
    egresos_por_categoria = [
        {"categoria": cat, "monto": round(float(monto or 0.0), 2)}
        for cat, monto in db.execute(
            select(EgresoCaja.categoria, func.sum(EgresoCaja.monto))
            .where(EgresoCaja.fecha >= desde, EgresoCaja.fecha <= hasta)
            .group_by(EgresoCaja.categoria)
            .order_by(func.sum(EgresoCaja.monto).desc())
        ).all()
    ]

    # De dónde entró la plata: por método de pago (lo aún no cobrado, aparte)
    entradas_por_metodo: dict[str, float] = {}
    for metodo, monto in db.execute(
        select(Orden.metodo_pago, func.sum(Orden.total))
        .where(Orden.fecha >= desde, Orden.fecha <= hasta, Orden.estado != "anulada")
        .group_by(Orden.metodo_pago)
    ).all():
        clave = metodo or "sin_cobrar"
        entradas_por_metodo[clave] = round(
            entradas_por_metodo.get(clave, 0.0) + float(monto or 0.0), 2
        )

    # Cobertura de recetas: qué tan confiable es el costo de insumos
    activos = db.scalars(
        select(Plato.id).where(Plato.activo_hoy == True, Plato.categoria != "bebida")  # noqa: E712
    ).all()
    con_receta = set(db.scalars(select(RecetaItem.plato_id).distinct()).all())
    cobertura = {
        "activos": len(activos),
        "con_receta": sum(1 for pid in activos if pid in con_receta),
    }

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "dias": dias,
        "ventas": ventas,
        "costo_insumos": costo_insumos,
        "mermas": mermas,
        "compras_insumos": compras,
        "egresos_caja": egresos,
        "costos_fijos_mes": fijos["total_costos_mes"],
        "planilla_mes": fijos["total_planilla_mes"],
        "fijos_periodo": fijos_periodo,
        "utilidad_estimada": utilidad,
        "margen_pct": margen_pct,
        "venta_diaria_necesaria": venta_diaria_necesaria,
        "promedio_venta_dia": promedio_venta_dia,
        "dias_con_venta": dias_con_venta,
        "cobertura_recetas": cobertura,
        "egresos_por_categoria": egresos_por_categoria,
        "entradas_por_metodo": entradas_por_metodo,
        "por_dia": por_dia,
    }


# ---------- Flujo de caja agrupado (día / semana / mes / año) ----------

MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]


@router.get("/flujo")
def flujo_de_caja(
    agrupar: str = Query(default="dia", pattern="^(dia|semana|mes|anio)$"),
    db: Session = Depends(get_db),
):
    """Lo que entró (ventas) y salió (egresos + compras) agrupado como el
    dueño quiera mirarlo: por día, semana, mes o año."""
    hasta = hoy_lima()
    if agrupar == "dia":
        desde = hasta - timedelta(days=29)
    elif agrupar == "semana":
        desde = hasta - timedelta(days=7 * 26 - 1)
    elif agrupar == "mes":
        desde = hasta - timedelta(days=365)
    else:  # anio: desde el primer dato que exista
        primera = db.scalar(select(func.min(Orden.fecha)))
        desde = primera or hasta

    ventas = dict(db.execute(
        select(Orden.fecha, func.sum(Orden.total))
        .where(Orden.fecha >= desde, Orden.fecha <= hasta, Orden.estado != "anulada")
        .group_by(Orden.fecha)
    ).all())
    egresos = dict(db.execute(
        select(EgresoCaja.fecha, func.sum(EgresoCaja.monto))
        .where(EgresoCaja.fecha >= desde, EgresoCaja.fecha <= hasta)
        .group_by(EgresoCaja.fecha)
    ).all())
    compras = dict(db.execute(
        select(MovimientoInsumo.fecha, func.sum(MovimientoInsumo.costo_total))
        .where(MovimientoInsumo.fecha >= desde, MovimientoInsumo.fecha <= hasta,
               MovimientoInsumo.tipo == "compra")
        .group_by(MovimientoInsumo.fecha)
    ).all())

    def clave_y_etiqueta(fecha):
        if agrupar == "dia":
            return fecha.isoformat(), f"{fecha.day:02d}/{fecha.month:02d}"
        if agrupar == "semana":
            lunes = fecha - timedelta(days=fecha.weekday())
            return lunes.isoformat(), f"Sem {lunes.day:02d}/{lunes.month:02d}"
        if agrupar == "mes":
            return f"{fecha.year}-{fecha.month:02d}", f"{MESES_CORTOS[fecha.month - 1]} {fecha.year}"
        return str(fecha.year), str(fecha.year)

    filas: dict[str, dict] = {}
    dias_totales = (hasta - desde).days + 1
    for n in range(dias_totales):
        fecha = desde + timedelta(days=n)
        clave, etiqueta = clave_y_etiqueta(fecha)
        fila = filas.setdefault(clave, {
            "etiqueta": etiqueta, "desde": fecha.isoformat(), "hasta": fecha.isoformat(),
            "entro": 0.0, "egresos": 0.0, "compras": 0.0,
        })
        fila["hasta"] = fecha.isoformat()
        fila["entro"] += float(ventas.get(fecha) or 0.0)
        fila["egresos"] += float(egresos.get(fecha) or 0.0)
        fila["compras"] += float(compras.get(fecha) or 0.0)

    resultado = []
    for clave in sorted(filas):
        f = filas[clave]
        resultado.append({**f, "entro": round(f["entro"], 2),
                          "egresos": round(f["egresos"], 2),
                          "compras": round(f["compras"], 2)})
    return {"agrupar": agrupar, "filas": resultado}
