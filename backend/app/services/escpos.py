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
# Espacio extra a la derecha de cada letra, en puntos (ESC SP n). La letra
# de la impresora es fija (Font A: 12 puntos de ancho, 1.5 mm a 203 ppp) y
# solo escala x2; para leerla más ancha se separan las letras.
ESPACIADO_PLATOS = 2  # 12 → 14 puntos por letra: +16.7 % de ancho de línea
ESPACIADO_NORMAL = b"\x1b\x20\x00"
FUENTE_A = b"\x1bM\x00"
FUENTE_B = b"\x1bM\x01"  # 9 puntos de ancho: letra chica (precuenta)


def _espaciado(puntos: int) -> bytes:
    return b"\x1b\x20" + bytes([puntos])


def columnas_con_espaciado(columnas: int, puntos: int) -> int:
    """Cuántas letras entran por línea si cada una lleva `puntos` extra.
    `columnas` es la configuración en Font A (12 puntos por letra)."""
    return (columnas * 12) // (12 + puntos)
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


def _recuadro(lineas: list[str], columnas: int) -> bytes:
    """Recuadro de lo que falta elegir, compacto (pedido del dueño: la mitad
    del anterior): borde doble fino en letra normal y el texto en negrita
    doble alto. Ningún renglón pasa de `columnas` (si pasa, la impresora lo
    parte en dos y el marco sale roto)."""
    ancho = columnas - 4
    borde_sup = "\u2554" + "\u2550" * (columnas - 2) + "\u2557"
    borde_inf = "\u255a" + "\u2550" * (columnas - 2) + "\u255d"
    cuerpo = b"".join(
        _texto("\u2551 " + linea[:ancho].center(ancho) + " \u2551") for linea in lineas if linea
    )
    return (TAMANO_NORMAL + _texto(borde_sup) + DOBLE_ALTO + NEGRITA_ON + cuerpo + NEGRITA_OFF
            + TAMANO_NORMAL + _texto(borde_inf) + DOBLE_ALTO)


def _plural(rotulo: str, veces: int) -> str:
    """"SEGUNDO" → "SEGUNDOS" cuando son varios ("3 SEGUNDOS")."""
    if veces <= 1:
        return rotulo
    palabras = rotulo.split()
    ultima = palabras[0]
    palabras[0] = ultima + ("S" if ultima[-1] in "AEIOU" else "ES")
    return " ".join(palabras)


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
    partes: list[bytes] = [INICIALIZAR, CODEPAGE_CP850, FUENTE_A, ESPACIADO_NORMAL, ALINEAR_IZQ]

    # Comanda de cocina: sin nombre del local (pedido del dueño). Arriba,
    # en grande, la orden pegada a la izquierda y la mesa a la derecha
    mesas = json.loads(orden.mesa_ids or "[]")
    if mesas and not orden.mesa_liberada:
        nombres = local.get("mesas") or {}
        mesa = "MESA " + " + ".join(nombres.get(m, f"#{m}") for m in mesas)
    elif orden.tipo_servicio == "llevar":
        mesa = "LLEVAR"
    else:
        # Pedido del dueño: si nadie eligió mesa, que el ticket lo diga
        mesa = "SIN MESA"
    izquierda = f"ORDEN #{numero}"
    media = columnas // 2  # en letra doble entra la mitad
    partes += [DOBLE_TAMANO, NEGRITA_ON]
    if len(izquierda) + 1 + len(mesa) <= media:
        partes.append(_texto(izquierda + mesa.rjust(media - len(izquierda))))
    else:
        partes += [_texto(izquierda), _texto(mesa[:media].rjust(media))]
    partes += [NEGRITA_OFF, TAMANO_NORMAL]

    # "OK y pagó" / "OK y no pagó" de la terminal
    if orden.pago_al_pedir == "pagado":
        partes += [CENTRAR, DOBLE_ALTO, NEGRITA_ON, _texto("PAGADO"), NEGRITA_OFF, TAMANO_NORMAL]
    elif orden.pago_al_pedir == "pendiente":
        partes += [CENTRAR, DOBLE_ALTO, NEGRITA_ON, _texto("** NO PAGO **"), NEGRITA_OFF, TAMANO_NORMAL]
    partes.append(CENTRAR)
    if orden.tipo_servicio == "mixto":
        partes.append(_texto("* MIXTO - parte para llevar *"))
    if len(orden.items) + len(orden.menus) >= 2 or orden.menus:
        # La entrega en negrita y tamaño normal (pedido del dueño: en
        # grande competía con la mesa)
        partes += [NEGRITA_ON, _texto(_linea_entrega(orden, categorias)), NEGRITA_OFF]

    partes += [ALINEAR_IZQ, _texto("-" * columnas)]

    # Los platos van en DOBLE ALTO: mismas columnas, letra al doble —
    # pedido del dueño tras el primer servicio (el ticket es la comanda
    # que viaja a cocina, se lee de un vistazo). Además letras separadas
    # (ESPACIADO_PLATOS): la línea es más ancha, así que entran menos.
    columnas_comanda = columnas
    columnas = columnas_con_espaciado(columnas_comanda, ESPACIADO_PLATOS)
    partes += [DOBLE_ALTO, _espaciado(ESPACIADO_PLATOS)]

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
            sin_por_rotulo[rotulo] = sin_por_rotulo.get(rotulo, 0) + om.cantidad
    for rotulo, veces in sin_por_rotulo.items():
        cuantos = f"{veces} " if veces > 1 else ""
        partes.append(_texto(f"** {cuantos}SIN {rotulo} **"))
    # Lo que una persona aún no eligió también va arriba: el ticket sale
    # igual y cocina sabe que falta ("2 SEGUNDO SIN ELEGIR")
    pendientes_por_rotulo: dict[tuple[str, str], int] = {}
    for om in orden.menus:
        for pendiente in om.pendientes():
            clave_p = (pendiente["rotulo"].upper(), (om.nombre_persona or "").upper())
            pendientes_por_rotulo[clave_p] = pendientes_por_rotulo.get(clave_p, 0) + om.cantidad
    for (rotulo, persona), veces in pendientes_por_rotulo.items():
        cuantos = f"{veces} " if veces > 1 else ""
        de_quien = f" ({persona})" if persona else ""
        partes.append(_recuadro([f"{cuantos}{_plural(rotulo, veces)}{de_quien}", "FALTA ELEGIR"], columnas))
    if sin_por_rotulo or pendientes_por_rotulo:
        partes.append(_texto(""))

    # Nombre de la persona (opcional) de cada menú: va al costado de sus
    # platos para que cocina y el mozo sepan de quién es cada uno
    persona_de_menu = {om.id: (om.nombre_persona or "").strip().upper() for om in orden.menus}
    # Si las personas salen distinto (unas junto, otras por tiempos), cada
    # plato de quien va por tiempos lo dice: la línea de arriba solo cuenta
    entrega_de_menu = {om.id: om.entrega or orden.entrega for om in orden.menus}
    mixta = "/" in _linea_entrega(orden, categorias)

    # Juntar iguales: mismo plato + mismo empaque + misma observación
    # (+ misma persona, si tiene nombre)
    grupos: dict[tuple, dict] = {}
    for item in orden.items:
        if es_bebida(item):
            continue
        bucket = "fondo" if item.es_agregado else categorias.get(item.plato_id)
        clave = (
            bucket, item.nombre_snapshot, item.empaque,
            # La presa / el cambio a huevo va primero, luego la observación
            "; ".join(filter(None, [item.detalle, _nota_de(item) or nota_por_item.get(item.id, "")])),
            item.es_extra, item.es_agregado, item.espera,
            persona_de_menu.get(item.orden_menu_id, ""),
            mixta and entrega_de_menu.get(item.orden_menu_id, orden.entrega) == "separado",
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
            _, nombre_plato, empaque, nota, es_extra, es_agregado, espera, persona, por_tiempos = clave
            datos = grupos[clave]
            if es_agregado:
                nombre = f"** +{datos['cantidad']} {nombre_plato.upper()} **"
            else:
                nombre = f"{datos['cantidad']} x {nombre_plato}"
                if es_extra:
                    nombre += " (EXTRA)"
                if espera:
                    # "Va a esperar": reservado, cocina no lo saca todavía
                    nombre += " (ESPERA)"
            if persona:
                nombre += f" ({persona})"
            if por_tiempos:
                nombre += " (SEPARADO)"
            # En OTROS (gaseosas y cargos sin plato) no van montos: la
            # comanda es para cocina, la plata se ve en caja
            monto = "" if bucket is None else (_soles(datos["monto"]) if datos["monto"] > 0 else "")
            if empaque != "mesa":
                # La etiqueta va SIEMPRE completa, con su espacio: si el
                # nombre es largo se recorta el plato, nunca el [TAPER]
                # (antes salía "...Huancaína [." y no se entendía nada)
                etiqueta = f" [{empaque.upper()}]"
                ancho = columnas - len(etiqueta) - (len(monto) + 1 if monto else 0)
                if len(nombre) > ancho:
                    nombre = nombre[: max(0, ancho - 1)] + "."
                nombre += etiqueta
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

    columnas = columnas_comanda
    partes += [TAMANO_NORMAL, ESPACIADO_NORMAL, _texto("-" * columnas)]
    # Sin "Gracias!" (es comanda de cocina): abajo va la fecha y la hora
    partes += [CENTRAR, _texto(f"{orden.fecha.isoformat()} - {orden.hora}")]
    partes.append(CORTAR)
    return b"".join(partes)


def _linea_entrega(orden, categorias: dict[int, str] | None = None) -> str:
    """La entrega en grande. Cada persona (menú) puede tener la suya: si
    todas coinciden se imprime como siempre; si no, cuántas de cada una.
    Las bebidas sueltas no cuentan: no pasan por cocina."""
    categorias = categorias or {}
    entregas = [om.entrega or orden.entrega for om in orden.menus for _ in range(om.cantidad)]
    if any(
        i.orden_menu_id is None and not i.es_cargo and categorias.get(i.plato_id) != "bebida"
        for i in orden.items
    ) or not entregas:
        entregas.append(orden.entrega)
    if len(set(entregas)) == 1:
        return "ENTREGA: SEPARADO" if entregas[0] == "separado" else "ENTREGA: TODO JUNTO"
    juntos = entregas.count("junto")
    return f"ENTREGA: {juntos} JUNTO / {len(entregas) - juntos} SEPARADO"


def render_bebida(datos: dict, local: dict, columnas: int = 42) -> bytes:
    """Ticket chico de SOLO las gaseosas agregadas a una orden desde caja
    (no se reimprime la comanda completa, pedido del dueño).

    datos: {"numero", "mesas": [nombres], "items": [{nombre, precio,
    cantidad}], "total", "hora" opcional}."""
    partes: list[bytes] = [INICIALIZAR, CODEPAGE_CP850, CENTRAR]
    partes += [NEGRITA_ON, _texto(local.get("nombre") or "Restaurante"), NEGRITA_OFF]
    titulo = datos.get("titulo") or "GASEOSAS"
    partes += [DOBLE_TAMANO, _texto(titulo), TAMANO_NORMAL]
    linea = f"Orden #{datos['numero']}"
    if datos.get("mesas"):
        linea += f" - Mesa {', '.join(datos['mesas'])}"
    partes += [DOBLE_ALTO, NEGRITA_ON, _texto(linea), NEGRITA_OFF, TAMANO_NORMAL]
    if datos.get("hora"):
        partes.append(_texto(datos["hora"]))

    partes += [ALINEAR_IZQ, _texto("-" * columnas), DOBLE_ALTO]
    for item in datos["items"]:
        monto = item["precio"] * item["cantidad"]
        partes.append(_texto(_fila(
            f"{item['cantidad']} x {item['nombre']}",
            _soles(monto) if monto else "",
            columnas,
        )))
    partes += [TAMANO_NORMAL, _texto("-" * columnas)]
    if titulo == "GASEOSAS":
        partes += [NEGRITA_ON, DOBLE_ALTO,
                   _texto(_fila("TOTAL GASEOSAS", f"S/ {_soles(datos['total'])}", columnas)),
                   TAMANO_NORMAL, NEGRITA_OFF]
        partes.append(_texto("Se suma al ticket de la orden"))
    else:
        # Cambio de una orden ya registrada: cuánto subió o bajó la cuenta
        signo = "+" if datos["total"] >= 0 else "-"
        partes += [NEGRITA_ON, _texto(_fila(
            "La cuenta cambia", f"{signo}S/ {_soles(abs(datos['total']))}", columnas,
        )), NEGRITA_OFF]
        partes.append(_texto(f"Nuevo total: S/ {_soles(datos['total_orden'])}"))
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

    # Lo vendido en el turno (pedido del dueño): cuántos pedidos y menús,
    # y cada plato con su cantidad, lo más vendido arriba
    venta = datos.get("venta")
    if venta:
        partes += [NEGRITA_ON, _texto("LO VENDIDO EN EL TURNO"), NEGRITA_OFF]
        pedidos = f"{venta['pedidos']}"
        if venta["anulados"]:
            pedidos += f" (+{venta['anulados']} anulados)"
        partes.append(_texto(_fila("Pedidos", pedidos, columnas)))
        partes.append(_texto(_fila("Menús", str(venta["menus"]), columnas)))
        for p in venta["platos"]:
            partes.append(_texto(_fila(f"{p['cantidad']:>3} x {p['nombre']}", "", columnas)))
        partes.append(_texto("-" * columnas))

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


def render_precuenta(orden: Orden, local: dict, columnas: int = 42) -> bytes:
    """Precuenta para el cliente que pagó al pedir ("OK y pagó"): corta y
    en letra chica (Font B, 9 puntos: entran 4/3 de las columnas). Le sirve
    de comprobante si su pedido se pierde."""
    ancho = (columnas * 12) // 9
    numero = f"{orden.numero_orden_dia:03d}"
    mesas = json.loads(orden.mesa_ids or "[]")
    nombres = local.get("mesas") or {}
    cabecera = f"Orden #{numero}"
    if mesas:
        cabecera += " - Mesa " + " + ".join(nombres.get(m, f"#{m}") for m in mesas)
    partes: list[bytes] = [INICIALIZAR, CODEPAGE_CP850, FUENTE_B, CENTRAR,
                           NEGRITA_ON, _texto(local.get("nombre") or "Restaurante"),
                           _texto("PRECUENTA"), NEGRITA_OFF, _texto(cabecera),
                           _texto(f"{orden.fecha.isoformat()} - {orden.hora}"),
                           ALINEAR_IZQ, _texto("-" * ancho)]
    for om in orden.menus:
        propios = [i for i in orden.items if i.orden_menu_id == om.id]
        platos = " + ".join(i.nombre_snapshot for i in propios if not i.es_agregado and i.precio_snapshot == 0)
        monto = om.precio_cobrado * om.cantidad + sum(i.precio_snapshot * i.cantidad for i in propios)
        partes.append(_texto(_fila(f"{om.cantidad} x {om.nombre_snapshot}", _soles(monto), ancho)))
        if platos:
            partes.append(_texto(f"  {platos}"[:ancho]))
    for item in orden.items:
        if item.orden_menu_id is None:
            partes.append(_texto(_fila(f"{item.cantidad} x {item.nombre_snapshot}",
                                       _soles(item.precio_snapshot * item.cantidad), ancho)))
    partes += [_texto("-" * ancho), NEGRITA_ON,
               _texto(_fila("TOTAL PAGADO", f"S/ {_soles(orden.total)}", ancho)), NEGRITA_OFF,
               CENTRAR, _texto("Guarde este papel: es el comprobante de su pedido"),
               FUENTE_A, CORTAR]
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
