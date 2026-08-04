---
tipo: plan
modulo_id: M29
feature_slug: m29-datadive-mapper
actualizado: 2026-05-26
status: approved
---

# M29 — DataDive parsers → `modules/parsers/` + mapper a V3 — Plan APROBADO

> Recreado en worktree `ppc-manager-m29-mapper` (branch `feature/m29-datadive-mapper`,
> desde `main` bf205f7). El original se perdió al cerrar el worktree m29-d3 (estaba
> gitignored bajo `notes/*`). Esta vez se versiona con `git add -f`.

**Goal:** extraer los 3 parsers de `datadive_analyzer.py` a `modules/parsers/datadive.py`
(testeables fuera de Streamlit) + mapper `DataDive MKL → V3_seo_opportunity` que se aplica
reusando el flujo B7 (`merge_blocks` + apply 2-clicks/save).

**Arquitectura:** parsers puros + mapper que produce un `ImportReport` de 1 `BlockDraft`
→ se mergea con la MISMA `merge_blocks`. Cero HTML round-trip, cero merge nuevo.

## Decisiones cerradas (Lenin, 2026-05-26)
- **D1** `opportunity_score = min(launch_score / 10, 1.0)` (None si no hay launch_score).
- **D2** fixture sintético (no real anonimizado).
- **D3** weak rank: `current_rank > 30 OR current_rank is None` → cuenta como missing.
- **D4** fix bug NaN en `parse_mkl` al extraer (E1) + helper local `_coerce_int_safe()`.
- **D5** `text_input` ASIN + default desde propuesta si existe + validación `^B0[A-Z0-9]{8}$`.
- **D6** `page1_domination_chart_data` y `launch_score_table` = `[]` en v1.
- **D7** branch `feature/m29-datadive-mapper` + worktree `ppc-manager-m29-mapper` (✅ creado).
- **D8** m29-d3 cerrado (✅).

## Schema V3_seo_opportunity (catalog L283-322)
```
missing_keywords           : array<object> REQUIRED
  keyword           : string  required=true
  sv                : integer required=false nullable=true
  current_rank      : integer required=false nullable=true   # null si no rankea top100
  opportunity_score : number  required=false nullable=true   # 0-1
launch_score_table         : array<object> required=false  → [] en v1 (D6)
page1_domination_chart_data: array<object> required=false  → [] en v1 (D6)
```

## Archivos
```
modules/parsers/__init__.py                 NUEVO
modules/parsers/datadive.py                 NUEVO  parse_mkl/parse_competitors/parse_rank_radar + COL_* + _coerce_int_safe
modules/sales/mappers/__init__.py           NUEVO
modules/sales/mappers/datadive_to_v3.py     NUEVO  map_mkl_to_v3 + build_v3_import_report
modules/pages/datadive_analyzer.py          MOD    wrappers @st.cache_data delegando a parsers
modules/pages/proposal_studio.py            MOD    + _render_datadive_importer_section + call post-L2575
tests/test_datadive_parser.py               NUEVO
tests/test_datadive_to_v3_mapper.py         NUEVO
```

## Firmas
```python
# modules/parsers/datadive.py
COL_SEARCH_TERM = "Search Term"; COL_SV = "SV"; COL_RELEVANCE = "Relevance"
COL_SUGG_BID = "Sugg. Bid"; COL_LAUNCH_SCORE = "Launch Score"
def _coerce_int_safe(raw) -> int | None: ...        # NaN-safe (fix D4)
def parse_mkl(data: bytes, name: str) -> tuple[pd.DataFrame, list[str]]: ...
def parse_competitors(data: bytes, name: str) -> tuple[pd.DataFrame, dict]: ...
def parse_rank_radar(data: bytes, name: str) -> tuple[pd.DataFrame, list[str], dict]: ...

# modules/sales/mappers/datadive_to_v3.py
V3_MODULE_ID = "V3_seo_opportunity"; WEAK_RANK_THRESHOLD = 30   # D3
def map_mkl_to_v3(df_mkl, asin, *, min_sv=100, max_keywords=50, only_gaps=True) -> dict: ...
def build_v3_import_report(v3_data: dict) -> ImportReport: ...   # BlockDraft+ImportReport de b7_importer
```

## Sub-bloques
- **E1** Extraer parsers a `modules/parsers/datadive.py` (1:1) + wrappers cacheados en datadive_analyzer.py + fix NaN (`_coerce_int_safe`, TDD). Validación: suite 76/76 verde + test NaN. ~40min
- **E2** `tests/test_datadive_parser.py` (fixture sintético in-memory). ~45min
- **E3** mapper `datadive_to_v3.py`. ~50min
- **E4** `tests/test_datadive_to_v3_mapper.py` (df hand-built + integración merge_blocks). ~40min
- **E5** `_render_datadive_importer_section` en proposal_studio.py + call post-L2575. ~45min
- (**E6** smoke E2E + merge a main — fuera de este pedido E1→E5; consolidación posterior.)

Reporte por Ex antes de seguir al siguiente. Commit local por Ex. NO push (SOP Rule 4).

## Riesgos
1. Bug NaN `parse_mkl` (`int(NaN)` crash) → fix D4 con `_coerce_int_safe`.
2. `@st.cache_data` coupling → parsers puros + wrappers.
3. opportunity_score derivado (D1); arrays opcionales `[]` (D6).
4. asin no natural de DataDive → text_input (D5).
5. V3 puede no estar en target → `merge_blocks` skipea con badge.
6. Drift de nombres de columna → constantes `COL_*` compartidas.

## Log de ejecución (chat 26/05 PM — autónomo E1→E5)

| Ex | Commit | Resultado |
|---|---|---|
| setup | `08ac59b` | plan recreado (perdido al cerrar m29-d3) + force-add |
| E1 | `b540531` | parsers extraídos + fix NaN (TDD) — suite 78/78 |
| E2 | `a92d9a8` | 8 tests parser (characterization) — suite 86/86 |
| E3 | `a1f93ac` | mapper `datadive_to_v3_block` (TDD RED→GREEN, 9 tests) — suite 95/95 |
| E4 | `b37b237` | UI `_render_datadive_importer_section` + call site — py_compile+import OK, suite 95/95 |
| E5 | (este) | smoke E2E CLI ALL PASS (v12→v13, 7 missing kw) — suite 95/95 |

**Smoke E5:** chain completa `parse_mkl(bytes) → datadive_to_v3_block → merge_blocks → save_proposal`
con MKL sintético (10 kw, ranks cliente 3 strong / 4 weak / 3 None) → v13 en disco con
7 missing_keywords, opportunity_score=0.7. Script throwaway borrado.

### Deudas / hallazgos nuevos (NO en STATE — acá)
- **P2 (OK'd separado):** `tests/test_b7_importer.py` y el test de integración del mapper dependen
  del proposal gitignored `01fbf5c2…__v12.json`. En worktree/clone limpio → `FileNotFoundError`
  (2-3 tests). Se destraba copiando el v12 del principal. Fix real: fixture trackeado en `tests/fixtures/`.
- **P3 flag-collision UI:** `_render_datadive_importer_section` reusa el flag de 2-clicks de
  `_render_b7_apply_flow` (`ps_b7_confirm_apply_{pid}`). Si el operador tiene el expander B7 y el de
  DataDive con upload simultáneo, el estado de confirmación se comparte. Edge case baja prob.
  Fix futuro: parametrizar `flag_key` en `_render_b7_apply_flow` (toca función B7, requiere OK).
- **Hallazgo (no bug):** ranks faltantes en columna mixta int/None del MKL quedan como `NaN`
  (no `None`) por upcast de pandas → el mapper usa `pd.isna()`/`pd.notna()`, no `is None`.
