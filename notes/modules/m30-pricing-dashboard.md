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
| F3.2 (parsers + lookups) | ✅ CERRADO | cfaa83d→86afa4d (4 commits) |
| F3.3 (scoring engine) | ✅ CERRADO | 84765f5→880967e (3 commits) |
| F3.4 (UI tabs) | ✅ CERRADO | dceffc5→108fa8e (6 commits, C1-C4b) |
| F3.5 (exports XLSX) | ✅ CERRADO | 1d420a4→12e7eb7 (3 commits, c1-c3) |
| F3.6 (integración router) | ✅ CERRADO | 23cf6d8 |

**BUILD 6/6 COMPLETO** — navegable en Account Health → `💲 Pricing Dashboard`.

## Branch

`feature/m30-pricing-port` desde main 6223700. HEAD actual: 12e7eb7 (pusheado).

## F3.5 — Exports XLSX (cerrada 2026-06-08)

**Discovery:** el HTML tenía 4 "exports" pero solo uno servía:
- `exportResumen` — único real + wireado. Porteado **verbatim** (9 cols, hoja 'Pricing', orden por clasificación con `_RESUMEN_ORDER` incl. `awdfba` dead-key heredado, anchos `[26,14,11,11,11,11,13,14,11]`, defaults `||` vía `_js_truthy`, key real `suggestedPrice` camelCase).
- `exportTracker` — definido pero **bloqueado**: depende de `RAW.tracker` (7º source no porteado). Feature aparte, fuera de M30.
- `exportAllInOne` / `exportTable` — **fantasmas** (botones que llaman funciones inexistentes en el HTML). No se portean.

**Scope real (Lenin):** `exportResumen` verbatim + 4 export-por-vista reconstruidos.

**Helpers (puros, fuera de render, openpyxl→BytesIO):**
- `_build_resumen_excel(resultados, snapshot_date) -> bytes`
- `_build_vista_excel(df, sheet_name) -> bytes` (header=df.columns, sheet[:31], NaN→None, anchos max(12,len))

**Wiring:** 5 `st.download_button` (1 resumen global + 4 por vista Principal/Liquidar/SinMargen/AIS), keys `m30_export_*`, `disabled` por `not resultados`/`df.empty`.

**Desviación consciente:** filename `Gamboa_` (HTML) → `{cliente}_<Vista>_{fecha}.xlsx` (multi-cliente).

**Commits:** `1d420a4` (c1) · `0755206` (c2) · `12e7eb7` (c3 menores reviewer). Tests: 16 passed. Reviewer: MERGE, 0 bloqueantes.

## Deuda viva (fuera del build)
**Builders awd/izzi `{sku: unidades}`** — port de izzi (hoja 'Inventario 2526', offset 2 filas, cols posicionales 0/5) + awd (filtrado filas metadata). Hasta entonces: tab AWD/FBA = panel pendiente, backup stock=0, restock PATH-37 inalcanzable. Flagueado en código y UI. Próxima sesión.

## 2026-06-17 — Vinculación a Supabase (vía capa compartida)

M30 quedó vinculado a Supabase NO con código propio, sino a través del swap de la capa compartida core/persistence.py (mismo mecanismo servirá a M28). Sin flag, M30 sigue en disco local (cero regresión). Con flag backend="supabase" en secrets de Cloud → persiste en ah_snapshots/ah_configs.

- Tablas: ah_snapshots PK (area,cliente,modulo,period), ah_configs PK (area,modulo,name,version). jsonb genérico.
- M30 usa: _save_snapshot/_load_snapshot/_load_history/_rebuild_history/_save_config/_load_config/_list_periods → todos delegando al backend activo. pricing_dashboard.py NO se tocó.
- Verificado end-to-end local (write/read/list/config) contra Supabase real, datos de prueba limpiados.
- Migración inicial: N/A (0 snapshots locales previos).
- Pendiente: swap-day en Cloud (flag + reboot). Branch feature/supabase-account-health mergeada a main (faf1ab6).
