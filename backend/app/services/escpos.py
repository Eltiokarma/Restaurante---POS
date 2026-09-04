"""Ticket en comandos ESC/POS para impresoras térmicas de 80 mm.

Se usa en el modo de impresión "puente": el backend (aunque viva en la
nube) genera los BYTES del ticket y el puente del local
(scripts/puente_impresion.py) solo los manda tal cual a la impresora por
su IP (puerto RAW 9100). Sin drivers, sin diálogos, con corte automático
— la misma mecánica que usan las apps de POS nativas.

El layout replica el ticket HTML (components/Ticket.tsx): cabecera del
local, número de orden grande, servicio/mesa/entrega, items con los menús
encadenados indentados, total y pie. Tildes y ñ via codepage CP850.
"""
import json

from ..models import Orden

# Comandos ESC/POS (estándar Epson, soportados por los clones chinos)
INICIALIZAR = b"\x1b@"
CODEPAGE_CP850 = b"\x1bt\x02"
CENTRAR = b"\x1ba\x01"
ALINEAR_IZQ = b"\x1ba\x00"
NEGRITA_ON = b"\x1bE\x01"
NEGRITA_OFF = b"\x1bE\x00"
DOBLE_TAMANO = b"\x1d!\x11"
DOBLE_ALTO = b"\x1d!\x01"
TAMANO_NORMAL = b"\x1d!\x00"
# Alimenta papel y corta (corte parcial con avance: no arranca a mitad)
CORTAR = b"\n\n\n\n" + b"\x1dV\x42\x03"


def _texto(linea: str) -> bytes:
    return linea.encode("cp850", errors="replace") + b"\n"


def _fila(izquierda: str, derecha: str, columnas: int) -> str:
    """Cantidad/plato a la izquierda, monto a la derecha, en una línea."""
    if not derecha:
        # Sin monto no hace falta reservar columna derecha ni el espacio
        if len(izquierda) > columnas:
            izquierda = izquierda[: columnas - 1] + "."
        return izquierda
    espacio = columnas - len(derecha)
    if len(izquierda) > espacio - 1:
        # "…" no existe en CP850 (saldría "?"): se corta con un punto
        izquierda = izquierda[: max(0, espacio - 2)] + "."
    return izquierda.ljust(espacio) + derecha


def _soles(monto: float) -> str:
    return f"{monto:.2f}"


def render_orden(
    orden: Orden,
    local: dict,
    columnas: int = 42,
    categorias: dict[int, str] | None = None,
) -> bytes:
    """El ticket completo de una orden, listo para mandarse a la impresora.

    El impreso funciona como COMANDA (decisión del dueño): las bebidas no
    salen (se sirven en mesa, no se preparan) y tampoco la línea del
    TOTAL — el monto se ve en la pantalla del cliente y en la caja.
    """
    categorias = categorias or {}

    def es_bebida(item) -> bool:
        return categorias.get(item.plato_id) == "bebida"
    numero = f"{orden.numero_orden_dia:03d}"
    partes: list[bytes] = [INICIALIZAR, CODEPAGE_CP850, CENTRAR]

    partes += [NEGRITA_ON, _texto(local.get("nombre") or "Restaurante"), NEGRITA_OFF]
    if local.get("direccion"):
        partes.append(_texto(local["direccion"]))
    if local.get("ruc"):
        partes.append(_texto(f"RUC: {local['ruc']}"))
    partes.append(_texto(""))
    partes += [DOBLE_TAMANO, _texto(f"ORDEN #{numero}"), TAMANO_NORMAL]

    if orden.tipo_servicio == "llevar":
        partes.append(_texto("* PARA LLEVAR *"))
    elif orden.tipo_servicio == "mixto":
        partes.append(_texto("* MIXTO - parte para llevar *"))
    mesas = json.loads(orden.mesa_ids or "[]")
    if mesas and not orden.mesa_liberada:
        nombres = local.get("mesas") or {}
        partes.append(_texto("MESA: " + " + ".join(nombres.get(m, f"#{m}") for m in mesas)))
    if len(orden.items) + len(orden.menus) >= 2 or orden.menus:
        partes.append(_texto(
            "ENTREGA: POR TIEMPOS" if orden.entrega == "separado" else "ENTREGA: TODO JUNTO"
        ))
    partes.append(_texto(f"{orden.fecha.isoformat()} - {orden.hora}"))

    partes += [ALINEAR_IZQ, _texto("-" * columnas)]

    # Los platos van en DOBLE ALTO: mismas columnas, letra al doble —
    # pedido del dueño tras el primer servicio (el ticket es la comanda
    # que viaja a cocina, se lee de un vistazo)
    partes.append(DOBLE_ALTO)

    # Menús encadenados: el menú con su precio, los tiempos indentados,
    # lo quitado en su propia línea destacada (SIN SOPA) y los agregados
    # como +1 PRESA — decisión del dueño: imposibles de pasar por alto
    for om in orden.menus:
        omitidos = om.omitidos()
        partes.append(_texto(_fila(
            f"{om.cantidad} x {om.nombre_snapshot}",
            _soles(om.precio_cobrado * om.cantidad), columnas,
        )))
        for omitido in omitidos:
            nombre = f"  ** SIN {omitido['rotulo'].upper()} **"
            monto = f"-{_soles(omitido['descuento'] * om.cantidad)}" if omitido["descuento"] > 0 else ""
            partes.append(_texto(_fila(nombre, monto, columnas)))
        items_menu = sorted(
            (i for i in orden.items if i.orden_menu_id == om.id and not es_bebida(i)),
            key=lambda i: (i.es_agregado, i.es_extra, i.tiempo_orden or 0),
        )
        for item in items_menu:
            if item.es_agregado:
                nombre = f"  ** +{item.cantidad} {item.nombre_snapshot.upper()} **"
            else:
                nombre = f"  . {item.cantidad} x {item.nombre_snapshot}"
                if item.es_extra:
                    nombre += " (EXTRA)"
            if item.empaque != "mesa":
                nombre += f" [{item.empaque.upper()}]"
            monto = _soles(item.precio_snapshot * item.cantidad) if item.precio_snapshot > 0 else ""
            partes.append(_texto(_fila(nombre, monto, columnas)))
        if om.nota:
            partes.append(_texto(f"  -> {om.nota}"))

    # Venta a la carta
    for item in orden.items:
        if item.orden_menu_id is not None or es_bebida(item):
            continue
        nombre = f"{item.cantidad} x {item.nombre_snapshot}"
        if item.empaque != "mesa":
            nombre += f" [{item.empaque.upper()}]"
        partes.append(_texto(_fila(
            nombre, _soles(item.precio_snapshot * item.cantidad), columnas,
        )))
        if item.nota:
            partes.append(_texto(f"  -> {item.nota}"))

    partes += [TAMANO_NORMAL, _texto("-" * columnas)]
    partes += [CENTRAR, _texto(""), _texto("Paga en caja con este ticket."), _texto("Gracias!")]
    partes.append(CORTAR)
    return b"".join(partes)


def render_prueba(local: dict, columnas: int = 42) -> bytes:
    """Ticket de prueba del botón de Admin → Configuración."""
    partes = [
        INICIALIZAR, CODEPAGE_CP850, CENTRAR,
        NEGRITA_ON, _texto(local.get("nombre") or "Restaurante"), NEGRITA_OFF,
        DOBLE_TAMANO, _texto("PRUEBA OK"), TAMANO_NORMAL,
        _texto(""),
        _texto("Si lees esto, el puente y la"),
        _texto("impresora quedaron conectados."),
        _texto("Tildes de prueba: aji - nino - Peru"),
        _texto("ñ á é í ó ú"),
        _texto("-" * columnas),
        CORTAR,
    ]
    return b"".join(partes)
