---
tipo: prompt-sesion
actualizado: 2026-05-22
cliente: mb
nota: owner oficial Cuki desde 11/05 — esta sesión actualiza por ad hoc Attribution 22/05
---

<arranque_sesion cliente="mb">

Hola Claude. Soy Lenin, Capybaras Agency.
Vengo a trabajar sesión M&B (Mott & Bow).

<contexto_proyecto>
Repo local: C:\proyectos\ppc-manager (rama main, GitHub Leninead/ppc-manager).
Vault Obsidian: notes/ dentro del repo.
Cliente: Mott & Bow — Amazon US, ropa premium (t-shirts, jeans, 3-packs).
Owner oficial: Cuki desde 11/05/2026.
AM principal: Agustín Favano.
</contexto_proyecto>

<lectura_obligatoria_en_orden>
notes/CLAUDE.md
notes/state/STATE-agencia.md
notes/brands/mb/MB.md (incluye sesión ad hoc 22/05 Attribution)
notes/daily/2026-05-22.md (sección M&B del cierre)
notes/sops/amazon-attribution-setup.md (SOP nuevo creado 22/05)
notes/TRASPASO_MottBow.md (handoff oficial a Cuki)
</lectura_obligatoria_en_orden>

<conocimiento_operativo_mb>

**Estado al 22/05:**

**Amazon Attribution V0 — Meta Facebook (entregado 22/05):**
- Campaign operativa: MB-US-META-2026Q2-v2 (External ID: MBMETA2026Q2v2)
- Campaign zombie a ignorar: MB-US-META-2026Q2 (ID 579799613303383079)
- 6 tags entregados a Agustín por Slack:
  - Familia A (CR Women Black $40): B0F6LDG3NK, B0FQPPLFRT, B0F6LF4SH4
  - Familia B (3-Pack Driggs BGN $92): B0GHZY9TSB, B0GHZTD49W, B0GHZBP1TN
- ⚠️ Familia B con historial 1★ — Agustín aprobó con conocimiento del riesgo

**Pendientes Attribution (esperando cliente):**
- Instagram channel (6 tags más si cliente corre IG)
- Email channel (6 tags más si quiere trackear newsletter)
- Brand Referral Bonus enrollment status
- V1 granular cuando cliente pase listado Meta real
- Validación 24-48hs post-deployment (entran clicks)

**Pendientes operativos regulares (de TRASPASO_MottBow):**
- Fase 2 gate pendiente (Cuki maneja)
- Audit SCAVENGER (Cuki maneja)
- Otros items según handoff

</conocimiento_operativo_mb>

<gotchas_attribution_22_05>
8 gotchas críticos documentados en [[amazon-attribution-setup]]:
1. Multi-cuenta riesgo (validar advertiser antes de cualquier acción)
2. Template Attribution ≠ Template SP
3. Template vacío rebota (Amazon usa filas ejemplo)
4. Publisher difference Bulk vs Manual
5. ⭐ CRÍTICO: Bulk Beta NO completa jerarquía Ads/Tags
6. Campaigns Attribution permanentes (no se eliminan)
7. Variation parents rechazados (solo child ASINs)
8. Modelo cambia 2026 (last-touch → shopping-signal weighted)
</gotchas_attribution_22_05>

<flujo_de_arranque>
Confirmá entendimiento de:
- Estado Attribution V0 entregado 22/05
- Pendientes esperando cliente (Instagram, Email, BRB, V1)
- Owner oficial sigue siendo Cuki

Recordame correr al inicio:
git status
git pull
git add . && git commit -m "checkpoint: pre-trabajo M&B [fecha]"

Preguntame qué atacamos hoy. Opciones probables:
(a) Validación 24-48hs Attribution V0 (entran clicks?)
(b) Setup Instagram si cliente confirmó
(c) Setup Email si cliente confirmó
(d) Brand Referral Bonus enrollment
(e) V1 granular Attribution (1 tag por ad set específico)
(f) Items regulares M&B según TRASPASO (consultar Cuki primero)
(g) Otro tema específico

Si involucra Attribution → revisar gotchas en [[amazon-attribution-setup]].
</flujo_de_arranque>

<rituales_obligatorios>
Al cierre: usar notes/prompts/sesion/cierre-meta.md
NUEVO POST-22/05:
- Validar ASINs no pertenecen a otra cuenta antes de mensajes
- Cruzar con Seller Central para flags abiertas
</rituales_obligatorios>

</arranque_sesion>
