# POS de Auto-Atención Táctil — Restaurante de Menú Peruano (Fase 1)

Sistema de auto-atención donde los clientes arman su propio pedido tocando la pantalla de una
terminal (laptop o tablet) en sala. El sistema toma el pedido, lo confirma con una ventana de
cancelación de 30 segundos, imprime el ticket con el número de orden y lo envía a la cola de
cocina. **El pago se hace en la caja física**, mostrando el ticket.

- **Vista de cliente** (`/`): pantalla táctil para armar el pedido, sin login.
- **Vista de cocina** (`/cocina`): cola de órdenes con estados (pendiente → preparando → listo → entregado).
- **Vista de admin** (`/admin`): menú del día, órdenes, log de cancelaciones y configuración (con contraseña).

> **Preparado para voz (Fase 3):** la voz será solo "otra manera de llenar el carrito". El módulo
> `backend/app/services/voice.py` es un stub vacío donde se enchufará Whisper + Claude API. El
> carrito, la confirmación, la ventana de cancelación, el ticket y la cola de cocina son agnósticos
> a cómo se llenó el pedido.

## Stack

- **Backend:** Python 3.11+ / FastAPI / SQLite (SQLAlchemy)
- **Frontend:** React (Vite) + TypeScript
- **Impresión:** HTML imprimible vía `window.print()` (impresora del sistema, ~80mm)

---

## Instalación paso a paso

### Requisitos previos

1. **Python 3.11 o superior** — [python.org/downloads](https://www.python.org/downloads/). En Windows, marca "Add Python to PATH" al instalar.
2. **Node.js 18 o superior** (incluye npm) — [nodejs.org](https://nodejs.org/).
3. Google Chrome o Microsoft Edge en la terminal táctil.

### 1. Backend

```bash
cd backend

# Crear y activar entorno virtual
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Crear tu archivo de configuración
cp .env.example .env        # Windows: copy .env.example .env
# Edita .env y cambia ADMIN_PASSWORD por una contraseña tuya

# Crear la base de datos con el menú de ejemplo
python seed.py
```

### 2. Frontend

```bash
cd frontend
npm install
```

---

## Cómo correr el sistema

### Modo producción (recomendado para el local): un solo comando

Compila el frontend y levanta todo en el puerto 8000:

```bash
./scripts/iniciar.sh      # Linux / macOS
scripts\iniciar.bat       # Windows (también funciona con doble clic)
```

| Pantalla | URL |
|---|---|
| Terminal de cliente | http://localhost:8000/ |
| Cocina | http://localhost:8000/cocina |
| Administración | http://localhost:8000/admin |
| Estación de impresión | http://localhost:8000/ticketera |

Desde otras máquinas de la red: `http://IP-DE-LA-LAPTOP:8000/...`

### Modo desarrollo (para trabajar en el código)

Necesitas **dos terminales abiertas**:

**Terminal 1 — backend (API):**

```bash
cd backend
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

Luego abre en el navegador:

| Pantalla | URL |
|---|---|
| Terminal de cliente | http://localhost:5173/ |
| Pantalla de cocina | http://localhost:5173/cocina |
| Administración | http://localhost:5173/admin |
| Estación de impresión | http://localhost:5173/ticketera |

Si la pantalla de cocina o la terminal es otra computadora/tablet en la misma red, usa la IP
de la máquina que corre el sistema, por ejemplo `http://192.168.1.50:5173/cocina`.

## Terminal en tablet (y cualquier impresora)

La terminal del cliente puede ser **cualquier dispositivo con navegador**: laptop, PC o
tablet (Android/iPad). La tablet solo abre la URL del sistema; no se instala nada en ella.
La impresión tiene dos modos (se elige en **/admin → Configuración → "¿Dónde se imprimen
los tickets?"**):

- **"En la terminal del cliente"** (default): la pantalla donde pide el cliente imprime.
  Úsalo cuando la terminal es la misma PC/laptop que tiene la impresora conectada.
- **"Estación de impresión"**: para terminales tablet. Los tickets NO se imprimen en la
  tablet: quedan en una cola y los imprime la computadora que tenga abierta la página
  **/ticketera** (la misma laptop que corre el sistema, con la impresora conectada).

Montaje típico con tablet:

1. La laptop corre backend + frontend y tiene la impresora conectada (cualquier impresora
   con driver del sistema: térmica, láser o de tinta).
2. En la laptop abre Chrome con impresión silenciosa apuntando a la ticketera:
   ```
   chrome --kiosk-printing http://localhost:5173/ticketera
   ```
   y déjala abierta (muestra "Esperando pedidos…", la cola y cuántos lleva impresos).
3. En `/admin → Configuración` elige "Estación de impresión" y guarda.
4. En la tablet abre `http://IP-DE-LA-LAPTOP:5173/` a pantalla completa. Listo: la tablet
   toma pedidos y los tickets salen solos por la impresora de la laptop.

Si la ticketera estuvo cerrada un rato, al abrirla imprime lo pendiente; también tiene un
botón para descartar la cola sin imprimir. Las reimpresiones (botón de la pantalla final y
🖨️ en admin) también salen por la estación cuando ese modo está activo.

## Cómo cargar el primer menú del día

1. `python seed.py` ya deja un menú de ejemplo cargado (sopa criolla, lomo saltado, ají de
   gallina, seco de res y chicha morada).
2. Para el menú real: entra a **http://localhost:5173/admin**, pon tu contraseña (la del `.env`)
   y en la pestaña **"Menú del día"**:
   - **+ Agregar plato** para crear platos nuevos (nombre, categoría, precio en S/).
   - **"Cargar menú de ayer"** duplica el último menú guardado para ajustarlo rápido cada mañana.
   - **"Ver catálogo histórico"** trae todos los platos que alguna vez creaste, para activar los de hoy.
   - Marca/desmarca **"Disponible hoy"** y pulsa **💾 Guardar menú del día**.
3. **¿Se agotó un plato a mitad de servicio?** Desmarca "Disponible hoy" y guarda: desaparece de
   la terminal en el siguiente refresco (máximo 30 segundos).

## Cómo poner la terminal en modo kiosko (Chrome)

Opción rápida: abre Chrome en `http://localhost:5173/` y pulsa **F11** (pantalla completa).

Opción kiosko real (sin barras, ni pestañas, ni botón de cerrar):

```bash
# Windows (acceso directo con esta ruta de destino):
"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --incognito http://localhost:5173/

# Linux:
google-chrome --kiosk --incognito http://localhost:5173/
```

Consejos:
- Crea un acceso directo en el escritorio con ese comando y ábrelo al empezar el día.
- Para salir del modo kiosko: **Alt+F4** (Windows) o **Ctrl+W**.
- Desactiva el protector de pantalla y la suspensión de la laptop/tablet en la configuración de energía.

## Cómo conectar la impresora del sistema

Esta fase imprime el ticket con la impresora **normal del sistema operativo** (la que uses por
defecto), vía el diálogo de impresión del navegador:

1. Instala/conecta tu impresora en Windows/macOS/Linux como cualquier impresora (si es térmica
   de 80mm, usa el driver del fabricante; casi todas traen driver de Windows).
2. Ponla como **impresora predeterminada** del sistema.
3. En Chrome, haz una impresión de prueba (Ctrl+P) y en el diálogo:
   - Selecciona la impresora.
   - En "Más ajustes", margen **Ninguno** y tamaño de papel de 80mm si tu driver lo ofrece.
4. Al confirmarse una orden, el sistema dispara `window.print()` automáticamente y solo se
   imprime el ticket (el resto de la interfaz queda oculta por CSS de impresión).
5. Para que no aparezca el diálogo en cada orden, arranca Chrome en modo kiosko con impresión
   directa: agrega el flag `--kiosk-printing` al comando del modo kiosko. Con ese flag, Chrome
   imprime directo en la impresora predeterminada sin preguntar.

```bash
"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --kiosk-printing --incognito http://localhost:5173/
```

### Reimprimir un ticket

Si un ticket no salió (papel atascado, impresora apagada):

- **En la terminal**: mientras se muestra la pantalla "ORDEN #XXX" hay un botón **"🖨️ Imprimir de nuevo"**.
- **Después**: en **/admin → Órdenes de hoy**, cada orden tiene un botón **🖨️** que vuelve a imprimir su ticket.

---

## Estructura del proyecto

```
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI, CORS, routers
│   │   ├── auth.py            # login admin (token simple, 12h)
│   │   ├── db.py              # SQLite + SQLAlchemy
│   │   ├── models.py          # platos, ordenes, orden_items, cancelaciones, config
│   │   ├── routes/            # menu, orders, cancellations, config, admin
│   │   └── services/
│   │       ├── orders.py      # correlativo diario + snapshot de precios
│   │       └── voice.py       # STUB — Whisper + Claude API en Fase 3
│   ├── requirements.txt
│   ├── seed.py                # BD + menú de ejemplo + config inicial
│   └── .env.example
├── frontend/
│   └── src/
│       ├── pages/             # Cliente, Cocina, Admin
│       ├── components/        # TarjetaPlato, BarraCarrito, CountdownCancel, Ticket
│       ├── hooks/             # useCarrito, useInactividad
│       └── api.ts
└── README.md
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/menu/today` | Menú activo de hoy |
| PUT | `/api/menu/today` | Actualizar menú del día (admin) |
| GET | `/api/menu/catalog` | Catálogo histórico de platos (admin) |
| GET | `/api/menu/previous` | Menú del último día de servicio anterior (admin) |
| POST | `/api/orders` | Guardar orden confirmada; devuelve número del día |
| GET | `/api/orders/today` | Órdenes de hoy (cocina y admin) |
| PATCH | `/api/orders/{id}/status` | Avanzar estado |
| POST | `/api/cancellations` | Registrar cancelación en el log |
| GET | `/api/cancellations/today` | Log de cancelaciones (admin) |
| GET / PUT | `/api/config` | Configuración del local |
| POST | `/api/admin/login` | Login de admin |

## Desplegar en la nube (Railway) — opcional

El proyecto incluye un `Dockerfile` listo para Railway (o cualquier plataforma que corra
contenedores). Pasos en Railway:

1. **New Project → Deploy from GitHub repo** → elige este repositorio. Railway detecta el
   `Dockerfile` y construye solo.
2. En el servicio, pestaña **Variables**: agrega `ADMIN_PASSWORD` con tu contraseña.
3. Pestaña **Settings → Volumes**: agrega un volumen montado en **`/data`** (ahí vive la
   base de datos SQLite; sin volumen, se borra en cada despliegue).
4. **Settings → Networking → Generate Domain** para obtener la URL pública.
5. El menú inicial se carga desde `/admin` (el seed es opcional; las tablas se crean solas).

**Piénsalo dos veces antes de operar el local desde la nube:**

- **Si se cae el internet del restaurante, el POS se detiene.** Corriendo en la laptop del
  local (modo LAN), sigue funcionando aunque no haya internet.
- **Cocina, terminal y ticketera no tienen contraseña por diseño** (son pantallas de una red
  local privada). En una URL pública, cualquiera que la conozca puede ver la cola de cocina o
  crear órdenes. Si algún día se opera en nube en serio, hay que agregar autenticación a esas
  vistas primero (está anotado en el roadmap).
- La impresión no cambia: la ticketera o la terminal imprimen desde el navegador del local
  igual que siempre, apuntando a la URL de Railway.

Para lo que sí sirve hoy: **demos** (mostrarle el sistema a alguien sin instalar nada) y
**monitoreo remoto** (ver el Resumen de ventas desde tu casa).

## Tests y CI

El backend tiene una suite de tests (correlativo diario, snapshot de precios, cola de
impresión, auth, menú, cancelaciones, configuración):

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

GitHub Actions (`.github/workflows/ci.yml`) corre los tests y el build del frontend en cada
push a `main` y en cada pull request.

## Copia de seguridad

La base de datos (`backend/pos.db`) guarda todas las ventas. **Mientras el servidor corre,
se respalda solo**: refresca `backend/backups/pos-AAAA-MM-DD.db` cada 30 minutos (una copia
por día, conserva las últimas 60). Ante una falla del disco se pierde como máximo media hora.

Para forzar una copia manual (por ejemplo al cierre, o hacia un USB):

```bash
cd backend
python backup.py
```

## Detalles de comportamiento importantes

- **La orden no existe hasta que pasa la ventana de cancelación.** El carrito vive solo en el
  frontend; recién al terminar la cuenta regresiva (o con "Confirmar ahora") se guarda en BD,
  se asigna el número correlativo del día y aparece en cocina.
- **Cancelaciones:** si el cliente cancela en la ventana de 30s, se registra en un log aparte
  (visible en admin) para que puedas medir si algo del flujo confunde.
- **Números de orden:** correlativo que reinicia cada día (#001, #002…), calculado con la zona
  horaria de Lima.
- **Precios congelados:** cada orden guarda nombre y precio del plato al momento de pedir; si
  mañana cambias precios, el histórico no se altera.
- **Inactividad:** si alguien deja un pedido a medias, a los 90 segundos (configurable) aparece
  "¿Sigues ahí?" con 15 segundos de gracia y luego la terminal se limpia sola.
- **Sin conexión:** si el backend no responde al confirmar, se muestra "Error de conexión,
  intenta de nuevo" y el carrito no se pierde.

## Fuera de alcance en esta fase

Sin voz (solo el stub), sin pagos integrados (Yape/tarjeta), sin driver térmico ESC/POS,
sin control de stock, sin WebSockets, sin app nativa ni multi-local.
