---
tipo: prompt-arranque-cliente
cliente: dermaglos
nivel: cargado
actualizado: 2026-06-19
proxima_actualizacion: cierre próxima sesión Dermaglos
heroes_oficiales:
  - B0CYLMJJJC
  - B0CYLM4L23
  - B0F4KXZVNM
status_atom11: v2026.2 EN REVISIÓN — esperando v2026.3
---

# Arranque Sesión — Dermaglos

> Prompt customizado para arrancar cualquier sesión del cliente Dermaglos.
> Pegar el bloque XML del primer code block en chat nuevo de Claude.ai.
> Se actualiza al cierre de cada sesión con el delta — el bloque que se pega
> es estable; el delta vive en las secciones de "Estado actual" y "Pendientes".

---

## 🚀 Bloque para pegar al chat (estable)

```xml
<arranque_sesion cliente="dermaglos">

Hola Claude. Soy Lenin, Capybaras Agency. Vengo a trabajar sesión Dermaglos.

<contexto_proyecto>
Repo local: C:\proyectos\ppc-manager (rama main, conectado a GitHub Leninead/ppc-manager).
Vault Obsidian: notes/ dentro del repo, sincronizado vía GitHub a este proyecto Claude.
Cliente: Dermaglos — Amazon USA, skincare hispano (vitamina A, allantoin como diferenciadores).
Equipo Atom11: Neha + Jais (rules automation).
</contexto_proyecto>

<lectura_obligatoria_en_orden>
1. notes/CLAUDE.md (estado general agencia)
2. notes/state/STATE-agencia.md (qué cambió + bloqueos abiertos)
3. notes/brands/dermaglos/DERMAGLOS.md (sesiones recientes, hallazgos, mensajes pendientes)
4. notes/brands/dermaglos/skus_dermaglos.md (mapeo ASIN/SKU vigente)
5. notes/brands/dermaglos/atom11-rules.md (rules en producción + findings reportados)
6. notes/daily/ (último daily Dermaglos disponible)
7. notes/sops/amazon-bulk-upload-guide.md (gotchas de bulk format)
</lectura_obligatoria_en_orden>

<conocimiento_operativo_dermaglos>

## Heroes oficiales (jerarquía revisada 28/04)
- B0CYLMJJJC (PVENUS0782) — Dermatological Cream $9.99 — HERO real, recibe 38% spend
- B0CYLM4L23 (PVENUS0787) — Body Lotion $18.89 — HERO real, ROAS 2.39× (más sólido)
- B0F4KXZVNM (KIT 4 - FBA) — Dermatological 2-Pack $16.99 — HERO real, ROAS 3.12× (subexplotado)
- B0F548KTXD (KIT 3 - FBA) — Body Lotion 2-Pack $32.11 — EX-HERO desde 28/04 (ROAS 0.61×)

## ASINs marginales / con flag
- B0F6VZMF2V (KIT 13 - FBA) — Facial Skincare Set — ESTRELLA OCULTA ROAS 6.20× CVR 33% pero OOS desde 09/04. Push diferido hasta restock.
- B0CYLDSQ5L (PVENUS0739) — Body Cream — sale activa $9.99, listing-issue documentado
- B0CYK4G2Y8 (PVENUS0758) — Facial Cleanser — CVR 5.8% (listing fix necesario)
- B0CYL1RLNQ, B0CYKDSDJX, B0CY2XC91Z — bajo volumen paid

## Atom11 v2026.2 — status: EN REVISIÓN, esperando v2026.3
4 findings activos reportados a Neha:
1. Rule HARD-STOP no dispara contra Prospecting Vitamin A SD (campaign ID 341852079119387). Sangrado lifetime $558. Diagnóstico CORREGIDO 28/04: el nombre real NO tiene coma (eso era de Atom11 mostrando 2 campañas con la misma rule). Bug real: tier mal asignado / double-optimize / asignación múltiple.
2. Double-optimize sistémico en TODAS las DEC tiers — INC son rangos disjuntos, DEC son thresholds acumulativos (>X). Aplica a 6 objetivos × SP/SB/SD = ~24 rules.
3. 5 SP ASIN "Related Dermaglos Products" con triple-classification (CONQUEST + DEFENSIVE + RANKING) — apuntan a ASINs propios → DEFENSIVE puro.
4. 13 Body Cream B0CYLDSQ5L SP sin HARD-STOP/NEGATE (cleanup ya las eliminó, pero al reactivar post listing fix aplicar set RANKING completo).

Hasta v2026.3 cerrada: NO escalar bids agresivos en campañas que toquen las DEC rules. Cuando Neha confirme fix → green light continuar Bloque B+C del plan maestro.

## Naming convention vigente (Atom11-friendly)
Híbrido: `DG | OBJETIVO | TIPO - Producto - ASIN - Cluster`
Ejemplos:
- `DG | CONQUEST | SP | EXACT - Cream - B0CYLMJJJC - Hipoglos`
- `DG | RANKING | SP | EXACT - Lotion - B0CYLM4L23 - Vitamin A Lotion`
- `DG | DEFENSIVE | SP | EXACT - All Heroes - Brand Hub Defensive`
- `DG | DISCOVERY | SP | PHRASE - Cream+Lotion - Spanish Hidratante`

Atom11 lee el OBJETIVO del prefijo y clasifica automáticamente. Para campañas viejas con naming `Producto - ASIN - Tipo - Cluster`, la clasificación es manual.

## Bid strategy estándar Capybaras para Dermaglos
| Tipo | Bidding Strategy bulk value | Placement TOS |
|---|---|---|
| Exact Brand/Conquest agresivo | Fixed bid | +50% |
| Exact Harvest/Profit | Dynamic bids - down only | +25% |
| Phrase Discovery | Dynamic bids - down only | +10% |
| Auto | Fixed bid | sin modifier |

## Clusters validados (priorización)
- ⭐ Vitamin A — músculo principal: 18 órdenes ACoS 51% IS 8.9% (techo). 8 KWs BS 100% en SQP.
- ⭐ Allantoin — diferenciador único Dermaglos. 7 ord ACoS 52%. IS 8-16% con CS desproporcionalmente alto.
- ⭐ Tattoo — 1 conv ACoS 12%, BS 100% en SQP. Volumen 500K imp/mes mkt. Listing copy pendiente.
- 💎 Hipoglos cream (cross-brand) — Mercado paga $19, Dermaglos $9.99 (47% más barato). SQV 1,074, BS 5.88%. Conquest creado 28/04.
- 🔥 dermaglos cleansing gel — la mina (ACoS 3% en STR, cross-SKU 100%). EXACT dedicado bid $13.50 creado 28/04.
- 💀 Retinol cluster — NO PERSEGUIR. $121 spend $0 sales en 30d. 7 negativos aplicados 28/04.

## Productos NO listados con demanda brand confirmada
Conversación pendiente con cliente (revenue futuro):
Vitamina C, Niacinamida serum, BB Cream, Protector Solar.
Hay tráfico orgánico vía búsqueda marca que convierte a OTROS productos.
</conocimiento_operativo_dermaglos>

<bugs_y_gotchas_bulk_format>
Estos son los 8 learnings críticos de la sesión 28/04. Aplicarlos SIEMPRE antes de generar bulks.

1. **Negative Keyword vs Campaign Negative Keyword** son entities distintas
   - `Negative Keyword` → nivel Ad Group (requiere Ad Group ID)
   - `Campaign Negative Keyword` → nivel Campaña (no requiere Ad Group ID)
   - Solo soportan `negativeExact` y `negativePhrase` (NO `negativeBroad`)

2. **Campaign IDs y Ad Group IDs según operación**
   - Crear campaña + ad group + KWs en mismo bulk → usar Campaign Name (string), Amazon hace match interno
   - Crear KWs/negativos en campañas YA existentes → usar ID numérico (descargar BulkSheetExport)
   - Update bids / state → usar ID numérico
   - Workflow: ANTES de modificar campañas existentes → Bulk Operations → Download campaigns → cruzar

3. **Start Date como TEXTO no float**
   - ✅ `20260428` (string) — `cell.number_format = "@"` + `value = str(value).split(".")[0]`
   - ❌ `20260428.0` (float, Amazon rechaza silencioso)

4. **Google Sheets corrompe IDs numéricos largos**
   - NO abrir el bulk en Google Sheets antes de subir
   - IDs como `497286372972562` se vuelven `4.97E+14`
   - Subir el .xlsx original directo

5. **Caracteres especiales en keywords**
   - `%` rechazado (caso `allantoin 0.5% cream`)
   - Punto + decimal puede causar problemas
   - Workaround: variantes (`allantoin .5 cream`) o agregar manual via UI

6. **Campaign Analyzer puede mostrar campañas YA ELIMINADAS**
   - Snapshot puede estar desactualizado
   - Antes de pausar/decidir budget → cruzar con BulkSheetExport actualizado
   - 28/04: analyzer mostró 114 camps, BulkSheetExport tenía 84 reales (30 zombies eliminadas)

7. **SD bulk schema diferente de SP** — 47 cols vs 31 cols. Incluye Tactic, Bid Optimization, Cost Type, Targeting Expression.

8. **Hoja única "Sponsored Products Campaigns"** — si tiene hojas extra, Amazon rechaza todo el archivo.
</bugs_y_gotchas_bulk_format>

<flujo_de_arranque>
Una vez leído todo el contexto:

1. Confirmá brevemente que entendiste:
   - Última sesión Dermaglos (fecha + qué se hizo)
   - Estado de Atom11 v2026.2 (¿v2026.3 cerrada o sigue pendiente?)
   - Pendientes activos del cliente (los que están en DERMAGLOS.md)
   - Bloqueos vigentes (OOS B0F6V, listing fixes, conversación cliente)

2. Recordame correr antes de cualquier trabajo:
   - `cd C:\proyectos\ppc-manager && git status && git pull`
   - `git add . && git commit -m "checkpoint: antes de [tarea de hoy]"`

3. Preguntame qué queremos atacar hoy. NO arranques trabajo nuevo sin esa confirmación.

4. Si la tarea de hoy involucra bulks → revisar la sección bugs_y_gotchas_bulk_format ANTES de generar archivos.

5. Si la tarea es análisis grande (STR/SQP/Campaign Wise cruzados) → primero revisá si hay un plan maestro vigente (00_PLAN_ACCION_MAESTRO_dermaglos_*.xlsx) para no duplicar trabajo.
</flujo_de_arranque>

<rituales_obligatorios>
Al final de cada sesión, recordame ejecutar (en este orden estricto):

1. Los 3 prompts del sop-writer:
   - Daily de hoy (notes/daily/YYYY-MM-DD.md)
   - Brand notes Dermaglos update (notes/brands/dermaglos/*.md)
   - STATE-agencia quirúrgico (notes/state/STATE-agencia.md)

2. Update de este mismo archivo: notes/prompts/sesion/clientes/arranque-dermaglos.md
   - Sección "Estado actual"
   - Sección "Pendientes activos"
   - Sección "Próxima evaluación"
   - Sección "Historial de actualizaciones"

3. Git commit + push:
   - `git add .`
   - `git commit -m "feat/fix/improve/docs: [descripción concreta]"`
   - `git push`

4. Refresh manual en proyecto Claude:
   - Ir al proyecto en claude.ai
   - "Add content from GitHub" → seleccionar archivos modificados
   - Sincronizar

5. Generar prompt de arranque para próxima sesión (si quedó algo a medias).

Si saltás cualquier paso de los 4 primeros, el próximo chat lee data stale y todo se rompe.
</rituales_obligatorios>

</arranque_sesion>
```

---

## 📊 Estado actual del cliente (snapshot 2026-06-19)

> Esta sección se actualiza al cierre de cada sesión.

### Sesión 2026-06-19 — 360 pre-Prime + ejecución
- **360 completo** sobre 5 fuentes (STR 19/05–17/06 · SQP May+W23+W24 · Campaign report 18/06 · MAI live · BSE all-states).
- **5 bulks ejecutados (todos Success)**: cirugía target/placement + 22 negativos + brand floor + escalado selectivo + Hipoglós reactivada.
- **Cuenta lista para Prime Day 23–30/06** (20% off sobre list, reemplaza sales previos).
- **ACoS baseline 58.9%** (STR) / 56.2% (Campaign report) → **objetivo 45%**.
- **Limitación = BID, no budget**: gasto efectivo $42/d = 5% del techo aprobado $803/d. Gasto efectivo objetivo Prime **~$110/d**.

### KPIs actuales vs target
| Métrica | Hoy (19/06) | Target Prime |
|---|---|---|
| ACoS cuenta | 58.9% | 45% |
| Gasto efectivo/día | $42 | ~$110 |
| Techo budget aprobado | $803/d | — |

---

## ⏰ Pendientes activos (al 2026-06-19)

> Esta sección se actualiza al cierre de cada sesión.

- **B0F6VZMF2V (Facial Set) OOS** → push diferido hasta restock (estrella oculta ROAS 6.20×).
- **Unfulfillable recovery**: 30u hero Cream B0CYLMJJJC (+ 11 Night + 10 2pk Cream) — recuperar inventario.
- **Listing fix micellar/cleanser** (B0CYK4G2Y8, CVR 5.8%) — fix de listing, no PPC. Para cliente.
- **Demanda de marca no listada**: protector solar, niacinamida serum (sumado a Vit C, BB Cream ya conocidos) — conversación revenue con Agustín/cliente.
- **Monitoreo Prime** (23–30/06): seguimiento diario de Hipoglós reactivada + escalado durante el evento.

---

## 📅 Próxima evaluación

> Esta sección lista los milestones esperados con fechas concretas.

- **2026-07-01**: STR fresco post-Prime → medir delta ACoS, performance Hipoglós + escalado durante el evento.
- **TBD (cuando llegue restock)**: B0F6VZMF2V Facial Set push activado. ROAS esperado >5×.
- **TBD (cuando Neha cierre v2026.3)**: validar fixes + bloque B+C del plan.
- **TBD (cuando llegue creative cliente)**: 8 SB zombies activadas con SBV.

---

## 🧠 Conocimiento operativo permanente

> Esta sección NO se actualiza por cierre de sesión. Es estable.
> Cambios solo si se redefine algo estructural.

### Contactos del cliente / equipo

| Contacto | Rol | Notas |
|---|---|---|
| Adam | Sales Director (interno) | Maneja compliance + escalations cliente |
| Agustín | Account Manager (interno) | Maneja conversaciones cliente día a día |
| Aaron | Compliance contact (cliente?) | Mencionado en LTD compliance — verificar relación con Dermaglos |
| Neha | Atom11 lead (Atom11 team) | Owner de las rules. Slack para comunicaciones técnicas. |
| Jais | Atom11 dev (Atom11 team) | Backup técnico |

### Decisiones de bid strategy históricas

- **Defensive brand exacts**: bid sostenido $0.50-0.80 (capturar tráfico orgánico a costo mínimo, no maximizar conversión)
- **Conquest exacts**: bid agresivo justificado solo si SQP muestra Brand Price advantage (caso Hipoglos: -47%)
- **Cleansing Gel exact**: bid $13.50 sostenido (cross-SKU 100%, ACoS 3% lo justifica)
- **Vitamin A Power**: bids escalados $1.50-2.50 según validación BS en SQP
- **SD VCPM Views Retargeting**: bid bajo $0.40-0.50 (audiencia chica, premium injustificado >$1)

### Campañas que sangran históricamente (cuidado)

- **`Body Lotion 2Pack - B0F548KTXD - SD - VCPM - Prospecting Vitamin A`** (ID 341852079119387) — pausada 28/04. Atom11 rule HARD-STOP no disparó. Sangrado lifetime $558.
- **Cluster Retinol completo** — Dermaglos no compite ahí. 7 negativos aplicados 28/04.
- **Cluster Oily Skin** — no es nicho Dermaglos. Validado en SQP.

### Listings con flag

- **B0CYK4G2Y8 (Facial Cleanser)** — CVR 5.8% es problema de listing, no de bids. Pre-fix Rufus es gate para escalar.
- **B0CYLDSQ5L (Body Cream)** — sale activa $9.99 puede canibalizar paid (orgánico en página 1 con sale, paid bid bajo no entra en subasta).
- **B0F548KTXD (Body Lotion 2Pack)** — ROAS 0.61× lifetime. Sale de heroes 28/04. Re-evaluar en 30 días.
- **Draft inactivo Micellar Water 6-in-1** — `Missing Information` desde 21/03/2024. Limpiar al cleanup (no urgente).

### Reglas Capybaras específicas para Dermaglos

- Ad group clusters: ~5 keywords por grupo (estándar agencia)
- Bulk Excel preferido sobre UI cuando volumen > 5 campañas
- Portfolio ID dejar VACÍO en bulks (asignar manual post-upload)
- Naming: hibrido Atom11-friendly (`DG | OBJETIVO | TIPO - Producto - ASIN - Cluster`)
- Match types: priorizar EXACT > PHRASE > BROAD (BROAD solo en discovery con AUTO)

---

## 📜 Historial de actualizaciones

> Una línea por sesión. Más reciente arriba.

- **2026-06-19**: 360 completo + 5 bulks ejecutados (cirugía target/placement + negativos + brand floor + escalado + Hipoglós reactivada). Limitación por bid no budget. Hipoglós era zombie pausada.
- **2026-04-28** (creación inicial): post sesión análisis cruzado completo Dermaglos. Plan maestro 5 archivos + 3 bulks ejecutados (93/94 + 46/46 + 7/10) + 10 P0 pausadas + 4 findings Atom11 reportados a Neha. 7 campañas live. Status B0F548KTXD: hero → monitor. Estrella oculta: B0F6VZMF2V (OOS).

---

## 🔗 Referencias cruzadas

- `[[DERMAGLOS]]` — brand note principal con sesiones detalladas + mensaje pendiente Neha
- `[[skus_dermaglos]]` — mapeo ASIN/SKU/precio/stock (snapshot Seller Central)
- `[[atom11-rules]]` — rules en producción + 4 findings activos
- `[[2026-04-28]]` — daily completo de la sesión inicial
- `[[amazon-bulk-upload-guide]]` — gotchas de bulk format (sección "Learnings 2026-04-28")
- `[[STATE-agencia]]` — estado global agencia + bloqueos
- `[[CLAUDE]]` — instrucciones generales repo + vault
