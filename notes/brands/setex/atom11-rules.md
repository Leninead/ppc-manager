---
tipo: brand-reference
actualizado: 2026-05-22
cliente: setex
---

# Atom11 Rules — Setex Technologies — v2026.3

**Status:** 🟡 ENVIADO A NEHA — esperando confirmación para deploy Fase 1

**Agencia:** Capybaras Agency
**Última actualización:** 2026-05-22
**Total rules diseñadas:** 52 (30 Bid + 10 Placement + 4 Negate + 4 Hard-Stop + 4 Harvest)
**Sistema:** v2026.3 por objetivo (disjoint ranges fix — lineage Dermaglos)
**Creadas por:** Lenin (manual)

**Detalle ejecución:** ver [[2026-05-22]] | catálogo: ver [[setex]] | estado: [[STATE-agencia]]

---

## Config general

| Parámetro | Valor |
|-----------|-------|
| Prefijo | STX |
| Target ACoS cuenta | 25% (= TACoS 18% confirmado meet 20/05) |
| Tier asignado | LOW único (price range MX$159-279 ≈ USD$9-16) |
| Brand exclude (Negate) | setex, gecko grip, nosepad |
| Frequency | Tue + Fri 06:00 ART |
| Wait between actions | 3 days |
| Lookback Bid/HardStop | 14 days |
| Lookback Negate/Harvest | 30 days |
| Bid max (INC) | MX$8.00 |
| Bid min (DEC) | MX$0.50 |
| Clicks Negate LOW | 18 |
| Spend Hard-Stop LOW | MX$300 |

## Targets por objetivo (cascade)

| Objetivo | Target ACoS | Multiplicador | Lógica |
|----------|-------------|---------------|--------|
| DISCOVERY | 30% | 120% cuenta | AUTO+BROAD — comprando data |
| RANKING | 25% | 100% | EXACT/PHRASE — posicionando |
| PROFIT | 17.5% | 70% | Harvested winners — eficiencia |
| CONQUEST | 15% | 60% | PT/PAT — cross-brand control |
| DEFENSIVE | 10% | 40% | Brand KWs — convierte solo |

## Thresholds v2026.3 — RANGOS DISJUNTOS (fix double-optimize)

| Objetivo | INC AGG < | INC SOFT | FLAT | DEC SOFT | DEC RISK | DEC CTRL | DEC HARD > |
|----------|-----------|----------|------|----------|----------|----------|------------|
| RANKING (t=25%) | <12.5% | 12.5-21.2% | 21.2-28.5% | 28.5-34.0% | 34.0-39.2% | 39.2-46.5% | >46.5% |
| DEFENSIVE (t=10%) | <5.0% | 5.0-8.5% | 8.5-11.4% | 11.4-13.6% | 13.6-15.7% | 15.7-18.6% | >18.6% |
| DISCOVERY (t=30%) | <15.0% | 15.0-25.5% | 25.5-34.2% | 34.2-40.8% | 40.8-47.1% | 47.1-55.8% | >55.8% |
| CONQUEST (t=15%) | <7.5% | 7.5-12.8% | 12.8-17.1% | 17.1-20.4% | 20.4-23.6% | 23.6-27.9% | >27.9% |
| PROFIT (t=17.5%) | <8.8% | 8.8-14.9% | 14.9-19.9% | 19.9-23.8% | 23.8-27.5% | 27.5-32.6% | >32.6% |

**Acción por rango**: +15% / +8% / no change / -10% / -15% / -25% / PAUSE TARGET

## Coverage — 86/86 ENABLED clasificadas (100%)

| Objetivo | Camps | Auto | Manual KW | Manual PT |
|----------|-------|------|-----------|-----------|
| RANKING | 25 | 0 | 25 | 0 |
| CONQUEST | 16 | 0 | 2 | 14 |
| DEFENSIVE | 14 | 0 | 9 | 5 |
| DISCOVERY | 28 | 23 | 5 | 0 |
| PROFIT | 3 | 0 | 3 | 0 |
| **TOTAL** | **86** | **23** | **44** | **19** |

## Plan de implementación 3 fases

| Fase | Rules | Cuándo | Detalle |
|------|-------|--------|---------|
| 1 — CRÍTICAS | 22 | 29/05 (eval día 7 bulks) | RANKING (6 Bid + 2 Placement + 1 Negate + 1 HardStop + 2 Harvest) + DEFENSIVE (6 Bid + 2 Placement) |
| 2 — ALCANCE | 20 | post-Fase 1 con 7d data | DISCOVERY (12) + CONQUEST (10) |
| 3 — EFICIENCIA | 10 | cuando haya 5+ Harvest creadas | PROFIT (10) |

## Diferencias vs template Dermaglos

| Aspecto | Dermaglos | Setex | Razón |
|---------|-----------|-------|-------|
| Tiers | LOW + MID | LOW único | Setex precio range chico ($9-16 USD) |
| Bid range | USD$0.15-$2.00 | MX$0.50-$8.00 | Mercado MX, CPCs más altos |
| Target DEFENSIVE | 50-71% | 40% | Brand defense Setex ultra eficiente (ACoS 0.2-5%) |
| Hard-Stop spend | USD$15-30 | MX$300 | Equivalente MX market |
| Total rules base | 79-83 | 52 | Setex no tiene SB/SD activos |

## Bid strategy Setex (post-12/05 + 22/05)

- Dynamic bids - down only en mayoría
- Fixed bid en DEFENSIVE Brand Hub Heroes
- Placement TOS: +50% para 5 THIN-PUSH (post-22/05) y Brand Hub Heroes
- Placement TOS: +20% para el resto

## Próximas evaluaciones

- 29/05: Eval día 7 post-bulks 22/05 + arranque Fase 1 Atom11 (si Neha confirmó)
- 05/06: Eval día 14 + eval Fase 1 Atom11 + arranque Fase 2 si todo OK
- 19/06: Eval día 28 + arranque Fase 3 (Harvest winners maduros)

## Findings/comentarios para Neha (en mensaje + Excel sheet 5)

1. ✅ v2026.3 incluye disjoint-range fix (no double-optimize en DEC tiers)
2. ✅ Single LOW tier — sin necesidad de MID/HIGH al launch
3. ✅ Bid min MX$0.50 (no USD$0.15 Dermaglos) — ajustado mercado MX
4. ⚠️ Capybaras ya ejecutó 5 bulks 22/05 (157 cambios / 33 camps) — Atom11 arranca
   en estado optimizado
5. ⚠️ Próxima review: 29/05 — eval día 7 post-launch
6. 📌 PROFIT con solo 3 camps al launch — Fase 3 se dispara cuando Harvest rules
   de Fase 1+2 generen más
7. 📌 Schedule sugerido: Tue+Fri 06:00 ART (same as Dermaglos)
