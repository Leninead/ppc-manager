---
tipo: sop
actualizado: 2026-07-24
---

# SOP PPC 360° — De reporte a decisión (Capybaras Agency)

**Qué es:** el método senior de auditoría de cuentas Amazon Ads fusionado con el flujo 360° de Capybaras. Convierte 9 fuentes de reporte en decisiones defendibles sobre bid, placement, budget, corte y escala.

**Principio rector:** ningún reporte se lee aislado, ningún número se lee sin su denominador, ninguna decisión se toma sin verificar el parent ASIN.

**Base:** fusión del método "De reporte a decisión" (origen marca ES, IVA 21%) con el 360° de Capybaras. El motor (reglas previas, aritmética, trampas, decisiones) es marketplace-agnóstico y vive en el CORE. Lo que cambia por cuenta (neto, mapa, familias, stop-loss) vive en los ANEXOS.

**Estado de esta versión:** aplicable sin COGS. El break-even queda como estimación etiquetada; el corte real se hace por **stop-loss en $** (dato duro). Cuando el AM pase COGS, se activa la capa de break-even rentable.

---

# PARTE A — MÉTODO CORE (marketplace-agnóstico)

## A.0 — Las 4 reglas previas (se aplican ANTES de mirar un número)

Si te salteás estas, todo lo que sigue está contaminado.

### Regla 1 — D-3: ventana de atribución
Amazon reestima la atribución 48–72h. **Los últimos 3 días de cualquier ventana no son evaluables para conversión.**

- Error caro: ver "0 ventas" en día 4 y cortar. La venta puede entrar el día 6 y atribuirse al día 2.
- **Ningún reporte cierra D-3.** Buscar confirmación en un segundo reporte con la misma ventana = confirmación circular.
- **Operativa:** para decidir corte, la ventana dura termina en X-3. Todo lo demás es provisional.

### Regla 2 — El cluster: qué colapsa el close variant
Amazon **colapsa** en la misma subasta: plurales, tildes/typos, orden de palabras, palabras función.
Amazon **NO colapsa** palabras de contenido ("alta firmeza 135x190" ≠ "muelles ensacados 135x190").

- **Consecuencia dura:** 4 campañas sobre close variants = **1 experimento partido en 4**. Amazon sirve una por subasta (mayor ad rank); las demás mueren en silencio.
- Si medís CVR sin agregar el cluster, tu techo de bid puede estar mal por **3×** (ver A.1.3, sensibilidad).
- **Operativa:** antes de calcular ACoS/CVR/BE CPC → **agregá el cluster**. En estructura: un cluster = una campaña.

### Regla 3 — Ningún archivo es censo
Dump de Manage Inventory, mapa de ASINs y esquema de SKU están **todos incompletos por construcción**.

- **Operativa:** antes de declarar "no existe" → búsqueda directa por SKU/ASIN con filtro **All** (no solo Active), fallback al Bulk Export.
- Antes de anunciar un ASIN por primera vez → agregarlo al mapa, o la campaña nace ciega para todo tu sistema de análisis.
- **Paso obligatorio de verificación de mapa** (ver A.2, secuencia): cruzar los ASINs del Advertised contra el mapa. Todo ASIN que se anuncia y no está clasificado (parent/familia/línea/medida, **por SKU nunca por título**) → marcar "sin clasificar", **no escalar** hasta resolver.

### Regla 4 — Runway de stock: verificar ANTES de escalar

Ninguna decisión de escala es válida sin verificar el runway del ASIN. La aritmética puede aprobar una escala que el stock veta.

| Runway | Decisión |
|---|---|
| < 15 días | **NO escalar.** Contener pauta si el quiebre es inminente |
| 15–25 días | Escalar con cuidado, revisar en el siguiente ciclo |
| > 25 días | Escalable |
| > 300 días | Overstock → candidato a **clearance** |

**Por qué es regla previa y no un chequeo tardío:** escalar un ASIN sin stock acelera su quiebre y quema presupuesto en tráfico hacia una ficha que va a quedar OOS. Peor: el quiebre cuesta **ranking orgánico**, que no se recupera solo cuando el stock vuelve.

**Caso real (Setex, jul-2026):** la Regla 4 vetó la escala de una joya CONQUEST con ACoS 6% (aritmética la aprobaba) porque el ASIN tenía 3 días de runway. La escala se redirigió a familias con stock. Resultado: el hero se quebró igual (−49% en ventas) pero **la cuenta cerró plana** porque el sostén vino de las familias escaladas. Sin la Regla 4, se habría acelerado el quiebre y perdido la compensación.

**Corolario operativo:** toda alerta de stock crítico se registra con (a) a quién se le pidió la reposición, (b) quién controla el follow-up, (c) fecha de control. Una alerta sin owner de seguimiento es una alerta que nadie mira.

---

## A.1 — La aritmética que gobierna las decisiones

### A.1.1 — El neto (base de comparación)
```
Neto = PVP / (1 + IVA_del_marketplace)
```
El factor lo define el **ANEXO de cada cuenta** (US: sin dividir; MX: /1.16). Amazon reporta ventas netas de IVA → tu break-even tiene que estar en la misma base.

**Confusión a evitar:** neto de IVA ≠ neto de fees. El fee es un **costo** que entra al break-even, no la definición del neto.

### A.1.2 — Break-even ACoS (techo de rentabilidad)
```
BE ACoS = margen disponible / neto
```
Requiere COGS real. **Sin COGS → estimación etiquetada** (ver A.1.6). Es un techo de rentabilidad, **NO** el punto de corte.

Trampas: no se hereda entre medidas del mismo modelo ni entre modelos. Sin BE calculado para una medida → no inventes proxy en el sistema de decisión; cortá por stop-loss en $.

### A.1.3 — Break-even CPC — LA FÓRMULA QUE DECIDE EL BID
```
Gasto permitido por venta = neto × BE_ACoS
Clicks por venta          = 1 / CVR
BE CPC                    = (neto × BE_ACoS) × CVR
```

**Sensibilidad (por qué el cluster importa):** mismo producto, mismo BE, el bid máximo cambia ~3× según el CVR. Si medís CVR mal (cluster fragmentado), tu techo de bid está mal por 3×.

**El diagnóstico más potente del método:**
```
Si BE CPC < piso de la subasta → término ESTRUCTURALMENTE inrentabilizable
```
No es problema de PPC — es de CVR (ficha/precio). "La publicidad no puede arreglar esto; el CVR sí." Convierte una tesis cualitativa en aritmética.

### A.1.4 — Stop-loss (punto de corte, en $)
Distinto del break-even. **BE = techo de rentabilidad (%). Stop-loss = cuánto tolero gastar sin venta antes de cortar ($).**

```
Techo por KEYWORD = neto × 10%, acotado a [piso, tope] del ANEXO
Techo por MODELO  = neto × factor de banda (agregado, cruza campañas)
```
Los factores de banda y los acotes **están en cada ANEXO** (recalibrados al ticket de la marca — los del método original eran para colchones en €, no aplican acá).

**El stop-loss ES la protección que te permite pujar arriba del break-even.** Si el objetivo es validar rápido, podés pujar sobre el BE CPC porque el stop-loss capea la pérdida. Eso se declara como compra de visibilidad consciente, no como jugada rentable.

### A.1.5 — Qué puede responder un test (antes de correrlo)
```
Clicks que compra el test = stop-loss / CPC
Ventas esperadas          = clicks × CVR
```
Si las ventas esperadas < 1 → el 0 no significa nada. El test no puede responder "¿convierte?", solo "¿aparecemos?" (impresiones). **Definí el criterio de éxito ANTES de correr el test y escribilo en el registro.**

### A.1.6 — Modo sin COGS (default operativo actual)
Mientras no haya COGS del AM:
- **NO se inventa BE.** El BE ACoS/BE CPC se corren solo como **estimación etiquetada**, usando el BE ACoS supuesto que fija cada ANEXO. Sirve para la conversación con el cliente ("con estos supuestos, esto no cierra"), **no para cortar**.
- **El corte real se hace por stop-loss en $** (dato duro).
- **El bid** se decide por palancas reales: CPC real vs impresiones vs ToS IS (¿aparecés? ¿ganás subasta?), capado por stop-loss.
- Todo número derivado de BE se escribe con el sufijo **`(est. — sin COGS)`**.

---

## A.2 — La secuencia 360° fusionada (orden de trabajo)

El 360° de Capybaras arranca por la capa orgánica (STR → SQP → cruzado), que el método SP-céntrico no cubre. El método arranca por Bulk (estado real). La fusión mantiene la capa orgánica adelante como **contexto de demanda**, e inserta la lectura de estado del método en el punto donde el 360° la necesita.

```
0. REGLAS PREVIAS      → D-3 · identificar clusters · verificar mapa (censo)
        ↓
── CAPA ORGÁNICA (Capybaras — el método no la tiene) ──
1. STR                 → qué búsqueda entró + cluster en vivo + derrame → cola de negativos
2. SQP                 → share orgánico de query (ImpShr / PurShr) → demanda y precio
3. CRUZADO STR × SQP   → framework de 5 buckets → dónde ganás/perdés orgánicamente
        ↓
── DESEMPATE DE ATRIBUCIÓN (Capybaras — resuelve lo que el método deja abierto) ──
4. BSR by child        → split orgánico/pagado por child → desambigua "Other SKU" (halo vs fuga)
        ↓
── CAPA PAGADA (motor del método) ──
5. CAMPAIGN            → dónde está la plata (motor/sangrado/joya) + hipótesis + OOB
6. ADVERTISED PRODUCT  → verificar por ASIN → ¿real o mirage?  [regla cardinal, cruza con paso 4]
7. PLACEMENT           → dónde se va el gasto (ToS/PDP/RoS) → sesga placement [si la cuenta lo expone]
8. TARGETING           → ToS IS fino + bid → sella visibilidad [si la cuenta lo expone]
        ↓
9. BSE (all-states)    → estado real para generar bulks: IDs, negativos vigentes, ENDED
        ↓
── DECISIÓN ──
10. ARITMÉTICA         → agregá cluster → CVR real → BE CPC (est.) vs piso → stop-loss $
11. DECISIONES         → bid · placement · budget · corte · escala
12. BULKS              → generar desde BSE, con fecha de upload por archivo
```

**Nota sobre el Bulk / BSE (doble uso):** el método lee el Bulk *al inicio* (estado real, negativos vigentes). En el 360° de Capybaras el BSE va *al final* porque su uso principal es **generar bulks** (trae los IDs numéricos). Consecuencia práctica: la lectura de **negativos vigentes** que el método hace en el paso 1, en este flujo se hace en el paso **1 (STR)** contra la cola de negativos y se **confirma contra el BSE del paso 9 antes de generar** (para no duplicar). Si en algún análisis necesitás el estado de negativos/ENDED antes de decidir, tirá un BSE de lectura temprana — es el mismo archivo.

**Por qué este orden funciona:** la capa orgánica te da la demanda y el precio (¿la gente busca esto? ¿a qué precio compra?) antes de mirar la plata pagada. El BSR by child resuelve la ambigüedad de "Other SKU" que el método admite no poder resolver solo. Recién ahí entra el motor pagado del método, que ya llega con contexto.

---

## A.3 — Los 9 reportes: qué responde cada uno

### 1. STR (Search Term Report)
`Targeting` (tu keyword) vs `Customer Search Term` (lo que buscó el cliente).
- Coinciden → match limpio · Difieren → derrame (evaluar negativo)
- **Mismo search term en varias campañas → cluster/canibalización (Regla 2, se ve en vivo acá)**
- Cazás: derrame a basura (negativizar), el cluster, términos con gasto y 0 conversión.
- **Antes de recomendar un negativo:** cruzalo contra el BSE (paso 9) para no duplicar uno vigente. Recordá los **dos niveles**: ad group (`Negative keyword`) y campaña (`Campaign negative keyword`).

### 2. SQP (Search Query Performance) — capa orgánica Capybaras
Share de la query: `Impression Share` y `Purchase Share` orgánicos.
- Te dice si **aparecés** en la query y si **cerrás** la compra, a nivel query, incluyendo orgánico.
- **El puente con la aritmética del método:** cuando el BE CPC diagnostica "estructuralmente inrentabilizable" (CVR muy bajo), el SQP te dice *por qué*: ImpShr decente + PurShr cero = aparecés pero no convertís → problema de precio/ficha, no de PPC. El método diagnostica el síntoma; el SQP da la causa orgánica.

### 3. Cruzado STR × SQP — framework de 5 buckets (capa orgánica Capybaras)
Cruce de lo que entró (STR) contra el share de query (SQP) para clasificar cada término en un bucket accionable (scale / fix / negativizar / investigar / defender). Es tu componente propio; el método no lo tiene.

### 4. BSR by child (Business Report by child item) — desempate Capybaras
Split **orgánico/pagado por child ASIN**. Esta es la pieza que **al método le falta**: el Advertised Product distingue `Advertised SKU` vs `Other SKU` pero **no dice qué se compró** — no separa halo sano (clic en medida A → compra medida B del mismo parent) de fuga real (clic en el bueno → compra el excluido). El BSR by child resuelve ese desempate. **Se usa como insumo del paso 6 (Advertised), no como reporte suelto.**

### 5. Campaign report
Ordenar por gasto. Marcar 3 zonas: **motor** (gasto alto + ROAS sano), **sangrado** (gasto alto + ROAS bajo/0), **joya** (ROAS altísimo + gasto mínimo).
- OOB + ROAS sano → subir budget · OOB + ROAS malo → contener · ROAS alto → **NO escalar sin Advertised**.
- Trampas: el ROAS acá es **agregado y puede ser mirage** (nunca base de decisión de escala). **SB/SD tienen atribución 14 días** — no compares su ROAS crudo contra SP (7 días) en ventana corta. El `Top-of-search IS` acá viene en buckets; el valor fino está en Targeting.

### 6. Advertised Product — el detector de mirages [regla cardinal]
Columnas que deciden: `Advertised ASIN`, `7 Day Advertised SKU Sales`, `7 Day Other SKU Sales`.
- **Mirage:** el cliente clickea el anuncio de A y compra B. La venta se atribuye a la campaña de A como Other SKU. La campaña se llama "A", pero quien vendió fue B.
- **Uso:** Campaign dice "rinde X" → Advertised dice "vendió el ASIN Y (Advertised u Other)" → cruzar Y contra el mapa **por parent/SKU, nunca por título** → si Y es familia excluida o no es el hero → **mirage, no escalar**.
- **Chequeo vacío:** verificar `Other SKU = 0` con `Total = 0` **no verifica nada**. Sin ventas no hay mirage que detectar.
- **Other SKU no es sinónimo de fuga:** halo sano (misma familia) vs fuga real (modelo excluido). El reporte no los separa → **acá entra el BSR by child (paso 4)** para desambiguar.
- Cualquier ROAS por ASIN **incluye Other SKU**. Si el 45% de tus ventas son Other, tus métricas por ASIN tienen 45% de ambigüedad — saberlo antes de presentar un número.

### 7. Placement report (si la cuenta lo expone)
SP tiene ToS · Product Pages · Rest of Search. **No existe modificador negativo** — el rango es 0% a +900%, no podés bajar Product Pages, solo subir ToS/RoS para sesgar. Cualquier plan de "bajar Product Pages" es inejecutable. `Bid efectivo ToS = bid × (1 + mod ToS)`. Patrón a cazar: 78% del gasto en PDP y casi nada en ToS = no validás la keyword, validás prospecting lateral.

### 8. Targeting report (si la cuenta lo expone)
Trae el **ToS IS en valor fino** (Campaign da buckets). ToS IS <1% = casi no aparecés arriba aunque gastes → explica por qué un head term "no funciona": no lo probaste, no ganaste la subasta. Ausencia de data ≠ conclusión (11 impresiones no es un test). **Suggested bid: ignorar** (Amazon maximiza sus impresiones, no tu margen). Prueba real de underbidding: si `CPC real ≈ tu bid` **y** hay impresiones → estás ganando subastas, no hay underbidding.

### 9. BSE (Bulk Sheet Export, all-states)
Única fuente con Campaign/Ad Group IDs y negativos vigentes. Filtrar por `Entity` → Campaign / Ad Group / Keyword / **Negative keyword** / **Campaign negative keyword** / Product Ad / Bidding Adjustment.
- **Dos exports distintos:** el de *performance* (con fechas) trae métricas pero filas de keyword/negativo **vacías**. El *Bulk Sheet Export* completo trae la estructura. **Validación:** si `Entity` no tiene ninguna fila `Negative keyword` → export equivocado, **parar, no inferir negativos por ausencia**.
- **ENDED ≠ ENABLED.** UPDATE sobre campañas ENDED puede hacer **fallar todo el upload** (rollback total). Filtrar por state antes de generar.

### Cómo bajar los reportes (aprendido en campo, 2026-07-23)
- **Advertised / Campaign desde la vista de tabla viene AGREGADO** — una fila por combinación campaña/adgroup/SKU, sin corte temporal. Para análisis con ventanas hay que bajarlo desde **Measurement & Reporting con `Time unit: Daily`**. El daily reemplaza `Start Date`/`End Date` por una sola columna `Date`.
- **El Targeting report SÍ expone `Top-of-search Impression Share`** en valor fino (fracción numérica). Es el **único** reporte que lo da a nivel target — el Campaign lo da en buckets.
- **El Campaign report de vista de tabla trae ToS IS y `Top-of-search bid adjustment`** por campaña. Útil aunque venga agregado.
- **Placement: bajar por ventana chica, NUNCA largo.** Si se baja agregado se pierde el corte PRE/POST necesario para medir cualquier test de placement.
- **Amazon topea las descargas de Ads a ~90 días** hacia atrás.
- **Auditoría iterativa de entregables:** cada corrección abre superficie nueva. En un caso real, 5 pasadas sobre un HTML: la 1ª encontró 4 errores de dato, la 2ª 5 inconsistencias, la 3ª 3 de encuadre, la 4ª 2 introducidos por la 3ª, la 5ª 1 residuo de la 4ª. **Regla: cuando las pasadas solo encuentran residuos de correcciones previas, parar.**

### Nota sobre el WoW (reporte semanal)
El WoW debe incluir el **split Advertised / Other SKU en Ad Sales**. Sin ese corte no se distingue el orgánico puro del atribuido, y se generan lecturas falsas de atribución (un ASIN puede parecer sostenido por ads cuando en realidad vende orgánico, o al revés).

---

## A.4 — Las 5 decisiones

### DECISIÓN 1 — El bid
```
1. Agregá el cluster (Regla 2) → CVR real
2. BE CPC = neto × BE_ACoS × CVR   [est. si no hay COGS]
3. Compará contra el piso de la subasta (CPC real del nicho)
```
| Situación | Decisión |
|---|---|
| BE CPC > piso, CPC actual < BE CPC | Hay espacio. Subir con margen |
| BE CPC > piso, CPC actual > BE CPC | Arriba del techo. Bajar o pérdida consciente |
| **BE CPC < piso** | **Estructuralmente inrentabilizable. No hay bid. El problema es CVR** |

**Sin COGS:** el BE CPC es estimado — no lo uses para cortar. Decidí subir/bajar por CPC real vs impresiones vs ToS IS, capado por stop-loss. Pujar arriba del BE = compra de visibilidad declarada, protegida por stop-loss.

**Cuándo NO bajar al BE:** si el BE CPC está debajo del piso, pujar ahí = no aparecer = no aprendés nada. Peor que gastar el stop-loss completo y saber.

### DECISIÓN 2 — El placement
Solo se sube, nunca se baja (no hay modificador negativo). Si el ToS IS es <1%, no tenés data de ToS: probá con modificador agresivo + stop-loss, o aceptá que no vas a saber. **Criterio de éxito del test de ToS = impression share, no ventas.**

### DECISIÓN 3 — El budget
| Situación | Decisión |
|---|---|
| OOB + ROAS sano | Subir. Cada día OOB es venta que no entra |
| OOB + ROAS malo | Contener. Subir es acelerar la pérdida |
| No OOB | El budget no es el limitante — el bid o el stop-loss lo son |

Si el bid es bajo, el budget nunca es el constraint. No lo toques.

### DECISIÓN 4 — El corte
```
Cortar cuando: gasto ≥ stop-loss  Y  0 ventas  Y  ventana fuera de D-3
```
- Nunca cortar dentro de D-3. El techo es límite de seguridad, no obligación de gastar: podés cortar antes **por diagnóstico cerrado** (agotaste bid, placement, matching), no por impaciencia, y con la ventana cerrada.
- **Pausar la keyword, no la campaña:** preserva estructura, es reversible, mantiene la audiencia para retargeting.

### DECISIÓN 5 — La escala
```
NUNCA escalar sin pasar por el Advertised Product.
```
| Chequeo | Si falla |
|---|---|
| ¿La venta es `Advertised SKU`? | Si es `Other SKU` → verificá qué se compró (BSR by child) |
| ¿El ASIN es el esperado (parent)? | Si es familia excluida → mirage, contener |
| ¿El ROAS es del cluster o suelto? | Si es suelto → recalculá agregado |
| ¿La muestra sostiene la conclusión? | n=1 no valida. Da más data, no escales de golpe |

---

## A.5 — Las 12 trampas

| # | Trampa | Cómo se caza |
|---|---|---|
| 1 | Mirage de ASIN | Advertised → `Other SKU Sales` + parent |
| 2 | Mirage de cluster | Agregar close variants antes de calcular |
| 3 | Chequeo vacío | Si no hay ventas, no verificaste nada |
| 4 | D-3 circular | Ningún reporte cierra D-3 |
| 5 | Suggested bid | CPC real ≈ bid + hay impresiones = no underbidding |
| 6 | Ausencia = conclusión | 11 impresiones no es un test |
| 7 | Export equivocado | Si `Entity` no trae `Negative keyword` → parar |
| 8 | UPDATE sobre ENDED | Filtrar por state antes de generar |
| 9 | Muerte silenciosa | Amazon sirve **una** campaña por subasta (mayor ad rank) |
| 10 | BE heredado | No se hereda entre precios/medidas/modelos |
| 11 | Proxy inventado | Sin BE → cortar por stop-loss ($ real) |
| 12 | n=1 | Calculá ventas esperadas antes de concluir |

**Trampa 9 (la más silenciosa):** si lanzás una campaña nueva sobre un término que ya corre en otra tuya con bid menor, matás la vieja sin registro (deja de servir, no da error). Mejor pausarla explícitamente.

---

## A.6 — Los hallazgos que SOLO aparecen cruzando

1. **Mirage** = Campaign (ROAS alto) × Advertised (venta de otro ASIN)
2. **Cluster** = STR (mismo término, varias campañas) × Campaign (sumar gasto)
3. **Invisibilidad con gasto** = Placement (78% en PDP) × Targeting (ToS IS 0,1%)
4. **Canibalización real** = STR × BSE (negativos faltantes, dos niveles)
5. **Halo vs fuga** = Advertised (Other SKU) × BSR by child (qué se compró) — *aporte Capybaras*
6. **Precio como causa de CVR** = BE CPC < piso (método) × SQP ImpShr alto + PurShr cero (Capybaras)

---

## A.7 — Checklist de auditoría

**Antes de mirar números:**
- [ ] D-3 aplicado
- [ ] Clusters identificados (close variants agrupados)
- [ ] Mapa de ASINs verificado contra el Advertised (¿falta alguno que se anuncia?)

**Los 9 reportes:**
- [ ] STR: derrame + cluster en vivo + cola de negativos (dos niveles)
- [ ] SQP: ImpShr / PurShr por query (capa orgánica)
- [ ] Cruzado STR×SQP: 5 buckets asignados
- [ ] BSR by child: split orgánico/pagado listo para desambiguar Other SKU
- [ ] Campaign: zonas marcadas. ¿OOB con ROAS sano? (ojo SB/SD 14 días)
- [ ] Advertised: verificado por parent. ¿`Other SKU`? ¿el chequeo tiene ventas que verificar?
- [ ] Placement: reparto ToS/PDP/RoS · bid efectivo ToS · ¿gasto sesgado a PDP? (si la cuenta lo expone)
- [ ] Targeting: ToS IS fino · suggested ignorado · test de underbidding (CPC≈bid + impresiones) (si la cuenta lo expone)
- [ ] BSE: ¿es el completo? ¿trae `Negative keyword`? ¿hay ENDED?

**Aritmética:**
- [ ] Neto = PVP/(1+IVA) según ANEXO, no PVP−fees
- [ ] CVR medido a nivel cluster
- [ ] BE CPC calculado (etiquetado est. si sin COGS) y comparado contra el piso
- [ ] Stop-loss definido (keyword y modelo) según ANEXO
- [ ] Criterio de éxito del test declarado ANTES de correrlo

**Decisiones:**
- [ ] Ninguna escala sin verificación por parent ASIN
- [ ] Ningún corte dentro de D-3
- [ ] Ningún negativo duplicado (cruzado contra BSE)
- [ ] Ningún UPDATE sobre campañas ENDED
- [ ] Todo bid arriba del BE declarado como compra de visibilidad, no jugada rentable

**Bulks:**
- [ ] IDs numéricos como texto (`str(v).split('.')[0]` + formato `@`)
- [ ] Verificar processing summary: Amazon marca todo como Failed si una fila falla
- [ ] Negative Product Targeting requiere Ad Group ID a nivel ad group
- [ ] **Fecha de upload especificada por cada archivo entregado** (tabla archivo → fecha)

---

# PARTE B — ANEXO US · Dermaglos (Amazon.com)

**Marketplace:** US. **Neto = PVP directo** (el sales tax se agrega en checkout, Amazon lo recauda aparte, no aparece en reportes de Ads → no se divide).

```
Neto_Dermaglos = PVP
```

**BE ACoS de cuenta = 60%** (provisto por el operador; usar hasta tener COGS por familia).
> Nota: 60% es un BE ACoS alto — implica margen de contribución amplio. Confirmar con COGS por familia cuando el AM lo pase; hasta entonces todo BE CPC derivado lleva `(est.)`.

**BE CPC (est.):**
```
BE CPC = PVP × 0.60 × CVR_cluster
```

**Stop-loss (recalibrado — sin ticket fino de catálogo, se basa en BE 60%):**
```
Techo por KEYWORD = PVP × 10%   (acote [ , ] — completar con rango de ticket real)
Techo por MODELO  = PVP × 0.50  (banda única provisional; el BE 60% da margen a un stop-loss alto)
```
> ⚠️ **Slot a completar:** rango de ticket (mín/máx/grueso) de Dermaglos para cerrar los acotes del techo por keyword y afinar la banda por modelo. Hasta entonces, banda por modelo provisional al 50% del neto.

**Config pendiente (Parte 6 del método):**
- [ ] Mapa de ASINs (parent/familia/línea/medida, por SKU) — verificar contra Advertised
- [ ] Familias excluidas — completar
- [ ] COGS/BE por familia — pendiente AM; hasta entonces BE ACoS 60% de cuenta (est.)
- [ ] Rango de ticket para stop-loss

---

# PARTE C — ANEXO MX · LTD / Love To Dream (Amazon.com.mx)

**Marketplace:** MX. **IVA 16% incluido en el precio.**
```
Neto_LTD = PVP / 1.16
```
**Validación del /1.16:** confirmada a nivel estructural con data real de MX (una venta reportada rinde ~0.85 del PVP lista, consistente con neto de IVA; si dividiera 1.0 no habría IVA descontado). ✅ **Validado estructural.** Para el clavado exacto (0.862), tomar una venta de **una sola unidad a precio lista** y verificar `Sales / PVP = 0.862`.

**Ticket:** catálogo $809–$1,069 MXN. **Modal/grueso = $859** (familia Swaddle UP regular). Transition ($1,040–1,069) = volumen bajo.
```
Neto típico = 859 / 1.16 = $740.5 MXN
```

**BE ACoS:** sin COGS → **estimación etiquetada**. Placeholder de cuenta sugerido: usar el **target ACoS de cuenta (~25–30%)** como proxy de trabajo, NO como BE rentable. Correr BE CPC como `(est. — sin COGS)`.
```
BE CPC (est.) = 740.5 × 0.30 × CVR_cluster
```

**Stop-loss (recalibrado al ticket MXN):**
```
Techo por KEYWORD = neto × 10% = ~$74 MXN, acotado [$60, $150] MXN
Techo por MODELO  = neto × 0.28 = ~$207 MXN por modelo (banda media)
```
> Nota: la banda 28% se hereda del rango medio del método, razonable para neto ~$740. Ajustar cuando entre COGS.

**Config:**
- [ ] Mapa de ASINs — hay snapshot en vault (heroes B0F8PCWD6J, B09MG1PM6L OLV S, etc.); verificar contra Advertised
- [ ] Familias excluidas — completar (los 2 productos no-rentables del BR de marzo son candidatos)
- [ ] Hero B09MG1PM6L: pausa de bulk en hold hasta BSE fresco (regla vigente)

**Validación empírica del método (Prime Day / genéricos):**
El hallazgo "LTD necesita estar a ≤1.2x del precio de mercado para convertir en genéricos" es **reproducible por dos caminos que convergen**:
1. **Camino BE CPC:** en genéricos con gap de precio alto, el CVR → 0 → BE CPC = neto × BE_ACoS × CVR → 0 → cae debajo del piso de subasta → estructuralmente inrentabilizable.
2. **Camino piso de subasta / SQP:** ImpShr decente + PurShr cero (aparecés pero no cerrás por precio) → el piso no baja, vos no convertís.
Ambos caminos dicen: en `saco de dormir` genérico (categoría 1.8x más cara para LTD) no hay bid que funcione — es CVR/precio, no PPC. LTD gana en producto diferenciado (`swaddle`, `swaddle up`, nichos recién nacido). **Cuando corramos el próximo análisis, cargar los números reales de Prime Day y verificar que el BE CPC calculado cae bajo el piso observado — es el test de que el método reproduce el hallazgo empírico.**

---

# PARTE D — ANEXO MX · Setex (Amazon.com.mx)

**Marketplace:** MX. **IVA 16% incluido.**
```
Neto_Setex = PVP / 1.16
```
**Validación del /1.16:** ✅ validado estructural (mismo check MX, ver Anexo C).

**Ticket:** catálogo $240–$320 MXN. Nose pads (top sellers) $240, temple tips $270, ear hooks $320. **Modal/grueso = $240.**
```
Neto típico = 240 / 1.16 = $206.9 MXN
```

**BE ACoS:** sin COGS → estimación etiquetada. **TACoS objetivo de cuenta = 18%** (del vault). Usar como proxy de trabajo, no como BE rentable.
```
BE CPC (est.) = 206.9 × [BE_ACoS proxy] × CVR_cluster
```
> Ticket bajo ($207 neto): el margen de maniobra en $ es chico. El stop-loss por keyword cae muy bajo si se aplica 10% literal → se levanta el acote (abajo).

**Stop-loss (recalibrado al ticket bajo):**
```
Techo por KEYWORD = neto × 10% = ~$21 MXN → demasiado bajo, ACOTAR a mínimo [$40, $80] MXN
Techo por MODELO  = neto × 0.30 = ~$62 MXN por modelo (banda baja, ticket < 175 USD-equiv no aplica; acá banda baja MXN)
```
> ⚠️ El 10% literal sobre neto $207 da $21, que corta demasiado rápido (1–2 clicks). Para Setex el techo por keyword se acota a un piso de $40 MXN para que el test compre suficientes clicks. Recalibrar con COGS.

**Config:**
- [ ] Mapa de ASINs — hay tabla en vault (B081GB8F89 1mm top seller, B09HVXDH7M 1.8mm, B08PZF22R1 nano, temple tips, ear hooks); verificar contra Advertised
- [ ] Familias excluidas — completar
- [ ] Watch: B08SNXF8HP (BuyBox 91%, único con pérdida real) y doble-SKU CLOSED en B081GB8F89 (revisar que no reincida)

---

# NOTAS DE VERSIÓN

- **v1 (hoy):** core fusionado + 3 anexos, modo sin-COGS operativo. Neto MX validado estructural. Stop-loss recalibrado a tickets reales (LTD $859 / Setex $240). Dermaglos con BE ACoS 60% dado, ticket pendiente.
- **v1.1 (2026-07-23):** Placement y Targeting promovidos de sub-bloques del Advertised (paso 6) a **pasos propios (7 y 8)** en la secuencia A.2, en el catálogo A.3 y en el checklist A.7. La cuenta pasa de **7 a 9 reportes**. BSE corre a paso 9; aritmética/decisiones/bulks a 10-12 (refs internas "BSE del paso 7" actualizadas a paso 9). Se mantiene la condicionalidad *si la cuenta lo expone* en los tres lugares: Amazon no siempre expone Placement/Targeting (ej. SD) → cuando falta, el paso se salta y se documenta la ausencia.
- **v1.2 (2026-07-24):** agregada **Regla 4 — runway de stock** como cuarta regla previa dura (con tabla de corte <15d / 15-25d / >25d / >300d), validada en producción en Setex. Agregada nota sobre el split Advertised/Other SKU en el WoW. Corolario: las alertas de stock se registran con destinatario, controlador y fecha.
- **Pendientes para v2:** COGS por familia (activa BE rentable) · ticket Dermaglos · mapas de ASINs verificados contra Advertised por cuenta · familias excluidas · clavado exacto del 0.862 con venta unitaria MX.
- **Vive en:** `notes/sops/` del vault. Registrar vía chat consolidador (este chat no toca git).
