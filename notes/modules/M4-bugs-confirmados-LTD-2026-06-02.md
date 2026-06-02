---
date: 2026-06-02
module: M4
tags: [module, m4, bugs, ltd-mx, regression-test]
status: open
fix_session_planned: 2026-06-06 con Marcos/Ramiro
---

# M4 STR_analizado — 10 bugs confirmados con LTD MX 01/05-01/06

Fix `b2763cb` del 26/05 **NO resuelve** para LTD. Bugs reproducibles con dataset LTD mayo:

## Bug list

1. **AUTO + PT match types ignorados** — solo procesa BROAD/PHRASE/EXACT = 425 rows ($4,736) de 2,279 ($33,281). Deja afuera 64.3% del business ($21,409 AUTO).

2. **Bulks generados con NaN en campos obligatorios** — Product, Campaign Name, Ad Group Name vacíos 100%. Fallan 100% al subir a Amazon.

3. **3 KWs simultáneamente clasificadas como Negative Y Harvest** (contradicción lógica):
   - swaddle
   - saco de dormir bebe
   - saco para dormir bebe

4. **12 ASINs propios LTD en bulk harvest** (auto-canibalización):
   b0f8pcwd6j, b0081gj038, b00mjxhm48, b0ck2c1zj5, b0081giz52, b0088hvghs, b09mg1j3lc, b09mg3mw3h, b0djsf2n6p, b0djsgbr4p, b0cyj8pr8t, b0f8pb4nhx

5. **KW convertidora clasificada como Negative** — "saco para dormir bebe" tiene $3,668 spend / $8,756 sales en STR → módulo la marca como Negative.

6. **Bids absurdos en bulk harvest**:
   - b0088hvghs $193.28 (vs bid LTD real $3-15)
   - love to dream $73.63 (vs bid brand defense $5-10)

7. **Duplicados en harvest** — 11 rows duplicadas de 27 total (41% del bulk).

8. **Duplicado en negatives** — `muselinas para bebe` × 2.

9. **Hojas "Por Estado" y "Por Tipo Termino"** — muestran $0 sales en todos los buckets (lógica de agregación rota).

10. **Solo 3 estados clasificados** — "Negativa?", "Revisar", "—" (debería tener clases más granulares por el flujo de decisión).

## Test case para regresión

**Input**: `STR LTD MX 01/05-01/06` (Sponsored_Products_Search_term_report__50___2_.xlsx, 2,279 rows)

**Expected (post-fix)**:
- TODOS los match types procesados (AUTO + PT + BROAD + PHRASE + EXACT)
- NaN en 0 campos obligatorios
- 0 KWs simultáneas en Negative + Harvest
- 0 self-ASINs LTD en harvest
- Bids en rango razonable ($3-15 para LTD MX)
- 0 duplicados internos
- Hojas Por Estado/Tipo con sales reales agregadas
- Clases granulares (>3 estados)

## Datasets para test
- `tests/fixtures/STR_LTD_MX_2026-05.xlsx` (copiar de uploads sesión 02/06)
- ASINs LTD whitelist: ver `notes/brands/ltd/LTD.md` sección 🦸 Heroes oficiales

## Sesión fix planificada
2026-06-06 con Marcos (M27 origin) + Ramiro (technical collab)
