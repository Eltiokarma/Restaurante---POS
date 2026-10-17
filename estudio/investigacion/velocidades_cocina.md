# Velocidades de preparación manual y efecto de la altura (Juliaca, 3 825 m)

Investigación web para el Gantt de producción matinal de un restaurante de menú. Fecha: 2026-10-17.

## Advertencia general sobre la calidad de los datos

Casi no hay estándares de mano de obra **publicados y abiertos** para tareas manuales de cocina.
- La **única tabla numérica seria** que encontré es la de la industria de cebollas de EE. UU. (Idaho-E. Oregon Onion Committee / USA Onions): minutos por libra para pelar, cortar en pluma, picar, etc., según el calibre.
- Existe un estudio académico de muestreo de trabajo (Block, Roach y Konz, *J. Am. Diet. Assoc.* 1985;85(2):206-209, PMID 3968358) con minutos por libra para limpiar zanahoria, apio, lechuga, cebolla y papa en un comedor universitario, pero **el texto completo está detrás de un muro de pago y no pude obtener las cifras**. Si consigues el PDF (biblioteca universitaria), es la mejor fuente para validar papa y zanahoria.
- El resto viene de anécdotas, sitios de recetas, competencias de cocina o páginas de proveedores. En esos casos lo marco como **ESTIMACIÓN** y el valor central lo calibro con tus propias referencias (arvejas 30 min/kg, papa 10 kg en 45 min, zanahoria 30 min/kg).
- Recomendación: cronometra 2 o 3 mañanas reales (con el mismo personal) y reemplaza los valores centrales. La variación entre personas es de 2 a 3 veces.

## Tabla de velocidades

"Cocinero promedio" significa alguien con oficio, sin ser rápido de competencia. Los tiempos son de trabajo efectivo. Para el Gantt, suma un 10–15 % por lavado de tablas, traslados e interrupciones.

| Tarea | Unidad | Valor central | Rango lento–rápido | Fuente y tipo |
|---|---|---|---|---|
| **Pelar papa con pelador** | min/kg | **4,5** | 2,5 – 8 | Tus datos: 10 kg en 45 min (2,5 si son 25 min). Páginas de proveedores: "10 lb en 25+ min" ≈ 5,5 min/kg y "2 lb en 15 min" ≈ 16 min/kg (esta segunda es claramente exagerada para vender máquinas). [spice.alibaba.com](https://spice.alibaba.com/spice-basics/peeler-potato-machine). **ESTIMACIÓN**: la papa amarilla o huayro (pequeña y con ojos) va hacia el extremo lento, la papa blanca grande hacia el rápido. |
| Pelar papa con cuchillo | min/kg | 6 | 4 – 10 | **ESTIMACIÓN**: un 30–50 % más lento que con pelador y con más merma (20–30 % frente a 8–12 %, según páginas de proveedores). |
| Sancochar papa entera mediana (olla grande) | min | 35–45 a hervor + calentar el agua | 30 – 60 | **ESTIMACIÓN**. A nivel del mar son 20–25 min de hervor. En Juliaca calcula ×1,5 (ver la sección de altura). Calentar 25–30 L de agua en una hornilla de GLP de restaurante toma 25–40 min adicionales. |
| **Pelar cebolla** (solo pelar), cebolla de 2½"–3" | min/kg | **2,2 – 3,7** | 0,7 (cebolla de 4½") – 3,7 | Tabla "Onion Preparation Times" de USA Onions / Idaho-E. Oregon Onion Committee: 1,66 min/lb para 2½" y 0,99 min/lb para 3". [Sizing-Guide.pdf](https://usaonions.com/wp-content/uploads/2022/04/Sizing-Guide.pdf). Es un dato de la industria, el más sólido de esta lista. |
| **Pelar y cortar cebolla en pluma (juliana)** | min/kg | **7 – 8** (cocinero de industria); **9–10** para un cocinero promedio | 5,1 – 12 | Misma tabla, fila "cutting slivers" (acumulativa, incluye pelado): 3,69 min/lb (2½") = 8,1 min/kg y 2,99 min/lb (3") = 6,6 min/kg. La cebolla roja peruana suele ser de 2½"–3". El ajuste para un cocinero promedio es **ESTIMACIÓN**. |
| Pelar y picar cebolla en cubos | min/kg | **7,5 – 9** | 5,9 – 12 | Misma tabla, fila "dicing": 3,99 min/lb (2½") = 8,8 min/kg y 3,32 min/lb (3") = 7,3 min/kg. Anécdota de un dueño en un foro de pizzerías: 5 cebollas en 15 min (cocinero hábil) frente a 30 min (su personal), es decir, ≈ 6–12 min/kg. |
| Pelar y picar cebolla fino (mince) | min/kg | 5 – 7 | 3,7 – 9 | Misma tabla: 3,02 y 2,35 min/lb. |
| Pelar y picar zanahoria en cubos medianos | min/kg | **15** | 10 – 30 | **ESTIMACIÓN**. Pelar ≈ 3–4 min/kg (por analogía con la papa) más el corte. Es más dura que la cebolla y necesita más cortes. Tu dato de 30 min/kg cuadra con un corte fino (brunoise) o con un cocinero lento. Para cubo mediano (1 cm), usa 12–18. |
| Pelar y trozar zapallo (macre/loche) | min/kg | 8 | 5 – 12 | **ESTIMACIÓN**. La cáscara dura toma tiempo, pero los trozos son grandes. |
| Poro: limpiar, lavar y rebanar | min/kg | 6 | 4 – 9 | **ESTIMACIÓN**. Lavar la tierra entre capas toma la mitad del tiempo. |
| Apio: lavar y picar | min/kg | 5 | 3 – 8 | **ESTIMACIÓN**. El estudio de 1985 midió "limpieza" de apio, pero no tengo la cifra. |
| **Desvainar arveja fresca** | min/kg de vaina | **30** | 20 – 45 | Tu dato (30 min/kg). Sitio de jardinería: 10–20 min/lb = 22–44 min/kg [latahcountyid.gov](https://phdns.latahcountyid.gov/article/how-to-shell-peas-quick-easy-guide) (fuente débil). Confirma el orden de magnitud. |
| Desvainar arveja: expresado por kg de grano | min/kg de grano | **65** | 45 – 100 | Rendimiento grano/vaina ≈ 40–50 %. Ensayo ecuatoriano: 2 607 kg/ha de grano frente a 5 976 kg/ha de vaina = 44 % [repositorio UTN](https://repositorio.utn.edu.ec/jspui/bitstream/123456789/667/3/03%20AGI%20269%20%20ART%c3%8dCULO%20CIENT%c3%8dFICO.pdf). Fuentes de EE. UU. dan "≈ la mitad del peso". Cálculo: 30 ÷ 0,45. |
| Desvainar haba fresca (1.ª pelada) | min/kg de vaina | 12 | 8 – 20 | **ESTIMACIÓN**. Las vainas son grandes y salen pocos granos por vaina. Rendimiento ≈ 25–33 % (3–4 lb de vaina por 1 lb de grano) [Garden Betty](https://gardenbetty.com/growing-harvesting-and-shelling-fava-beans/), [Jessica Gavin](https://www.jessicagavin.com/how-to-cook-fava-beans/). Equivale a ≈ 40 min por kg de grano. |
| Pelar la piel del haba (2.ª pelada, tras blanquear 30–60 s) | min/kg de grano | 35 | 25 – 50 | **ESTIMACIÓN** (no encontré datos numéricos). |
| Pelar ajo a mano | min/kg | **28** | 20 – 45 | Páginas de baja calidad: 12–15 min/lb = 26–33 min/kg (citan estudios que no pude verificar) [spice.alibaba.com](https://spice.alibaba.com/spice-basics/how-to-peel-garlic-quickly). Aplastar o remojar el ajo lo acelera. |
| Pelar y picar o moler ajo | min/kg | 40 | 30 – 60 | **ESTIMACIÓN**. En un menú típico se usan 150–300 g al día, unos 8–15 min. El ajo pelado de mercado elimina esta tarea. |
| Ají (amarillo o panca): desvenar, despepitar y licuar | min/kg | 20 | 12 – 35 | **ESTIMACIÓN**. Si es seco, suma el remojo o hervido (tiempo de espera, no de mano de obra) y 5 min por licuada. |
| Ensalada: lavar y picar lechuga | min/kg | 6 | 4 – 10 | **ESTIMACIÓN** (el estudio de 1985 tiene la cifra de "limpieza" de lechuga, pero no es accesible). |
| Tomate: lavar y cortar en rodajas o cubos | min/kg | 6 | 4 – 9 | **ESTIMACIÓN**. |
| Pepino: pelar y rebanar | min/kg | 5 | 3 – 8 | **ESTIMACIÓN**. |
| **Trozar pollo entero en 8 piezas** | min/pollo | **4** | 2 – 10 | Sitios de recetas caseras: 5–10 min [ifoodreal](https://ifoodreal.com/how-to-cut-a-whole-chicken), [Easy Chicken Recipes](https://easychickenrecipes.com/how-to-cut-whole-chicken/). En Skills Canada (competencia de estudiantes) se dan **20 min** para trozar en 8 con presentación cuidada, que es un límite holgado [PDF](https://skillscanada.bc.ca/wp-content/uploads/2026/03/Cook_2026_Secondary_Provincial_FINAL-February-26-2026-.pdf). Un pollero o cocinero diario lo hace en 1,5–3 min. Valor central = **ESTIMACIÓN**. |
| Bistec: filetear de pieza entera y golpear o ablandar | min/kg (≈ 7 bistecs de 140 g) | 8 | 5 – 12 | **ESTIMACIÓN**: ≈ 1 min por bistec. Si la carnicería lo entrega cortado, solo queda el golpeado: ≈ 3–4 min/kg. |
| Chuleta de cerdo: separar o porcionar | min/chuleta | 0,5 | 0,3 – 1 | **ESTIMACIÓN**. Si se compra cortada, ≈ 0 (solo sazonar). |
| Trucha entera: eviscerar, limpiar y quitar agallas | min/pescado | 2 | 1 – 4 | **ESTIMACIÓN**. Las guías de pesca dicen "segundos" o "pocos minutos" por trucha chica [Field & Stream](https://www.fieldandstream.com/stories/fishing/freshwater-fishing/how-to-clean-a-trout). En Puno se compra a menudo ya eviscerada. Filetear y desespinar: 4–6 min. |
| Lavar arroz | min/tanda (3–5 kg) | 3 | 2 – 5 | **ESTIMACIÓN**. |
| Cocer arroz en olla grande (graneado) | min | **40 – 50** (sofreír, hervor, secado) + 10 de reposo | 35 – 60 | Chef de altura: un arroz que a nivel del mar toma 18–20 min puede demorar **hasta 40 min** en altura [chefandhotel.cl](https://chefandhotel.cl/opinion/el-desafio-de-cocinar-en-alturas/). En altura conviene ¼–½ taza más de agua por taza de arroz [buenazo.pe](https://buenazo.pe/tecnicas-y-tips/2021/02/28/como-cocinar-arroz-perfecto-altura-303). |
| Caldo o sopa base (pollo o res), 20–40 L | h | 2 – 2,5 (incluye llegar al hervor) | 1,5 – 3,5 | **ESTIMACIÓN** de práctica culinaria. Gran parte es espera sin mano de obra. |
| Guiso o seco de res, olla abierta | h | 2 – 2,5 en Juliaca | 1,5 – 3 | **ESTIMACIÓN**: 1,5 h a nivel del mar × 1,3–1,6. Con olla a presión: 35–50 min. |
| Menestra (frejol o lenteja secos) | h | olla abierta: 3–4+ / a presión: 0,7–1 | — | Ver la sección de altura (estudio de Guatemala). Con olla abierta en Juliaca no es práctico. |
| **Lavado a mano por cubierto** (plato de entrada o sopa, plato de fondo, vaso y cubiertos) | s/cubierto | **45** | 30 – 75 | **ESTIMACIÓN**. Un proyecto de ingeniería reporta 8 platos/min de lavado manual frente a 24/min a máquina [kscst.org.in](https://www.kscst.org.in/sppArchive/public/show/abs/037/7555) (fuente débil). Hobart (fabricante de lavavajillas) reporta sesiones de lavado manual de 15–40 min y un 40 % menos de tiempo con máquina, sin dato por cubierto [Hobart](https://blog.hobartcorp.com/blog/comparing-productivity-compliance-between-manual-automated-dishwashing). **Ollas y utensilios de cocina aparte: 30–60 min al día.** |
| Emplatado en menú (una persona) | s/plato | sopa 10–15; segundo 20–40 | 8 – 60 | **ESTIMACIÓN**. En banquetes con línea o faja se llega a 2,4–5 s por plato por línea [CMAA](https://www.cmaa.org/idea-fair/idea-fair-entries/engineering-better-banquet-service/) y [Rational](https://hcms.rational-online.com/hcms/v1.7/entity/brochure/797361/storage/MDA3OTczNjEvMC9wZGYtcHJldmlldy0xNTBwcGktcHJpbnRzaGVldC8vLzU3MTg3NzE2/download/finishing_guide_english_us.pdf), pero eso es con varios operarios y emplatado de producción. |

### Lectura de la tabla de cebolla (la fuente más sólida)

Las filas de corte de la tabla de USA Onions **incluyen el pelado**: "slabs" − "peeling" = 1,00 min/lb exactos en todos los calibres. El tiempo cae mucho con cebollas grandes, porque el pelado es por unidad. La tabla original está en minutos por libra; multiplica por 2,205 para obtener min/kg.

| Calibre | Pelar | Rodajas | Aros | Pluma | Cubos | Picado fino |
|---|---|---|---|---|---|---|
| 2½" (≈ 150–180 g) | 3,7 | 5,9 | 12,5 | 8,1 | 8,8 | 6,7 |
| 3" (≈ 220–280 g) | 2,2 | 4,4 | 9,5 | 6,6 | 7,3 | 5,2 |
| 3½" | 1,4 | 3,6 | 8,0 | 5,8 | 6,6 | 4,4 |
| 4" | 1,0 | 3,2 | 7,1 | 5,4 | 6,1 | 4,0 |

(Valores en min/kg.)

## Notas de confiabilidad

1. **Alta**: la cebolla (tabla de la industria, aunque es de EE. UU. y con cocineros entrenados, posiblemente de los años 90–2000) y los rendimientos grano/vaina de la arveja (ensayo agronómico).
2. **Media**: la papa y la arveja, porque tus datos coinciden en orden de magnitud con fuentes externas débiles. Además, el tiempo límite de Skills Canada para trozar pollo es un dato verificable, pero es un límite, no un promedio.
3. **Baja (estimaciones)**: zanahoria, zapallo, poro, apio, haba, ajo, ají, ensalada, bistec, chuleta, trucha, lavado y emplatado. Son razonamientos por analogía con la cebolla y la papa más práctica de cocina. Cronometrar en el local es obligatorio para estas tareas.
4. El estudio que más valdría la pena conseguir: Block, Roach y Konz (1985), "Occurrence sampling in a residence hall foodservice: cleaning times for selected vegetables", *J Am Diet Assoc* 85(2):206-9, https://pubmed.ncbi.nlm.nih.gov/3968358/ (≈ 350 h de trabajo, > 2 000 observaciones, min/lb para zanahoria, apio, lechugas, cebolla y papas).
5. La velocidad depende mucho del tamaño de la pieza (pelar es un costo por unidad), del filo del cuchillo y de si la persona hace la misma tarea en bloque. Agrupar las tareas (toda la cebolla de una vez) es más rápido que intercalarlas.
6. Tus datos son coherentes: papa 4,5 min/kg está en el rango normal; arveja 30 min/kg de vaina coincide con las fuentes; zanahoria 30 min/kg es el doble de mi estimación para cubo mediano, así que conviene confirmar el tipo de corte.

## Efecto de la altura (Juliaca 3 825 m)

**Punto de ebullición**
- Con la atmósfera estándar, a 3 825 m la presión es ≈ 63 kPa y el agua hierve a **≈ 87–88 °C** (cálculo propio con la fórmula barométrica). Para comparar: en La Paz (3 640 m) se citan 87–88 °C.
- Una tesis de la UANCV midió **85 °C** en Juliaca, probablemente con un termómetro de poca precisión [ALICIA/CONCYTEC](https://alicia.concytec.gob.pe/vufind/Record/REVUANCV_aa05b2fb89d1dd31a8a83747bd72b432).
- Regla práctica: el punto de ebullición baja ≈ 3 °C por cada 1 000 m [buenazo.pe](https://buenazo.pe/tecnicas-y-tips/2021/02/28/como-cocinar-arroz-perfecto-altura-303).

**Tiempos de cocción en olla abierta**
- **Menestras secas (frejol)**: es el efecto más grande y el mejor documentado. Un estudio en Guatemala (frejol negro, 8 localidades) midió **78 min a 0 m frente a 264 min a 2 256 m (×3,4)** [Springer, Plant Foods Hum Nutr](https://link.springer.com/article/10.1007/BF01092522) (cifras tomadas del resumen indexado). Didinger et al. 2023 (*Legume Science*, frejol pinto, 4 altitudes) confirman que la altura alarga la cocción y que remojar con sal o bicarbonato reduce el efecto [AGRIS/FAO](https://agris.fao.org/search/en/records/675ac61c0ce2cede71d10db7). A 3 825 m, en olla abierta, se esperaría ≥ ×3: **usar olla a presión**.
- **Arroz**: ×1,5–2. De 18–20 min a nivel del mar pasa a hasta 40 min [chefandhotel.cl](https://chefandhotel.cl/opinion/el-desafio-de-cocinar-en-alturas/). Algunas guías dicen que sobre ~2 000 m el agua ya no alcanza la temperatura ideal de gelatinización y recomiendan olla a presión o más agua.
- **Papa**: no hay estudio directo. Con la cinética de ablandamiento de papa publicada (Ea de 7,5 a 32,5 kcal/mol según el estudio y el método) [redalyc](https://www.redalyc.org/pdf/1698/169823914024.pdf), la ecuación de Arrhenius da entre ×1,4 y ×4,7 al pasar de 100 a 87 °C (cálculo propio). En la práctica andina, la papa sancochada se cuece en tiempos razonables. **Para planificar: ×1,5 (rango 1,3–2)**. Es una ESTIMACIÓN; cronometrar una olla en el local la reemplaza.
- **Caldos y fondos**: un fondo ya se cocina normalmente a fuego bajo (85–95 °C), así que la altura afecta poco la extracción. El ablandamiento del colágeno de la carne sí es más lento: **×1,2–1,5** (ESTIMACIÓN). Llegar al hervor es algo más rápido, porque solo hay que calentar hasta 87 °C (≈ 13 % menos calor sensible).
- Las reglas de olla a presión de Colorado State University (+5 % de tiempo por cada 1 000 ft sobre 2 000 ft) extrapoladas a 12 500 ft dan ≈ +50 %. La misma CSU indica que el ajuste es más necesario en frejoles y arroz [CSU Extension](https://extension.colostate.edu/resource/adjusting-for-elevation-when-pressure-cooking).

**Consumo de gas**
- La cocción a fuego sostenido se alarga en la misma proporción que el tiempo, así que el gas de esa fase sube igual: ≈ +30–50 % en papa y arroz, +100–200 % en menestras en olla abierta (ESTIMACIÓN derivada).
- Los quemadores calibrados para nivel del mar entregan menos potencia por el menor oxígeno. Los códigos de gas norteamericanos asumen **−4 % de potencia por cada 1 000 ft sobre 2 000 ft** (≈ −40 % a 3 800 m) si el fabricante no indica otra cosa [Johnson Controls IOM](https://webselect.johnsoncontrols.com/pdf/iom/145.25-IOM3.pdf), [Alberta STANDATA](https://open.alberta.ca/dataset/88448076-7f1e-4bbc-8767-b90caca76fbe/resource/a0e37bd6-55ec-4280-955d-836f104829d5/download/ma-standata-gas-bulletin-20-gcb-07-rev2.pdf). En la práctica, las cocinas industriales de Puno suelen venir reguladas para altura, pero los tiempos para llegar al hervor de ollas grandes son más largos que en Lima.
- Una calculadora de excursionismo estima +20–35 % de combustible en alta montaña (dato orientativo, sin estudio) [vulcanoexpediciones](https://vulcanoexpediciones.com/calculadoras-outdoor/punto-ebullicion-agua-altitud).
- **Olla a presión**: en una demostración (Welthungerhilfe/HEDON, a solo 1 500 m), una sopa con papa consumió **1/5 del combustible** del método tradicional. Además, el ahorro crece con la altitud [energypedia](https://energypedia.info/images/2/25/Pressure_cooker_training_whh-HEDON.pdf).
- **Para el estudio de rentabilidad**: asume +30–50 % de gas frente a recetas o costeos hechos en Lima para cocción en olla abierta. Asume la olla a presión como estándar para menestras y carnes de guiso.

## Supuestos sugeridos para el Gantt (cocinero promedio, Juliaca)

| Tarea | Supuesto |
|---|---|
| Papa (pelador) | 4,5 min/kg; sancochado 40 min de hervor + 30 min calentando agua |
| Cebolla en pluma | 9 min/kg; cubos 9 min/kg |
| Zanahoria en cubo | 15 min/kg (30 si es brunoise) |
| Arveja | 30 min/kg de vaina (≈ 65 min/kg de grano) |
| Haba | 40 min/kg de grano desvainado + 35 si se pela la piel |
| Ajo | pelado y molido: 40 min/kg (o comprarlo pelado) |
| Pollo | 4 min por pollo en 8 piezas |
| Bistec | 1 min por unidad |
| Trucha | 2 min por pieza |
| Arroz | 50 min + 10 de reposo por tanda |
| Caldo | 2–2,5 h (casi todo es espera) |
| Guiso | 2–2,5 h en olla abierta / 45 min con olla a presión |
| Lavado | 45 s por cubierto + 45 min al día de ollas |
| Emplatado | 30 s por menú completo (sopa + segundo) |
