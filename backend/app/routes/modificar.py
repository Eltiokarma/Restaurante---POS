"""Cambios a una orden YA registrada (pedido del dueño).

El cliente se arrepiente después de la ventana de cancelación: quiere la
sopa que había quitado, que su segundo vaya en táper, sumar a otra
persona o una gaseosa, o quitar algo. Cada cambio:

- recalcula el total desde cero (menús − descuentos + cada ítem), igual
  que al crear la orden, así nunca se descuadra;
- ajusta el kardex (consume lo nuevo, devuelve lo quitado);
- avisa a cocina con un ticket chico "CAMBIO" con SOLO lo que cambió
  (no se reimprime la comanda entera), en modo puente/estación;
- lo quitado queda en el log de cancelaciones (análisis), nunca se borra
  en silencio.

Solo órdenes de hoy, no anuladas y no anotadas a mano.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Cancelacion, Config, MenuPlantilla, Orden, OrdenItem, OrdenMenu, Plato, TicketBebida,
    ahora_lima, hoy_lima,
)
from ..services.cocina import recalcular_estado_orden
from ..services.inventario import consumir_item, devolver_item
from ..services.orders import (
    EleccionInvalida, EntregaObligadaSeparado, PlatoNoDisponible, _armar_menu,
    _plato_activo, _tipo_servicio_de,
)
from .config import leer_config
from .orders import (
    EMPAQUES, BebidaPedida, ItemIn, MenuIn, _mapa_categorias, _mapa_mesas, _orden_a_dict,
    _sumar_bebidas, _validar_bebidas,
)

router = APIRouter(prefix="/api/orders", tags=["modificar"])


# ---------- utilidades ----------

def _orden_modificable(db: Session, orden_id: int) -> Orden:
    orden = db.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if orden.estado == "anulada":
        raise HTTPException(status_code=409, detail="La orden está anulada")
    if orden.fecha != hoy_lima() or orden.origen == "manual":
        raise HTTPException(status_code=409, detail="Solo se modifican los pedidos de hoy")
    return orden


def _precio_taper(db: Session) -> float:
    registro = db.get(Config, "precio_taper")
    return max(0.0, float(registro.valor)) if registro else 0.0


def _recalcular(db: Session, orden: Orden) -> None:
    """Línea del táper, tipo de servicio, total y estado, desde cero."""
    precio_taper = _precio_taper(db)
    cargo = next((i for i in orden.items if i.es_cargo and i.nombre_snapshot == "Táper"), None)
    en_taper = sum(i.cantidad for i in orden.items if i.empaque == "taper" and not i.es_cargo)
    if precio_taper > 0 and en_taper > 0:
        if cargo is None:
            orden.items.append(OrdenItem(
                plato_id=None, nombre_snapshot="Táper", precio_snapshot=precio_taper,
                cantidad=en_taper, empaque="mesa", nota="", es_cargo=True, estado="entregado",
            ))
        else:
            cargo.cantidad = en_taper
    elif cargo is not None:
        orden.items.remove(cargo)
        db.delete(cargo)

    platos = [i for i in orden.items if not i.es_cargo]
    orden.tipo_servicio = _tipo_servicio_de([i.empaque for i in platos] or ["mesa"])
    total = 0.0
    for om in orden.menus:
        total += om.precio_snapshot * om.cantidad
        total -= sum(o["descuento"] for o in om.omitidos()) * om.cantidad
    total += sum(i.precio_snapshot * i.cantidad for i in orden.items)
    orden.total = round(total, 2)
    recalcular_estado_orden(orden)


def _cerrar_cambio(db: Session, orden: Orden, total_antes: float, lineas: list[dict],
                   quitado: list[dict] | None = None) -> dict:
    """Recalcula, deja el ticket de CAMBIO para cocina y responde."""
    _recalcular(db, orden)
    diferencia = round(orden.total - total_antes, 2)
    modo = leer_config(db)["modo_impresion"]
    if lineas and modo in ("puente", "estacion"):
        db.add(TicketBebida(
            orden_id=orden.id, detalle_json=json.dumps(lineas, ensure_ascii=False),
            total=diferencia, titulo="CAMBIO", total_orden=orden.total,
        ))
    if quitado:
        ahora = ahora_lima()
        db.add(Cancelacion(
            fecha=ahora.date(), hora=ahora.strftime("%H:%M:%S"),
            items_json=json.dumps(quitado, ensure_ascii=False),
            total=round(sum(q["precio"] * q["cantidad"] for q in quitado), 2),
        ))
    db.commit()
    db.refresh(orden)
    mapa = _mapa_mesas(db)
    ids_mesa = json.loads(orden.mesa_ids or "[]")
    return {
        "orden": _orden_a_dict(orden, mapa, _mapa_categorias(db)),
        "modo_impresion": modo,
        # En modo terminal la propia pantalla imprime este ticket
        "ticket_cambio": {
            "numero": f"{orden.numero_orden_dia:03d}",
            "mesas": [mapa.get(i, f"#{i}") for i in ids_mesa],
            "items": lineas,
            "total": diferencia,
            "titulo": "CAMBIO",
            "total_orden": orden.total,
        } if lineas else None,
    }


def _linea(cantidad: int, texto: str, precio: float = 0.0) -> dict:
    return {"cantidad": cantidad, "nombre": texto, "precio": round(precio, 2)}


def _de_quien(om: OrdenMenu | None) -> str:
    return f" ({om.nombre_persona.upper()})" if om is not None and om.nombre_persona else ""


# ---------- agregar personas, platos y gaseosas ----------

class AgregarIn(BaseModel):
    menus: list[MenuIn] = Field(default_factory=list, max_length=20)
    items: list[ItemIn] = Field(default_factory=list, max_length=20)
    bebidas: list[BebidaPedida] = Field(default_factory=list, max_length=10)


@router.post("/{orden_id}/agregar")
def agregar_a_orden(orden_id: int, payload: AgregarIn, db: Session = Depends(get_db)):
    """Suma personas (menús), platos de carta o gaseosas a la orden."""
    orden = _orden_modificable(db, orden_id)
    if not payload.menus and not payload.items and not payload.bebidas:
        raise HTTPException(status_code=422, detail="No hay nada que agregar")
    for item in payload.items:
        if item.empaque not in EMPAQUES:
            raise HTTPException(status_code=422, detail=f"Empaque inválido: {item.empaque}")
    for menu in payload.menus:
        if menu.empaque not in EMPAQUES or any(e not in EMPAQUES for e in menu.empaques.values()):
            raise HTTPException(status_code=422, detail="Empaque inválido")
    _validar_bebidas(db, payload.bebidas)

    total_antes = orden.total
    ya_estaban = {i.id for i in orden.items}
    menus_antes = {om.id for om in orden.menus}
    try:
        for pedido in payload.menus:
            _armar_menu(db, orden, pedido.model_dump(), orden.entrega)
        for pedido in payload.items:
            plato = _plato_activo(db, pedido.plato_id)
            orden.items.append(OrdenItem(
                plato_id=plato.id, nombre_snapshot=plato.nombre, nombre_corto=plato.nombre_corto, precio_snapshot=plato.precio,
                cantidad=pedido.cantidad, empaque=pedido.empaque, nota=pedido.nota.strip(),
            ))
    except PlatoNoDisponible as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"'{e.nombre}' ya no está disponible")
    except EntregaObligadaSeparado as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"{e.nombre} se prepara al momento: va por tiempos")
    except EleccionInvalida as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    if payload.bebidas:
        _sumar_bebidas(db, orden, payload.bebidas)
    db.flush()

    lineas: list[dict] = []
    for item in orden.items:
        if item.id in ya_estaban or item.nombre_snapshot == "Táper":
            continue
        if not item.es_cargo:
            consumir_item(db, orden, item)
        om = item.orden_menu
        etiqueta = f" [{item.empaque.upper()}]" if item.empaque != "mesa" else ""
        espera = " (ESPERA)" if item.espera else ""
        prefijo = "+" if item.es_agregado else "AGREGAR: "
        lineas.append(_linea(item.cantidad, f"{prefijo}{item.nombre_impreso}{etiqueta}{espera}{_de_quien(om)}"))
    for om in orden.menus:
        if om.id in menus_antes:
            continue
        # Lo que la persona nueva aún no eligió también va al aviso
        for p in om.pendientes():
            lineas.append(_linea(om.cantidad, f"AGREGAR: {p['rotulo'].upper()} SIN ELEGIR{_de_quien(om)}"))
        for o in om.omitidos():
            lineas.append(_linea(om.cantidad, f"(SIN {o['rotulo'].upper()}){_de_quien(om)}"))
    return _cerrar_cambio(db, orden, total_antes, lineas)


# ---------- devolver un tiempo quitado ("ahora sí quiere la sopa") ----------

class DevolverIn(BaseModel):
    tiempo_orden: int
    # El plato elegido; sin plato queda "por elegir" (la comanda lo dice)
    plato_id: int | None = None


@router.post("/{orden_id}/menus/{orden_menu_id}/devolver")
def devolver_tiempo(orden_id: int, orden_menu_id: int, payload: DevolverIn,
                    db: Session = Depends(get_db)):
    orden = _orden_modificable(db, orden_id)
    om = db.get(OrdenMenu, orden_menu_id)
    if om is None or om.orden_id != orden.id:
        raise HTTPException(status_code=404, detail="Esa persona no está en la orden")
    omitidos = om.omitidos()
    omitido = next((o for o in omitidos if o["tiempo_orden"] == payload.tiempo_orden), None)
    if omitido is None:
        raise HTTPException(status_code=409, detail="Ese tiempo no estaba quitado")
    plantilla = db.get(MenuPlantilla, om.menu_id) if om.menu_id else None
    tiempo = next((t for t in plantilla.tiempos if t.orden == payload.tiempo_orden), None) if plantilla else None
    if tiempo is None:
        raise HTTPException(status_code=409, detail="Ese menú ya no existe")

    total_antes = orden.total
    om.omitidos_json = json.dumps(
        [o for o in omitidos if o["tiempo_orden"] != payload.tiempo_orden], ensure_ascii=False,
    )
    hermanos = [i for i in orden.items if i.orden_menu_id == om.id and not i.es_agregado]
    empaque = hermanos[0].empaque if hermanos else "mesa"
    if payload.plato_id is None:
        om.pendientes_json = json.dumps(
            om.pendientes() + [{"tiempo_orden": tiempo.orden, "rotulo": tiempo.rotulo}],
            ensure_ascii=False,
        )
        lineas = [_linea(om.cantidad, f"AGREGAR: {tiempo.rotulo.upper()} SIN ELEGIR{_de_quien(om)}")]
    else:
        alternativa = next((a for a in tiempo.alternativas if a.plato_id == payload.plato_id), None)
        plato = db.get(Plato, payload.plato_id)
        if alternativa is None:
            raise HTTPException(status_code=422, detail="Ese plato no es una opción de este tiempo")
        if plato is None or not plato.activo_hoy:
            raise HTTPException(status_code=409, detail="Ese plato ya no está disponible")
        item = OrdenItem(
            plato_id=plato.id, nombre_snapshot=plato.nombre, nombre_corto=plato.nombre_corto, precio_snapshot=alternativa.recargo,
            cantidad=om.cantidad, empaque=empaque, nota="", tiempo_orden=tiempo.orden,
        )
        item.orden_menu = om
        orden.items.append(item)
        db.flush()
        consumir_item(db, orden, item)
        etiqueta = f" [{empaque.upper()}]" if empaque != "mesa" else ""
        lineas = [_linea(om.cantidad, f"AGREGAR: {plato.nombre_corto or plato.nombre}{etiqueta}{_de_quien(om)}")]
    return _cerrar_cambio(db, orden, total_antes, lineas)


# ---------- cambiar el empaque de un plato ----------

class EmpaqueIn(BaseModel):
    empaque: str


@router.patch("/{orden_id}/items/{item_id}/empaque")
def cambiar_empaque(orden_id: int, item_id: int, payload: EmpaqueIn, db: Session = Depends(get_db)):
    orden = _orden_modificable(db, orden_id)
    if payload.empaque not in EMPAQUES:
        raise HTTPException(status_code=422, detail=f"Empaque inválido: {payload.empaque}")
    item = db.get(OrdenItem, item_id)
    if item is None or item.orden_id != orden.id or item.es_cargo:
        raise HTTPException(status_code=404, detail="Ese plato no está en la orden")
    if item.empaque == payload.empaque:
        return _cerrar_cambio(db, orden, orden.total, [])
    total_antes = orden.total
    item.empaque = payload.empaque
    lineas = [_linea(item.cantidad, f"{item.nombre_impreso} -> {payload.empaque.upper()}{_de_quien(item.orden_menu)}")]
    return _cerrar_cambio(db, orden, total_antes, lineas)


# ---------- quitar una persona o un plato ----------

@router.delete("/{orden_id}/menus/{orden_menu_id}")
def quitar_persona(orden_id: int, orden_menu_id: int, db: Session = Depends(get_db)):
    orden = _orden_modificable(db, orden_id)
    om = db.get(OrdenMenu, orden_menu_id)
    if om is None or om.orden_id != orden.id:
        raise HTTPException(status_code=404, detail="Esa persona no está en la orden")
    sueltos = [i for i in orden.items if i.orden_menu_id is None and not i.es_cargo]
    if len(orden.menus) == 1 and not sueltos:
        raise HTTPException(status_code=409, detail="Es lo único del pedido: mejor anula la orden")
    total_antes = orden.total
    precio = om.precio_snapshot - sum(o["descuento"] for o in om.omitidos())
    suyos = [i for i in orden.items if i.orden_menu_id == om.id]
    for item in suyos:
        devolver_item(db, orden, item)
        precio += item.precio_snapshot * item.cantidad / max(om.cantidad, 1)
        orden.items.remove(item)
        db.delete(item)
    platos = ", ".join(i.nombre_snapshot for i in suyos if not i.es_agregado) or om.nombre_snapshot
    lineas = [_linea(om.cantidad, f"QUITAR: {platos}{_de_quien(om)}")]
    quitado = [{"nombre": f"{om.nombre_snapshot} ({platos})", "precio": round(precio, 2), "cantidad": om.cantidad}]
    orden.menus.remove(om)
    db.delete(om)
    return _cerrar_cambio(db, orden, total_antes, lineas, quitado)


@router.delete("/{orden_id}/items/{item_id}")
def quitar_item(orden_id: int, item_id: int, db: Session = Depends(get_db)):
    """Quita un plato de carta, una gaseosa, un agregado o una porción
    extra. El plato de un tiempo del menú no se quita así: eso cambia el
    menú (quitar a la persona o pedir el tiempo de nuevo)."""
    orden = _orden_modificable(db, orden_id)
    item = db.get(OrdenItem, item_id)
    if item is None or item.orden_id != orden.id or item.nombre_snapshot == "Táper":
        raise HTTPException(status_code=404, detail="Ese plato no está en la orden")
    if item.orden_menu_id is not None and not (item.es_agregado or item.es_extra):
        raise HTTPException(status_code=409, detail="Es parte del menú: quita a la persona")
    resto = [i for i in orden.items if i.id != item.id and not i.es_cargo]
    if not orden.menus and not resto:
        raise HTTPException(status_code=409, detail="Es lo único del pedido: mejor anula la orden")
    total_antes = orden.total
    devolver_item(db, orden, item)
    lineas = [_linea(item.cantidad, f"QUITAR: {item.nombre_impreso}{_de_quien(item.orden_menu)}")]
    quitado = [{"nombre": item.nombre_snapshot, "precio": item.precio_snapshot, "cantidad": item.cantidad}]
    orden.items.remove(item)
    db.delete(item)
    return _cerrar_cambio(db, orden, total_antes, lineas, quitado)
