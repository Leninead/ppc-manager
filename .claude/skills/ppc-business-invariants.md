# PPC Business Invariants

Reglas duras que TODA recomendación o export del Agency OS debe cumplir.
No son preferencias de estilo: son condiciones que, si se violan, producen
output que daña cuentas de clientes reales.

Aplica a: M2 (STR), M4 (Análisis Cruzado), M10/Campaign Builder, Bid Optimizer,
y cualquier módulo que genere bulks o recomiende bids, negativos o harvest.

---

## INV-1 — Techo de bid

Ningún bid recomendado puede superar `precio × (target_acos / 100)`.

Razón: un bid por encima de ese valor garantiza ACoS > target incluso con
CVR del 100%. Es matemáticamente imposible que sea rentable.

- Piso: 0.10 (mínimo de Amazon)
- Techo: `precio × (target_acos / 100)`
- El CVR usado en la fórmula se clampea a ≤ 100% antes de multiplicar

Fórmula canónica: `bid = clamp(0.10, cvr_clamped × precio × target_acos/100, precio × target_acos/100)`

## INV-2 — No se negativiza lo que convierte

Un término con `orders > 0` NUNCA se exporta como negativo
(`negativeExact` / `negativePhrase`), sin importar su ACoS.

Si el ACoS es malo pero hay órdenes, la acción es **bajar bid** o **revisar**,
nunca negativizar. Negativizar mata la conversión y el ranking orgánico
asociado al término.

Excepción: ninguna. Si un caso parece requerirla, es un bug de clasificación.

## INV-3 — Piso de significancia

Fuente: Capybaras Launch SOP v2026, sección 5.1 y tabla de métricas objetivo.
Reemplaza los tiers por precio usados antes, que eran una aproximación.

### Threshold de clicks para negativizar

`clicks_minimos = max(10, (1 / CVR_producto) × 2)`

Donde `CVR_producto` es el CVR del producto, no del search term.

| CVR producto | Clicks sin orden requeridos |
|---|---|
| 20% | 10 (mínimo absoluto) |
| 10% | 20 |
| 5%  | 40 |
| 2%  | 100 |

Regla global #10 del SOP: por debajo de este umbral se están matando
keywords por falta de estadística, no por mal rendimiento.

### Threshold de spend para negativizar

`spend_minimo = precio_de_venta × 0.50`

Producto de $30 → negativizar si gastó $15 sin ventas.

### Otros pisos

- Harvest por CVR alto: `CVR >= 10% AND clicks >= 15`
- Harvest principal: `orders >= 3 AND acos <= 25%`
- Harvest por volumen: `orders >= 5` (sin techo de ACoS, ver INV-4)
- CTR bajo: `impresiones >= 2500 AND ctr < 0.18% AND orders == 0`
  (500 impresiones es insuficiente)

## INV-4 — Techo de ACoS en harvest

Fuente: SOP v2026, tabla de reglas de harvesting.

| Regla | Criterio | Techo de ACoS |
|---|---|---|
| Principal | `orders >= 3 AND acos <= 25%` | implícito en el criterio |
| Por CVR alto | `cvr >= 10% AND clicks >= 15` | configurable, default `target × 3` |
| Por volumen | `orders >= 5` | **SIN TECHO — por diseño del SOP** |

La regla de volumen es deliberadamente independiente del ACoS: el SOP
prioriza impacto en ranking orgánico sobre eficiencia. Un término con
5+ órdenes y ACoS alto se harvestea igual.

No "arreglar" esto. Si aparece como hallazgo en una revisión, es
comportamiento correcto.

Destino del harvest (SOP sección 6): campaña Exact dedicada en portfolio
PROFIT, bid = suggested bid, ToS modifier +25%. Además: bajar bid del
término en la campaña de origen, y opcionalmente agregarlo como negative
exact ahí. Son 3 bulks, no uno.

## INV-5 — Contrato del bulk de Amazon

Validado empíricamente 2026-08-26 contra uploads reales (cuenta LTD MX).
Fuentes: F0-1_negativos (Success 4/4), F0-2_fix_bid (Success 1/1),
F2-1_campana_nueva (Success 6/6), report__60_ (Failed 0/8).

### INV-5.1 — Los dos modos de ID

Amazon acepta dos cosas distintas en `Campaign ID` / `Ad Group ID`, según
si la entidad ya existe:

**Modo REFERENCIA (entidad existente en la cuenta):**
El ID debe ser el numérico real de Amazon (~15 dígitos).
Aplica a: negativos sobre campañas existentes, updates de bid, pausas.
Ejemplo validado: `Campaign ID = 132313349237695`.
Un nombre de campaña en este campo NO resuelve.

**Modo ALIAS (entidad creada en el mismo archivo):**
El ID puede ser un string arbitrario que linkea filas dentro del XLSX.
Amazon lo resuelve al crear y asigna los IDs reales.
Aplica a: creación completa de campaña (Campaign + Ad Group + Product Ad + Keyword).
Ejemplo validado: `Campaign ID = 'SU-AGE-HARVEST-001'` repetido en las 4 filas.

Regla: si la fila toca algo que ya existe en la cuenta, va ID numérico.
Si la fila crea algo cuyo padre también se crea en el archivo, va alias.
Nunca mezclar los dos criterios en la misma fila.

### INV-5.2 — Entities y sus campos obligatorios

| Entity | Campaign ID | Ad Group ID | Keyword ID | Match Type |
|---|---|---|---|---|
| `Campaign Negative Keyword` | numérico | **vacío** | vacío | `Negative Exact` / `Negative Phrase` |
| `Negative Keyword` | numérico | numérico | vacío | `Negative Exact` / `Negative Phrase` |
| `Keyword` (Create) | numérico o alias | numérico o alias | vacío | `Exact` / `Phrase` / `Broad` |
| `Keyword` (Update bid) | numérico | numérico | **numérico** | `Exact` / `Phrase` / `Broad` |
| `Campaign` (Create) | alias | vacío | vacío | vacío |
| `Ad Group` (Create) | alias | alias | vacío | vacío |
| `Product Ad` (Create) | alias | alias | vacío | vacío |

`Campaign Negative Keyword` con `Ad Group ID` lleno es un error de nivel:
el negativo a nivel campaña no pertenece a ningún ad group.

### INV-5.3 — Valores canónicos

Strings exactos, tomados de bulks aceptados por Amazon:

- `Product`: `Sponsored Products`
- `Operation`: `Create` | `Update`
- `State`: `enabled` | `paused` | `archived`
- `Match Type` positivos: `Exact` | `Phrase` | `Broad`
- `Match Type` negativos: `Negative Exact` | `Negative Phrase`

PROHIBIDO: `campaignNegativeExact`. Rechazado por Amazon con
`Invalid value: "campaignNegativeExact" for column: "Match Type"`
(report__60_, 8/8 filas rechazadas).

Los valores camelCase (`negativeExact`, `exact`) NO tienen validación
empírica. Usar siempre Title Case, que sí la tiene.

### INV-5.4 — Rollback total

Una sola fila inválida rechaza el ARCHIVO COMPLETO.
Evidencia: report__60_ → "no change was applied", 0 de 8 procesadas,
siendo el único defecto un valor de Match Type.

Consecuencia de diseño: todo módulo que genere bulks DEBE validar antes
de habilitar la descarga. Un bulk con una fila mala no es un archivo
imperfecto: es una sesión de trabajo perdida. La validación va antes del
`st.download_button`, no después.

### INV-5.5 — Columnas

Template validado: 26 columnas. Las columnas anexas (Prioridad, Regla,
Customer Search Term, notas) van en hoja separada, NUNCA en la hoja
`Sponsored Products Campaigns`.

Otras reglas heredadas y aún vigentes:
- Negative Product Targeting requiere Ad Group ID
- `Start Date` formato `YYYYMMDD`

## INV-6 — Toda fila se clasifica

Ningún término termina en un bucket catch-all (`"—"`, `None`, vacío).

Si la lógica no puede clasificar una fila, la rama por defecto es explícita
y nombrada (ej. `"Sin datos suficientes"`), y se cuenta y se muestra.
Un bucket silencioso esconde errores de parseo.

## INV-7 — ACoS tiene una sola fuente de verdad

`acos = (spend / sales) × 100 if sales > 0 else None`

- `None` cuando no hay ventas — nunca 0, nunca 999
- Se calcula en UN solo helper compartido
- No se mezcla el ACoS del archivo con el recomputado en la misma vista

Un ACoS de 0 se lee como "excelente" en cualquier semáforo. Es el peor
default posible para el caso "no vendió nada".

## INV-8 — Sin mutación de estado compartido

Una tab no agrega, renombra ni elimina columnas del DataFrame que recibe.

Si necesita columnas derivadas, trabaja sobre una copia (`df.copy()`).
Mutar el df compartido hace que el resultado dependa del orden en que
el usuario abrió las tabs.

## INV-9 — Lo que se ve es lo que se exporta

Si la vista muestra N filas candidatas y el export trae M < N, la UI dice
explícitamente cuántas se omitieron y por qué.

El export nunca se arma desde el DataFrame ya filtrado por controles
visuales sin avisar.

## INV-10 — Anti-self

Nunca se negativiza la keyword pivote de la propia campaña, ni se targetea
el ASIN propio.

Requiere cruce con Campaign CSV o catálogo de marca. Si ese input no está
disponible, la funcionalidad se ofrece pero advierte que el guard está inactivo.

## INV-11 — Nunca negativizar contra el ranking

Fuente: SOP v2026, regla global #5 y sección 5.2. Es la regla más
importante del set: violarla destruye posición orgánica, que no se
recupera ajustando bids.

### INV-11.1 — Exclusión dura por match type de origen

Los negativos se aplican SOLO a términos provenientes de campañas
Auto, Broad y Phrase.

Términos que vienen de campañas Exact o Product Targeting NO son
candidatos a negativización. No aparecen en la tabla de candidatos,
no se pre-tildan, no se exportan. Es un filtro previo, no una opción.

Si una keyword en Exact rinde mal, la acción es bajar bid o pausar.

### INV-11.2 — Guard anti-Exact-activo

Un search term que existe como keyword Exact activa en cualquier
campaña de la cuenta NO se negativiza, aunque tenga ACoS alto en
Broad o Phrase.

Requiere cruce contra las keywords Exact enabled de la cuenta.
Fuente del dato: hoja `Sponsored Products Campaigns` del Bulk File,
filtrando `Entity == 'Keyword'`, `Match Type == 'Exact'`,
`State == 'enabled'`.

Si ese cruce no está disponible, la funcionalidad advierte que el
guard está inactivo (ver INV-10).

### INV-11.3 — Ranking keywords: default seguro

Términos provenientes de campañas en portfolio RANKING se marcan
por defecto como ranking keyword y NO se negativizan salvo que el
usuario lo desmarque explícitamente, término por término.

El default se invierte respecto de lo intuitivo a propósito: el costo
de no negativizar algo negativizable es unos dólares de spend; el costo
de negativizar una ranking keyword es posición orgánica perdida.

Fuente del dato: columna `Portfolio Name (Informational only)` de la
hoja `SP Search Term Report` del Bulk File.

### INV-11.4 — Regla 4 (ACoS extremo) no negativiza

`acos > 70% AND orders < 5` produce la acción **bajar bid**, nunca
un negativo directo. Solo si el problema persiste tras bajar el bid,
y el término no es ranking keyword, se evalúa negativizar.

Esta es la redacción del SOP, no una interpretación.

---

## Cómo se usa este skill

- `code-reviewer`: agrega estas 11 invariantes como checks. Cualquier
  violación es severidad 🔴, no ⚠️.
- `testing-agent`: cada invariante debe tener al menos un test que la
  verifique con datos sintéticos que la violen.
- Cualquier agente que genere bulks: valida contra INV-5 antes de entregar.
