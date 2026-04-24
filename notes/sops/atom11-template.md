# 🤖 Atom11 Rules — Template Maestro Capybaras Agency
**Versión:** v2026.2
**Última actualización:** 2026-03-26
**Aplica a:** Todas las marcas — reemplazar `[PREFIX]` por el prefijo de la cuenta

---

## 🧠 Dos sistemas disponibles

| Sistema | Cuándo usarlo | Rules totales | Complejidad |
|---------|--------------|---------------|-------------|
| **v1 — Tiers por precio** | Cuentas nuevas, ACoS desconocido, catálogos mixtos de precio | 44 | Media |
| **v2026.2 — Por objetivo** | Cuentas con estructura clara de portfolios/objetivos, ACoS target definido | 83 | Alta |

> **Regla práctica:** Empezar con v2026.2 si ya tenés los grupos de campañas clasificados por objetivo. Usar v1 si la cuenta es nueva o los grupos no están definidos aún.

---

## 📐 Config global (aplica a ambos sistemas)

| Parámetro | Valor | Notas |
|-----------|-------|-------|
| Frecuencia | Martes + Viernes | 06:00 AM timezone de la cuenta |
| Wait between actions | 3 días | Entre ejecuciones sobre el mismo keyword |
| Bid máximo (INC) | $2.00 | Hasta que alcanza este valor |
| Bid mínimo (DEC) | $0.15 | Hasta que alcanza este valor |
| Exclude keywords | `[brand]` + `[brandé]` | Nunca negar brand terms propios |
| Lookback Bid/HardStop | 14 días | |
| Lookback Negate | 30 días | |
| Lookback Harvest | 30 días | |

---

---

# SISTEMA v1 — TIERS POR PRECIO

## Cuándo usar v1
- Cuenta nueva sin grupos de campañas definidos
- Target ACoS único para toda la cuenta
- Quiero protegerme por precio antes de tener suficiente data

## 🏗️ Configuración de Tiers

| Tier | Rango precio | Clicks Negate | Spend Hard-Stop | CVR ref |
|------|-------------|---------------|-----------------|---------|
| LOW | < $12 | 18 clicks | $15 | ~11% |
| MID | $12–$22 | 22 clicks | $22 | ~10% |
| HIGH | > $22 | 28 clicks | $30 | ~8% |

**Fórmula clicks negativización:** `round(1 / CVR_estimado) × 2`

### Cómo asignar tiers a tus ASINs
1. Listar todos los ASINs activos con su precio de venta
2. Asignar tier según rango
3. Agrupar campañas por tier en Atom11 (una sheet por tier)
4. Cada tier tiene su propio set de 14-16 rules

---

## 1. Bid Optimiser v1 — 18 rules (6 × 3 tiers)

**Lógica:** Aumentar cuando ACoS sano, bajar en escalera cuando se dispara.
**Flat Zone** = no tocar bid (zona de mantenimiento).

### TIER LOW (<$12) — Target ACoS ~60%

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| BID \| TIER LOW \| INC AGG — ACOS <35` | ACoS < 35% AND Orders ≥ 2 AND Clicks ≥ 10 | +15% until $2.00 |
| `[PREFIX] \| BID \| TIER LOW \| INC SOFT — ACOS 35-50` | ACoS 35-50% AND Orders ≥ 1 AND Clicks ≥ 8 | +8% until $2.00 |
| ⚡ FLAT ZONE 50-60% | — no tocar — | — |
| `[PREFIX] \| BID \| TIER LOW \| DEC SOFT — ACOS >90` | ACoS > 90% AND Clicks ≥ 5 | -10% until $0.15 |
| `[PREFIX] \| BID \| TIER LOW \| DEC RISK — ACOS >100` | ACoS > 100% AND Clicks ≥ 5 | -15% until $0.15 |
| `[PREFIX] \| BID \| TIER LOW \| DEC CTRL — ACOS >110` | ACoS > 110% AND Clicks ≥ 5 | -25% until $0.15 |
| `[PREFIX] \| BID \| TIER LOW \| DEC HARD — ACOS >130` | ACoS > 130% AND Clicks ≥ 5 | -40% until $0.15 |

### TIER MID ($12–$22) — Target ACoS ~60%

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| BID \| TIER MID \| INC AGG — ACOS <35` | ACoS < 35% AND Orders ≥ 2 AND Clicks ≥ 10 | +15% until $2.00 |
| `[PREFIX] \| BID \| TIER MID \| INC SOFT — ACOS 35-50` | ACoS 35-50% AND Orders ≥ 1 AND Clicks ≥ 8 | +8% until $2.00 |
| ⚡ FLAT ZONE 50-60% | — no tocar — | — |
| `[PREFIX] \| BID \| TIER MID \| DEC SOFT — ACOS >100` | ACoS > 100% AND Clicks ≥ 5 | -10% until $0.15 |
| `[PREFIX] \| BID \| TIER MID \| DEC RISK — ACOS >115` | ACoS > 115% AND Clicks ≥ 5 | -15% until $0.15 |
| `[PREFIX] \| BID \| TIER MID \| DEC CTRL — ACOS >125` | ACoS > 125% AND Clicks ≥ 5 | -25% until $0.15 |
| `[PREFIX] \| BID \| TIER MID \| DEC HARD — ACOS >145` | ACoS > 145% AND Clicks ≥ 5 | -40% until $0.15 |

### TIER HIGH (>$22) — Target ACoS ~60%

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| BID \| TIER HIGH \| INC AGG — ACOS <35` | ACoS < 35% AND Orders ≥ 2 AND Clicks ≥ 10 | +15% until $2.00 |
| `[PREFIX] \| BID \| TIER HIGH \| INC SOFT — ACOS 35-50` | ACoS 35-50% AND Orders ≥ 1 AND Clicks ≥ 8 | +8% until $2.00 |
| ⚡ FLAT ZONE 50-60% | — no tocar — | — |
| `[PREFIX] \| BID \| TIER HIGH \| DEC SOFT — ACOS >110` | ACoS > 110% AND Clicks ≥ 5 | -10% until $0.15 |
| `[PREFIX] \| BID \| TIER HIGH \| DEC RISK — ACOS >125` | ACoS > 125% AND Clicks ≥ 5 | -15% until $0.15 |
| `[PREFIX] \| BID \| TIER HIGH \| DEC CTRL — ACOS >140` | ACoS > 140% AND Clicks ≥ 5 | -25% until $0.15 |
| `[PREFIX] \| BID \| TIER HIGH \| DEC HARD — ACOS >160` | ACoS > 160% AND Clicks ≥ 5 | -40% until $0.15 |

---

## 2. Placement Optimiser v1 — 18 rules (6 × 3 tiers)

TOS = Top of Search | PP = Product Pages

### TIER LOW

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| PLACEMENT \| TIER LOW \| TOS INC — ACOS <45` | TOS ACoS < 45% AND Clicks ≥ 10 | TOS +10% |
| `[PREFIX] \| PLACEMENT \| TIER LOW \| TOS DEC SOFT — ACOS >65` | TOS ACoS > 65% AND Clicks ≥ 8 | TOS -15% |
| `[PREFIX] \| PLACEMENT \| TIER LOW \| TOS DEC HARD — ACOS >95` | TOS ACoS > 95% AND Clicks ≥ 8 | TOS -30% |
| `[PREFIX] \| PLACEMENT \| TIER LOW \| PP INC — ACOS <40` | PP ACoS < 40% AND Clicks ≥ 10 | PP +10% |
| `[PREFIX] \| PLACEMENT \| TIER LOW \| PP DEC SOFT — ACOS >60` | PP ACoS > 60% AND Clicks ≥ 8 | PP -15% |
| `[PREFIX] \| PLACEMENT \| TIER LOW \| PP DEC HARD — ACOS >85` | PP ACoS > 85% AND Clicks ≥ 8 | PP -30% |

### TIER MID

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| PLACEMENT \| TIER MID \| TOS INC — ACOS <45` | TOS ACoS < 45% AND Clicks ≥ 10 | TOS +10% |
| `[PREFIX] \| PLACEMENT \| TIER MID \| TOS DEC SOFT — ACOS >70` | TOS ACoS > 70% AND Clicks ≥ 8 | TOS -15% |
| `[PREFIX] \| PLACEMENT \| TIER MID \| TOS DEC HARD — ACOS >100` | TOS ACoS > 100% AND Clicks ≥ 8 | TOS -30% |
| `[PREFIX] \| PLACEMENT \| TIER MID \| PP INC — ACOS <40` | PP ACoS < 40% AND Clicks ≥ 10 | PP +10% |
| `[PREFIX] \| PLACEMENT \| TIER MID \| PP DEC SOFT — ACOS >65` | PP ACoS > 65% AND Clicks ≥ 8 | PP -15% |
| `[PREFIX] \| PLACEMENT \| TIER MID \| PP DEC HARD — ACOS >90` | PP ACoS > 90% AND Clicks ≥ 8 | PP -30% |

### TIER HIGH

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| PLACEMENT \| TIER HIGH \| TOS INC — ACOS <45` | TOS ACoS < 45% AND Clicks ≥ 10 | TOS +10% |
| `[PREFIX] \| PLACEMENT \| TIER HIGH \| TOS DEC SOFT — ACOS >75` | TOS ACoS > 75% AND Clicks ≥ 8 | TOS -15% |
| `[PREFIX] \| PLACEMENT \| TIER HIGH \| TOS DEC HARD — ACOS >105` | TOS ACoS > 105% AND Clicks ≥ 8 | TOS -30% |
| `[PREFIX] \| PLACEMENT \| TIER HIGH \| PP INC — ACOS <40` | PP ACoS < 40% AND Clicks ≥ 10 | PP +10% |
| `[PREFIX] \| PLACEMENT \| TIER HIGH \| PP DEC SOFT — ACOS >70` | PP ACoS > 70% AND Clicks ≥ 8 | PP -15% |
| `[PREFIX] \| PLACEMENT \| TIER HIGH \| PP DEC HARD — ACOS >95` | PP ACoS > 95% AND Clicks ≥ 8 | PP -30% |

---

## 3. Search Term Negator v1 — 3 rules

**Ventana:** 30 días | **Excluir:** brand terms propios

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| NEGATE \| TIER LOW \| C>18 O=0` | Clicks ≥ 18 AND Orders = 0 | Negative Exact |
| `[PREFIX] \| NEGATE \| TIER MID \| C>22 O=0` | Clicks ≥ 22 AND Orders = 0 | Negative Exact |
| `[PREFIX] \| NEGATE \| TIER HIGH \| C>28 O=0` | Clicks ≥ 28 AND Orders = 0 | Negative Exact |

---

## 4. Search Term Harvester v1 — 2 rules universales

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| HARVEST \| AUTO→PHRASE \| ORD≥2 ACOS<[120%target]` | Orders ≥ 2 AND ACoS < 120% del target AND Clicks ≥ 5 | Add as Phrase Match |
| `[PREFIX] \| HARVEST \| PHRASE→EXACT \| ORD≥3 ACOS<[target]` | Orders ≥ 3 AND ACoS < target AND Clicks ≥ 8 | Add as Exact Match |

---

## 5. Hard Stop Anti-Drain v1 — 3 rules

**Ventana:** 14 días

| Nombre | Condición | Acción |
|--------|-----------|--------|
| `[PREFIX] \| HARD-STOP \| TIER LOW \| SPEND>$15 O=0` | Spend ≥ $15 AND Orders = 0 AND Clicks ≥ 18 | Decrease bid -50% |
| `[PREFIX] \| HARD-STOP \| TIER MID \| SPEND>$22 O=0` | Spend ≥ $22 AND Orders = 0 AND Clicks ≥ 22 | Decrease bid -50% |
| `[PREFIX] \| HARD-STOP \| TIER HIGH \| SPEND>$30 O=0` | Spend ≥ $30 AND Orders = 0 AND Clicks ≥ 28 | Decrease bid -50% |

### Resumen v1 — 44 rules totales

| Tipo | LOW | MID | HIGH | Total |
|------|-----|-----|------|-------|
| Bid Optimiser | 6 | 6 | 6 | 18 |
| Placement Optimiser | 6 | 6 | 6 | 18 |
| Negator | 1 | 1 | 1 | 3 |
| Harvester | — | 2 | — | 2 |
| Hard Stop | 1 | 1 | 1 | 3 |
| **TOTAL** | **14** | **16** | **14** | **44** |

---

---

# SISTEMA v2026.2 — POR OBJETIVO (AGRESIVO)

## Cuándo usar v2026.2
- Campañas ya clasificadas en grupos por objetivo (RANKING, DEFENSIVE, DISCOVERY, etc.)
- Target ACoS definido por objetivo
- Cuenta con suficiente data (>4 semanas de historial)
- ACoS cuenta alto y necesitás mayor velocidad de corrección

## 🎯 Objetivos y sus targets

| Objetivo | Target ACoS | Lógica | Ad Types |
|----------|-------------|--------|----------|
| DISCOVERY | 120% del target cuenta | Comprando data — tolerante | SP Auto + Broad |
| RANKING | = target cuenta | Posicionando — balance | SP Exact + Phrase |
| CONQUEST | ~86% del target | Menor CVR en competidores | SP PAT + ASIN |
| DEFENSIVE | ~71% del target | Brand terms — más estricto | SP + SB brand KWs |
| PROFIT | 50% del target | Harvested winners — eficiencia | SP Exact harvested |
| REMARKETING | ~71% del target | Retargeting, buen CVR esperado | SD |

**Ejemplo con target cuenta = 70%:**
- DISCOVERY: 84% | RANKING: 70% | CONQUEST: 60% | DEFENSIVE: 50% | PROFIT: 35% | REMARKETING: 50%

---

## 📊 Fórmula para calcular thresholds

Dado `TARGET` = ACoS objetivo del grupo:

| Nivel | Multiplicador | Fórmula |
|-------|--------------|---------|
| INC AGG | <0.50× | ACoS < TARGET × 0.50 → +15% |
| INC SOFT | 0.50×-0.85× | ACoS entre TARGET×0.50 y TARGET×0.85 → +8% |
| FLAT | 0.85×-1.0× | Zona de mantenimiento — no tocar |
| DEC SOFT | >1.14× | ACoS > TARGET × 1.14 → -10% |
| DEC RISK | >1.36× | ACoS > TARGET × 1.36 → -15% |
| DEC CTRL | >1.57× | ACoS > TARGET × 1.57 → -25% |
| DEC HARD | >1.86× | ACoS > TARGET × 1.86 → **PAUSE TARGET** |

---

## 📐 Thresholds precalculados por objetivo (ejemplo target cuenta 70%)

| Objetivo | Target | INC AGG < | INC SOFT | DEC SOFT > | DEC RISK > | DEC CTRL > | DEC HARD > |
|----------|--------|-----------|----------|------------|------------|------------|------------|
| RANKING | 70% | 35% | 35-60% | 80% | 95% | 110% | 130% |
| DEFENSIVE | 50% | 25% | 25-42% | 57% | 68% | 78% | 93% |
| DISCOVERY | 84% | 42% | 42-71% | 96% | 114% | 132% | 156% |
| CONQUEST | 60% | 30% | 30-51% | 68% | 82% | 94% | 112% |
| PROFIT | 35% | 18% | 18-30% | 40% | 48% | 55% | 65% |
| REMARKETING | 50% | 25% | 25-42% | 57% | 68% | 78% | 93% |

> Para otros targets de cuenta: aplicar los multiplicadores de la tabla de arriba sobre el target de cada objetivo.

---

## Naming convention v2026.2

```
[PREFIX] | [OBJETIVO] | [AD TYPE] | [TIPO RULE] | [TIER] | [DESCRIPCIÓN]

Ejemplos:
DG | RANKING | SP | BID | MID | INC AGG — ACOS <35
DG | DEFENSIVE | SB | BID | MID | DEC HARD — ACOS >93
DG | RANKING | HARD-STOP | MID | SPEND>$22 O=0
DG | DISCOVERY | HARVEST | AUTO→PHRASE | ORD≥2 ACOS<101
DG | RANKING | NEGATE | MID | C>22 O=0
```

---

## Rules por grupo — v2026.2

### SP Groups (RANKING, DEFENSIVE, DISCOVERY, CONQUEST, PROFIT)
Cada grupo tiene:
- 6 Bid Optimiser rules (INC AGG, INC SOFT, DEC SOFT, DEC RISK, DEC CTRL, DEC HARD)
- 1 Search Term Negator
- 1 Hard Stop Anti-Drain

### RANKING + DISCOVERY — adicional
- 2 Harvest rules cada uno (AUTO→PHRASE y PHRASE→EXACT)

### SB Groups (DEFENSIVE SB, RANKING SB)
- 6 Bid Optimiser rules
- 1 Hard Stop
- ⚠️ Sin Negate (SB no tiene search terms)

### SD Groups (DEFENSIVE SD, CONQUEST SD, REMARKETING SD)
- 6 Bid Optimiser rules
- 1 Hard Stop
- ⚠️ Sin Negate (SD no tiene search terms)
- ⚠️ Sin Harvest (SD no genera search terms)

### SCAVENGER
- ❌ Sin rules automáticas (catch-all, low bid, dejar correr)

---

## Harvest thresholds v2026.2

| Rule | Condición | Acción |
|------|-----------|--------|
| `[PREFIX] \| DISCOVERY \| HARVEST \| AUTO→PHRASE` | Orders ≥ 2 AND ACoS < 120%×target AND Clicks ≥ 4 | Add as Phrase |
| `[PREFIX] \| DISCOVERY \| HARVEST \| PHRASE→EXACT` | Orders ≥ 3 AND ACoS < target AND Clicks ≥ 7 | Add as Exact |
| `[PREFIX] \| RANKING \| HARVEST \| AUTO→PHRASE` | Orders ≥ 2 AND ACoS < 120%×target AND Clicks ≥ 4 | Add as Phrase |
| `[PREFIX] \| RANKING \| HARVEST \| PHRASE→EXACT` | Orders ≥ 3 AND ACoS < target AND Clicks ≥ 7 | Add as Exact |

> ⚠️ **Antes de crear RANKING AUTO→PHRASE:** verificar que existan campañas RANKING con Auto targeting. Si todas las campañas RANKING son Exact/Phrase, esta rule no aplica — descartarla. En Dermaglos se descartó por este motivo (no hay campañas RANKING AUTO SP).

---

## Resumen v2026.2 — 83 rules (ejemplo Dermaglos)

| Grupo | Bid | Negate | HardStop | Harvest | Total |
|-------|-----|--------|----------|---------|-------|
| RANKING SP | 6 | 1 | 1 | 2 | 10 |
| DEFENSIVE SP | 6 | 1 | 1 | — | 8 |
| DISCOVERY SP | 6 | 1 | 1 | 2 | 10 |
| CONQUEST SP | 6 | 1 | 1 | — | 8 |
| PROFIT SP | 6 | 1 | 1 | — | 8 |
| REMARKETING SD | 6 | — | 1 | — | 7 |
| DEFENSIVE SB | 6 | — | 1 | — | 7 |
| RANKING SB | 6 | — | 1 | — | 7 |
| DEFENSIVE SD | 6 | — | 1 | — | 7 |
| CONQUEST SD | 6 | — | 1 | — | 7 |
| SCAVENGER | — | — | — | — | 0 |
| **TOTAL** | | | | | **79-83** |

---

---

# 🔄 CHECKLIST DE IMPLEMENTACIÓN — Nueva Marca

## Paso 1 — Elegir sistema
- [ ] ¿Tenés grupos de campañas por objetivo? → v2026.2
- [ ] ¿Cuenta nueva o sin estructura? → v1 tiers

## Paso 2 — Definir parámetros
- [ ] Prefijo de la cuenta: `____` (DG / MB / STX / LTD...)
- [ ] Target ACoS de la cuenta: `____%`
- [ ] Brand terms a excluir del Negate: `______________`
- [ ] Listar ASINs con precio → asignar tier LOW / MID / HIGH

## Paso 3 — Calcular thresholds (v2026.2)
Aplicar multiplicadores sobre el target de cada objetivo:

| Objetivo | Target | INC AGG | INC SOFT | DEC SOFT | DEC RISK | DEC CTRL | DEC HARD |
|----------|--------|---------|----------|----------|----------|----------|----------|
| RANKING | | | | | | | |
| DEFENSIVE | | | | | | | |
| DISCOVERY | | | | | | | |
| CONQUEST | | | | | | | |
| PROFIT | | | | | | | |
| REMARKETING | | | | | | | |

## Paso 4 — Clasificar campañas
- [ ] Crear Campaign Groups Excel (una sheet por objetivo)
- [ ] Completar sheet RESUMEN con cantidad por grupo
- [ ] Identificar campañas pausadas → excluir del upload

## Paso 5 — Crear rules en Atom11
- [ ] Fase 1: RANKING SP + DEFENSIVE SP (las más críticas)
- [ ] Fase 2: DISCOVERY SP + CONQUEST SP + Harvest
- [ ] Fase 3: PROFIT SP + REMARKETING SD + SB/SD groups
- [ ] Subir Campaign Groups via "Upload Campaigns File"
- [ ] Verificar "Selected Campaigns" coincide con el grupo

## Paso 6 — Documentar en .md del cliente
```
## 🤖 Atom11 Rules
- Sistema: v2026.2 / v1
- Target cuenta: X%
- Prefijo: XX
- Tiers: LOW=ASINs... MID=ASINs... HIGH=ASINs...
- Thresholds: ver tabla en Atom11_Template.md
- Rules activas: N
- Última revisión: fecha
- Próxima revisión: fecha (2 semanas)
```

---

## 📋 Implementaciones por cliente

| Cliente | Prefijo | Sistema | Target cuenta | Rules activas | Archivo de referencia | Próxima revisión |
|---------|---------|---------|--------------|---------------|----------------------|-----------------|
| Dermaglos USA | DG | v2026.2 | 70% | 62 activas + 14 pausadas viejas | `Atom11_Rules_DG.md` | 07/04/2026 (2 semanas) |
| M&B MX | MB | — | — | 0 | pendiente | — |
| Love To Dream MX | LTD | — | — | 0 | pendiente | — |
| Setex Technologies MX | STX | — | — | 0 | pendiente | — |

---

## ⚠️ Errores comunes

| Error | Causa | Solución |
|-------|-------|----------|
| "Not Found" al subir campaigns | Campaña pausada o eliminada | Remover del xlsx antes de subir — solo campañas ENABLED |
| Selected Campaigns: 0 | No se asignaron campañas al crear la rule | Hacer upload del Campaign Groups xlsx correspondiente |
| Rule ejecuta 0 veces | Lookback window muy corto o datos insuficientes | Cambiar a 30 días o más |
| Bid sube sin control | INC AGG sin condición de Orders | Agregar Orders ≥ 1 como condición mínima |
| Brand terms negativizados | Exclude keywords no configurado | Agregar brand + variante con acento en "Exclude Keywords" |
| Harvest AUTO→PHRASE no aplica | No existen campañas con Auto targeting en ese grupo | Descartar esa rule — no crear |
| SB/SD rules sin Negate | SD y SB no tienen search terms propios | No crear Negate para grupos SB o SD — es correcto |
| Campañas asignadas < esperado | Mezcla de campañas pausadas/activas en el xlsx | Filtrar solo ENABLED antes de generar el Campaign Groups xlsx |
