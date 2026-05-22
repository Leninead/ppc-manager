---
tipo: prompt-sesion
actualizado: 2026-05-22
cliente: setex
---

<arranque_sesion cliente="setex">

Hola Claude. Soy Lenin, Capybaras Agency. Vengo a trabajar sesión Setex.

<contexto_proyecto>
Repo local: C:\proyectos\ppc-manager (rama main, GitHub Leninead/ppc-manager).
Vault Obsidian: notes/ dentro del repo, sincronizado vía GitHub a este proyecto Claude.
Cliente: Setex Technologies — Amazon México (MXN), nose pads/ear hook/thumbstick.
Equipo interno: Tatiana Velasquez (Listings/Producto), Cleimery Bravo (Mercado Libre),
Adam Pixler (Sales Director).
</contexto_proyecto>

<lectura_obligatoria_en_orden>
notes/CLAUDE.md (estado general agencia)
notes/state/STATE-agencia.md (qué cambió + bloqueos abiertos)
notes/brands/setex/setex.md (sesiones recientes, fases ejecutadas, pendientes)
notes/brands/setex/atom11-rules.md (rules v2026.3 status Neha)
notes/daily/2026-05-22.md (último daily Setex)
notes/sops/amazon-bulk-upload-guide.md (16 learnings — gotchas de bulk format)
</lectura_obligatoria_en_orden>

<conocimiento_operativo_setex>

**Estado post 22/05 (snapshot tras 5 bulks)**

KPIs cuenta:
- ACoS cuenta pre-bulks: 19.4% · TACoS 14% (target 18% confirmado meet 20/05)
- ROAS 5.15x · 393 orders / 30d · CVR 10.46%
- Net esperado post-bulks: -$400/mo spend / +$25k/mo sales

5 bulks ejecutados 22/05 (UUIDs):
- Bulk 1 Pausas+Archive (7): `cb02fff2-3421-48cb-8a22-724f12d745b9`
- Bulk 2 Bid Up (15): `cc7bb7a9-f6bf-4c78-a79c-2157ee72ec90`
- Bulk 3 Bid Down (4): `9e7cad37-24ed-4879-9b31-f09b2c0cda09`
- Bulk 4 Escalar (5): `92e33b06-dd4c-4d19-85da-68638ede73bd`
- Bulk 5 Negativos (126): `cd9c099c-bcbd-41dd-9b9a-cc111aae38cc`

Atom11 status:
- 🟡 ENVIADO A NEHA 22/05 — esperando confirmación de:
  - Prefix STX (alternativa SETEX)
  - Schedule Tue+Fri 06:00 ART
  - Timeline Fase 1 (22 rules RANKING + DEFENSIVE)
- 52 rules diseñadas v2026.3 con coverage 100% (86/86 ENABLED clasificadas)
- Archivo: `Setex_Atom11_Rules_v2026_3_22May.xlsx`

Heroes Setex actuales:
- B081GB8F89 (1mm 5p Transp $240) — Best Seller badge, 253u/30d ($50,672 sales)
- B08C2T72ND (1mm 5p Negro $240) — 113u/30d ($22,032)
- B0F3PSP82K (Thin family parent, 5 EXACT THIN-PUSH activas con bid $6 nuevo)
- B0DK7PHXXC + B0DK7Q4ZTY (Nano Gen2) — ROAS 11x
- B09HW4VWQR + B09HVXDH7M (Thick 1.8mm 5p) — ROAS 10x

Pendientes Tati (mensaje posteado 22/05):
- Listing audit B081GB8F89 ES (8 EXACT funnel break SQP)
- Audit listing EN B081GB8F89 (queries EN PS 0%)
- Confirmar ETAs inbound: B0F63LTD92 / B0C7WPFVGV / B0B94KBY8H

Flags Seller Central activas 22/05:
- B09F7YB74Y (1mm Rojos): 3u + 10u inbound → riesgo OOS
- B0DW9Z2H2W (Nano 15p Negros): Missing offer + 0u stock
- B0CC6THCDS (Kids 15p Transp $530): 1u en 30d con 33u stock — eval precio

Naming convention Setex post-22/05:
Patrón Atom11: `Setex | <PORTFOLIO> | SP | <MATCH> - <CATEGORÍA> - <ASIN> - <CLUSTER>`
Campañas legacy de marzo siguen naming distinto — no reescribir.

Bid strategy:
- Dynamic bids - down only en mayoría
- Fixed bid en DEFENSIVE Brand Hub Heroes
- TOS +50% para 5 THIN-PUSH (post-22/05) y Brand Hub Heroes
- TOS +20% para el resto

Targets ACoS por objetivo (cascade):
- DISCOVERY 30% / RANKING 25% / PROFIT 17.5% / CONQUEST 15% / DEFENSIVE 10%

</conocimiento_operativo_setex>

<bugs_y_gotchas_bulk_format>
Aplican los 16 learnings del SOP. Últimos 5 críticos (post-22/05):
12. Bug módulo M4 STR_analizado solo procesa KW campaigns (70% business out)
13. Cross-client ASIN safety check pre-mensajes operativos
14. Cruce Seller Central obligatorio pre-mensajes Tati
15. Orden CREATE vs UPDATE en secuencia bulks (CREATE último, más tolerante)
16. Validación cruzada 7 checks pre-bulk harvest EXACT
</bugs_y_gotchas_bulk_format>

<flujo_de_arranque>
Confirmá brevemente entendimiento de:
- Estado post-bulks 22/05 (5 bulks aplicados / +$223/d budget winners)
- Status Atom11 (esperando Neha)
- Pendientes Tati (3 items posteados)
- Flags nuevas Seller Central

Recordame correr al inicio:
git status
git pull
git add . && git commit -m "checkpoint: pre-trabajo Setex [fecha]"

Preguntame qué atacamos hoy. Opciones probables:
(a) Eval día 7 post-bulks 22/05 (impressions + winners + KW post-bid-down)
(b) Arranque Fase 1 Atom11 si Neha confirmó (22 rules RANKING + DEFENSIVE)
(c) Reevaluar harvest EXACT con SQP fresco post-optimización
(d) Consolidar duplicados brand defense (7 camps duplicadas)
(e) CLUSTER Core ES case-by-case (6 KWs uniformes $13.10)
(f) Otro tema específico

Si involucra bulks → revisar gotchas (especialmente learning 12 del módulo M4)
</flujo_de_arranque>

<rituales_obligatorios>
Al cierre: usar notes/prompts/sesion/cierre-meta.md para generar el mega-prompt
para CC que actualiza el vault, hace git commit + push, y recuerda el refresh
del proyecto Claude.

NUEVO POST-22/05:
- Validar ASINs no pertenecen a otra cuenta antes de mensajes
- Cruzar con Seller Central para flags abiertas
</rituales_obligatorios>

</arranque_sesion>
