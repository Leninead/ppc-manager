# SOP — Crear Parent + Children Variations vía Flat File (Pet Food)

> **Última validación:** 2026-04-27 con VITALPET (B0GFK8GQ47, B0GFJYLKS6, B0GFKHKBDF)
> **Modo probado:** Merge / Actualización parcial (no toca listings existentes)
> **Marketplace:** MX (`A1AM78C64UM0Y8`)
> **Categoría:** Pet Food (`fptcustom`)

---

## 🎯 Cuándo usar este SOP

Cuando tenés N listings activos en Amazon que comparten todo excepto **un 
atributo** (sabor, tamaño, aroma, etc.) y querés agruparlos bajo un parent 
para mejorar conversión y CTR.

**Pre-requisitos:**
- Los N children ya existen en Amazon (tienen ASIN)
- Comparten marca, categoría y formato
- Difieren solo en el atributo del variation_theme

---

## 📥 Inputs necesarios del cliente

1. **Template flat file `.xlsm`** descargado de Seller Central → Catálogo → 
   Añadir productos a través de subida → Inventory Files (categoría aplicable)
2. **Reportes para verificar SKUs/ASINs:**
   - Inventory Report (`.txt` tab-separated)
   - All Listings Report (`.txt` tab-separated)
3. **Decisiones del cliente:**
   - SKU del parent nuevo (no existe en Amazon todavía)
   - Si hay FBA + FBM, cuáles agrupar (NO ambos del mismo ASIN)
   - Variation theme aplicable

---

## 🧬 Variation Themes válidos para Pet Food

| Theme (label) | Atributo Field Name | Cuándo usarlo |
|---|---|---|
| Sabor | `flavor_name` | Distintas proteínas/sabores |
| Nombre del Tamano | `size_name` | Distintos tamaños del mismo sabor |
| Tamano del Sabor | `size_name` + `flavor_name` | Sabor Y tamaño combinados |
| Nombre del Patron | `pattern_name` | Patrones de empaque |
| Scent | `scent_name` | Aromas (raro en comida) |
| FlavorName-SizeName | `flavor_name` + `size_name` | Sintaxis vieja, equivalente a "Tamano del Sabor" |
| Nombre del Patron y del Tamano | `pattern_name` + `size_name` | Patrón + tamaño |

---

## 🛡️ Regla de oro: 1 ASIN ≠ 2 children

Cada child de un parent **debe tener un ASIN único**. Si un producto tiene FBA 
y FBM (mismo ASIN, dos SKUs), elegí UNO solo para el variation. El otro queda 
como SKU stand-alone o se maneja aparte.

---

## 📝 Estructura del flat file

### Hoja a editar: `Plantilla` (datos desde fila 4)

### Fila 4 = PARENT (modo Crear o reemplazar — full update)

| Campo | Valor |
|---|---|
| `feed_product_type` | `petfood` |
| `item_sku` | SKU NUEVO (ej: `MARCA_PRODUCTO_PARENT`) |
| `brand_name` | Marca registrada en Amazon |
| `manufacturer` | Igual que brand (o el real) |
| `update_delete` | `Crear o reemplazar (actualización completa)` |
| `item_name` | Título genérico del parent (sin variante) |
| `recommended_browse_nodes` | ID del nodo (ver tabla abajo) |
| `gtin_exemption_reason` | `Pieza` |
| `parent_child` | `Parent` |
| `variation_theme` | Uno de los 7 listados arriba |
| `age_range_description` | `Adulto` / `Cachorro` / etc. |
| `target_audience_keywords` | `Perros` / `Gatos` / etc. |
| `country_of_origin` | `México` (u otro) |
| `condition_type` | `Nuevo` |
| `parent_sku`, `relationship_type` | **VACÍOS** |

### Filas 5+ = CHILDREN (modo Editar parcial — preserva listings)

| Campo | Valor |
|---|---|
| `feed_product_type` | `petfood` |
| `item_sku` | SKU EXISTENTE del child |
| `brand_name` | Igual que parent |
| `update_delete` | `Editar (Actualización parcial)` |
| `parent_child` | `Child` |
| `parent_sku` | SKU del parent (mismo de fila 4) |
| `relationship_type` | `variation` |
| `variation_theme` | Mismo que el parent |
| Atributo del theme | Valor único por child (ej: `flavor_name = "Pollo"`) |

**No incluir** otros campos en los children — modo merge respeta lo que ya 
está en el listing.

---

## 🍖 Browse nodes Pet Food MX (más comunes)

| Node ID | Categoría |
|---|---|
| 11601177001 | Alimento Seco para Perros |
| 11601177801 | Alimento Seco para Gatos |
| 11601176901 | Alimento Húmedo para Perros |
| 11601177701 | Alimento Húmedo para Gatos |
| 12478891701 | Suplementos Probióticos para Perros |
| 12478918011 | Suplementos Herbales para Perros |
| 12478915011 | Suplementos Antioxidantes para Perros |
| 12478599011 | Premios para Perros |

(lista completa: ver hoja "Valores válidos" del template, o buscar en Seller 
Central → Catálogo → Clasificar productos)

---

## 🍗 Flavors válidos del template visible (29) + alias API

El template Excel muestra una lista limitada en el dropdown, pero Amazon 
acepta más valores vía API. Si Seller Central muestra el valor en el dropdown 
de un listing existente, el feed lo va a aceptar.

**Lista del template:** Cordero, Fresa, Bacon, Venado, Queso, Hígado, Batata, 
Atún, Manzana, Arándano, Salmón, Calabaza, Mariscos, Cerdo, Arroz, Plátano, 
Calabacín, Pato, Arándano rojo, Pollo, Zanahoria, Bisonte, Conejo, Mantequilla 
de cacahuete, Pavo, Leche, Ternera, Huevo

**Alias API confirmados (no en dropdown pero válidos):**
- `Carne de vacuno` ← validado 2026-04-27 con VITALPET BEEFBASED

**Si dudás de un valor:** ir a Seller Central → editar un listing existente → 
ver qué muestra el dropdown del campo. Lo que aparezca ahí es válido.

---

## 🚨 Errores comunes y soluciones

| Error de Amazon | Causa | Fix |
|---|---|---|
| `Invalid value for variation_theme` | Amazon espera ID en inglés | Cambiar `Sabor` → `FLAVOR` |
| `Invalid value for flavor_name` | Valor no en el alias map | Probar variantes (Ternera / beef / Carne de vacuno) |
| `Item must have recommended browse node` | Browse node mal | Verificar ID en Seller Central |
| `Two children have same ASIN` | FBA y FBM del mismo producto como children | Solo uno de los dos por parent |
| `Parent SKU already exists` | El SKU del parent ya existía | Cambiar a uno nuevo |
| `Children belong to different brands` | Un child tiene marca distinta | Verificar `brand_name` en cada child |

---

## ✅ Caso de éxito de referencia (2026-04-27)

**Cliente:** VITALPET (alimento premium para perros adultos)

**Parent generado:** `VITALPET_ADULT_PARENT`

**Children agrupados (3 FBA, omitidos los FBM):**
- `VITALPET_BEEFBASED_ADULT_FBA` (B0GFK8GQ47) → flavor = Carne de vacuno
- `VITALPET_CHICKENBASED_ADULT_FBA` (B0GFJYLKS6) → flavor = Pollo
- `VITALPET_RABBITBASED_ADULT_FBA` (B0GFKHKBDF) → flavor = Conejo

**Variation theme:** Sabor
**Browse node:** 11601177001 (Alimento Seco para Perros)
**Resultado:** ✅ Feed procesado sin errores, parent + 3 children agrupados 
correctamente en Amazon MX.

---

## 🛠️ Cómo replicar el caso (5 pasos)

1. Pedir al cliente: template `.xlsm`, Inventory Report, All Listings Report
2. Identificar los 3+ ASINs candidatos a agrupar (mismo formato, distinto 
   atributo)
3. Validar en Seller Central qué valor de atributo está activo en cada 
   listing existente (no asumir, copiar lo que el cliente ya ve)
4. Llenar fila 4 (parent) y filas 5+ (children) según las tablas de arriba
5. Subir vía Seller Central → Catálogo → Añadir productos a través de subida 
   → Cargar archivo de inventario

**Tiempo de procesamiento típico:** 5-30 min.
**Validar:** ir al ASIN del parent (recién creado) en Amazon — debería 
aparecer un selector con las 3 variantes.

---

## 📌 Notas para el módulo Variation Builder (M26)

Este SOP refleja la lógica del módulo `modules/pages/variation_builder.py`. 
Cuando se actualice el módulo:

- El módulo actualmente tiene `update_delete = "Actualizar"` hardcodeado para 
  todos. **Mejora futura:** modo merge vs full update por child (parent 
  siempre full, children configurables).
- El módulo usa `Sabor` como theme literal — si Amazon empieza a exigir 
  `FLAVOR` en algún caso, agregar mapeo.
- Los flavors no están limitados al dropdown desde el fix de 2026-04-26 
  (TextColumn libre).
