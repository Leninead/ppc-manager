"""Characterization tests para M30 F3.3 — scoring engine + orchestrator.

Port verbatim del HTML (.claude/porting-sources/pricing-dashboard.html):
    computeAIS    (L934-940)  -> _compute_ais
    computeScore  (L998-1155) -> _compute_score
    enrichRecord  (L925)      -> _enrich_record
    runAnalysis   (L800-924)  -> _run_analysis

Estos tests CONGELAN el comportamiento verbatim (incluida la asimetría de umbrales
y el bug 30-vs-37). NO son specs de "lo correcto": son specs de "lo que hace el HTML".
"""

import pytest

from modules.pages.pricing_dashboard import _compute_ais


# =====================================================================
# B5 — _compute_ais (Aged Inventory Surcharge, 8 buckets)
# =====================================================================
_AIS_KEYS = [
    "estimated-ais-181-210-days",
    "estimated-ais-211-240-days",
    "estimated-ais-241-270-days",
    "estimated-ais-271-300-days",
    "estimated-ais-301-330-days",
    "estimated-ais-331-365-days",
    "estimated-ais-366-455-days",
    "estimated-ais-456-plus-days",
]


class TestComputeAis:
    def test_suma_de_los_8_buckets(self):
        rec = {k: float(i + 1) for i, k in enumerate(_AIS_KEYS)}  # 1..8
        assert _compute_ais(rec) == 36.0  # 1+2+...+8

    def test_suma_valores_mixtos(self):
        rec = dict.fromkeys(_AIS_KEYS, 0)
        rec[_AIS_KEYS[0]] = 12.5
        rec[_AIS_KEYS[7]] = 7.5
        assert _compute_ais(rec) == 20.0

    def test_buckets_ausentes_son_cero(self):
        # solo 2 de los 8 presentes; el resto ausente -> 0 (parseFloat(r[c]||0)||0)
        rec = {_AIS_KEYS[2]: 10, _AIS_KEYS[5]: 5}
        assert _compute_ais(rec) == 15.0

    def test_buckets_none_son_cero(self):
        rec = dict.fromkeys(_AIS_KEYS, None)
        rec[_AIS_KEYS[0]] = 9
        assert _compute_ais(rec) == 9.0

    def test_todos_en_cero(self):
        rec = dict.fromkeys(_AIS_KEYS, 0)
        assert _compute_ais(rec) == 0.0

    def test_record_vacio(self):
        assert _compute_ais({}) == 0.0
