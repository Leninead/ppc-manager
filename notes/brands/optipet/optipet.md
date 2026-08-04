---
tipo: client
nombre: OPTIPET
tipo_relacion: personal (Lenin freelance, NO Capybaras)
estado: activo
marketplace: MX
categoria: petfood
cuenta: gestionada directamente por Lenin
ppc_status: sin historial — PPC futuro
actualizado: 2026-05-14
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
- Children FBA-only (3 sabores planificados, 3 creados al 2026-05-19):
  - 🟡 B0H16T5H18 · OPTIPETFLAVORHIGADO (Hígado y Espirulina) — UPC 613365967019 — Inactive por compliance, peso ahora correcto 297g
  - 🟡 B0H2CFM37X · OPTIPETFLAVORPOLLO (Pollo y Cúrcuma) — UPC 610655848478 — en review 48h (hasta ~2026-05-21)
  - 🔴 B00ZCVB3Z8 · OPTIPETFLAVORPULMON (Pulmón y Melena de León) — UPC 610655663064 — ASIN viejo heredado de catálogo previo, item_name pisado, requiere investigación
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
- **2026-05-12** — Diagnóstico compliance Hígado + análisis Innasa Master Sheet.
  - Identificado bloqueo del Hígado: violación política `GRLKLZ6WQ9R259LC` Pet Consumables MX
  - Encontrado panel oficial Amazon "Add Compliance" para upload de docs
  - Confirmados ingredientes reales Pulmón (Pulmón y Melena de León) y Pollo (Pollo y Cúrcuma)
  - Pricing oficial Flavor Boost confirmado: $349 MXN Amazon / $303.48 MXN real
  - Identificada línea OPTICAT nueva (3 SKUs para gatos, 80g, $299 MXN)
  - UPCs originales de Pulmón y Pollo confirmados como bloqueados permanentemente (cliente no elimina Cat Treats Inactive)
- **2026-05-14** — Respuesta de Mario al pedido del 2026-05-12.
  - 4 UPCs nuevos agregados al pool ADAM REQUEST en master sheet (filas 21-24)
  - UPCs disponibles: 610655663064 · 610655848478 · 610655951536 · 610655934935
  - Codebars físicos generados por Mario en Drive folder "ADAM CODEBARS" (4 formatos × 4 UPCs)
  - Master sheet confirma peso bruto del paquete Flavor Boost: **297g** (resuelve pendiente vs 360g del v4)
  - Mensaje enviado a Mario en formato pregunta abierta (no asumir nada sobre cajas) — esperando respuesta sobre asignación UPC + estado packaging
- **2026-05-19** — Upload v5 + v6 FlavorBoost. Hallazgos GS1 + 2 gotchas nuevas.
  - **v5 (UPCs lockeados Mario)**: 13 issues — error 8541 confirma contaminación GS1 de los 2 UPCs que Mario asignó (951536→colisión B0GPPR1ZGC / 934935→colisión B0GPPXWPB1)
  - **v6 (UPCs sobrantes pool)**: 7 issues — Pollo creado limpio (B0H2CFM37X, review 48h), Pulmón creado con ASIN viejo heredado (B00ZCVB3Z8, UPC 663064 ya en catálogo)
  - **Hígado patch peso 297g aplicado** vía PartialUpdate quirúrgico (con flavor_name explícito tras gotcha 15)
  - **Snapshots**: `flat-files/OPTIPET_FlavorBoost_2026-05-19_v5.txt` + `flat-files/OPTIPET_FlavorBoost_2026-05-19_v6.txt`
- **2026-05-21** — A+ Premium Vitality creado. Patrón: A+ por child (no parent). 4 módulos visibles: Hero "Combustible premium" / Lifestyle "Almas imparables" / Dr. Bacterias endorsement / Beneficios (Aminoácidos + Metabolismo + Para Perros Activos). Status approval TBD.
- **2026-05-22 (confirmado en cierre 2026-05-21)** — Estado Adult variation family verificado: 179u FBA totales (59+60+60). Inbound 72u + pre-existentes consolidados. **Primera venta Adult: Vitality 1u en 30d window** = primer ingreso operativo OPTIPET Adult.

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
8. **UPCs nuevos del fabricante** para Pulmón y Pollo (cliente rechazó eliminar Cat Treats Inactive — la única salida es UPCs nuevos asignados por PETSA)
9. Conseguir imágenes Flavor Boost (3 main_image_url públicas)
10. Confirmar ingredientes reales Pulmón y Pollo con iNASA Innovation
11. Confirmar shelf life real del producto (default 730d en feed actual)
12. **Compliance documentation Hígado** — esperando del cliente:
    - COA del producto Flavor Boost (3 sabores)
    - Etiqueta física alta resolución (frente, dorso, laterales)
    - Ficha técnica con análisis garantizado
    - Status regulatorio (¿desregulado clase III o código SAGARPA 8 dígitos?)
    - Certificación Non-GMO formal (sin esto, sacar claim del título)
13. ✅ **RESUELTO 2026-05-14**: peso bruto del paquete = 297g (confirmado master sheet col 31 rows 13-15)
14. **Imágenes finales en URLs públicas**: las del master sheet están en Drive (no aceptado por Amazon main_image_url) — hay que re-hostear
15. **OPTICAT roadmap Amazon**: confirmar si entra al pipeline (3 SKUs nuevos para gatos identificados en master sheet)
16. **FBM zombi `OPTIPETSKINCOATFBA` reapareció Active el 2026-05-06** — apagar con Close listing real

### A+ Content roadmap (decisión: por child, no parent)
- A+ Premium Skin and Coat (`B0G6TW7G12`) — pendiente arte equivalente al de Vitality
- A+ Premium Healthy Gut (`B0G6TPVT2G`) — pendiente arte equivalente al de Vitality
- Verificar status approval A+ Vitality (próxima sesión)

## Notas operativas

- **SKUs FBA-only por política del cliente.** Si aparecen FBMs nuevos compartiendo ASIN con un child, apagar antes de cualquier cambio en variations (lección aprendida 2026-05-08 con `OPTIPETSKINCOATFBA`).
- **Browse node validado**: `11601177001` — reutilizar para futuros productos OPTIPET de la misma línea (suplementos en polvo).
- **Theme `Sabor` con valores custom en inglés**: validado en MX. Amazon acepta strings fuera del dropdown sin warnings, incluso semánticos no-sabor.
- **Reviews y BSR**: se consolidan a nivel parent post-agrupación. Monitorear en próxima sesión cuando lleguen ventas.
- **Parent NO comprable**: solo referente. Children mantienen ASINs originales y son los que venden.
- **Variation Family Adult 100% operativa al 2026-05-09** (51u stock total, precio $649, Buy Box ganado).
- **VITALPET_ADULT_PARENT ASIN confirmado**: B0GZLWRY9Z (Jan 2026).
- **Cat Treats OPTIPET Inactive desde Feb 2026** (Tuna Bites + Chicken Bites) — UPCs reutilizados en cajas Flavor Boost causando collision.
- **Master Sheet INASA es fuente de verdad para datos de producto** (peso, dimensiones, ingredientes, pricing). Validado 2026-05-12.
- **SKU naming Amazon ≠ SKU naming master sheet INASA**: el master sheet usa OP-FLB-LIV-270J / OP-FLB-LNG-270J / OP-FLB-CHK-270J; Amazon usa OPTIPETFLAVOR{SABOR}. Mantener Amazon naming en flat files.
- **Línea OPTICAT** (3 SKUs para gatos, 80g, $299 MXN): identificada en master sheet 2026-05-12, NO lanzada en Amazon todavía. UPCs: 610655906857 (Chicken), 610655895748 (Liver), 610655814770 (Tuna).
- **Política compliance Amazon MX Pet Food**: `GRLKLZ6WQ9R259LC`. URL: https://sellercentral.amazon.com/help/hub/reference/GRLKLZ6WQ9R259LC
- **Decisión cliente 2026-05-12**: NO eliminar Cat Treats Inactive (Tuna Bites + Chicken Bites). UPCs originales 613365694298 + 613365971085 quedan reservados permanentemente.
- **Peso bruto paquete Flavor Boost CONFIRMADO 297g** (master sheet col 31, rows 13-15, validado 2026-05-14). Aplicar `package_weight = 297 GR` en futuros flat files (corrección sobre `360 GR` usado en v4).
- **4 UPCs nuevos disponibles en pool ADAM REQUEST** (master sheet rows 21-24 al 2026-05-14): `610655663064`, `610655848478`, `610655951536`, `610655934935`. Codebars físicos en Drive folder "ADAM CODEBARS" (4 formatos × 4 UPCs). Intercambiables operativamente hasta que Mario confirme preferencia o lockee asignación en GS1.
- **Hallazgo lateral master sheet 2026-05-14**: VITALPET row 6 (Chicken Based Adult) y row 11 (Chicken Cookie) comparten UPC `613365632764`. Duplicado interno VITALPET, no problema OPTIPET. Documentado por si Mario lo plantea más adelante.
- **Regla epistemológica 2026-05-14 (Lenin)**: no asumir nada que no haya sido dicho explícitamente por la contraparte. En particular: no asumir estado de cajas físicas, no asumir asignación de UPC, no asumir timing de inbound. Preguntar primero, actuar después.
- **GS1 platform contamina UPCs nuevos cuando el fabricante hace update vinculándolos a ASINs viejos** (2026-05-19). Pre-flight check: pedir al fabricante NO hacer update GS1 hasta que Amazon confirme creación del ASIN nuevo desde cero.
- **`unit_count` + `unit_count_type` obligatorios** para petfood MX 2026 (validado v5/v6). Para 270g polvo: `270` + `gramo`.
- **PartialUpdate en variation child requiere `flavor_name` explícito** aunque el listing ya lo tenga seteado. Sin él, error 99003.
- **Campos vacíos en `Update` NO nulean valores previos** — Amazon retiene del feed previo. Para limpiar URLs placeholder TBD, sobreescribir con URL real.
- **Template fptcustom Pet Food MX version actualizada a `2026.0508`** (era `2026.0427` en knowledge anterior). 220 cols upload / 222 cols processing summary.
- **A+ Content por child, no parent** (decisión 2026-05-21): debido a que el arte de cada sabor es específico (frasco + claim de beneficio individual), A+ se hace a nivel child. Implicación: requiere 3 A+ separados para cubrir Vitality / SkinCoat / HealthyGut. Workaround si arte por sabor no está disponible: A+ genérico a nivel parent. Patrón a replicar también en Flavor Boost cuando lleguen imágenes.

## Wikilinks

[[2026-05-08-variation-builder-flat-file-format]] · [[arranque-optipet]] · [[2026-05-08]]
