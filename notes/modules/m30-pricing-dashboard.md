---
tipo: modulo
modulo: M30
seccion: Account Health
estado: en-port-f31
owner: lenin
fuente: .claude/porting-sources/pricing-dashboard.html
porting-pattern: Caso 3 (HTML complejo con scoring multi-fuente)
---

# M30 Pricing Dashboard

Port desde HTML self-contained (3.16 MB) entregado por Marcos. Sección Account Health, multi-cliente.

## Origen

HTML fuente: `.claude/porting-sources/pricing-dashboard.html` (gitignored, copia local 2026-06-01).

## Funcionalidad

Dashboard de pricing semanal por SKU con scoring multi-fuente:
- 6 inputs: fba (CSV), fee (CSV), pl (XLSX), maestro (XLSX), awd (CSV), izzi (XLSX)
- 20+ reglas de scoring (DoS, health, aging, ventas, BB gap, margen, AIS)
- 4 clasificaciones: subir / bajar / liquidar / mantener
- 7 tabs internos: resumen + principal + AWD/FBA + liquidar + sin margen + AIS + histórico
- 4 exports XLSX

## Schema

`data/_schemas/pricing-dashboard-v1.json` — commit 8d79e9e.

47 columnas, 21 required + 26 opcionales. Layout disco:
```
data/account-health/<cliente>/pricing-dashboard/<YYYY-MM-DD>.parquet
data/account-health/<cliente>/pricing-dashboard/_history.parquet  (reconstruido)
data/account-health/pricing-dashboard/<cliente>-v1.json  (config per-cliente)
```

## Bug heredado conocido (NO arreglar durante port)

**Restock alert 30-vs-37**: dos paths con multiplicadores y mensajes distintos.

- `runAnalysis` HTML L837: `Math.round(dailyR * 37) - fbaAv`, mensaje "Mover Xu a FBA desde Y"
- `computeScore` HTML L1029: `Math.round(daily_rate * 30) - fba_avail`, mensaje "Mover Xu desde Y"

Misma condición de disparo (`fba_dos <= 30 && has_backup && total_dos > 30`). Path 30 es dead-code efectivo en flujo normal (guard `!restock_alert`).

**Decisión**: replicar ambos paths verbatim en Python. Fix consciente en sesión posterior (fuera del scope del port).

## Decisiones arquitectónicas del port

1. **Snapshot HTML self-contained eliminado**. Reemplazado por Parquet + XLSX exports. Reversible.
2. **SAMPLE_DATA NO porteada**. Botón "Cargar datos de ejemplo" eliminado.
3. **SUBCAT_FEE_AVG**: hardcoded en HTML → config per-cliente en Python.
4. **Year**: hardcoded 2026 en v1. v2 selector.
5. **Strings de Amazon ('Excess', 'Low stock', 'Out of stock', 'Invierno')**: verbatim, no normalizar.

## Estado actual

| Fase | Estado | Commit |
|---|---|---|
| F1 Pasada 1 (recon) | ✅ | (sin commit, análisis) |
| F1 Pasada 2 (lógica) | ✅ | (sin commit, análisis) |
| F2 (diseño) | ✅ | (sin commit, revisión) |
| F3.1 (schema + persistencia) | ✅ APROBADO | 8d79e9e |
| F3.2 (parsers + lookups) | pendiente | — |
| F3.3 (scoring engine) | pendiente | — |
| F3.4 (UI tabs) | pendiente | — |
| F3.5 (exports XLSX) | pendiente | — |
| F3.6 (integración router) | pendiente | — |

## Branch

`feature/m30-pricing-port` desde main 6223700. HEAD actual: 8d79e9e.
