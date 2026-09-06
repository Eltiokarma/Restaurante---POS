from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

import json
from datetime import date, datetime, time

from sqlalchemy import update

from ..db import get_db
from ..models import CierreCaja, Config, LIMA, Mesa, Orden, Plato, ahora_lima, hoy_lima
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


class MenuAgregadoIn(BaseModel):
    agregado_id: int
    cantidad: int = Field(gt=0, le=50)


class MenuIn(BaseModel):
    menu_id: int
    cantidad: int = Field(gt=0, le=50)
    # {tiempo_orden: plato_id}; un tiempo con una sola alternativa se
    # completa solo en el backend (viene incluido, no se elige)
    elecciones: dict[int, int] = Field(default_factory=dict)
    extras: list[MenuExtraIn] = Field(default_factory=list, max_length=10)
    # Tiempos quitados ("sin sopa") y porciones agregadas ("+1 presa")
    omitidos: list[int] = Field(default_factory=list, max_length=6)
    agregados: list[MenuAgregadoIn] = Field(default_factory=list, max_length=10)
    # Empaque por tiempo (tiempo_orden → empaque); lo que no venga usa "empaque"
    empaques: dict[int, str] = Field(default_factory=dict)
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


def _segundos_desde_anulacion(orden: Orden) -> float | None:
    """Segundos desde que se anuló, calculados en el servidor (cocina
    muestra el cintillo "no preparar" los primeros 60 s). None si no está
    anulada o si es una anulación vieja sin timestamp."""
    if orden.estado != "anulada" or orden.anulada_en is None:
        return None
    momento = orden.anulada_en
    if momento.tzinfo is None:  # SQLite guarda naive: es hora de Lima
        momento = momento.replace(tzinfo=LIMA)
    return max(0.0, (ahora_lima() - momento).total_seconds())


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


def _mapa_categorias(db: Session) -> dict[int, str]:
    """plato_id → categoría, para que cocina sepa qué NO prepara (bebidas)."""
    return dict(db.execute(select(Plato.id, Plato.categoria)).all())


def _orden_a_dict(
    orden: Orden,
    mapa_mesas: dict[int, str] | None = None,
    categorias: dict[int, str] | None = None,
) -> dict:
    mapa_mesas = mapa_mesas or {}
    categorias = categorias or {}
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
        "pago_pendiente": orden.pago_pendiente,
        "vuelto_pendiente": orden.vuelto_pendiente,
        "entrega": orden.entrega,
        "mesa_ids": ids_mesa,
        "mesas": [mapa_mesas.get(i, f"#{i}") for i in ids_mesa],
        "mesa_liberada": orden.mesa_liberada,
        "minutos_espera": round(_minutos_espera(orden), 1),
        "anulada_hace_seg": _segundos_desde_anulacion(orden),
        # Solo la venta a la carta: los platos de un menú van agrupados en
        # "menus" (cocina y ticket muestran el menú como UN bloque)
        "items": [
            _item_a_dict(i, categorias) for i in orden.items if i.orden_menu_id is None
        ],
        "menus": [_orden_menu_a_dict(orden, om, categorias) for om in orden.menus],
    }


def _item_a_dict(item, categorias: dict[int, str] | None = None) -> dict:
    return {
        "nombre": item.nombre_snapshot,
        "es_cargo": item.es_cargo,
        # Un plato borrado del catálogo queda sin categoría: cocina lo muestra
        "categoria": (categorias or {}).get(item.plato_id),
        "precio": item.precio_snapshot,
        "cantidad": item.cantidad,
        "empaque": item.empaque,
        "nota": item.nota,
        "estado": item.estado,
        "subtotal": round(item.precio_snapshot * item.cantidad, 2),
    }


def _orden_menu_a_dict(orden: Orden, om, categorias: dict[int, str] | None = None) -> dict:
    """Un menú vendido con sus platos (elegidos, extras y agregados) y
    los tiempos que el cliente quitó ("sin sopa")."""
    items_menu = [i for i in orden.items if i.orden_menu_id == om.id]
    items_menu.sort(key=lambda i: (i.es_agregado, i.es_extra, i.tiempo_orden or 0))
    omitidos = om.omitidos()
    return {
        "nombre": om.nombre_snapshot,
        "precio": om.precio_snapshot,
        "cantidad": om.cantidad,
        "nota": om.nota,
        "omitidos": [{"rotulo": o["rotulo"], "descuento": o["descuento"]} for o in omitidos],
        "items": [
            {**_item_a_dict(i, categorias), "tiempo_orden": i.tiempo_orden,
             "es_extra": i.es_extra, "es_agregado": i.es_agregado}
            for i in items_menu
        ],
        # Precio del menú × cantidad − descuentos por quitar tiempos
        # + recargos, porciones extra y agregados
        "subtotal": round(
            om.precio_cobrado * om.cantidad
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
        for e in menu.empaques.values():
            if e not in EMPAQUES:
                raise HTTPException(status_code=422, detail=f"Empaque inválido: {e}")
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
    # en "estacion" la orden queda en cola para /ticketera y en "puente"
    # para el puente de impresión del local (ESC/POS directo).
    if config["modo_impresion"] == "terminal":
        orden.impreso = True
    db.commit()

    return {
        "orden": _orden_a_dict(orden, _mapa_mesas(db), _mapa_categorias(db)),
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


def _impresion_atascada(db: Session, ordenes: list[Orden], fecha: date) -> dict:
    """Tickets que llevan rato sin imprimirse.

    Si la ticketera o el puente se cuelgan, los tickets se acumulan EN
    SILENCIO: cocina no se entera y el cliente espera un plato que nadie
    está preparando. Caja y cocina muestran esto como cintillo.

    Solo aplica cuando imprime alguien más (modos "estacion" y "puente");
    en modo "terminal" la orden nace impresa.
    """
    vacio = {"cantidad": 0, "minutos": 0.0}
    if fecha != hoy_lima() or leer_config(db)["modo_impresion"] == "terminal":
        return vacio
    pendientes = [o for o in ordenes if not o.impreso and o.estado != "anulada"]
    if not pendientes:
        return vacio
    # La más antigua manda: es la que lleva más tiempo esperando
    return {
        "cantidad": len(pendientes),
        "minutos": round(max(_minutos_espera(o) for o in pendientes), 1),
    }


def _ordenes_del_dia(db: Session, fecha: date) -> dict:
    ordenes = db.scalars(
        select(Orden)
        .options(selectinload(Orden.items), selectinload(Orden.menus))
        .where(Orden.fecha == fecha)
        .order_by(Orden.numero_orden_dia)
    ).all()
    mapa = _mapa_mesas(db)
    categorias = _mapa_categorias(db)
    total_vendido = round(sum(o.total for o in ordenes if o.estado != "anulada"), 2)
    return {
        "fecha": fecha.isoformat(),
        "ordenes": [_orden_a_dict(o, mapa, categorias) for o in ordenes],
        "total_vendido": total_vendido,
        "impresion_pendiente": _impresion_atascada(db, ordenes, fecha),
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
    mapa = _mapa_mesas(db)

    # Tickets chicos de gaseosas (solo de hoy) para la estación HTML
    from ..models import TicketBebida
    pendientes_bebida = db.scalars(
        select(TicketBebida)
        .join(Orden, TicketBebida.orden_id == Orden.id)
        .where(
            TicketBebida.impreso == False,  # noqa: E712
            Orden.fecha == hoy_lima(),
            Orden.estado != "anulada",
        )
        .order_by(TicketBebida.id)
    ).all()
    tickets_bebida = []
    for tb in pendientes_bebida:
        orden_tb = db.get(Orden, tb.orden_id)
        ids_mesa = json.loads(orden_tb.mesa_ids or "[]")
        tickets_bebida.append({
            "id": tb.id,
            "numero": f"{orden_tb.numero_orden_dia:03d}",
            "mesas": [mapa.get(i, f"#{i}") for i in ids_mesa],
            "items": json.loads(tb.detalle_json),
            "total": tb.total,
            "hora": tb.creado_en.strftime("%H:%M"),
        })

    return {
        "ordenes": [_orden_a_dict(o, mapa) for o in ordenes],
        "tickets_bebida": tickets_bebida,
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
    from ..models import TicketBebida
    db.execute(update(TicketBebida).where(TicketBebida.impreso == False).values(impreso=True))  # noqa: E712
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
        orden.anulada_en = ahora_lima()  # cocina muestra "no preparar" 60 s
    elif payload.estado != "anulada" and orden.estado == "anulada":
        consumir_por_orden(db, orden)
        orden.anulada_en = None

    orden.estado = payload.estado
    # Avanzar la orden completa arrastra sus ítems (el estado de la orden es
    # el mínimo de sus ítems: deben quedar consistentes). Pero SOLO hacia
    # adelante: si cocina ya tachó porciones por bulk, "empezar a preparar"
    # no puede devolverlas a la cola y hacer que se cocinen dos veces.
    if payload.estado != "anulada":
        from ..services.cocina import RANGO_ESTADO

        destino = RANGO_ESTADO[payload.estado]
        for item in orden.items:
            if RANGO_ESTADO[item.estado] < destino:
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
    categorias = _mapa_categorias(db)
    return {"ordenes": [_orden_a_dict(o, mapa, categorias) for o in cambiadas]}


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


class BebidaPedida(BaseModel):
    bebida_id: int
    cantidad: int = Field(gt=0, le=20)


class BebidasIn(BaseModel):
    items: list[BebidaPedida] = Field(min_length=1, max_length=10)


@router.post("/{orden_id}/bebidas")
def agregar_bebidas(orden_id: int, payload: BebidasIn, db: Session = Depends(get_db)):
    """La caja añade gaseosas de la lista fija a una orden YA creada.

    El item nace "entregado" y es_cargo=True (cocina no lo ve ni frena la
    orden), entra al total y descuenta botellas del kardex. NO se reimprime
    la comanda: sale solo un ticket chico con las gaseosas (en modo
    puente/estación espera en la cola; en modo terminal lo imprime la
    propia caja con los datos que devuelve este endpoint)."""
    from ..models import Bebida, Insumo, OrdenItem, TicketBebida
    from ..services.inventario import consumir_directo

    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if orden.estado == "anulada":
        raise HTTPException(status_code=409, detail="La orden está anulada")

    detalle: list[dict] = []
    total_bebidas = 0.0
    referencia = f"orden #{orden.numero_orden_dia:03d} gaseosa"
    for pedido in payload.items:
        bebida = db.get(Bebida, pedido.bebida_id)
        if bebida is None or not bebida.activa:
            raise HTTPException(status_code=422, detail="Bebida no disponible")
        orden.items.append(OrdenItem(
            plato_id=None,
            nombre_snapshot=bebida.nombre,
            precio_snapshot=bebida.precio,
            cantidad=pedido.cantidad,
            empaque="mesa",
            nota="",
            es_cargo=True,
            estado="entregado",
        ))
        total_bebidas += bebida.precio * pedido.cantidad
        detalle.append({"nombre": bebida.nombre, "precio": bebida.precio,
                        "cantidad": pedido.cantidad})
        if bebida.insumo_id is not None:
            insumo = db.get(Insumo, bebida.insumo_id)
            if insumo is not None:
                consumir_directo(db, insumo, pedido.cantidad, referencia, orden.id)

    total_bebidas = round(total_bebidas, 2)
    orden.total = round(orden.total + total_bebidas, 2)

    modo = leer_config(db)["modo_impresion"]
    if modo in ("puente", "estacion"):
        db.add(TicketBebida(orden_id=orden.id, detalle_json=json.dumps(detalle),
                            total=total_bebidas))
    db.commit()

    mapa = _mapa_mesas(db)
    ids_mesa = json.loads(orden.mesa_ids or "[]")
    return {
        "orden": _orden_a_dict(orden, mapa, _mapa_categorias(db)),
        "modo_impresion": modo,
        "ticket_bebida": {
            "numero": f"{orden.numero_orden_dia:03d}",
            "mesas": [mapa.get(i, f"#{i}") for i in ids_mesa],
            "items": detalle,
            "total": total_bebidas,
        },
    }


class TrasladoIn(BaseModel):
    de_mesa_id: int
    a_mesa_id: int
    # True = las órdenes movidas vuelven a la cola de impresión con su
    # mesa nueva (modo puente/estación); en modo terminal no aplica
    reimprimir: bool = False


@router.post("/trasladar-mesa")
def trasladar_mesa(payload: TrasladoIn, db: Session = Depends(get_db)):
    """Mueve TODOS los pedidos de hoy de una mesa a otra de un toque
    (el grupo se cambió de sitio). Mesas combinadas: solo se reemplaza
    la mesa de origen, las demás quedan."""
    if payload.de_mesa_id == payload.a_mesa_id:
        raise HTTPException(status_code=422, detail="Elige una mesa distinta")
    _validar_mesas(db, [payload.de_mesa_id, payload.a_mesa_id])

    ordenes = db.scalars(
        select(Orden)
        .options(selectinload(Orden.items), selectinload(Orden.menus))
        .where(
            Orden.fecha == hoy_lima(),
            Orden.estado != "anulada",
            Orden.mesa_liberada == False,  # noqa: E712
        )
        .order_by(Orden.numero_orden_dia)
    ).all()
    movidas = []
    for orden in ordenes:
        ids = json.loads(orden.mesa_ids or "[]")
        if payload.de_mesa_id not in ids:
            continue
        nuevas = []
        for i in ids:
            reemplazo = payload.a_mesa_id if i == payload.de_mesa_id else i
            if reemplazo not in nuevas:
                nuevas.append(reemplazo)
        orden.mesa_ids = json.dumps(nuevas)
        if payload.reimprimir:
            orden.impreso = False
        movidas.append(orden)

    if not movidas:
        raise HTTPException(status_code=409, detail="Esa mesa no tiene pedidos hoy")
    db.commit()
    mapa = _mapa_mesas(db)
    categorias = _mapa_categorias(db)
    return {
        "trasladadas": len(movidas),
        "ordenes": [_orden_a_dict(o, mapa, categorias) for o in movidas],
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
    # Pagó: la marca de "falta pagar" se levanta sola
    orden.pago_pendiente = False
    db.commit()
    return {"id": orden.id, "metodo_pago": orden.metodo_pago}


class PagoPendienteIn(BaseModel):
    pendiente: bool


@router.patch("/{orden_id}/pago-pendiente")
def marcar_pago_pendiente(orden_id: int, payload: PagoPendienteIn, db: Session = Depends(get_db)):
    """Marca (o levanta) el "FALTA PAGAR" de un ticket: salió a la mesa
    pero la plata aún no entró. Mientras esté marcado, el cierre de caja
    NO espera ese efectivo — antes se llevaba de memoria y descuadraba."""
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if orden.estado == "anulada":
        raise HTTPException(status_code=409, detail="Una orden anulada no se cobra")
    orden.pago_pendiente = payload.pendiente
    if payload.pendiente:
        # Aún no se sabe cómo pagará: el método se registra al cobrar
        orden.metodo_pago = None
    db.commit()
    return {"id": orden.id, "pago_pendiente": orden.pago_pendiente}


class VueltoIn(BaseModel):
    # Con cuánto pagó el cliente; None = vuelto entregado (limpia la marca)
    pago_con: float | None = Field(default=None, ge=0, le=10_000)


@router.patch("/{orden_id}/vuelto")
def registrar_vuelto(orden_id: int, payload: VueltoIn, db: Session = Depends(get_db)):
    """El cliente pagó con un billete grande y el vuelto queda debiendo:
    se registra "pagó con S/ X" y el sistema calcula el vuelto pendiente.
    Mientras esté pendiente, el cierre espera ESA plata de más en el
    cajón. `pago_con: null` = ya se entregó el vuelto."""
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if orden.estado == "anulada":
        raise HTTPException(status_code=409, detail="Una orden anulada no se cobra")
    if payload.pago_con is None:
        orden.vuelto_pendiente = None
        db.commit()
        return {"id": orden.id, "vuelto_pendiente": None}
    if payload.pago_con < orden.total:
        raise HTTPException(
            status_code=422,
            detail=f"Pagó {payload.pago_con:.2f} y el ticket es {orden.total:.2f}: no alcanza",
        )
    vuelto = round(payload.pago_con - orden.total, 2)
    orden.vuelto_pendiente = vuelto if vuelto > 0 else None
    # El vuelto es cosa de efectivo: pagar con billete cobra la orden
    orden.metodo_pago = "efectivo"
    orden.pago_pendiente = False
    db.commit()
    return {"id": orden.id, "vuelto_pendiente": orden.vuelto_pendiente}
