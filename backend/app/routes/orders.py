from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

import json
from datetime import date, datetime, time

from sqlalchemy import update

from ..db import get_db
from ..models import LIMA, CierreCaja, Config, Mesa, Orden, ahora_lima, hoy_lima
from ..routes.config import leer_config
from ..services.orders import (
    EleccionInvalida,
    EntregaObligadaSeparado,
    PlatoNoDisponible,
    crear_orden,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])

# "anulada" existe para la caja: un pedido registrado que al final no se
# atendió (cliente se fue, error). No cuenta en las ventas.
ESTADOS = ["pendiente", "preparando", "listo", "entregado", "anulada"]


class ItemIn(BaseModel):
    plato_id: int
    cantidad: int = Field(gt=0, le=50)
    # mesa (default) | taper | bolsa | lonchera — por plato, no por orden
    empaque: str = "mesa"
    # Pedido especial: "sin frijoles", "con un huevo frito"…
    nota: str = Field(default="", max_length=150)


TIPOS_SERVICIO = ["sala", "llevar", "mixto"]
EMPAQUES = ["mesa", "taper", "bolsa", "lonchera"]


class MenuExtraIn(BaseModel):
    """Porción adicional de un tiempo pedida junto al menú ("una entrada
    más"): se cobra al precio_extra configurado en el tiempo."""

    tiempo_orden: int
    plato_id: int
    cantidad: int = Field(gt=0, le=50)


class MenuIn(BaseModel):
    menu_id: int
    cantidad: int = Field(gt=0, le=50)
    # {tiempo_orden: plato_id}; un tiempo con una sola alternativa se
    # completa solo en el backend (viene incluido, no se elige)
    elecciones: dict[int, int] = Field(default_factory=dict)
    extras: list[MenuExtraIn] = Field(default_factory=list, max_length=10)
    empaque: str = "mesa"
    nota: str = Field(default="", max_length=150)


class OrdenIn(BaseModel):
    items: list[ItemIn] = Field(default_factory=list)
    menus: list[MenuIn] = Field(default_factory=list, max_length=20)
    # Medido por la terminal: segundos desde que empezó el pedido hasta
    # confirmar. Opcional; se ignora fuera de un rango razonable.
    duracion_seg: int | None = Field(default=None, ge=0, le=3600)
    # tactil (default) | voz | mixto — cómo se llenó el carrito
    origen: str = "tactil"
    # Mesas asignadas al crear (la caja las manda; la terminal no).
    # Varias = mesas combinadas para un grupo.
    mesa_ids: list[int] = Field(default_factory=list, max_length=10)
    # junto (default) | separado — cómo sale el pedido
    entrega: str = "junto"


class EstadoIn(BaseModel):
    estado: str


def _minutos_espera(orden: Orden) -> float:
    """Minutos desde que se creó la orden, calculados en el servidor para no
    depender del reloj ni la zona horaria del dispositivo de cocina."""
    h, m, s = (int(x) for x in orden.hora.split(":"))
    creada = datetime.combine(orden.fecha, time(h, m, s), tzinfo=LIMA)
    return max(0.0, (ahora_lima() - creada).total_seconds() / 60)


ENTREGAS = ["junto", "separado"]


def _validar_entrega(db: Session, entrega: str, plato_ids: list[int]) -> None:
    """Un plato que se prepara al momento (bistec frito) no puede salir
    'todo junto' con el resto: obliga entrega separada."""
    if entrega not in ENTREGAS:
        raise HTTPException(status_code=422, detail=f"Entrega inválida: {entrega}")
    if entrega != "junto":
        return
    from ..models import Plato

    for plato_id in plato_ids:
        plato = db.get(Plato, plato_id)
        if plato is not None and plato.sale_al_momento:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{plato.nombre} se prepara al momento y no puede salir todo junto: "
                    "elige entrega \"Separado por tiempos\"."
                ),
            )


def _validar_mesas(db: Session, mesa_ids: list[int]) -> None:
    for mesa_id in mesa_ids:
        mesa = db.get(Mesa, mesa_id)
        if mesa is None or not mesa.activa:
            raise HTTPException(status_code=422, detail=f"Mesa inválida: {mesa_id}")


def _mapa_mesas(db: Session) -> dict[int, str]:
    return {m.id: m.nombre for m in db.scalars(select(Mesa)).all()}


def _orden_a_dict(orden: Orden, mapa_mesas: dict[int, str] | None = None) -> dict:
    mapa_mesas = mapa_mesas or {}
    ids_mesa = json.loads(orden.mesa_ids or "[]")
    return {
        "id": orden.id,
        "numero_orden_dia": orden.numero_orden_dia,
        "fecha": orden.fecha.isoformat(),
        "hora": orden.hora,
        "total": orden.total,
        "estado": orden.estado,
        "tipo_servicio": orden.tipo_servicio,
        "origen": orden.origen,
        "metodo_pago": orden.metodo_pago,
        "entrega": orden.entrega,
        "mesa_ids": ids_mesa,
        "mesas": [mapa_mesas.get(i, f"#{i}") for i in ids_mesa],
        "mesa_liberada": orden.mesa_liberada,
        "minutos_espera": round(_minutos_espera(orden), 1),
        # Solo la venta a la carta: los platos de un menú van agrupados en
        # "menus" (cocina y ticket muestran el menú como UN bloque)
        "items": [
            _item_a_dict(i) for i in orden.items if i.orden_menu_id is None
        ],
        "menus": [_orden_menu_a_dict(orden, om) for om in orden.menus],
    }


def _item_a_dict(item) -> dict:
    return {
        "nombre": item.nombre_snapshot,
        "precio": item.precio_snapshot,
        "cantidad": item.cantidad,
        "empaque": item.empaque,
        "nota": item.nota,
        "estado": item.estado,
        "subtotal": round(item.precio_snapshot * item.cantidad, 2),
    }


def _orden_menu_a_dict(orden: Orden, om) -> dict:
    """Un menú vendido con sus platos (elegidos y extras) indentados."""
    items_menu = [i for i in orden.items if i.orden_menu_id == om.id]
    items_menu.sort(key=lambda i: (i.es_extra, i.tiempo_orden or 0))
    return {
        "nombre": om.nombre_snapshot,
        "precio": om.precio_snapshot,
        "cantidad": om.cantidad,
        "nota": om.nota,
        "items": [
            {**_item_a_dict(i), "tiempo_orden": i.tiempo_orden, "es_extra": i.es_extra}
            for i in items_menu
        ],
        # Precio del menú × cantidad + recargos y porciones extra
        "subtotal": round(
            om.precio_snapshot * om.cantidad
            + sum(i.precio_snapshot * i.cantidad for i in items_menu),
            2,
        ),
    }


@router.post("", status_code=201)
def crear(payload: OrdenIn, db: Session = Depends(get_db)):
    """Guarda la orden YA CONFIRMADA (después de la ventana de cancelación).

    Devuelve el número de orden del día y los datos del local para imprimir
    el ticket.
    """
    if not payload.items and not payload.menus:
        raise HTTPException(status_code=422, detail="La orden no tiene items")
    for item in payload.items:
        if item.empaque not in EMPAQUES:
            raise HTTPException(status_code=422, detail=f"Empaque inválido: {item.empaque}")
    for menu in payload.menus:
        if menu.empaque not in EMPAQUES:
            raise HTTPException(status_code=422, detail=f"Empaque inválido: {menu.empaque}")
    if payload.origen not in ("tactil", "voz", "mixto"):
        raise HTTPException(status_code=422, detail=f"Origen inválido: {payload.origen}")
    _validar_mesas(db, payload.mesa_ids)
    # Los platos elegidos del menú los valida crear_orden (ahí recién se
    # resuelven las elecciones); aquí solo la venta a la carta
    _validar_entrega(db, payload.entrega, [i.plato_id for i in payload.items])

    # Candado: sin apertura de caja (fondo inicial) no se vende
    config = leer_config(db)
    if config["exigir_caja_abierta"]:
        apertura = db.scalar(select(CierreCaja).where(CierreCaja.fecha == hoy_lima()))
        if apertura is None:
            raise HTTPException(
                status_code=409,
                detail="La caja aún no se abre. Registra el fondo inicial en la pantalla de Caja.",
            )
    try:
        orden = crear_orden(
            db, [i.model_dump() for i in payload.items],
            payload.duracion_seg, payload.origen,
            menus=[m.model_dump() for m in payload.menus],
            entrega=payload.entrega,
        )
    except PlatoNoDisponible as e:
        raise HTTPException(status_code=409, detail=f"'{e.nombre}' ya no está disponible")
    except EntregaObligadaSeparado as e:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{e.nombre} se prepara al momento y no puede salir todo junto: "
                "elige entrega \"Separado por tiempos\"."
            ),
        )
    except EleccionInvalida as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Mesas asignadas al crear (la caja las manda al sentar al grupo)
    if payload.mesa_ids:
        orden.mesa_ids = json.dumps(payload.mesa_ids)

    # En modo "terminal" la propia pantalla del cliente imprime el ticket;
    # en modo "estacion" la orden queda en cola para /ticketera.
    if config["modo_impresion"] != "estacion":
        orden.impreso = True
    db.commit()

    return {
        "orden": _orden_a_dict(orden, _mapa_mesas(db)),
        "local": {
            "nombre": config["nombre_local"],
            "direccion": config["direccion"],
            "ruc": config["ruc"],
        },
    }


@router.get("/today")
def ordenes_de_hoy(db: Session = Depends(get_db)):
    """Órdenes de hoy, para la vista de cocina y el admin."""
    return _ordenes_del_dia(db, hoy_lima())


@router.get("/of-day")
def ordenes_de_un_dia(fecha: date, db: Session = Depends(get_db)):
    """Órdenes de cualquier fecha (historial de movimiento en el admin)."""
    return _ordenes_del_dia(db, fecha)


def _ordenes_del_dia(db: Session, fecha: date) -> dict:
    ordenes = db.scalars(
        select(Orden)
        .options(selectinload(Orden.items), selectinload(Orden.menus))
        .where(Orden.fecha == fecha)
        .order_by(Orden.numero_orden_dia)
    ).all()
    mapa = _mapa_mesas(db)
    total_vendido = round(sum(o.total for o in ordenes if o.estado != "anulada"), 2)
    return {
        "fecha": fecha.isoformat(),
        "ordenes": [_orden_a_dict(o, mapa) for o in ordenes],
        "total_vendido": total_vendido,
    }


@router.get("/pending-print")
def pendientes_de_impresion(db: Session = Depends(get_db)):
    """Cola de la estación de impresión (/ticketera): órdenes de hoy que
    todavía no tienen ticket impreso, más los datos del local."""
    ordenes = db.scalars(
        select(Orden)
        .options(selectinload(Orden.items), selectinload(Orden.menus))
        .where(
            Orden.fecha == hoy_lima(),
            Orden.impreso == False,  # noqa: E712
            Orden.estado != "anulada",  # una anulada en cola ya no se imprime
        )
        .order_by(Orden.numero_orden_dia)
    ).all()
    config = leer_config(db)
    return {
        "ordenes": [_orden_a_dict(o, _mapa_mesas(db)) for o in ordenes],
        "local": {
            "nombre": config["nombre_local"],
            "direccion": config["direccion"],
            "ruc": config["ruc"],
        },
    }


@router.post("/pending-print/clear")
def descartar_pendientes(db: Session = Depends(get_db)):
    """Marca todo lo pendiente como impreso sin imprimir (p. ej. si la
    ticketera estuvo apagada un rato y esos pedidos ya se atendieron)."""
    resultado = db.execute(
        update(Orden)
        .where(Orden.fecha == hoy_lima(), Orden.impreso == False)  # noqa: E712
        .values(impreso=True)
    )
    db.commit()
    return {"descartadas": resultado.rowcount}


@router.post("/{orden_id}/printed")
def marcar_impreso(orden_id: int, db: Session = Depends(get_db)):
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    orden.impreso = True
    db.commit()
    return {"id": orden.id, "impreso": True}


@router.post("/{orden_id}/reprint")
def reimprimir(orden_id: int, db: Session = Depends(get_db)):
    """Reencola la orden para que la estación de impresión la vuelva a
    imprimir."""
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    orden.impreso = False
    db.commit()
    return {"id": orden.id, "impreso": False}


@router.patch("/{orden_id}/status")
def cambiar_estado(orden_id: int, payload: EstadoIn, db: Session = Depends(get_db)):
    if payload.estado not in ESTADOS:
        raise HTTPException(status_code=422, detail=f"Estado inválido: {payload.estado}")
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    # Kardex: anular devuelve el stock consumido (y des-anular lo vuelve a consumir)
    from ..services.inventario import consumir_por_orden, revertir_por_orden

    if payload.estado == "anulada" and orden.estado != "anulada":
        revertir_por_orden(db, orden)
    elif payload.estado != "anulada" and orden.estado == "anulada":
        consumir_por_orden(db, orden)

    orden.estado = payload.estado
    # Avanzar la orden completa arrastra todos sus ítems (el estado de la
    # orden es el mínimo de sus ítems: deben quedar consistentes)
    if payload.estado != "anulada":
        for item in orden.items:
            item.estado = payload.estado
    db.commit()
    return {"id": orden.id, "estado": orden.estado}


# ---------- Despacho por bulks (§3): tachar desde "Por salir" ----------

ESTADOS_ITEM = ["pendiente", "preparando", "listo", "entregado"]


class BulkLineaIn(BaseModel):
    # Una de las dos referencias; "Por salir" agrupa por nombre (snapshot)
    plato_id: int | None = None
    plato_nombre: str | None = None
    cantidad: int = Field(gt=0, le=200)


class BulkIn(BaseModel):
    estado_destino: str
    # Varias líneas = bulk mixto ("2 asados y 2 tallarines"): todo o nada
    lineas: list[BulkLineaIn] = Field(min_length=1, max_length=30)


@router.post("/despachar-bulk")
def despachar_bulk_endpoint(payload: BulkIn, db: Session = Depends(get_db)):
    """Avanza N porciones de un plato al estado destino, en cascada de la
    orden más antigua a la más nueva. Devuelve las órdenes que cambiaron
    para que la pantalla de cocina se actualice sin esperar el poll."""
    from ..services.cocina import BulkInsuficiente, despachar_bulk

    if payload.estado_destino not in ESTADOS_ITEM or payload.estado_destino == "pendiente":
        raise HTTPException(
            status_code=422, detail=f"Estado destino inválido: {payload.estado_destino}"
        )
    for linea in payload.lineas:
        if linea.plato_id is None and not linea.plato_nombre:
            raise HTTPException(
                status_code=422, detail="Cada línea necesita plato_id o plato_nombre"
            )
    try:
        cambiadas = despachar_bulk(
            db, [l.model_dump() for l in payload.lineas], payload.estado_destino
        )
    except BulkInsuficiente as e:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"De {e.nombre} solo quedan {e.disponibles} porciones por avanzar "
                f"(se pidió {e.pedidas}). Refresca la pantalla."
            ),
        )
    mapa = _mapa_mesas(db)
    return {"ordenes": [_orden_a_dict(o, mapa) for o in cambiadas]}


class MesasIn(BaseModel):
    mesa_ids: list[int] = Field(default_factory=list, max_length=10)


@router.patch("/{orden_id}/mesas")
def asignar_mesas(orden_id: int, payload: MesasIn, db: Session = Depends(get_db)):
    """Asigna (o cambia) las mesas de un ticket. Varias = combinadas.
    Lista vacía = quitar la asignación."""
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if orden.estado == "anulada":
        raise HTTPException(status_code=409, detail="Una orden anulada no lleva mesa")
    _validar_mesas(db, payload.mesa_ids)
    orden.mesa_ids = json.dumps(payload.mesa_ids)
    orden.mesa_liberada = False  # re-asignar re-ocupa
    db.commit()
    mapa = _mapa_mesas(db)
    return {
        "id": orden.id,
        "mesa_ids": payload.mesa_ids,
        "mesas": [mapa.get(i, f"#{i}") for i in payload.mesa_ids],
    }


class EntregaIn(BaseModel):
    entrega: str


@router.patch("/{orden_id}/entrega")
def corregir_entrega(orden_id: int, payload: EntregaIn, db: Session = Depends(get_db)):
    """La caja corrige cómo sale el pedido (igual que el método de pago)."""
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    _validar_entrega(db, payload.entrega, [i.plato_id for i in orden.items if i.plato_id])
    orden.entrega = payload.entrega
    db.commit()
    return {"id": orden.id, "entrega": orden.entrega}


@router.post("/{orden_id}/liberar-mesa")
def liberar_mesa_del_ticket(orden_id: int, db: Session = Depends(get_db)):
    """Libera SOLO la mesa de este ticket (mesas compartidas: un grupo se
    va, el otro sigue comiendo en la misma mesa). La mesa queda libre
    únicamente cuando ya no la ocupa ningún ticket."""
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    orden.mesa_liberada = True
    db.commit()
    return {"id": orden.id, "mesa_liberada": True}


METODOS_PAGO = ["efectivo", "tarjeta", "yape"]


class PagoIn(BaseModel):
    metodo_pago: str


@router.patch("/{orden_id}/pago")
def registrar_pago(orden_id: int, payload: PagoIn, db: Session = Depends(get_db)):
    """La caja registra cómo se pagó la orden. Re-PATCH corrige el método."""
    if payload.metodo_pago not in METODOS_PAGO:
        raise HTTPException(status_code=422, detail=f"Método inválido: {payload.metodo_pago}")
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if orden.estado == "anulada":
        raise HTTPException(status_code=409, detail="Una orden anulada no se cobra")
    orden.metodo_pago = payload.metodo_pago
    db.commit()
    return {"id": orden.id, "metodo_pago": orden.metodo_pago}
