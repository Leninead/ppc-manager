---
tipo: client
nombre: OPTIPET
tipo_relacion: personal (Lenin freelance, NO Capybaras)
estado: activo
marketplace: MX
categoria: petfood
cuenta: gestionada directamente por Lenin
ppc_status: sin historial — PPC futuro
actualizado: 2026-05-08
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
- **Stock total FBA al 2026-05-08**: 0 disponibles · 72u inbound

### Pre-flight cleanup ejecutado
- SKU `OPTIPETSKINCOATFBA` (FBM zombi, 15u Active) compartía ASIN `B0G6TW7G12` con el child FBA — apagado vía `Close listing` antes del feed para respetar la regla "1 ASIN ≠ 2 children".

## Hitos completados

- **2026-05-08** — Variation Family creada vía flat file Variation Builder.
  - Feed batch ID Amazon: `50059020581`
  - Resultado: 4/4 SKUs successful · 0 errors · 0 warnings
  - Parent ASIN asignado: `B0H12ZXVPF`
  - Variation Family confirmada en Seller Central post-upload
  - Snapshot del flat file: `flat-files/OPTIPET_AdultParent_2026-05-08.txt`

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

## Notas operativas

- **SKUs FBA-only por política del cliente.** Si aparecen FBMs nuevos compartiendo ASIN con un child, apagar antes de cualquier cambio en variations (lección aprendida 2026-05-08 con `OPTIPETSKINCOATFBA`).
- **Browse node validado**: `11601177001` — reutilizar para futuros productos OPTIPET de la misma línea (suplementos en polvo).
- **Theme `Sabor` con valores custom en inglés**: validado en MX. Amazon acepta strings fuera del dropdown sin warnings, incluso semánticos no-sabor.
- **Reviews y BSR**: se consolidan a nivel parent post-agrupación. Monitorear en próxima sesión cuando lleguen ventas.
- **Parent NO comprable**: solo referente. Children mantienen ASINs originales y son los que venden.

## Wikilinks

[[2026-05-08-variation-builder-flat-file-format]] · [[arranque-optipet]] · [[2026-05-08]]
