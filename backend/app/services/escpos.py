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
    espacio = columnas - len(derecha)
    if len(izquierda) > espacio - 1:
        izquierda = izquierda[: max(0, espacio - 2)] + "…"
    return izquierda.ljust(espacio) + derecha


def _soles(monto: float) -> str:
    return f"{monto:.2f}"


def render_orden(orden: Orden, local: dict, columnas: int = 42) -> bytes:
    """El ticket completo de una orden, listo para mandarse a la impresora."""
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
    import json

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

    # Menús encadenados: el menú con su precio, los tiempos indentados
    for om in orden.menus:
        partes.append(_texto(_fila(
            f"{om.cantidad} x {om.nombre_snapshot}",
            _soles(om.precio_snapshot * om.cantidad), columnas,
        )))
        items_menu = sorted(
            (i for i in orden.items if i.orden_menu_id == om.id),
            key=lambda i: (i.es_extra, i.tiempo_orden or 0),
        )
        for item in items_menu:
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
        if item.orden_menu_id is not None:
            continue
        nombre = f"{item.cantidad} x {item.nombre_snapshot}"
        if item.empaque != "mesa":
            nombre += f" [{item.empaque.upper()}]"
        partes.append(_texto(_fila(
            nombre, _soles(item.precio_snapshot * item.cantidad), columnas,
        )))
        if item.nota:
            partes.append(_texto(f"  -> {item.nota}"))

    partes.append(_texto("-" * columnas))
    partes += [
        DOBLE_ALTO, NEGRITA_ON,
        _texto(_fila("TOTAL", f"S/ {_soles(orden.total)}", columnas)),
        NEGRITA_OFF, TAMANO_NORMAL,
    ]
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
