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
    partes.append(NEGRITA_ON)
    if mesas and not orden.mesa_liberada:
        nombres = local.get("mesas") or {}
        partes.append(_texto("MESA: " + " + ".join(nombres.get(m, f"#{m}") for m in mesas)))
    elif orden.tipo_servicio != "llevar":
        # Pedido del dueño: si nadie eligió mesa, que el ticket lo diga
        partes.append(_texto("SIN MESA"))
    partes.append(NEGRITA_OFF)
    if len(orden.items) + len(orden.menus) >= 2 or orden.menus:
        # La entrega en letra grande: es la instrucción que cocina y el
        # mozo tienen que ver primero (pedido del dueño)
        partes += [DOBLE_ALTO, NEGRITA_ON, _texto(
            "ENTREGA: POR TIEMPOS" if orden.entrega == "separado" else "ENTREGA: TODO JUNTO"
        ), NEGRITA_OFF, TAMANO_NORMAL]
    partes.append(_texto(f"{orden.fecha.isoformat()} - {orden.hora}"))

    partes += [ALINEAR_IZQ, _texto("-" * columnas)]

    # Los platos van en DOBLE ALTO: mismas columnas, letra al doble —
    # pedido del dueño tras el primer servicio (el ticket es la comanda
    # que viaja a cocina, se lee de un vistazo)
    partes.append(DOBLE_ALTO)

    # La comanda va POR GRUPOS (pedido del dueño tras el servicio real):
    # las entradas arriba, los segundos abajo, cada plato con su
    # observación al costado. Se juntan iguales (2 x Sopa) sin importar de
    # qué menú salieron; los agregados (+1 UNA CARNE MAS) van con los
    # segundos y lo quitado (SIN SOPA) destacado arriba.
    def _nota_de(item) -> str:
        return (item.nota or "").strip()

    # La nota de un menú se le pega a su segundo (ahí van los "sin
    # frijoles"); si el menú no tiene segundo, al primer plato del menú.
    nota_por_item: dict[int, str] = {}
    for om in orden.menus:
        if not om.nota:
            continue
        propios = [
            i for i in orden.items
            if i.orden_menu_id == om.id and not i.es_agregado and not es_bebida(i)
        ]
        destino = next(
            (i for i in propios if categorias.get(i.plato_id) == "fondo" and not i.es_extra),
            propios[0] if propios else None,
        )
        if destino is not None:
            nota_por_item[destino.id] = om.nota.strip()

    # Omitidos de todos los menús, juntados por rótulo
    sin_por_rotulo: dict[str, int] = {}
    for om in orden.menus:
        for omitido in om.omitidos():
            rotulo = omitido["rotulo"].upper()
            sin_por_rotulo[rotulo] = sin_por_rotulo.get(rotulo, 0) + 1
    for rotulo, veces in sin_por_rotulo.items():
        cuantos = f"{veces} " if veces > 1 else ""
        partes.append(_texto(f"** {cuantos}SIN {rotulo} **"))
    if sin_por_rotulo:
        partes.append(_texto(""))

    # Juntar iguales: mismo plato + mismo empaque + misma observación
    grupos: dict[tuple, dict] = {}
    for item in orden.items:
        if es_bebida(item):
            continue
        bucket = "fondo" if item.es_agregado else categorias.get(item.plato_id)
        clave = (
            bucket, item.nombre_snapshot, item.empaque,
            _nota_de(item) or nota_por_item.get(item.id, ""),
            item.es_extra, item.es_agregado,
        )
        grupo = grupos.setdefault(clave, {"cantidad": 0, "monto": 0.0})
        grupo["cantidad"] += item.cantidad
        grupo["monto"] += item.precio_snapshot * item.cantidad

    SECCIONES = [("entrada", "ENTRADAS"), ("fondo", "SEGUNDOS"), ("postre", "POSTRES"), (None, "OTROS")]
    primera_seccion = True
    for bucket, titulo in SECCIONES:
        del_grupo = sorted(
            (c for c in grupos if c[0] == bucket),
            key=lambda c: (c[5], c[4], c[1]),  # platos, extras y al final agregados
        )
        if not del_grupo:
            continue
        if not primera_seccion:
            partes.append(_texto(""))
        primera_seccion = False
        partes += [NEGRITA_ON, _texto(titulo), NEGRITA_OFF]
        for clave in del_grupo:
            _, nombre_plato, empaque, nota, es_extra, es_agregado = clave
            datos = grupos[clave]
            if es_agregado:
                nombre = f"** +{datos['cantidad']} {nombre_plato.upper()} **"
            else:
                nombre = f"{datos['cantidad']} x {nombre_plato}"
                if es_extra:
                    nombre += " (EXTRA)"
            if empaque != "mesa":
                nombre += f" [{empaque.upper()}]"
            monto = _soles(datos["monto"]) if datos["monto"] > 0 else ""
            if nota:
                # La observación al costado si entra; si no, debajo
                con_nota = f"{nombre} -> {nota}"
                if len(con_nota) + (len(monto) + 1 if monto else 0) <= columnas:
                    partes.append(_texto(_fila(con_nota, monto, columnas)))
                else:
                    partes.append(_texto(_fila(nombre, monto, columnas)))
                    partes.append(_texto(f"  -> {nota}"))
            else:
                partes.append(_texto(_fila(nombre, monto, columnas)))

    partes += [TAMANO_NORMAL, _texto("-" * columnas)]
    partes += [CENTRAR, _texto(""), _texto("Paga en caja con este ticket."), _texto("Gracias!")]
    partes.append(CORTAR)
    return b"".join(partes)


def render_bebida(datos: dict, local: dict, columnas: int = 42) -> bytes:
    """Ticket chico de SOLO las gaseosas agregadas a una orden desde caja
    (no se reimprime la comanda completa, pedido del dueño).

    datos: {"numero", "mesas": [nombres], "items": [{nombre, precio,
    cantidad}], "total", "hora" opcional}."""
    partes: list[bytes] = [INICIALIZAR, CODEPAGE_CP850, CENTRAR]
    partes += [NEGRITA_ON, _texto(local.get("nombre") or "Restaurante"), NEGRITA_OFF]
    partes += [DOBLE_TAMANO, _texto("GASEOSAS"), TAMANO_NORMAL]
    linea = f"Orden #{datos['numero']}"
    if datos.get("mesas"):
        linea += f" - Mesa {', '.join(datos['mesas'])}"
    partes += [DOBLE_ALTO, NEGRITA_ON, _texto(linea), NEGRITA_OFF, TAMANO_NORMAL]
    if datos.get("hora"):
        partes.append(_texto(datos["hora"]))

    partes += [ALINEAR_IZQ, _texto("-" * columnas), DOBLE_ALTO]
    for item in datos["items"]:
        partes.append(_texto(_fila(
            f"{item['cantidad']} x {item['nombre']}",
            _soles(item["precio"] * item["cantidad"]),
            columnas,
        )))
    partes += [TAMANO_NORMAL, _texto("-" * columnas)]
    partes += [NEGRITA_ON, DOBLE_ALTO,
               _texto(_fila("TOTAL GASEOSAS", f"S/ {_soles(datos['total'])}", columnas)),
               TAMANO_NORMAL, NEGRITA_OFF]
    partes.append(_texto("Se suma al ticket de la orden"))
    partes.append(CORTAR)
    return b"".join(partes)


def render_cierre(datos: dict, local: dict, columnas: int = 42) -> bytes:
    """Resumen impreso del cierre de caja (pedido del dueño): queda un
    papel con el cuadre del turno — fondo, ventas por método, egresos,
    esperado, contado y el descuadre en grande."""
    partes: list[bytes] = [INICIALIZAR, CODEPAGE_CP850, CENTRAR]
    partes += [NEGRITA_ON, _texto(local.get("nombre") or "Restaurante"), NEGRITA_OFF]
    partes += [DOBLE_TAMANO, _texto("CIERRE DE CAJA"), TAMANO_NORMAL]
    turno = datos.get("turno", 1)
    linea_dia = datos["fecha"]
    if datos.get("turnos_del_dia", 1) > 1 or turno > 1:
        linea_dia += f" - caja {turno} del dia"
    partes.append(_texto(linea_dia))
    partes.append(_texto(
        f"Abierta {datos['hora_apertura'][:5]} - Cerrada {(datos['hora_cierre'] or '')[:5]}"
    ))

    partes += [ALINEAR_IZQ, _texto("-" * columnas)]
    partes.append(_texto(_fila("Fondo inicial", _soles(datos["monto_apertura"]), columnas)))
    partes.append(_texto(_fila("Ventas efectivo", _soles(datos["ventas_efectivo"]), columnas)))
    partes.append(_texto(_fila("Ventas tarjeta", _soles(datos["ventas_tarjeta"]), columnas)))
    partes.append(_texto(_fila("Ventas Yape", _soles(datos["ventas_yape"]), columnas)))
    partes += [NEGRITA_ON, _texto(_fila(
        "TOTAL VENDIDO", _soles(datos["total_sistema"]), columnas
    )), NEGRITA_OFF]

    if datos["egresos"]:
        partes.append(_texto("-" * columnas))
        partes.append(_texto("EGRESOS (salio del cajon):"))
        for e in datos["egresos"]:
            partes.append(_texto(_fila(f"  {e['concepto']}", f"-{_soles(e['monto'])}", columnas)))
        partes += [NEGRITA_ON, _texto(_fila(
            "TOTAL EGRESOS", f"-{_soles(datos['egresos_total'] or 0.0)}", columnas
        )), NEGRITA_OFF]

    por_cobrar = datos.get("por_cobrar") or 0.0
    vueltos = datos.get("vueltos_pendientes") or 0.0
    esperado = round(
        datos["monto_apertura"] + datos["ventas_efectivo"]
        - (datos["egresos_total"] or 0.0) - por_cobrar + vueltos, 2
    )
    partes.append(_texto("-" * columnas))
    if por_cobrar > 0:
        partes.append(_texto(_fila("Falta pagar (no entro)", f"-{_soles(por_cobrar)}", columnas)))
    if vueltos > 0:
        partes.append(_texto(_fila("Vueltos por dar (de mas)", f"+{_soles(vueltos)}", columnas)))
    partes.append(_texto(_fila("Esperado en caja", _soles(esperado), columnas)))
    partes.append(_texto(_fila("Contado", _soles(datos["monto_contado"]), columnas)))

    diferencia = datos["diferencia"]
    veredicto = (
        "CUADRO EXACTO" if diferencia == 0
        else f"SOBRAN {_soles(diferencia)}" if diferencia > 0
        else f"FALTAN {_soles(-diferencia)}"
    )
    partes += [CENTRAR, DOBLE_TAMANO, NEGRITA_ON, _texto(veredicto),
               NEGRITA_OFF, TAMANO_NORMAL]
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
