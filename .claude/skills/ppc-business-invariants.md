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

Ninguna recomendación se emite sobre una sola observación.

- Negativizar requiere: `clicks >= threshold_tier` AND `orders == 0`
- Harvest requiere: `orders >= 2` como mínimo absoluto
- Agregar (M4) requiere: `purchases >= 2`

Thresholds por tier de precio (clicks sin orden para negativizar):

| Tier  | Precio    | Clicks | Spend |
|-------|-----------|--------|-------|
| LOW   | < $12     | 18     | $15   |
| MID   | $12–$22   | 22     | $22   |
| HIGH  | > $22     | 28     | $30   |

## INV-4 — Techo de ACoS en harvest

No se hace harvest de un término perdedor.

`acos <= target_acos × 3` es el techo. Un término con ACoS 178% no se
promociona a exact match aunque tenga volumen de órdenes: se está
escalando una pérdida.

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

---

## Cómo se usa este skill

- `code-reviewer`: agrega estas 10 invariantes como checks. Cualquier
  violación es severidad 🔴, no ⚠️.
- `testing-agent`: cada invariante debe tener al menos un test que la
  verifique con datos sintéticos que la violen.
- Cualquier agente que genere bulks: valida contra INV-5 antes de entregar.
