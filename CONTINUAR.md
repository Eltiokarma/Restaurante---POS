# Continuar inmediatamente — sesión 3

> Este archivo es el punto de arranque de la próxima conversación. Léelo junto con
> `CLAUDE.md` y `ROADMAP.md` y empieza de frente por el bloque 1, sin pedir contexto.
> Cuando un bloque quede mergeado, márcalo aquí; cuando los tres estén hechos, borra
> este archivo y deja el registro en `ROADMAP.md`.

## Cómo trabajamos (igual que las sesiones 1 y 2)

- Dueño no técnico: explicar claro y sin jerga, en español peruano. Él prueba en el local
  con tablets y reporta; nosotros implementamos, probamos y mergeamos.
- Por cada bloque: implementar → `python -m pytest tests/ -q` (backend) → `npm run build`
  (frontend) → verificación en navegador real con Playwright (`/opt/pw-browsers/chromium`,
  `--no-sandbox`) → commit en español → push a la rama de trabajo → PR contra `main` →
  merge → `git fetch origin main && git checkout -B <rama> origin/main`.
- Rama de trabajo: la que indique el sistema al iniciar la sesión (en la sesión 2 fue
  `claude/pos-restaurante-sesion-2-oybq0g`). Railway despliega `main`.
- Antes de cerrar cada bloque, pasar `/code-review` sobre el diff y corregir hallazgos:
  en la sesión 2 esto encontró bugs de plata reales (PR #29).
- Detalles útiles: `pkill` devuelve 144 y corta cadenas de comandos (correrlo solo);
  usar rutas absolutas; `SessionLocal` tiene `autoflush=False` (hacer `db.flush()` antes
  de leer ids recién creados).

## Estado al cerrar la sesión 2 (todo en `main`, PRs #20–#29)

Menú encadenado (§1), cocina por bulks (§3), menores (§4), impresión ESC/POS con modo
puente y ticketera RawBT, "Empezar limpio", aviso de tickets sin imprimir (cerrable),
stock mínimo, sugerencia automática de menú en el resumen del cliente + asistente de
armado en Admin, kardex intuitivo con 62 insumos y 47 recetas base editables. 171 tests
en verde. Pendiente de prueba en sala: la vuelta de kardex y la sugerencia de menú.

## Bloque 1 — Reporte de consumo semanal del kardex (+ CSV) — HECHO

> Mergeado en la sesión 2. Quedó en Admin → Insumos → Consumo, con endpoints
> `GET /api/insumos/consumo` y `/consumo.csv` y el servicio `services/consumo.py`.
> Detalle abajo, por si hace falta el contexto.

Lo que falta del kardex según `ROADMAP.md` ("Kardex fase 2").

Backend (`backend/app/routes/insumos.py`, servicios en `services/` si crece):
- `GET /api/insumos/consumo?desde=&hasta=` (default: últimos 7 días, zona `America/Lima`
  con `hoy_lima()`). Agrega `movimientos_insumo` por insumo y por tipo:
  consumido (ventas), comprado (cantidad y S/), mermas, ajustes, stock al cierre,
  costo del consumo (cantidad × costo promedio del insumo) y "días de stock"
  (stock actual ÷ consumo diario promedio; null si no hubo consumo). Incluir además
  `por_dia` (consumo total en S/ por día) para la gráfica y `top` (5 insumos por S/
  consumidos). Reutilizar `_despensa_por_nombre` / FACTOR_UNIDAD solo si hace falta;
  las cantidades ya están en la unidad real del insumo.
- `GET /api/insumos/consumo.csv` con el mismo rango (mismo estilo que
  `routes/stats.py` → `ventas.csv`: `StreamingResponse`, UTF-8 con BOM, separador `;`
  para que Excel en español lo abra directo). Cabeceras en español.
- Ambos protegidos con `Depends(requiere_admin)` como el resto del kardex.
- Tests nuevos en `backend/tests/test_kardex_consumo.py`: compra + venta con receta +
  merma → cifras exactas; rango sin movimientos → ceros; CSV con BOM y columnas.

Frontend (`frontend/src/pages/Admin.tsx`, pestaña Insumos → subpestaña nueva
"Consumo" al lado de Despensa / Recetas / Historial):
- Selector Esta semana / Semana pasada / Últimos 30 días / rango a mano.
- Tarjetas grandes: "Gastaste en insumos S/ X", "Se perdió S/ Y (mermas)", "Insumos
  por agotarse: N" (usar `por_agotarse` ya existente).
- Tabla por insumo ordenada por S/ consumidos: consumido, comprado, merma, stock,
  días de stock (rojo si < 2). Lenguaje claro ("Se usó", "Compraste", "Se perdió").
- Botón "Descargar Excel (CSV)" → `api.consumoKardexCsv(desde, hasta)`.
- Tipos y métodos nuevos en `src/api.ts` (`ConsumoInsumo`, `ResumenConsumo`,
  `api.consumoKardex`, `api.consumoKardexCsv`).

## Bloque 2 — Pedido "desde el menú" — HECHO

> Mergeado en la sesión 2 (con las respuestas del dueño: quitar SÍ descuenta —
> configurable por tiempo—, agregados a S/ 4 / 1.50 / 1.50 / 2 / 2, y cocina ve
> SIN SOPA / +1 PRESA destacados). Queda solo el bloque 3. Detalle abajo.

## (referencia) Bloque 2 — Pedido "desde el menú": empezar por "Un menú" y editar cada uno

Pedido del dueño (textual): *"algo más lógico para el comensal es empezar desde pedir
'Un menú', todo el combo completo y después restarle sopa o añadirle más refresco, más
presas, más arroz, más ensalada, más guarnición, o menos. Poder editar cada 'Menú', si se
han pedido varios, que se vean todos en una lista desplegable, editable ahí para que el
cliente pueda ver sus 5 menús en lista, cada uno con lo quitado o agregado, con sus
costos, con su total."*

Diseño acordado a proponer al dueño al inicio (confirmar los dos puntos abiertos antes
de tocar el backend):

1. **Primera pantalla del pedido = el menú del día completo.** Botón gigante "Un menú —
   S/ 11" (uno por plantilla activa) que agrega UNA línea de menú ya armada con la
   opción por defecto de cada tiempo (la primera alternativa disponible, o la única).
   Debajo, la carta suelta como hoy. La sugerencia automática (`SugerenciaMenu`) sigue
   para quien arma a la carta.
2. **Cada menú del carrito es una tarjeta editable** (lista desplegable: "Menú 1 de 5 ·
   S/ 12.50 ▾"). Dentro: por cada tiempo, la elección actual con botón "Cambiar"
   (abre las alternativas) y un toggle **"Sin sopa"** (quitar el tiempo); una sección
   **"Agregar"** con chips **+ refresco, + presa, + arroz, + ensalada, + guarnición**
   con su precio; empaque y nota como hoy. Resumen por tarjeta: "Quitaste: sopa ·
   Agregaste: 1 presa (S/ 4), 1 refresco (S/ 1.50) · Total S/ 16.50". Al pie, total
   del pedido.
3. **Quitar un tiempo no descuenta** salvo que el admin configure un descuento por
   tiempo (`MenuTiempo.descuento_si_se_quita`, default 0). PUNTO ABIERTO 1: preguntar
   al dueño si "sin sopa" baja el precio y cuánto.
4. **Agregados** son porciones de componente, no platos de carta: nueva tabla
   `menu_agregados` (id, plantilla_id nullable = aplica a todas, nombre, precio,
   activo, orden) editable en Admin → Menú del día (editor de plantillas) con chips
   sugeridos: refresco, presa, arroz, ensalada, guarnición, sopa. PUNTO ABIERTO 2:
   precios iniciales (proponer S/ 1.50 refresco, S/ 4 presa, S/ 1.50 arroz, S/ 2
   ensalada, S/ 2 guarnición) y si cocina los ve como línea aparte ("+1 PRESA").
5. **Backend**: `OrdenMenu` gana `omitidos` (lista de `tiempo_orden`) y los agregados
   entran como `OrdenItem`s ligados al menú con `es_agregado=True`, snapshot de nombre
   y precio (invariante: el histórico no cambia). `crear_orden` valida: no se puede
   omitir un tiempo y a la vez elegirlo; los agregados deben existir y estar activos;
   total = precio menú + recargos + extras + agregados − descuentos. Ticket, cocina y
   caja muestran "SIN SOPA" en mayúsculas destacado y "+1 PRESA" como línea; CSV suma
   columna `agregados`. Migración ligera en `_migrar()`.
6. **Frontend**: `useCarrito` con `omitirTiempo(idx, orden, boolean)`,
   `cambiarEleccion(idx, orden, plato_id)`, `cambiarAgregado(idx, agregado_id, delta)`;
   `subtotalMenu` en `src/api.ts` incorpora agregados y descuentos (una sola función,
   la usan cliente, caja y ticket). Componente nuevo `TarjetaMenuCarrito.tsx`
   (acordeón, botones ≥ 80 px, sin hover). `ArmadoMenu` se mantiene para "armar desde
   cero" y para "Cambiar".
7. Tests: `test_menu_editable.py` (omitidos, agregados, descuento, validaciones 422,
   ticket ESC/POS con "SIN SOPA"). Verificación en navegador: pedir 5 menús, editar el
   3.º, ver la lista con costos y total, confirmar, ticket y cocina correctos.

## Bloque 3 — Que encaje en cualquier tamaño de tablet

Auditoría de responsive de las cinco vistas, con foco en la del cliente (se probó en
tablets 8" y 10", vertical y horizontal). Hoy `styles.css` solo tiene un breakpoint
(`max-width: 900px` para la caja) y las grillas usan `minmax(340px, 1fr)`, que en un
7"–8" vertical deja una sola columna con tarjetas enormes.

- Probar con Playwright en estos viewports (vertical y horizontal): 600×960 (7"),
  800×1280 (8"), 1200×1920 (10"), 1024×768 (iPad viejo), 1366×768 (laptop). Guardar
  capturas en el scratchpad y revisarlas una por una.
- Reglas: unidades relativas (`clamp()` para tipografía y botones), grillas
  `auto-fill` con mínimos de 150–180 px para platos, barra del carrito fija abajo que
  nunca tape el último plato (padding inferior = alto de la barra), modales que caben
  en 600 px de alto sin scroll externo (scroll interno), botones ≥ 80 px de alto en
  cliente y ≥ 56 px en admin/caja, nada de scroll horizontal, `100dvh` en vez de
  `100vh` (barra del navegador Android).
- Cocina: en horizontal 10" deben verse ≥ 4 tarjetas; en vertical, la tira "Por salir"
  pasa a dos filas. Caja: columnas a una en < 900 px ya está; revisar el modal de cobro.
- Admin: tablas con `overflow-x: auto` en su contenedor y subpestañas que no se rompan
  en 600 px.
- Dejar en `ROADMAP.md` la nota de que estas reglas son las que hereda la app: "al
  final se sabe que se hará de todo esto una o varias apps" (dueño). La app propia de
  impresión sigue para la fase final.

## Orden y cierre

Queda solo el bloque 3 (los bloques 1 y 2 ya están mergeados). Al terminar los tres: actualizar `ROADMAP.md` (Kardex fase 2
tachado, decisión nueva sobre menú editable y agregados en el registro, nota de
responsive), borrar este archivo y dar al dueño el resumen corto en su idioma.
