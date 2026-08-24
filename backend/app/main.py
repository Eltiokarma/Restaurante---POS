from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routes import admin, cancellations, config, menu, orders

app = FastAPI(title="POS Auto-Atención", version="1.0.0")

# La terminal corre el frontend de Vite en otro puerto durante desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(cancellations.router)
app.include_router(config.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"ok": True}
