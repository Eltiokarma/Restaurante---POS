"""Copia de seguridad manual de la base de datos.

Uso (desde backend/, con el entorno virtual activado):

    python backup.py

Crea/refresca backups/pos-AAAA-MM-DD.db. El servidor también respalda
solo cada 30 minutos mientras corre (ver app/services/backup.py); este
script sirve para forzar una copia al cierre o programarla aparte.
"""
from app.services.backup import crear_backup


def main() -> None:
    destino = crear_backup()
    if destino is None:
        print("No existe la base de datos; nada que respaldar.")
        return
    print(f"Backup creado: {destino} ({destino.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
