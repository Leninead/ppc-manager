> ⚠️ **DEPRECATED (2026-04-24)** — Este documento fue reemplazado por `AmazonBulkUploadGuide.md` durante el fix bulk Amazon 2026 compliance (2026-04-21, commit `ebbe498`). **Usá siempre `AmazonBulkUploadGuide.md`** — contiene 31 columnas, flujo asíncrono 2026, helper `_fila_vacia_bulk()`, y checklist post-upload validado en producción.

---

## Referencia histórica — Por qué se deprecó

El archivo original `AmazonBulk.md` fue creado basado en el flujo sincrónico de 2025. En abril 2026, Amazon rediseñó Bulk Operations:

- **Batch IDs**: cambio de numéricos (158936020550) a UUIDs (cee6c2f5-...)
- **Flujo asíncrono**: Uploading → Processing → Success/Failed (no inmediato)
- **Result file**: ya no trae IDs rellenados — verificación visual obligatoria en Campaign Manager
- **Columnas**: de 30 a 31 (agregada `Sites`)
- **Validación**: verificación post-upload en 6 pasos (no alcanza ver "Success")

**Consultar siempre**: `AmazonBulkUploadGuide.md` en la raíz del proyecto.
