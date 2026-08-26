# Guía del proyecto — POS de Auto-Atención

POS de auto-atención táctil para un restaurante de menú peruano. El cliente arma su pedido en
una terminal (PC o tablet), confirma con ventana de cancelación, se imprime un ticket y la
orden va a la cola de cocina. El pago es en caja física. Ver `ROADMAP.md` para fases y
decisiones tomadas.

## Arquitectura

- **`backend/`** — FastAPI + SQLite (SQLAlchemy 2.x). Rutas en `app/routes/` (una por
  dominio: menu, orders, cancellations, config, admin), lógica de negocio en `app/services/`.
- **`frontend/`** — React + Vite + TypeScript. Páginas en `src/pages/` (Cliente, Cocina,
  Admin, Ticketera), componentes reutilizables en `src/components/`, hooks en `src/hooks/`,
  cliente HTTP único en `src/api.ts`.
- **Comunicación**: polling simple (menú 30s, cocina 10s, ticketera 3s). Sin WebSockets por
  decisión de fase 1; si el polling queda corto al escalar, migrar con cuidado.
- **Impresión**: HTML + `window.print()` con dos modos (config `modo_impresion`):
  `terminal` (imprime la pantalla del cliente) o `estacion` (cola servida por `/ticketera`
  en la PC con impresora). NO integrar drivers ESC/POS sin decidirlo en el roadmap.
- **Voz (fase 3)**: `backend/app/services/voice.py` es el stub. La voz debe ser SOLO otra
  manera de llenar el carrito; el flujo posterior (resumen, confirmación, ventana, ticket,
  cocina) es agnóstico al origen del pedido y no debe modificarse para soportarla.

## Invariantes del dominio (no romper)

- La orden NO se persiste hasta que termina la ventana de cancelación; el carrito vive solo
  en el estado del frontend.
- `numero_orden_dia` es correlativo POR DÍA (zona horaria `America/Lima`) y su asignación
  está serializada con un lock en `services/orders.py`.
- Los items de orden guardan snapshot de nombre y precio: el histórico nunca cambia aunque
  cambien los platos.
- Cancelaciones van a su propia tabla (log de análisis), nunca a `ordenes`.
- Cambios de esquema: agregar la migración ligera en `_migrar()` de `app/main.py`
  (`create_all` no altera tablas existentes).

## Convenciones

- Textos de UI y de commits en español peruano natural ("¿Sigues ahí?", "Paga en caja").
- Código (identificadores, comentarios) en español, consistente con lo existente.
- UX táctil primero: botones ≥80px de alto en vistas de cliente, sin dependencias de hover.
- Moneda: soles con 2 decimales; el backend es la autoridad de totales.
- Endpoints admin protegidos con `Depends(requiere_admin)` (token HMAC de 12h, header
  `X-Admin-Token`). Cliente, cocina y ticketera no llevan auth (app de LAN).

## Comandos

```bash
# Backend (desde backend/, con .venv activado)
pip install -r requirements-dev.txt
python seed.py                     # BD + menú de ejemplo
uvicorn app.main:app --port 8000   # desarrollo
python -m pytest tests/ -q         # tests (deben pasar antes de cada push)
python backup.py                   # copia de seguridad de la BD

# Frontend (desde frontend/)
npm run dev     # desarrollo con proxy a :8000
npm run build   # typecheck + build (CI lo exige verde)

# Producción en el local: un solo comando, todo en :8000
./scripts/iniciar.sh    # Windows: scripts\iniciar.bat
```

## Al terminar un cambio

1. `python -m pytest tests/ -q` en backend y `npm run build` en frontend deben pasar.
2. Si el cambio toca el flujo del cliente o la impresión, probarlo en navegador real, no
   solo con tests.
3. Actualizar `ROADMAP.md` si se tomó una decisión de arquitectura o se completó un ítem.
