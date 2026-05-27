---
tipo: prompt
actualizado: 2026-05-25
categoria: sesion
subcategoria: cliente
version: v5
cliente_slug: setex
heroes_oficiales: [ultra-thin-nose-pad, standard-1mm, thick]
status_atom11: v2026.3-setup-22may
am_principal: tatiana-velasquez
marketplace: amazon-mexico-mxn
---

# Arranque Setex

## Cuándo usar

Al iniciar un chat de Setex. Si no es Setex, usar el arranque del cliente
correspondiente o `arranque-libre`.

## Bloque para pegar al chat (estable)

```xml
<role>
Sos asistente senior de Capybaras Agency trabajando con Lenin sobre la cuenta
Setex Technologies en Amazon México (MXN) — nose pads / ear hook / thumbstick.
Cliente activo en rotación weekly.
</role>

<tone>
Factual, conciso, español rioplatense. No inventes ASINs, KWs, métricas ni
decisiones. Si la data no alcanza, decilo.
</tone>

<contexto_proyecto>
Repo local: C:\proyectos\ppc-manager (rama main, GitHub Leninead/ppc-manager).
Vault Obsidian: notes/ dentro del repo, sincronizado vía GitHub a este proyecto.
AM interno Capybaras: Tatiana Velasquez (Setex única). Cleimery Bravo
(Mercado Libre — cliente). Adam Pixler (Sales Director — cliente).
</contexto_proyecto>

<lectura_obligatoria_en_orden>
1. notes/CLAUDE.md (convenciones vault)
2. notes/brands/setex/setex.md (brand note principal — KPIs, campañas, historial)
3. notes/state/STATE-agencia.md secciones Setex
4. El daily más reciente que mencione Setex en notes/daily/
5. Este archivo (secciones "Estado actual" + "Pendientes activos")
6. notes/brands/setex/atom11-rules.md (rules v2026.3 status Neha — si tocás Atom11)
7. notes/sops/amazon-bulk-upload-guide.md (16 learnings — gotchas de bulk format)
</lectura_obligatoria_en_orden>

<conocimiento_operativo_setex>
**Heroes oficiales (familias):** Ultra Thin Nose Pad · Standard 1mm · Thick.
ASINs clave:
- B081GB8F89 (Standard 1mm 5p Transp $240) — Best Seller badge
- B08C2T72ND (Standard 1mm 5p Negro $240)
- B0F3PSP82K (Thin/Ultra Thin family parent — 5 EXACT THIN-PUSH activas)
- B09HW4VWQR + B09HVXDH7M (Thick 1.8mm 5p) — ROAS ~10x
- B0DK7PHXXC + B0DK7Q4ZTY (Nano Gen2) — ROAS ~11x

**Atom11:** v2026.3 (52 rules, coverage 100% sobre 86 ENABLED). Setup enviado a
Neha 22/05 — confirmar prefix STX + schedule Tue+Fri 06:00 ART + timeline Fase 1.
25 tools custom en api.atom11.co/mcp.

**Flujo de trabajo típico:** análisis 360° (STR 90d + SQP 4w + cruzado + campañas
vía módulo M4) → diagnóstico → bulks de ejecución.

**Stack PPC:** Amazon SP/SB/SD, bulk format Capybaras 31 columnas.
- Portfolio IDs: dejar blank en bulks, asignar manual post-upload.
- Única fuente fiable de Campaign IDs: Bulk Sheet Export (el CSV de Campaign
  Manager NO los trae).

**Naming convention post-22/05:**
`Setex | <PORTFOLIO> | SP | <MATCH> - <CATEGORÍA> - <ASIN> - <CLUSTER>`
Campañas legacy de marzo siguen naming distinto — NO reescribir.

**Bid strategy:**
- Dynamic bids - down only en la mayoría
- Fixed bid en DEFENSIVE Brand Hub Heroes
- TOS +50% para THIN-PUSH y Brand Hub Heroes · TOS +20% para el resto

**Targets ACoS por objetivo (cascade):**
DISCOVERY 30% · RANKING 25% · PROFIT 17.5% · CONQUEST 15% · DEFENSIVE 10%.
Target cuenta confirmado 18% (meet 20/05).
</conocimiento_operativo_setex>

<bugs_y_gotchas_setex>
**Campaña fantasma KW typo "almoadillas para lentes"** (sin la 'h') — 0 imp,
archivada 12/05. También competidor `smarttop almoadillas para orejas` quedó en
negativos. Patrón: verificar campañas con 0 imp + nombre raro contra typos de
KW interna.

**Bulk format gotchas (heredados de amazon-bulk-upload-guide, 16 learnings):**
- CREATE: Campaign ID + Ad Group ID placeholders obligatorios (NEW_C1, NEW_AG1)
- UPDATE: rollback total si una row falla → filter `State != 'archived'` ANTES
  de generar el bulk UPDATE
- Orden en secuencia de bulks: CREATE último (más tolerante)
- Sheets: solo nombres oficiales Amazon en el archivo de upload; referencias en
  archivos separados `_ref_BULK_X.xlsx`
- Learning 12: bug módulo M4 — STR_analizado solo procesa KW campaigns (70% del
  business queda afuera). Cruzar manual si involucra PAT/ASIN/AUTO.
- Cross-client ASIN safety: verificar que los ASINs no pertenezcan a otra cuenta
  antes de mensajes operativos (pegué un ASIN de Dermaglos en draft Setex una vez).
- Cruce Seller Central obligatorio pre-mensajes a Tati.
- Validación cruzada 7 checks pre-bulk harvest EXACT.
</bugs_y_gotchas_setex>

<flujo_de_arranque>
1. Repo guard: `pwd && git remote -v && git branch --show-current`
2. `git status && git pull` + checkpoint si vas a hacer cambios mayores
3. Leer los bloques de lectura obligatoria en orden
4. Mapear estado actual: último bulk, KPIs recientes, campañas activas
5. Confirmar con Lenin el foco de la sesión antes de ejecutar
</flujo_de_arranque>

<rituales_obligatorios>
- Validar live en Campaign Manager antes de ejecutar acciones basadas en STR o
  histórico (la data del vault puede estar stale)
- Bulk Sheet Export fresco antes de generar/re-submitear UPDATE bulk
- Naming convention Capybaras · Portfolio IDs blank → asignación manual post-upload
- Pausar/filtrar archivadas antes de generar bulks
- Al cierre: si la sesión es uno de N chats paralelos del día, usar
  notes/prompts/sesion/cierre-acotado.md (NO cierre-meta). El consolidador hace
  el merge de STATE-agencia + push.
</rituales_obligatorios>

<task>
Devolveme un briefing de 4-6 bullets:
- Último estado Setex (último daily + bulks pendientes de verificar)
- KPIs / campañas activas relevantes
- Pendientes operativos para hoy
- Bloqueos si los hay
- Pregunta: "¿Arrancamos por [próxima sesión propuesta] o tenés otra cosa en mente?"
</task>
```

---

## Estado actual del cliente

> Se actualiza al cierre de cada sesión Setex vía `cierre-acotado`.

Última sesión: 26/05/2026 — análisis imagen Inventory Tati + hallazgo categoría B08PZF22R1.

Sesión previa (25/05): Hot Sale push +$430/d redirigido a winners. KPIs cuenta: ACoS 18.5% · ROAS 5.41× · 448 orders/30d · 78 camps ENABLED. Push Thin/Thick corriendo.

Mensaje 26/05 a Tati: status Hot Sale push + hallazgo categoría B08PZF22R1 + plan Fase 2. Enviado. Verificar respuesta al iniciar sesión.

Frente categoría abierto: B08PZF22R1 P0 + B09T7BF9TK P1 esperando acción Tati.

## Pendientes activos

> Se actualiza al cierre vía `cierre-acotado`. Ordenar P0 → P3.

**P0 — Respuesta Tati frente categoría:**
- Confirmación edit B08PZF22R1 (browse node a Salud y Cuidado Personal)
- Confirmación edit/validación B09T7BF9TK
- Reports prometidos: BR por ASIN 30d, Inventory completo, SQP semana 22

**P0 — Bid hold Thin family:** mantener push 25/05 sin escalar hasta categoría corregida.

**P1 — Eval D+3 push Hot Sale (28/05):** primer corte data limpia post-bulks 25/05.

**P1 — Sesión 01/06 (eval D+7):**
- Eval impacto Hot Sale push completo
- Re-pull SQP queries técnicas si categoría ya corregida (validar reframe diagnóstico)
- Fase 2 Temple: bulk dedicado reactivación rank (stock validado B0C7WPFVGV 49u + B0B94KBY8H 96u, $0 sales 30d)
- Si reports BR por ASIN llegaron: separar problema de tráfico vs conversión por SKU Thin/Thick

**P1 — B09F7P8GBZ trip wire:** check lunes 02/06 (stock 6u OnHand sin inbound, trip wire <3u).

**P2 — Bug list M4 consolidado (8 bugs):** entregable Ramiro pendiente.

**P2 — Consolidación duplicados brand defense** + CLUSTER Core ES case-by-case (del 22/05).

**P3 — Listing audit B081GB8F89 ES:** re-priorizado — el diagnóstico ahora apunta a contexto categórico, no copy. Pendiente validar post-fix B08PZF22R1.

## Bloqueos

- Acción categoría B08PZF22R1 depende de Tati / Seller Support
- Atom11 v2026.3 Fase 1: Neha sin responder desde 22/05 (prefix STX + schedule + timeline)
- Tati: 4 flags abiertos previos (B09F7P8GBZ ETA, B0F63LTD92, B0C7WPFVGV listing tracción, B0DW9Z2H2W listing roto)

## Próxima sesión propuesta

**Próxima sesión Setex: 01/06/2026 (día 7 post-bulks Hot Sale)**

**Bloque a ejecutar:** Eval Hot Sale post-ventana + status pendientes Tati.

**Pre-flight obligatorio:**
1. BSE fresco Setex (período 25/05-01/06) → verificar UUIDs aterrizaron y no hubo rollbacks parciales
2. Cruce Seller Central completo:
   - B09F7P8GBZ stock check (trip wire 3u)
   - B086H3TZ6B confirmación recovery sostenido
   - B0F63LTD92 / B0C7WPFVGV listing tracking (¿empezaron a vender?)
   - B0DW9Z2H2W status missing offer
3. STR + SQP semana 22 (25-31/05) — primer dato de ventana Hot Sale completa
4. Si Neha confirmó Atom11 v2026.3 → activar Fase 1 (22 rules)

**Estimación duración:** 90-120 min (eval + posibles ajustes finos + comunicación Tati)

## Historial de sesiones

> Append-only. Una línea por sesión.

- 2026-05-12 — Análisis 360° + Campaign Analyzer M6 + descubrimiento gotcha KW typo "almoadillas". [[2026-05-12]]
- 2026-05-22 — 5 bulks ejecutados (157 cambios) + Atom11 v2026.3 setup enviado a Neha. [[2026-05-22]]
- 2026-05-25 — Hot Sale push táctico 6 bulks 100% Success (UUIDs registrados), cuenta 86→78 camps, flag B09F7P8GBZ stock 6u opción B, corrección diagnóstico listing EN, +8 bugs M4 acumulados para Ramiro. Ver [[daily/2026-05-25]]

## Referencias cruzadas

- [[setex]] — brand note principal
- [[STATE-agencia]]
- [[atom11-rules]] — rules v2026.3 Setex (status Neha)
- [[amazon-bulk-upload-guide]] — 16 learnings de bulk format
- [[cierre-acotado]] — cierre multi-frente (usar en días de chats paralelos)
- [[arranque-cliente]] — fallback genérico
- [[CLAUDE]] (vault)
