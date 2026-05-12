---
tipo: prompt-arranque-cliente
cliente: optipet
nivel: cargado
actualizado: 2026-05-12
proxima_actualizacion: cierre próxima sesión OPTIPET
parent_asin: B0H12ZXVPF
flavorboost_parent_asin: B0H16N6SHP
status_catalogo: Adult variation family 100% operativa (51u FBA, Buy Box ganado) | FlavorBoost variation family 1 child Inactive por compliance, 2 children pendientes UPCs nuevos
status_ppc: sin historial al 2026-05-12 — agregar cuando se inicien campañas
status_compliance: Hígado bloqueado por política GRLKLZ6WQ9R259LC Pet Consumables MX — esperando docs cliente
---

# Arranque Sesión — OPTIPET

> Prompt customizado para arrancar cualquier sesión del cliente personal OPTIPET.
> Pegar el bloque XML del primer code block en chat nuevo de Claude.ai.
> Se actualiza al cierre de cada sesión con el delta — el bloque que se pega
> es estable; el delta vive en las secciones de "Estado actual" y "Pendientes".

---

## 🚀 Bloque para pegar al chat (estable)

```xml
<arranque_sesion cliente="optipet">

Hola Claude. Soy Lenin. Vengo a trabajar sesión OPTIPET — cliente personal mío, gestión directa fuera de cualquier agencia.

<contexto_proyecto>
Repo local: C:\proyectos\ppc-manager (rama main, conectado a GitHub Leninead/ppc-manager).
Vault Obsidian: notes/ dentro del repo, sincronizado vía GitHub a este proyecto Claude.
Cliente: OPTIPET — Amazon MX, suplementos alimenticios premium para perros adultos.
Relación: cliente personal directo (no es cuenta de agencia, no aplica workflow Capybaras).
PPC: sin historial al 2026-05-08 — agregar cuando se inicien campañas.
</contexto_proyecto>

<lectura_obligatoria_en_orden>
1. notes/clients/optipet/optipet.md (brand note: catálogo, hitos, pendientes activos)
2. notes/knowledge/2026-05-08-variation-builder-flat-file-format.md (formato flat file + caso de éxito OPTIPET)
3. notes/clients/optipet/flat-files/ (listar archivos disponibles para auditoría rápida)
4. El daily más reciente que mencione OPTIPET (buscar en notes/daily/ por "OPTIPET" o por fecha del último hito)
</lectura_obligatoria_en_orden>

<conocimiento_operativo_optipet>

## Variation Family activa (creada 2026-05-08)

| Rol | ASIN | SKU | Sabor | Estado |
|---|---|---|---|---|
| Parent | B0H12ZXVPF | OPTIPET_ADULT_PARENT | (referente) | Asignado por Amazon post-feed |
| Child | B0G6VWT7RB | OPTIPETVITALITY | Vitality | OOS · 24u inbound |
| Child | B0G6TW7G12 | OPTIPETSKINCOAT | Skin and Coat | OOS · 24u inbound |
| Child | B0G6TPVT2G | OPTIPETHEALTHYGUT | Healthy Gut | OOS · 24u inbound |

- Theme variation: Sabor con valores custom en inglés (validado en MX).
- Browse node: 11601177001 (suplementos en polvo).
- Stock total FBA: 0 disponibles · 72u inbound.
- FBM zombi apagado pre-feed: OPTIPETSKINCOATFBA (compartía ASIN B0G6TW7G12).

## Reglas duras del catálogo OPTIPET

- SKUs FBA-only por política del cliente. Si aparece un FBM nuevo compartiendo ASIN con un child, apagar antes de cualquier cambio en variations.
- Parent NO comprable: solo referente. Children mantienen sus ASINs originales y son los que venden.
- Reviews y BSR se consolidan a nivel parent post-agrupación (monitorear cuando lleguen ventas).
- Theme `Sabor` (col 39 `flavor_name`) acepta valores custom en inglés sin warnings.

## PPC: sin historial al 2026-05-08 — agregar cuando se inicien campañas

</conocimiento_operativo_optipet>

<flujo_de_arranque>
Una vez leído todo el contexto:

1. Confirmá brevemente que entendiste:
   - Estado actual de la Variation Family (parent + children, stock, OOS).
   - Hitos completados de la última sesión (qué se hizo y cuándo).
   - Pendientes activos del cliente (los que están en optipet.md).
   - Si hay flat files nuevos planeados o cambios de catálogo en pipeline.

2. Recordame correr antes de cualquier trabajo:
   - `cd C:\proyectos\ppc-manager && git status && git pull`
   - `git add . && git commit -m "checkpoint: antes de [tarea de hoy]"`

3. Preguntame qué queremos atacar hoy. NO arranques trabajo nuevo sin esa confirmación.

4. Si la tarea de hoy involucra un flat file nuevo → revisar primero notes/knowledge/2026-05-08-variation-builder-flat-file-format.md (gotchas + caso de éxito) y aplicar la regla "1 ASIN ≠ 2 children" antes de generar nada.

5. Si la tarea es PPC (primera vez) → tratar como greenfield: definir naming convention propia, decidir arquitectura (campañas por child vs apuntando al parent), y NO copiar convenciones de otras cuentas sin validar que apliquen a este catálogo.
</flujo_de_arranque>

<rituales_obligatorios>
Al final de cada sesión, recordame ejecutar (en este orden estricto):

1. Update de los archivos del cliente:
   - notes/clients/optipet/optipet.md (catálogo, hitos, pendientes)
   - notes/clients/optipet/flat-files/ (si se subió un flat file nuevo, agregar snapshot)
   - notes/daily/YYYY-MM-DD.md (resumen de la sesión)

2. Update de este mismo archivo: notes/prompts/sesion/clientes/arranque-optipet.md
   - Sección "Estado actual"
   - Sección "Pendientes activos"
   - Sección "Próxima evaluación"
   - Sección "Historial de actualizaciones"

3. Git commit + push:
   - `git add .`
   - `git commit -m "feat/fix/improve/docs: optipet [descripción concreta]"`
   - `git push`

4. Refresh manual en proyecto Claude (si aplica):
   - Ir al proyecto en claude.ai
   - "Add content from GitHub" → seleccionar archivos modificados
   - Sincronizar

5. Generar prompt de arranque para próxima sesión (si quedó algo a medias).

Si saltás cualquier paso de los 3 primeros, el próximo chat lee data stale y todo se rompe.
</rituales_obligatorios>

</arranque_sesion>
```

---

## 📊 Estado actual del cliente

> Esta sección se actualiza al cierre de cada sesión.

### Snapshot al cierre 2026-05-12

#### Variation Family #1 — Adult (creada 2026-05-08, 100% operativa)
| Child | ASIN | Stock FBA | Estado |
|---|---|---|---|
| Vitality | B0G6VWT7RB | 22u | Active, Buy Box ganado |
| Skin and Coat | B0G6TW7G12 | 22u | Active, Buy Box ganado |
| Healthy Gut | B0G6TPVT2G | 21u | Active, Buy Box ganado |

Total 65u FBA · Precio MXN $649 · Parent B0H12ZXVPF (OPTIPET_ADULT_PARENT)

⚠️ FBM zombi OPTIPETSKINCOATFBA reapareció Active el 2026-05-06 (15u, mismo ASIN B0G6TW7G12) — pendiente apagar con Close listing real.

#### Variation Family #2 — Flavor Boost (iniciada 2026-05-09, BLOQUEADA)
| SKU | ASIN | Estado |
|---|---|---|
| OPTIPET_FLAVORBOOST_PARENT | B0H16N6SHP | Inactive (consecuencia compliance del Hígado) |
| OPTIPETFLAVORHIGADO (Hígado y Espirulina) | B0H16T5H18 | Inactive — Review blocked reason (compliance MAVERiCK MX) |
| OPTIPETFLAVORPULMON (Pulmón y Melena de León) | — | Sin crear — bloqueado por UPC collision permanente |
| OPTIPETFLAVORPOLLO (Pollo y Cúrcuma) | — | Sin crear — bloqueado por UPC collision permanente |

Compliance issue activo:
- Policy: `GRLKLZ6WQ9R259LC` Pet Consumables: Food and Product Safety Issues
- Fecha violación: 2026-05-10
- Estado: Listing removed, esperando upload de docs vía panel "Add Compliance" en Safety & Compliance tab del listing

---

## ⏰ Pendientes activos

> Esta sección se actualiza al cierre de cada sesión.

### Bloqueantes absolutos (sin esto no avanza nada)

1. **UPCs nuevos del fabricante** para Pulmón y Pollo (cliente confirmó NO eliminar Cat Treats Inactive — única vía es UPCs nuevos PETSA)
2. **Compliance docs Hígado** — esperando del cliente:
   - COA del producto
   - Etiqueta física alta resolución (frente + dorso de los 3 sabores)
   - Ficha técnica con análisis garantizado
   - Status regulatorio (¿desregulado clase III o código SAGARPA 8 dígitos?)
   - Certificación Non-GMO formal (sin esto, sacar claim del título)

### Operativos no bloqueantes pero importantes

3. **Peso bruto paquete**: confirmar 297g (master sheet) vs 360g (intento v4)
4. **Imágenes en URLs públicas**: re-hostear desde Drive a host directo (.jpg/.png)
5. **OPTICAT roadmap Amazon**: confirmar si los 3 SKUs nuevos para gatos entran al pipeline
6. **FBM zombi OPTIPETSKINCOATFBA**: Close listing real (reapareció 2026-05-06)

### Variation Family Adult (sin cambios esta sesión)

7. Definir fecha launch oficial
8. Definir hero del variation (default en search results)
9. Validar bullets / A+ Content de cada child post-agrupación
10. Decidir Brand Store / A+ específico del parent

### PPC (cuando arranque)

11. Definir naming convention propio (NO aplica estándar Capybaras)
12. Decidir arquitectura: campañas por child vs apuntando al parent

### Diferidos

13. M26 refactor (10 bloques VB-001 a VB-011) — post 3 casos validados Variation Builder
14. Si Amazon notifica template nuevo flat file → bajar `.xlsm` actual y regenerar knowledge entry

---

## 📅 Próxima evaluación

> Esta sección lista los milestones esperados con fechas concretas.

- **Inmediato (esperando respuesta de Adam vía WhatsApp)**: framing de presentación para chat INASA + ¿Lenin pregunta directo a Mario los UPCs nuevos, o lo maneja Adam?
- **TBD (cuando responda Adam)**: Lenin escribe directo a Mario y Abraham en chat INASA con los 5 pedidos concretos (UPCs nuevos, peso, imágenes, Non-GMO, OPTICAT)
- **TBD (cuando lleguen UPCs nuevos)**: armar borrador v5 flat file en local (NO subir hasta Hígado Active)
- **TBD (cuando lleguen compliance docs)**: upload paquete completo al panel "Add Compliance" del Hígado
- **TBD (24-72h post-upload)**: Amazon review compliance → si pasa Active, validar si "child SKU not setup correctly" persiste

---

## 🧠 Conocimiento operativo permanente

> Esta sección NO se actualiza por cierre de sesión. Es estable.
> Cambios solo si se redefine algo estructural.

### Relación comercial
- Cliente personal directo de Lenin Acosta — gestión 1:1 sin equipo intermedio.
- No aplica workflow de agencia (briefings, status calls, equipos compartidos).
- Decisiones operativas se toman directo entre Lenin y el cliente.

### Reglas duras del catálogo
- **1 ASIN ≠ 2 children**: si producto tiene FBA + FBM mismo ASIN, elegir UNO. Apagar el otro con `Close listing` antes de cualquier feed.
- **SKUs FBA-only** por política del cliente. FBMs nuevos compartiendo ASIN con un child → apagar antes de tocar variations.
- **Browse node validado**: `11601177001` para suplementos en polvo OPTIPET.
- **Theme `Sabor` con custom values**: válido en MX, sin warnings.
- **Política compliance Amazon MX para suplementos pet**: `GRLKLZ6WQ9R259LC`. URL: https://sellercentral.amazon.com/help/hub/reference/GRLKLZ6WQ9R259LC. Amazon requiere docs específicos del producto (no solo del fabricante) antes de permitir venta.
- **Master Sheet INASA es fuente de verdad** para datos físicos de producto. SKU naming interno ≠ Amazon (master usa OP-FLB-*, Amazon usa OPTIPETFLAVOR*).
- **Línea OPTICAT existe en master sheet** pero NO lanzada en Amazon al 2026-05-12. 3 SKUs: OPTICAT_CHICKEN, OPTICAT_LIVER, OPTICAT_TUNA.

### Histórico de operaciones
- **2026-05-08**: Variation Family Adult creada (3 children FBA bajo parent `B0H12ZXVPF`).

---

## 📜 Historial de actualizaciones

> Una línea por sesión. Más reciente arriba.

- **2026-05-12**: diagnóstico compliance Hígado (policy GRLKLZ6WQ9R259LC), análisis Innasa Master Sheet (ingredientes reales confirmados, pricing oficial $349, línea OPTICAT identificada), comunicación con Adam (escribe directo a chat INASA, esperando framing). Adult variation 100% operativa con 65u FBA. FBM zombi reapareció. Cat Treats Inactive NO se eliminan por decisión del cliente.
- **2026-05-08** (creación inicial): post operación puntual de Variation Family. 3 children FBA agrupados bajo parent `OPTIPET_ADULT_PARENT` (`B0H12ZXVPF`). Theme `Sabor` con valores custom en inglés. Feed batch `50059020581` 4/4 successful. Pre-flight cleanup: FBM zombi `OPTIPETSKINCOATFBA` apagado. Stock FBA 0 disponibles · 72u inbound.

---

## 🔗 Referencias cruzadas

- `[[optipet]]` — brand note principal con catálogo + hitos + pendientes activos
- `[[2026-05-08-variation-builder-flat-file-format]]` — formato flat file + caso de éxito #2 OPTIPET + gotchas
- `[[2026-05-08]]` — daily de la sesión inicial
- `[[CLAUDE]]` — instrucciones generales del vault
