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

## Fase 2 de voz — laboratorio (`voz-lab/`, independiente del POS)

- [x] Banco de pruebas Whisper + Claude: grabadora de audios, pipeline de evaluación con
      `resultados.csv`, y modo `--solo-interpretacion` para iterar el prompt sin volver a
      pagar transcripción. El intérprete (`voz-lab/services/interpreter.py`) usa el MISMO
      contrato que consumirá el POS: `{"items": [{"plato_id", "cantidad"}],
      "no_encontrados": [], "notas": ""}`.
- [ ] Capturar mínimo 30 audios reales (protocolo en `voz-lab/README.md`) y afinar el
      prompt hasta que la interpretación sea confiable.

## Fase 3 — pedido por voz (integración al POS)

- [ ] Conectar el intérprete validado del laboratorio en
      `backend/app/services/voice.py`. Contrato ya definido en el stub: la voz devuelve
      items para el carrito y NADA MÁS cambia (el flujo posterior es agnóstico al origen).

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
| 8 | Operación LAN-first; nube (Railway) solo para demo/monitoreo | Si se cae el internet del local, el POS debe seguir tomando pedidos. Hay `Dockerfile` listo, pero operar en nube requiere primero autenticación en cocina/terminal/ticketera (hoy son de LAN privada por diseño). |
