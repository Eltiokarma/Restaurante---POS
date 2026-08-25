from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .db import Base, engine
from .routes import admin, cancellations, config, menu, orders


def _migrar(engine_) -> None:
    """Migraciones ligeras para bases creadas por versiones anteriores
    (create_all no agrega columnas a tablas existentes)."""
    with engine_.connect() as conn:
        columnas = [fila[1] for fila in conn.execute(text("PRAGMA table_info(ordenes)"))]
        if columnas and "impreso" not in columnas:
            # Las órdenes previas ya fueron atendidas: no deben reimprimirse
            conn.execute(text("ALTER TABLE ordenes ADD COLUMN impreso BOOLEAN NOT NULL DEFAULT 1"))
            conn.commit()

app = FastAPI(title="POS Auto-Atención", version="1.0.0")

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


@app.get("/api/health")
def health():
    return {"ok": True}
