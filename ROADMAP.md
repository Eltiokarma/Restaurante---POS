# Roadmap y registro de decisiones

## Estado actual — Fase 1 (completa, pendiente de prueba en sala)

- [x] Flujo de cliente: inicio → menú por categorías → resumen → ventana de cancelación →
      ticket → número de orden.
- [x] Cola de cocina con estados y resaltado de urgencia (>10 min).
- [x] Admin: menú del día, catálogo, órdenes, log de cancelaciones, configuración.
- [x] Impresión en dos modos: terminal (PC con impresora) y estación (`/ticketera`, para
      terminales tablet, compatible con cualquier impresora con driver del sistema).
- [x] Tests de backend (pytest) + CI en GitHub Actions.
- [x] Modo producción de un solo comando (`scripts/iniciar.*`, todo en el puerto 8000).
- [x] Backup de la BD (`backend/backup.py`).
- [ ] **Prueba en sala** (bloqueada: requiere el hardware en el local).

### Qué medir en la prueba en sala

1. Pedidos completados en terminal vs. pedidos que terminaron pidiéndole a una persona.
2. Cancelaciones en la ventana de 30s (muchas = algo confunde en el flujo).
3. Tiempo promedio por pedido en terminal vs. cajero. Las órdenes guardan hora exacta y las
   cancelaciones también, así que 1 y 2 ya salen del admin; el tiempo por pedido de punta a
   punta es candidato a instrumentarse en Fase 2.

## Fase 2 — según resultados de la prueba en sala (por priorizar)

- [x] Métricas para el dueño: pestaña "Resumen" en admin con total vendido, tiempo promedio
      por pedido (instrumentado inicio→confirmación, campo `duracion_seg`), tasa de
      cancelación, ventas por plato, órdenes por hora y export CSV para Excel.
- [x] Resumen semanal/histórico: selector Hoy / Últimos 7 días / Últimos 30 días en el
      Resumen, con ventas por día y export CSV del período (`GET /api/stats/range`).
- [ ] Ajustes de UX táctil que surjan de observar clientes reales.
- [ ] Impresión ESC/POS directa desde el backend (corte automático, gaveta, doble copia) si
      la impresión por driver + `--kiosk-printing` queda corta en la práctica.
- [ ] Endurecer multi-terminal si se agrega una segunda tablet (hoy ya es seguro a nivel de
      datos; revisar UX de números de orden y capacidad de la ticketera).
- [x] Backup automático: el servidor refresca la copia del día cada 30 minutos mientras
      corre (`app/services/backup.py`); `python backup.py` queda para copias manuales.
- [x] Export CSV de ventas (por día o por rango, desde el Resumen del admin).

- [x] Temporizador en los pedidos de cocina: cada tarjeta muestra el tiempo de espera
      corriendo en vivo (mm:ss), en rojo cuando supera los 10 minutos en pendiente.
- [x] Vista de caja (`/caja`): el cajero registra pedidos sin ventana de cancelación
      (confirma en persona) y gestiona los del día — avanzar estado, reimprimir y anular.
      Estado nuevo `anulada`: la orden queda en BD pero no cuenta en ventas, sale de la
      cola de impresión y no aparece en cocina.
- [x] Apertura y cierre de caja: fondo inicial, conteo al cierre, diferencia contra el
      sistema (re-cerrar corrige), un registro por día e historial para el admin.
- [x] Tipo de servicio por pedido (sala / llevar / mixto): selector en terminal y caja,
      resaltado en ticket y cocina, columna en el CSV de ventas.
- [x] Cocina por tandas: tira "Por salir" con totales por plato y selección múltiple para
      avanzar 2-3 pedidos de una vez.
- [x] Empaque POR PLATO (mesa / táper / bolsa / lonchera): chips por línea en el resumen
      del cliente y en la caja; visible en la tarjeta de cocina, en el desglose de la tira
      "Por salir" (5× lomo: 3 mesa · 2 táper), en el ticket ([TAPER]) y en el CSV. El tipo
      de servicio de la orden ahora se deriva de los empaques.
- [x] Candado `PIN_LOCAL` para despliegues en internet (Railway): con la variable definida,
      toda la API exige el PIN (se pide una vez por dispositivo); sin ella, la LAN funciona
      igual que siempre.

## Fase 4 — operación avanzada

- [x] **Métodos de pago**: la caja registra cómo se pagó cada orden (💵 efectivo / 💳
      tarjeta / 📱 Yape; corregible con re-toque). El cierre de caja cuadra SOLO el
      efectivo esperado (fondo + ventas en efectivo) y reporta tarjeta/Yape aparte; una
      orden sin método registrado se asume efectivo (comportamiento histórico). Columna
      `pago` en el CSV.
- [x] **Insumos y recetas**: catálogo de insumos con stock y costo promedio ponderado, y
      receta por plato (insumo + cantidad por porción) con costo por porción y margen
      calculados.
- [x] **Kardex**: compras (recalculan costo promedio), mermas, ajustes por conteo físico y
      **consumo automático por venta** según la receta (anular una orden devuelve el
      stock). Stock negativo visible en rojo = vendiste más de lo que el kardex tenía.
- [x] **Mesas**: configuración en admin (crear/renombrar/desactivar), asignación de tickets
      a mesas desde caja (al crear o después), **combinar** mesas (un ticket con varias),
      **liberar** (libera el ticket completo, combinadas juntas), panel de ocupación en
      caja, insignia en cocina y línea "MESA" en el ticket. Ocupación calculada desde las
      órdenes del día (anular desocupa).
- [x] **Candado de apertura**: con `exigir_caja_abierta` (default encendido, toggle en
      Configuración) no se registran ventas hasta abrir la caja con su fondo — la terminal
      muestra "aún estamos abriendo la caja" y se habilita sola; el backend rechaza con 409
      como red de seguridad.
- [x] **Movimiento de todos los días**: selector de fecha en Admin → Órdenes
      (`GET /api/orders/of-day`) e historial de cierres de caja (últimos 30) en el Resumen.
- [ ] **Despliegue en Railway** (guía lista en el README): crear el proyecto con la cuenta
      del dueño, variables (`ADMIN_PASSWORD`, `PIN_LOCAL`), volumen en `/data` y dominio.
- [ ] Kardex fase 2 (cuando se use en serio): reporte de consumo semanal, alertas de stock
      mínimo por insumo, export CSV del kardex.

## Fase 2 de voz — laboratorio (`voz-lab/`, independiente del POS)

- [x] Banco de pruebas Whisper + Claude: grabadora de audios, pipeline de evaluación con
      `resultados.csv`, y modo `--solo-interpretacion` para iterar el prompt sin volver a
      pagar transcripción. El intérprete (`voz-lab/services/interpreter.py`) usa el MISMO
      contrato que consumirá el POS: `{"items": [{"plato_id", "cantidad"}],
      "no_encontrados": [], "notas": ""}`.
- [ ] Capturar mínimo 30 audios reales (protocolo en `voz-lab/README.md`) y afinar el
      prompt hasta que la interpretación sea confiable.

## Fase 3 — pedido por voz (integración al POS)

- [x] Integración completa, **apagada por defecto** (kill switch `voz_habilitada` en
      Configuración; además requiere las API keys en `.env`): botón "🎤 PEDIR POR VOZ" en
      la terminal, grabación con medidor de nivel y corte por silencio (2.5s) o 20s,
      pantalla de verificación táctil (la voz NUNCA confirma sola), suma al carrito y
      sigue el flujo estándar. Campo `origen` (tactil/voz/mixto) en órdenes y CSV,
      sinónimos por plato editables en admin (chips), tabla `voz_logs`, y panel Admin →
      Voz con % aceptado/corregido/descartado, latencia y costo del día en S/.
- [ ] **Antes de encenderla**: correr el banco de pruebas (Fase 2) con audios reales del
      local y pegar el prompt refinado + sinónimos en los marcadores `TODO` de
      `backend/app/services/voice.py`. Umbral acordado: >85% integra; 70–85% con
      corrección obligatoria (ya es el diseño); <70% se queda apagada.

## Fuera de alcance por ahora

Pagos integrados (Yape/tarjeta), control de stock y mermas, app nativa, multi-local.

---

## Registro de decisiones

| # | Decisión | Motivo |
|---|---|---|
| 1 | SQLite, sin Postgres | Un solo local, una BD-archivo simplifica operación y backup. Revisar solo si hay multi-local. |
| 2 | Polling, sin WebSockets | Menos piezas móviles; los intervalos (30/10/3s) son suficientes para un restaurante de menú. |
| 3 | Impresión vía navegador + estación `/ticketera` | Compatible con cualquier impresora con driver del sistema; evita el lock-in de hardware tipo Loyverse. ESC/POS directo queda como opción de Fase 2, no requisito. |
| 4 | La orden se persiste recién tras la ventana de cancelación | Cocina nunca ve pedidos que se cancelan; el log de cancelaciones queda separado para análisis. |
| 5 | Correlativo diario calculado en BD con lock, zona `America/Lima` | Números cortos para cantar en caja; independiente del reloj de los dispositivos. |
| 6 | Auth admin: token HMAC stateless de 12h | Suficiente para un local con una laptop; sin tabla de sesiones ni dependencias extra. |
| 7 | Frontend compilado servido por FastAPI en producción | Un solo proceso y un solo puerto (8000) en la laptop del local; Vite queda solo para desarrollo. |
| 8 | Nube (Railway) habilitada con candado `PIN_LOCAL`; la laptop queda como plan B ante cortes de internet | El dueño decidió operar en nube. El PIN protege todas las pantallas en la URL pública; la misma base de código corre local con `iniciar.bat` si el internet del local falla (bases de datos separadas). |
