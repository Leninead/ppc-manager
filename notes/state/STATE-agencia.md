---
tipo: state
actualizado: 2026-04-24
---

# STATE Agencia — Capybaras

Snapshot operativo de la agencia. Agregador por diseño (no nota atómica).

---

## Clientes activos

| Cliente | Mercado | ACoS cuenta | Focus Q2 | Bloqueo principal | Brand note |
|---|---|---|---|---|---|
| Dermaglos | Amazon USA 🇺🇸 | 58.0% (↓ de 76.1%) | Meta ≤55%, escalar vitamin A + allantoin + tattoo ES | Rufus analysis 4 heroes + confirmación equipo Atom11 ejecutó entregable | [[DERMAGLOS]] · [[DERMAGLOS_DATA]] · [[atom11-rules]] |
| Mott & Bow | Amazon US 🇺🇸 | 11.7% (sano) | Full-Funnel Women — Fase 2 (SBV White Tee + SP Exact Premium Cotton) | Video creativo + Brand Store Women actualizado para lanzar Fase 2 26-30 abril | [[MB (2)]] |
| Love To Dream | Amazon MX 🇲🇽 | 22.7% (TACoS 17.4%) | TACoS target 10% Q3 · revenue $1M/mes · brand protection Atom11 | Stockout B09MG1PM6L (1u) + B09MG1J3LC (5u) — no escalar PPC | [[LTD]] |
| Setex Technologies | Amazon MX 🇲🇽 | 25.5% (↓ de 31.7%) | Listing optimization nose pads + temple tips · SBV B08PZF22R1 | Video SBV — definir quién produce (Tatiana/agencia) · BuyBox B08SNXF8HP | [[setex]] |
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

- **Sprint 1 Campaign Builder v2.0 — SB rewrite (cerrado 2026-04-23)**. `_render_sb()` reescrito 864→1121 líneas en `modules/pages/campaign_builder.py`. Selector SBV/SBH. Brand Entity ID obligatorio. 29 columnas bulk SB 2026. Validaciones estrictas. Naming Capybaras hardcoded preservado (contrato con M11 Atom11 Rules Builder).
- **Gamboa Generator M25 (integrado 2026-04-22)**. Módulo Account para reportes HTML integrales (SQP mensual + BR semanal). 5 archivos en `modules/gamboa/` + `modules/pages/gamboa_generator.py` (383L). Live en producción.
- **Bulk Amazon 2026 compliance (2026-04-21)**. 30→31 columnas, helper `_fila_vacia_bulk()`. Validado con Batch ID UUID. Ver [[PPC-SOP-Manager]] sección Campaign Builder + [[AmazonBulkUploadGuide]].
- **Vault Obsidian versionado (hoy 2026-04-24)**. `.gitignore` fix `notes/` → `notes/*` + excepciones por carpeta. Estructura 8 directorios (`brands/`, `daily/`, `knowledge/`, `personal/`, `prompts/`, `sops/`, `state/`, `.obsidian/`). 6 brand notes + 9 archivos sueltos reorganizados con `git mv`.
- **Sprint 2 Campaign Builder Modo B (TBD ~4-5h)**. XLSX custom + `st.data_editor` para flujo rápido power-user.
- **Sprint 3 DaypartingApp (TBD ~2h)**. Módulo nuevo Account Manager — automatización bids por día/hora.

---

## Bloqueos y pendientes críticos

- **Dermaglos**: Rufus analysis pendiente para los 4 heroes (B0CYLMJJJC, B0CYLM4L23, B0F4KXZVNM, B0F548KTXD) — gate para escalar ads. Confirmar equipo Atom11 ejecutó entregable `DG_Atom11_v2026_2_ENTREGABLE.xlsx` (fix bug CONQUEST SD + 8 rules SCAVENGER SP nuevas).
- **LTD stockout crítico**: B09MG1PM6L (1u, $24.8K MXN/mes) + B09MG1J3LC (5u, $15.9K MXN/mes). Alertar cliente. Además $226K USD/mes en top US sin presencia MX.
- **M&B Fase 2 bloqueada**: necesita Brand Store Women actualizado + video SBV para lanzar White Tee ($30/d) + Premium Cotton ($10/d) el 26-30 abril.
- **Setex SBV**: producción de video para B08PZF22R1 (Gecko Grip 0.6mm nano) sin dueño asignado.
- **360 Essentials SBV**: espera video creativo FreedomPlus para lanzar 3 campañas SBV ($45/d).
- **Git**: 2 commits locales sin push (`fbae212`, `3f04fb1`) + los que se agreguen hoy. Push manual al cerrar sesión.
- **Repo deuda técnica**: `INTELLIGENCE-INDEX.md` stale (dice 1 nota, M&B listado como MX en vez de US, sin 360 Essentials ni PVM).

---

## Próximos pasos inmediatos

1. **Dermaglos** — Ejecutar Rufus en 4 heroes (B0CYLMJJJC, B0CYLM4L23, B0F4KXZVNM, B0F548KTXD) + negativizaciones (18 términos) + harvest 7 KWs + escalar `dermaglos facial` / `dermaglos moisturizing cream` (0% brand share). Verificar equipo Atom11 ejecutó entregable `DG_Atom11_v2026_2_ENTREGABLE.xlsx`.
2. **M&B** — 27/04 evaluación día 14 Elizabeth Greene (3 camps con ToS +900%, bid efectivo $0.20). 05/05 evaluación día 14 PAT Premium (2 camps, 12 ASINs target DataDive). Condicionado → Fase 2 SBV + Premium Cotton.
3. **LTD** — Atom11 Rules Fase 1 (DEFENSIVE + RANKING) sobre 99 campañas. Seguir formato [[atom11-rules]] Dermaglos. Además: alertar cliente sobre stockout inminente B09MG1PM6L + B09MG1J3LC.
4. **360 Essentials** — Revisar evaluación Atom11 del 16/04 (pasó) y ejecutar plan PPC 2026: 3 camps SBV FreedomPlus ($45/d), test incrementalidad PHRASE KWS, relanzar SD RET VIEWS bid $1. Gate: video creativo FreedomPlus con cliente.
5. **Setex** — Listing optimization con STR+SQP keywords de mayor conversión para nose pads (B081GB8F89) y temple tips (B0B94KBY8H). Definir dueño del video SBV B08PZF22R1.
6. **Pura Vida Moringa** — 16/04 próxima evaluación: re-evaluar campañas HARVEST sesiones 1-3 (14+ días data). Negativizar b0dqr3ldwn y b08bbdc9c7 nuevos en AUTO DISCOVERY. Bajar bid RANK moringa capsulas.
7. **Repo** — decidir Sprint 2 (Campaign Builder Modo B, ~4-5h) vs Sprint 3 (DaypartingApp, ~2h) según prioridad. Actualizar [[INTELLIGENCE-INDEX]] stale (1 nota reportada, falta incluir 360 Essentials + PVM + corregir MB → US). Push de commits locales.
8. **Flujo vault + Claude.ai Project GitHub integration** — probar [[prompts-arranque-sesion]] la próxima sesión con una marca real (Dermaglos o M&B). Evaluar 2026-05-01 si el patrón "daily automático al cierre" se sostiene. Decidir si el compañero de agencia también setea el mismo flujo.
