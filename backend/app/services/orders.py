"""Lógica de creación de órdenes.

Punto clave: el número de orden es un correlativo POR DÍA (la orden #1, #2...
de hoy) y se calcula dentro de la misma transacción que inserta la orden.

Menú encadenado (§1): un menú vendido es UNA unidad (OrdenMenu) con su
precio propio; los platos elegidos entran como OrdenItems ligados al menú
con precio 0 (o el recargo de la alternativa, o el precio de una porción
extra). El total nunca suma el precio de carta de esos platos: el precio
ya está en el menú.
"""
import json
import threading

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import MenuAgregado, MenuPlantilla, Orden, OrdenItem, OrdenMenu, Plato, ahora_lima

# Serializa la asignación del correlativo del día: sin esto, dos
# confirmaciones simultáneas (p. ej. dos terminales) podrían leer el mismo
# máximo y crear dos órdenes con el mismo número.
_lock_creacion = threading.Lock()


class PlatoNoDisponible(Exception):
    def __init__(self, nombre: str):
        self.nombre = nombre
        super().__init__(f"Plato no disponible: {nombre}")


class EleccionInvalida(Exception):
    """El pedido de menú está mal armado (elección fuera de las
    alternativas, tiempo obligatorio sin elegir, extra no ofrecido…)."""


class EntregaObligadaSeparado(Exception):
    """Un plato elegido del menú sale al momento: la entrega no puede ser
    'junto'. Guarda el nombre para el mensaje de la terminal."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        super().__init__(nombre)


def crear_orden(
    db: Session,
    items: list[dict],
    duracion_seg: int | None = None,
    origen: str = "tactil",
    menus: list[dict] | None = None,
    entrega: str = "junto",
) -> Orden:
    """Crea una orden confirmada (tras la ventana de cancelación).

    ``items`` es una lista de {"plato_id", "cantidad", "empaque"?, "nota"?}
    (venta a la carta). ``menus`` es una lista de {"menu_id", "cantidad",
    "elecciones" {tiempo_orden: plato_id}, "extras" [{tiempo_orden,
    plato_id, cantidad}], "empaque"?, "nota"?}. Nombre y precio se toman
    de la BD en el momento de crear la orden (snapshot), no del payload
    del cliente. ``duracion_seg`` es cuánto demoró el cliente en armar y
    confirmar (lo mide la terminal).

    El tipo de servicio de la orden se deriva de los empaques: todo
    "mesa" = sala; nada "mesa" = llevar; mezcla = mixto.
    """
    with _lock_creacion:
        return _crear_orden(db, items, duracion_seg, origen, menus or [], entrega)


def _tipo_servicio_de(empaques: list[str]) -> str:
    en_mesa = [e == "mesa" for e in empaques]
    if all(en_mesa):
        return "sala"
    if not any(en_mesa):
        return "llevar"
    return "mixto"


def _plato_nombre(db: Session, plato_id: int) -> str:
    plato = db.get(Plato, plato_id)
    return plato.nombre if plato else f"id {plato_id}"


def _plato_activo(db: Session, plato_id: int) -> Plato:
    plato = db.get(Plato, plato_id)
    if plato is None or not plato.activo_hoy:
        raise PlatoNoDisponible(plato.nombre if plato else f"id {plato_id}")
    return plato


def _armar_menu(db: Session, orden: Orden, pedido: dict, entrega: str) -> float:
    """Agrega un menú (OrdenMenu + sus OrdenItems) a la orden y devuelve
    lo que suma al total: precio del menú × cantidad + recargos + extras."""
    plantilla = db.get(MenuPlantilla, pedido["menu_id"])
    if plantilla is None or not plantilla.activo_hoy:
        raise PlatoNoDisponible(plantilla.nombre if plantilla else f"menú id {pedido['menu_id']}")

    cantidad = int(pedido["cantidad"])
    if cantidad <= 0:
        raise EleccionInvalida("La cantidad del menú debe ser mayor a 0")
    empaque = pedido.get("empaque", "mesa")
    # Empaque POR TIEMPO ("la sopa en bolsa, el segundo en lonchera"): si un
    # tiempo no viene aquí, usa el empaque general del menú
    empaques_por_tiempo = {int(k): v for k, v in (pedido.get("empaques") or {}).items()}
    numeros_de_tiempo = {t.orden for t in plantilla.tiempos}
    if not set(empaques_por_tiempo) <= numeros_de_tiempo:
        raise EleccionInvalida(f"El {plantilla.nombre} no tiene ese tiempo")
    elecciones = {int(k): int(v) for k, v in (pedido.get("elecciones") or {}).items()}

    # Tiempos que el cliente quitó ("sin sopa"): descuentan lo configurado
    # en el tiempo y no generan item. Quitar y elegir a la vez no tiene
    # sentido; una porción EXTRA del mismo tiempo sí (quitó la sopa del
    # menú pero pide una entrada aparte: esa se cobra a precio de extra).
    tiempos_por_orden = {t.orden: t for t in plantilla.tiempos}
    omitidos: list[dict] = []
    for numero in {int(n) for n in pedido.get("omitidos") or []}:
        tiempo = tiempos_por_orden.get(numero)
        if tiempo is None:
            raise EleccionInvalida(f"El {plantilla.nombre} no tiene ese tiempo")
        if numero in elecciones:
            raise EleccionInvalida(
                f"Quitaste {tiempo.rotulo} del {plantilla.nombre} y a la vez lo elegiste"
            )
        omitidos.append({
            "tiempo_orden": numero,
            "rotulo": tiempo.rotulo,
            "descuento": tiempo.descuento_si_se_quita,
        })
    omitidos.sort(key=lambda o: o["tiempo_orden"])

    orden_menu = OrdenMenu(
        menu_id=plantilla.id,
        nombre_snapshot=plantilla.nombre,
        precio_snapshot=plantilla.precio,
        cantidad=cantidad,
        nota=pedido.get("nota", "").strip(),
        omitidos_json=json.dumps(omitidos, ensure_ascii=False),
    )
    orden.menus.append(orden_menu)
    if plantilla.precio - sum(o["descuento"] for o in omitidos) < 0:
        # Un descuento mal configurado no puede dejar el menú en negativo
        raise EleccionInvalida(f"El descuento del {plantilla.nombre} deja el precio en negativo")
    subtotal = plantilla.precio * cantidad
    subtotal -= sum(o["descuento"] for o in omitidos) * cantidad
    numeros_omitidos = {o["tiempo_orden"] for o in omitidos}

    for tiempo in plantilla.tiempos:
        if tiempo.orden in numeros_omitidos:
            continue
        todas = {a.plato_id: a for a in tiempo.alternativas}
        # Solo cuentan las alternativas con plato disponible hoy
        alternativas = {
            plato_id: a
            for plato_id, a in todas.items()
            if (p := db.get(Plato, plato_id)) is not None and p.activo_hoy
        }
        eleccion = elecciones.get(tiempo.orden)
        if eleccion is None and len(alternativas) == 1:
            # Un tiempo con una sola opción no se elige: viene incluido
            eleccion = next(iter(alternativas))
        if eleccion is None:
            if not tiempo.obligatorio:
                continue
            if not alternativas:
                # Tiempo obligatorio con todo agotado: el menú no se puede vender
                raise PlatoNoDisponible(f"{plantilla.nombre} — {tiempo.rotulo}")
            raise EleccionInvalida(
                f"Falta elegir {tiempo.rotulo} del {plantilla.nombre}"
            )
        if eleccion not in alternativas:
            if eleccion in todas:
                # Era una alternativa válida, pero el plato se agotó → 409
                raise PlatoNoDisponible(_plato_nombre(db, eleccion))
            raise EleccionInvalida(
                f"La elección de {tiempo.rotulo} no es una alternativa del {plantilla.nombre}"
            )
        plato = _plato_activo(db, eleccion)
        _revisar_al_momento(plato, entrega)
        recargo = alternativas[eleccion].recargo
        subtotal += recargo * cantidad
        item = OrdenItem(
            plato_id=plato.id,
            nombre_snapshot=plato.nombre,
            precio_snapshot=recargo,  # el precio del plato ya está en el menú
            cantidad=cantidad,
            empaque=empaques_por_tiempo.get(tiempo.orden, empaque),
            nota="",
            tiempo_orden=tiempo.orden,
            es_extra=False,
        )
        item.orden_menu = orden_menu
        orden.items.append(item)

    for extra in pedido.get("extras") or []:
        tiempo = tiempos_por_orden.get(int(extra["tiempo_orden"]))
        if tiempo is None:
            raise EleccionInvalida(f"El {plantilla.nombre} no tiene ese tiempo")
        if tiempo.precio_extra <= 0:
            raise EleccionInvalida(
                f"El {plantilla.nombre} no ofrece porciones extra de {tiempo.rotulo}"
            )
        alternativa = next(
            (a for a in tiempo.alternativas if a.plato_id == int(extra["plato_id"])), None
        )
        if alternativa is None:
            raise EleccionInvalida(
                f"La porción extra de {tiempo.rotulo} no es una alternativa del {plantilla.nombre}"
            )
        cantidad_extra = int(extra["cantidad"])
        if cantidad_extra <= 0:
            continue
        plato = _plato_activo(db, alternativa.plato_id)
        _revisar_al_momento(plato, entrega)
        precio_extra = tiempo.precio_extra + alternativa.recargo
        subtotal += precio_extra * cantidad_extra
        item = OrdenItem(
            plato_id=plato.id,
            nombre_snapshot=plato.nombre,
            precio_snapshot=precio_extra,
            cantidad=cantidad_extra,
            empaque=empaques_por_tiempo.get(tiempo.orden, empaque),
            nota="",
            tiempo_orden=tiempo.orden,
            es_extra=True,
        )
        item.orden_menu = orden_menu
        orden.items.append(item)

    # Agregados: porciones sueltas (+1 presa, +1 refresco) con su propio
    # precio; no son platos de carta, así que van sin plato_id y con
    # snapshot de nombre y precio del agregado.
    for pedido_agregado in pedido.get("agregados") or []:
        agregado = db.get(MenuAgregado, int(pedido_agregado["agregado_id"]))
        if (
            agregado is None
            or not agregado.activo
            or (agregado.menu_id is not None and agregado.menu_id != plantilla.id)
        ):
            raise EleccionInvalida(f"El {plantilla.nombre} no ofrece ese agregado")
        cantidad_agregado = int(pedido_agregado["cantidad"])
        if cantidad_agregado <= 0:
            continue
        subtotal += agregado.precio * cantidad_agregado
        item = OrdenItem(
            plato_id=None,
            nombre_snapshot=agregado.nombre,
            precio_snapshot=agregado.precio,
            cantidad=cantidad_agregado,
            empaque=empaque,
            nota="",
            es_agregado=True,
        )
        item.orden_menu = orden_menu
        orden.items.append(item)

    return subtotal


def _revisar_al_momento(plato: Plato, entrega: str) -> None:
    if entrega == "junto" and plato.sale_al_momento:
        raise EntregaObligadaSeparado(plato.nombre)


def _crear_orden(
    db: Session,
    items: list[dict],
    duracion_seg: int | None,
    origen: str,
    menus: list[dict],
    entrega: str,
) -> Orden:
    ahora = ahora_lima()
    hoy = ahora.date()

    ultimo = db.execute(
        select(func.max(Orden.numero_orden_dia)).where(Orden.fecha == hoy)
    ).scalar()
    numero = (ultimo or 0) + 1

    orden = Orden(
        numero_orden_dia=numero,
        fecha=hoy,
        hora=ahora.strftime("%H:%M:%S"),
        total=0.0,
        estado="pendiente",
        duracion_seg=duracion_seg,
        origen=origen,
        entrega=entrega,
    )

    total = 0.0
    for item in items:
        plato = _plato_activo(db, item["plato_id"])
        cantidad = int(item["cantidad"])
        if cantidad <= 0:
            continue
        total += plato.precio * cantidad
        orden.items.append(
            OrdenItem(
                plato_id=plato.id,
                nombre_snapshot=plato.nombre,
                precio_snapshot=plato.precio,
                cantidad=cantidad,
                empaque=item.get("empaque", "mesa"),
                nota=item.get("nota", "").strip(),
            )
        )

    for pedido_menu in menus:
        total += _armar_menu(db, orden, pedido_menu, entrega)

    if not orden.items and not orden.menus:
        raise ValueError("La orden no tiene items")

    # El tipo de servicio se deriva de los empaques de TODOS los platos
    # (los del menú heredan el empaque del menú)
    orden.tipo_servicio = _tipo_servicio_de([i.empaque for i in orden.items] or ["mesa"])
    orden.total = round(total, 2)
    db.add(orden)
    db.flush()  # asigna orden.id ANTES de ligar los movimientos del kardex

    # Kardex: descuenta insumos según las recetas (los platos elegidos del
    # menú también consumen: son OrdenItems con plato_id)
    from .inventario import consumir_por_orden

    consumir_por_orden(db, orden)

    db.commit()
    db.refresh(orden)
    return orden
