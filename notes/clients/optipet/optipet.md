---
tipo: client
nombre: OPTIPET
tipo_relacion: personal (Lenin freelance, NO Capybaras)
estado: activo
marketplace: MX
categoria: petfood
cuenta: gestionada directamente por Lenin
ppc_status: sin historial — PPC futuro
actualizado: 2026-05-09
---

# OPTIPET

## Resumen

Cliente personal de Lenin Acosta gestionado directamente fuera de la agencia. Marca de suplementos alimenticios premium para perros adultos en Amazon México. Operación puntual de variation family completada el 2026-05-08 — 3 children FBA agrupados bajo un parent nuevo, todos OOS al cierre con 24 unidades inbound por SKU.

## Estructura del catálogo

### Variation Family activa (creada 2026-05-08)

| Rol | ASIN | SKU | Sabor / Theme | Estado |
|---|---|---|---|---|
| Parent | `B0H12ZXVPF` | `OPTIPET_ADULT_PARENT` | (referente, no comprable) | Asignado por Amazon post-feed |
| Child | `B0G6VWT7RB` | `OPTIPETVITALITY` | Vitality | OOS · 24u inbound |
| Child | `B0G6TW7G12` | `OPTIPETSKINCOAT` | Skin and Coat | OOS · 24u inbound |
| Child | `B0G6TPVT2G` | `OPTIPETHEALTHYGUT` | Healthy Gut | OOS · 24u inbound |

### Configuración del variation
- **Theme**: `Sabor` (`flavor_name` col 39 del flat file `fptcustom`)
- **Valores custom validados**: Vitality / Skin and Coat / Healthy Gut (semánticos no-sabor en inglés, aceptados sin warnings por Amazon MX)
- **Browse node**: `11601177001` (validado para suplementos en polvo)
- **Stock al 2026-05-09**: Vitality 16u FBA, Skin and Coat 18u FBA, Healthy Gut 17u FBA. Total 51u operativo. Precio MXN $649 con Buy Box ganado en los 3.

### Pre-flight cleanup ejecutado
- SKU `OPTIPETSKINCOATFBA` (FBM zombi, 15u Active) compartía ASIN `B0G6TW7G12` con el child FBA — apagado vía `Close listing` antes del feed para respetar la regla "1 ASIN ≠ 2 children".

### Variation Family #2 — OPTIPET Flavor Boost (creada 2026-05-09)
- Parent ASIN: B0H16N6SHP · SKU: OPTIPET_FLAVORBOOST_PARENT (creado 2026-05-09)
- Children FBA-only (3 sabores planificados, 1 creado al 2026-05-09):
  - ✅ B0H16T5H18 · OPTIPETFLAVORHIGADO (Hígado y Espirulina) — UPC 613365967019
  - 🔴 sin ASIN · OPTIPETFLAVORPULMON (Pulmón y Melena de León) — UPC 613365694298 BLOQUEADO
  - 🔴 sin ASIN · OPTIPETFLAVORPOLLO (Pollo y Cúrcuma) — UPC 613365971085 BLOQUEADO
- Theme variation: Sabor (valores en español)
- Bloqueante: UPCs de Pulmón y Pollo colisionan con OPTIPET Gato Premios Inactive (B0GPPR1ZGC + B0GPPXWPB1)
- Pendiente respuesta cliente: ¿eliminar Cat Treats Inactive para liberar UPCs?

## Hitos completados

- **2026-05-08** — Variation Family creada vía flat file Variation Builder.
  - Feed batch ID Amazon: `50059020581`
  - Resultado: 4/4 SKUs successful · 0 errors · 0 warnings
  - Parent ASIN asignado: `B0H12ZXVPF`
  - Variation Family confirmada en Seller Central post-upload
  - Snapshot del flat file: `flat-files/OPTIPET_AdultParent_2026-05-08.txt`
- **2026-05-09**: Variation Family #2 FlavorBoost iniciada. 2/4 SKUs creados (parent + Hígado). 2 children bloqueados por collision UPC con OPTIPET Cat Treats Inactive (Tuna Bites B0GPPR1ZGC + Chicken Bites B0GPPXWPB1).

## Pendientes activos

### Operativos (esperan trigger externo)
1. Esperar arrival inbound 72u FBA (24u × 3 children) — fecha TBD.
2. Definir fecha oficial de launch del variation family.
3. Definir hero del variation — cuál de los 3 children será el default mostrado en search results.

### Listing post-agrupación
4. Validar bullets / A+ Content de cada child post-agrupación (que sigan reflejando el child individual y no se hayan sobrescrito).
5. Decidir Brand Store / A+ específico del parent — cómo presentar la familia completa.

### PPC (cuando se inicien campañas)
6. Definir naming convention propio (no aplica el estándar Capybaras).
7. Decidir arquitectura: campañas separadas por child vs única apuntando al parent.

### FlavorBoost (sesión 2026-05-09)
8. Esperar respuesta cliente: eliminación de Cat Treats Inactive (libera UPCs) vs alternativas
9. Conseguir imágenes Flavor Boost (3 main_image_url públicas)
10. Confirmar ingredientes reales Pulmón y Pollo con iNASA Innovation
11. Confirmar shelf life real del producto (default 730d en feed actual)

## Notas operativas

- **SKUs FBA-only por política del cliente.** Si aparecen FBMs nuevos compartiendo ASIN con un child, apagar antes de cualquier cambio en variations (lección aprendida 2026-05-08 con `OPTIPETSKINCOATFBA`).
- **Browse node validado**: `11601177001` — reutilizar para futuros productos OPTIPET de la misma línea (suplementos en polvo).
- **Theme `Sabor` con valores custom en inglés**: validado en MX. Amazon acepta strings fuera del dropdown sin warnings, incluso semánticos no-sabor.
- **Reviews y BSR**: se consolidan a nivel parent post-agrupación. Monitorear en próxima sesión cuando lleguen ventas.
- **Parent NO comprable**: solo referente. Children mantienen ASINs originales y son los que venden.
- **Variation Family Adult 100% operativa al 2026-05-09** (51u stock total, precio $649, Buy Box ganado).
- **VITALPET_ADULT_PARENT ASIN confirmado**: B0GZLWRY9Z (Jan 2026).
- **Cat Treats OPTIPET Inactive desde Feb 2026** (Tuna Bites + Chicken Bites) — UPCs reutilizados en cajas Flavor Boost causando collision.

## Wikilinks

[[2026-05-08-variation-builder-flat-file-format]] · [[arranque-optipet]] · [[2026-05-08]]
