---
title: Walmart Spec Template — Herbal Supplements (WFS)
type: reference/schema
platform: walmart
schema_version: 5.0.20260330-14_47_14
feed_type: MP_WFS_ITEM
category: Health / Supplements / Herbal Supplements
fulfillment: Walmart Fulfilled (WFS)
date_captured: 2026-06-08
filename_original: omni-marketplacewfs-en-external-5_0_20260330-14_47_14.xlsx
---

# Walmart Spec Template — Herbal Supplements (WFS)

Snapshot del template de creación bulk descargado durante el scan de Seller Central sesión 1. Este documento sirve como referencia técnica para diseñar el parser/validator del futuro módulo `walmart-listings`.

**Versión del schema**: `5.0.20260330-14_47_14`
Walmart versiona sus spec templates y los actualiza periódicamente. Re-snapshot cuando cambie la versión.

## Estructura del archivo (5 sheets)

| Sheet | Estado | Filas × Cols | Función |
|---|---|---|---|
| `Hidden_product_content_and_sit` | hidden | 627 × 142 | Dropdown valid values (closed lists) para el sheet principal |
| `Data Definitions` | visible | 77 × 8 | Documentación de cada campo |
| `Product Content And Site Exp` | visible | 6 × 131 | **Sheet principal de datos del listing** |
| `Hidden_trade_item_configuratio` | hidden | 272 × 11 | Dropdown valid values para Trade Items |
| `Trade Item Configurations` | visible | 6 × 9 | Dimensiones físicas / supply chain |

## Pattern de 5 filas de metadata + data

A diferencia de Amazon (típicamente 3 filas de header), Walmart codifica 5 niveles de metadata antes de que arranque la data del seller:

```
Row 1: Version string parseable
       Ej: "Version=5.0.20260330-14_47_14,MP_WFS_ITEM,product_content_and_site_exp,en,external,Product Content And Site Exp,0,0"

Row 2: SECTION GROUP (banda horizontal)
       'Required' / 'Conditional/Required for Hazardous Materials' /
       'Required for site visibility' / 'Recommended for search/browse' /
       'Recommended to create variant experience' / 'Optional'

Row 3: ATTRIBUTE GROUP con API JSON path en paréntesis
       Ej: 'Product Identifiers (productIdentifiers)'
            'Lithium Ion Batteries (lithiumIonBatteries)'

Row 4: UI FIELD NAME (lo que ve el seller en Seller Center)
       Ej: 'Product ID Type'

Row 5: API FIELD NAME (camelCase JSON key para integración API)
       Ej: 'productIdType'

Row 6+: DATA — filas de ítems reales del seller
```

**Implicancia para el parser**:
- Skip rows 1-5 al leer data.
- Usar Row 5 para auto-mapear columnas al schema de Marketplace API.
- Usar Row 4 para reportes legibles al usuario.
- Usar Row 2 + Row 3 para agrupar campos en la UI del validator (mostrar bloques por grupo).

## Bloques temáticos del sheet principal (131 cols)

### Required (cols 4-5)
- `sku` (col 4) — identificador del seller (alphanumeric, 50 chars)
- `specProductType` (col 5) — product type Walmart

### Required para WFS (cols 6-10)
- `productId` (col 6) — GTIN/UPC
- `productIdType` (col 7)
- `productName` (col 8)
- `brand` (col 9)
- `price` (col 10) — selling price

### Conditional / Hazmat (cols 11-40)

Walmart maneja hazmat con granularidad muy superior a Amazon. 30 columnas dedicadas.

**State restrictions**:
- `states` / `stateRestrictionsText` / `zipCodes`

**Chemical / Aerosol / Pesticide flags**:
- `isChemical`, `isAerosol`, `isPesticide`, `pesticide_type`

**Electronics + Battery (granularidad alta)**:
- Lithium Ion (cols 23-31): hasBatteries, batterySize, ionBatteryFormFactor, ionNumberOfBatteries, ionBatteryModel, ionIncludedBatteryPackaging, ionNumberOfBatteryCells, batteryWattHour, ionBatteryWeight
- Lithium Metal (cols 32-38): metalBatteryWeight, metalNumberOfBatteries, metalBatteryFormFactor, metalBatteryModel, metalIncludedBatteryPackaging, metalBatteryCellCount, lithiumMetalContentWeight

**Hazmat docs**:
- `labelImageContains` (Supplement Facts / Drug Facts / etc.)
- `labelImageURL`
- `safetyDataSheet` (+) — array
- `numberOfHazardousComponents`
- `required_storage_condition` (+)

### Required para Site Visibility (cols 41-57) — Listing essentials

- `shortDescription` (col 41) — Site Description
- `keyFeatures` × 4 slots (cols 42-45) — 4 bullets discretos
- `mainImageUrl` (col 46)
- `countPerPack` (col 47), `multipackQuantity` (col 48)
- `isProp65WarningRequired` (col 49) — California Prop 65
- `productNetContentUnit` / `productNetContentMeasure` (cols 50-51)
- `ageGroup` (col 52), `condition` (col 53)
- `fsma_section_204_traceability` (col 54) — FDA Food Safety Modernization Act
- `gender` (col 55)
- `has_written_warranty` (col 56)
- **`vitamin_and_supplement_type` (col 57)** — campo crítico para supplements

### Recommended para search/browse (cols 58-114) — 57 columnas

**Imágenes adicionales (4 slots discretos)**:
- `productSecondaryImageURL` × 4 (cols 58-61)

**Compliance claims estructurados (closed lists, no prosa libre)**:
- `allergens_not_contained` (col 62)
- `prop65WarningText` (col 71)
- `dietaryMethod`, `nutrientContentClaims` (cols 77-78)
- `ingredientPreference`, `ingredient_properties`, `ingredients` (cols 84-86)
- `healthConcerns` (col 83) — closed list
- `symptoms` (col 109) — closed list
- `food_and_drug_fact_label_type` (col 97) — Supplement Facts / Drug Facts label type

**Dimensiones físicas (4 ejes, cada uno con measure + unit)**:
- Assembled Product Depth (cols 63-64)
- Assembled Product Height (cols 65-66)
- Assembled Product Weight (cols 67-68)
- Assembled Product Width (cols 69-70)

**Compliance docs**:
- `certification_type` (col 74)
- `children_product_certificate_document_reference_id` (col 75)
- `children_product_test_report_document_reference_id` (col 76)
- `general_certificate_of_conformity_document_reference_id` (col 82)

**Supplement-specific**:
- `dosage` (col 79)
- `enteral_medication_form` (col 80)
- `flavor` (col 81)
- `medicineStrength` (col 90)
- `nationalDrugCode12` (col 91) — NDC-12 para OTC drugs
- `netContentStatement` (col 92)
- `pieceCount` (col 93)

**Nutrition block (cols 94-104)** — Walmart estructura nutrición como triple, no como texto:
- `nutrientAmount` (col 94)
- `nutrientName` (col 95)
- `nutrientPercentageDailyValue` (col 96)
- `primaryIngredient` (col 98)
- `productLine` (col 99)
- `product_multifunction_descriptor` (col 100)
- `product_usage_frequency` (col 101)
- `ib_retail_packaging` (col 102)
- `servingSize` (col 103)
- `servingsPerContainer` (col 104)
- `size` (col 105)

**Stop use / warnings**:
- `stopUseIndications` (col 106) — array
- Calorías per Serving (cols 107-108): measure + unit
- `warningText` (col 112), `warrantyText` (col 113), `warrantyURL` (col 114)

**Acreditaciones de terceros**:
- `thirdPartyAccreditationSymbolOnProductPackageCode` (col 110) — USDA Organic, NSF, GMP, etc.

### Variants (cols 115-119)

Modelo distinto a Amazon. Walmart usa "Variant Group ID" externo en lugar de parent-child ASIN.

- `variantGroupId` (col 115)
- `variantAttributeNames` (col 116)
- `isPrimaryVariant` (col 117)
- `swatchVariantAttribute` (col 118)
- `swatchImageUrl` (col 119)

### Optional + Pricing/Repricer (cols 120-131)

- `startDate` / `endDate` (cols 120-121) — control de visibilidad temporal nativo
- `MustShipAlone` (col 122)
- `shipsInOriginalPackaging` (col 123)
- `SkuUpdate` (col 124) — flag CREATE vs UPDATE
- `externalProductIdType` / `externalProductId` (cols 125-126)
- `thirdPartyProductFulfillmentType` (col 127)

**Pricing + Repricer (cols 128-131) — diferencia arquitectónica vs Amazon**:
- `msrp` (col 128)
- `minimumSellerAllowedPrice` (col 129) — piso del Repricer
- `repricerStrategy` (col 130) — activación de Repricer DESDE creación
- `maximumSellerAllowedPrice` (col 131) — cap del Repricer

**Implicancia**: en Walmart, el listing y el Repricer se crean juntos en el mismo XLSX. En Amazon, Automate Pricing se configura aparte. Para el módulo `walmart-listings`, esto significa que el workflow de onboarding genera AMBOS al mismo tiempo.

## Sheet "Trade Item Configurations" (9 cols)

Walmart separa el listing (contenido del cliente) del trade item (dimensiones físicas del SKU para supply chain). Útil para auditorías logísticas independientes.

Columnas:
- `sku` (col 4)
- `countryOfOriginAssembly` (col 5)
- `eachWidth` (col 6) — Decimal, inches, 0-999999999
- `eachHeight` (col 7) — Decimal, inches, 0-999999999
- `eachDepth` (col 8) — Decimal, inches, 0-999999999
- `eachWeight` (col 9) — Decimal, lbs, 0-99999999999

## Sheet "Data Definitions" (77 rows × 8 cols)

Documentación field-by-field. Columnas:
- Attribute Name
- Definitions
- Product Type
- Example Values
- Min Characters
- Max Characters
- Min Number of Values
- Recommended Number of Values

**Esto es la base de un validador automático**. El módulo puede leer Data Definitions, generar reglas de validación dinámicas (min/max chars, # values requeridos), y validar el sheet de datos antes de upload.

## Campos distintivos vs Amazon — quick reference

Campos que NO existen como columna estructurada en flat files de Amazon o tienen forma muy distinta:

- `prop65WarningText` (California Prop 65 — Amazon lo tiene pero menos visible)
- `electronicsIndicator` + 14 atributos de batería separados
- `safetyDataSheet`, `numberOfHazardousComponents`
- `isPesticide`, `pesticide_type`
- `fsma_section_204_traceability` (FDA FSMA)
- `nationalDrugCode12` (NDC para OTC)
- `dietaryMethod`, `dietaryNeed`, `ingredientPreference` (closed lists, no prosa libre)
- `healthConcerns`, `symptoms` (closed lists — Amazon te suspende por estos en bullets)
- `dosage`, `medicineStrength`, `servingSize`, `servingsPerContainer`
- `productLine` (explícito; Amazon lo trata como variation theme)
- `food_and_drug_fact_label_type` (FDA label type)
- `thirdPartyAccreditationSymbolOnProductPackageCode` (USDA Organic, NSF, etc.)
- `stateRestrictions`, `zipCodes` (geographic restrictions nativas)
- Pricing/Repricer integrado al template de creación

## Diseño preliminar del módulo `walmart-listings`

Idea esbozada en sesión 1, no para construir todavía:

```
walmart-listings/
├── parser.py            # Skip rows 1-5, mapear Row 4 (UI) + Row 5 (API)
├── validator.py         # Lee Data Definitions → genera reglas dinámicas
├── compliance_gate.py   # Flags items con healthConcerns/symptoms vacíos en H&W
├── repricer_auto.py     # Aplica min/max según margen objetivo + elige strategy
├── diff_engine.py       # Compara template generado vs último uploaded → solo cambios
└── pre_upload_check.py  # Image URL accesible, GTINs válidos, state restrictions coherentes
```

**Decisión arquitectónica**: este módulo NO existe todavía. Va al backlog para evaluar prioridad vs M27 cleanup, M30 F3.5, y listing comprehension auditor.

## Cuándo re-snapshot

Re-descargar el spec template y re-generar este documento cuando:
- Walmart bumpee la versión del schema (`5.0.YYYYMMDD-HH_MM_SS`).
- Se agreguen nuevos product types relevantes (cosmetics, food, OTC drugs, etc.).
- Aparezcan campos nuevos en cambios anunciados por Walmart Marketplace.
