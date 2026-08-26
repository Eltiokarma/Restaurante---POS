"""Copia de seguridad de la base de datos.

Uso (desde backend/, con el entorno virtual activado):

    python backup.py

Crea backups/pos-AAAA-MM-DD.db (una por día; si ya existe la de hoy, la
reemplaza con la versión más reciente). La BD guarda todas las ventas,
así que conviene correrlo al cierre de cada día — o programarlo en el
Programador de tareas de Windows / cron.
"""
import shutil
import sqlite3
from pathlib import Path

from app.db import DATABASE_PATH
from app.models import hoy_lima

BACKUPS_DIR = Path(__file__).resolve().parent / "backups"


def main() -> None:
    origen = Path(DATABASE_PATH)
    if not origen.exists():
        print(f"No existe la base de datos en {origen}; nada que respaldar.")
        return

    BACKUPS_DIR.mkdir(exist_ok=True)
    destino = BACKUPS_DIR / f"pos-{hoy_lima().isoformat()}.db"

    # sqlite3.backup copia de forma consistente aunque el servidor esté
    # corriendo (una copia de archivo a secas podría salir corrupta a
    # mitad de una escritura)
    with sqlite3.connect(origen) as con_origen, sqlite3.connect(destino) as con_destino:
        con_origen.backup(con_destino)

    tamano_kb = destino.stat().st_size / 1024
    print(f"Backup creado: {destino} ({tamano_kb:.0f} KB)")

    # Conserva los últimos 60 backups para no llenar el disco
    backups = sorted(BACKUPS_DIR.glob("pos-*.db"))
    for viejo in backups[:-60]:
        viejo.unlink()
        print(f"Backup antiguo eliminado: {viejo.name}")


if __name__ == "__main__":
    main()
