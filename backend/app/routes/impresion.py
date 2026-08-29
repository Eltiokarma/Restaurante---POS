"""Cola de impresión para el puente del local (modo "puente").

El puente (scripts/puente_impresion.py) corre en una PC o aparato del
local, pide esta cola cada pocos segundos, manda los bytes ESC/POS a la
impresora de red y marca cada orden como impresa con el endpoint que ya
existe (POST /api/orders/{id}/printed). Así el backend puede vivir en la
nube (Railway) y la impresora en la red del restaurante.
"""
import base64
import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import requiere_admin
from ..db import get_db
from ..models import Config, Mesa, Orden, hoy_lima
from ..routes.config import leer_config
from ..services.escpos import render_orden, render_prueba

router = APIRouter(prefix="/api/print", tags=["impresion"])

CLAVE_PRUEBA = "imprimir_prueba"


@router.post("/prueba", dependencies=[Depends(requiere_admin)])
def pedir_ticket_de_prueba(db: Session = Depends(get_db)):
    """Encola un ticket de prueba; el puente lo recoge en su próximo ciclo."""
    registro = db.get(Config, CLAVE_PRUEBA)
    if registro is None:
        db.add(Config(clave=CLAVE_PRUEBA, valor="1"))
    else:
        registro.valor = "1"
    db.commit()
    return {"encolada": True}


@router.get("/cola")
def cola_de_impresion(db: Session = Depends(get_db)):
    """Trabajos pendientes en bytes ESC/POS (base64) + datos de la impresora.

    Sin auth de admin (el PIN del local aplica como en toda la API): el
    puente manda el header X-Pin-Local. La orden se marca impresa recién
    cuando el puente confirma con POST /api/orders/{id}/printed — si la
    impresora falla, el trabajo sigue en cola.
    """
    config = leer_config(db)
    local = {
        "nombre": config["nombre_local"],
        "direccion": config["direccion"],
        "ruc": config["ruc"],
        "mesas": {m.id: m.nombre for m in db.scalars(select(Mesa)).all()},
    }
    columnas = config["impresora_columnas"]
    trabajos = []

    # Ticket de prueba (botón de Admin → Configuración): se consume al servirse
    registro_prueba = db.get(Config, CLAVE_PRUEBA)
    if registro_prueba is not None and registro_prueba.valor == "1":
        registro_prueba.valor = "0"
        db.commit()
        trabajos.append({
            "tipo": "prueba",
            "orden_id": None,
            "numero": "PRUEBA",
            "datos_b64": base64.b64encode(render_prueba(local, columnas)).decode(),
        })

    ordenes = db.scalars(
        select(Orden)
        .options(selectinload(Orden.items), selectinload(Orden.menus))
        .where(
            Orden.fecha == hoy_lima(),
            Orden.impreso == False,  # noqa: E712
            Orden.estado != "anulada",
        )
        .order_by(Orden.numero_orden_dia)
    ).all()
    for orden in ordenes:
        trabajos.append({
            "tipo": "orden",
            "orden_id": orden.id,
            "numero": f"{orden.numero_orden_dia:03d}",
            "datos_b64": base64.b64encode(render_orden(orden, local, columnas)).decode(),
        })

    return {
        "impresora": {
            "ip": config["impresora_ip"],
            "puerto": config["impresora_puerto"],
        },
        "trabajos": trabajos,
    }
