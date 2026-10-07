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
2. **Cuadre de caja**: el 05/10 faltaron S/ 20 con S/ 0 de Yape registrado
   (el 06/10 igual, S/ 0 Yape de S/ 977). No hay bug de cálculo (los
   totales de todas las órdenes cuadran); la causa probable es Yape no
   marcado, porque "OK y pagó" no pregunta el medio y el sistema asume
   efectivo. El dueño decidió tratarlo como tema del equipo. **Si vuelve a
   descuadrar**, ofrecer: "Pagó efectivo" / "Pagó Yape" en la terminal en
   lugar de un solo "OK y pagó". Revisar también anulados que ya estaban
   pagados (05/10 #54 S/ 20; 06/10 #1 S/ 11 y #38 S/ 33).
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
