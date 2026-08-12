---
date: 2026-08-12
tags: [gotcha, bulk-sheets, amazon-ads, negative-keyword, auto-campaign, mott-bow-us]
session: mb-us-12-08
severity: medium
---

# Gotcha: Negative Keyword en campaña AUTO requiere `Ad Group ID` además de `Campaign ID`

## Síntoma

Bulk de negativos contra campañas **AUTO** (scavenger) es rechazado por Amazon con:

```
Missing value for column Ad Group ID
```

El bulk trae `Campaign ID` correcto y la fila luce bien. Falla igual, fila por fila, sin procesar ninguna.

## Causa raíz

`Negative Keyword` es una entidad de **nivel ad group**, no de nivel campaña. Amazon exige la coordenada completa:

- `Campaign ID` → ubica la campaña
- `Ad Group ID` → ubica el ad group **dentro** de esa campaña ← **el que falta**

La confusión viene de que existe una entidad hermana a nivel campaña — `Campaign Negative Keyword` — que sí se resuelve solo con `Campaign ID`. Son entidades distintas: la de campaña bloquea el término en toda la campaña, la de ad group solo en ese ad group. Si el `Entity` de la fila dice `Negative Keyword`, el `Ad Group ID` es obligatorio aunque la campaña sea AUTO y tenga un único ad group.

En AUTO el error es más fácil de cometer porque el ad group suele ser uno solo y autogenerado — se lo trata mentalmente como "la campaña".

## Fix

Poblar `Ad Group ID` en toda fila `Negative Keyword`. El ID sale del bulk export de la cuenta, cruzando por `Campaign ID`:

```python
exp = pd.read_excel("bulk-export.xlsx", sheet_name="Sponsored Products Campaigns")
# Normalizar IDs primero — Ad Group ID viene float64 por los rows vacíos
# (ver [[2026-06-02-gotcha-bulk-export-adgroup-id-float]])
exp["Campaign ID"] = exp["Campaign ID"].astype("Int64").astype(str)
exp["Ad Group ID"] = exp["Ad Group ID"].astype("Int64").astype(str)

# Mapa campaña → ad group, solo desde filas Entity == "Ad Group"
ag_map = (
    exp[exp["Entity"] == "Ad Group"]
    .set_index("Campaign ID")["Ad Group ID"]
    .to_dict()
)

mine["Ad Group ID"] = mine["Campaign ID"].map(ag_map)
assert mine["Ad Group ID"].notna().all(), "Campañas sin ad group resuelto"
```

Si una campaña AUTO tiene más de un ad group, el `.to_dict()` se queda con el último — validar el conteo antes de mapear a ciegas.

## Aplicable a

- **Mismo patrón que `Negative Product Targeting`**: también es entidad de nivel ad group y también exige `Ad Group ID`. Si el bulk de negativos KW falló por esto, el de negative PT va a fallar igual.
- Cualquier bulk de negativos contra AUTO/scavenger, en cualquier cuenta.
- No aplica a `Campaign Negative Keyword` — esa sí se resuelve solo con `Campaign ID`.

## Contexto

Cazado en el frente **M&B (Mott & Bow US) 12/08/2026**, bulk F0-1 (10 negativos AUTO scavenger). Corregido y reenviado: 10/10 aplicados. Ver [[2026-08-12]].
