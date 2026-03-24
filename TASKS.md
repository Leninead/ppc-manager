# TASKS.md — Tareas del día
**Última actualización:** 2026-03-24

---

## 🔴 HOY — Atom11 Rules Fase 2

Fase 1 completa (20 rules ✅). Crear las 16 rules de Fase 2 en Atom11:

### DISCOVERY SP Bid — Target 84% — 16 campañas (sheet: DG | DISCOVERY | SP)
- INC AGG <42% → ACOS < 42, Orders > 1, Clicks > 11 → Increase Bid 15%, until $2.00
- INC SOFT 42-71% → ACOS > 42 AND < 71, Orders > 0 → Increase Bid 8%, until $2.00
- FLAT 71-84% — NO CREAR
- DEC SOFT >96% → ACOS > 96, Clicks > 4 → Decrease Bid 10%, until $0.15
- DEC RISK >114% → ACOS > 114, Clicks > 4 → Decrease Bid 15%, until $0.15
- DEC CTRL >132% → ACOS > 132, Clicks > 4 → Decrease Bid 25%, until $0.15
- DEC HARD >156% → ACOS > 156, Clicks > 4 → PAUSE TARGET

### CONQUEST SP Bid — Target 60% — 15 campañas (sheet: DG | CONQUEST | SP)
- INC AGG <30% → ACOS < 30, Orders > 1, Clicks > 11 → Increase Bid 15%, until $2.00
- INC SOFT 30-51% → ACOS > 30 AND < 51, Orders > 0 → Increase Bid 8%, until $2.00
- FLAT 51-60% — NO CREAR
- DEC SOFT >68% → ACOS > 68, Clicks > 4 → Decrease Bid 10%, until $0.15
- DEC RISK >82% → ACOS > 82, Clicks > 4 → Decrease Bid 15%, until $0.15
- DEC CTRL >94% → ACOS > 94, Clicks > 4 → Decrease Bid 25%, until $0.15
- DEC HARD >112% → ACOS > 112, Clicks > 4 → PAUSE TARGET

### Harvest — DISCOVERY + RANKING — Lookback 30 days
- DG | DISCOVERY | HARVEST | AUTO→PHRASE | ORD≥2 ACOS<101 → Orders > 1, ACOS < 101%, Clicks > 4 → Add as Phrase Match
- DG | DISCOVERY | HARVEST | PHRASE→EXACT | ORD≥3 ACOS<84 → Orders > 2, ACOS < 84%, Clicks > 7 → Add as Exact Match
- DG | RANKING | HARVEST | AUTO→PHRASE | ORD≥2 ACOS<84 → Orders > 1, ACOS < 84%, Clicks > 4 → Add as Phrase Match
- DG | RANKING | HARVEST | PHRASE→EXACT | ORD≥3 ACOS<70 → Orders > 2, ACOS < 70%, Clicks > 7 → Add as Exact Match

### Config para todas: SP, 14d (Bid) o 30d (Harvest), Wait 3d, Tue+Fri 06:00

---

## 🟢 PRÓXIMAS SESIONES

- Fase 3 rules: PROFIT (6) + REMARKETING (6) + Negate/HardStop restantes (4)
- Sesión 11: Account Pulse
- Sesión 12: SOP completo
- Actualizar CLAUDE.md + DERMAGLOS.md + Atom11_Rules.md

---

## ✅ COMPLETADO

- [x] 6 rules RANKING SP Bid — creadas manual (2026-03-23)
- [x] 6 rules DEFENSIVE SP Bid — creadas Cowork (2026-03-23)
- [x] 4 rules Negate (RANKING/DEFENSIVE/DISCOVERY/CONQUEST) — Cowork (2026-03-23)
- [x] 4 rules Hard-Stop (RANKING/DEFENSIVE/DISCOVERY/CONQUEST) — Cowork (2026-03-23)
- [x] Rules viejas pausadas: 14 RANKING + 10 DEFENSIVE
- [x] 15 campañas B0CYLDSQ5L pausadas en Campaign Manager (2026-03-23)
- [x] 5 campañas B0CYLDSQ5L mantenidas con bid $0.50 (2026-03-23)
