# Nota de diseño — rama `design/rediseno-visual`

## Identidad: "Fonda"

Una fonda peruana moderna no es minimalismo blanco ni admin oscuro: es papel de
estraza, tinta café, pizarra con el menú del día y una cenefa de mayólica en el
zócalo. El sistema traduce eso a cinco decisiones:

1. **Papel y tinta, no gris y azul.** Fondo `#f6f0e4` (papel cálido), texto
   `#221a14` (tinta café). Las superficies son papel más claro con filete fino,
   no tarjetas flotantes con sombra genérica.
2. **Dos voces tipográficas, cero descargas.** Serif del sistema
   (`Iowan Old Style / Palatino / Georgia`) para los rótulos — el cartel pintado
   a mano: nombre del local, títulos de pantalla, nombres de plato, total,
   número de orden. Sans del sistema para toda la operación. Ninguna fuente se
   descarga: el POS se ve igual sin internet.
3. **Paleta de cocina.** Achiote `#b03a22` (acción principal), ají `#e0a021`
   (atención y notas), culantro `#2f6b3a` (confirmar y "elegido"), mayólica
   `#1b5f86` (voz e información). Ningún gradiente decorativo.
4. **La cenefa.** Franja de 7 px con el patrón de mayólica en el borde superior
   de las cinco pantallas y en el borde de modales y del login. Es la única
   ornamentación, hecha con gradientes: 0 bytes de imagen.
5. **Jerarquía por peso y aire, no por color.** Los números que importan
   (total, orden, timers, dinero) van en cifras tabulares y tamaño grande; el
   color se reserva para significado.

## Por contexto de uso

- **`/` Terminal del cliente.** Es la cara del negocio: el nombre del local en
  serif grande con su filete rojo, y un botón de pedido de 150 px con relieve
  físico (se hunde al tocarlo). Objetivos de toque ≥80 px; los +/− de cantidad
  son de 82 px. El plato elegido se marca con banda verde a la izquierda además
  del color de fondo. El total del resumen queda separado por una doble línea,
  como una cuenta escrita a mano.
- **`/caja`.** Aquí la belleza es claridad: fondo más hondo que el cliente,
  filas de pedido compactas con banda de estado, dinero alineado a la derecha en
  cifras tabulares, botones ≥48 px. El menú se compacta a tarjetas de 76 px para
  que quepan más platos sin scroll.
- **`/cocina`.** Fondo `#14171a`, número de orden a 2.6 rem, ítems a 1.6 rem con
  cantidad a 1.75 rem en negra 900. La barra de estado a la izquierda pasa a
  14 px. Las notas ("sin frijoles") son bloque amarillo ají con marco negro
  interior, mayúsculas y 1.4 rem: imposible ignorarlas a 4 metros. La urgencia
  >10 min mantiene el rojo más gritón de todo el sistema (fondo granate, marco
  rojo, timer con fondo rojo y parpadeo por opacidad).
  **"Por salir" pasa a ser la pieza principal de la pantalla**: panel de ancho
  completo con marco ají de 3 px, rótulo propio y la cantidad de cada plato a
  2.5 rem en amarillo. La cocina cocina por bulks (4 asados de pollo con puré,
  después 2 y 2, después solo entradas y sopas), no ticket por ticket; los
  tickets de abajo quedan como el detalle de respaldo (rejilla algo más
  compacta, sin perder legibilidad a 4 metros).
- **`/admin`.** Tablas cómodas con filas alternadas, cabeceras en versalitas,
  cifras tabulares, tabs con subrayado en vez de píldoras rellenas. Poco color:
  solo la barra de proporción y el filete del primer tile.
- **`/ticketera`.** Casi nadie la mira, así que solo dice su estado: título
  reducido a etiqueta y un único bloque grande con el estado de la cola.

## Accesibilidad y estados

- **Estados sin depender del matiz.** Cada `.etiqueta-estado` lleva una forma
  además del color y de su texto: pendiente = triángulo, preparando = rombo,
  listo = círculo lleno, entregado = círculo hueco atenuado, anulada = aspa
  sobre rayado diagonal. Las órdenes anuladas además llevan trama rayada en la
  fila. Mesas: libre = contorno limpio; ocupada = relleno rayado. El mismo
  vocabulario se aplica al panel de voz del admin.
- Contraste AA en todo texto (los rellenos de color llevan tinta oscura propia).
  Tras la auditoría visual de 2026-09: `--tinta-suave` es `#6f6559` (≈5.6:1 sobre
  papel alto); el valor viejo `#8d8375` vive como `--tinta-decorativa` y se usa
  SOLO en bordes o iconos no informativos. Regla: texto por debajo de 1.1 rem
  nunca usa el token más claro.
- Métrica táctil (auditoría 2026-09): `--toque-min: 48px` es el piso absoluto
  (iconos, controles dentro de tabla) y `--toque: 56px` el alto de los botones
  de fila en /caja y /admin; la terminal del cliente sigue en 80 px. Nada por
  debajo de 48 px.
- Cifras de caja donde la cifra ES el contenido (totales, número de orden,
  countdown, tiles): `--fuente-ui` con `font-variant-numeric: lining-nums
  tabular-nums`. La serif display queda para nombres y rótulos, no para dinero.
- Foco de teclado visible global (`:focus-visible`, anillo mayólica de 3 px).
- Hover nunca es funcional; solo hay transiciones de `transform`/`opacity`.
- `prefers-reduced-motion` apaga transiciones y el parpadeo de urgencia, pero la
  urgencia se mantiene con un marco rojo fijo de 5 px.

## Lo sagrado, verificado

- `@media print` intacto en comportamiento: `body * { visibility: hidden }`,
  solo `#ticket-print` visible, `@page { size: 80mm auto }`, `.solo-impresion`
  vuelve a `position: static`. Se añadió únicamente el apagado de la cenefa y
  `background: none` en el ticket, para garantizar papel térmico sin fondos.
- El ticket gana carácter tipográfico (versalitas espaciadas en el nombre del
  local, tracking en ORDEN y TOTAL, monoespaciada del sistema) y sigue siendo
  un documento de 80 mm en blanco y negro puro.
- Overlays: `.modal-fondo` sigue en `z-index: 50` sobre todo el contenido; la
  cenefa es una franja de 7 px sin eventos de puntero.
- Responsive: el colapso de `.caja-columnas` a 1 columna en `<900px` se
  conserva tal cual; la terminal usa `clamp()` en los tamaños de cartel para
  funcionar en tablet vertical y horizontal.

## Alcance real del cambio

Un solo archivo: `frontend/src/styles.css`. **Cero cambios en `.tsx`**, cero
`className` renombrados o eliminados, cero dependencias, cero recursos externos.
No se tocó `backend/`, `voz-lab/`, `scripts/`, `api.ts` ni ningún hook.

## Sugerencias que requerirían tocar lógica (NO implementadas)

1. **Fotos de plato en la terminal.** Es lo que más subiría la conversión del
   kiosko; requiere campo `imagen` en el modelo y subida en admin.
2. **Categoría como pestañas fijas en `/`**, en vez de scroll continuo: hoy el
   cliente de pie tiene que desplazarse para ver "Bebidas". Requiere estado de
   pestaña activa en `Cliente.tsx`.
3. **Emoji → SVG inline.** El diseño los mantiene porque están dentro de los
   textos de UI en el JSX. Reemplazarlos por SVG (🍳, 💵, 🪑, ⏱) unificaría el
   lenguaje icónico, pero implica editar markup.
4. **La cola de cocina debería operarse por bulks, no por ticket.** El diseño ya
   asciende "Por salir" a pieza principal de la pantalla, pero solo puede
   mostrar totales: hoy no se puede **tachar un bulk**. Lo que falta (y requiere
   lógica, no está en el repo todavía):
   - Tocar una línea de "Por salir" y marcar N porciones de ese plato como
     salidas, avanzando en cascada los tickets más antiguos que las contenían
     (4 asados de pollo con puré → despacha los 4, sin importar de qué tickets
     vengan).
   - Bulks mixtos: seleccionar dos o tres líneas y tacharlas juntas (2 y 2), y
     un filtro rápido por familia para el bulk de entradas y sopas.
   - Estado parcial por ítem de orden (hoy el estado vive en la orden completa),
     que es el cambio de modelo que esto implica.
   - El agrupado por plato ya existe en `Cocina.tsx` (`porSalir`) y sirve de
     base; el resto es backend + estado por ítem.
5. **El menú es una unidad encadenada, no ítems sueltos.** Este es el cambio de
   fondo del sistema y toca frontend y backend por igual: la entrada o sopa va
   encadenada a un segundo, y ese a su refresco (y a futuro, postre). Hoy el
   carrito trata cada plato como línea independiente con su propio precio.
   - El precio pasa a vivir en el **menú**, no en cada plato; los platos son
     alternativas de cada tiempo.
   - **Los tiempos sin alternativas no se eligen.** Hoy el refresco es único:
     debe mostrarse como incluido, sin selección posible. Cuando entre postre,
     se comporta igual mientras no haya opciones.
   - Modelo: entidad de menú con tiempos ordenados y alternativas por tiempo;
     la orden guarda el menú y la elección de cada tiempo (manteniendo el
     snapshot de nombre y precio). Cocina y ticket tienen que mostrar el menú
     agrupado, no cuatro líneas sin relación.
   - **Diseño listo:** frame `03b` del tablero y las clases `.combo`,
     `.combo-tiempos`, `.tiempo`, `.tiempo-sin-opciones`, `.tiempo-incluido` en
     `styles.css`, marcadas como propuesta y sin uso todavía.

6. **"Todo junto" / "Separado" al elegir empaque.** Cuando el cliente reparte
   táper / bolsa / lonchera / mesa, falta decir **cómo sale el pedido**: todo
   junto en una sola entrega, o separado por tiempos. Casos reales: la sopa a la
   mesa y el segundo para llevar; o todo para llevar pero en dos bolsas para que
   el segundo llegue caliente.
   - La opción **no aplica a platos con preparación al momento**: no se puede
     pedir un bistec frito y esperar que salga junto con la sopa. Requiere una
     marca por plato en el catálogo (algo como `sale_al_momento` / tiempo de
     preparación); cuando el menú incluye uno, "Todo junto" queda **bloqueado
     con aviso** que explica por qué, en vez de desaparecer sin decir nada.
   - Impacto: campo nuevo en el modelo de plato, campo de entrega en el menú de
     la orden, y ese dato tiene que llegar a cocina (bulk de entrega) y al
     ticket.
   - **Diseño listo:** clases `.combo-entrega`, `.selector-entrega`,
     `.boton-entrega` (con estado `:disabled`) y `.aviso-entrega`.

7. **Orden de la cola de cocina por antigüedad descendente y "por salir" como
   columna fija** en pantallas anchas: hoy es una tira horizontal que se corta
   con muchos platos.
8. **Estado "anulada" en cocina**: hoy desaparece de la vista. Un cintillo de
   "anulada, no preparar" por 60 s evitaría platos cocinados de más.
9. **Aviso de descuadre en el cierre de caja** con la diferencia como cifra
   grande y su signo; hoy va en prosa dentro del panel.
