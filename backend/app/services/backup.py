"""Copias de seguridad de la base de datos.

Usado por dos vías:
- `python backup.py` (manual o tarea programada del sistema).
- La tarea de fondo del servidor, que refresca la copia del día cada
  30 minutos mientras el sistema corre (`ciclo_backup_automatico`).

Una copia por día (backups/pos-AAAA-MM-DD.db), refrescada in situ; se
conservan las últimas RETENER copias.
"""
import asyncio
import logging
import sqlite3
from pathlib import Path

from ..db import BACKEND_DIR, DATABASE_PATH
from ..models import hoy_lima

logger = logging.getLogger("uvicorn.error")

BACKUPS_DIR = BACKEND_DIR / "backups"
RETENER = 60
INTERVALO_SEG = 30 * 60
RETRASO_INICIAL_SEG = 60


def crear_backup(directorio: Path | None = None) -> Path | None:
    """Crea (o refresca) la copia de hoy. Devuelve la ruta, o None si no
    hay base de datos que respaldar."""
    origen = Path(DATABASE_PATH)
    if not origen.exists():
        return None

    directorio = directorio or BACKUPS_DIR
    directorio.mkdir(exist_ok=True)
    destino = directorio / f"pos-{hoy_lima().isoformat()}.db"

    # sqlite3.backup copia de forma consistente aunque el servidor esté
    # escribiendo (una copia de archivo a secas podría salir corrupta)
    with sqlite3.connect(origen) as con_origen, sqlite3.connect(destino) as con_destino:
        con_origen.backup(con_destino)

    for viejo in sorted(directorio.glob("pos-*.db"))[:-RETENER]:
        viejo.unlink()

    return destino


async def ciclo_backup_automatico() -> None:
    """Tarea de fondo: refresca la copia del día cada 30 minutos, así lo
    máximo que se puede perder ante una falla del disco es media hora.
    El primer respaldo espera un minuto para no estorbar el arranque."""
    await asyncio.sleep(RETRASO_INICIAL_SEG)
    while True:
        try:
            destino = await asyncio.to_thread(crear_backup)
            if destino is not None:
                logger.info("Backup automático: %s", destino.name)
        except Exception:
            logger.exception("Falló el backup automático; se reintenta en el próximo ciclo")
        await asyncio.sleep(INTERVALO_SEG)
