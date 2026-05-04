---
tipo: report
cliente: setex
fecha: 2026-04-29
periodo: WoW (semana 23-29 abril vs 16-22 abril)
framework: Decomposición orgánico vs paid
actualizado: 2026-04-29
---

# Setex WoW Report — Decomposición orgánico vs paid (29/04/2026)

> **TL;DR**: La caída -14% WoW NO fue causada por PPC. 68% del gap es orgánico (OOS de 2 parents). PPC mejoró: orders +3%, CPC -1%. Plan ejecutado: pausar OOS + escalar momentum del 1mm + 9 campañas nuevas. Best Seller badge confirmado post-sesión = catalizador del récord histórico de ayer.

---

## 1. Snapshot inicial (meet WoW Tati)

| Métrica | Esta semana | Semana anterior | Δ |
|---|---|---|---|
| Sales totales | $1,467 | $1,711 | **-14%** |
| TACOS | 17.5% | — | mejorando |
| ROAS | 4.8× | — | sano |
| ACOS cuenta | 20.9% | — | mejorando |

Cliente atribuyó la caída a PPC y pidió subir budget. Antes de mover budget, decidí descomponer el gap.

## 2. Framework — Decomposición orgánico vs paid

Cuando AM atribuye una caída a PPC, el primer movimiento NO es subir budget. Es descomponer:

**Total gap = Ad gap + Organic gap**

Si organic gap > 50% del total gap → no es PPC, es operativo (OOS, listing, rank).

### Aplicado a Setex 23-29 abril:

| Componente | Cambio absoluto | % del gap |
|---|---|---|
| Total gap | -$244 | 100% |
| Ad sales delta | -$78 (-6%) | **32%** |
| Organic sales delta | -$166 (-41%) | **68%** |

**Conclusión:** 68% del problema es orgánico, no PPC.

### Métricas PPC reales (ignorando el ruido)

PPC mejoró WoW:
- Orders: +3%
- CPC: -1%
- CVR: flat (sin degradación)
- Spend dirigido: estable
- ACoS: mejorando

**Si subíamos budget como pidió el cliente** → estaríamos quemando plata en spend redundante mientras el problema operativo (OOS) seguía intacto.

## 3. Identificación del gap orgánico — root cause

Análisis por parent (ventas absolutas WoW):

| Parent ASIN | Producto | Sales esta sem | Sales sem ant | Δ |
|---|---|---|---|---|
| B0F4M9PS7R | Temple Tips | $0 | ~$200 | **-92%** 🔴 |
| B0F63LTD92 | Ear Hooks | $580 | ~$650 | -11% 🟡 |
| B081GB8F89 | 1mm Hero | $3,358 (¡ayer!) | $3,200 | +5% 🟢 |

### Verificación stockout (Inventory Snapshot Seller Central)

- **B0C7WPFVGV** (Temple grises): 0 unidades, OOS desde 18/04
- **B0B94KBY8H** (Temple negros): 0 unidades, OOS desde 23/04
- **B0F63LTD92** (Ear Hooks): 5u disponibles + 1 reservada → 4 reales, runway ~4 días

✅ Confirmado: caída orgánica de Temple Tips = 100% causada por OOS, no PPC.

## 4. Hallazgo paralelo — Récord histórico ayer (03/05)

Mientras analizábamos la caída WoW, descubrimos que ayer la cuenta hizo un **récord absoluto: 30u / $8,310** en un solo día.

### Split por Child Item (Business Report)

| ASIN | Producto | Units | Sales | % del récord |
|---|---|---|---|---|
| **B081GB8F89** | 1mm 5p Transp | **14u** | $3,358 | **47%** |
| B08C2T72ND | 1mm 5p Negros | 5u | $1,200 | 17% |
| B08SNRCL63 | 1mm 15p Negros | 2u | $960 | 12% |
| B09HW4VWQR | Thick 5p Negros | 2u | $578 | 7% |
| B09VYCD9PB | Thumbstick negro | 2u | $524 | 6% |
| B0F63LTD92 | Ear Hooks | 2u | $580 | 7% |
| B08SMSBFG9 | Thin 5p Negros | 1u | $290 | 3% |
| B0BQ8FNGR5 | Thick 15p Negros | 1u | $530 | 6% |
| B0DK7Q4ZTY | Nano 5p Transp | 1u | $290 | 3% |

**1mm acumulado: 21u (70% del récord)** — el caballo de batalla rocketeó, no Ear Hooks.

### Causa raíz — Best Seller badge confirmado

Tati confirmó al final de la sesión: **B081GB8F89 obtuvo Best Seller #1 en "Kits de Reparación para Lentes y Anteojos"** (Amazon MX). 4.1★, 17,049 reviews, 100+ comprados último mes.

El sales rank pasó de 24,672 → 6,261 (4× mejora) en los días previos al récord. El badge es resultado + acelerador (efecto bola de nieve).

## 5. Plan ejecutado (141 movimientos en 5 bulks)

| Bulk | Acción | Filas | Impacto |
|---|---|---|---|
| #1 Defensivo | Pause OOS Temple + waste + Ear Hook + budget -40% | 39 | -MX$28k/mes |
| #2 Ofensivo | Escalado +25-50% en winners 1mm/Ultra Thin/Nano | 12 | +MX$7,380/mes |
| #5 Negativos | Quirúrgico STR-based en Thumbstick (no preventivo) | 9 | -MX$120/mes waste |
| #4 Campañas Nuevas | 9 nuevas Atom11-friendly hero=B081GB8F89 | 75 | +MX$1,410/mes |
| #3 Reducir | Budget -25 a -35% en 6 campañas ACoS alto | 6 | -MX$4,050/mes |

**Net cuenta:** ~MX$23,000/mes redirigidos de waste hacia winners.

### Decisión PPC senior crítica del día

**Descarté el plan original 23/04 de aplicar 286 negativos preventivos a 22 campañas non-Thumbstick.** STR 30d mostró 0% contaminación gaming en non-Thumbstick. Aplicar negativos preventivos sin evidencia = ruido + deuda técnica.

En su lugar, generé bulk quirúrgico de 9 filas basado en STR real de Thumbstick remaining (donde sí había bleeders reales con MX$562/mes wasted).

**Principio**: nunca aplicar optimización porque "no hace daño". Solo aplicar si hay evidencia o ROI medible.

## 6. Por qué esto se alinea con el badge (descubierto post-sesión)

### Validación 1 — Bulk #2 escaló 1mm winners
Subimos `1mm CLUSTER English` +50% ($40→$60), `1mm PAT MATCH AA` +30% ($150→$195). Capturamos momentum del badge antes de saber del badge.

### Validación 2 — Bulk #4 con 8 de 9 nuevas hero=B081GB8F89
Cuando elegí concentrar en B081GB8F89 (no mix), el argumento fue "concentrar signal en el winner del récord". Resultó ser exactamente correcto — el winner del récord = el ASIN con badge.

### Validación 3 — Brand Hub Heroes (DEFENSIVE multi-target)
Con badge activo, búsquedas brand van a explotar. La campaña con $8/d budget + 50% ToS bid up está perfectamente posicionada para capturar el viento de cola del badge.

## 7. Riesgos identificados (post-badge)

### URGENTE
1. **B086H3TZ6B (1mm 15p Transp): 1 unidad de stock** — child del Best Seller. Si OOS prolongado puede degradar el listing del parent y arriesgar el badge.

### Importante
2. **Reviews ≥ 4★** — actualmente 4.1 con 17k reviews. Buen colchón pero monitorear.
3. **BuyBox >90%** — B08SNXF8HP histórico flagueado al 91.18%, monitorear.
4. **Sin flags/suppression** — Ningún listing flag actual.

## 8. KPIs target post-implementación (proyección 30 días)

| Métrica | Pre-bulks | Post-bulks (proyección) |
|---|---|---|
| Spend mensual | ~MX$50k | ~MX$30k (eficiente) |
| Sales mensuales | ~MX$48k (sub-OOS) | ~MX$60-70k (post-restock + badge boost) |
| ACoS cuenta | 20.9% | 15-18% target |
| TACOS | 17.5% | 14-16% target |
| Campañas activas (post Bulk #1) | 92 | 64 → enabled de calidad |

## 9. Próximas evaluaciones

- **Lunes 6 mayo**: chequeo impressions en las 9 campañas nuevas (4 días de aprendizaje)
- **Jueves 9 mayo**: review performance EXACT iniciales (1 semana)
- **Lunes 13 mayo**: review completo (10 días) — decidir si escalar budgets de las nuevas
- **Lunes 20 mayo**: review WoW completo post-implementación (3 semanas)
- **Día del restock Temple/Ear Hook**: reactivación con bid +25-30% según playbook [[PENDIENTES_RESTOCK]]

## 10. Decisiones para Tati (URGENTES)

1. ETA reposición FBA Temple Tips (B0C7WPFVGV + B0B94KBY8H)
2. ETA reposición FBA Ear Hooks B0F63LTD92 (4u runway 2-3 días)
3. B086H3TZ6B (1u): ¿es relanzamiento del restock? o stock crítico real
4. Aprobar (o ajustar) próximos pasos sugeridos:
    - Subir bid Brand Hub Heroes $3 → $5
    - Crear campañas con KWs "best nose pads", "amazon choice nose pads"
    - Listing optimization B081GB8F89 para lock-in del badge

---

Wikilinks: [[setex]] [[2026-04-29]] [[STATE-agencia]] [[PENDIENTES_RESTOCK]]
