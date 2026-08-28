# Banco de pruebas de voz — Fase 2

Herramienta **independiente del POS** para decidir si la voz es viable en el ambiente real
del local antes de integrarla (Fase 3). Mide **por separado** las dos mitades del pipeline:

1. **Transcripción (Whisper)**: ¿el texto refleja lo que dijo el cliente? → **WER** contra
   el ground truth que anotas al grabar.
2. **Interpretación (Claude)**: dado el texto, ¿el pedido estructurado es correcto? →
   **match exacto/parcial** contra el pedido esperado que anotas.

Así, si el pipeline falla, sabes dónde: WER alto = problema de micrófono/ruido; WER bajo
pero pedido malo = problema del prompt de interpretación. El intérprete usa el **mismo
diseño** que usará el POS — tool use que devuelve
`{"items": [{"plato_id", "cantidad"}], "no_encontrados": [], "notas": ""}`.

Todo queda en archivos y CSV (sin base de datos, sin UI de producción).

## Define tu umbral ANTES de empezar

Que el resultado del experimento decida, no el entusiasmo. Sugerencia:

- Interpretación exacta **> 85%** → se integra voz en Fase 3.
- **70–85%** → se integra, pero con pantalla de corrección táctil obligatoria antes de
  confirmar.
- **< 70%** → el local se queda solo con táctil (y la inversión de Fase 3 se ahorra).

## Instalación

```bash
cd voz-lab
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # Windows (Linux/macOS: cp .env.example .env)
```

Edita `.env` y pon tus claves:

- `ANTHROPIC_API_KEY` — [console.anthropic.com](https://console.anthropic.com) → API Keys.
  Se usa para la interpretación (modelo por defecto: `claude-opus-5`).
- `OPENAI_API_KEY` — [platform.openai.com](https://platform.openai.com) → API Keys.
  Se usa solo para Whisper (transcripción).

## Uso

### 1. Grabar audios de prueba (grabadora web)

```bash
uvicorn grabadora_web:app --host 0.0.0.0 --port 8001
```

Abre **http://localhost:8001** en la laptop. Flujo por audio: 🎤 Grabar → el cliente habla
→ ⏹ Detener → escuchas el audio para verificar → anotas **lo que realmente dijo** (ground
truth), el **pedido correcto esperado** ("2x lomo saltado, 1x chicha") y **notas de
contexto** ("mucho ruido", "cliente mayor", "habló rápido") → Guardar. El contador muestra
cuántos llevas (meta: 30).

> Nota sobre celulares: el micrófono del navegador solo funciona en orígenes seguros;
> `http://localhost` en la laptop sí, una IP de la red no (salvo el flag
> `chrome://flags/#unsafely-treat-insecure-origin-as-secure`). Para la prueba basta la
> laptop parada donde iría la terminal.

Alternativa por consola (micrófono de la laptop, sin navegador): `python grabadora.py`.

### 2. Evaluar el pipeline completo

```bash
python evaluar.py --menu menu.json
```

Por cada audio: transcribe con Whisper (una sola vez; queda en `transcripciones/`),
interpreta con Claude, calcula WER y match contra tus anotaciones, y mide latencias y costo
estimado. Todo va a **`resultados.csv`** (ábrelo en Excel) y al final imprime el reporte:

```
=== RESULTADOS (32 audios) ===
Transcripción correcta (WER < 10%): 28/32 (87%)
Interpretación correcta (exacta): 25/32 (78%)
Interpretación parcial: 4/32
Fallas de Whisper (texto malo): 4
Fallas de Claude (texto bueno, pedido malo): 3
Latencia promedio total: 3.2 s
Costo promedio por pedido: $0.004
---
Audios fallidos (revisar): 003, 007, 019, 021
```

### 3. Iterar el prompt rápido y barato

```bash
python evaluar.py --solo-interpretacion
```

Re-corre SOLO la interpretación de Claude sobre las transcripciones ya guardadas, sin
volver a pagar Whisper. Es el modo para afinar el prompt de `services/interpreter.py`
contra el mismo set de audios hasta que los resultados cuadren. El menú va cacheado
(prompt caching), así que las corridas repetidas salen más baratas.

Para probar un cambio de menú: edita `menu.json` (o pasa `--menu otro.json`).

## Protocolo de captura sugerido

**No inventes los audios tú solo hablando claro a la laptop** — eso da ~95% de precisión y
una falsa confianza. Graba en servicio real: pídele a clientes de confianza que "pidan al
micrófono" mientras pagan normal, o que los meseros dicten los pedidos que van tomando,
parados donde estaría la terminal.

Graba **mínimo 30 audios reales**: unos 10 en hora tranquila (8:30–10:00) y unos 20 en hora
punta con el ruido real de sala. Varía además:

- **Tipo de cliente**: rápido y seco ("dos lomos y chicha"), dubitativo ("este… me da…
  ¿qué tienen?… ya, un seco porfa"), con correcciones ("un lomo… no, mejor dos"),
  adulto mayor, con jerga o quechuismos locales.
- **Distancia al micrófono**: pegado, a medio metro, a un metro.
- **Casos trampa**: pedir algo que no está en el menú, cantidades en palabras
  ("un par de chichas"), diminutivos ("sequito", "chichita", "agüita").

Los nombres locales y formas de pedir que descubras van directo a los `sinonimos` de
`menu.json` — y en Fase 3, al menú de producción.

## Qué mirar en `resultados.csv`

1. ¿Los `items` coinciden con la columna `esperado`? (exactitud de la interpretación)
2. ¿La `transcripcion` dice lo que realmente se habló? (si falla aquí, es Whisper/micrófono,
   no el prompt)
3. ¿`no_encontrados` captura lo de fuera de menú sin inventar platos?
4. Las `notas` con dudas del modelo señalan qué casos agregar al prompt.

## Estructura

```
voz-lab/
├── grabadora_web.py         # página web de grabación (uvicorn ... --port 8001)
├── grabadora.py             # grabadora alternativa por consola
├── evaluar.py               # Whisper + Claude + métricas → resultados.csv + reporte
├── services/
│   ├── interpreter.py       # el intérprete (se transfiere al POS en Fase 3)
│   └── metricas.py          # WER, parseo del esperado, match, costos
├── menu.json                # menú de prueba con sinónimos por plato
├── tests/                   # tests offline (sin API): python -m pytest tests/ -q
└── .env.example
```

## Fuera de alcance (a propósito)

Sin UI de producción, sin integración con el POS de Fase 1, sin base de datos, sin
detección de silencio ni streaming. Eso llega en Fase 3, cuando este laboratorio demuestre
que la interpretación es confiable.
