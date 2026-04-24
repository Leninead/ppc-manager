# Atom11 Rules — Dermaglos USA — v2026.2 AGRESIVO
**Agencia:** Capybaras Agency
**Última actualización:** 2026-03-26
**Total rules activas:** 62 (+ 1 skipped + 1 harvest descartada)
**Rules viejas pausadas:** 14 (reemplazadas por v2026.2 — ver historial)
**Sistema:** v2026.2 por objetivo — ver lógica completa en `Atom11_Template.md`
**Creadas por:** Lenin (manual) + Cowork (automatizado via Claude in Chrome)
---
## Thresholds v2026.2 (multiplicadores × target ACoS)
| Nivel | Multiplicador | Acción |
|-------|--------------|--------|
| INC AGG | <0.50× | Increase Bid 15%, until $2.00 |
| INC SOFT | 0.50×-0.85× | Increase Bid 8%, until $2.00 |
| FLAT | 0.85×-1.0× | No tocar |
| DEC SOFT | >1.14× | Decrease Bid 10%, until $0.15 |
| DEC RISK | >1.36× | Decrease Bid 15%, until $0.15 |
| DEC CTRL | >1.57× | Decrease Bid 25%, until $0.15 |
| DEC HARD | >1.86× | PAUSE TARGET |
---
## Targets por objetivo
| Objetivo | Target ACoS | Campañas | Tipo Ad |
|----------|-------------|----------|---------|
| RANKING | 70% | 41 | SP |
| DEFENSIVE | 50% | 23 | SP |
| DISCOVERY | 84% | 16 | SP |
| CONQUEST | 60% | 15 | SP |
| PROFIT | 35% | 5 | SP |
| REMARKETING | 50% | 2 | SD |
| SCAVENGER | — | 6 | SP (sin rules) |
---
## Thresholds por objetivo (valores exactos)
| Objetivo | Target | INC AGG < | INC SOFT | DEC SOFT > | DEC RISK > | DEC CTRL > | DEC HARD > (PAUSE) |
|----------|--------|-----------|----------|------------|------------|------------|-------------------|
| RANKING | 70% | 35% | 35-60% | 80% | 95% | 110% | 130% |
| DEFENSIVE | 50% | 25% | 25-42% | 57% | 68% | 78% | 93% |
| DISCOVERY | 84% | 42% | 42-71% | 96% | 114% | 132% | 156% |
| CONQUEST | 60% | 30% | 30-51% | 68% | 82% | 94% | 112% |
| PROFIT | 35% | 18% | 18-30% | 40% | 48% | 55% | 65% |
| REMARKETING | 50% | 25% | 25-42% | 57% | 68% | 78% | 93% |
---
## Rules creadas — Inventario completo
### FASE 1 — Creadas 23/03/2026 (20 rules)
| # | Nombre | Tipo | Campañas | Condiciones | Acción |
|---|--------|------|----------|-------------|--------|
| 1 | DG RANKING BID MID INC AGG — ACOS <35 | Bid Optimiser SP | 41 | ACOS<35, Ord>1, Clicks>11 | +15% until $2 |
| 2 | DG RANKING BID MID INC SOFT — ACOS 35-60 | Bid Optimiser SP | 41 | ACOS>35 AND <60, Ord>0 | +8% until $2 |
| 3 | DG RANKING BID MID DEC SOFT — ACOS >80 | Bid Optimiser SP | 41 | ACOS>80, Clicks>4 | -10% until $0.15 |
| 4 | DG RANKING BID MID DEC RISK — ACOS >95 | Bid Optimiser SP | 41 | ACOS>95, Clicks>4 | -15% until $0.15 |
| 5 | DG RANKING BID MID DEC CTRL — ACOS >110 | Bid Optimiser SP | 41 | ACOS>110, Clicks>4 | -25% until $0.15 |
| 6 | DG RANKING BID MID DEC HARD — ACOS >130 | Bid Optimiser SP | 41 | ACOS>130, Clicks>4 | PAUSE TARGET |
| 7 | DG DEFENSIVE BID MID INC AGG — ACOS <25 | Bid Optimiser SP | 23 | ACOS<25, Ord>1, Clicks>11 | +15% until $2 |
| 8 | DG DEFENSIVE BID MID INC SOFT — ACOS 25-42 | Bid Optimiser SP | 23 | ACOS>25 AND <42, Ord>0 | +8% until $2 |
| 9 | DG DEFENSIVE BID MID DEC SOFT — ACOS >57 | Bid Optimiser SP | 23 | ACOS>57, Clicks>4 | -10% until $0.15 |
| 10 | DG DEFENSIVE BID MID DEC RISK — ACOS >68 | Bid Optimiser SP | 23 | ACOS>68, Clicks>4 | -15% until $0.15 |
| 11 | DG DEFENSIVE BID MID DEC CTRL — ACOS >78 | Bid Optimiser SP | 23 | ACOS>78, Clicks>4 | -25% until $0.15 |
| 12 | DG DEFENSIVE BID MID DEC HARD — ACOS >93 | Bid Optimiser SP | 23 | ACOS>93, Clicks>4 | PAUSE TARGET |
| 13 | DG RANKING NEGATE MID C>22 O=0 | Search Term Negator SP | 41 | Clicks>21, Ord=0 | Negate Exact |
| 14 | DG DEFENSIVE NEGATE MID C>22 O=0 | Search Term Negator SP | 23 | Clicks>21, Ord=0 | Negate Exact |
| 15 | DG DISCOVERY NEGATE MID C>22 O=0 | Search Term Negator SP | 16 | Clicks>21, Ord=0 | Negate Exact |
| 16 | DG CONQUEST NEGATE MID C>22 O=0 | Search Term Negator SP | 15 | Clicks>21, Ord=0 | Negate Exact |
| 17 | DG RANKING HARD-STOP MID SPEND>$22 O=0 | Bid Optimiser SP | 41 | Spend>22, Ord=0, Clicks>21 | -50% until $0.15 |
| 18 | DG DEFENSIVE HARD-STOP MID SPEND>$22 O=0 | Bid Optimiser SP | 23 | Spend>22, Ord=0, Clicks>21 | -50% until $0.15 |
| 19 | DG DISCOVERY HARD-STOP MID SPEND>$22 O=0 | Bid Optimiser SP | 16 | Spend>22, Ord=0, Clicks>21 | -50% until $0.15 |
| 20 | DG CONQUEST HARD-STOP MID SPEND>$22 O=0 | Bid Optimiser SP | 15 | Spend>22, Ord=0, Clicks>21 | -50% until $0.15 |
### FASE 2 — Creadas 24/03/2026 (12 rules + 3 Harvest activas + 1 descartada)
| # | Nombre | Tipo | Campañas | Condiciones | Acción |
|---|--------|------|----------|-------------|--------|
| 21 | DG DISCOVERY BID MID INC AGG — ACOS <42 | Bid Optimiser SP | 16 | ACOS<42, Ord>1, Clicks>11 | +15% until $2 |
| 22 | DG DISCOVERY BID MID INC SOFT — ACOS 42-71 | Bid Optimiser SP | 16 | ACOS>42 AND <71, Ord>0 | +8% until $2 |
| 23 | DG DISCOVERY BID MID DEC SOFT — ACOS >96 | Bid Optimiser SP | 16 | ACOS>96, Clicks>4 | -10% until $0.15 |
| 24 | DG DISCOVERY BID MID DEC RISK — ACOS >114 | Bid Optimiser SP | 16 | ACOS>114, Clicks>4 | -15% until $0.15 |
| 25 | DG DISCOVERY BID MID DEC CTRL — ACOS >132 | Bid Optimiser SP | 16 | ACOS>132, Clicks>4 | -25% until $0.15 |
| 26 | DG DISCOVERY BID MID DEC HARD — ACOS >156 | Bid Optimiser SP | 16 | ACOS>156, Clicks>4 | PAUSE TARGET |
| 27 | DG CONQUEST BID MID INC AGG — ACOS <30 | Bid Optimiser SP | 15 | ACOS<30, Ord>1, Clicks>11 | +15% until $2 |
| 28 | DG CONQUEST BID MID INC SOFT — ACOS 30-51 | Bid Optimiser SP | 15 | ACOS>30 AND <51, Ord>0 | +8% until $2 |
| 29 | DG CONQUEST BID MID DEC SOFT — ACOS >68 | Bid Optimiser SP | 15 | ACOS>68, Clicks>4 | -10% until $0.15 |
| 30 | DG CONQUEST BID MID DEC RISK — ACOS >82 | Bid Optimiser SP | 15 | ACOS>82, Clicks>4 | -15% until $0.15 |
| 31 | DG CONQUEST BID MID DEC CTRL — ACOS >94 | Bid Optimiser SP | 15 | ACOS>94, Clicks>4 | -25% until $0.15 |
| 32 | DG CONQUEST BID MID DEC HARD — ACOS >112 | Bid Optimiser SP | 15 | ACOS>112, Clicks>4 | PAUSE TARGET |
| 33 | DG DISCOVERY HARVEST AUTO→PHRASE (ORD≥2 ACOS<101) | Search Term Harvester SP | 10 | Ord≥2, ACOS<101 | Add Phrase | ✅ Atom11 #46 |
| 34 | DG DISCOVERY HARVEST PHRASE→EXACT (ORD≥3 ACOS<84) | Search Term Harvester SP | 3 | Ord≥3, ACOS<84 | Add Exact | ✅ Atom11 #45 |
| 35 | DG RANKING HARVEST AUTO→PHRASE | — | — | — | — | ❌ DESCARTADA (no existen campañas RANKING AUTO SP) |
| 36 | DG RANKING HARVEST PHRASE→EXACT (ORD≥3 ACOS<70) | Search Term Harvester SP | 13 | Ord≥3, ACOS<70 | Add Exact | ✅ Atom11 #44 |
### FASE 3 — Creadas 24/03/2026 (15 rules + 1 skipped)
| # | Nombre | Tipo | Campañas | Condiciones | Acción |
|---|--------|------|----------|-------------|--------|
| 37 | DG PROFIT BID MID INC AGG — ACOS <18 | Bid Optimiser SP | 5 | ACOS<18, Ord>1, Clicks>11 | +15% until $2 |
| 38 | DG PROFIT BID MID INC SOFT — ACOS 18-30 | Bid Optimiser SP | 5 | ACOS>18 AND <30, Ord>0 | +8% until $2 |
| 39 | DG PROFIT BID MID DEC SOFT — ACOS >40 | Bid Optimiser SP | 5 | ACOS>40, Clicks>4 | -10% until $0.15 |
| 40 | DG PROFIT BID MID DEC RISK — ACOS >48 | Bid Optimiser SP | 5 | ACOS>48, Clicks>4 | -15% until $0.15 |
| 41 | DG PROFIT BID MID DEC CTRL — ACOS >55 | Bid Optimiser SP | 5 | ACOS>55, Clicks>4 | -25% until $0.15 |
| 42 | DG PROFIT BID MID DEC HARD — ACOS >65 | Bid Optimiser SP | 5 | ACOS>65, Clicks>4 | PAUSE TARGET |
| 43 | DG REMARKETING BID MID INC AGG — ACOS <25 | Bid Optimiser SD | 2 | ACOS<25, Ord>1, Clicks>11 | +15% until $2 |
| 44 | DG REMARKETING BID MID INC SOFT — ACOS 25-42 | Bid Optimiser SD | 2 | ACOS>25 AND <42, Ord>0 | +8% until $2 |
| 45 | DG REMARKETING BID MID DEC SOFT — ACOS >57 | Bid Optimiser SD | 2 | ACOS>57, Clicks>4 | -10% until $0.15 |
| 46 | DG REMARKETING BID MID DEC RISK — ACOS >68 | Bid Optimiser SD | 2 | ACOS>68, Clicks>4 | -15% until $0.15 |
| 47 | DG REMARKETING BID MID DEC CTRL — ACOS >78 | Bid Optimiser SD | 2 | ACOS>78, Clicks>4 | -25% until $0.15 |
| 48 | DG REMARKETING BID MID DEC HARD — ACOS >93 | Bid Optimiser SD | 2 | ACOS>93, Clicks>4 | PAUSE TARGET |
| 49 | DG PROFIT NEGATE C>22 O=0 | Search Term Negator SP | 5 | Clicks>21, Ord=0 | Negate Exact |
| 50 | DG REMARKETING NEGATE | — | — | — | ❌ SKIPPED (SD no tiene search terms) |
| 51 | DG PROFIT HARD-STOP SPEND>$22 O=0 | Bid Optimiser SP | 5 | Spend>22, Ord=0, Clicks>21 | -50% until $0.15 |
| 52 | DG REMARKETING HARD-STOP SPEND>$22 O=0 | Bid Optimiser SD | 2 | Spend>22, Ord=0, Clicks>21 | -50% until $0.15 |
### FASE 4 — Creadas 25/03/2026 (7 rules CONQUEST SD)
| # | Nombre | Tipo | Campañas | Condiciones | Acción |
|---|--------|------|----------|-------------|--------|
| 53 | DG CONQUEST SD BID MID INC AGG — ACOS <30 | Bid Optimiser SD | 1 | ACOS<30, Ord>1, Clicks>11 | +15% until $2 |
| 54 | DG CONQUEST SD BID MID INC SOFT — ACOS 30-51 | Bid Optimiser SD | 1 | ACOS>30 AND <51, Ord>0 | +8% until $2 |
| 55 | DG CONQUEST SD BID MID DEC SOFT — ACOS >68 | Bid Optimiser SD | 1 | ACOS>68, Clicks>4 | -10% until $0.15 |
| 56 | DG CONQUEST SD BID MID DEC RISK — ACOS >82 | Bid Optimiser SD | 1 | ACOS>82, Clicks>4 | -15% until $0.15 |
| 57 | DG CONQUEST SD BID MID DEC CTRL — ACOS >94 | Bid Optimiser SD | 1 | ACOS>94, Clicks>4 | -25% until $0.15 |
| 58 | DG CONQUEST SD BID MID DEC HARD — ACOS >112 | Bid Optimiser SD | 1 | ACOS>112, Clicks>4 | PAUSE TARGET |
| 59 | DG CONQUEST SD HARD-STOP MID SPEND>$22 O=0 | Bid Optimiser SD | 1 | Spend>22, Ord=0, Clicks>21 | -50% until $0.15 |
### NO INCLUIDAS en v2026.2 (por diseño)
| Grupo | Campañas | Motivo |
|-------|----------|--------|
| SCAVENGER SP | 6 | Catch-all low bid, sin automatización |
| DEFENSIVE SB | 6 | Creadas por Lenin 24/03 — 7 rules custom SB (no v2026.2) |
| RANKING SB | 2 | Creadas por Lenin 25/03 — 7 rules custom SB (no v2026.2) |
| DEFENSIVE SD | 6 | Creadas por Lenin 25/03 — 7 rules custom SD (no v2026.2) |
| CONQUEST SD | 1 | ✅ MOVIDO a Fase 4 — 7 rules creadas 25/03/2026 |
---
## Config global todas las rules
- TIER: MID (único tier activo — cuenta con precios $9.99-$18.89)
- Wait: 3 days entre ejecuciones
- Frecuencia: Tuesday + Friday 06:00
- Lookback: 14 days (Bid/HardStop) | 30 days (Negate/Harvest)
- Until reaches INC: $2.00 | Until reaches DEC: $0.15
- Negate exclude KW: dermaglos, dermaglós
- Rules viejas pausadas (pre-v2026.2): 14 rules Feb/Mar 2026 pausadas 26/03/2026
---
## Historial de cambios
| Fecha | Cambio |
|-------|--------|
| 23/03/2026 | v2026.2 diseñada — thresholds agresivos, PAUSE TARGET en DEC HARD |
| 23/03/2026 | Fase 1: 20 rules (6 RANKING + 6 DEFENSIVE + 4 Negate + 4 HardStop) |
| 24/03/2026 | Fase 2: 12 rules (6 DISCOVERY + 6 CONQUEST) + Harvest |
| 24/03/2026 | Fase 3: 15 rules (6 PROFIT + 6 REMARKETING + Negate/HardStop) + 1 skipped |
| 25/03/2026 | Fase 4: 7 rules CONQUEST SD (6 Bid + 1 HardStop) |
| 26/03/2026 | 14 rules viejas pausadas (pre-v2026.2 duplicadas) |
| 26/03/2026 | Harvest: 3 activas (#44/#45/#46), 1 descartada (RANKING AUTO→PHRASE) |
| 26/03/2026 | Rule #97 SD ANTI-DRAIN pausada (10 errores, reemplazada) |
| 26/03/2026 | Rule #62 RANKING HARD-STOP — 28 campañas asignadas (activas, sin pausadas) |

---

## ⏳ Pendientes

- [ ] Primera evaluación de rules — **07/04/2026** (2 semanas desde activación)
- [ ] Evaluar agregar TIER LOW/HIGH cuando ACoS baje a <40%
- [ ] Verificar rule #66 RANKING NEGATE — confirmar 28 camps = correcto (son solo Manual Targeting)

### Rules viejas pausadas — 26/03/2026
Las siguientes rules de Feb/Mar 2026 fueron pausadas porque ya están cubiertas por las rules v2026.2:

| S.No. original | Nombre | Fecha creación | Motivo |
|----------------|--------|---------------|--------|
| #79 | DG REMARKETING SD VIEWS PAUSE - ACOS >150 | Mar 02 | Reemplazada por DG REMARKETING BID MID DEC HARD (#48) |
| #80 | DG SB EXACT VCPM PAUSE - ACOS > 120 | Feb 24 | Reemplazada por rules SB custom (#15-#21) |
| #81 | DG SB Defensive VCPM PAUSE - ACOS 120 | Feb 24 | Reemplazada por rules SB custom (#22-#28) |
| #82 | DG SB Defensive VCPM HARD DECREASE - ACOS 110 | Feb 24 | Reemplazada por rules SB custom (#22-#28) |
| #83 | DG SB Defensive VCPM SAFETY DECREASE - ACOS 80 | Feb 24 | Reemplazada por rules SB custom (#22-#28) |
| #84 | DG SB EXACT VCPM HARD DECREASE - ACOS > 110 | Feb 24 | Reemplazada por rules SB custom (#15-#21) |
| #85 | DG SB EXACT VCPM SAFETY DECREASE - ACOS 80 | Feb 24 | Reemplazada por rules SB custom (#15-#21) |
| #86 | DG SB EXACT VCPM INCREASE - ACOS <50 | Feb 24 | Reemplazada por rules SB custom (#15-#21) |
| #87 | DG SB ALL VCPM ANTI-DRAIN | Feb 24 | Reemplazada por HardStop rules v2026.2 |
| #89 | DG REMARKETING SD VIEWS HARD DECREASE - ACOS 80-120 | Feb 24 | Reemplazada por DG REMARKETING BID MID rules (#43-#48) |
| #90 | DG REMARKETING SD VIEWS SOFT DECREASE - ACOS 60-80 | Feb 24 | Reemplazada por DG REMARKETING BID MID rules (#43-#48) |
| #91 | DG REMARKETING SD VIEWS INCREASE - ACOS <40 | Feb 24 | Reemplazada por DG REMARKETING BID MID rules (#43-#48) |
| #94 | DG DEFENSIVE SD PAUSE - ACOS >120 | Feb 24 | Reemplazada por rules DEFENSIVE SD custom |
| #95 | DG DEFENSIVE SD HARD DECREASE - ACOS 90-120 | Feb 24 | Reemplazada por rules DEFENSIVE SD custom |
| #96 | DG DEFENSIVE SD SOFT DECREASE - ACOS 70-90 | Feb 24 | Reemplazada por rules DEFENSIVE SD custom |
| #97 | DG SD ALL ANTI-DRAIN - DECREASE - CLICKS >25 | Feb 24 | Reemplazada por HardStop rules v2026.2 |
