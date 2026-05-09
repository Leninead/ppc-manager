---
tipo: prompt-arranque-cliente
cliente: optipet
nivel: cargado
actualizado: 2026-05-08
proxima_actualizacion: cierre próxima sesión OPTIPET
parent_asin: B0H12ZXVPF
status_catalogo: variation family creada 2026-05-08, esperando inbound 72u FBA
status_ppc: sin historial al 2026-05-08 — agregar cuando se inicien campañas
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

## 📊 Estado actual del cliente (snapshot 2026-05-08)

> Esta sección se actualiza al cierre de cada sesión.

### Hitos ejecutados (2026-05-08)
- **Variation Family creada** vía flat file Variation Builder.
- Feed batch ID Amazon: `50059020581`.
- Resultado: 4/4 SKUs successful · 0 errors · 0 warnings.
- Parent ASIN asignado por Amazon: `B0H12ZXVPF`.
- Variation Family confirmada en Seller Central post-upload.
- Pre-flight cleanup: `OPTIPETSKINCOATFBA` (FBM zombi) apagado vía `Close listing`.

### Catálogo post-sesión
| Rol | ASIN | SKU | Sabor | Stock FBA |
|---|---|---|---|---|
| Parent | `B0H12ZXVPF` | `OPTIPET_ADULT_PARENT` | (referente) | — |
| Child | `B0G6VWT7RB` | `OPTIPETVITALITY` | Vitality | 0 · 24u inbound |
| Child | `B0G6TW7G12` | `OPTIPETSKINCOAT` | Skin and Coat | 0 · 24u inbound |
| Child | `B0G6TPVT2G` | `OPTIPETHEALTHYGUT` | Healthy Gut | 0 · 24u inbound |

### KPIs
PPC: sin historial al 2026-05-08 — agregar cuando se inicien campañas.

Operativos:
- Stock total FBA: 0 disponibles · 72u inbound (24u × 3 children).
- Variation Family: 1 active · 100% children FBA-only.

---

## ⏰ Pendientes activos (al 2026-05-08)

> Esta sección se actualiza al cierre de cada sesión.

### Operativos (esperan trigger externo)
1. **Esperar arrival inbound 72u FBA** (24u × 3 children) — fecha TBD.
2. **Definir fecha oficial de launch** del variation family.
3. **Definir hero del variation** — cuál de los 3 children será el default mostrado en search results de Amazon MX.

### Listing post-agrupación
4. Validar bullets / A+ Content de cada child post-agrupación (que sigan reflejando el child individual).
5. Decidir Brand Store / A+ específico del parent — cómo presentar la familia completa.

### PPC (cuando se inicien campañas)
6. Definir naming convention propia para OPTIPET (no aplica el estándar Capybaras).
7. Decidir arquitectura: campañas separadas por child vs única apuntando al parent.

### Diferidos (no urgentes)
8. Si Amazon notifica template nuevo del flat file → bajar `.xlsm` actual y regenerar el knowledge entry con header fresco.

---

## 📅 Próxima evaluación

> Esta sección lista los milestones esperados con fechas concretas.

- **TBD (cuando llegue inbound 72u FBA)**: confirmar stock activo en los 3 children + definir fecha de launch.
- **TBD (post-launch)**: primera medición de ventas + reviews consolidados a nivel parent.
- **TBD (pre-PPC)**: workshop interno con Lenin para definir naming convention y arquitectura de campañas.

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

### Histórico de operaciones
- **2026-05-08**: Variation Family Adult creada (3 children FBA bajo parent `B0H12ZXVPF`).

---

## 📜 Historial de actualizaciones

> Una línea por sesión. Más reciente arriba.

- **2026-05-08** (creación inicial): post operación puntual de Variation Family. 3 children FBA agrupados bajo parent `OPTIPET_ADULT_PARENT` (`B0H12ZXVPF`). Theme `Sabor` con valores custom en inglés. Feed batch `50059020581` 4/4 successful. Pre-flight cleanup: FBM zombi `OPTIPETSKINCOATFBA` apagado. Stock FBA 0 disponibles · 72u inbound.

---

## 🔗 Referencias cruzadas

- `[[optipet]]` — brand note principal con catálogo + hitos + pendientes activos
- `[[2026-05-08-variation-builder-flat-file-format]]` — formato flat file + caso de éxito #2 OPTIPET + gotchas
- `[[2026-05-08]]` — daily de la sesión inicial
- `[[CLAUDE]]` — instrucciones generales del vault
