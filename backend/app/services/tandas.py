"""Tandas de cocina: el pre-orquestador (sesión 3).

El "Por salir" acumula porciones por plato; las TANDAS parten lo
pendiente en grupos de ÓRDENES COMPLETAS con reglas deterministas, para
que al terminar una tanda salgan mesas completas, no platos sueltos.
La futura IA orquestadora solo reemplazará este cálculo: la pantalla,
los endpoints y los logs quedan.

Reglas (decisiones del dueño, 2026-09-06):

- La tanda cierra con LO QUE SE LLENE PRIMERO: la ventana de minutos
  (``cocina_bulk_min``) desde la orden más antigua de la tanda, o el
  tope de tickets (``cocina_tanda_max_tickets``; 0 = sin tope).
- Gating por tiempos: en una orden "separado", mientras su entrada no
  esté lista los segundos NO entran a la tanda — aparecen aparte como
  "esperando su entrada" (al estar la entrada, el recálculo los mete a
  la tanda abierta). En "junto" todo el ticket va a la misma tanda.
- El gating AVISA, nunca bloquea: la cocina manda.
- Capacidad opcional por plato (``platos.capacidad_tanda``): 9 chuletas
  con capacidad 6 se muestran "6 + 3 (2 tandas de sartén)".
"""
import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import LIMA, Orden, OrdenItem, Plato, TandaLog, ahora_lima, hoy_lima

# Estados de ítem que la cocina todavía tiene por delante
_PENDIENTES = ("pendiente", "preparando")


def _va_a_cocina(item: OrdenItem, categorias: dict[int, str]) -> bool:
    """Mismo criterio que la pantalla de cocina: los cargos (táper,
    gaseosas) y las bebidas no se cocinan."""
    if item.es_cargo:
        return False
    return categorias.get(item.plato_id) != "bebida"


def _entrada_pendiente(orden: Orden, categorias: dict[int, str]) -> bool:
    """¿Le falta salir alguna entrada a esta orden?"""
    return any(
        item.estado in _PENDIENTES
        for item in orden.items
        if _va_a_cocina(item, categorias) and categorias.get(item.plato_id) == "entrada"
    )


def _items_activos(orden: Orden, categorias: dict[int, str]) -> tuple[list[OrdenItem], list[OrdenItem]]:
    """Parte los ítems cocinables pendientes de una orden en (entran a la
    tanda, esperan su entrada). El gating solo aplica a "separado"."""
    pendientes = [
        i for i in orden.items
        if i.estado in _PENDIENTES and _va_a_cocina(i, categorias)
    ]
    if orden.entrega != "separado" or not _entrada_pendiente(orden, categorias):
        return pendientes, []
    entran = [i for i in pendientes if categorias.get(i.plato_id) == "entrada"]
    esperan = [i for i in pendientes if categorias.get(i.plato_id) != "entrada"]
    return entran, esperan


def _hora_a_datetime(orden: Orden) -> datetime:
    h, m, s = (int(x) for x in orden.hora.split(":"))
    return datetime.combine(orden.fecha, datetime.min.time()).replace(
        hour=h, minute=m, second=s, tzinfo=LIMA,
    )


def _partes_por_capacidad(cantidad: int, capacidad: int) -> list[int]:
    if capacidad <= 0 or cantidad <= capacidad:
        return []
    partes = []
    resto = cantidad
    while resto > 0:
        partes.append(min(capacidad, resto))
        resto -= capacidad
    return partes


def _ordenes_activas(db: Session) -> list[Orden]:
    return db.scalars(
        select(Orden)
        .options(selectinload(Orden.items), selectinload(Orden.menus))
        .where(
            Orden.fecha == hoy_lima(),
            Orden.estado.in_(_PENDIENTES),
        )
        .order_by(Orden.numero_orden_dia)
    ).all()


def calcular_tandas(db: Session, config: dict, mapa_mesas: dict[int, str]) -> list[dict]:
    """Parte las órdenes activas de hoy en tandas. Puro cálculo: no escribe."""
    ventana_min = config["cocina_bulk_min"]
    max_tickets = config["cocina_tanda_max_tickets"]
    categorias = dict(db.execute(select(Plato.id, Plato.categoria)).all())
    platos_info = {
        p.id: p for p in db.scalars(select(Plato)).all()
    }

    ordenes = [
        o for o in _ordenes_activas(db)
        if any(i.estado in _PENDIENTES and _va_a_cocina(i, categorias) for i in o.items)
    ]

    ahora = ahora_lima()
    tandas: list[dict] = []
    actual: dict | None = None
    inicio_actual: datetime | None = None

    for orden in ordenes:
        llegada = _hora_a_datetime(orden)
        abre_nueva = actual is None
        if actual is not None and inicio_actual is not None:
            # La tanda cierra con lo que se llene primero: ventana o tope
            if ventana_min > 0 and llegada - inicio_actual > timedelta(minutes=ventana_min):
                abre_nueva = True
            if max_tickets > 0 and len(actual["orden_ids"]) >= max_tickets:
                abre_nueva = True
        if abre_nueva:
            actual = {
                "numero": len(tandas) + 1,
                "orden_ids": [],
                "tickets": [],
                "platos": {},
                "esperando": [],
                "espera_min": 0,
                "empezada": True,  # queda en False si algún ítem sigue pendiente
            }
            inicio_actual = llegada
            tandas.append(actual)

        entran, esperan = _items_activos(orden, categorias)
        ids_mesa = json.loads(orden.mesa_ids or "[]")
        actual["orden_ids"].append(orden.id)
        actual["tickets"].append({
            "numero": f"{orden.numero_orden_dia:03d}",
            "mesas": [mapa_mesas.get(i, f"#{i}") for i in ids_mesa],
            "entrega": orden.entrega,
        })
        actual["espera_min"] = max(
            actual["espera_min"],
            int((ahora - llegada).total_seconds() // 60),
        )
        for item in entran:
            clave = item.nombre_snapshot
            grupo = actual["platos"].setdefault(clave, {
                "nombre": clave,
                "cantidad": 0,
                "al_momento": bool(
                    item.plato_id and platos_info.get(item.plato_id)
                    and platos_info[item.plato_id].sale_al_momento
                ),
                "capacidad": (
                    platos_info[item.plato_id].capacidad_tanda
                    if item.plato_id and platos_info.get(item.plato_id) else 0
                ),
            })
            grupo["cantidad"] += item.cantidad
            if item.estado == "pendiente":
                actual["empezada"] = False
        if esperan:
            actual["esperando"].append({
                "numero": f"{orden.numero_orden_dia:03d}",
                "platos": [f"{i.cantidad}× {i.nombre_snapshot}" for i in esperan],
            })

    # Forma final: platos como lista ordenada (al momento primero: lo
    # frito manda la duración de la tanda) y partición por capacidad
    resultado = []
    for tanda in tandas:
        platos = sorted(
            tanda["platos"].values(),
            key=lambda g: (not g["al_momento"], g["nombre"]),
        )
        for g in platos:
            g["partes"] = _partes_por_capacidad(g["cantidad"], g["capacidad"])
            del g["capacidad"]
        # Una tanda puede quedar solo con órdenes "esperando su entrada"
        if not platos and not tanda["esperando"]:
            continue
        resultado.append({
            "numero": len(resultado) + 1,
            "orden_ids": tanda["orden_ids"],
            "tickets": tanda["tickets"],
            "platos": platos,
            "esperando": tanda["esperando"],
            "espera_min": tanda["espera_min"],
            "empezada": bool(platos) and tanda["empezada"],
        })
    return resultado


def _composicion(tanda_ordenes: list[Orden], categorias: dict[int, str]) -> str:
    """Snapshot JSON de lo que la tanda va a mover (para tanda_logs)."""
    detalle = []
    for orden in tanda_ordenes:
        entran, _ = _items_activos(orden, categorias)
        detalle.append({
            "orden_id": orden.id,
            "numero": orden.numero_orden_dia,
            "entrega": orden.entrega,
            "platos": [
                {"nombre": i.nombre_snapshot, "cantidad": i.cantidad, "estado": i.estado}
                for i in entran
            ],
        })
    return json.dumps(detalle, ensure_ascii=False)


def avanzar_tanda(db: Session, orden_ids: list[int], destino: str,
                  log_id: int | None = None) -> tuple[list[Orden], list[str], int]:
    """Mueve los ítems de la tanda (los que ENTRAN, no los gateados) a
    ``preparando`` o ``listo``. Devuelve (órdenes cambiadas, avisos,
    id del tanda_log). Los avisos informan, nunca bloquean."""
    from .cocina import RANGO_ESTADO, _lock_despacho, recalcular_estado_orden

    with _lock_despacho:
        categorias = dict(db.execute(select(Plato.id, Plato.categoria)).all())
        ordenes = db.scalars(
            select(Orden)
            .options(selectinload(Orden.items))
            .where(Orden.id.in_(orden_ids))
            .order_by(Orden.numero_orden_dia)
        ).all()

        avisos: list[str] = []
        cambiadas: list[Orden] = []
        rango_destino = RANGO_ESTADO[destino]
        ahora = ahora_lima()

        composicion = _composicion(ordenes, categorias)

        for orden in ordenes:
            if orden.estado == "anulada":
                avisos.append(f"El ticket #{orden.numero_orden_dia:03d} está anulado: no se tocó.")
                continue
            entran, esperan = _items_activos(orden, categorias)
            tocada = False
            for item in entran:
                if RANGO_ESTADO[item.estado] < rango_destino:
                    item.estado = destino
                    tocada = True
            if tocada:
                recalcular_estado_orden(orden)
                cambiadas.append(orden)
            if destino == "listo" and esperan:
                avisos.append(
                    f"El segundo del #{orden.numero_orden_dia:03d} sigue esperando su "
                    "entrada: entrará a la próxima tanda."
                )

        # Snapshot para el orquestador: al empezar se abre el log; al
        # salir se cierra (o se crea completo si nadie apretó "empezar")
        if destino == "preparando":
            log = TandaLog(
                fecha=hoy_lima(),
                composicion_json=composicion,
                hora_inicio=ahora.strftime("%H:%M:%S"),
            )
            db.add(log)
            db.flush()
        else:
            log = db.get(TandaLog, log_id) if log_id else None
            if log is None:
                log = TandaLog(
                    fecha=hoy_lima(),
                    composicion_json=composicion,
                    hora_inicio=ahora.strftime("%H:%M:%S"),
                )
                db.add(log)
                db.flush()
            log.hora_listo = ahora.strftime("%H:%M:%S")

        db.commit()
        return cambiadas, avisos, log.id
