# CONTINUAR — Sesión 6: validar en campo lo nuevo y decidir lo pendiente

> Plan de la sesión en curso. Empezar por el bloque 1 sin pedir contexto.
> El sistema está VIVO en el local (Railway despliega `main`, ~2-3 min).
> Flujo por cambio: implementar → `python -m pytest tests/ -q` (backend/.venv)
> → `npm run build` → navegador real → commit en español → PR a main →
> merge → realinear la rama de sesión con `origin/main`.

## Dónde quedó todo (sesión 5, cerrada 2026-10-07)

Entregado y en producción (PR #102 a #119):

- **Voz**: intérprete rápido por reglas (`voz_rapida.py`) antes de la IA;
  diminutivos en todo; "falta elegir / ahorita te digo" deja el tiempo
  pendiente; mesa sin letra se autoasigna (14 → 14A, 14B…); "para la 7"
  es mesa; reparte segundos y empaques; desglose vs adicional ("cuatro
  menús, uno para llevar" = 4); entiende presa y huevo. Lo seguro va
  directo a la ventana de cancelación; lo dudoso pasa por "¿Eso pediste?".
- **Comanda**: sin nombre del local ni "Gracias", ORDEN izq / MESA der,
  "SEPARADO" por defecto ("TODO JUNTO" solo si todo es para llevar),
  recuadro chico "FALTA ELEGIR" con plural, refresco oculto, letras
  separadas (ESC SP 2), PAGADO / NO PAGO. Producción a 48 columnas.
- **Pago al pedir**: botones "OK y pagó" / "OK y no pagó" (y "Así nomás:
  Pagó / No pagó" cuando falta elegir). Con "pagó" sale la **precuenta**
  (Font B, dos columnas: entrada | segundo | monto por menú; ~8 renglones).
- **Plato**: presa de pollo (platos con "pollo" en el nombre), "2 huevos
  fritos en vez de la carne" (a la inglesa / bien frito), opciones Sin
  puré / lentejas / ensalada / frejoles / papas / ají / cebolla, Poco o
  Sin arroz, Jugoso / Sin jugo. El "⏳ Que espere" se movió dentro de la
  hoja del plato (antes se tocaba por error).
- **Stock del día**: Caja → "📋 Menú del día" → "¿Cuántos hay hoy?"; la
  terminal muestra "Quedan N" (solo aviso, nunca bloquea). Lo de la última
  vez queda de sugerencia ("ayer: 25" → "Usar 25" / "Usar en todos").
- **Cajón de dinero** (CBX en el puerto DK, pin 2, probado OK por el dueño):
  se abre con "OK y pagó" y con "💵 Abrir cajón" en la cabecera de Caja.
  Config en Admin → Configuración (pin 2 / pin 5 / no). El pulso suelto
  viaja como trabajo "prueba" (numero "CAJON") para no exigir actualizar
  la app Android ni el puente.

## Sesión 6 (propuesta)

1. **Validar en campo lo nuevo** (preguntar al dueño, mirar datos):
   - la precuenta en papel (¿se lee bien la letra chica a dos columnas?);
   - el stock sugerido al abrir el día siguiente a poner cantidades;
   - que el cajón abra con cada "OK y pagó" y no con "no pagó".
2. **Cuadre de caja** — HECHO (sesión 6): la terminal ya no tiene un solo
   "OK y pagó": son "💵 Pagó efectivo" / "📱 Pagó Yape" / "💵📱 Pagó mixto"
   (y en "Así nomás": Efectivo / Yape / Mixto / No pagó). El método sale en
   la precuenta ("YAPE - TOTAL PAGADO S/ …") y queda en la orden; con Yape
   el cajón no se abre. El mixto NO pide montos en la terminal: en Caja,
   botón "💵📱 Mixto · falta el Yape" → "¿Cuánto fue por Yape?" (columna
   `ordenes.pago_yape`); sin desglosar cuenta como efectivo y la caja avisa.
   Pendiente: revisar anulados que ya estaban pagados (05/10 #54 S/ 20;
   06/10 #1 S/ 11 y #38 S/ 33).
2b. **"Plato reservado" en la comanda** — RESUELTO con datos (sesión 6):
   no era "espera" (ninguna orden del 03 al 06/10 tiene `espera`). Era la
   orden #55 del 06/10 (táctil): estofado mesa + estofado llevar, ambos sin
   entrada. La persona de mesa quedó "por tiempos" (el default) y la de
   llevar "junto"; al mezclarse, la comanda imprimía "Estofado (SEPARADO)",
   que se lee como plato separado/reservado. Ahora una persona con un solo
   plato de cocina siempre va "junto" (backend al crear la orden y botón
   de entrega bloqueado en la terminal). De paso quedaron blindados la voz
   (no marca "sale después" si no se dijo) y el "Que espere" (al fondo de
   la hoja, visible como "⏳ SALE DESPUÉS").
2c. **Sesión 6 (08/10)**: (a) ticket #14: "Camote Rebosado (SEPARADO)" se
   leía como reservado → la comanda ya no marca "(SEPARADO)" por plato; en
   entregas mezcladas solo marca la excepción ("(JUNTO)" en mesa, "(POR
   TIEMPOS)" en llevar). (b) Nombres largos: campo **nombre corto** por
   plato (Admin → Menú, debajo del nombre y en la hoja ⋯), snapshot en
   `orden_items.nombre_corto`; sale en la terminal, comanda, precuenta y
   tickets de cambios. Las marcas ([TAPER], la persona) ya no se recortan.
   **Pendiente con el dueño**: llenar los nombres cortos de los platos
   largos (Estofado…, Bistec Frito…, Arroz a la Jardinera…).
3. **Diferidos de sesiones anteriores** (no arrancar sin el dueño):
   validar tandas con `tanda_logs` y el orquestador IA; migrar botones
   viejos a la clase base `.boton`.

## Datos operativos

- Producción: `https://restaurante-pos-production-dc39.up.railway.app`
  (headers `X-Pin-Local` y `X-Admin-Token` de `POST /api/admin/login`).
  El PIN y la contraseña los da el dueño en el chat: NUNCA escribirlos en
  archivos, commits ni PRs. Se compartieron en chat: sugerir rotar
  `ADMIN_PASSWORD` en Railway.
- Impresión: modo `puente`, app Android de la tablet (`android-impresora/`),
  `impresora_columnas` = 48, `gaveta` = pin2.
- Rama de trabajo: `claude/hopeful-keller-jbjz46` (alineada a
  `origin/main`); PR por bloque y merge al toque.
- Playwright: Chromium en `/opt/pw-browsers/chromium`; desde Node importar
  `/opt/node22/lib/node_modules/playwright/index.mjs`. Server de prueba
  con `DATABASE_PATH` en el scratchpad + `seed.py`, puerto 8011. Para
  matarlo: `ps -eo pid,args | grep "[u]vicorn ... --port 8011" | awk
  '{print $1}' | xargs -r kill` (`pkill -f` mata la propia shell).
