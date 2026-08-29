"""Crea la BD, la configuración inicial y un menú de ejemplo.

Uso (desde la carpeta backend/, con el entorno virtual activado):

    python seed.py
"""
from app.db import Base, SessionLocal, engine
from app.models import (
    CONFIG_DEFAULTS,
    Config,
    Mesa,
    MenuAlternativa,
    MenuPlantilla,
    MenuTiempo,
    Plato,
    hoy_lima,
)

MENU_EJEMPLO = [
    # (nombre, categoria, precio S/)
    ("Sopa criolla", "entrada", 6.00),
    ("Papa a la huancaína", "entrada", 6.00),
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

        # Menú encadenado de ejemplo: entrada o sopa → segundo → refresco.
        # El precio vive en el MENÚ; "una entrada más" sale a S/ 3.00.
        db.flush()  # la sesión no auto-flushea: los platos recién agregados deben verse
        if db.query(MenuPlantilla).count() == 0 and db.query(Plato).count() > 0:
            por_nombre = {p.nombre: p for p in db.query(Plato).all()}
            entradas = [p for n, p in por_nombre.items() if p.categoria == "entrada"]
            segundos = [p for n, p in por_nombre.items() if p.categoria == "fondo"]
            bebidas = [p for n, p in por_nombre.items() if p.categoria == "bebida"]
            if entradas and segundos:
                plantilla = MenuPlantilla(nombre="Menú del día", precio=11.00,
                                          activo_hoy=True, en_catalogo=True)
                t1 = MenuTiempo(orden=1, rotulo="Entrada o sopa", obligatorio=True,
                                precio_extra=3.00)
                t1.alternativas = [MenuAlternativa(plato_id=p.id) for p in entradas]
                t2 = MenuTiempo(orden=2, rotulo="Segundo", obligatorio=True)
                t2.alternativas = [MenuAlternativa(plato_id=p.id) for p in segundos]
                plantilla.tiempos = [t1, t2]
                if bebidas:
                    t3 = MenuTiempo(orden=3, rotulo="Refresco", obligatorio=True)
                    t3.alternativas = [MenuAlternativa(plato_id=bebidas[0].id)]
                    plantilla.tiempos.append(t3)
                db.add(plantilla)
                print("Menú encadenado de ejemplo creado (Menú del día S/ 11.00).")

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
