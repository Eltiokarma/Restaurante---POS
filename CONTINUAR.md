# CONTINUAR — Sesión 3: Tandas de cocina (el pre-orquestador)

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

## La sesión 3: TANDAS en /cocina

### Por qué (auditoría del bulk actual)

El "Por salir" de `Cocina.tsx` acumula por PLATO todo lo no-listo (total,
sin empezar, empaques) y una "tanda" implícita: las porciones de ese plato
pedidas dentro de `cocina_bulk_min` minutos desde la más antigua. El tachado
(`POST /api/orders/despachar-bulk`) va de la orden más antigua a la más
nueva. Sirve, pero **no separa estratégicamente**:

1. La tanda es por plato, no por servicio: no dice "estas 4 chuletas salen
   JUNTAS con estos 3 ajíes porque completan los tickets #12 y #15". Se
   tacha un plato y la mesa sale a medias.
2. "Todo junto" no está amarrado: se puede marcar listo el segundo de un
   ticket cuya entrada ni se empezó.
3. "Por tiempos" tampoco: la sopa del menú debería salir en la tanda de
   ahora y el segundo en la siguiente; hoy compiten en la misma tira.
4. Los platos al momento (`sale_al_momento`: frituras, chuleta) no se
   distinguen en la tira: son los que marcan cuánto demora una tanda.
5. No hay noción de capacidad ("entran 6 chuletas por sartén"): la cocinera
   parte mentalmente el 9× en 6+3.

### Qué construir (propuesta aceptada a validar con el dueño en campo)

**Tablero de TANDAS** arriba de la grilla de cocina: el sistema parte lo
pendiente en Tanda 1 / Tanda 2 / … con reglas deterministas. Es el
pre-orquestador: la futura IA solo reemplazará el cálculo, la pantalla y los
datos quedan.

- **Bloque 1 — backend `services/tandas.py` + `GET /api/orders/tandas`:**
  - Agrupar órdenes activas por ventana de llegada (`cocina_bulk_min`):
    la tanda arranca con la orden más antigua sin despachar y toma las que
    llegaron hasta X min después; la siguiente orden abre la Tanda 2.
  - **Tanda = órdenes completas**, no porciones sueltas: al terminarla se
    entregan mesas completas. Cada tanda lista sus tickets/mesas.
  - **Gating por tiempos**: en órdenes "separado", solo la entrada entra a
    la tanda; el segundo queda "esperando su entrada" y entra a la próxima
    tanda cuando la entrada esté lista. En "junto" todos los platos del
    ticket van a la misma tanda.
  - Dentro de la tanda, desglose por plato en dos estaciones:
    **🍳 al momento** (`sale_al_momento`) y **🥘 de olla** — lo frito manda
    la duración.
  - **Capacidad opcional por plato** (`platos.capacidad_tanda`, 0 = sin
    límite; editable en Admin → Menú): si la tanda pide 9 chuletas y entran
    6, se muestra "6 + 3 (2 sartenes)".
  - Snapshot para la IA futura: tabla `tanda_logs` (composición, hora de
    inicio, hora en que todo quedó listo) que se escribe al despachar.
- **Bloque 2 — frontend `/cocina`:**
  - Tarjetas de tanda: platos con cantidades por estación, tickets/mesas
    que completa, espera de la más antigua. Botones grandes
    "▶ Empezar tanda" (todo a preparando) y "✔ Salió la tanda" (todo a
    listo; las órdenes completadas se resaltan para entregar).
  - La tira "Por salir" actual se queda como ajuste fino (tachar porciones
    sueltas); las tarjetas de orden no cambian.
  - Toggle `cocina_tandas` en Admin → Configuración (default encendido);
    `cocina_bulk_min` sigue siendo la ventana.
- **Bloque 3 — pruebas y campo:** tests de la partición (ventana, gating
  junto/separado, capacidad), navegador real con un servicio simulado
  (6-8 tickets mezclados), ROADMAP, PR.

### Decisiones abiertas (preguntar al dueño antes del bloque 1)

1. ¿La ventana de tanda actual (minutos) le sirve o prefiere "tandas de N
   tickets" (p. ej. de 3 en 3)?
2. ¿Capacidad por plato sí o no en esta fase? (es un campo más que llenar)
3. ¿El gating de "todo junto" debe BLOQUEAR el tachado del segundo o solo
   avisar? (propuesta: solo avisar, cocina manda)

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
