import asyncio
import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .db import BACKEND_DIR, Base, engine
from .routes import (
    admin, bebidas, caja, cancellations, config, impresion, insumos,
    mantenimiento, menu, mesas, orders, stats, voice,
)
from .services.backup import ciclo_backup_automatico


def _migrar(engine_) -> None:
    """Migraciones ligeras para bases creadas por versiones anteriores
    (create_all no agrega columnas a tablas existentes)."""
    with engine_.connect() as conn:
        columnas = [fila[1] for fila in conn.execute(text("PRAGMA table_info(ordenes)"))]
        if columnas and "impreso" not in columnas:
            # Las órdenes previas ya fueron atendidas: no deben reimprimirse
            conn.execute(text("ALTER TABLE ordenes ADD COLUMN impreso BOOLEAN NOT NULL DEFAULT 1"))
            conn.commit()
        if columnas and "duracion_seg" not in columnas:
            conn.execute(text("ALTER TABLE ordenes ADD COLUMN duracion_seg INTEGER"))
            conn.commit()
        if columnas and "tipo_servicio" not in columnas:
            conn.execute(text(
                "ALTER TABLE ordenes ADD COLUMN tipo_servicio TEXT NOT NULL DEFAULT 'sala'"
            ))
            conn.commit()
        if columnas and "origen" not in columnas:
            conn.execute(text(
                "ALTER TABLE ordenes ADD COLUMN origen TEXT NOT NULL DEFAULT 'tactil'"
            ))
            conn.commit()
        columnas_platos = [fila[1] for fila in conn.execute(text("PRAGMA table_info(platos)"))]
        if columnas_platos and "sinonimos" not in columnas_platos:
            conn.execute(text("ALTER TABLE platos ADD COLUMN sinonimos TEXT NOT NULL DEFAULT '[]'"))
            conn.commit()
        columnas_items = [fila[1] for fila in conn.execute(text("PRAGMA table_info(orden_items)"))]
        if columnas_items and "empaque" not in columnas_items:
            conn.execute(text(
                "ALTER TABLE orden_items ADD COLUMN empaque TEXT NOT NULL DEFAULT 'mesa'"
            ))
            conn.commit()
        if columnas and "metodo_pago" not in columnas:
            conn.execute(text("ALTER TABLE ordenes ADD COLUMN metodo_pago TEXT"))
            conn.commit()
        columnas_cierres = [fila[1] for fila in conn.execute(text("PRAGMA table_info(cierres_caja)"))]
        for col in (
            "ventas_efectivo", "ventas_tarjeta", "ventas_yape", "egresos",
            "por_cobrar", "vueltos_pendientes",
        ):
            if columnas_cierres and col not in columnas_cierres:
                conn.execute(text(f"ALTER TABLE cierres_caja ADD COLUMN {col} FLOAT"))
                conn.commit()
        # "Falta pagar" / "falta vuelto" por ticket (descuadraban la caja)
        if columnas and "pago_pendiente" not in columnas:
            conn.execute(text(
                "ALTER TABLE ordenes ADD COLUMN pago_pendiente BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.execute(text("ALTER TABLE ordenes ADD COLUMN vuelto_pendiente FLOAT"))
            conn.commit()
        columnas_movs = [fila[1] for fila in conn.execute(text("PRAGMA table_info(movimientos_insumo)"))]
        if columnas_movs and "orden_id" not in columnas_movs:
            conn.execute(text("ALTER TABLE movimientos_insumo ADD COLUMN orden_id INTEGER"))
            conn.commit()
        if columnas and "mesa_ids" not in columnas:
            conn.execute(text("ALTER TABLE ordenes ADD COLUMN mesa_ids TEXT NOT NULL DEFAULT '[]'"))
            conn.commit()
        if columnas and "mesa_liberada" not in columnas:
            conn.execute(text(
                "ALTER TABLE ordenes ADD COLUMN mesa_liberada BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.commit()
        if columnas_items and "nota" not in columnas_items:
            conn.execute(text("ALTER TABLE orden_items ADD COLUMN nota TEXT NOT NULL DEFAULT ''"))
            conn.commit()
        if columnas_platos and "sale_al_momento" not in columnas_platos:
            conn.execute(text(
                "ALTER TABLE platos ADD COLUMN sale_al_momento BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.commit()
        if columnas and "entrega" not in columnas:
            conn.execute(text(
                "ALTER TABLE ordenes ADD COLUMN entrega TEXT NOT NULL DEFAULT 'junto'"
            ))
            conn.commit()
        # Menú encadenado (§1): las tablas nuevas las crea create_all; aquí
        # solo las columnas de orden_items. NULL = a la carta, que es
        # exactamente lo que eran las órdenes históricas.
        if columnas_items and "orden_menu_id" not in columnas_items:
            conn.execute(text("ALTER TABLE orden_items ADD COLUMN orden_menu_id INTEGER"))
            conn.execute(text("ALTER TABLE orden_items ADD COLUMN tiempo_orden INTEGER"))
            conn.execute(text(
                "ALTER TABLE orden_items ADD COLUMN es_extra BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.commit()
        # §4: cintillo de anulada en cocina y fotos de plato
        if columnas and "anulada_en" not in columnas:
            conn.execute(text("ALTER TABLE ordenes ADD COLUMN anulada_en DATETIME"))
            conn.commit()
        if columnas_platos and "foto" not in columnas_platos:
            conn.execute(text("ALTER TABLE platos ADD COLUMN foto VARCHAR(80)"))
            conn.commit()
        # Aviso de stock que se acaba: 0 = sin alerta (comportamiento previo)
        columnas_insumos = [fila[1] for fila in conn.execute(text("PRAGMA table_info(insumos)"))]
        if columnas_insumos and "stock_minimo" not in columnas_insumos:
            conn.execute(text(
                "ALTER TABLE insumos ADD COLUMN stock_minimo FLOAT NOT NULL DEFAULT 0"
            ))
            conn.commit()
        # Estado por ítem (§3): los ítems históricos heredan el estado de su
        # orden (una anulada no es estado de cocina: sus ítems quedan
        # 'pendiente', igual da porque cocina no la muestra)
        if columnas_items and "estado" not in columnas_items:
            conn.execute(text(
                "ALTER TABLE orden_items ADD COLUMN estado VARCHAR(20) NOT NULL DEFAULT 'pendiente'"
            ))
            conn.execute(text(
                "UPDATE orden_items SET estado = ("
                "  SELECT CASE WHEN o.estado IN ('pendiente','preparando','listo','entregado')"
                "  THEN o.estado ELSE 'pendiente' END FROM ordenes o WHERE o.id = orden_id)"
            ))
            conn.commit()

        # Menú editable: quitar tiempos con descuento y agregados (+presa…)
        columnas_tiempos = [fila[1] for fila in conn.execute(text("PRAGMA table_info(menu_tiempos)"))]
        if columnas_tiempos and "descuento_si_se_quita" not in columnas_tiempos:
            conn.execute(text(
                "ALTER TABLE menu_tiempos ADD COLUMN descuento_si_se_quita FLOAT NOT NULL DEFAULT 0"
            ))
            conn.commit()
        columnas_menus = [fila[1] for fila in conn.execute(text("PRAGMA table_info(orden_menus)"))]
        if columnas_menus and "omitidos_json" not in columnas_menus:
            conn.execute(text(
                "ALTER TABLE orden_menus ADD COLUMN omitidos_json TEXT NOT NULL DEFAULT '[]'"
            ))
            conn.commit()
        if columnas_items and "es_agregado" not in columnas_items:
            conn.execute(text(
                "ALTER TABLE orden_items ADD COLUMN es_agregado BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.commit()
        # Cargo por táper ("táper cuesta un sol más")
        if columnas_items and "es_cargo" not in columnas_items:
            conn.execute(text(
                "ALTER TABLE orden_items ADD COLUMN es_cargo BOOLEAN NOT NULL DEFAULT 0"
            ))
            conn.commit()

        # Varias cajas por día (turnos): la tabla nació con fecha UNIQUE y
        # SQLite no permite soltar esa restricción con ALTER, así que se
        # reconstruye una sola vez copiando los registros tal cual.
        ddl_cierres = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='cierres_caja'"
        )).scalar()
        if ddl_cierres and "UNIQUE" in ddl_cierres.upper():
            conn.execute(text("ALTER TABLE cierres_caja RENAME TO cierres_caja_unica"))
            Base.metadata.tables["cierres_caja"].create(bind=conn)
            cols = ", ".join(
                fila[1]
                for fila in conn.execute(text("PRAGMA table_info(cierres_caja_unica)"))
            )
            conn.execute(text(
                f"INSERT INTO cierres_caja ({cols}) SELECT {cols} FROM cierres_caja_unica"
            ))
            conn.execute(text("DROP TABLE cierres_caja_unica"))
            conn.commit()


def _sembrar_agregados(engine_) -> None:
    """Los agregados de arranque (+presa, +refresco…) se crean UNA vez.

    Solo si la tabla está vacía: si el dueño los editó o borró, se respeta.
    Se distingue "nunca hubo" de "los borró" con la marca en config."""
    from sqlalchemy import select

    from .db import SessionLocal
    from .models import AGREGADOS_INICIALES, Config, MenuAgregado

    db = SessionLocal()
    try:
        if db.get(Config, "agregados_sembrados") is not None:
            return
        if not db.scalars(select(MenuAgregado)).first():
            for numero, (nombre, precio) in enumerate(AGREGADOS_INICIALES, start=1):
                db.add(MenuAgregado(nombre=nombre, precio=precio, orden=numero))
        db.add(Config(clave="agregados_sembrados", valor="1"))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def _ciclo_de_vida(app_: FastAPI):
    # Backup automático mientras el servidor corre (ver services/backup.py).
    # El retraso inicial de 60s hace que no interfiera con tests ni arranques.
    tarea_backup = asyncio.create_task(ciclo_backup_automatico())
    _avisar_si_voz_mal_configurada()
    yield
    tarea_backup.cancel()


def _avisar_si_voz_mal_configurada() -> None:
    """Voz encendida sin API keys: warning al arrancar y el botón no aparece
    en la terminal (voz_disponible=False); la app no se rompe."""
    import logging

    from .db import SessionLocal
    from .routes.config import leer_config
    from .services.voice import claves_configuradas

    db = SessionLocal()
    try:
        cfg = leer_config(db)
        if cfg["voz_habilitada"] and not claves_configuradas():
            logging.getLogger("uvicorn.error").warning(
                "voz_habilitada está encendida pero faltan OPENAI_API_KEY / "
                "ANTHROPIC_API_KEY en el .env: el botón de voz no aparecerá."
            )
    finally:
        db.close()


app = FastAPI(title="POS Auto-Atención", version="1.0.0", lifespan=_ciclo_de_vida)

# La terminal corre el frontend de Vite en otro puerto durante desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
_migrar(engine)
_sembrar_agregados(engine)

# --- Candado del local (para despliegues en internet, ej. Railway) ---
# Si la variable de entorno PIN_LOCAL está definida, TODA la API (salvo
# /api/health y /api/admin/login) exige el header X-Pin-Local con ese
# valor. El frontend lo pide una sola vez por dispositivo. En la LAN del
# local (sin PIN_LOCAL) nada cambia.
RUTAS_SIN_PIN = ("/api/health", "/api/admin/login")
# Las fotos de plato se cargan con <img>, que no puede mandar el header
# del PIN. Una foto del menú no es información sensible.
PREFIJOS_SIN_PIN = ("/api/menu/fotos/",)


@app.middleware("http")
async def _candado_pin(request: Request, call_next):
    pin = os.getenv("PIN_LOCAL", "")
    if (
        pin
        and request.url.path.startswith("/api")
        and request.url.path not in RUTAS_SIN_PIN
        and not request.url.path.startswith(PREFIJOS_SIN_PIN)
        and request.method != "OPTIONS"
        and not hmac.compare_digest(request.headers.get("X-Pin-Local", ""), pin)
    ):
        return JSONResponse(status_code=401, content={"detail": "PIN requerido"})
    return await call_next(request)

app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(cancellations.router)
app.include_router(config.router)
app.include_router(admin.router)
app.include_router(stats.router)
app.include_router(caja.router)
app.include_router(bebidas.router)
app.include_router(voice.router)
app.include_router(insumos.router)
app.include_router(mesas.router)
app.include_router(impresion.router)
app.include_router(mantenimiento.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# --- Modo producción: servir el frontend compilado desde este mismo puerto ---
# Si existe frontend/dist (npm run build), el sistema completo corre solo con
# uvicorn en el puerto 8000: /, /cocina, /admin y /ticketera salen de aquí.
# En desarrollo (sin dist o usando Vite en 5173) nada de esto interfiere:
# las rutas /api se registran antes y siempre tienen prioridad.
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        # Archivos sueltos del build (favicon, etc.); todo lo demás es una
        # ruta del SPA y devuelve index.html (React Router resuelve).
        # resolve() + is_relative_to impiden escapar de dist/ con "..".
        archivo = (FRONTEND_DIST / ruta).resolve()
        if ruta and archivo.is_file() and archivo.is_relative_to(FRONTEND_DIST.resolve()):
            return FileResponse(archivo)
        return FileResponse(FRONTEND_DIST / "index.html")
