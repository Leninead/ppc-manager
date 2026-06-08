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

Última sesión 2026-06-08: análisis 360° completo + 8 bulks ejecutados (156 cambios,
todos Success). Cuenta dentro de target: ACoS 17.6% / TACoS 10.0% / Organic share 43%.
1mm sigue siendo motor (64% ventas, 52% orgánico). B081GB8F89 = 39.5% catálogo BR
con BB 99.6% y runway ~34d. Thumbstick XG9J821 pausada (era ACoS 122%), XG9J841 con
bid down −50%. Temple Tips reactivadas (20 camps Capybaras, stock 141u combinado).
Bid up +30% en 8 heroes confirmados. 111 negativos quirúrgicos creados (anti-
canibalización + waste). Cruce M4: AGREGAR EXACT = 0 aprobados (4ta sesión
consecutiva = cuenta cosechada estructural).

## Pendientes activos

> Se actualiza al cierre vía `cierre-acotado`. Ordenar P0 → P3.

**P0 — Respuesta Tati a 5 flags abiertos:**
- 🔴 B0DW9Z2H2W (Nano 15p Negros) listing roto — Missing offer + price $0
- 🔴 B09F7P8GBZ (1mm 5p Azul) trip wire 4u — PA pausado preventivo, espera ETA
- 🟡 B08C2T72ND (1mm 5p Negro) runway 14d — #2 catálogo 100% orgánico
- 🚨 B0BT8HTGKM (Thumbstick funda PS5) precio anómalo $672 vs hermanos $262
- 🟡 B0BQ8GJFQH (Thick 15p Transp) BB 96.1% persistente

**P1 — Decisión Ear Hook B0F63LTD92 (action item meet 03/06):**
Plan completo en sesión dedicada D+7. Decidir: invertir en variantes Ear Hook ES
(listing/A+ adaptado al intent "soporte para lentes orejas") o bajar exposición
controlada. Diagnóstico cerrado: 87% paid-driven + cluster funnel break SQP.

**P1 — Audit listing B081GB8F89 (cluster funnel break sistémico):**
Cluster "sujetador/soporte/patitas/retenedores" = 2,800 SQV combined con PS 0% brand.
Hipótesis confirmada: listing actual NO matchea intent "temple tip/patilla".
Pendiente coordinación con Edu para audit de copy + bullets + A+.

**P2 — Atom11 v2026.3 Fase 1:**
Neha sin responder desde 22/05 (17 días). Pendiente: prefix STX + schedule Tue+Fri
06:00 ART + timeline. Re-pinguear con resumen ejecutivo de optimización 360° hoy.

**P2 — Categoría B08PZF22R1 + B09T7BF9TK (gotcha 26/05):**
ASINs con categoría mal seteada. Depende de Tati / Seller Support.

**P3 — Limpieza catálogo Thumbstick (508u parado, 7 ASINs fantasma):**
Problema de catálogo, no de PPC. Coordinar con Tati ajustes precio o cierre SKUs.

## Bloqueos

- Decisión audit listing B081GB8F89 depende de Tati + Edu (cluster funnel break 2,800 SQV)
- Decisión Ear Hook B0F63LTD92 depende de Tati (87% paid-driven, riesgo estructural)
- Atom11 v2026.3 Fase 1 — Neha sin responder desde 22/05 (17 días)
- B08PZF22R1 + B09T7BF9TK categoría — depende de Tati/Seller Support
- 5 flags Tati abiertos (P0) requieren respuesta para varios next steps

## Próxima sesión propuesta

D+7 (15/06/2026) — evaluación impacto bulks 08/06. Pre-flight obligatorio:
BSE fresco + Manage Inventory live + respuesta Tati a 5 flags.

**Foco esperado:** medir efecto bid up +30% en 8 heroes (esperar mejora ACoS hacia
14-15% en KW escaladas), validar pausa Thumbstick (esperar caída TACoS familia
de 56.8% a <20%), decisión Ear Hook (listing/A+ vs reducir exposición), decisión
audit B081GB8F89 si Tati + Edu disponibles. Estimación 60–90 min.

Si Tati no responde 5 flags antes del D+7, sesión se vuelve solo evaluación
cuantitativa de bulks sin decisiones estratégicas nuevas.

## Historial de sesiones

> Append-only. Una línea por sesión.

- 2026-05-12 — Análisis 360° + Campaign Analyzer M6 + descubrimiento gotcha KW typo "almoadillas". [[2026-05-12]]
- 2026-05-22 — 5 bulks ejecutados (157 cambios) + Atom11 v2026.3 setup enviado a Neha. [[2026-05-22]]
- 2026-05-25 — Hot Sale push táctico 6 bulks 100% Success (UUIDs registrados), cuenta 86→78 camps, flag B09F7P8GBZ stock 6u opción B, corrección diagnóstico listing EN, +8 bugs M4 acumulados para Ramiro. Ver [[daily/2026-05-25]]
- 2026-06-03 — Analisis WoW desde export cliente + reporte HTML bilingue ES/EN,
  sin bulks. 3 findings a validar. [[daily/2026-06-03]]
- 2026-06-08 — Análisis 360° completo + 8 bulks ejecutados (156 cambios) + cruce M4 formal (AGREGAR EXACT = 0 por 4ta sesión, tesis cuenta cosechada estructural confirmada). [[daily/2026-06-08]]

## Referencias cruzadas

- [[setex]] — brand note principal
- [[STATE-agencia]]
- [[atom11-rules]] — rules v2026.3 Setex (status Neha)
- [[amazon-bulk-upload-guide]] — 16 learnings de bulk format
- [[cierre-acotado]] — cierre multi-frente (usar en días de chats paralelos)
- [[arranque-cliente]] — fallback genérico
- [[CLAUDE]] (vault)
