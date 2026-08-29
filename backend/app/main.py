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
from .routes import admin, caja, cancellations, config, insumos, menu, mesas, orders, stats, voice
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
        for col in ("ventas_efectivo", "ventas_tarjeta", "ventas_yape"):
            if columnas_cierres and col not in columnas_cierres:
                conn.execute(text(f"ALTER TABLE cierres_caja ADD COLUMN {col} FLOAT"))
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

# --- Candado del local (para despliegues en internet, ej. Railway) ---
# Si la variable de entorno PIN_LOCAL está definida, TODA la API (salvo
# /api/health y /api/admin/login) exige el header X-Pin-Local con ese
# valor. El frontend lo pide una sola vez por dispositivo. En la LAN del
# local (sin PIN_LOCAL) nada cambia.
RUTAS_SIN_PIN = ("/api/health", "/api/admin/login")


@app.middleware("http")
async def _candado_pin(request: Request, call_next):
    pin = os.getenv("PIN_LOCAL", "")
    if (
        pin
        and request.url.path.startswith("/api")
        and request.url.path not in RUTAS_SIN_PIN
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
app.include_router(voice.router)
app.include_router(insumos.router)
app.include_router(mesas.router)


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
