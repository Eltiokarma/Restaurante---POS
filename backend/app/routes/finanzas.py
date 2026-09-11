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
import unicodedata
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import (
    CostoFijo, EgresoCaja, MovimientoInsumo, Orden, OrdenItem, Plato,
    RecetaItem, Trabajador, hoy_lima,
)
from ..services import consumo as servicio_consumo
from ..services import inventario as servicio_inventario
from ..services import orders as servicio_ordenes

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


# ---------- Tablero: la foto completa del negocio en una pantalla ----------

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


@router.get("/tablero")
def tablero(
    dias: int = Query(default=30, ge=1, le=366),
    desde: date | None = Query(default=None, description="Inicio del rango (manda sobre dias)"),
    hasta: date | None = Query(default=None, description="Fin del rango; por defecto hoy"),
    db: Session = Depends(get_db),
):
    """Todo lo que el tablero pinta, en una sola llamada: los números
    grandes, la venta por día, qué día de la semana vende más, los platos
    que se vendieron y la tabla de insumos ya clasificada (ABC).

    El período se puede pedir de dos maneras: `dias` (los últimos N) o un
    rango exacto `desde`/`hasta` — que es lo que usa el dueño cuando toca
    un día en la gráfica o elige fechas a mano."""
    hasta = hasta or hoy_lima()
    if desde is None:
        desde = hasta - timedelta(days=dias - 1)
    if desde > hasta:
        raise HTTPException(status_code=400, detail="La fecha 'desde' no puede ser posterior a 'hasta'")
    dias = (hasta - desde).days + 1
    if dias > 366:
        raise HTTPException(status_code=400, detail="El rango no puede pasar de un año")

    ventas_dia = dict(db.execute(
        select(Orden.fecha, func.sum(Orden.total))
        .where(Orden.fecha >= desde, Orden.fecha <= hasta, Orden.estado != "anulada")
        .group_by(Orden.fecha)
    ).all())
    egresos_dia = dict(db.execute(
        select(EgresoCaja.fecha, func.sum(EgresoCaja.monto))
        .where(EgresoCaja.fecha >= desde, EgresoCaja.fecha <= hasta)
        .group_by(EgresoCaja.fecha)
    ).all())
    compras_dia = dict(db.execute(
        select(MovimientoInsumo.fecha, func.sum(MovimientoInsumo.costo_total))
        .where(MovimientoInsumo.fecha >= desde, MovimientoInsumo.fecha <= hasta,
               MovimientoInsumo.tipo == "compra")
        .group_by(MovimientoInsumo.fecha)
    ).all())

    por_dia = []
    acumulado_semana = [[0.0, 0] for _ in range(7)]  # [total, días con venta]
    for n in range(dias):
        fecha = desde + timedelta(days=n)
        venta = round(float(ventas_dia.get(fecha) or 0.0), 2)
        por_dia.append({
            "fecha": fecha.isoformat(),
            "etiqueta": f"{fecha.day:02d}/{fecha.month:02d}",
            "dia_semana": DIAS_SEMANA[fecha.weekday()],
            "ventas": venta,
            "egresos": round(float(egresos_dia.get(fecha) or 0.0), 2),
            "compras": round(float(compras_dia.get(fecha) or 0.0), 2),
        })
        if venta > 0:
            acumulado_semana[fecha.weekday()][0] += venta
            acumulado_semana[fecha.weekday()][1] += 1

    # Qué día de la semana vende más (promedio de los días que abrió)
    por_dia_semana = [
        {
            "dia": DIAS_SEMANA[i],
            "total": round(total, 2),
            "veces": veces,
            "promedio": round(total / veces, 2) if veces else 0.0,
        }
        for i, (total, veces) in enumerate(acumulado_semana)
    ]

    # TODOS los platos vendidos, del que más sale al que menos: el dueño
    # mira las dos puntas de la lista (qué se repite y qué casi no se pide).
    top_platos = [
        {"nombre": nombre, "cantidad": int(cantidad or 0), "total": round(float(monto or 0.0), 2)}
        for nombre, cantidad, monto in db.execute(
            select(OrdenItem.nombre_snapshot, func.sum(OrdenItem.cantidad),
                   func.sum(OrdenItem.cantidad * OrdenItem.precio_snapshot))
            .join(Orden, OrdenItem.orden_id == Orden.id)
            .where(Orden.fecha >= desde, Orden.fecha <= hasta, Orden.estado != "anulada",
                   OrdenItem.es_cargo == False)  # noqa: E712
            .group_by(OrdenItem.nombre_snapshot)
            .order_by(func.sum(OrdenItem.cantidad).desc())
        ).all()
    ]

    kardex = servicio_consumo.resumen(db, desde, hasta)
    ventas = round(sum(d["ventas"] for d in por_dia), 2)
    egresos = round(sum(d["egresos"] for d in por_dia), 2)
    compras = round(sum(d["compras"] for d in por_dia), 2)
    dias_con_venta = sum(1 for d in por_dia if d["ventas"] > 0)
    costo = kardex["valor_consumo"]

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "dias": dias,
        "kpis": {
            "ventas": ventas,
            "costo_insumos": costo,
            "mermas": kardex["valor_mermas"],
            "compras": compras,
            "egresos": egresos,
            "margen_pct": round((ventas - costo) / ventas * 100, 1) if ventas > 0 else None,
            "dias_con_venta": dias_con_venta,
            "promedio_dia": round(ventas / dias_con_venta, 2) if dias_con_venta else 0.0,
            "mejor_dia": max((d for d in por_dia), key=lambda d: d["ventas"], default=None),
        },
        "por_dia": por_dia,
        "por_dia_semana": por_dia_semana,
        "top_platos": top_platos,
        "insumos": kardex["insumos"],
    }


# ---------- Ventas anotadas a mano (días en que el POS no se usó) ----------

def _norm(nombre: str) -> str:
    s = unicodedata.normalize("NFD", nombre.lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


class LineaManualIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    cantidad: int = Field(gt=0, le=999)
    # Sin precio: se usa el del plato del catálogo que coincida por nombre
    precio: float | None = Field(default=None, ge=0)


class VentaManualIn(BaseModel):
    fecha: date
    efectivo: float = Field(default=0.0, ge=0, le=100_000)
    tarjeta: float = Field(default=0.0, ge=0, le=100_000)
    yape: float = Field(default=0.0, ge=0, le=100_000)
    lineas: list[LineaManualIn] = Field(default_factory=list, max_length=60)


@router.post("/ventas-manuales", status_code=201)
def registrar_venta_manual(payload: VentaManualIn, db: Session = Depends(get_db)):
    """Registra la venta de UN día contada a mano (cuaderno del dueño).

    Crea una orden "manual" por método de pago con el MONTO DECLARADO
    como total (la autoridad es el cuaderno: los precios por plato de un
    conteo a mano no siempre cuadran con el total real). Las líneas van
    como items de la primera orden: alimentan el ranking de platos y, si
    el plato tiene receta, descuentan el kardex FECHADO en ese día.
    """
    hoy = hoy_lima()
    if payload.fecha > hoy:
        raise HTTPException(status_code=422, detail="La fecha no puede ser futura")
    if payload.fecha < hoy - timedelta(days=366):
        raise HTTPException(status_code=422, detail="Máximo un año hacia atrás")
    montos = [("efectivo", round(payload.efectivo, 2)),
              ("tarjeta", round(payload.tarjeta, 2)),
              ("yape", round(payload.yape, 2))]
    montos = [(m, v) for m, v in montos if v > 0]
    if not montos:
        raise HTTPException(status_code=422, detail="Pon cuánto entró por al menos un método")

    # Resolver líneas contra el catálogo (por nombre, sin tildes)
    platos = {_norm(p.nombre): p for p in db.scalars(select(Plato)).all()}
    resueltas = []
    for linea in payload.lineas:
        plato = platos.get(_norm(linea.nombre))
        precio = linea.precio if linea.precio is not None else (plato.precio if plato else None)
        if precio is None:
            raise HTTPException(
                status_code=422,
                detail=f"'{linea.nombre}' no está en el catálogo: manda su precio",
            )
        resueltas.append((plato, linea.nombre, linea.cantidad, round(precio, 2)))

    # Mismo lock que la creación normal: el correlativo del día es sagrado
    with servicio_ordenes._lock_creacion:
        base = db.scalar(
            select(func.max(Orden.numero_orden_dia)).where(Orden.fecha == payload.fecha)
        ) or 0
        ordenes = []
        for n, (metodo, monto) in enumerate(montos, start=1):
            orden = Orden(
                numero_orden_dia=base + n,
                fecha=payload.fecha,
                hora="14:00:00",
                total=monto,
                estado="entregado",
                impreso=True,
                tipo_servicio="sala",
                origen="manual",
                metodo_pago=metodo,
            )
            db.add(orden)
            ordenes.append(orden)
        db.flush()

        # Todas las líneas en la primera orden (el conteo del día vive una vez)
        principal = ordenes[0]
        for plato, nombre, cantidad, precio in resueltas:
            db.add(OrdenItem(
                orden_id=principal.id,
                plato_id=plato.id if plato else None,
                nombre_snapshot=plato.nombre if plato else nombre,
                precio_snapshot=precio,
                cantidad=cantidad,
                es_cargo=plato is None,
                estado="entregado",
            ))
        db.flush()
        db.refresh(principal)
        servicio_inventario.consumir_por_orden(db, principal, fecha=payload.fecha)
        db.commit()

    ligadas = sum(1 for p, *_ in resueltas if p is not None)
    return {
        "fecha": payload.fecha.isoformat(),
        "ordenes": [{"id": o.id, "numero": o.numero_orden_dia,
                     "metodo_pago": o.metodo_pago, "total": o.total} for o in ordenes],
        "total": round(sum(v for _, v in montos), 2),
        "lineas_ligadas_al_catalogo": ligadas,
        "lineas_libres": len(resueltas) - ligadas,
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
