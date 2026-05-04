---
tipo: state
actualizado: 2026-04-29
---

# STATE Agencia — Capybaras

Snapshot operativo de la agencia. Agregador por diseño (no nota atómica).

---

## Última sesión — 2026-04-27

**Cliente tocado**: M&B (Mott & Bow USA). Sesión sin cambios en repo Streamlit — todo análisis + ejecución en Amazon Ads Console.

**Hallazgo crítico**: Las 9 campañas non-branded del 07/04 (Marcy) + 13/04 (Elizabeth Greene) nunca arrancaron — bid $0.02 + ToS +900% no superó bid floor de Amazon. Pivot ejecutivo a arquitectura clásica EXACT con multi-child.

**Acciones ejecutadas**:
- Cleanup quirúrgico: 8 campañas pausadas, 2 bid -50%, 4 acciones internas en ad groups SD/SBV (descubrimiento Purchases:90 con 80% CVR, KW "women t shirt" singular winner aislado).
- 3 EXACT non-branded HW lanzadas (Batch UUID `b09c8dd1-00c5-4b2c-a86b-af169ac7ac49`): NB CR HW A ($15/d, 5 KWs validadas, M+L+S White), NB VN HW A ($8/d, 1 KW HOT, M+L+XL Crimson), NB VN HW B ($7/d, 3 KWs expansión, M+L+XL Crimson). Total $30/d, eval 11/05.
- Bid up PAT Premium 21/04: 24 targets de $0.60 → $1.10 (bulk action).
- Verificado vs Campaign_Apr_27_2026__3_.csv: cleanup ejecutado al 100%.

**Saga bulk**: 4 intentos hasta success. v2 falló por `%` en KW pero CREÓ campañas parcialmente (UI engañosa). v3 falló "already exists". v4 con naming HV→HW + fecha 27 = success.

**Pendiente bloqueante**: mensaje gate AM Fase 2 (Brand Store Women + video SBV) NO se redactó hoy. Ventana original 26-30 abril ya pasó.

**Próximas evaluaciones M&B**: 05/05 PAT Premium día 14 (con bid up $1.10) · 11/05 NB HW día 14.

---

## Clientes activos

| Cliente | Mercado | ACoS cuenta | Focus Q2 | Bloqueo principal | Brand note |
|---|---|---|---|---|---|
| Dermaglos | Amazon USA 🇺🇸 | 58.0% (↓ de 76.1%) | Meta ≤55%, escalar vitamin A + allantoin + tattoo ES | Rufus analysis 4 heroes + confirmación equipo Atom11 ejecutó entregable | [[DERMAGLOS]] · [[DERMAGLOS_DATA]] · [[atom11-rules]] |
| Mott & Bow | Amazon US 🇺🇸 | 11.7% (sano) | Full-Funnel Women — Fase 2 (SBV White Tee + SP Exact Premium Cotton) | Video creativo + Brand Store Women actualizado para lanzar Fase 2 26-30 abril | [[MB (2)]] |
| Love To Dream | Amazon MX 🇲🇽 | 16.1% | Plan 6 Fases ejecutado (5 de 6) — Fase 6 pendiente esta semana (Adam→Aaron, Agustín→cliente) | Mismatch producto/KW sistémico — auditoría dedicada esta semana · B09MG1J3LC sigue OOS · 5 EXACT heroes Delivering desde hoy | [[LTD]] |
| Setex Technologies | Amazon MX 🇲🇽 | 20.9% (↓ de 25.5%) | 🏆 Best Seller badge en B081GB8F89 — lock-in del badge + protección B086H3TZ6B (1u stock, child) + reactivación post-restock Temple/Ear Hook | ETA reposición FBA Temple Tips + Ear Hooks · B086H3TZ6B URGENTE 1u · portfolios manuales 9 nuevas | [[setex]] · [[PENDIENTES_RESTOCK]] |
| 360 Essentials | Amazon USA 🇺🇸 | 23.0% (✅ target 35%) | SBV FreedomPlus branded + test incrementalidad + relanzar SD bid $1 | Video creativo FreedomPlus para SBV (3 camps) | [[360ESSENTIALS]] |
| Pura Vida Moringa | Amazon MX 🇲🇽 | 45.5% marzo (proyectado 48-52% post-opt) | Bajar ACoS a 40-45% · consolidar rank orgánico top 2-5 | Sin crédito Atom11 — optimización manual | [[Puravidamoringa]] |

**Patrón cross-client**: todos los USA con cuenta madura (Dermaglos, M&B, 360 Essentials) corrieron Atom11 v2026.2 en marzo. Los MX (LTD, Setex, PVM) manuales — LTD con 38 rules vía Cowork, Setex sin Atom11, PVM sin crédito.

---

## Estado Atom11 por cliente

| Cliente | Rules activas | Versión | Coverage campañas | Próxima evaluación |
|---|---|---|---|---|
| Dermaglos | 83 | v2026.2 AGRESIVO | 117/123 (95%) | 11/04 realizada, 14 días desde confirmación equipo |
| 360 Essentials | 49 | v2026.2 | 110/131 + 23★ pendientes | 16/04 (primera evaluación) |
| LTD | 38 | custom (via Cowork) | 99 camps en 6 grupos | pendiente schedule oficial |
| M&B | — | sin Atom11 | optimización manual | n/a |
| Setex | — | sin Atom11 | 92 camps ENABLED | pendiente gestión con Guille |
| Pura Vida Moringa | — | sin Atom11 (sin crédito) | 14 camps manual | 16/04 evaluación manual |

---

## Proyectos en curso — Agency OS (PPC Manager)

Todos commiteados a `main`, pendientes de push.

- **Variation Builder M26 (2026-04-26 en curso)**. Módulo nuevo Account Manager para generar flat files Amazon (1 parent + N children). `modules/pages/variation_builder.py` (929L). 4 tabs: Parent / Children+Theme / Preview / Descargar. Tema Variation (Sabor, Tamano, Scent, etc). Bug abierto: `data_editor` requiere doble entrada para persistir — fix diseñado (3 keys pattern) pendiente de aplicar. End-to-end validado con template cliente `PET_FOOD__1_.xlsm`.
- **Sprint 1 Campaign Builder v2.0 — SB rewrite (cerrado 2026-04-23)**. `_render_sb()` reescrito 864→1121 líneas en `modules/pages/campaign_builder.py`. Selector SBV/SBH. Brand Entity ID obligatorio. 29 columnas bulk SB 2026. Validaciones estrictas. Naming Capybaras hardcoded preservado (contrato con M11 Atom11 Rules Builder).
- **Gamboa Generator M25 (integrado 2026-04-22)**. Módulo Account para reportes HTML integrales (SQP mensual + BR semanal). 5 archivos en `modules/gamboa/` + `modules/pages/gamboa_generator.py` (383L). Live en producción.
- **Bulk Amazon 2026 compliance (2026-04-21)**. 30→31 columnas, helper `_fila_vacia_bulk()`. Validado con Batch ID UUID. Ver [[PPC-SOP-Manager]] sección Campaign Builder + [[amazon-bulk-upload-guide]].
  - 2026-04-28: 8 learnings nuevos sumados (Negative vs Campaign Negative Keyword, Campaign IDs numéricos para campañas existentes, Start Date como texto, Google Sheets corrompe IDs, caracteres especiales rechazados, campaign analyzer puede mostrar zombies, SD schema 47 cols vs SP 31 cols, hoja única obligatoria). Ver sección "Learnings 2026-04-28" en [[amazon-bulk-upload-guide]].
- **Vault Obsidian versionado (hoy 2026-04-24)**. `.gitignore` fix `notes/` → `notes/*` + excepciones por carpeta. Estructura 8 directorios (`brands/`, `daily/`, `knowledge/`, `personal/`, `prompts/`, `sops/`, `state/`, `.obsidian/`). 6 brand notes + 9 archivos sueltos reorganizados con `git mv`.
- **Sprint 2 Campaign Builder Modo B (TBD ~4-5h)**. XLSX custom + `st.data_editor` para flujo rápido power-user.
- **Sprint 3 DaypartingApp (TBD ~2h)**. Módulo nuevo Account Manager — automatización bids por día/hora.

---

## Iniciativas cliente en curso

- **Dermaglos plan ejecución 28/04** — propagación 30 días. 7 campañas live desde 28/04 ($200/d budget). 46 negativos aplicados. 10 P0 pausadas ($3,960/mes recuperable). Targets: ACoS 56.3%→42-45% / Sales/d $76→$110-130 / Brand IS 0%→60-80%. Re-correr STR 15/05 para medir delta. Re-evaluar B0F548KTXD post-30 días con bids ajustados.
- **Setex cierre completo 29/04** — sesión de mayor impacto histórica de la cuenta. 5 bulks ejecutados (141 movimientos exitosos): #1 Defensivo (39 filas, UUID `7096ec9c-9528-4c22-a18f-328d56cb2a29`) · #2 Ofensivo (12 filas, UUID `5944afce-052e-4c7c-9084-545195cd8929`) · #5 Negativos quirúrgicos (9 filas, UUID `23877dc3-80de-489a-bbb1-12d35ff16385`) · #4 Campañas Nuevas (75 filas, UUID `ad5d988d-a835-43a1-912e-0bdb79991a2a`) · #3 Reducir (6 filas, UUID `426473c9-8e81-4b57-92c6-8817be3012fa`). Net cuenta: ~MX$23k/mes redirigidos. **Best Seller badge confirmado** post-sesión en B081GB8F89 (categoría "Kits de Reparación para Lentes y Anteojos") — validó retroactivamente toda la estrategia. **Framework "Decomposición orgánico vs paid"** descubierto y aplicado: caída -14% WoW era 68% orgánica (OOS Temple+Ear), no PPC. 9 campañas nuevas con naming Capybaras/Atom11-friendly creadas (8 hero=B081GB8F89 + 1 multi-target Brand Hub). Pendiente urgente: reposición FBA Temple Tips + Ear Hooks + B086H3TZ6B (1u, child del badge). Próximas evals: 06/05 (4d), 09/05 (1sem), 13/05 (10d), 20/05 (3sem). Ver [[setex]] y [[2026-04-29-WoW-organic-vs-paid-decomp]].

---

## Bloqueos y pendientes críticos

- **Variation Builder M26**: `data_editor` bug abierto — fix necesario antes de release. Seguimiento en [[daily/2026-04-26]].
- **Dermaglos**: ✅ Sesión 28/04 cierre completo — análisis cruzado + plan maestro + 3 bulks ejecutados (93/94 + 46/46 + 7/10 success) + 10 campañas P0 pausadas ($932 net waste detenido / $132/d budget liberado). 7 campañas nuevas live ($200/d budget). ⏳ Pendientes manuales próxima sesión (ver [[2026-04-28]]): Portfolio ID assignment a las 7 nuevas, allantoin 0.5% cream resolver, bid SD Views Retargeting 30D ($1→$0.50), budget B0CYLDSQ5L SP ASIN Related ($5→$15), mensaje corregido a Neha, listing opt Tattoo + Cleanser + Body Cream, restock B0F6V para activar push diferido. Atom11 v2026.2 EN REVISIÓN — Neha trabajando en v2026.3 con 4 fixes (1 corregido en diagnóstico hoy: bug del comma era falso positivo, problema real es rule HARD-STOP que no dispara). Cambio de status: B0F548KTXD sale de heroes (ROAS 0.61×). Estrella oculta identificada: B0F6VZMF2V (ROAS 6.20× OOS desde 09/04).
- **LTD progreso 25/04 cierre completo**: ✅ Fases 1+3+4+5 ejecutadas (sesiones 1+2 mismo día) · ⏳ Fase 6 pendiente esta semana — delegada a equipo (Adam con Aaron compliance B005ULUZIQ, Agustín con cliente ETA restock B09MG1J3LC + summary + lista heroes 3ra solicitud). Push Heroes Fase 4: 5 EXACT Delivering desde hoy +$200/d. Brand Defense expandido a 5 ad groups. Auditoría sistémica match producto/KW pendiente esta semana sin owner asignado. Outputs: bulk xlsx + HTML internal brief para Adam y Agustín.
- **M&B Fase 2 bloqueada (escalada pendiente)**: ventana original 26-30 abril vencida. Mensaje gate AM con pregunta cerrada (Brand Store Women + video SBV listos sí/no) NO se hizo hoy — primera tarea próxima sesión. Mientras: las 3 EXACT HW non-branded ($30/d) cubren funnel mid sin esperar al cliente. Eval 11/05.
- **Setex pendientes post-29/04**: ✅ Sesión 29/04 cierre completo — 141 movimientos en 5 bulks (todos UUIDs registrados) · Best Seller badge confirmado en B081GB8F89 · framework Decomposición orgánico vs paid descubierto. ⏳ Pendientes: (1) **B086H3TZ6B URGENTE — 1u stock, child del Best Seller, riesgo perder badge** · (2) ETA reposición FBA Temple Tips (B0C7WPFVGV + B0B94KBY8H, OOS desde 18-23/04) · (3) ETA reposición Ear Hooks B0F63LTD92 (4u runway 3-4d) · (4) Asignación manual portfolios RANKING/CONQUEST/DEFENSIVE a las 9 campañas nuevas · (5) Subir bid Brand Hub Heroes $3→$5 post-badge · (6) Crear KWs "best nose pads", "amazon choice nose pads" · (7) Listing optimization B081GB8F89 lock-in del badge · (8) Coordinar con Nicki: 5 SKUs duplicados Closed · (9) SBV B08PZF22R1 sin owner (heredado 15/04). Diferidos hasta restock: 5 campañas nuevas Temple/Ear Hook + 12 KWs harvest documentados en [[PENDIENTES_RESTOCK]]. Ver detalle completo en [[2026-04-29]] y [[setex]].
- **360 Essentials SBV**: espera video creativo FreedomPlus para lanzar 3 campañas SBV ($45/d).
- **Git**: 2 commits locales sin push (`fbae212`, `3f04fb1`) + los que se agreguen hoy. Push manual al cerrar sesión.
- **Repo deuda técnica**: `INTELLIGENCE-INDEX.md` stale (dice 1 nota, M&B listado como MX en vez de US, sin 360 Essentials ni PVM).
- **AmazonBulkUploadGuide.md stale (4 puntos críticos descubiertos 27/04)**: (1) caracteres prohibidos en Keyword Text no documentados (`%`, `$`, `#`, `@`, `*`, etc.) — el `&` SÍ se permite en negativeExact, (2) comportamiento secuencial stop-on-error 2026 no documentado — UI muestra Failed pero filas anteriores ya creadas (verificación visual obligatoria), (3) estrategia re-subida con cambio de 1 letra del naming, (4) Regla #2 lista 30 cols pero el código en producción usa 31 (Sites). Próxima sesión: actualizar guía. Riesgo si no se hace: bulks futuros van a fallar igual y el equipo va a perder horas.
- **Patrón Streamlit a documentar (29/04)**: `st.expander` no se puede anidar dentro de otro `st.expander` (`_check_nested_element_violation`). Bug intermitente — solo crashea cuando se ejecuta el branch que crea el expander interno, por eso pasa code review básico. Reemplazo standard: `st.popover` (Streamlit ≥1.28). Documentar en `notes/sops/` o `module-architecture-standard.md`.
- **Listing Monitor fix aplicado 29/04 + 2 sospechosos pendientes**: `modules/pages/listing_monitor.py` L563 — `st.expander("Ver bullets actuales")` anidado dentro de expander padre L508 → fix aplicado con `st.popover` (1 línea). Live en producción, validado con ASIN B01M6DFC5W (Medix 5.5, marketplace MX). Diagnóstico via agente `code-reviewer` reveló 2 sospechosos del mismo bug que NO se atacaron (scope): `modules/pages/gamboa_generator.py` L322+L370 y `modules/pages/atom11.py` L261+L303. Verificar indentación próxima sesión y aplicar mismo fix preventivo si confirma.

---

## Próximos pasos inmediatos

1. **Variation Builder M26** — Aplicar fix de 3 keys al `data_editor` de tab Children. Testing end-to-end. Si falla → pasar a `st.form`. Commit + push.
2. **Dermaglos** — Ejecutar Rufus en 4 heroes (B0CYLMJJJC, B0CYLM4L23, B0F4KXZVNM, B0F548KTXD) + negativizaciones (18 términos) + harvest 7 KWs + escalar `dermaglos facial` / `dermaglos moisturizing cream` (0% brand share). Verificar equipo Atom11 ejecutó entregable `DG_Atom11_v2026_2_ENTREGABLE.xlsx`.
3. **M&B** — (1) Redactar mensaje gate AM Fase 2 (NO se hizo 27/04) — pregunta cerrada Brand Store Women + video SBV. (2) 05/05 eval día 14 PAT Premium (bid $1.10 desde 27/04) — si no impresiona en 72h escalada $1.50/creative/re-validar ASINs. (3) 11/05 eval día 14 NB HW (3 EXACT $30/d). (4) Investigar catálogo Jeans M&B — fuga branded 60-70% en queries "mott and bow jeans" (~$300+/mes). (5) Research PAT Conquest MTC vs TrueClassic ($69.99/541 purchases mercado/0% share) + Goodfellow + Lacoste + Polo RL — resuelve scope Men pendiente desde 21/04.
4. **LTD** — Fase 6 esta semana (delegada a equipo): Adam con Aaron por flag B005ULUZIQ, Agustín con cliente por ETA restock B09MG1J3LC + summary Fases 1+3+4+5 + lista heroes definitiva (3ra solicitud) + verificar movimiento precio $859→$809 B09MG1PM6L. Lenin pendiente: asignar portfolios manualmente a las 5 EXACT recién creadas (SU-NB / SU-M ×2 / SU-T / SU-S) + programar auditoría sistémica match producto/KW. Evaluaciones día 7 (02/05) y día 14 (09/05) anotadas en [[LTD]].
5. **360 Essentials** — Revisar evaluación Atom11 del 16/04 (pasó) y ejecutar plan PPC 2026: 3 camps SBV FreedomPlus ($45/d), test incrementalidad PHRASE KWS, relanzar SD RET VIEWS bid $1. Gate: video creativo FreedomPlus con cliente.
6. **Setex** — Listing optimization con STR+SQP keywords de mayor conversión para nose pads (B081GB8F89) y temple tips (B0B94KBY8H). Definir dueño del video SBV B08PZF22R1.
7. **Pura Vida Moringa** — 16/04 próxima evaluación: re-evaluar campañas HARVEST sesiones 1-3 (14+ días data). Negativizar b0dqr3ldwn y b08bbdc9c7 nuevos en AUTO DISCOVERY. Bajar bid RANK moringa capsulas.
8. **Repo** — decidir Sprint 2 (Campaign Builder Modo B, ~4-5h) vs Sprint 3 (DaypartingApp, ~2h) según prioridad. Actualizar [[INTELLIGENCE-INDEX]] stale (1 nota reportada, falta incluir 360 Essentials + PVM + corregir MB → US). Push de commits locales + cambios de hoy.
9. **Agentes** — ⏳ EN PROGRESO. `code-reviewer.md` actualizado 29/04 (claude-sonnet-4-5-20250514 → claude-sonnet-4-6). Pendiente: auditar el resto de `.claude/agents/*.md` por mismo patrón. Síntoma del bug: agente devuelve `tool_uses=0` sin error explícito. Revisar system prompt de `sop-writer` para que no modifique archivos no autorizados.
10. **Outputs LTD sesión 25/04**: Bulk `LTD_Fase4_Bulk_M4_Push_Heroes_25Abr2026.xlsx` subido a Amazon (Batch UUID 10d5a6ef). HTML internal brief `LTD_Sesion_25Abr2026_InternalBrief.html` generado para distribución interna Adam+Agustín. Ambos en /mnt/user-data/outputs (compartidos con Lenin desde Claude chat).
11. **Biblioteca de prompts v5 (2026-04-27)** — refrescar 7 archivos en proyecto Claude vía "Add content from GitHub". Después validar `cierre-meta` en sesión real durante esta misma conversación. Crear archivos de `codigo/` cuando aparezca el primer módulo nuevo. Actualizar [[CLAUDE]] del vault + [[Biblioteca]] con la nueva carpeta.
12. **Setex** — (1) Esperar respuesta Tati con ETA reposición FBA Temple Tips + Ear Hooks + B086H3TZ6B. (2) Asignación manual portfolios RANKING/CONQUEST/DEFENSIVE a las 9 nuevas en Campaign Manager. (3) 06/05 chequeo impressions de las 9 nuevas (4d). (4) 09/05 review performance EXACT iniciales (1sem). (5) Cuando llegue restock: ejecutar [[PENDIENTES_RESTOCK]] playbook (5 campañas + 12 KWs + bid +25-30%). (6) Próxima sesión también: subir bid Brand Hub Heroes $3→$5 + crear KWs "best nose pads" + listing opt B081GB8F89 + conectar Atom11 con Guille (pre-requisito ✓ cumplido).
