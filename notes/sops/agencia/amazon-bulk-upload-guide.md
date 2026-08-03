---
tipo: sop
actualizado: 2026-06-08
ambito: agency-wide
---

# Amazon Bulk Upload Guide — Capybaras Agency

Guía operativa para subir bulks (Sponsored Products / Brands / Display) a Amazon Ads Console sin que Amazon los rechace y sin corromper la cuenta. Aplica a todos los clientes y a todas las operaciones que hagamos via Bulk (crear / update / pausar / negativizar / harvest).

## Cuándo usar bulk vs Campaign Manager UI

| Operación | Vía recomendada |
|---|---|
| Crear N ≥ 3 campañas con misma estructura | Bulk |
| Aplicar 10+ negativos a 5+ campañas | Bulk |
| Update masivo de bids o budgets | Bulk |
| Pausar/reactivar > 5 campañas | Bulk (con IDs numéricos reales) |
| Crear 1 campaña aislada | UI |
| Editar audiencia de 1 SD | UI |
| Cambios que el bulk rechaza por carácter (ej `%`) | UI |

## Workflow estándar

1. **Antes de generar el bulk** descargar `BulkSheetExport` desde Campaign Manager → Bulk Operations → Download. Sirve para extraer Campaign IDs / Ad Group IDs reales y para verificar qué campañas existen actualmente (no confiar en analyzers cacheados).
2. Generar el bulk via [[campaign_builder]] o el módulo correspondiente. Validar columnas requeridas según tipo (SP=31, SD=47).
3. Abrir y revisar SOLO en Excel (NO Google Sheets — ver gotcha #4 más abajo).
4. Subir a Amazon Ads Console → Bulk Operations → Upload.
5. **Esperar el reporte de Amazon**. Records OK / Records Failed con detalle de error.
6. Si fallan records: leer error, fixear, regenerar bulk solo con records faltantes, re-subir.
7. Documentar en el daily del cliente: qué se subió, cuántos records OK/fail, qué quedó pendiente manual.

## Reglas duras

- **Nunca** subir un bulk sin haber descargado el `BulkSheetExport` actualizado primero.
- **Nunca** abrir el bulk en Google Sheets antes de subirlo (corrompe IDs largos).
- **Nunca** asumir que un campaign analyzer / module local refleja el estado actual de la cuenta. La fuente de verdad es siempre `BulkSheetExport`.
- **Siempre** mantener una sola hoja en el archivo (`Sponsored Products Campaigns` para SP). Las hojas extra (resumen, notas) hacen que Amazon rechace todo el archivo.
- **Siempre** documentar qué Bulk se subió en el daily del cliente con fecha y cantidad de records OK/fail.

## Learnings 2026-04-28 — sesión Dermaglos

8 gotchas críticos descubiertos hoy ejecutando 3 bulks (negativos, campañas nuevas, harvest) en cuenta Dermaglos USA. Detalle de la sesión en [[2026-04-28]].

### 1. Negative Keyword vs Campaign Negative Keyword (ENTITIES DISTINTAS)

| Entity | Aplica a | Requiere Ad Group ID |
|---|---|---|
| `Negative Keyword` | Nivel **Ad Group** | ✅ Sí |
| `Campaign Negative Keyword` | Nivel **Campaña** | ❌ No |

Si querés negativizar a nivel campaña, usar SIEMPRE `Campaign Negative Keyword`. Match types soportados: solo `negativeExact` y `negativePhrase` (NO `negativeBroad`).

**Cómo se manifestó hoy**: Bulk 05 v1 falló con "Missing Parent ID" porque usamos `Negative Keyword` sin Ad Group ID. Fix: cambiamos a `Campaign Negative Keyword` y los 46 records pasaron OK.

### 2. Campaign IDs y Ad Group IDs según operación

| Caso | Campaign ID / Ad Group ID |
|---|---|
| Crear campaña + ad group + keywords en el **mismo bulk** | Usar **Campaign Name / Ad Group Name** (string). Amazon hace match interno por nombre. |
| Crear keywords/negativos en **campañas YA existentes** | Usar **ID numérico real** (descargar BulkSheetExport antes). |
| Update bids / Update state | Usar **ID numérico real** |

Workflow: ANTES de modificar campañas existentes via bulk → Campaign Manager → Bulk Operations → Download campaigns → cruzar con el bulk.

**Cómo se manifestó hoy**: Bulk 05 v2 falló porque usamos Campaign Name string para negativos en campañas existentes. Fix: cruzamos con BulkSheetExport para extraer Campaign IDs numéricos reales.

### 3. Start Date debe ser TEXTO no float

- ✅ `20260428` (string)
- ❌ `20260428.0` (float, Amazon rechaza silencioso)

Helper code Python (openpyxl):

```python
cell.number_format = "@"
value = str(value).split(".")[0]
```

### 4. Google Sheets corrompe IDs numéricos largos

NO abrir el bulk en Google Sheets antes de subir. Los IDs como `497286372972562` se transforman a notación científica `4.97E+14`. Siempre subir el `.xlsx` original. Si necesitás revisar visualmente, abrir en Excel local con la columna formateada como Texto.

### 5. Caracteres especiales en keywords

Los siguientes caracteres pueden causar rechazo de Amazon:

- `%` confirmado rechazo (`allantoin 0.5% cream` falló en bulk Dermaglos 28/04)
- Punto + decimal puede causar problemas según contexto

**Workaround**: usar variantes (`allantoin .5 cream`, `allantoin half percent cream`) o agregar manual via Campaign Manager UI (a veces el UI sí acepta lo que el bulk rechaza).

### 6. Campaign Analyzer puede mostrar campañas YA ELIMINADAS

El campaign-wise analyzer puede tener snapshot desactualizado. Antes de tomar decisiones de pausa o budget, **cruzar siempre con BulkSheetExport actualizado**. En la sesión 28/04 Dermaglos: el analyzer mostraba 114 camps, BulkSheetExport mostraba 84 reales (30 zombies del analyzer ya eliminadas).

### 7. SD bulk schema diferente de SP

SD tiene 47 columnas vs 31 de SP. Incluye `Tactic`, `Bid Optimization`, `Cost Type`, `Targeting Expression`. Si vas a tocar SD via bulk, generar archivo con schema SD-específico — usar plantilla SD oficial de Amazon o el generador correspondiente, NO reutilizar la plantilla SP.

### 8. Hoja única "Sponsored Products Campaigns"

Recordatorio: si el archivo tiene hojas adicionales (resumen, notas, etc.), Amazon las intenta parsear como bulk y rechaza todo el archivo. Mantener una sola hoja con el nombre exacto que Amazon espera (`Sponsored Products Campaigns` para SP, `Sponsored Brands Campaigns` para SB, `Sponsored Display Campaigns` para SD).

## Referencias

- Última ejecución completa documentada: [[2026-04-28]]
- Brand state Dermaglos: [[DERMAGLOS]]
- SOP general PPC: [[PPC-SOP-Manager]]
- Atom11 rules vigentes Dermaglos: [[atom11-rules]]

---

## 🎓 Aprendizajes sesión 2026-05-20 (14 nuevos)

### 1. Bulk CREATE requiere placeholder IDs

Amazon Ads exige Campaign ID y Ad Group ID en TODAS las entidades hijas (Ad Group, Product Ad, Keyword, Product Targeting), aún para Operation=Create. Solución: strings únicos como placeholder (ej: NEW_C1, NEW_AG1). Amazon resuelve dependencias internamente y asigna IDs reales al procesar. NO usar IDs vacíos en hijas.

Estructura correcta:

- Row Campaign: Campaign ID="NEW_C1", Ad Group ID=""
- Row Ad Group: Campaign ID="NEW_C1", Ad Group ID="NEW_AG1"
- Row Product Ad: Campaign ID="NEW_C1", Ad Group ID="NEW_AG1"
- Row Keyword: Campaign ID="NEW_C1", Ad Group ID="NEW_AG1"

### 2. "No change was applied" es engañoso en CREATE

Cuando un bulk de CREATE falla por errores en filas hijas, las filas de Campaign (que crean el Campaign ID) SÍ se procesan. Resultado: Campañas creadas vacías sin Ad Group / Product Ads / Keywords.

**Protocolo obligatorio antes de re-subir bulk CREATE fallido:**

1. Bajar Bulk Sheet Export actualizado o verificar Campaign Manager
2. Confirmar si las campañas/entidades parent ya existen
3. Si existen vacías → poblar con UPDATE usando Campaign IDs reales (no re-crear)
4. Si no existen → re-subir con técnica de placeholder IDs

### 3. Amazon bloquea bulks con hojas "Invalid Headers"

Solo aceptan hojas con nombres oficiales: `Sponsored Products Campaigns`, `Sponsored Brands Campaigns`, etc. Hojas auxiliares como "Referencia spend" rompen toda la validación.

**Regla operativa:** nunca incluir hojas de referencia en el bulk. Generarlas como archivos `_ref_BULK_X.xlsx` separados.

### 4. Conflictos KW propia vs negative

No se puede negativizar (negative phrase/exact) una keyword que ya está sembrada en la misma campaña con esa misma frase. Antes de generar un Bulk 2 (negative keywords), correr validación cruzada contra Bulk Sheet Export para detectar conflictos. Si la KW propia es bleeder root → pausarla (no negativizarla).

### 5. Negative Product Targeting requiere Campaign ID + Ad Group ID

A diferencia de Campaign Negative Keyword (que solo requiere Campaign ID), Negative Product Targeting aplica a nivel Ad Group. Necesita ambos IDs sí o sí.

### 6. Bulk Sheet Export es la fuente de verdad

El Campaign CSV (Campaign Manager → Export) NO trae Campaign IDs. Solo el Bulk Sheet Export (Sponsored Ads → Bulk operations → Create custom spreadsheet) trae todos los IDs (Campaign, Ad Group, Keyword, Ad, Portfolio). Para cualquier bulk de UPDATE/PAUSE, partir siempre del Bulk Sheet Export.

### 7. SearchTerm ≠ Keyword sembrada

Los "search terms" del STR son matches de keywords sembradas, no keywords sembradas en sí. No se puede hacer bid update directo sobre un search term — hay que (a) negativizarlo o (b) ajustar el bid de la keyword root que lo matchea. Si el bleeder es la propia KW root → pausar la root.

### 8. Bulk Portfolio Assignment SÍ funciona con Portfolio IDs

**ACTUALIZA regla previa del vault.** Anteriormente se decía que asignar portfolio en bulk no funcionaba. La regla era cierta SOLO con Portfolio Names. Con Portfolio IDs numéricos (extraídos del Bulk Sheet Export, hoja "Portfolios"), el bulk de Update Campaign con Portfolio ID funciona perfectamente.

### 9. Bulks de UPDATE hacen rollback TOTAL ante un error

Si una sola row del bulk de UPDATE falla validación (ej: campaña archivada, KW que no existe), Amazon rechaza TODO el batch. Ninguna row se aplica.

**Regla operativa:** filtrar siempre `State == 'enabled'` o `'paused'` antes de generar bulks de UPDATE. Excluir archived.

### 10. Diferencia CREATE vs UPDATE en rollback

- **CREATE:** procesa row a row, las válidas se aplican aunque otras fallen (de ahí campañas vacías si hijas fallan)
- **UPDATE:** rollback total si una sola row falla

### 11. ASINs son marketplace-specific (US ≠ MX)

ASINs son específicos por marketplace. Un ASIN de Amazon US generalmente NO existe en Amazon MX (aunque sea el mismo producto físico). Antes de armar Product Targeting Expression con ASINs competidores, validar visualmente en el marketplace destino (amazon.com.mx para MX, amazon.com para US).

### 12. "Delivering" + "Unable to load product details" = ASINs inválidos

Una campaña puede estar en "Delivering" status pero los Product Targeting tener ASINs inválidos del marketplace. El indicador es ⚠️ "Unable to load product details" en el ASIN row. En ese caso la campaña NO va a servir impressions aunque esté técnicamente activa. Chequear post-launch siempre.

### 13. Brands premium US no siempre operan en MX

SwaddleMe (Summer Infant) sí opera en MX. Halo SleepSack sí. Swaddelini opera en MX pero catálogo limitado (~164 reviews total). Kyte Baby sí. Antes de crear PAT vs competidores, validar primero (a) si la marca opera en marketplace destino, (b) si tiene catálogo robusto.

### 14. Buscador nativo Amazon Ads > búsqueda pública para ASINs targeting

El buscador integrado de Product Targeting en Campaign Manager (Targeting → Add product targets → Individual products) SOLO muestra ASINs válidos del marketplace donde está la cuenta. Es la fuente más confiable para targeting por ASIN — superior a copiar ASINs de búsquedas públicas o de Helium 10.

**Recomendación operativa:** para PAT vs competidores, NO armar bulk con ASINs específicos. Mejor:

1. Crear campaña + ad group + product ads via bulk (sin Product Targeting)
2. Asignar Product Targets via UI usando el buscador nativo
3. Validar Impressions > 0 a las 24-48h

## Learnings 2026-05-22 (Setex 5 bulks)

### 12. Bug módulo M4 `STR_analizado.xlsx` — solo procesa KW campaigns

Mismo patrón Dermaglos 08/05. El script `modules/pages/str.py` (o equivalente)
solo procesa search terms con Match Type EXACT/PHRASE/BROAD. Deja fuera AUTO
(43% spend típico) y PT (27% spend típico) = 70% del business sin analizar.

Bugs adicionales en bulks pre-armados del módulo:
- Duplicados masivos en negativos (mismo término 2-4 veces)
- Mismas KWs en negatives Y harvest simultáneamente
- Brand propio (`setex gecko grip`) clasificado como negativo
- ASIN propio en harvest con bids altos

**✅ RESUELTO (commit b2763cb, 2026-05-26)** — el classifier de M4 fue reescrito: dedupe SQP, anti-self-ASIN, cross-brand → CONQUEST, NaN ≠ 0, relevancia confirmada para ESCALAR, bloque BRAND prioritario. M4 ahora cubre AUTO + PT vía panel diagnóstico visual (warning si > 20% del spend en AUTO/PT/sin Match Type). El fix REAL upstream en M2 (`search_term_report.py` L325-345) queda pendiente para sesión C-2.

### 13. Cross-client ASIN safety check antes de mensajes operativos

Por correr 3+ cuentas en una misma semana (LTD/Dermaglos/Setex/M&B), riesgo
real de pegar ASIN de un cliente en mensaje de otro. Ejemplo 22/05: B0CYLMJJJC
(Dermaglos $9.99) apareció en draft mensaje Setex.

**Patch SOP cierre**: antes de postear cualquier mensaje a equipo cliente,
validar que los 5 últimos ASINs mencionados pertenecen al cliente del thread.

### 14. Cruce Seller Central obligatorio pre-mensajes Tati

Vault desincronizado con realidad Seller Central genera ruido:
- B086H3TZ6B "urgente" del 29/04 ya tenía inbound activo desde 19/05
- B08SNXF8HP "BuyBox 91%" ya estaba en 100% Featured offer sin Match
- Restocks "iniciar" eran "confirmar ETA" (inbound ya activo)

**Patch SOP cierre**: refresh Seller Central como primer paso pre-mensaje
operativo Tati. Validar status REAL de cada flag/restock vs lo que dice el vault.

### 15. Diferencia CREATE vs UPDATE rollback (refresh del 12/05)

CREATE procesa row-by-row → 126 negativos del 22/05 todos aplicados sin rollback.
UPDATE hace rollback total → un solo error en Bulk 2 o 3 hubiera tirado todos los
cambios. Por eso: subir CREATE bulks últimos (más tolerantes), UPDATE bulks
primero (necesitan archivo limpio).

Orden ejecutado 22/05 (recomendado):
1. UPDATE state (pausas+archive)
2. UPDATE bid down (frenar sangrado)
3. UPDATE bid up (reactivar)
4. UPDATE budget (escalar)
5. CREATE negativos (al final, más tolerante)

### 16. Validación cruzada pre-bulk (7 checks descartó harvest EXACT)

Antes de generar bulk de CREATE harvest, ejecutar 7 checks:
1. ¿Existe ya como EXACT activa?
2. ¿Convierte hoy en AUTO/PT con ACoS bajo? (canibalización)
3. ¿Variante plural/singular cercana en EXACT? (Amazon close match)
4. ¿Existe como PHRASE/BROAD activo que la cubre?
5. ¿Tráfico real en STR 30d?
6. ¿SQV suficiente en SQP semanal?
7. ¿AUTO winner ya la captura barato? (no canibalizar)

Si AUTO captura a ACoS <10%, **NO crear EXACT** — solo escalar AUTO budget.

---

## Learnings 2026-05-26 (cierre fix M4 — bulks ejecutables)

### Bulks M4 ahora ejecutables (commit b2763cb)
El Plan de Acción bulk de M4 dejó de ser inejecutable: Max Bid calculado (CVR × precio × target ACoS), Match Type variable por acción (ESCALAR→exact, AGREGAR→phrase, DEFENDER→exact), contrato con M10 Campaign Builder preservado (4 columnas inmutables). **Verificar `target_acos` antes de descargar el bulk** (default 35, ajustar según cliente: Setex 18, Dermaglos 50, LTD 35) — un target más estricto reduce las filas ESCALAR y baja el Max Bid calculado.

---

## Learnings 2026-06-08

### #1 — Sites column opcional / "amazon.com.mx" inválido
Para Campaign Create, el valor `"amazon.com.mx"` en columna Sites es RECHAZADO por Amazon. Las campañas del cliente lo tienen vacío (NaN). El marketplace ya está implícito desde la seller account. REGLA: dejar Sites vacío en Create.

### #2 — "Negative Product Targeting" es ad-group-level
Entity "Negative Product Targeting" REQUIERE Ad Group ID (es ad-group-level). NO existe "Campaign Negative Product Targeting". Para cobertura campaign-wide de un ASIN competidor hay que crearlo en cada ad group. EN CONTRASTE: "Campaign Negative Keyword" SÍ es campaign-level y NO requiere Ad Group ID.

### #3 — Verificar negativos PRE-EXISTENTES antes de CREATE
La verificación anti-duplicado debe incluir entities `Negative Product Targeting` + `Campaign Negative Keyword` existentes (no solo KWs positivas). CATEGORY DISCOVERY tenía 48 neg PT preexistentes → 18 errores "already exists" en el upload (benignos, CREATE es row-by-row y aplica el resto, pero ensucian el reporte). REGLA: cross-check pre-bulk debe extraer neg PT/KW existentes por ad group y excluir duplicados del CREATE.

### #4 — CREATE row-by-row confirmado
Upload con 18 errores sobre 172 filas → 154 aplicados igual. El header "Failed" del upload NO significa rollback: significa que el archivo tuvo ≥1 error. Los records exitosos SÍ se aplican (CREATE row-by-row). Verificar siempre "Number of records successful" en el reporte, no el header.

---

## Learnings 2026-07-09 (LTD Prime Day + 360° julio)

### #5 — IDs numéricos en UPDATE: pandas los lee como float y agrega ".0"
Amazon lo rechaza como "temporary ID".
FIX: `str(v).split('.')[0]` + formato de celda `"@"`.
Aplica a: Keyword ID, Ad Group ID, Campaign ID, Product Targeting ID.
(Caso real: LTD 03/07, el bulk C v1 falló entero por esto; la v2 con el fix entró OK.)

### #6 — "Failed" de Amazon puede esconder éxito parcial
Si UNA fila tiene error, Amazon marca TODO el upload como Failed aunque N-1 filas hayan entrado.
**Verificar el record count (successful vs errors) en el Processing Summary, NO el flag Failed/Success del listado.**

### #7 — Re-subir un bulk de negativos que ya entró parcialmente rebota con "already exists"
Eso NO es un error — confirma que el trabajo previo SÍ se aplicó.
(Caso real: LTD 03/07, 19/32 nuevos + 13 already-exists.)

### #8 — Advertised Product report usa atribución 7-day-from-click
NO sirve para segmentar ads por ventana temporal corta. Distorsiona: las ventas del evento se corren a fechas previas.
Síntoma: al hacer split orgánico/pagado por semana, aparece "pagado > total" o incluso orgánico negativo.
**Para split orgánico/pagado por ventana, usar período agregado con atribución cerrada.**
(Casos reales: LTD dio orgánico negativo al intentar split semanal; Setex dio "pagado > total" en el 360° del 03/07 — mismo mecanismo.)

---

## Learnings 2026-07-16 (Dermaglós US — 360° + 3 bulks)

### #9 — Campaign Negative Keyword: valor de Match Type
Los `Campaign Negative Keyword` usan `negativeExact` o `negativePhrase` como Match Type.
**NO existe `campaignNegativeExact`** — Amazon lo rechaza con `"Invalid value: campaignNegativeExact for column: Match Type"` y hace **ROLLBACK TOTAL del upload** (ninguna fila aplica, ni las válidas).
El prefijo "campaign" lo infiere Amazon del Entity, no se repite en el Match Type.
⚠️ Ojo con la distinción: este caso es rollback total (Failed = nada entró), distinto del learning #6 "Failed ≠ fallo total" (donde Failed esconde éxito parcial). Siempre leer el Processing Summary para saber cuál de los dos es.
Detectado en Dermaglós US, bulk 2 del 16-jul-2026 (Failed → v2 Success).

---

## Learnings 2026-07-23 (Dermaglós US — 360° v1.1)

### #10 — Búsqueda por ASIN en STR ≠ Product Targeting sobre ASIN — verificar contra BSE antes de negativizar
En el STR, un ASIN puede aparecer como `Customer Search Term` (gente tipeando el ASIN en el buscador). Eso NO es lo mismo que un Product Targeting sobre ese ASIN. **Se ven casi idénticos en el reporte y llevan a conclusiones opuestas.**
Caso real (Dermaglós US, 23-jul-2026): el STR mostraba `b0f4kxzvnm` con $50,84 y 0 ventas → parecía fuga, se preparó bulk de negativos. Al cruzar contra BSE se vio que los **PAT sobre ASINs propios rendían $52,22 → $248,26 (ACoS 21%)** — cross-selling en PDP. **El bulk habría destruido $248 de ventas.**
**Regla: antes de negativizar cualquier cosa que parezca un ASIN, cruzar contra el BSE para distinguir search term de product target.**
