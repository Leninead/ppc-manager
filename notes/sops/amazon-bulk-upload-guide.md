---
tipo: sop
actualizado: 2026-04-28
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
