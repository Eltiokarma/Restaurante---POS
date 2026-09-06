# CONTINUAR — Sesión 4: validar las tandas en campo y pensar el orquestador

> Plan de la sesión en curso. Empezar por el bloque 1 sin pedir contexto.
> El prototipo está VIVO en el local (Railway despliega `main`, ~2-3 min).
> Flujo por cambio: implementar → `python -m pytest tests/ -q` (backend/.venv)
> → `npm run build` → navegador real → commit en español → PR a main →
> merge → realinear la rama de sesión con `origin/main`.

## Dónde quedó todo (sesión 2, cerrada 2026-09-06)

Entregado y en producción: varias cajas por día (turnos) con doble check,
resumen de cierre en pantalla + impreso, egresos del turno, **falta pagar /
falta vuelto por ticket** (afectan el esperado del cierre), comanda impresa
por grupos (ENTRADAS/SEGUNDOS con observaciones al costado), mesa desde el
pedido + SIN MESA + reimpresión al asignar, menús guardados por día,
contador de menús, caja con la tarjeta "+ UN MENÚ" de la terminal (sin
platos sueltos), auditoría visual de Claude Design aplicada (tablero de
caja, contraste AA, piso táctil 48/56px, iconos SVG, menú "⋯" en filas de
caja y tabs del admin).

Pendiente diferido (decisión del dueño, no arrancar solos): app propia
Android para imprimir (RawBT pide un toque por ticket mientras tanto),
migrar todos los botones viejos a la clase base `.boton`, voz (fase 3).

## TANDAS: ENTREGADO (sesión 3, 2026-09-06)

Las 3 decisiones del dueño quedaron aplicadas: la tanda cierra con LO QUE
SE LLENE PRIMERO (ventana `cocina_bulk_min` o tope `cocina_tanda_max_tickets`,
default 4, 0 = sin tope); capacidad opcional por plato
(`platos.capacidad_tanda`, editable en el "⋯" del plato: 9 chuletas con
capacidad 6 → "6 + 3 · 2 sartenes"); el gating de "por tiempos" SOLO AVISA
("el segundo del #003 espera su entrada"), nunca bloquea.

Qué quedó construido:

- `services/tandas.py` + `GET /api/orders/tandas`: partición determinista
  de órdenes COMPLETAS (al salir la tanda salen mesas completas), gating
  del segundo en "separado" hasta que su entrada esté lista, estaciones
  🍳 al momento (primero: lo frito manda) / 🥘 de olla.
- `POST /api/orders/tandas/empezar` (todo a preparando, abre `tanda_logs`)
  y `/salio` (todo a listo, cierra el log). `tanda_logs` guarda
  composición + hora de inicio + hora en que salió: es el dato de
  entrenamiento del futuro orquestador IA.
- `/cocina`: tablero de tarjetas arriba de la grilla (tickets/mesas,
  espera, platos por estación, partición por capacidad, "⏳ espera su
  entrada", botones ▶ EMPEZAR / ✔ SALIÓ de 64px). La tira "Por salir"
  sigue para el ajuste fino por porciones.
- Admin → Configuración: toggle `cocina_tandas` (default ON) + tope de
  tickets. Tests de partición/gating/capacidad/logs (suite completa en
  verde).

## La sesión 4 (propuesta)

1. **Validar las tandas en servicio real**: mirar 2-3 días de
   `tanda_logs` (composición vs. cuánto tardó cada tanda) y ajustar con
   el dueño ventana/tope/capacidades reales de su cocina.
2. **Orquestador IA (fase siguiente, NO arrancar solos)**: reemplazar el
   cálculo determinista por una sugerencia inteligente usando los
   `tanda_logs` acumulados; la pantalla y los endpoints ya están.

## Ya entregado en la sesión 2 (cerrado, decisiones del dueño aplicadas)

- **Gaseosas en el pedido** (HECHO): lista fija con marca/tamaño/precio en
  Admin → Menú del día → "🥤 Bebidas de caja"; la caja las agrega a una
  orden YA creada con el botón "🥤 Gaseosa"; descuentan botellas del kardex
  (insumo en "unidad" auto-creado); imprime SOLO un ticket chico de
  gaseosas, sin reimprimir la comanda (tipo "bebida" en la cola).
- **Trasladar pedidos de mesa** (HECHO): botón "⇄ Trasladar mesa" en caja
  mueve TODOS los pedidos de hoy de una mesa a otra; reimpresión de
  comandas opcional (checkbox, modos puente/estación).

## Datos operativos

- Producción: `https://restaurante-pos-production-dc39.up.railway.app`
  (menú real cargado; el dueño debía rotar `ADMIN_PASSWORD` en Railway).
- Rama de trabajo: `claude/pos-restaurante-sesion-2-oybq0g` (alineada a
  `origin/main`); crear PR por bloque y mergear al toque.
- Playwright: `executable_path="/opt/pw-browsers/chromium"`,
  `args=["--no-sandbox"]`; el server de prueba con `DATABASE_PATH` en el
  scratchpad + `seed.py`; `pkill` sale con 144 (correrlo solo).
