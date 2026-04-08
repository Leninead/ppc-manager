# 📦 Guía Definitiva — Amazon Bulk Upload Format
## Capybaras Agency · Formato validado · Abril 2026

---

## Regla #1 — El archivo debe tener UNA SOLA hoja

**Nombre exacto de la hoja:** `Sponsored Products Campaigns`

Si el archivo tiene hojas adicionales (resumen, notas, etc.), Amazon las intenta parsear como bulk y rechaza todo el archivo.

---

## Regla #2 — Las 30 columnas exactas (en este orden)

```
Product
Entity
Operation
Campaign ID
Ad Group ID
Portfolio ID
Ad ID
Keyword ID
Product Targeting ID
Campaign Name
Ad Group Name
Start Date
End Date
Targeting Type
State
Daily Budget
SKU
Ad Group Default Bid
Bid
Keyword Text
Native Language Keyword
Native Language Locale
Match Type
Bidding Strategy
Placement
Percentage
Product Targeting Expression
Audience ID
Shopper Cohort Percentage
Shopper Cohort Type
```

Si faltan columnas, Amazon puede rechazar filas silenciosamente. Siempre incluir las 30 aunque estén vacías.

---

## Regla #3 — Campaign ID y Ad Group ID = NOMBRE (no numérico)

Este es el error más común. Para operaciones `create`:

| Fila | Campaign ID | Ad Group ID |
|------|------------|-------------|
| Campaign | = Campaign Name | (vacío) |
| Ad Group | = Campaign Name | = Ad Group Name |
| Product Ad | = Campaign Name | = Ad Group Name |
| Keyword | = Campaign Name | = Ad Group Name |
| Product Targeting | = Campaign Name | = Ad Group Name |
| Bidding Adjustment | = Campaign Name | (vacío) |

**Sin esto, Amazon crea la campaña pero NO puede linkear los Ad Groups, Keywords y Product Ads — falla con "Missing Parent ID".**

---

## Regla #4 — Start Date formato `yyyyMMdd`

| ✅ Correcto | ❌ Incorrecto |
|------------|--------------|
| `20260408` | `04/08/2026` |
| `20260415` | `2026-04-15` |
| `20260501` | `05/01/2026` |

Si se guarda como número (20260408.0), Amazon también lo rechaza. Guardar siempre como **texto**.

---

## Regla #5 — Bidding Strategy valores exactos

| ✅ Valor para Bulk Upload | ❌ Valor de display (Campaign Manager) |
|--------------------------|---------------------------------------|
| `Fixed bid` | `Fixed bids` |
| `Dynamic bids - down only` | `Dynamic bidding (down only)` |
| `Dynamic bids - up and down` | `Dynamic bidding (up and down)` |

**Ojo:** El Campaign CSV de descarga muestra los valores de "display" — NO son los mismos que acepta el bulk upload.

---

## Regla #6 — Product Targeting (PAT / Conquista)

Para campañas de Product Targeting por ASIN:

| Campo | Valor |
|-------|-------|
| Entity | `Product Targeting` |
| Product Targeting Expression | `asin="B0XXXXXXXX"` |
| Keyword Text | (vacío) |
| Match Type | (vacío) |

**NO usar** Product Targeting ID para el ASIN. Usar **Product Targeting Expression**.

---

## Regla #7 — NO incluir filas vacías separadoras

Amazon parsea cada fila. Una fila vacía genera error de validación.

---

## Regla #8 — Targeting Type

| Tipo de campaña | Valor |
|----------------|-------|
| SP Manual (Keywords o PAT) | `MANUAL` |
| SP Auto | `AUTO` |

---

## Estructura de filas por campaña (orden exacto)

Para cada campaña nueva, las filas van en este orden:

```
1. Campaign       → crea la campaña
2. Ad Group       → crea el ad group dentro de la campaña
3. Product Ad     → asocia el SKU al ad group
4. Keyword (×N)   → agrega keywords al ad group
   — o —
4. Product Targeting (×N) → agrega ASINs target al ad group
```

---

## Template de ejemplo — Campaña SP Exact con Keywords

| Product | Entity | Operation | Campaign ID | Ad Group ID | Campaign Name | Ad Group Name | Start Date | Targeting Type | State | Daily Budget | SKU | Ad Group Default Bid | Bid | Keyword Text | Match Type | Bidding Strategy |
|---------|--------|-----------|-------------|-------------|---------------|---------------|------------|----------------|-------|-------------|-----|---------------------|-----|-------------|------------|-----------------|
| Sponsored Products | Campaign | create | MI CAMPAÑA | | MI CAMPAÑA | | 20260408 | MANUAL | enabled | 15 | | | | | | Fixed bid |
| Sponsored Products | Ad Group | create | MI CAMPAÑA | MI AD GROUP | MI CAMPAÑA | MI AD GROUP | | | enabled | | | 0.70 | | | | |
| Sponsored Products | Product Ad | create | MI CAMPAÑA | MI AD GROUP | MI CAMPAÑA | MI AD GROUP | | | enabled | | MI-SKU-123 | | | | | |
| Sponsored Products | Keyword | create | MI CAMPAÑA | MI AD GROUP | MI CAMPAÑA | MI AD GROUP | | | enabled | | | | 0.70 | mi keyword | exact | |
| Sponsored Products | Keyword | create | MI CAMPAÑA | MI AD GROUP | MI CAMPAÑA | MI AD GROUP | | | enabled | | | | 0.65 | otra keyword | exact | |

---

## Template de ejemplo — Campaña SP PAT (Product Targeting)

| Product | Entity | Operation | Campaign ID | Ad Group ID | Campaign Name | Ad Group Name | Start Date | Targeting Type | State | Daily Budget | SKU | Ad Group Default Bid | Bid | Product Targeting Expression | Bidding Strategy |
|---------|--------|-----------|-------------|-------------|---------------|---------------|------------|----------------|-------|-------------|-----|---------------------|-----|-----------------------------|-----------------|
| Sponsored Products | Campaign | create | MI CAMPAÑA PAT | | MI CAMPAÑA PAT | | 20260408 | MANUAL | enabled | 10 | | | | | Fixed bid |
| Sponsored Products | Ad Group | create | MI CAMPAÑA PAT | MI AG PAT | MI CAMPAÑA PAT | MI AG PAT | | | enabled | | | 0.60 | | | |
| Sponsored Products | Product Ad | create | MI CAMPAÑA PAT | MI AG PAT | MI CAMPAÑA PAT | MI AG PAT | | | enabled | | MI-SKU-123 | | | | |
| Sponsored Products | Product Targeting | create | MI CAMPAÑA PAT | MI AG PAT | MI CAMPAÑA PAT | MI AG PAT | | | enabled | | | | 0.60 | asin="B0XXXXXXXX" | |

---

## Checklist pre-upload

- [ ] ¿El archivo tiene UNA sola hoja llamada "Sponsored Products Campaigns"?
- [ ] ¿Las 30 columnas están en el orden correcto?
- [ ] ¿Campaign ID = Campaign Name en TODAS las filas?
- [ ] ¿Ad Group ID = Ad Group Name en filas de AG, Product Ad, Keyword, PT?
- [ ] ¿Start Date en formato yyyyMMdd como TEXTO?
- [ ] ¿Bidding Strategy usa valores de bulk ("Fixed bid", "Dynamic bids - down only")?
- [ ] ¿No hay filas vacías?
- [ ] ¿Los SKUs son correctos (no ASINs)?
- [ ] ¿PAT usa Product Targeting Expression (no Product Targeting ID)?

---

## Errores comunes y solución

| Error Amazon | Causa | Solución |
|-------------|-------|----------|
| "Missing Parent ID: Campaign ID" | Campaign ID vacío en fila hija | Poner Campaign Name como Campaign ID |
| "Invalid value for Start Date" | Formato fecha incorrecto | Usar yyyyMMdd como texto |
| "Invalid value for Bidding Strategy" | "Fixed bids" con s | Usar "Fixed bid" (sin s) |
| "Invalid Headers in sheet X" | Hojas extra en el archivo | Dejar solo 1 hoja |
| "Missing value for columns: Campaign ID, Ad Group ID" | IDs vacíos en Keywords | Completar con nombres |

---

**Validado:** 07 abril 2026 — Batch ID 158936020550 — 52/52 rows processed successfully
**Agencia:** Capybaras Agency | **Dev:** Lenin Acosta
