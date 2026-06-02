---
date: 2026-06-02
tags: [gotcha, bulk-sheets, amazon-ads, pandas, ltd-mx]
session: ltd-mx-02-06
severity: medium
---

# Gotcha: Bulk Sheet Export `Ad Group ID` viene como float64 en pandas

## Síntoma
Cross-check de duplicados Negative PT / Negative KW contra bulk export NO detecta los que ya existen en cuenta. Resultado: bulk procesa con N "already exists" errors evitables (no rompe el bulk, pero ensucia el reporte).

## Causa raíz
`pd.read_excel("bulk-export.xlsx", sheet_name="Sponsored Products Campaigns")` carga:
- `Campaign ID` → int64 (OK)
- `Ad Group ID` → **float64** (BUG)

Razón: hay rows con Ad Group ID vacío (rows tipo Campaign, Campaign Negative Keyword a nivel campaign, Portfolio), pandas convierte la columna entera a float64 para soportar NaN.

Al convertir a string para merge:
- Mi bulk: `298759676613763` (int → str directo)
- Export: `2.987597e+14` (float → str en notación científica)
→ merge falla silenciosamente, no detecta duplicados, falso PASS en validación.

## Fix
```python
# Al cargar bulk export, normalizar IDs ANTES de cualquier cross-check:
exp = pd.read_excel("bulk-export.xlsx", sheet_name="Sponsored Products Campaigns")
exp["Campaign ID"] = exp["Campaign ID"].astype("Int64").astype(str)
exp["Ad Group ID"] = exp["Ad Group ID"].astype("Int64").astype(str)
# Int64 (pandas nullable int) preserva NaN sin caer a float
```

## Patrón mejor (recomendado para overlap check)
Comparar por sets en lugar de merge:
```python
# Extraer ASIN del expression `asin="B0XXX"`
exp["asin_clean"] = exp["Product Targeting Expression"].astype(str).str.extract(r'asin="(B0[A-Z0-9]{8})"').iloc[:,0]
mine["asin_clean"] = mine["Product Targeting Expression"].astype(str).str.extract(r'asin="(B0[A-Z0-9]{8})"').iloc[:,0]

existing_keys = set(zip(exp["Campaign ID"].astype(str), exp["asin_clean"].dropna()))
my_keys = set(zip(mine["Campaign ID"].astype(str), mine["asin_clean"].dropna()))
overlap = my_keys & existing_keys
```

## Impacto sesión LTD MX 02/06
Bulk #4 Negative PT: 32 rows submitted → 16 success + 16 "already exists" rechazados por Amazon. Sin pérdida real (los rechazados ya estaban negativizados), pero el cross-check daba falso PASS. Patrón corregido para próximas sesiones.

## Aplicable a
- M27 Flat File Migrator (cuando lee bulk exports)
- M29 Proposal Studio (si parsea bulks)
- Cualquier script ad-hoc que cruce contra bulk export
