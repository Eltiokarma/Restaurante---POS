"""Copias de seguridad de la base de datos."""
import sqlite3

from app.services.backup import crear_backup


def test_crear_backup_copia_consistente(client, menu_ejemplo, tmp_path):
    # Con datos reales en la BD del entorno de tests
    client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
    })

    destino = crear_backup(directorio=tmp_path)
    assert destino is not None and destino.exists()
    assert destino.name.startswith("pos-")

    # La copia es una BD SQLite válida con la orden dentro
    con = sqlite3.connect(destino)
    assert con.execute("SELECT COUNT(*) FROM ordenes").fetchone()[0] == 1
    con.close()


def test_backup_se_refresca_en_el_mismo_dia(client, menu_ejemplo, tmp_path):
    crear_backup(directorio=tmp_path)
    client.post("/api/orders", json={
        "items": [{"plato_id": menu_ejemplo["Lomo saltado"], "cantidad": 1}],
    })
    crear_backup(directorio=tmp_path)

    copias = list(tmp_path.glob("pos-*.db"))
    assert len(copias) == 1  # una por día, refrescada
    con = sqlite3.connect(copias[0])
    assert con.execute("SELECT COUNT(*) FROM ordenes").fetchone()[0] == 1
    con.close()
