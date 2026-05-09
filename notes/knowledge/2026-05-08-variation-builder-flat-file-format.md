---
tipo: knowledge
actualizado: 2026-05-08
cliente: OPTIPET
marca: OPTIPET
template_version: 2026.0427
marketplace: MX
categoria: petfood
---

# Variation Builder — Formato flat file OPTIPET (Pet Food MX)

> Patrón validado en 2 casos de éxito: VITALPET (2026-04-27) y OPTIPET (2026-05-08).
> Esta nota permite regenerar un flat file de variation OPTIPET sin pedir el spreadsheet de referencia. Aplica para mismo cliente / misma marca / mismo marketplace.

## Cuándo aplica este patrón sin pedir nada más

Reutilizar este header tal cual SI:
- Cliente: OPTIPET (misma cuenta Seller Central)
- Marca: OPTIPET
- Marketplace: México (`A1AM78C64UM0Y8`)
- Categoría: Pet Food (`fptcustom`)
- Versión template: `2026.0427` o compatible

Si Amazon notifica al cliente que tiene que bajar un template nuevo, pedir el `.xlsm` actual y regenerar este knowledge entry con header fresco.

## Estructura del archivo (.txt tab-separated, UTF-8)

220 columnas, 7+ filas:

| Fila | Contenido |
|---|---|
| 1 | Settings (TemplateType, Version, contributorId, marketplace IDs) |
| 2 | Labels en español (lo que se ve en el dropdown del template) |
| 3 | `field_name` interno (lo que Amazon parsea) |
| 4 | Parent SKU |
| 5+ | Children SKUs (uno por fila) |

## Posiciones de campos críticos (1-indexed)

```
col   1: feed_product_type        → "petfood"
col   2: item_sku                 → SKU del producto
col   3: brand_name               → "OPTIPET"
col   4: update_delete            → "Update" (parent) | "PartialUpdate" (child)
col   7: item_name                → Título (solo parent)
col   8: manufacturer             → "OPTIPET"
col  12: recommended_browse_nodes → "11601177001" (validado para suplementos OPTIPET)
col  13: gtin_exemption_reason    → "Pieza" (solo parent)
col  14: age_range_description    → "Adulto" (solo parent)
col  25: parent_child             → "Parent" | "Child"
col  26: parent_sku               → SKU del parent (SOLO en children — vacío en parent)
col  27: relationship_type        → "variation" (solo children)
col  28: variation_theme          → "Sabor" (validado con valores custom)
col  35: target_audience_keywords → "Perros" (solo parent)
col  39: flavor_name              → valor único por child
col  92: country_of_origin        → "México" (solo parent)
col 161: condition_type           → "Nuevo" (solo parent)
```

## Patrón Parent (full update — Update)

14 columnas pobladas, resto vacío. `parent_sku` (col 26) queda VACÍO en parent.

## Patrón Child (minimal payload — PartialUpdate)

9 columnas pobladas, resto vacío. Con `PartialUpdate`, Amazon respeta item_name, bullets, descripción, imágenes y A+ del listing existente. Si se popula `item_name` en child, Amazon SOBRESCRIBE el actual — NO hacerlo.

## Themes válidos para Pet Food (col 28)

| Theme | Atributo | Cuándo |
|---|---|---|
| Sabor | flavor_name (col 39) | Distintos sabores. Acepta valores custom no-sabor (validado en OPTIPET con "Vitality", "Skin and Coat", "Healthy Gut") |
| Nombre del Tamano | size_name (col 38) | Distintos tamaños mismo sabor |
| Tamano del Sabor | size_name + flavor_name | Sabor Y tamaño combinados |
| Nombre del Patron | pattern_name | Patrones de empaque |
| Scent | scent_name | Aromas |

## Gotchas (reglas duras)

1. **1 ASIN ≠ 2 children**: si producto tiene FBA + FBM mismo ASIN, elegir UNO. Apagar el otro con `Close listing` antes del feed. Validado en OPTIPET (FBM `OPTIPETSKINCOATFBA` zombi tuvo que apagarse).
2. **`update_delete` IDs en inglés**: dropdown muestra "Actualizar / Actualizar Parcialmente / Borrar" pero los IDs API son `Update / PartialUpdate / Delete`.
3. **`flavor_name` acepta custom**: post-fix M26 (2026-04-26) y validado en Amazon (OPTIPET 2026-05-08) — campo libre, acepta strings fuera del dropdown, incluso semántica no-sabor en inglés.
4. **Browse node OPTIPET = `11601177001`**: validado para suplementos en polvo. Reutilizar para futuros productos OPTIPET de la misma línea.
5. **Parent NO comprable**: solo referente. Children mantienen ASINs y venden.
6. **Reviews y BSR**: se consolidan a nivel parent post-agrupación.

## Caso de éxito #2 — OPTIPET ADULT (2026-05-08)

### Inputs
- Cliente: OPTIPET (suplementos perros, MX)
- 3 ASINs:
  - `B0G6VWT7RB` → SKU `OPTIPETVITALITY` (Vitality)
  - `B0G6TW7G12` → SKU `OPTIPETSKINCOAT` (Skin and Coat)
  - `B0G6TPVT2G` → SKU `OPTIPETHEALTHYGUT` (Healthy Gut)
- Parent SKU nuevo: `OPTIPET_ADULT_PARENT`
- Theme: `Sabor` con valores custom (innovación vs VITALPET que usó sabores reales)

### Output
- Feed batch ID: `50059020581`
- 4/4 SKUs successful · 0 errors · 0 warnings
- **Parent ASIN asignado**: `B0H12ZXVPF`
- Variation Family confirmada en Seller Central post-upload

### Pre-flight cleanup
Apagar `OPTIPETSKINCOATFBA` (FBM zombi compartiendo ASIN con child FBA) antes de subir el feed.

## Filas de datos OPTIPET (referencia exacta)

Las 4 filas que cambian entre cargas. Las filas 1-3 (header) están en la sección "Header del template" más abajo.

```
ROW 4 (Parent OPTIPET_ADULT_PARENT):
  col   1: petfood
  col   2: OPTIPET_ADULT_PARENT
  col   3: OPTIPET
  col   4: Update
  col   7: OPTIPET Suplementos Alimenticios para Perros Adultos | Apoyo Nutricional Diario | Vitaminas, Probióticos y Prebióticos | 270 g
  col   8: OPTIPET
  col  12: 11601177001
  col  13: Pieza
  col  14: Adulto
  col  25: Parent
  col  28: Sabor
  col  35: Perros
  col  92: México
  col 161: Nuevo

ROW 5 (Child Vitality):
  col 1: petfood | col 2: OPTIPETVITALITY | col 3: OPTIPET | col 4: PartialUpdate
  col 25: Child | col 26: OPTIPET_ADULT_PARENT | col 27: variation
  col 28: Sabor | col 39: Vitality

ROW 6 (Child Skin and Coat):
  col 1: petfood | col 2: OPTIPETSKINCOAT | col 3: OPTIPET | col 4: PartialUpdate
  col 25: Child | col 26: OPTIPET_ADULT_PARENT | col 27: variation
  col 28: Sabor | col 39: Skin and Coat

ROW 7 (Child Healthy Gut):
  col 1: petfood | col 2: OPTIPETHEALTHYGUT | col 3: OPTIPET | col 4: PartialUpdate
  col 25: Child | col 26: OPTIPET_ADULT_PARENT | col 27: variation
  col 28: Sabor | col 39: Healthy Gut
```

## Header del template OPTIPET/VITALPET (filas 1-3)

Bloque exacto a usar en futuros flat files de OPTIPET. Reemplazar SOLO las filas 4+ con los datos del nuevo Parent + Children. Mantener tabs como separador y UTF-8 sin BOM.

⚠️ NOTA OPERATIVA: las 3 filas del header están guardadas como referencia binaria en el archivo del módulo `modules/pages/variation_builder.py` (helper `_parse_template`). Cuando se arme un flat file nuevo para OPTIPET, el flujo es:

OPCIÓN 1 (recomendada): generar el .txt usando el módulo Variation Builder de la app Streamlit, que lee el `.xlsm` adjunto y arma el archivo automático.

OPCIÓN 2 (regenerar manual desde knowledge): pedir a Lenin el último `.txt` válido de OPTIPET (ej: el del 2026-05-08), reemplazar las filas 4+ con los nuevos datos, dejar las filas 1-3 intactas.

OPCIÓN 3 (Claude regenera todo): Claude tiene en este knowledge entry suficiente metadata (categoría, marketplace, version, contributorId del cliente) para reconstruir las filas 1-3 si Lenin se lo pide explícitamente. Validar siempre con un upload de prueba antes de mandarlo a producción.

## Ubicación de archivos generados

Los flat files generados se guardan en `notes/clients/optipet/flat-files/` con nomenclatura `OPTIPET_{descripcion}_{YYYY-MM-DD}.txt`. Ej:
- `OPTIPET_AdultParent_2026-05-08.txt` (caso de éxito #2)

## Cómo usar este knowledge en una sesión futura

Lenin pide: "armemos otro variation para OPTIPET, parent X con children Y, Z, W"

Claude debe:
1. Leer este knowledge entry
2. Verificar que cliente/marca/marketplace coinciden (OPTIPET MX)
3. Confirmar con Lenin: parent SKU nuevo, theme aplicable, valores `flavor_name` (o el atributo del theme) por child
4. Recordar gotcha 1 (FBM zombi) y pedir confirmación
5. Generar el .txt con header reutilizado + filas 4+ nuevas
6. Guardar en `notes/clients/optipet/flat-files/`
7. Post-upload: capturar Parent ASIN asignado y agregar como nuevo caso de éxito a esta nota

## Wikilinks

[[SOP_Variation_Builder_FlatFile]] · [[CLAUDE]] · [[2026-05-08]] · [[STATE-agencia]] · [[optipet]]
