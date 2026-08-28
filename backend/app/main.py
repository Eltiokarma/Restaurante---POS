import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .db import BACKEND_DIR, Base, engine
from .routes import admin, cancellations, config, menu, orders, stats
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

@asynccontextmanager
async def _ciclo_de_vida(app_: FastAPI):
    # Backup automático mientras el servidor corre (ver services/backup.py).
    # El retraso inicial de 60s hace que no interfiera con tests ni arranques.
    tarea_backup = asyncio.create_task(ciclo_backup_automatico())
    yield
    tarea_backup.cancel()


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

app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(cancellations.router)
app.include_router(config.router)
app.include_router(admin.router)
app.include_router(stats.router)


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
