"""Crea la BD, la configuración inicial y un menú de ejemplo.

Uso (desde la carpeta backend/, con el entorno virtual activado):

    python seed.py
"""
from app.db import Base, SessionLocal, engine
from app.models import CONFIG_DEFAULTS, Config, Mesa, Plato, hoy_lima

MENU_EJEMPLO = [
    # (nombre, categoria, precio S/)
    ("Sopa criolla", "entrada", 6.00),
    ("Lomo saltado", "fondo", 15.00),
    ("Ají de gallina", "fondo", 13.00),
    ("Seco de res", "fondo", 14.00),
    ("Chicha morada", "bebida", 3.50),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for clave, valor in CONFIG_DEFAULTS.items():
            if db.get(Config, clave) is None:
                db.add(Config(clave=clave, valor=valor))

        if db.query(Plato).count() == 0:
            hoy = hoy_lima()
            for nombre, categoria, precio in MENU_EJEMPLO:
                db.add(
                    Plato(
                        nombre=nombre,
                        categoria=categoria,
                        precio=precio,
                        activo_hoy=True,
                        en_catalogo=True,
                        ultima_vez_activo=hoy,
                    )
                )
            print(f"Menú de ejemplo cargado ({len(MENU_EJEMPLO)} platos).")
        else:
            print("Ya existen platos; no se cargó el menú de ejemplo.")

        if db.query(Mesa).count() == 0:
            for n in range(1, 5):
                db.add(Mesa(nombre=f"Mesa {n}"))
            print("4 mesas de ejemplo creadas (renómbralas en Admin → Configuración).")

        db.commit()
        print("Base de datos lista.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
