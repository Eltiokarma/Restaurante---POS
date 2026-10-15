# Brief para Claude Code: Estudio de rentabilidad del menú en Perú

Contexto para retomar en Claude Code (despliegue en Railway). Todo lo que sigue sale de una sesión en Claude del 15-oct-2026.

## Qué es

Un análisis económico del sector de restaurantes de menú en Perú, para decidir inversiones a largo plazo:
- abrir locales propios (menú popular S/ 7–13 y menú ejecutivo S/ 15–30);
- escalar a una cadena con cocina central y locales satélite.

Alcance: 12 ciudades (Lima Metropolitana, Arequipa, Trujillo, Chiclayo, Piura, Cusco, Huancayo, Juliaca, Puno, Iquitos, Tacna, Ica). La unidad de análisis tiene que bajar de ciudad a **zona** (mercado, centro, universidad, barrio), porque dentro de una ciudad conviven negocios distintos.

Caso de calibración: el restaurante Candela (Juliaca, menú a S/ 11). Sus números son privados (no van en este repo): la app necesita login y no debe exponerlos.

## Qué ya existe (en esta carpeta)

| Archivo | Qué es |
|---|---|
| `data/dataset.json` | Parámetros por ciudad, nacionales, de riesgo y de cocina central, con campos estimados marcados (`est_campos`, `confianza`). 25 fuentes. |
| `docs/informe.md` | Informe del sector: costos, demanda, competencia, riesgos, cocina central, ranking. |
| `docs/research_notes/*.md` | Notas de investigación con todas las URLs. Fuente de verdad para cualquier cifra. |
| `prototypes/rentabilidad-menu.html` | Calculadora de un local (punto de equilibrio, estado de resultados, mapa precio × volumen). |
| `prototypes/rentabilidad-ciudades.html` | Modelo de 12 ciudades: ranking, frontera de precio, ficha editable, Monte Carlo, cocina central. La lógica de cálculo está en el `<script>`: portarla tal cual como referencia. |

## Parámetros regulatorios verificados (no cambiar sin norma nueva)

- IGV reducido restaurantes MYPE: **10.5% en 2026** (8% IGV + 2.5% IPM), **15% en 2027** (12% + 3%). Desde 2028 no hay norma: supuesto 18% general, marcarlo como supuesto. Leyes 31556, 32219, 32387. Requisitos: ventas ≤ 1,700 UIT, ≥ 70% de ingresos de restaurante, sin vinculación económica, no Nuevo RUS.
- Sueldo mínimo: **S/ 1,230 desde 1-oct-2026** (D.S. 015-2026-TR). S/ 1,300 fijado para el 1er semestre de 2027 con fecha pendiente.
- UIT 2026: S/ 5,500.
- Costo laboral microempresa ×1.05, pequeña empresa ×1.27.

## Cómo calcula el modelo actual (portar y testear)

- Ventas netas = precio ÷ (1 + IGV). Informal: IGV 0 y multiplicador laboral 1.0.
- Costo variable por menú = insumos × 1.05 (merma) + descartables (S/ 0.20 popular, 0.35 ejecutivo).
- Personal escalonado: cocina = máx(2, ⌈q/80⌉) popular o ⌈q/55⌉ ejecutivo (el primero es cocinero); mozos = máx(1, ⌈q/70⌉) popular o ⌈q/40⌉ ejecutivo. Formal: nadie bajo el sueldo mínimo; cocinero ≥ sueldo mínimo × 1.06.
- **Gas = gasto fijo mensual** (balones de 45 kg × precio), no por plato. Decisión del usuario.
- Fijos = personal + alquiler (×1.25 en ejecutivo) + gas + servicios + S/ 400 otros (+ S/ 1,500 sueldo del dueño, activado por defecto).
- 26 días al mes. Equilibrio = primer q con utilidad ≥ 0 (barrido 5–600).
- Monte Carlo de 1 año, 2,000 corridas: volumen lognormal (σ 0.20), insumos normal (σ 0.08), precio triangular dentro del rango (±4% si el precio es dato propio), conflicto con probabilidad anual por ciudad que quita 2–8 semanas de contribución.

Valores de referencia para tests de regresión (popular, 2026, formal, 100 menús/día, 5 balones, **sin** sueldo del dueño): equilibrio Lima 57, Arequipa 65, Ica 66, Piura 84, Cusco 86, Trujillo 87, Huancayo 94, Tacna 94, Iquitos 96, Chiclayo 98, Puno 108, Juliaca 138 (este último con el precio estimado de S/ 8, que está mal; ver abajo).

## Qué falta (en orden de prioridad)

1. **Precios observados.** Solo Lima, Cusco y Piura tienen precio de menú observado; el resto es estimado. Juliaca figura a S/ 8 pero Candela cobra S/ 11 y en el centro hay menús a S/ 20. Es la variable que más mueve el ranking.
2. **Volumen de un local nuevo.** El modelo lo recibe como dato. Falta estimar captación por zona y la curva de arranque (meses hasta el volumen estable).
3. **Horizonte largo.** El modelo mira un año. Falta flujo de caja a 10 años con VAN y TIR: arranque, IGV 2026→2027→2028, saltos del sueldo mínimo (~+10% cada 2–3 años), alza del alquiler, reinversión en equipos, impuesto a la renta (Régimen MYPE Tributario), valor residual o traspaso.
4. **Competencia por distrito.** No hay conteo de restaurantes para Juliaca, Puno, Iquitos ni Tacna. Idea: padrón de RUC de SUNAT filtrado por ubigeo. Verificar primero qué campos trae el padrón reducido; si no trae actividad económica, buscar otra vía.
5. **Supervivencia.** No hay tablas peruanas; hoy se usa Brasil (55% a 3 años, 40% a 5) como referencia.
6. **Cocina central:** casi todos sus parámetros son estimados con confianza baja.
7. Reconciliar informe y modelo: el informe asumió personal fijo (3 personas) y el modelo lo escalona, por eso sus equilibrios difieren.

## Qué construir

### Fase 1: Motor y datos
- Paquete Python con el motor (unit economics, equilibrio, frontera, Monte Carlo) portado del prototipo, con tests contra los valores de referencia.
- Postgres en Railway: `ciudades`, `zonas`, `parametros` (valor, fuente, URL, fecha, confianza, si es estimado), `escenarios`. Sembrar desde `dataset.json`. Cada cifra conserva su fuente.
- Flujo de caja a 10 años (VAN, TIR, payback descontado) con la trayectoria regulatoria y la curva de arranque como parámetros.

### Fase 2: Sondeo de campo
- Formulario web para celular (funciona mal de señal: guardar local y sincronizar) para registrar pizarras de menú: ciudad, zona y tipo de zona, ubicación, precio, segmento, qué incluye (entrada, segundo, refresco, postre), foto, fecha y conteo de comensales entre 12:30 y 14:30.
- Meta: 40–60 pizarras por ciudad, dos rondas separadas por 3 meses.
- Agregar por ciudad y zona (mediana, rango) y reemplazar los precios estimados del modelo, marcando la fuente como "sondeo".

### Fase 3: Tablero
- Ranking por ciudad y zona, frontera de precio, mapa precio × volumen, Monte Carlo, flujo a 10 años y cocina central. Reutilizar el diseño de los prototipos.
- Ficha "Candela" privada para calibrar con datos reales.

## Datos que el usuario tiene que pasar (pendientes)

Candela: menús/día promedio, flojo y bueno; días al mes; gasto semanal en insumos; sueldo de cada puesto (cocinero principal, dos ayudantes, mesero, asistente, cajero) y si están en planilla; alquiler, luz y agua; balones de gas al mes y su precio; régimen SUNAT; costo de montar un local igual hoy; tiempo que tardó en llegar a su volumen.

Juliaca: precio del menú por zona (mercado, su cuadra, centro, universidades), menús/día de locales llenos, alquiler fuera del centro (en el centro es S/ 6,000–10,000).

Otras ciudades: precios conocidos o contactos que manden fotos de pizarras.

## Criterios
- Ninguna cifra sin fuente o sin marca de estimado.
- Separar siempre dato observado, estimado y supuesto.
- Montos en soles, escenarios en soles constantes salvo el flujo a 10 años, que puede ir nominal con inflación de 2–2.5%.
