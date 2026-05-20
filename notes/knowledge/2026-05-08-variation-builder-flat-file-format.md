---
tipo: knowledge
actualizado: 2026-05-19
cliente: OPTIPET
marca: OPTIPET
template_version: 2026.0508
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

220 columnas en el archivo upload (222 en el processing summary — Amazon agrega 2 cols `::number_of_attributes_with_errors` y `::number_of_attributes_with_other_suggestions` al inicio post-procesamiento, NO van en el archivo de upload), 7+ filas:

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
7. **"FBM 0" del parent es transitorio (no es bug)**: después de un upload de variation, el parent SKU puede aparecer en Manage All Inventory con `Available (FBM) 0` y status "Missing offer". Esto NO es bug — es estado default mientras los children todavía no están activos con oferta válida (precio + stock + imagen). Una vez que los children se procesan correctamente y tienen Featured Offer, el "FBM 0" del parent desaparece. NO intentar forzar FBA en el parent. Validado en 3 casos: VITALPET_ADULT_PARENT, OPTIPET_ADULT_PARENT, OPTIPET_FLAVORBOOST_PARENT.
8. **Pet Food MX endureció requirements en 2026**: campos `max_order_quantity` y `number_of_items` son obligatorios para `feed_product_type=petfood` en MX al 2026-05-09 aunque NO lo eran cuando VITALPET pasó en Jan 2026. Para Pet Food MX, hoy requiere AMBOS campos en cada child (típicamente max_order_quantity=999 sin límite, number_of_items=1 cuando es 1 envase).
9. **Bug crítico: `\n` y `\t` crudos rompen TSV**: si `product_description` (o cualquier campo) tiene saltos de línea reales, escribir el archivo como TSV los interpreta como cambio de fila. Resultado: archivo con N filas falsas en lugar de las reales. Validar SIEMPRE antes de escribir el .txt: ningún valor puede contener `\n`, `\t` ni `\r` crudos. Reemplazar por espacio o separador plano.
10. **Valores enum en INGLÉS aunque label esté en español**: el template muestra labels en español (ej. "Tipo de caducidad del producto") pero los valores válidos del campo `product_expiration_type` son `Expiration Date Required` o `Expiration On Package` en INGLÉS. NO traducir el label como valor. Consultar SIEMPRE la hoja "Valores válidos" del template `.xlsm` para campos enum antes de asumir traducciones.
11. **Listings Inactive NO liberan UPCs** (deuda M26 → VB-011): Amazon mantiene UPCs reservados para listings en estado Inactive. Si querés reutilizar un UPC de un listing inactivo en uno nuevo, hay que ELIMINAR completamente el listing inactivo (Delete listing & product), no solo desactivarlo. Después esperar 24-48h para que Amazon refleje la liberación. Validado con caso OPTIPET Cat Treats Feb 2026 vs FlavorBoost May 2026.
12. **Error 99001 puede ser falso positivo**: el código 99001 ("se requiere un valor para X") a veces se dispara no porque el campo sea estrictamente requerido, sino porque Amazon perdió la detección del feed_product_type. Si el campo aparece como requerido pero no debería serlo según el SOP, verificar primero la integridad del archivo (ver gotcha 9) y la columna feed_product_type antes de asumir que el campo es obligatorio.
13. **Error 8541 (catalog conflict)**: cuando el UPC enviado ya existe en el catálogo Amazon asignado a otro ASIN. Mensaje típico: "El ean proporcionado coincide con el ASIN [X], pero algunos de los datos del listado contradicen lo que ya se encuentra en el catálogo de Amazon". Soluciones: (a) eliminar el ASIN preexistente si te pertenece, (b) usar gtin_exemption_reason=Pieza para evitar UPC, (c) conseguir UPCs nuevos.
14. **`unit_count` + `unit_count_type` obligatorios para petfood MX 2026** (validado v5 OPTIPET FlavorBoost 2026-05-19): error 99001 si faltan. Valores válidos `unit_count_type`: `unidad`, `gramo`, `metro`, `mililitro`, `metro cuadrado`. Para productos sólidos por peso (Flavor Boost 270g polvo): `unit_count=270` + `unit_count_type=gramo`.
15. **PartialUpdate en variation child REQUIERE `flavor_name` (o el atributo del theme) explícito** (validado v5 OPTIPET 2026-05-19): aunque PartialUpdate "respeta los campos no enviados", Amazon valida integridad del variation theme y exige el atributo del theme. Sin él, error 99003 doble (uno por variation_theme col 30, otro por flavor_name col 41).
16. **UPCs "nuevos" del fabricante pueden venir contaminados en GS1**: si el fabricante registra los UPCs en GS1 platform vinculándolos a ASINs viejos del mismo seller (intencional o no), Amazon dispara error 8541 al subir. Pre-flight check sugerido: pedir al fabricante NO hacer update GS1 hasta que Amazon confirme creación del ASIN nuevo desde cero. Validado 2026-05-19 con OPTIPET: 2 de 4 UPCs del pool ADAM REQUEST contaminados (951536+934935 linkeados a Cat Treats Inactive B0GPPR1ZGC + B0GPPXWPB1).
17. **Campos vacíos en `Update` NO nulean valores previos** (validado 2026-05-19): si un SKU tuvo un valor inválido en upload previo (ej: URL placeholder), mandar el campo vacío en upload posterior NO lo borra — Amazon retiene del feed previo. Para limpiar, sobreescribir con valor válido. Caso real: URLs `http://TBD-pending-image-URL-*` persistieron del v5 al v6 aunque el v6 enviaba `main_image_url` vacío.
18. **UPCs ya en catálogo Amazon → match a ASIN existente, no creación nueva**: si el UPC enviado ya existe en el catálogo Amazon (vinculado a cualquier producto previo del seller o de otros), Amazon hace match al ASIN existente en lugar de crear uno nuevo. El SKU nuevo hereda imagen + item_name + datos del producto previo. Detectar por formato del ASIN devuelto: `B00*` (pre-2017) o `B07*` (2017-2020) cuando esperabas `B0H*` o `B0G*` (2024+). Caso 2026-05-19: OPTIPETFLAVORPULMON con UPC 610655663064 → heredó ASIN `B00ZCVB3Z8` y disparó error 90244 al rechazar el flavor_name nuevo.

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

## Caso de éxito #3 — OPTIPET FlavorBoost (2026-05-09 → 2026-05-19)

### Inputs
- Cliente: OPTIPET (cliente personal de Lenin, NO Capybaras)
- 3 productos Flavor Boost a crear desde cero (270g, polvo, FBA, suplemento topper)
- Parent SKU nuevo: OPTIPET_FLAVORBOOST_PARENT
- Theme: Sabor con valores en español (decisión: español encaja mejor culturalmente para sabores reales)
- Diferencia clave vs casos #1 y #2: **listing rico desde cero** — children con `update_delete=Update` y payload completo (item_name, bullets, description, ingredients, peso, dimensiones, caducidad). NO minimal payload.

### Resultado al cierre 2026-05-09
- ✅ Parent ASIN B0H16N6SHP creado
- ✅ Child Hígado y Espirulina ASIN B0H16T5H18 creado (UPC 613365967019)
- 🔴 Child Pulmón y Melena de León bloqueado (UPC 613365694298 colisión con B0GPPR1ZGC Tuna Bites Inactive)
- 🔴 Child Pollo y Cúrcuma bloqueado (UPC 613365971085 colisión con B0GPPXWPB1 Chicken Bites Inactive)

### 4 versiones del flat file iteradas
| Versión | Fix aplicado | Resultado |
|---|---|---|
| v1 | Estado inicial | 1/4 — bug `\n`, faltan max_order_quantity/number_of_items |
| v2 clean | Sin max_order_quantity ni number_of_items (replicar VITALPET) | 1/4 — confirma que SÍ son requeridos |
| v3 | max_order_quantity=999, number_of_items=1, parent en PartialUpdate | 1/4 — falla por product_expiration_type valor inválido |
| v4 | product_expiration_type='Expiration On Package' | 2/4 — Hígado pasa, Pulmón/Pollo bloqueados por UPC collision |

### Datos validados para futuros listings ricos OPTIPET
- `item_form` = "Polvo" (col 45)
- `unit_count` = "270" + `unit_count_type` = "Gramo" (cols 46-47)
- `package_weight` = 360g (cuando producto neto = 270g, paquete cerrado ≈ 360g)
- `package_length` x `package_width` x `package_height` = 9.46 x 9.26 x 9.26 CM (envases tipo lata 270g)
- `is_expiration_dated_product` = "TRUE"
- `product_expiration_type` = "Expiration On Package" (cuando label dice "VÉASE EN EMPAQUE")
- `fc_shelf_life` = 730 días default razonable para suplementos en polvo
- `max_order_quantity` = 999 (sin límite efectivo)
- `number_of_items` = 1 (cuando SKU = 1 envase, no pack)
- `bullet_point1-5` = max 100 chars cada uno (validado)
- `item_name` = max 250 chars (validado)
- `product_description` = max 2000 chars, sin saltos de línea crudos (validado)

### Pendientes para retomar
- Respuesta cliente: ¿eliminar Cat Treats Inactive para liberar UPCs?
- Conseguir 3 main_image_url públicas
- Confirmar ingredientes reales Pulmón y Pollo
- Confirmar shelf life real (default 730d)

### Continuación 2026-05-19 (uploads v5 + v6)

**Inputs nuevos**:
- 4 UPCs nuevos del pool ADAM REQUEST (entregados por Mario 2026-05-13):
  - 610655663064 / 610655848478 / 610655951536 / 610655934935
- Mario asignó en master sheet: Pulmón→951536, Pollo→934935
- Peso paquete corregido a 297 GR (master sheet col 31, era 360 GR en v4)

**v5 — primer intento (2026-05-19)**: 13 issues
- Resultado: 4 procesados, 3 errores, 1 advertencia. Sin SKU creado.
- Causa raíz: gotchas 14 + 15 + 16 + 17 desconocidas hasta esta sesión.

**v6 — segundo intento (2026-05-19, con fixes)**: 7 issues
- UPCs cambiados a los sobrantes (pool ADAM REQUEST no asignados por Mario): Pulmón→663064, Pollo→848478
- Fix gotcha 14: agregado unit_count=270 + unit_count_type=gramo
- Fix gotcha 15: flavor_name="Hígado y Espirulina" en patch Hígado
- ASINs asignados:
  - OPTIPETFLAVORPOLLO → **B0H2CFM37X** ✅ (review 48h, normal)
  - OPTIPETFLAVORPULMON → **B00ZCVB3Z8** 🔴 (gotcha 18: ASIN viejo heredado)
  - OPTIPETFLAVORHIGADO → B0H16T5H18 (patch peso 297g OK)

**Estado al 2026-05-19**: 3 de 3 children "creados" pero solo 1 funcionalmente limpio (Pollo). Pulmón requiere investigación de B00ZCVB3Z8. Hígado peso corregido pero sigue Inactive por compliance.

## Caso de estudio #4 — Compliance Amazon MX bloquea listing (OPTIPET FlavorBoost Hígado, 2026-05-10)

### Contexto
Listing creado exitosamente el 2026-05-09 (caso #3) pasó a Inactive el 2026-05-10 por violación de política de producto, NO por error en flat file.

### Causa raíz
Amazon MX clasificó al producto como "nutritional supplement" y aplicó automáticamente la política `GRLKLZ6WQ9R259LC` (Pet Consumables: Food and Product Safety Issues), que exige documentación específica antes de permitir la venta.

### Lección operativa nueva (gotcha #14)

**Crear el listing exitosamente NO significa que esté autorizado a vender.** Categorías reguladas (Pet Food MX, suplementos, alimentos, dietary supplements) tienen una capa de compliance automática que se aplica horas o días después del feed exitoso. Si falta documentación de producto, Amazon suprime el listing.

**Mitigación pre-launch**: para categorías reguladas, **antes de subir el flat file**:
1. Identificar la política Amazon aplicable (buscar "Restricted products" + categoría en Seller Central)
2. Validar que se tiene el paquete completo de docs ANTES de crear el listing
3. Tener el panel "Add Compliance" identificado y los docs preparados para upload inmediato post-feed

### Documentación requerida por la política GRLKLZ6WQ9R259LC

Lista oficial Amazon MX para Pet food y suplementos nutricionales:
- Nombre y dirección del fabricante, importador, distribuidor o representante autorizado
- Etiquetas del producto (físicas, alta resolución, frente y dorso)
- Marcas de cumplimiento visibles en empaque
- Advertencias de peligro
- Instrucciones y manuales del producto
- Nombre del producto
- Lista de ingredientes
- Código de autorización SAGARPA de 8 dígitos (CRÍTICO, visible en empaque)

Si producto es **desregulado clase III "venta libre"**: justificar citando el "ACUERDO por el que se especifican los productos no medicados para uso o consumo animal que se desregulan" (publicado en DOF 29/11/2010) + Dictamen de Verificación SENASICA del fabricante.

### Ruta de navegación al panel de upload

Seller Central → Manage Inventory → buscar SKU → click "Edit" del listing → tab **Safety & Compliance** → panel "Add Compliance" → opción "Add compliance for this product" (Not started) abre wizard guiado.

### Documentos válidos en el caso OPTIPET (validados al 2026-05-12)

Documentación corporativa (cubre fabricante + titular de marca):
- Aviso SENASICA de Inicio de Funcionamiento del fabricante (PETSA del Bajío, expediente 11685)
- Dictamen de Verificación SENASICA (folio KU0842, vigente 1 año)
- Constancia Fiscal SAT del titular de marca (INASA)
- Carta declaración fabricante-titular firmada por ambos CEOs
- Acuse IMPI del registro de marca (clase 5 para suplementos animales)

Documentación específica de producto (pendiente del cliente al cierre):
- COA del producto
- Etiqueta física alta resolución
- Ficha técnica con análisis garantizado
- Certificación Non-GMO formal (si título tiene claim Non-GMO)

## Wikilinks

[[SOP_Variation_Builder_FlatFile]] · [[CLAUDE]] · [[2026-05-08]] · [[STATE-agencia]] · [[optipet]]
