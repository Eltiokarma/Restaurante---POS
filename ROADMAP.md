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
- [x] **Empezar limpio**: Admin → Configuración borra el movimiento de las pruebas
      (órdenes, cancelaciones, caja, kardex, logs de voz) conservando menú, plantillas,
      mesas, insumos, recetas y config. Pide escribir "BORRAR" y opcionalmente deja el
      stock en 0 para el conteo físico inicial. Sin esto, el primer día real arranca con
      los números de las pruebas encima.
- [x] **Aviso de impresión detenida**: si la ticketera/puente se cuelga, los tickets se
      acumulaban EN SILENCIO y cocina no se enteraba. Caja y cocina muestran ahora un
      cintillo "⚠ N tickets sin imprimir hace X min" (a partir de 2 min; solo en modos
      estacion/puente).
- [x] Impresión ESC/POS directa (corte automático, tildes CP850): quedó corta en la
      práctica la impresión por driver al pasar a tablets + Railway. Modo de impresión
      nuevo "puente": el backend genera los bytes del ticket y
      `scripts/puente_impresion.py` (PC del local, solo Python estándar) los manda a la
      impresora de red por IP:9100 usando la cola existente. Config de impresora en
      Admin → Configuración con ticket de prueba. Gaveta y doble copia quedan como
      mejoras futuras.
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
- [x] **Mesas compartidas**: varios tickets pueden ocupar la misma mesa (local lleno).
      "🪑✔ Se fue" libera solo la mesa de ESE ticket; la mesa queda libre cuando el último
      grupo se va. Liberar la mesa completa desde el panel sigue disponible (con aviso).
- [x] **Notas por plato**: pedidos especiales ("sin frijoles", "con un huevo frito") por
      item — se escriben en terminal o caja, salen resaltadas en la tarjeta de cocina y en
      el ticket impreso, y quedan en el CSV.
- [x] **Rediseño visual "Fonda"** (de Claude Design, auditado e integrado): identidad de
      fonda peruana moderna en `styles.css` — papel y tinta, serif del sistema para
      rótulos, paleta achiote/ají/culantro/mayólica, cenefa, estados con forma además de
      color, "Por salir" como pieza principal de cocina. Cero dependencias, cero recursos
      externos, impresión térmica intacta. Nota completa en `docs/NOTA-DE-DISENO.md`.
- [x] **Despliegue en Railway**: proyecto creado con la cuenta del dueño, variables
      (`ADMIN_PASSWORD`, `PIN_LOCAL`), volumen en `/data` y dominio público. Las tablets
      del local entran por esa URL con el PIN. Ojo aprendido: Railway debe apuntar a la
      rama `main`, si no sirve una versión vieja.

## Fase 5 — el menú como unidad de venta (espec en `docs/ESPEC-FONDA-BACKEND.md`)

Especificación completa entregada junto al rediseño. Orden acordado:

- [x] §2 `sale_al_momento` por plato (checkbox en el menú del admin) + entrega "Todo
      junto" / "Separado por tiempos": selector en el resumen del cliente (con "junto"
      bloqueado y aviso cuando hay un plato al momento), corregible en caja, badge en
      cocina, línea ENTREGA en el ticket, columna en el CSV y validación 422 en backend.
- [x] §1 Menú encadenado: plantillas de menú con tiempos y alternativas (editor en
      Admin → Menú del día), precio en el MENÚ (los platos elegidos entran con precio
      0/recargo: sin doble cobro), tiempos de una sola opción se informan como
      incluidos, porciones extra por tiempo a precio configurable ("una entrada más"
      a S/ 3 aunque dentro del menú vaya a S/ 1), armado táctil en terminal y caja
      (clases `.combo-*`), bloque agrupado en cocina/ticket/caja, "Por salir" suma
      los platos elegidos, menús en Resumen y CSV (columna `menu`), compatibilidad
      total con la venta a la carta y el histórico.
- [x] §3 Estado por ítem + despacho por bulks desde "Por salir": los chips de la tira
      son tachables (elige cuántas porciones y si pasan a preparación o listas), la
      cascada va de la orden más antigua a la más nueva partiendo ítems si hace falta
      (el total nunca cambia), bulk mixto atómico en el backend, ítems tachados en la
      tarjeta, y "tanda" configurable: agrupa el pedido más antiguo con los que
      llegaron en los siguientes X minutos (Admin → Configuración, default 10, 0 =
      apagado) y sugiere esa cantidad al tachar.
- [ ] Pantalla de cocina POR ESTACIÓN (plancha / entradas): filtrar la tira y las
      tarjetas por categoría o estación. Decidido dejarlo para más adelante.
- [x] §4 Menores: cintillo "ANULADA — NO PREPARAR" 60 s en cocina (timestamp
      `anulada_en`, segundos calculados en el servidor), descuadre del cierre como
      cifra grande (signo y magnitud separados en la API: `descuadre {tipo, monto}`),
      fotos de plato (subida en Admin → Menú del día, servidas por el backend desde
      `<carpeta de la BD>/fotos` — en Railway el volumen `/data`; el GET de fotos va
      sin PIN porque un `<img>` no manda headers), y arranque de emoji → SVG con
      `components/Iconos.tsx` (cabeceras y badges: sartén, billete, silla, reloj,
      engranaje, prohibido); el resto de emojis migra gradualmente.
- [x] **Alertas de stock mínimo**: cada insumo puede tener un "avisar bajo" (0 = sin
      aviso); Admin → Insumos resalta la fila y muestra "se está acabando: pollo, arroz".
- [x] **Kardex intuitivo con bases pregrabadas** (pedido tras la prueba en sala): Admin →
      Insumos en tres pestañas — Despensa (acciones por fila: Compré / Conté / Se perdió,
      sin formularios aparte), Recetas (elige el plato y "Usar receta base" si es un
      clásico) e Historial en lenguaje claro. `app/data/fonda_base.py` trae 62 insumos
      típicos de fonda (unidad, costo referencial, mínimo sugerido) y 47 recetas base por
      porción; se cargan sin duplicar y todo queda editable.
- [x] **Reporte de consumo del kardex** (Admin → Insumos → Consumo): rango Esta semana /
      Semana pasada / Últimos 30 días / fechas a mano; tarjetas de compraste, se usó, se
      perdió y por agotarse; barras de consumo por día; tabla por insumo con lo usado, lo
      comprado, la merma, el stock de hoy y para cuántos días alcanza; y export CSV
      (`GET /api/insumos/consumo` y `/consumo.csv`). Lo usado se valoriza al costo promedio
      vigente y la devolución de una orden anulada descuenta del consumo sin bajar de cero.
- [x] **La caja se puede reabrir y corregir** (caso real: se abrió una caja de prueba y el
      día quedó amarrado): botón "Reabrir caja" (deshace el cierre, las ventas no se tocan,
      el conteo se repite al cierre de verdad) y "Corregir fondo inicial" (abierta o
      cerrada; si ya cerró, el descuadre se recalcula con el fondo nuevo).
- [x] **Varias cajas por día y doble check al cerrar** (pedido del dueño): cerrada una
      caja se puede abrir la siguiente ("🆕 Abrir caja nueva"), y cada una cuadra SOLO
      con las ventas de su tramo — el registro guarda `desde_orden_id` (la última orden
      del día al abrirla; NULL = todo el día, como los cierres históricos), así el corte
      es por orden y no por hora. El cierre ahora pide confirmación en dos pasos
      mostrando el resultado antes ("¿Cerrar con S/ X? Faltarían S/ Y"). El historial
      del admin numera las cajas del día ("· caja 2"). La tabla `cierres_caja` perdió el
      UNIQUE de fecha (migración que la reconstruye una sola vez, datos intactos).
- [x] **Comanda de cocina legible de lejos** (feedback del primer servicio real): las
      bebidas no salen en la comanda ni en "Por salir" — se sirven en mesa, el refresco
      interrumpía la lectura (cada ítem viaja con su categoría; un plato borrado del
      catálogo se muestra por si acaso) — y la letra de los platos va al doble (3.1rem)
      con tarjetas más anchas para que quepan los nombres largos. El ticket y la caja
      siguen mostrando todo.
- [x] **Auditoría visual aplicada** (handoff de Claude Design, 12 hallazgos sobre /caja y
      /admin, 5 transversales): token `--tinta-suave` ahora cumple AA (#6f6559; el viejo
      quedó como `--tinta-decorativa`), cifras de dinero en sans con `lining-nums
      tabular-nums` en TODAS las pantallas (terminal, caja, cocina, admin), piso táctil
      `--toque-min: 48px` / `--toque: 56px`, panel de caja como tablero (esperado en
      efectivo a 40px manda; egresos/tarjeta/Yape en grid; "sin registrar" como chip),
      banda izquierda de la fila de pedido coloreada por estado como en cocina, avisos en
      franja de alto reservado fuera del header + cintillo persistente de "sin conexión",
      egresos como filas auditables con ✕ de 48px, tiles del resumen con jerarquía (el
      total manda a 52px), tabs del admin en una línea con scroll, barras del resumen
      fluidas con línea de base y "pico 13h · N órdenes" (achiote solo sobre el promedio),
      tablas editables con inputs de 52px y precio a la derecha, 8 iconos SVG nuevos
      reemplazan emoji (candados, egreso, tarjeta, móvil, impresora, lápiz, aspa) y los
      mensajes de estado van sin emoji. Pendiente por decisión de producto: agrupar
      acciones secundarias tras un "⋯" (hallazgos 01/02/07) y migrar todos los botones a
      la clase base `.boton`. Reglas nuevas documentadas en `docs/NOTA-DE-DISENO.md`.
- [x] **Caja con "+ UN MENÚ" y cierre con resumen en pantalla**: la caja usa la misma
      tarjeta de oferta que la terminal (lista de platos por tiempo sin precios, un toque
      agrega el menú completo, contador al costado; adiós al modal "ARMAR MENÚ", ahora
      código muerto eliminado). El doble check del cierre muestra EN PANTALLA el mismo
      resumen que se imprime (TicketCierre en un modal) para chequearlo antes de
      confirmar; los errores del cierre se ven dentro del modal. La fórmula del esperado
      vive en un solo helper (`esperadoEnCaja`) usado por panel, modal y ticket.
- [x] **Egresos del turno y resumen impreso del cierre**: en Caja se registra la plata
      que sale del cajón (gas, verduras…) con concepto y monto — cada egreso pertenece a
      SU caja (tabla `egresos_caja` amarrada al registro) y baja el efectivo esperado del
      cierre (snapshot en `cierres_caja.egresos`; se borran solo con la caja abierta). Al
      cerrar, se imprime un resumen del turno (fondo, ventas por método, egresos,
      esperado, contado y el descuadre en grande): en modo puente lo saca la ticketera
      (trabajo tipo "cierre", confirma con `POST /api/print/cierre/impresa`) y en los
      demás modos lo imprime la propia pantalla de caja. El historial del admin ganó la
      columna 💸 Egresos.
- [x] **Menús guardados por día** ("el menú de los jueves"): en Admin → Menú del día se
      guarda el menú de hoy con un nombre (chips Lunes…Domingo o texto libre; el mismo
      nombre actualiza) y otro día se carga con un toque — restaura platos activos Y las
      plantillas con sus alternativas (snapshot JSON en `menus_guardados`). Cargar pide
      confirmación porque reemplaza el menú de HOY.
- [x] **Contador de menús y "Volver" en la espera** (feedback del servicio): junto al
      botón "+ UN MENÚ" hay un box del mismo alto con el total de menús del pedido (se
      cuenta sin scrollear), y la pantalla de espera ganó "↩ VOLVER A CORREGIR" — antes
      solo se podía cancelar todo o saltarse la espera.
- [x] **Comanda por grupos y mesa desde el pedido** (feedback del servicio): la comanda
      impresa agrupa ENTRADAS arriba y SEGUNDOS abajo (junta iguales: "3 x Sopa"), con la
      observación al costado del plato (o debajo si no entra); la nota de un menú se pega
      a su segundo. "ENTREGA: POR TIEMPOS / TODO JUNTO" va en letra grande y negrita. La
      mesa ahora se elige al tomar el pedido en la terminal (chips opcionales, se puede
      marcar varias); si nadie la elige, el ticket dice "SIN MESA", y al asignarla después
      desde Caja el ticket se reimprime solo con su mesa.
- [x] **Táper con precio y empaques configurables** (reglas del dueño para el servicio
      real: "táper cuesta un sol más; bolsa y lonchera no"): `precio_taper` en Admin →
      Configuración cobra cada porción en táper como línea "Táper × N" (item `es_cargo`,
      nace "entregado": entra al total, al ticket y al CSV pero cocina no la ve ni frena
      la orden), con el cargo visible ANTES de confirmar y el "+S/ 1.00" en el propio
      chip del táper; `empaques_ofrecidos` apaga bolsa/lonchera en terminal y caja (mesa
      siempre va). La "carne más a S/ 6" es el agregado, editable en Admin.
- [x] **Pantalla única del pedido** (pedido del dueño tras probar): tocar la pantalla de
      inicio lleva DIRECTO a "Tu pedido" — la oferta del menú con su botón "UN MENÚ"
      arriba y las tarjetas editables abajo; sin pantalla intermedia y sin "Prefiero
      elegir cada plato" (todo se cambia en la tarjeta: elección, sin sopa, empaque por
      plato, extras, agregados, nota). "Cancelar todo" y la voz viven en la misma
      cabecera. Con el interruptor de solo-menús apagado, o si hoy no hay menú activo,
      el flujo de carta de dos pantallas sigue igual.
- [x] **Menú para varios, cada uno a su manera** (caso real del dueño: "una señora quiere
      algo para 4 — uno segundo solo, otro con sopa acá y segundo para llevar, otro sin
      frijoles, otro todo en bolsa y lonchera"): el armado "para N" entra como N tarjetas
      independientes (los extras y agregados del armado van en la primera, no se
      multiplican) y salta directo a la lista para configurar cada una; en cada tarjeta se
      elige el **empaque POR PLATO** ("Mesa ▾" en cada tiempo → mesa/táper/bolsa/lonchera,
      con "Todo el menú:" como general) y también las **porciones extra** del tiempo (la
      regla de la entrada: incluida vale lo del menú, una más a su `precio_extra`); quitar
      un tiempo bota sus extras. Backend: `empaques {tiempo_orden→empaque}` en el payload
      con validación, empaque por ítem en cocina/ticket/CSV y `tipo_servicio` mixto
      derivado solo. El minicaso de los amigos sale exacto: solos S/ 14 + S/ 10; juntos,
      dos menús completos a S/ 11 pasándose la entrada.
- [x] **La terminal muestra SOLO los menús** (pedido del dueño tras probar el pedido
      "desde el menú"): las secciones de platos sueltos (entradas, segundos…) ya no salen
      en la terminal — repetían lo del menú y confundían. Interruptor en Admin →
      Configuración por si algún día se quiere volver a mostrar la carta (y si no hay
      ningún menú activo, la carta aparece sola como respaldo); la caja siempre ve todo.
- [x] **Pedido "desde el menú"** (pedido del dueño tras probar en sala): el flujo arranca
      con el botón "UN MENÚ — S/ 11" que agrega el combo completo con la opción por defecto
      de cada tiempo (la primera sin recargo); en el resumen cada menú es una tarjeta
      desplegable ("Menú 1, Menú 2…") donde se cambia la elección, se quita un tiempo
      ("Sin sopa", con descuento configurable por tiempo — decisión del dueño: S/ 1 la
      entrada) y se suman agregados (+presa S/ 4, +refresco S/ 1.50, +arroz S/ 1.50,
      +ensalada S/ 2, +guarnición S/ 2 — editables en Admin → Menú del día), con lo quitado
      y agregado, su costo y el total por tarjeta. Cocina y ticket destacan "SIN SOPA" y
      "+1 PRESA"; el CSV y el Resumen descuentan lo quitado. Los agregados NO descuentan
      kardex (no tienen receta): pendiente decidir si se les cuelga una.
- [x] **Auditoría de tamaños de tablet**: las cinco vistas probadas con capturas en 600×960,
      960×600, 800×1280, 1280×800, 1200×1920, 1920×1200, 1024×768 y 1366×768. Correcciones:
      chips y steppers del cliente a ≥64px (los botones principales siguen en ≥80px), el
      chip largo de "Por salir" ya no desborda en 7", los modales usan `dvh` con scroll
      interno y el pie del armado queda pegado abajo siempre visible, y las tablas del
      admin scrollean dentro de sí mismas bajo 900px. La regla táctil quedó escrita en
      `CLAUDE.md` y es la que heredará la app cuando se haga (decisión del dueño: "al final
      se hará de todo esto una o varias apps").
- [ ] **App propia de Android para imprimir** (reemplazo de RawBT): decisión del dueño —
      se hace en la fase final del prototipo, no ahora. Llevaría dentro el mismo driver
      ESC/POS que hoy pone RawBT, se compilaría en GitHub Actions y se instalaría en la
      tablet; ventaja extra sobre el navegador: puede seguir imprimiendo con la tablet
      bloqueada. Mientras tanto opera RawBT — probado en sala: imprime, pero en la
      tablet del dueño **pide un toque por ticket** (política de Chrome Android). Por eso
      la app propia sube de prioridad para la fase final.
- [ ] **Impresora "cloud"** (Star CloudPRNT / Epson Server Direct Print) como opción para
      cuando se renueve el hardware: la impresora pregunta sola a nuestro servidor y no
      hace falta ni app ni PC ni tablet-jefe. No comprar solo por esto.

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
| 9 | Menú encadenado: los platos elegidos son `OrdenItem`s ligados a `orden_menus` con `precio_snapshot` = 0/recargo/extra; la `entrega` sigue viviendo en la ORDEN (no por menú) | El precio del menú vive en `orden_menus` y el total nunca suma el precio de carta de los platos (sin doble cobro), pero cocina y kardex los ven como items normales. La espec sugería `entrega` por menú; se mantuvo por orden porque así se implementó el §2 y la cocina despacha la orden completa. |
| 10 | Porciones extra con el menú: `precio_extra` configurable POR TIEMPO en la plantilla (+ recargo de la alternativa) | "Una entrada más" no se cobra ni al precio de carta (S/ 6) ni al implícito del combo (S/ 1), sino al precio que el dueño fija (S/ 3). Vacío/0 = ese tiempo no ofrece extras. |
| 11 | `ordenes.estado` queda como CACHÉ recalculada = el estado MÍNIMO de sus ítems (no un campo derivado en consultas) | Media docena de sitios lo leen (cocina, caja, admin, stats, ticketera): mantenerlo materializado no rompe a nadie. Se recalcula en cada despacho de bulk; avanzar la orden completa arrastra todos sus ítems al mismo estado. Anulada sigue siendo estado solo de la orden. |
| 12 | Despacho parcial parte el ítem en dos filas (mismas snapshots, estados distintos) | Es la única forma de tachar "3 de 5" sin perder de qué orden salió cada porción; el total de la orden y el kardex no se alteran (la anulación devuelve por movimientos, no por filas). |
| 13 | Impresión con impresora de red: el backend renderiza ESC/POS y un PUENTE en el local lo manda a IP:9100 (modo "puente") | Una página web no puede hablarle directo a una impresora, y el backend en Railway no alcanza la red del local. El puente (stdlib de Python, cero instalaciones) reusa la cola `impreso=False` que ya existía para /ticketera; si la impresora falla, el ticket queda en cola y se reintenta. |
| 14b | Avanzar la ORDEN solo empuja ítems hacia adelante, nunca los retrocede | Encontrado en la revisión de la sesión: con estado por ítem, "empezar a preparar" en la tarjeta devolvía a la cola porciones ya tachadas por bulk y se cocinaban dos veces. El bulk y el avance por orden conviven solo si ambos respetan el rango del estado. |
| 14c | Los trabajos de impresión (ticket de prueba incluido) salen de la cola al CONFIRMARSE, nunca al servirse | El ticket de prueba se consumía al entregarse a quien imprime: si la impresora no respondía — el caso exacto que el botón diagnostica — el trabajo se perdía y el admin veía "encolado ✔" sin que saliera nada. |
| 14 | El local NO debe depender de una PC: /ticketera en una tablet Android con la app RawBT también atiende la cola ESC/POS (rawbt:base64 vía iframe + enlace con gesto como respaldo) | Decisión del dueño: solo tablets. RawBT hace de driver de la impresora de red en la propia tablet; la misma cola sirve para tablet (RawBT) o PC (puente) — se usa una de las dos. El lanzamiento va por iframe oculto porque navegar la página a un esquema bloqueado la deja "colgada". |
| 15 | Menú editable: quitar un tiempo descuenta lo configurado en `menu_tiempos.descuento_si_se_quita` (snapshot en `orden_menus.omitidos_json`); los agregados (+presa…) viven en `menu_agregados` y entran como `OrdenItem`s con `es_agregado=True` y `plato_id NULL` | Decisión del dueño (2026-09-04): "sin sopa" sí baja un poco el precio, y pedir una sopa aparte cuesta el precio de porción extra (S/ 3). El total sigue siendo del backend: base − descuentos + recargos + extras + agregados, nunca negativo por unidad. Al no ser platos, los agregados no descuentan kardex todavía. |
