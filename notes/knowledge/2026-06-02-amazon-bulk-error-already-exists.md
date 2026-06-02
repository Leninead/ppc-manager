---
date: 2026-06-02
tags: [amazon-ads, bulk-sheets, error-codes, reference]
severity: low
---

# Amazon Bulk Error: "NegativeTargetingClause already exists!"

## Cuándo aparece
Al hacer CREATE de un Negative PT o Negative KW que YA EXISTE en la cuenta (no importa si está enabled o paused).

## Mensaje literal
Input Error / Invalid User Input
NegativeTargetingClause with campaignId=X, adGroupId=Y, expression=[(value=B0XXXXXXXXX, type=ASIN_SAME_AS)] already exists!

## Comportamiento
- Solo esa row se rechaza (Input Error)
- El resto del bulk procesa normalmente
- CREATE no hace rollback completo como UPDATE
- Resultado típico: Success parcial (ej. 16/32 success + 16 errors)

## Acción
No requiere fix de bulk ni reupload. Los ASINs/KWs duplicados ya cumplen su función en la cuenta.

## Prevención
Ver [[knowledge/2026-06-02-gotcha-bulk-export-adgroup-id-float]] — el cross-check correcto contra bulk export evita estos errores antes de subir.

## Diferencia vs error en UPDATE
UPDATE bulks SÍ hacen rollback completo si una row falla — diferencia crítica. CREATE procesa row-a-row, falla aislada.
