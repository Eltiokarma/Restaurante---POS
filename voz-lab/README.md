# Laboratorio de pedidos por voz — Fase 2

Banco de pruebas **independiente del POS** para validar el pipeline de voz antes de
integrarlo (Fase 3): se graban audios reales de clientes pidiendo, Whisper los transcribe y
Claude interpreta la transcripción con el **mismo diseño** que usará el POS — tool use que
devuelve `{"items": [{"plato_id", "cantidad"}], "no_encontrados": [], "notas": ""}`.

Todo queda en archivos y CSV (sin base de datos, sin UI): la meta es medir qué tan bien se
entiende a un cliente peruano real y afinar el prompt barato y rápido.

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

### 1. Grabar audios de prueba

```bash
python grabadora.py
```

Enter para empezar a grabar, el "cliente" habla su pedido, Enter para parar. Cada audio se
guarda como `audios/001.wav`, `002.wav`, … y puedes anotar qué se dijo y qué pedido se
esperaba (queda en `audios/metadata.csv`, sirve para comparar después).

### 2. Evaluar el pipeline completo

```bash
python evaluar.py
```

Transcribe cada audio con Whisper (una sola vez: las transcripciones se guardan en
`transcripciones/`) y le pasa cada transcripción a Claude. El resultado queda en
**`resultados.csv`** (ábrelo en Excel): transcripción, items interpretados, lo que no estaba
en el menú, notas del modelo y el pedido esperado que anotaste.

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

Graba **mínimo 30 audios reales** antes de sacar conclusiones, variando:

- **Hora**: con ruido de hora punta (12–1 pm) y en horas tranquilas.
- **Tipo de cliente**: rápido y seco ("dos lomos y chicha"), dubitativo ("este… me da…
  ¿qué tienen?… ya, un seco porfa"), con correcciones ("un lomo… no, mejor dos"),
  adulto mayor, con jerga.
- **Distancia al micrófono**: pegado, a medio metro, a un metro.
- **Casos trampa**: pedir algo que no está en el menú, cantidades en palabras
  ("un par de chichas"), diminutivos ("sequito", "chichita", "agüita").

## Qué mirar en `resultados.csv`

1. ¿Los `items` coinciden con la columna `esperado`? (exactitud de la interpretación)
2. ¿La `transcripcion` dice lo que realmente se habló? (si falla aquí, es Whisper/micrófono,
   no el prompt)
3. ¿`no_encontrados` captura lo de fuera de menú sin inventar platos?
4. Las `notas` con dudas del modelo señalan qué casos agregar al prompt.

## Estructura

```
voz-lab/
├── grabadora.py             # graba audios/NNN.wav + metadata.csv
├── evaluar.py               # Whisper + Claude → resultados.csv
├── services/interpreter.py  # el intérprete (se transfiere al POS en Fase 3)
├── menu.json                # menú de prueba con sinónimos por plato
├── tests/                   # tests offline (sin API): python -m pytest tests/ -q
└── .env.example
```

## Fuera de alcance (a propósito)

Sin UI de producción, sin integración con el POS de Fase 1, sin base de datos, sin
detección de silencio ni streaming. Eso llega en Fase 3, cuando este laboratorio demuestre
que la interpretación es confiable.
