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
| `motor/bd.py` | Base de datos: `ciudades`, `zonas`, `parametros` (cada cifra con origen, fuente, fecha y confianza), `fuentes` y `escenarios`. |
| `tests/` | Regresión: los 12 equilibrios del brief y 96 combinaciones contra el prototipo (`referencia_prototipo.json`, generado corriendo su JavaScript con Node). |
| `prototipos/` | Las calculadoras HTML originales (referencia de cálculo y de diseño). |

## Usarlo

```bash
cd estudio
pip install -r requirements.txt
python -m pytest tests/ -q            # 114 tests
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

## Origen de cada cifra

`parametros.origen` es uno de: `observado`, `estimado`, `supuesto`, `sondeo`
(pizarras de campo) o `propio` (datos de Candela). Lo de `sondeo` y `propio`
se carga en el ámbito más específico (zona) y manda sobre lo de la ciudad;
volver a sembrar el dataset no lo borra.

## Privacidad

Los números de Candela son privados: **no van en este repo**. Se cargarán
directo en la base del estudio (origen `propio`), que vive aparte.

## Pendiente (orden del brief)

1. Flujo de caja a 10 años (VAN, TIR, payback descontado) con la trayectoria
   regulatoria y la curva de arranque.
2. Precios observados por zona (formulario de sondeo, Fase 2).
3. Tablero (Fase 3) con la ficha privada de Candela.
