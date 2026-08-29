from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import CONFIG_DEFAULTS, Config

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigIn(BaseModel):
    nombre_local: str | None = None
    direccion: str | None = None
    ruc: str | None = None
    ventana_cancelacion_seg: int | None = None
    timeout_inactividad_seg: int | None = None
    modo_impresion: str | None = None  # "terminal" | "estacion"
    voz_habilitada: bool | None = None  # kill switch del pedido por voz
    exigir_caja_abierta: bool | None = None  # bloquear ventas sin apertura de caja


def leer_config(db: Session) -> dict:
    valores = dict(CONFIG_DEFAULTS)
    for c in db.scalars(select(Config)).all():
        valores[c.clave] = c.valor
    from ..services.voice import claves_configuradas

    modo = valores["modo_impresion"]
    voz_habilitada = valores["voz_habilitada"] in ("1", "true", "True")
    return {
        "nombre_local": valores["nombre_local"],
        "direccion": valores["direccion"],
        "ruc": valores["ruc"],
        "ventana_cancelacion_seg": int(valores["ventana_cancelacion_seg"]),
        "timeout_inactividad_seg": int(valores["timeout_inactividad_seg"]),
        "modo_impresion": modo if modo in ("terminal", "estacion") else "terminal",
        # El toggle guardado (para el admin) y la disponibilidad efectiva
        # (toggle encendido + API keys presentes) para la terminal
        "voz_habilitada": voz_habilitada,
        "voz_disponible": voz_habilitada and claves_configuradas(),
        "exigir_caja_abierta": valores["exigir_caja_abierta"] in ("1", "true", "True"),
    }


@router.get("")
def obtener(db: Session = Depends(get_db)):
    # Sin auth: la terminal de cliente necesita la duración de la ventana
    # de cancelación y el timeout de inactividad.
    return leer_config(db)


@router.put("", dependencies=[Depends(requiere_admin)])
def actualizar(payload: ConfigIn, db: Session = Depends(get_db)):
    for clave, valor in payload.model_dump(exclude_none=True).items():
        if clave in ("voz_habilitada", "exigir_caja_abierta"):
            valor = "1" if valor else "0"
        registro = db.get(Config, clave)
        if registro is None:
            db.add(Config(clave=clave, valor=str(valor)))
        else:
            registro.valor = str(valor)
    db.commit()
    return leer_config(db)
