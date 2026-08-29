"""Endpoints del pedido por voz.

Las API keys viven en el .env del backend; el frontend nunca las ve.
"""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import requiere_admin
from ..db import get_db
from ..models import VozLog, ahora_lima, hoy_lima
from ..services import voice
from .config import leer_config

router = APIRouter(prefix="/api/voice", tags=["voice"])

RESULTADOS_VALIDOS = ["aceptado", "corregido", "descartado"]
# Para mostrar el costo en soles en el panel del admin (ajustable)
TIPO_CAMBIO_SOLES = 3.6

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # ~20s de webm caben de sobra


def _voz_operativa(db: Session) -> None:
    if not leer_config(db)["voz_habilitada"]:
        raise HTTPException(status_code=503, detail="El pedido por voz está apagado")
    if not voice.claves_configuradas():
        raise HTTPException(
            status_code=503,
            detail="Faltan las API keys de voz en el .env del servidor",
        )


@router.post("/order")
async def pedido_por_voz(
    audio: UploadFile = File(...),
    duracion_seg: float = Form(0.0),
    db: Session = Depends(get_db),
):
    _voz_operativa(db)
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="El audio es demasiado largo")
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="No llegó ningún audio")

    try:
        transcripcion, resultado, items_resueltos, latencia_ms, costo_usd = (
            voice.procesar_audio(db, audio_bytes, audio.filename or "audio.webm", duracion_seg or None)
        )
    except voice.VozError as e:
        raise HTTPException(status_code=502, detail=e.mensaje_cliente)

    log = VozLog(
        fecha=hoy_lima(),
        hora=ahora_lima().strftime("%H:%M:%S"),
        transcripcion=transcripcion,
        interpretacion_json=json.dumps(resultado, ensure_ascii=False),
        resultado="pendiente",
        latencia_ms=latencia_ms,
        audio_duracion_s=duracion_seg or None,
        costo_usd=costo_usd,
    )
    db.add(log)
    db.commit()

    return {
        "log_id": log.id,
        "transcripcion": transcripcion,
        "items_resueltos": items_resueltos,
        "no_encontrados": resultado["no_encontrados"],
        "notas": resultado["notas"],
        "latencia_ms": latencia_ms,
    }


class ResultadoIn(BaseModel):
    resultado: str


@router.patch("/logs/{log_id}")
def actualizar_resultado(log_id: int, payload: ResultadoIn, db: Session = Depends(get_db)):
    if payload.resultado not in RESULTADOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Resultado inválido: {payload.resultado}")
    log = db.get(VozLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Log no encontrado")
    log.resultado = payload.resultado
    db.commit()
    return {"id": log.id, "resultado": log.resultado}


@router.get("/logs/today", dependencies=[Depends(requiere_admin)])
def logs_de_hoy(db: Session = Depends(get_db)):
    """Panel de voz del admin: logs del día + métricas + costo estimado."""
    logs = db.scalars(
        select(VozLog).where(VozLog.fecha == hoy_lima()).order_by(VozLog.id.desc())
    ).all()

    total = len(logs)
    conteo = {r: sum(1 for l in logs if l.resultado == r) for r in RESULTADOS_VALIDOS}
    latencias = [l.latencia_ms for l in logs]
    costo_usd = sum(l.costo_usd or 0 for l in logs)

    def pct(n: int) -> float:
        return round(n / total * 100, 1) if total else 0.0

    return {
        "logs": [
            {
                "id": l.id,
                "hora": l.hora,
                "transcripcion": l.transcripcion,
                "interpretacion": json.loads(l.interpretacion_json),
                "resultado": l.resultado,
                "latencia_ms": l.latencia_ms,
            }
            for l in logs
        ],
        "metricas": {
            "total": total,
            "pct_aceptado": pct(conteo["aceptado"]),
            "pct_corregido": pct(conteo["corregido"]),
            "pct_descartado": pct(conteo["descartado"]),
            "latencia_promedio_ms": round(sum(latencias) / total) if total else None,
            "costo_dia_usd": round(costo_usd, 4),
            "costo_dia_soles": round(costo_usd * TIPO_CAMBIO_SOLES, 2),
        },
    }
