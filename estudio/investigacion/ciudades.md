# Investigación por ciudad: insumos, precio de menú, competencia, sueldos, altura y alquiler

Fecha de la investigación: 17-oct-2026. Base: `estudio/data/dataset.json` (12 ciudades: Lima, Arequipa,
Trujillo, Chiclayo, Piura, Cusco, Huancayo, Juliaca, Puno, Iquitos, Tacna, Ica).

**Escala de fiabilidad** usada abajo:
- **A**: fuente oficial con metodología (MINEM/Osinergmin, INEI, MIDAGRI).
- **B**: prensa que visita mercados (una foto de un día y de un puesto) o un agregador con n declarado.
- **C**: blogs, guías de viaje o avisos sueltos.
- **Est.**: cálculo o inferencia propia.

**Bloqueos encontrados**: SISAP/MIDAGRI (precios mayoristas regionales) no respondió (timeout).
Expatistan, Indeed, Computrabajo y Properati devuelven 403 a las descargas directas; sus cifras salen
de los fragmentos del buscador. El PDF de PRODUCE sobre el sector restaurantes (abr-2026) devolvió 503.

---

## 1. Resumen: lo que más cambiaría el estudio

1. **La hipótesis "en la sierra las verduras son 30% más baratas" NO se sostiene para un restaurante
   urbano.** En las visitas a mercados de mar-2026, la papa y la cebolla en Juliaca y Arequipa cuestan
   lo mismo o poco menos que en Lima: papa S/ 2.0–2.5 y cebolla S/ 2.0–2.5 frente a un mayorista de
   Lima de S/ 1.8–2.3. Lo que sube en la sierra es lo que viene de la costa o de la selva:
   - **arroz**: S/ 4–5/kg en Puno, Juliaca y Arequipa frente a S/ 3 en Piura e Iquitos (+35–65%);
   - **limón**: S/ 4–6/kg en Puno y Juliaca frente a S/ 1.5 en el mayorista de Lima (2.5–4×);
   - **pollo**: S/ 11.5–13 frente a ~S/ 12 en Lima, es decir igual o más caro. En nov-2025, Cusco
     estaba a S/ 11 cuando la costa estaba a S/ 8–9 (+25–35%).

   Conclusión: **el costo de insumos de un menú en Juliaca o Puno debería ser ≥ el de Lima, no menor.**
   Hoy el dataset pone `insumos_popular` Juliaca 4.2 y Puno 4.4 frente a Lima 4.4: es razonable, y se
   podría subir Puno a 4.5.
2. **El gas en altura cuesta más por menú por dos efectos que se suman.** El balón es entre −1% y
   +10% más caro que en Lima en la sierra y el norte, y +42% en Iquitos (MINEM, ago-2026). Además se
   consume más por la altura: estimo **+25–60% de GLP en Juliaca, Puno, Cusco y Huancayo** si no se
   usa olla a presión, y **+10–20%** con olla a presión en sopas, menestras y guisos. En una cocina
   con GLP en balón de 45 kg es la diferencia de costo más grande que encontré por ciudad.
3. **El balón ya no está en el precio de enero de 2026.** El `gas_balon45` del dataset sale de Facilito
   de enero de 2026 (Lima 185). Después de la crisis de Camisea, el balón de 45 kg en Lima está en
   ~S/ 230 (may-2026) y el de 10 kg sigue en ~S/ 49–50 (ago-2026, +8–11% sobre enero). Hay que subir
   todos los `gas_balon45` entre +10% y +25%.
4. **Los precios del menú ejecutivo del dataset coinciden con Expatistan** (relación con Lima de
   0.62–0.81). No hay ninguna fuente nueva para el menú popular de Juliaca, Puno, Trujillo, Chiclayo,
   Huancayo, Tacna ni Ica: sigue siendo la variable más débil del estudio.
5. **El alquiler de Trujillo parece sobrestimado.** El dataset pone S/ 45/m², pero los avisos de 2026
   están entre S/ 18 y S/ 28/m². En Arequipa, Properati da S/ 38/m² (set-2026; el dataset pone 35) y
   en Ica S/ 20/m² (jun-2026; el dataset pone 20).
6. **En Juliaca la brecha de sueldos es fuerte.** El ingreso laboral promedio es S/ 1,322, −46% frente
   a Lima (S/ 2,433). Con informalidad de 82%, un ayudante informal probablemente cobra menos de la RMV.
   En la sierra se paga menos, no más, salvo en Cusco, donde el turismo presiona hacia arriba.

---

## 2. Tabla por ciudad (hallazgos con números)

Abreviaturas: LR = La República (visita a mercados); MINEM = "Precios de combustibles líquidos y GLP
a nivel usuario final" al 20-08-2026 (datos de Osinergmin), promedio departamental del balón de
10 kg en locales de venta; Fac. = Facilito vía preciocombustible.com (registros de ene-2026, mediana
de locales); Exp. = Expatistan, "basic lunchtime menu incl. drink, business district" (equivale a un
menú ejecutivo).

| Ciudad | Insumos observados (S/ por kg salvo que se indique) | GLP 10 kg: MINEM ago-26 (vs Lima) | GLP 45 kg: Fac. ene-26 → est. hoy | Menú observado | Alquiler local | Ingreso / sueldos |
|---|---|---|---|---|---|---|
| **Lima** | Mayorista GMML 8-oct-26: papa canchán 2.10, papa única 1.83, cebolla roja 2.25, zanahoria 1.65, tomate 3.33, limón 1.47, ajo 3.5–4.5 (A). Pollo: ~12.06 a inicios de 2026 y >12 en mar-26 (B); INEI jul-26: 11.23 (A) | 50.14 (base) | 185 → **~205–230** (nacional may-26: 230, B) | Popular S/ 12→14 en mercado de Magdalena (mar-26, B); "promedio S/ 15, podría ir a 16–17" (Expreso, B). Exp.: S/ 25–26 (set-26) | Lima Cercado S/ 50/m² (Properati, jun-26, B) | Ingreso S/ 2,433 (INEI, oct-24 a set-25, A) |
| **Arequipa** | 13-mar-26 (Puerta Verde): pollo 11.50, papa 2.00, cebolla 2.50, arroz 5.00, limón 3–4 (B). 27-mar-26 (FEPA): pollo 11.90, papa 4.00, cebolla 1.00, arroz 5.00 (B). Ago-26: pollo 10.50, res 19.80 (Correo, B). Tomate en súper 6.90 (oct-26, B) | 52.33 (+4%) | 200 → ~215 | Exp.: S/ 21 (set-25). Picantería: plato S/ 20–40 (C) | **S/ 38/m²** (Properati set-26, +16.6% m/m, B) | Ingreso S/ 2,279 (A). Avisos de cocinero S/ 1,700–2,500 (Computrabajo, C) |
| **Trujillo** | Nov-25 (Los Portales): pollo 7 (dudoso), cebolla 2–2.50, papa 1.20–1.50, arroz 3–4 (B) | 52.33 (+4%) | 205 → ~215 | Exp.: S/ 19 (jun-26) | Avisos: 130 m² S/ 2,400 (S/ 18/m²); 92 m² S/ 2,600 (S/ 28/m²); 280 m² S/ 7,500 (S/ 27/m²) (C) | Ingreso > S/ 2,000 (A, sin cifra exacta) |
| **Chiclayo** | 13-mar-26 (Antenor Orrego): pollo 11.80, papa 3.00, cebolla 3.00, arroz 3.20–4.40, limón 3.50 la cuartilla (B). Nov-25: pollo 8–8.30, res 20 (B) | 51.16 (+2%) | 210 → ~210 | Exp.: S/ 18 (nov-25) | Sin dato nuevo | Ingreso S/ 1,654 (A) |
| **Piura** | 13-mar-26: pollo 11.20–12, papa 2.50, cebolla 1.50–2.50, arroz 3.00, limón 1.50 la cuartilla (B). 27-mar-26: pollo 12, papa 2, cebolla 2, arroz 2.80 (B). Nov-25: pollo 8.30–9, res 16 (B) | 55.22 (+10%) | 220 → ~225 | Sin dato nuevo (el dataset usa un TikTok de S/ 10) | Sin dato nuevo | Ingreso < S/ 2,000 (A) |
| **Cusco** | Nov-25 (Ttito, Wanchaq): pollo 11, res 18, cebolla 2, tomate 4, arveja 4, arroz 4.50 (B) | 54.88 (+9%) | 230 → ~225–235 | Exp.: S/ 21 (jul-26). Menú de mercado S/ 10–20 (guías 2026, C) | Sin dato agregado | Ingreso > S/ 2,000 (A). Avisos S/ 1,025–3,000 (hoteles, C) |
| **Huancayo** | Sin dato 2026. Nota de ~feb-26: pollo 10.50 en el mayorista y 9 en puestos; papa yungay/mariva 1.80–2.00 en el mayorista (Correo, B/C, fecha incierta) | 49.85 (−1%) | 192 → ~205 | Exp.: S/ 16 (set-26) | Avisos de S/ 8–25/m² (Nuroa, C); uno de USD 10/m² | Ingreso < S/ 2,000 (A). Avisos de cocinero S/ 1,550–1,850 (C) |
| **Juliaca** | 13-mar-26 (Mercado Dominical): pollo 11.50, papa 2.50, cebolla 2.00, arroz 4.00, limón 4.00 (B) | 53.80 (+7%) dpto. Puno | 220 → ~220–235 | **Ningún dato** de menú de restaurante (solo "La Kasa, desde S/ 20" en TikTok, C) | Sin avisos de locales | **Ingreso S/ 1,322 (−46% vs Lima)** (A) |
| **Puno** | 27-mar-26 (Laykakota): pollo 13, papa 3, cebolla 3, arroz 5, limón 6, huevo 14 la plancha (B). Nov-25 (Central): pollo 9, res 19, tomate 4, cebolla 2.50, papa 2.50, arroz 5, limón 4.50 (B) | 53.80 (+7%) | 245 (1 registro) → ~235–245 | Sin dato nuevo | 200 m² cerca de la Plaza Pino a S/ 14,000 (S/ 70/m², zona turística, C) | Sin cifra (INEI no la publica en la nota) |
| **Iquitos** | 27-mar-26 (Belén): pollo 13, papa 3.50, cebolla 2, arroz 3, limón 3.50 (B). Nov-25: pollo 9.50, res 16, arroz 3 (B) | **71.26 (+42%)** | Sin balón de 45 kg; 10 kg a 70–73 → est. ~290 | Blogs: S/ 5–12 el económico y S/ 15–20 el ejecutivo (2022 o antes, C) | Sin dato | Ingreso < S/ 2,000 (A) |
| **Tacna** | Nov-25 (Mayorista Grau): pollo 8.80, res 18, papa 2, arroz 4.80 (B) | 53.25 (+6%) | 210 → ~220 | Exp.: S/ 17 (jun-26, n=7) | Avisos de S/ 1,200–8,000/mes (Properati, C) | Ingreso < S/ 2,000 (A) |
| **Ica** | Sin dato de mercado | 50.14 (0%) | 217 → ~205–220 | Exp.: S/ 21 (fecha no clara, C) | **S/ 20/m²**, valor medio S/ 4,000 (Properati jun-26, B) | Ingreso > S/ 2,000 (A) |

Nota sobre el GLP: "est. hoy" = precio MINEM del balón de 10 kg × 4.5 × 0.91. El 0.91 es el
descuento por kg del balón de 45 kg frente al de 10 kg que se observa en Lima en enero (185/45 vs
45/10). En Lima, la cifra de prensa de may-2026 (S/ 230) es mayor que este cálculo (S/ 206). Uso el
rango 205–230. MINEM además publica el precio en **plantas envasadoras**: Lima S/ 40.5, Cusco 46.4,
Junín 44.3, Puno 48.0. En la sierra la compra directa en planta ahorra 10–15%.

### Índice relativo a Lima (síntesis, est.)

| Ciudad | Verduras base (papa, cebolla) | Arroz | Limón | Pollo | GLP por balón | GLP por menú (con altura) | Menú ejecutivo (Exp./Lima) |
|---|---|---|---|---|---|---|---|
| Arequipa | ≈ 0 a +10% | +30–40% | +100% | ≈ 0 | +4% | +15–25% | 0.81 |
| Trujillo | −10 a −30% | ≈ 0 | ≈ 0 (zona productora cercana) | ≈ 0 | +4% | +4% | 0.73 |
| Chiclayo | +0–30% (dato de un solo día) | ≈ 0 | ≈ 0 | ≈ 0 | +2% | +2% | 0.69 |
| Piura | ≈ 0 | −15–20% | −30% (zona productora) | ≈ 0 | +10% | +10% | s/d |
| Cusco | ≈ 0 a +10% | +20–30% | s/d | +0–25% | +9% | +35–60% | 0.81 |
| Huancayo | −10 a −20% (zona papera) | s/d | s/d | −10% (dudoso) | −1% | +25–50% | 0.62 |
| Juliaca | ≈ 0 a +10% | +10–20% | +150% | ≈ 0 | +7% | +35–70% | s/d |
| Puno | +10–30% | +35% | +200–300% | +5–10% | +7% | +35–70% | s/d |
| Iquitos | +0–60% | −15% | +100% | +5–10% | +42% | +42% | s/d |
| Tacna | ≈ 0 | +30% | s/d | ≈ 0 | +6% | +6% | 0.65 |
| Ica | s/d | s/d | s/d | s/d | 0% | 0% | 0.81 |

Las columnas de verduras, arroz, limón y pollo comparan precios de mercado minorista de 1–2 días con
la referencia limeña (mayorista + INEI minorista). Son indicativas, con un error de ±15–20 pp. Para
el arroz y el pollo, la referencia minorista de Lima es ~S/ 3.5–4.0 y ~S/ 12.

---

## 3. Precio del menú por ciudad (2025–2026)

- **No existe una serie pública de precios del menú por ciudad.** El INEI solo publica la variación del
  rubro "menú en restaurantes" (mar-2026: +1.1% a +1.4% en el mes a nivel nacional y Lima), no el nivel.
  - Fuente: INEI, Boletín de precios mar-2026.
- **Expatistan (menú ejecutivo de zona empresarial)**:

  | Ciudad | Precio | Fecha |
  |---|---|---|
  | Lima | S/ 25–26 | set-2026 |
  | Arequipa | S/ 21 | set-2025 |
  | Cusco | S/ 21 | jul-2026 |
  | Ica | S/ 21 | fecha no clara |
  | Trujillo | S/ 19 | jun-2026 |
  | Chiclayo | S/ 18 | nov-2025 |
  | Tacna | S/ 17 | jun-2026, n=7 |
  | Huancayo | S/ 16 | set-2026 |

  Muestras de 5 a 15 aportes (B−). **Coinciden con el `precio_ejecutivo` del dataset dentro de ±S/ 2**,
  así que los ejecutivos quedan validados como orden de magnitud.
- **Menú popular**:
  - Lima: S/ 12→14 (Magdalena, mar-2026, Infobae); "promedio S/ 15, podría subir a S/ 16–17"
    (Expreso, mar-2026).
  - Promedio nacional de restaurante económico: S/ 12.02 (Preciosmundi, jul-2026, C).
  - Cusco: S/ 10–20 en mercados y picanterías (guías 2026, C).
  - Iquitos: S/ 5–12 (blogs anteriores a 2023, C).
  - Juliaca, Puno, Trujillo, Chiclayo, Huancayo, Tacna e Ica: **sin dato**.
- **Inflación 12 meses por ciudad (abr-25 a mar-26, INEI, A)**:

  | Ciudad | IPC 12 m |
  |---|---|
  | Lima | 3.80% |
  | Ica | 3.55% |
  | Huancayo | 3.37% |
  | Piura | 3.14% |
  | Chiclayo | 2.91% |
  | Arequipa | 2.89% |
  | Iquitos | 2.83% |
  | Cusco | 2.77% |
  | Tacna | 2.67% |
  | Puno | 2.60% |

  La sierra sur tuvo menos inflación que Lima en este período.
- **Presión de costos en 2026**:
  - Crisis de GLP y GNV por la rotura del ducto de Camisea (mar-2026).
  - Pollo +4.6% solo en marzo; INEI, en jul-2026: pollo +10.1% en 26 ciudades, con Huancayo +13.5%,
    Chiclayo +8.5% y Piura +6.5%.
  - CCL/Idexcam (may-2026): insumos importados de 2024 a 2026 (carne deshuesada +25%, aceite en bruto
    +35%, pollo importado +36%), con traslado parcial a los menús y las pollerías.

## 4. Competencia e informalidad

- **PRODUCE, en base a la Encuesta Mensual de Restaurantes del INEI** (abr-2026, B porque solo se leyó
  el fragmento): **161,859 empresas de restaurantes en 2024 (+9.9% frente a 2023)**. Participación
  regional después de Lima:

  | Región | Participación | Empresas (est.) | Por 1,000 hab. del departamento (est.) |
  |---|---|---|---|
  | La Libertad | 6.6% | ≈10,700 | ≈5.1 |
  | Arequipa | 6.0% | ≈9,700 | ≈6.2 |
  | Piura | 5.5% | ≈8,900 | ≈4.2 |
  | Cusco | 5.4% | ≈8,700 | ≈6.3 |
  | Resto de regiones (incluye Puno, Junín, Loreto, Tacna e Ica) | < 4.5% cada una | | |

  Son empresas con RUC, no locales. El `restaurantes_por_mil` del dataset (xMap, locales) es un
  concepto distinto, mayor y por ciudad.
- **El orden coincide con el dataset**: Trujillo y La Libertad están entre las plazas más densas, con
  Arequipa y Cusco cerca.
- **Informalidad**:
  - Rubro "alojamiento y restaurantes": **75.1%** de empleo informal a nivel nacional (CCL, ENAHO, B).
  - No hay cifra por departamento para restaurantes. La aproximación es la informalidad urbana por
    ciudad que ya tiene el dataset (Juliaca 82.3%).
  - Negocios informales por región (CCL): Lima 35.9%, Piura 7.2%, La Libertad 6.1% y Lambayeque 5.0%
    del total nacional.
- **Brecha**: no hay conteo de restaurantes para Juliaca, Puno, Iquitos ni Tacna. Para tenerlo habría que
  consultar el Directorio Central de Empresas del INEI o pedir a SUNAT los RUC activos del CIIU 5610
  por distrito.

## 5. Sueldos de cocina por región

- **Nacional**:
  - Cocinero: S/ 1,653/mes (Indeed, ago-2026, n≈3.2k avisos, B).
  - Cocinero/a: S/ 1,356, y "cocineros/as": S/ 1,201 (Computrabajo, B).
  - Cocinero y ayudante: S/ 1,273 (Indeed).
  - Chef: S/ 2,051 (Indeed).
- **Por ciudad (avisos sueltos, C)**:
  - Arequipa: S/ 1,700–2,500.
  - Cusco: S/ 1,025–3,000 (hoteles).
  - Huancayo: S/ 1,550–1,850 (parrillero, cocinero líder).
  - Juliaca y Puno: **ningún aviso con sueldo**.
- **Ingreso laboral promedio por ciudad (INEI, oct-24 a set-25, A)**:

  | Ciudad | Ingreso promedio |
  |---|---|
  | Lima | S/ 2,433 |
  | Arequipa | S/ 2,279 |
  | Chiclayo | S/ 1,654 |
  | Juliaca | S/ 1,322 |

  Están por encima de S/ 2,000 Cusco, Ica y Trujillo; por debajo, Tacna, Iquitos, Huancayo y Piura.
- **¿En la altura se paga más? No.** Juliaca y Puno tienen los ingresos más bajos de la lista. El piso
  formal es la RMV, S/ 1,230 desde oct-2026. En las MYPE informales, el promedio nacional fue S/ 858 y
  en Puno S/ 476 (ENAHO 2023, ComexPerú, B−; las cifras regionales lucen ruidosas). **Est.:** en Juliaca,
  un ayudante informal cobraría ~S/ 900–1,100 y un cocinero formal ~RMV + 5–10%. Cusco es la excepción:
  el turismo sube el sueldo del cocinero.
- **Brecha**: las remuneraciones de la Planilla Electrónica (MTPE) por región y por CIIU 5610 existen pero
  no se pudieron descargar. Es la mejor fuente pendiente.

## 6. Efecto de la altura en la cocción

| Ciudad | Altitud (m) | Presión (kPa) | Hervor (°C) | ΔT vs nivel del mar | Tiempo de hervido: guías de extensión (+4–10% por cada 1,000 pies) | Cinética (Q10 = 2) | Derrateo del quemador (NFPA 54: −4% por cada 1,000 pies sobre 2,000 pies) |
|---|---|---|---|---|---|---|---|
| Lima, Trujillo, Chiclayo, Piura, Iquitos, Ica | 0–400 | ~100 | 99.5–100 | 0–0.5 | ~0 | ~0 | 0 |
| Tacna | ~560 | 95 | 98.1 | 1.9 | +7–18% | ×1.14 | 0 |
| Arequipa | 2,335 | 76.2 | **92.2** | 7.7 | +30–75% | ×1.7 | −23% |
| Huancayo | 3,250 | 67.9 | **89.2** | 10.8 | +43–107% | ×2.1 | −35% |
| Cusco | 3,400 | 66.6 | **88.7** | 11.3 | +45–112% | ×2.2 | −37% |
| Juliaca / Puno | 3,825 | 63.1 | **87.3** | 12.7 | +50–125% | ×2.4 | −42% |

Cálculo propio: atmósfera estándar + ecuación de Antoine. Es consistente con la regla de "~1 °F cada
500 pies".

**Cómo pasar del tiempo de cocción al gas (est.):**

- **Solo cambia la cocción en agua**: caldo, sopa, arroz, menestra, guisos, papa sancochada. Freír y
  saltear no cambia (el aceite no depende de la presión).
- **El calentamiento previo es más barato** en altura: se calienta hasta ~87 °C y no hasta 100 °C
  (−13%).
- **El hervor lento es más largo y más caro**: más minutos perdiendo calor por la tapa, las paredes y
  el vapor.
- **El aire frío de la sierra** (agua y ollas a 5–12 °C) suma algo de consumo.
- **Evidencia medida, con leña**: una cocina mejorada consumió **+27% de combustible específico en el
  Water Boiling Test (WBT) y +15% en el Controlled Cooking Test (CCT)** al pasar de 678 a 1,976 m
  (OSTI/ETDEWEB). No encontré una medición con GLP.
- **Estimación** para una cocina de menú en la que ~60–70% del gas va a hervidos:
  - **Juliaca/Puno**: **+35–60%** sin olla a presión; **+10–20%** con olla a presión industrial en
    sopas, menestras y carnes (MINEM estima ~50% de ahorro de energía con olla a presión).
  - **Cusco y Huancayo**: +30–50% sin olla a presión y +8–15% con ella.
  - **Arequipa**: +15–30% sin olla a presión y +5–10% con ella.
- **Otros efectos (sin cuantificar)**:
  - El arroz en altura pide más agua y más tiempo, y queda menos graneado sin presión.
  - Con frío extremo (madrugadas bajo 0 °C en Juliaca y Puno), el balón de 45 kg baja de presión y
    queda gas residual. Hipótesis que no pude verificar.
- **Recomendación para el modelo**: agregar un `factor_gas_altura` por ciudad (Lima 1.00, Arequipa 1.10,
  Huancayo y Cusco 1.20, Juliaca y Puno 1.25, con un rango de 1.10 a 1.60) y multiplicar el consumo de
  balones. Fiabilidad: Est., confianza baja-media.

## 7. Alquileres de locales pequeños

| Ciudad | Dato | Fuente / fiabilidad |
|---|---|---|
| Lima Cercado | S/ 50/m², valor medio S/ 6,596 (jun-2026) | Properati, B |
| Lima, San Miguel | 200 m² para restaurante a S/ 8,350 (S/ 42/m²) | Urbania, C |
| Arequipa | S/ 38/m² (set-2026; +16.6% m/m, una serie volátil) | Properati, B |
| Trujillo | S/ 18–28/m² (3 avisos) → **el dataset (45) parece alto** | Properati/Remax, C |
| Huancayo | S/ 8–25/m² (avisos); uno de USD 10/m² | Nuroa/Mitula, C |
| Puno | S/ 70/m² junto a la Plaza Pino (turístico, 1 aviso) | Urbania, C |
| Tacna | S/ 1,200–8,000/mes, 80–625 m² | Properati, C |
| Ica | S/ 20/m², valor medio S/ 4,000 (jun-2026) | Properati, B |
| Chiclayo, Piura, Cusco, Juliaca, Iquitos | Sin dato agregado | — |

Son precios pedidos, no contratos. Los locales de menú popular suelen estar fuera de los portales:
Facebook Marketplace o avisos en la puerta.

---

## 8. Brechas (no se encontró dato)

1. **Menú popular observado** en Juliaca, Puno, Trujillo, Chiclayo, Huancayo, Tacna e Ica. La única
   forma confiable es un relevamiento propio: 10–20 pizarras por ciudad, fotos de Google Maps o un
   sondeo de TikTok/Facebook con fecha.
2. **Precios mayoristas regionales comparables** (SISAP/MIDAGRI: Arequipa, Huancayo, Juliaca, Trujillo,
   Chiclayo, Piura, Cusco). El portal no respondió. Es la fuente adecuada para reemplazar las fotos de
   prensa y cubre arveja, zanahoria, ajo y tomate, que la prensa casi no reporta.
3. **Carne de res y huevo** comparables: hay datos pero con unidades inconsistentes (plancha, docena,
   "kilo de huevos").
4. **Sueldos de cocinero, ayudante y mozo** en Juliaca, Puno, Iquitos, Tacna e Ica (Planilla Electrónica
   por región y CIIU 5610).
5. **Número de restaurantes** en Juliaca, Puno, Iquitos y Tacna, e **informalidad del rubro por región**.
6. **Medición del consumo de GLP en altura** en cocinas comerciales (no hay estudio con GLP; el único
   dato medido es con leña).
7. **Alquiler** en Juliaca, Chiclayo, Piura, Cusco (fuera del centro histórico) e Iquitos.
8. **Ica** no tiene ningún dato de insumos de mercado.

## 9. Ajustes sugeridos al dataset (para discutir; ninguno aplicado)

| Campo | Cambio | Motivo |
|---|---|---|
| `gas_balon45` (todas) | +10–25% | Post-crisis: MINEM ago-26 × 4.5 × 0.91, o S/ 230 en Lima según la prensa de may-26. Iquitos ~290 se mantiene. Puno 245 tiene un solo registro: usar ~235 |
| nuevo `factor_gas_altura` | Lima y costa 1.00, Tacna 1.02, Arequipa 1.10, Huancayo y Cusco 1.20, Juliaca y Puno 1.25 | Sección 6 |
| `insumos_popular` | Puno 4.4 → 4.5; Juliaca 4.2 → 4.3–4.4; Huancayo 4.0 se puede mantener (zona productora); Trujillo y Piura 4.0–4.1 | Arroz y limón más caros en el altiplano; papa y cebolla a la par |
| `alquiler_m2` Trujillo | 45 → ~25–30 | Avisos de 2026 |
| `alquiler_m2` Arequipa | 35 → 38 | Properati set-26 |
| `precio_ejecutivo` | Sin cambio | Validado por Expatistan (±S/ 2) |

---

## 10. Fuentes (URL, institución, fecha)

**GLP**
- MINEM, "Precios de combustibles líquidos y GLP a nivel usuario final", al 20-08-2026 (Tablas 7–9,
  balón de 10 kg por departamento):
  https://cdn.www.gob.pe/uploads/document/file/10485613/8503002-reporte-diario-20-08-2026.pdf
  (colección: https://www.gob.pe/institucion/minem/colecciones/44465-precios-de-combustibles-liquidos-y-glp-a-nivel-usuario-final)
- La República Verificador, 06-04-2026 (MINEM 19-feb y 19-mar-2026, por región):
  https://larepublica.pe/verificador/2026/04/06/el-sur-del-peru-paga-el-gas-mas-caro-datos-oficiales-contradicen-a-george-forsyth-236232
- Facilito/Osinergmin vía preciocombustible.com, registros de ene-2026, descargado el 17-10-2026:
  https://www.preciocombustible.com/balon-de-gas-glp/puno/juliaca/ (y equivalentes por ciudad)
- Infobae, 25-05-2026 (10 kg ~S/ 64 puesto en casa; 45 kg S/ 230):
  https://www.infobae.com/peru/2026/05/25/balon-de-gas-vuelve-a-subir-y-golpea-a-familias-y-restaurantes-ejecutivo-prepara-decreto-especial/
- La República, 27-03-2026 (balón por ciudad: Piura 54.5, Puno 65, Tacna 58, Arequipa 46.5, Iquitos 76.5):
  https://larepublica.pe/economia/2026/03/16/cuanto-esta-el-combustible-hoy-en-peru-precios-del-gnv-glp-diesel-y-gasolina-en-marzo-2026-hnews-535457

**Insumos**
- La República, mercados al 13-03-2026 (Piura, Chiclayo, Arequipa, Juliaca):
  https://larepublica.pe/economia/2025/12/09/precios-canasta-basica-hoy-peru-mercados-pollo-papa-limon-huevo-arroz-hnews-477176
- La República, mercados al 27-03-2026 (Piura, Arequipa, Puno, Iquitos):
  https://larepublica.pe/economia/2026/03/16/precios-hoy-peru-canasta-basica-mercados-pollo-papa-limon-huevo-arroz-hnews-247611
- La República, mercados ~21-11-2025 (Piura, Chiclayo, Trujillo, Arequipa, Tacna, Cusco, Puno, Iquitos):
  https://larepublica.pe/economia/2025/11/19/precio-de-canasta-basica-hoy-en-mercados-del-peru-cuanto-cuestan-pollo-papa-huevo-y-otros-alimentos-hnews-533406
- Revista Lombriz, 09-10-2026 (MIDAGRI-DGESEP, GMML 08-10-2026 vs supermercados de Arequipa):
  https://revistalombriz.com.pe/precio-tomate-arequipa-limon-ajo/
- Diario Correo Arequipa (pollo 10.50, res 19.80; jul–ago 2026): https://diariocorreo.pe/noticias/precios-de-alimentos/
- Diario El Pueblo, 08-03-2026 (res en Arequipa: 17.50 → 19–20):
  https://diarioelpueblo.com.pe/2026/03/08/alimentos-de-primera-necesidad-suben-de-precio-en-mercados-de-arequipa/
- INEI, Boletín de precios mar-2026 (variaciones por ciudad, IPC 12 m):
  https://www.inei.gob.pe/media/MenuRecursivo/boletines/boletin-precios-mar2026.pdf
- INEI, Boletín estadístico ago-2026 (pollo jul-26: Lima 11.23; +10.1% en 26 ciudades):
  https://www.inei.gob.pe/media/MenuRecursivo/boletines/boletin_estadistico_agosto_2026.pdf
- Infobae, 05/08-05-2026 (línea de pobreza extrema 2025: nacional 260, Lima 307, costa 281, selva
  239, sierra 230; dependen de la composición de la canasta, no son paridad pura):
  https://www.infobae.com/peru/2026/05/05/canasta-basica-aumento-a-s260-en-peru-y-acumula-alza-de-36-en-los-ultimos-cinco-anos/
- Infobae, 07-05-2026 (CCL/Idexcam, insumos importados):
  https://www.infobae.com/peru/2026/05/07/menus-y-pollerias-suben-hasta-un-51-sus-precios-por-alza-historica-de-carne-y-aceites-importados-alerta-la-ccl/

**Menú**
- Expatistan (menú ejecutivo por ciudad, fragmentos del buscador):
  https://www.expatistan.com/cost-of-living/comparison/lima/huancayo ,
  https://www.expatistan.com/cost-of-living/comparison/lima/cusco ,
  https://www.expatistan.com/cost-of-living/comparison/cusco/trujillo ,
  https://www.expatistan.com/cost-of-living/arequipa , https://www.expatistan.com/cost-of-living/chiclayo ,
  https://expatistan.com/price/daily-menu/tacna
- Infobae, 10-03-2026 (Lima, S/ 12 → 14):
  https://www.infobae.com/peru/2026/03/10/menus-suben-de-precio-hasta-18-soles-por-tarifa-del-balon-de-gas-que-supera-los-100-soles/
- Expreso (Lima, menú promedio S/ 15 → 16–17):
  https://www.expreso.com.pe/economia/crisis-del-gnv-en-peru-asi-se-disparan-los-precios-del-balon-de-gas-segun-distrito-sjm-san-miguel-noticia/1269723/
- Preciosmundi, jul-2026 (nacional S/ 12.02): https://preciosmundi.com/peru/precio-restaurantes
- Uros Expeditions, 29-01-2026 (guía de viaje): https://www.urosexpeditions.com/blog/food-prices-in-peru-2026

**Competencia, informalidad, sueldos**
- PRODUCE, Análisis sectorial de restaurantes 2021–2025 (abr-2026; solo se leyó el fragmento):
  https://www.producempresarial.pe/wp-content/uploads/2026/04/PPT-RESTAURANTE-2021_2025.pdf
- La Cámara (CCL), informalidad por rubro y región: https://lacamara.pe/el-empleo-informal-avanza-a-paso-firme/
- Gestión (INEI, ingreso por ciudad, oct-24 a set-25):
  https://gestion.pe/economia/solo-en-11-de-27-ciudades-los-trabajadores-ganan-mas-de-s-2000-al-mes-cuales-son-noticia/
- ComexPerú, 16-08-2024 (ENAHO 2023, MYPE formal/informal por región):
  https://www.comexperu.org.pe/articulo/mypes-informales-solo-pagan-s-858-en-promedio-a-sus-trabajadores
- Indeed: https://pe.indeed.com/career/cocinero%2Fa/salaries ; Computrabajo: https://pe.computrabajo.com/salarios/cocineroa

**Altura**
- NFPA 54 / Código Mecánico, apéndice B (derrateo de 4% por cada 1,000 pies):
  https://gocodebook.com/library/us/ca/ca-mechanical-code/appendix-b-procedures-to-be-followed-to-place-gas-equipment-in-operation
- Cocina de leña a 678 vs 1,976 m (WBT +27.3%, CCT +15.3% de consumo específico):
  https://www.osti.gov/etdeweb/biblio/22602920
- Guías de cocina en altura (+4–10% de tiempo por cada 1,000 pies; frejoles +18–35% a 5,000 pies):
  https://alegumeaday.com/beans-and-high-elevation-5-things-to-know/ , https://cookingcalcs.com/tools/altitude-cooking-calculator.html
- MINEM, ~50% de ahorro de energía con olla a presión (citado por RPP):
  https://rpp.pe/economia/estilo-de-vida/las-ventajas-de-cocinar-con-ollas-a-presion-noticia-910922

**Alquileres**
- Properati (fragmentos del buscador): https://www.properati.com.pe/s/arequipa/local-comercial/alquiler ,
  https://www.properati.com.pe/s/lima-cercado/local-comercial/alquiler , https://www.properati.com.pe/s/ica/local-comercial/alquiler
- Urbania Puno: https://urbania.pe/buscar/alquiler-de-propiedades-en-puno ;
  Nuroa Huancayo: https://www.nuroa.pe/alquiler/local-comercial-huancayo ;
  Urbania Trujillo: https://urbania.pe/buscar/locales-comerciales-en-trujillo--la-libertad
