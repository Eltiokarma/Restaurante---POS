# Cambios de backend para Claude Code

Especificación de lo que el rediseño necesita y que **NO** está implementado.
El rediseño visual entregado no toca nada de esto: `frontend/src/styles.css` es
el único archivo modificado. Lo de abajo es cambio de modelo, API y lógica.

Referencias reales del repo: modelos en `backend/app/models.py`, rutas en
`backend/app/routes/`, lógica en `backend/app/services/`, migración ligera en
`_migrar()` de `backend/app/main.py` (`create_all` no altera tablas existentes),
cliente HTTP único en `frontend/src/api.ts`.

Invariantes que **no** se pueden romper (de `CLAUDE.md`):

- La orden no se persiste hasta que termina la ventana de cancelación.
- `numero_orden_dia` es correlativo por día (`America/Lima`), serializado con
  lock en `services/orders.py`.
- Los items guardan snapshot de nombre y precio: el histórico nunca cambia.
- Cancelaciones van a su propia tabla, nunca a `ordenes`.
- El backend es la autoridad de totales.

---

## 1. El menú es una unidad encadenada (cambio de fondo)

Hoy `OrdenItem` es una línea independiente con `plato_id`, `nombre_snapshot`,
`precio_snapshot`, `cantidad`, `empaque`, `nota`. Un menú del día no es eso: la
entrada o sopa va encadenada a un segundo, y ese a su refresco (y a futuro,
postre). Es **una unidad de venta con tiempos**, y el precio vive en el menú.

### Modelo nuevo

```python
class MenuPlantilla(Base):          # "Menú del día S/ 15"
    __tablename__ = "menu_plantillas"
    id, nombre, precio, activo_hoy, en_catalogo, created_at

class MenuTiempo(Base):             # un eslabón de la cadena
    __tablename__ = "menu_tiempos"
    id, menu_id -> menu_plantillas.id
    orden: int                      # 1 entrada/sopa, 2 segundo, 3 refresco, 4 postre
    rotulo: str                     # "Entrada o sopa", "Segundo", "Refresco"
    obligatorio: bool = True

class MenuAlternativa(Base):        # los platos que pueden ocupar ese tiempo
    __tablename__ = "menu_alternativas"
    id, tiempo_id -> menu_tiempos.id, plato_id -> platos.id
    recargo: float = 0.0            # 0 = sin costo extra
```

Regla que el frontend ya dibuja (frame `03b` del tablero): **un tiempo con una
sola alternativa no se elige** — se informa como incluido. El backend debe
exponer el conteo para que la terminal no renderice un selector de una opción.

### Modelo de la orden

```python
class OrdenMenu(Base):              # un menú vendido dentro de una orden
    __tablename__ = "orden_menus"
    id, orden_id -> ordenes.id
    menu_id -> menu_plantillas.id (nullable, por si se borra la plantilla)
    nombre_snapshot: str
    precio_snapshot: float          # el precio del MENÚ, no de los platos
    cantidad: int
    entrega: str = "junto"          # junto | separado  (ver §2)
    nota: str = ""
```

`OrdenItem` gana `orden_menu_id` (nullable) y `tiempo_orden` (nullable):

- `orden_menu_id = NULL` → venta a la carta, comportamiento actual intacto.
- `orden_menu_id` presente → el ítem es el plato elegido para ese tiempo. Sigue
  guardando `nombre_snapshot` (para cocina y ticket) pero su
  `precio_snapshot` pasa a `0.0` o al `recargo`: **el precio ya está en el
  menú**, no se puede sumar dos veces.

El total de la orden = Σ(`orden_menus.precio_snapshot` × cantidad + recargos) +
Σ(items a la carta). Esto vive en `services/orders.py`, que sigue siendo la
autoridad del total.

### Migración

En `_migrar()`: `CREATE TABLE IF NOT EXISTS` para las cuatro tablas nuevas y
`ALTER TABLE orden_items ADD COLUMN orden_menu_id INTEGER` /
`ADD COLUMN tiempo_orden INTEGER`. Las órdenes históricas quedan con NULL = a la
carta, que es exactamente lo que eran.

### API

- `GET /api/menu/hoy` gana `menus: [{id, nombre, precio, tiempos: [{orden,
  rotulo, obligatorio, alternativas: [{plato_id, nombre, precio, recargo}]}]}]`
  además de los `platos` actuales (a la carta). **No romper la forma actual**:
  agregar, no reemplazar, para que `api.ts` siga tipando.
- `POST /api/orders` acepta `menus: [{menu_id, cantidad, elecciones: {tiempo_orden:
  plato_id}, entrega, empaque, nota}]` junto a los `items` actuales.
  Valida: que cada tiempo obligatorio tenga elección, que la elección esté entre
  las alternativas de ESE tiempo, y que el plato siga activo hoy (mismo 409 que
  ya existe cuando algo se agota).
- Admin: CRUD de plantillas, tiempos y alternativas bajo `requiere_admin`.

### Cocina y ticket

- La respuesta de órdenes debe agrupar por menú, no devolver cuatro líneas
  sueltas: cocina tiene que ver "Menú 1 · sopa + segundo" como un bloque, y el
  ticket imprimir el menú con sus tiempos indentados.
- El agrupado por plato de `Cocina.tsx` (`porSalir`) sigue sirviendo para "Por
  salir": suma alternativas elegidas, no menús.

### Tests

`tests/test_menu.py` y `tests/test_orders.py`: total correcto con menú (no doble
cobro), rechazo de elección fuera de las alternativas, tiempo obligatorio
faltante, plato agotado a mitad del pedido, y que una orden a la carta antigua
siga calculando igual.

---

## 2. Entrega: "Todo junto" / "Separado", y platos que salen al momento

`Plato` gana:

```python
sale_al_momento: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
# opcional, mejor que un bool si se quiere ordenar la cola:
# minutos_preparacion: Mapped[int | None]
```

Migración: `ALTER TABLE platos ADD COLUMN sale_al_momento BOOLEAN DEFAULT 0`.
Editable en Admin → Catálogo (una casilla más en la tabla que ya existe).

Regla de negocio, validada en el backend además de la UI: si algún plato elegido
del menú tiene `sale_al_momento = True`, `entrega` **debe** ser `separado`. Un
bistec frito no puede salir junto con la sopa. Si el cliente manda `junto`,
responder 422 con un mensaje que la terminal pueda mostrar tal cual.

`entrega` viaja a cocina (define el bulk de entrega) y al ticket (`TODO JUNTO` /
`POR TIEMPOS`). En `/caja` es corregible como el método de pago.

Tests: menú con plato al momento rechaza `junto`; menú sin platos al momento
acepta ambos; el valor llega en la respuesta de órdenes y en el CSV.

---

## 3. Cocina por bulks: tachar desde "Por salir"

El rediseño ya asciende "Por salir" a pieza principal de `/cocina`, pero solo
puede mostrar totales: hoy no se puede tachar un bulk. Cocina cocina 4 asados de
pollo con puré, después 2 y 2, después solo entradas y sopas — no ticket por
ticket.

El bloqueo es de modelo: **el estado vive en la orden completa**
(`ordenes.estado`), no por ítem.

```python
# en OrdenItem
estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
# pendiente | preparando | listo | entregado
```

- `ordenes.estado` pasa a ser **derivado** (el mínimo de sus ítems) o se mantiene
  como caché recalculada al mover ítems. Decidir explícitamente y anotarlo en el
  registro de decisiones de `ROADMAP.md`: media docena de sitios leen ese campo
  (cocina, caja, admin, stats, ticketera).
- Endpoint nuevo: `POST /api/orders/despachar-bulk`
  `{plato_nombre | plato_id, cantidad, estado_destino}` → avanza esas N
  porciones en cascada, **de la orden más antigua a la más nueva**, y devuelve
  qué órdenes cambiaron para que la pantalla se actualice sin esperar el poll.
- Bulk mixto: aceptar una lista de líneas en una sola llamada, para tachar
  "2 y 2" de golpe (transacción única, o nada).
- Migración: `ALTER TABLE orden_items ADD COLUMN estado VARCHAR(20) DEFAULT
  'pendiente'`; los ítems históricos heredan el estado de su orden en el mismo
  `_migrar()`.

Tests: despacho parcial (3 de 5 porciones), cascada por antigüedad, bulk mixto
atómico, estado derivado de la orden correcto en cada combinación, y que anular
una orden siga devolviendo el stock exacto vía `movimientos_insumo.orden_id`.

---

## 4. Menores

- **Cintillo de anulada en cocina.** Hoy la orden anulada desaparece de la vista
  y la cocina puede seguir cocinándola. Devolverla en `/api/orders/today` con un
  campo `anulada_en` (timestamp) y que cocina la muestre 60 s con "no preparar".
- **Descuadre de caja como cifra grande.** Solo presentación, pero el signo y la
  magnitud deberían venir separados en la respuesta de `cajaHoy()` en vez de
  reconstruirse en el cliente.
- **Fotos de plato** (`Plato.imagen_url` o archivo servido por el backend): es lo
  que más subiría la conversión del kiosko.
- **Emoji → SVG inline**: solo markup, pero cambia JSX. Unificaría el lenguaje
  icónico (🍳 💵 🪑 ⏱).

---

## Orden sugerido de trabajo

1. §2 (`sale_al_momento` + `entrega`) — es el más chico y no depende de nada.
2. §1 (menú encadenado) — el grande; hacerlo antes de §3 porque cambia la forma
   de los ítems.
3. §3 (estado por ítem + bulks) — el más invasivo en lecturas; con §1 ya cerrado
   se toca una sola vez.
4. §4.

Después de cada uno: `python -m pytest tests/ -q` en backend (94 tests hoy) y
`npm run build` en frontend.
