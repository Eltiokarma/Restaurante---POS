# Estudio de rentabilidad del menú en Perú

Proyecto **aparte del POS**: no se despliega con él (el `Dockerfile` del POS
solo copia `backend/` y `frontend/`) y usa **su propia base de datos**. Nunca
escribe en la base del local.

El encargo completo está en [`BRIEF.md`](BRIEF.md). Las cifras salen de
`data/dataset.json` y sus fuentes, de `docs/research_notes/`.

## Qué hay

| Ruta | Qué es |
|---|---|
| `motor/modelo.py` | Estado de resultados de un local, punto de equilibrio y frontera de precio (portado del prototipo). |
| `motor/montecarlo.py` | Monte Carlo de un año, con el **mismo generador aleatorio** que el HTML: da exactamente sus mismos números. |
| `motor/central.py` | Cocina central con satélites (parámetros de confianza baja). |
| `motor/flujo.py` | Flujo de caja a 10 años por régimen (informal, Nuevo RUS, RER, MYPE): IGV por año, sueldo mínimo, inflación, curva de arranque, VAN, TIR y recupero. |
| `motor/personal.py` | Planilla propia, una fila por persona (cada una con su sueldo o jornal), pago mensual, quincenal o por día, turno día/noche, y cuándo sale la plata en el mes. |
| `motor/sensibilidad.py` | Tornado (qué número mueve más la utilidad), cuánto aguanta cada uno antes de perder y tabla precio × menús/día. |
| `motor/recetas.py` | Costeo por receta con merma por insumo, margen por plato y del menú, ingeniería de menú (estrella, caballito, rompecabezas, perro) y peso de cada insumo en las compras. |
| `data/arquetipos.json` | Catálogo de restaurantes tipo (dueña que cocina, familia sin sueldos, inversor, dueño ausente, puesto de mercado, Nuevo RUS, ejecutivo, día y noche, exitoso de referencia). Se cargan como escenarios al arrancar, sin pisar los editados. |
| `reporte/` | Generador del ensayo en PDF (XeLaTeX + matplotlib): `datos.py` calcula y guarda `salida/datos.json`, `figuras.py` dibuja, `ensayo.py` arma y compila. La salida no se sube (incluye datos de Candela). |
| `motor/barrido.py` | Corridas sistemáticas: barrido de decisiones (precio × porción × mezcla de segundos × turno noche, cada una bajo varias elasticidades de demanda, ordenadas por su peor caso) y prueba de estrés (golpes uno por uno y todos juntos). Las corre el servicio en segundo plano y las guarda en `corridas`. |
| `web/` | El panel (React + Vite): simulador del mes con barras, flujo a 10 años y escenarios guardados. |
| `motor/bd.py` | Base de datos: `ciudades`, `zonas`, `parametros` (cada cifra con origen, fuente, fecha y confianza), `fuentes` y `escenarios`. |
| `tests/` | Regresión: los 12 equilibrios del brief y 96 combinaciones contra el prototipo (`referencia_prototipo.json`, generado corriendo su JavaScript con Node). |
| `prototipos/` | Las calculadoras HTML originales (referencia de cálculo y de diseño). |

## Usarlo

```bash
cd estudio
pip install -r requirements.txt
python -m pytest tests/ -q            # 145 tests
python -m motor.bd                    # crea y siembra la base (SQLite local: estudio.db)
DATABASE_URL=postgres://... python -m motor.bd   # lo mismo en el Postgres de Railway
```

```python
from motor import Escenario, cargar_dataset, equilibrio, local_de_ciudad, simular

data = cargar_dataset()
juliaca = next(c for c in data["ciudades"] if c["id"] == "juliaca")
local = local_de_ciudad(juliaca, precio=11)          # corrección: precio observado
esc = Escenario(segmento="popular", anio=2026, formal=True, balones=5)
equilibrio(local, esc, data["nacional"])             # menús/día para no perder
simular(local, esc, data["nacional"], data["riesgo"], q_ref=80)
```

## Servicio en Railway (aparte del POS)

`api.py` es una API pequeña (FastAPI) que corre como **su propio servicio**
en el mismo proyecto de Railway, junto a su base Postgres. Al arrancar crea
las tablas y siembra `dataset.json` usando la dirección **interna** de la
base, así la base no necesita acceso público.

Configuración del servicio en Railway:
- **Source**: este mismo repo; **Root Directory** = `/estudio` (usa el
  `Dockerfile` y `railway.json` de esta carpeta).
- **Variables**: `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (referencia a
  la base) y `ESTUDIO_TOKEN` = una clave larga (la pide todo menos `/salud`,
  en el header `X-Token`).
- **Networking**: generar un dominio público (HTTPS).

En la raíz del dominio está **el panel**: se entra con el token y se mueven
las barras. El `Dockerfile` lo compila (Node) y FastAPI lo sirve: no hace
falta Vercel ni otro servicio.

Endpoints (todos bajo `/api`): `GET /api/salud` (sin token), `GET /api/ciudades`,
`GET /api/parametros`, `POST /api/zonas`, `POST /api/parametros` (cargar
cifras de sondeo o propias con su fuente), `POST /api/calcular` (equilibrio,
frontera de precio, mes a q, Monte Carlo y curva de utilidad; acepta
correcciones de insumos, alquiler, sueldos, gas y servicios),
`POST /api/flujo` (10 años del régimen elegido y comparación de los cuatro),
`POST /api/sensibilidad`, `/api/insumos` y `/api/platos` (CRUD de recetas),
`GET /api/platos/analisis`, `POST /api/comparar` (métricas de varios escenarios lado a lado) y
`GET/POST/DELETE /api/escenarios` (juegos de barras guardados con nombre) y `POST/GET/DELETE /api/corridas` (cálculos largos en segundo plano).

Panel en desarrollo: `uvicorn api:app --port 8001` en `estudio/` y
`npm run dev` en `estudio/web/`.

## Ensayo en PDF

Requiere `xelatex` (texlive-xetex, texlive-lang-spanish, lmodern) y `pip install matplotlib`.

```bash
cd estudio
ESTUDIO_URL=https://<servicio>.up.railway.app ESTUDIO_TOKEN=... python -m reporte.ensayo
# → reporte/salida/ensayo.pdf (sin ESTUDIO_URL sale sin el caso Candela)
```

## Origen de cada cifra

`parametros.origen` es uno de: `observado`, `estimado`, `supuesto`, `sondeo`
(pizarras de campo) o `propio` (datos de Candela). Lo de `sondeo` y `propio`
se carga en el ámbito más específico (zona) y manda sobre lo de la ciudad;
volver a sembrar el dataset no lo borra.

## Privacidad

Los números de Candela son privados: **no van en este repo**. Se cargarán
directo en la base del estudio (origen `propio`), que vive aparte.

## Pendiente (orden del brief)

1. Cargar los datos propios de Candela (origen `propio`) y sus recetas.
2. Recetas e insumos de Candela: se copiaron una vez del POS (receta por
   porción, costo de referencia y ventas de 60 días). Falta sincronizarlo solo
   y traer del POS las ventas por plato (popularidad real para la ingeniería de
   menú) en vez de escribirlas a mano.
3. Precios observados por zona (formulario de sondeo, Fase 2).
4. Arrastre de pérdidas en el MYPE y valor residual del local en el flujo.
5. Organización de la cocina: hecho en `motor/cocina.py` con las tareas de
   `data/cocina.json` (Gantt de la mañana, cola del almuerzo con la llegada de
   pedidos del POS, capacidad por forma de trabajar). Los tiempos de las tareas
   y lo que la organización recorta del desorden son supuestos: falta una semana
   de registro en la cocina de Candela para reemplazarlos.
6. Capítulo 2 del ensayo (ciudades): actualizar la base con lo de
   `investigacion/ciudades.md` (gas por departamento, factor de altura, sueldos,
   alquileres), modelar la competencia como tope de precio y hacer un sondeo de
   pizarras.
7. Otros formatos de comida: chicharronería, pollería de pollo frito, cevichería
   y carrito sanguchero, con sus recetas, planilla y venta, comparados con el menú.
   El primero ya está: el autoservicio criollo (`motor/autoservicio.py`, supuestos
   en `data/autoservicio.json`), con la planilla calculada puesto por puesto para
   cada venta. Falta contrastarlo con un local real: flujo de gente de la
   ubicación, tiempo de cobro con Yape y menús por hora de una línea de baño maría.
