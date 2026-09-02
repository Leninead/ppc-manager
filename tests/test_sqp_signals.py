"""M3 SQP - deterministic signals feeding the AI layer (_compute_funnel_signals /
_compute_account_rollup and pure helpers).

Scope: ONLY the new additive functions consumed by the ai/agents/sqp agent.
Excluded: _compute_market_share, _compute_gaps and render() (pre-existing UI kept
intact by design - this file ALSO verifies the signals never mutate the input df).

Design rules:
- Anti-placebo rule: every expected value is hand-derived (calculator) over
  minimal synthetic fixtures, never copied from the code under test.
- No Streamlit runtime: pure functions called directly.
- pandas quantiles (linear interpolation): with n=5, q25 lands exactly on the
  2nd sorted value; with n=9, q90 = x7 + 0.2*(x8-x7). Fixtures are built so
  every percentile is unambiguous by hand.
- Reference spec: notes/modules/m3-sqp-ai-signals-spec.md.
"""
import numpy as np
import pandas as pd
import pytest

from modules.pages.search_query_performance import (
    _compute_account_rollup,
    _compute_funnel_signals,
    _norm_query,
    _price_band,
    _safe_div,
    _sqp_ai_rows,
    _SQP_FIELD_NAMES,
    _sqp_synthesis_for_display,
    _TOP_ROWS,
)


def _mk_df(rows):
    """Build a frame with the real SQP export column names from compact dicts.

    Keys per row: q, vol, it/ib (impressions), ct/cb (clicks), at/ab (cart adds),
    pt/pb (purchases), price_mkt/price_brand per stage (pc/pbc, pa/pba, pp/pbp),
    exp_imp_share (Amazon's own % column, optional).
    """
    cols = {
        "Search Query": [r["q"] for r in rows],
        "Search Query Volume": [r.get("vol", 100) for r in rows],
        "Impressions: Total Count": [r.get("it", 0) for r in rows],
        "Impressions: Brand Count": [r.get("ib", 0) for r in rows],
        "Clicks: Total Count": [r.get("ct", 0) for r in rows],
        "Clicks: Brand Count": [r.get("cb", 0) for r in rows],
        "Cart Adds: Total Count": [r.get("at", 0) for r in rows],
        "Cart Adds: Brand Count": [r.get("ab", 0) for r in rows],
        "Purchases: Total Count": [r.get("pt", 0) for r in rows],
        "Purchases: Brand Count": [r.get("pb", 0) for r in rows],
    }
    if any("pc" in r for r in rows):
        cols["Clicks: Price (Median)"] = [r.get("pc", np.nan) for r in rows]
        cols["Clicks: Brand Price (Median)"] = [r.get("pbc", np.nan) for r in rows]
    if any("pa" in r for r in rows):
        cols["Cart Adds: Price (Median)"] = [r.get("pa", np.nan) for r in rows]
        cols["Cart Adds: Brand Price (Median)"] = [r.get("pba", np.nan) for r in rows]
    if any("pp" in r for r in rows):
        cols["Purchases: Price (Median)"] = [r.get("pp", np.nan) for r in rows]
        cols["Purchases: Brand Price (Median)"] = [r.get("pbp", np.nan) for r in rows]
    if any("exp_imp_share" in r for r in rows):
        cols["Impressions: Brand Share %"] = [r.get("exp_imp_share", np.nan) for r in rows]
    return pd.DataFrame(cols)


def _signals(rows, brand_terms=None):
    df = _mk_df(rows)
    signals, th = _compute_funnel_signals(df, "Search Query", brand_terms or [])
    assert signals is not None
    return signals.set_index("query"), th


# pure helpers ──────────────────────────────────────────────────

class TestSafeDiv:
    def test_zero_denominator_is_nan_never_zero_nor_inf(self):
        out = _safe_div(pd.Series([10.0, 5.0]), pd.Series([0, 2]))
        assert np.isnan(out.iloc[0])
        assert out.iloc[1] == 2.5

    def test_nan_denominator_propagates_nan(self):
        out = _safe_div(pd.Series([10.0]), pd.Series([np.nan]))
        assert np.isnan(out.iloc[0])


class TestNormQuery:
    def test_strips_accents_case_and_spaces(self):
        assert _norm_query("  Dermaglós   CREMA ") == "dermaglos crema"


class TestPriceBandBoundaries:
    # Exact spec boundaries: (-inf,-15] / (-15,-5] / (-5,+5) / [+5,+25] / (+25,inf)
    @pytest.mark.parametrize("gap,band", [
        (-15.0, "DESCUENTO_AGRESIVO"),
        (-14.99, "VALUE"),
        (-5.0, "VALUE"),
        (-4.99, "PARIDAD"),
        (4.99, "PARIDAD"),
        (5.0, "PREMIUM_NO_VERIFICADO"),
        (25.0, "PREMIUM_NO_VERIFICADO"),
        (25.01, "PREMIUM_RIESGO"),
        (np.nan, "SIN_DATO_PRECIO"),
    ])
    def test_band(self, gap, band):
        assert _price_band(gap) == band


# shares and cascade ───────────────────────────────────────────────

class TestStageShares:
    def test_hand_derived_shares(self):
        # 50/200=25% - 20/80=25% - 8/40=20% - 1/20=5%
        signals, _ = _signals([dict(q="a", it=200, ib=50, ct=80, cb=20,
                                at=40, ab=8, pt=20, pb=1)])
        row = signals.loc["a"]
        assert (row["imp_share"], row["click_share"],
                row["cart_share"], row["purchase_share"]) == (25.0, 25.0, 20.0, 5.0)

    def test_zero_stage_total_gives_nan_share(self):
        signals, _ = _signals([dict(q="a", it=100, ib=10, ct=10, cb=2, at=0, ab=0,
                                pt=5, pb=0)])
        assert np.isnan(signals.loc["a", "cart_share"])

    def test_missing_columns_returns_none(self):
        df = pd.DataFrame({"Search Query": ["a"], "Otra Col": [1]})
        signals, th = _compute_funnel_signals(df, "Search Query", [])
        assert signals is None and th is None

    def test_input_df_not_mutated(self):
        df = _mk_df([dict(q="a", it=100, ib=10, ct=10, cb=2, pt=5, pb=1)])
        before = df.copy(deep=True)
        _compute_funnel_signals(df, "Search Query", ["a"])
        pd.testing.assert_frame_equal(df, before)


class TestCascadeLeak:
    # File d2 values: [+5, +2, 0, -1, -10] -> sorted [-10,-1,0,2,5], q25 = -1.
    # Material requires d2 < 0 AND d2 < -1: only the -10 row. No negative d1/d3.
    def _rows(self):
        base = dict(it=1000, ib=100, ct=100, cb=10)  # imp/click share 10 parejo
        return [
            dict(q="r1", **base, at=100, ab=15, pt=100, pb=15),   # d2 +5
            dict(q="r2", **base, at=100, ab=12, pt=100, pb=12),   # d2 +2
            dict(q="r3", **base, at=100, ab=10, pt=100, pb=10),   # d2 0
            dict(q="r4", **base, at=100, ab=9, pt=100, pb=9),     # d2 -1 == q25
            dict(q="r5", it=1000, ib=200, ct=100, cb=25,
                 at=100, ab=15, pt=10, pb=2),                     # d1 +5, d2 -10, d3 +5
        ]

    def test_deltas_hand_derived(self):
        signals, th = _signals(self._rows())
        assert signals.loc["r5", "d1"] == 5.0
        assert signals.loc["r5", "d2"] == -10.0
        assert signals.loc["r5", "d3"] == 5.0
        assert th["p25_d2"] == -1.0

    def test_leak_is_first_material_stage_only(self):
        signals, _ = _signals(self._rows())
        assert signals.loc["r5", "leak_stage"] == "pdp"
        assert signals.loc["r4", "leak_stage"] == ""  # exactly at q25 is not material
        assert (signals.loc[["r1", "r2", "r3"], "leak_stage"] == "").all()


class TestBrandVsMarketIndices:
    def test_ctr_index_excludes_brand_from_market(self):
        # brand ctr 300/900=0.3333; market without brand (500-300)/(1000-900)=2.0
        signals, _ = _signals([dict(q="a", it=1000, ib=900, ct=500, cb=300,
                                at=100, ab=60, pt=50, pb=30)])
        assert signals.loc["a", "ctr_index"] == pytest.approx(0.17, abs=0.005)

    def test_index_nan_when_market_side_is_zero(self):
        # it == ib: the market-minus-brand has no impressions -> NaN, never 0/inf
        signals, _ = _signals([dict(q="a", it=500, ib=500, ct=100, cb=50,
                                at=20, ab=10, pt=10, pb=5)])
        assert np.isnan(signals.loc["a", "ctr_index"])


# price ─────────────────────────────────────────────────────────

class TestPriceSignals:
    def test_gap_hand_derived_and_band(self):
        # (12-10)/10*100 = +20 -> PREMIUM_NO_VERIFICADO
        signals, _ = _signals([dict(q="a", it=100, ib=10, ct=10, cb=2, pt=5, pb=1,
                                pp=10.0, pbp=12.0)])
        assert signals.loc["a", "gap_purchase"] == 20.0
        assert signals.loc["a", "price_band"] == "PREMIUM_NO_VERIFICADO"

    def test_band_falls_back_to_click_gap(self):
        # no purchase price, band falls back to gap_click: (8-10)/10 = -20
        signals, _ = _signals([dict(q="a", it=100, ib=10, ct=10, cb=2, pt=5, pb=1,
                                pc=10.0, pbc=8.0, pp=np.nan, pbp=np.nan)])
        assert signals.loc["a", "gap_click"] == -20.0
        assert signals.loc["a", "price_band"] == "DESCUENTO_AGRESIVO"

    def test_autodilution_flag_boundary(self):
        rows = [dict(q="hi", it=100, ib=50, ct=100, cb=50, pt=100, pb=41),
                dict(q="lo", it=100, ib=50, ct=100, cb=50, pt=100, pb=40)]
        signals, _ = _signals(rows)
        assert bool(signals.loc["hi", "price_self_diluted"]) is True   # 41% > 40
        assert bool(signals.loc["lo", "price_self_diluted"]) is False  # 40% == 40


# gate, invisibility, gems, defense ────────────────────────────

class TestLowDataGate:
    @pytest.mark.parametrize("cb,pt,expected", [
        (10, 5, True), (9, 5, False), (10, 4, False), (9, 4, False),
    ])
    def test_gate_boundaries(self, cb, pt, expected):
        signals, _ = _signals([dict(q="a", it=1000, ib=100, ct=100, cb=cb,
                                pt=pt, pb=1)])
        assert bool(signals.loc["a", "sufficient_data"]) is expected


class TestEsInvisible:
    def test_zero_brand_impressions_is_invisible(self):
        signals, _ = _signals([dict(q="a", it=5000, ib=0, pt=40, pb=0)])
        assert bool(signals.loc["a", "is_invisible"]) is True

    def test_sub_one_percent_share_without_own_purchases_is_invisible(self):
        # 9/1000 = 0.9% with pb=1 (< 2) -> invisible
        signals, _ = _signals([dict(q="a", it=1000, ib=9, ct=100, cb=1, pt=50, pb=1)])
        assert bool(signals.loc["a", "is_invisible"]) is True

    def test_own_purchases_rescue_visibility(self):
        signals, _ = _signals([dict(q="a", it=1000, ib=9, ct=100, cb=5, pt=50, pb=2)])
        assert bool(signals.loc["a", "is_invisible"]) is False

    def test_share_at_or_above_one_percent_is_visible(self):
        signals, _ = _signals([dict(q="a", it=1000, ib=12, ct=100, cb=1, pt=50, pb=0)])
        assert bool(signals.loc["a", "is_invisible"]) is False


class TestHiddenGem:
    def _rows(self):
        # imp shares: [0.5, 10, 20, 30, 40, 50, 60, 70, 80] -> q25 = x2 = 20.
        rows = [dict(q="gem", it=10000, ib=50, ct=500, cb=20, at=100, ab=10,
                     pt=1000, pb=10)]          # 0.5% imp, 1.0% pur (>= 1.3*0.5)
        rows.append(dict(q="thin", it=1000, ib=100, ct=100, cb=20, at=50, ab=5,
                         pt=100, pb=5))        # 10% imp, 5% pur: falla ratio
        for i, share in enumerate([20, 30, 40, 50, 60, 70, 80]):
            rows.append(dict(q=f"f{i}", it=1000, ib=share * 10, ct=100, cb=20,
                             at=50, ab=10, pt=100, pb=10))
        return rows

    def test_gem_detected_and_ratio_counterexample(self):
        signals, th = _signals(self._rows())
        assert th["p25_imp_share"] == 20.0
        assert bool(signals.loc["gem", "hidden_gem"]) is True
        assert bool(signals.loc["thin", "hidden_gem"]) is False

    def test_gem_needs_min_own_purchases(self):
        rows = self._rows()
        rows[0]["pb"] = 1  # purchase share still >= 1.3*imp_share, but pb < 2
        signals, _ = _signals(rows)
        assert bool(signals.loc["gem", "hidden_gem"]) is False

    def test_gem_is_never_invisible(self):
        signals, _ = _signals(self._rows())
        assert bool(signals.loc["gem", "is_invisible"]) is False


class TestDefenseBreach:
    def test_first_stage_below_floor_with_share(self):
        # imp 90 (ok) -> clicks 60 (< 80): breach at clicks with share 60
        signals, _ = _signals([dict(q="alpha cream", it=1000, ib=900, ct=500, cb=300,
                                at=100, ab=60, pt=50, pb=30)],
                          brand_terms=["alpha"])
        assert signals.loc["alpha cream", "defense_breach_stage"] == "clicks"
        assert signals.loc["alpha cream", "defense_breach_share"] == 60.0

    def test_non_brand_rows_never_breach(self):
        signals, _ = _signals([dict(q="generic soap", it=1000, ib=10, ct=100, cb=1,
                                pt=50, pb=0)], brand_terms=["alpha"])
        assert signals.loc["generic soap", "defense_breach_stage"] == ""

    def test_brand_match_ignores_accents_and_case(self):
        signals, _ = _signals([dict(q="ALPHA jabón", it=100, ib=90, ct=10, cb=9,
                                at=5, ab=5, pt=5, pb=5)],
                          brand_terms=["álpha"])
        assert bool(signals.loc["ALPHA jabón", "is_own_brand"]) is True


# tier, opportunity, priority ───────────────────────────────────

class TestVolumeTier:
    def test_tiers_hand_derived(self):
        # vols 10..90: q90 = 80 + 0.2*(90-80) = 82 -> HEAD only 90; q50 = 50.
        rows = [dict(q=f"v{v}", vol=v, it=100, ib=10, pt=10, pb=1)
                for v in range(10, 100, 10)]
        signals, th = _signals(rows)
        assert th["vol_q90"] == 82.0 and th["vol_q50"] == 50.0
        assert signals.loc["v90", "volume_tier"] == "HEAD"
        assert signals.loc["v50", "volume_tier"] == "TORSO"
        assert signals.loc["v40", "volume_tier"] == "LONG_TAIL"


class TestRevenueOpportunity:
    def test_branded_target_hand_derived(self):
        # BRANDED target 80: (80-60)/100 * 50 purchases * $20 = $200
        signals, _ = _signals([dict(q="alpha soap", vol=100, it=1000, ib=900,
                                ct=500, cb=300, at=100, ab=60, pt=50, pb=30,
                                pp=20.0, pbp=20.0)],
                          brand_terms=["alpha"])
        assert signals.loc["alpha soap", "opp_usd"] == 200.0

    def test_generic_head_target_hand_derived(self):
        # single row -> its vol is q90 -> HEAD, target 10: 0.10 * 40 * $10 = $40
        signals, _ = _signals([dict(q="water jug", vol=500, it=5000, ib=0,
                                pt=40, pb=0, pp=10.0, pbp=np.nan)])
        assert signals.loc["water jug", "opp_usd"] == 40.0

    def test_opportunity_zero_without_market_price(self):
        signals, _ = _signals([dict(q="a", vol=500, it=5000, ib=0, pt=40, pb=0)])
        assert signals.loc["a", "opp_usd"] == 0.0

    def test_sorted_by_priority_desc(self):
        rows = [dict(q="big", vol=1000, it=5000, ib=0, pt=100, pb=0, pp=30.0),
                dict(q="small", vol=10, it=500, ib=0, pt=5, pb=0, pp=1.0)]
        df = _mk_df(rows)
        signals, _ = _compute_funnel_signals(df, "Search Query", [])
        assert signals.iloc[0]["query"] == "big"


# integrity ─────────────────────────────────────────────────────

class TestIntegrityOracle:
    def test_divergent_export_share_flags_row(self):
        rows = [dict(q="bad", it=200, ib=50, pt=10, pb=1, exp_imp_share=50.0),
                dict(q="good", it=200, ib=50, pt=10, pb=1, exp_imp_share=25.0)]
        signals, _ = _signals(rows)
        assert bool(signals.loc["bad", "integrity_ok"]) is False   # 25 vs 50
        assert bool(signals.loc["good", "integrity_ok"]) is True

    def test_rounding_within_tolerance_passes(self):
        # 1/3 = 33.333..%; export says 33.33 -> diff < 0.6 pts
        signals, _ = _signals([dict(q="a", it=3, ib=1, pt=10, pb=1,
                                exp_imp_share=33.33)])
        assert bool(signals.loc["a", "integrity_ok"]) is True


# rollup ─────────────────────────────────────────────────────────

def _rollup(rows, brand_terms=None):
    df = _mk_df(rows)
    signals, th = _compute_funnel_signals(df, "Search Query", brand_terms or [])
    return _compute_account_rollup(signals, th), signals


class TestAccountRollup:
    def test_weighted_shares_hand_derived(self):
        # (10+50)/(100+300) = 15%
        r, _ = _rollup([dict(q="a", it=100, ib=10, pt=10, pb=2),
                        dict(q="b", it=300, ib=50, pt=10, pb=2)])
        assert r["weighted_shares"]["imp"] == 15.0

    def test_coverage_measured_only_on_visible_rows(self):
        # 1 visible passing the gate + 1 visible failing it + 2 invisible -> 50%
        rows = [dict(q="ok", it=1000, ib=500, ct=100, cb=50, pt=100, pb=10),
                dict(q="thin", it=1000, ib=500, ct=100, cb=3, pt=100, pb=10),
                dict(q="inv1", it=1000, ib=0, pt=50, pb=0),
                dict(q="inv2", it=1000, ib=0, pt=50, pb=0)]
        r, _ = _rollup(rows)
        assert r["pct_rows_with_data"] == 50.0
        assert r["pct_invisible"] == 50.0

    def test_volumen_sin_visibilidad_preflag(self):
        # invisible opp $40 over ~$45 total -> > 25%
        rows = [dict(q="inv", vol=900, it=5000, ib=0, pt=40, pb=0, pp=10.0),
                dict(q="vis", vol=10, it=100, ib=50, ct=50, cb=20, at=20, ab=10,
                     pt=20, pb=10, pp=1.0, pbp=1.0)]
        r, _ = _rollup(rows)
        assert r["pre_flags"]["VOLUMEN_SIN_VISIBILIDAD"] is True

    def test_defensa_rota_preflag_and_queries(self):
        r, _ = _rollup([dict(q="alpha cream", it=1000, ib=900, ct=500, cb=300,
                             at=100, ab=60, pt=50, pb=30)],
                       brand_terms=["alpha"])
        assert r["pre_flags"]["DEFENSA_MARCA_ROTA"] is True
        assert r["defense_broken"]["queries"] == ["alpha cream"]

    def test_premium_cluster_requires_gate(self):
        # 3 PREMIUM_RIESGO rows with a pdp leak but WITHOUT the gate -> flag false
        def leaky(i, cb):
            return dict(q=f"p{i}", it=1000, ib=500, ct=100, cb=cb, at=100,
                        ab=5, pt=100, pb=2, pp=10.0, pbp=15.0)
        rows = [leaky(i, cb=3) for i in range(3)]
        rows.append(dict(q="anchor", it=1000, ib=500, ct=100, cb=50, at=100,
                         ab=50, pt=100, pb=50))
        r, _ = _rollup(rows)
        assert r["pre_flags"]["CLUSTER_PREMIUM_RIESGO"] is False

    def test_tail_aggregates_beyond_top_rows(self):
        rows = [dict(q=f"q{i}", vol=1000 - i, it=100, ib=50, ct=10, cb=5,
                     pt=10, pb=2) for i in range(_TOP_ROWS + 3)]
        r, _ = _rollup(rows)
        assert r["tail"]["rows"] == 3

    def test_preflag_keys_are_stable(self):
        r, _ = _rollup([dict(q="a", it=100, ib=10, pt=10, pb=1)])
        assert set(r["pre_flags"]) == {
            "DEFENSA_MARCA_ROTA", "GEMAS_OCULTAS", "FUGA_CHECKOUT_HEAD_TERM",
            "CLUSTER_PREMIUM_RIESGO", "VOLUMEN_SIN_VISIBILIDAD",
            "COBERTURA_BAJA", "SIN_DATO_PRECIO_MASIVO", "INTEGRIDAD_EXPORT",
        }


# display rows ──────────────────────────────────────────────────
# The row builder joins AI opinions back to the payload records positionally;
# a wrong join here puts an opinion under the wrong query on screen.

class TestSqpFieldNames:
    """The AI prose must never show the CSV column names to the AM: the
    glossary covers every signal column in both languages and the display
    path rewrites leaks deterministically."""

    @pytest.mark.parametrize("lang", ["es", "en"])
    def test_glossary_covers_every_signal_column(self, lang):
        from ai.agents.sqp.context import _ROW_COLS
        # "volume" is an ordinary word inside query texts: never rewritten.
        missing = [c for c in _ROW_COLS if c not in ("query", "volume")
                   and not _SQP_FIELD_NAMES[lang].get(c)]
        assert missing == []
        assert "volume" not in _SQP_FIELD_NAMES[lang]
        # A human name must never be another column name (would re-leak).
        assert not set(_SQP_FIELD_NAMES[lang].values()) & set(_ROW_COLS)

    def test_rows_rewrite_leaked_names_in_reasoning_and_warning(self):
        records = [{"query": "brita jug", "imp_share": 0.0, "click_share": 0.0,
                    "cart_share": 0.0, "purchase_share": 0.0,
                    "opp_usd": 23797.2}]
        opinions = [{"row_id": "Q01", "reasoning": "El mercado mueve pur_t "
                     "1753 y imp_b 21 sobre imp_t 2493569 marcan is_invisible.",
                     "warning": "opp_usd alto con clk_b 3.",
                     "funnel_diagnosis": "SIN_VISIBILIDAD",
                     "action": "AGREGAR_EXACT", "confidence": "ALTA"}]
        row = _sqp_ai_rows(records, opinions, _SQP_FIELD_NAMES["es"])[0]
        assert row["reasoning"] == ("El mercado mueve compras del mercado 1753 "
                                    "y impresiones de la marca 21 sobre "
                                    "impresiones del mercado 2493569 marcan "
                                    "marca sin visibilidad.")
        assert row["warning"] == "oportunidad alto con clics de la marca 3."
        # Without a glossary the rows are untouched (legacy callers).
        raw = _sqp_ai_rows(records, opinions)[0]
        assert "pur_t" in raw["reasoning"]

    def test_synthesis_prose_fields_are_rewritten_and_structure_kept(self):
        synth = {"situation": "imp_share 0.0 ponderado.",
                 "week_actions": ["Abrir Q01 (opp_usd 23797.2, pur_t 8400)."],
                 "mid_term": ["Re-chequear hidden_gem Q04."],
                 "risks": [{"type": "DEFENSA_MARCA_ROTA", "urgency": "ALTA",
                            "detail": "defense_breach_share 61.0 en 11 filas"}],
                 "executive_summary": "pur_t 1753; opp_usd $23,797.20."}
        out = _sqp_synthesis_for_display(synth, _SQP_FIELD_NAMES["es"],
                                         {"Q01": "brita jug"})
        assert out["situation"] == "share de impresiones 0.0 ponderado."
        assert out["week_actions"] == [
            "Abrir Q01 (brita jug) (oportunidad 23797.2, compras del mercado 8400)."]
        assert out["mid_term"] == ["Re-chequear gema oculta Q04."]
        assert out["risks"][0]["type"] == "DEFENSA_MARCA_ROTA"
        assert out["risks"][0]["detail"] == \
            "share con la defensa rota 61.0 en 11 filas"
        assert out["executive_summary"] == \
            "compras del mercado 1753; oportunidad $23,797.20."
        assert synth["situation"].startswith("imp_share")  # input untouched
        bare = _sqp_synthesis_for_display(synth, None, {})
        assert bare["situation"] == synth["situation"]


class TestSqpAiRows:
    _RECORDS = [
        {"query": "brita jug", "imp_share": 1.0, "click_share": 2.0,
         "cart_share": float("nan"), "purchase_share": 0.0, "opp_usd": 23797.2},
        {"query": "water filter", "imp_share": 0.5, "click_share": 0.1,
         "cart_share": 0.2, "purchase_share": 0.0, "opp_usd": 100.0},
    ]

    def test_positional_join_and_row_contract(self):
        opinions = [{"row_id": "Q02", "query_type": "GENERICA",
                     "funnel_diagnosis": "SIN_VISIBILIDAD",
                     "action": "AGREGAR_EXACT", "confidence": "ALTA",
                     "warning": None, "reasoning": "r2"}]
        rows = _sqp_ai_rows(self._RECORDS, opinions)
        assert [r["row_id"] for r in rows] == ["Q01", "Q02"]
        assert rows[0]["item"] == "brita jug" and rows[0]["reasoning"] == ""
        assert rows[1]["item"] == "water filter"
        assert rows[1]["badges"] == ["SIN_VISIBILIDAD", "AGREGAR_EXACT"]
        assert rows[1]["reasoning"] == "r2"

    def test_nan_share_renders_dash_and_opp_formats(self):
        rows = _sqp_ai_rows(self._RECORDS, [])
        assert "cart —" in rows[0]["metrics"]
        assert "opp $23,797" in rows[0]["metrics"][-1]

    def test_invented_row_ids_are_ignored(self):
        opinions = [{"row_id": "Q99", "reasoning": "ghost"}]
        rows = _sqp_ai_rows(self._RECORDS, opinions)
        assert all(r["reasoning"] == "" for r in rows)


def test_row_labels_map_positional_ids_to_queries():
    from modules.pages.search_query_performance import _sqp_row_labels
    records = [{"query": "brita jug"}, {"query": "water filter"}]
    assert _sqp_row_labels(records) == {"Q01": "brita jug",
                                        "Q02": "water filter"}
    assert _sqp_row_labels([]) == {}


def test_sqp_result_renders_glossary_ids_and_headings():
    """The visible output: leaked column names rewritten, ids ahead of the
    queries and annotated in the actions, the synthesis headings present."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st
from core import ai_tab
from modules.pages.search_query_performance import _render_sqp_ai_result, _SQP_LABELS

class A:
    elapsed = 9

records = [{"query": "brita jug", "imp_share": 1.0, "click_share": 2.0,
            "cart_share": 0.5, "purchase_share": 0.0, "opp_usd": 23797.2}]
result = {"queries": [{"row_id": "Q01", "reasoning": "pur_t 1753 sin imp_b",
                       "query_type": "GENERICA", "funnel_diagnosis": "SIN_VISIBILIDAD",
                       "price_causality": "INDETERMINADO", "action": "AGREGAR_EXACT",
                       "confidence": "ALTA", "warning": None}],
          "synthesis": {"situation": "imp_share 0.0 ponderado.",
                        "week_actions": ["Abrir Q01 ya"], "mid_term": [],
                        "risks": [], "executive_summary": "e"}}
labels = ai_tab.ai_labels("es", _SQP_LABELS["es"])
_render_sqp_ai_result(result, A(), records, labels)
'''
    at = AppTest.from_string(script)
    at.run(timeout=30)
    assert not at.exception
    html = " ".join(str(m.value) for m in at.markdown)
    assert "compras del mercado 1753 sin impresiones de la marca" in html
    assert "share de impresiones 0.0 ponderado" in html
    assert "Abrir Q01 (brita jug) ya" in html
    assert html.index("Q01") < html.index("brita jug")
    assert "ACCIONES SUGERIDAS PARA ESTA SEMANA" in html.upper()
    assert "pur_t" not in html and "imp_share" not in html


class TestSignalsBehindTheVerdict:
    """The columns the prompt anchors its diagnosis on (leak_is_own, indices,
    market_buys, share_state, price gaps and drift), hand-derived."""

    def test_own_leak_index_and_market_buys_on_the_cascade_fixture(self):
        signals, _ = _signals(TestCascadeLeak()._rows())
        # r5 leaks at pdp: cart_index = (15/25) / ((100-15)/(100-25)) = 0.6/1.1333 = 0.53
        assert signals.loc["r5", "cart_index"] == pytest.approx(0.53, abs=0.005)
        assert bool(signals.loc["r5", "leak_is_own"]) is True
        assert bool(signals.loc["r1", "leak_is_own"]) is False  # no leak at all
        # positive market purchases [100,100,100,100,10] -> median 100
        assert bool(signals.loc["r1", "market_buys"]) is True
        assert bool(signals.loc["r5", "market_buys"]) is False

    def test_share_state_thresholds(self):
        # 35% > 30 -> dominando; 10% -> competitivo (>=10); 5% -> oportunidad
        signals, _ = _signals([
            dict(q="dom", it=1000, ib=350, ct=100, cb=35, pt=10, pb=3),
            dict(q="comp", it=1000, ib=100, ct=100, cb=10, pt=10, pb=1),
            dict(q="opp", it=1000, ib=50, ct=100, cb=5, pt=10, pb=1),
        ])
        assert signals.loc["dom", "share_state"] == "dominando"
        assert signals.loc["comp", "share_state"] == "competitivo"
        assert signals.loc["opp", "share_state"] == "oportunidad"

    def test_price_gap_is_brand_against_market_and_drift_is_purchase_minus_click(self):
        # click: (11-10)/10 = +10.0 ; purchase: (13-10)/10 = +30.0 ; drift = 20.0
        signals, _ = _signals([dict(q="a", it=1000, ib=100, ct=100, cb=20,
                                    at=50, ab=10, pt=20, pb=5,
                                    pc=10.0, pbc=11.0, pa=10.0, pba=12.0,
                                    pp=10.0, pbp=13.0)])
        row = signals.loc["a"]
        assert row["gap_click"] == pytest.approx(10.0)
        assert row["gap_purchase"] == pytest.approx(30.0)
        assert row["price_trend"] == pytest.approx(20.0)
        assert row["price_band"] == "PREMIUM_RIESGO"  # gap_purchase 30 > 25

    def test_gate_and_gem(self):
        # imp shares 1/5/10/20 -> pandas q25 = 1 + 0.75*(5-1) = 4.0: only "gem" is below
        signals, _ = _signals([
            dict(q="gem", it=1000, ib=10, ct=100, cb=10, at=40, ab=15, pt=50, pb=10),
            dict(q="b", it=1000, ib=50, ct=100, cb=15, at=40, ab=6, pt=10, pb=1),
            dict(q="thin", it=1000, ib=100, ct=100, cb=5, at=40, ab=5, pt=10, pb=1),
            dict(q="d", it=1000, ib=200, ct=100, cb=3, at=40, ab=3, pt=10, pb=1),
        ])
        # gem: purchase share 20 >= 1.3*1.0, imp 1.0 < 4.0, pur_b 10 >= 2, gate ok
        assert bool(signals.loc["gem", "hidden_gem"]) is True
        # b: purchase 10 >= 1.3*5 but imp 5.0 is not below the file's q25 (4.0)
        assert bool(signals.loc["b", "hidden_gem"]) is False
        assert bool(signals.loc["thin", "sufficient_data"]) is False  # 5 brand clicks
        assert bool(signals.loc["gem", "sufficient_data"]) is True
        assert bool(signals.loc["gem", "is_invisible"]) is False  # 1.0% is not < 1.0

    def test_invisibility(self):
        signals, _ = _signals([
            dict(q="ghost", it=1000, ib=0, ct=100, cb=0, at=40, ab=0, pt=20, pb=0),
            dict(q="faint", it=10000, ib=50, ct=100, cb=2, at=10, ab=1, pt=5, pb=1),
            dict(q="seen", it=1000, ib=10, ct=100, cb=10, at=40, ab=15, pt=50, pb=10),
        ])
        assert bool(signals.loc["ghost", "is_invisible"]) is True   # imp_b == 0
        assert bool(signals.loc["faint", "is_invisible"]) is True   # 0.5% and 1 purchase
        assert bool(signals.loc["seen", "is_invisible"]) is False   # 1.0% is not < 1.0


class TestRollupPreFlags:
    """Each risk pre-flag asserted TRUE and FALSE on fixtures whose
    percentages are hand-derived."""

    def _rollup(self, rows):
        df = _mk_df(rows)
        signals, th = _compute_funnel_signals(df, "Search Query", [])
        return _compute_account_rollup(signals, th), signals

    def test_gems_and_low_coverage(self):
        gem_rows = [
            dict(q="gem", it=1000, ib=10, ct=100, cb=10, at=40, ab=15, pt=50, pb=10),
            dict(q="b", it=1000, ib=50, ct=100, cb=15, at=40, ab=6, pt=10, pb=1),
            dict(q="c", it=1000, ib=100, ct=100, cb=5, at=40, ab=5, pt=10, pb=1),
            dict(q="d", it=1000, ib=200, ct=100, cb=3, at=40, ab=3, pt=10, pb=1),
        ]
        rollup, signals = self._rollup(gem_rows)
        assert rollup["pre_flags"]["GEMAS_OCULTAS"] is True
        assert rollup["gems"] == {"rows": 1, "top_queries": ["gem"]}
        # brand present in all 4; gate passes for gem and b -> 2/4 = 50.0, not < 50
        assert rollup["pct_rows_with_data"] == 50.0
        assert rollup["pre_flags"]["COBERTURA_BAJA"] is False
        gem_rows[1] = dict(q="b", it=1000, ib=50, ct=100, cb=5, at=40, ab=5, pt=10, pb=1)
        rollup, _ = self._rollup(gem_rows)  # now 1/4 = 25.0 -> low coverage
        assert rollup["pct_rows_with_data"] == 25.0
        assert rollup["pre_flags"]["COBERTURA_BAJA"] is True
        assert rollup["pre_flags"]["GEMAS_OCULTAS"] is True

    def test_no_price_data_and_export_integrity(self):
        base = [dict(q=f"q{i}", it=1000, ib=100 * (i + 1), ct=100, cb=20,
                     at=40, ab=8, pt=20, pb=4) for i in range(4)]
        rollup, _ = self._rollup(base)  # no price columns at all
        assert rollup["pct_no_price_data"] == 100.0
        assert rollup["pre_flags"]["SIN_DATO_PRECIO_MASIVO"] is True
        priced = [dict(r, pc=10.0, pbc=10.0, pp=10.0, pbp=10.0) for r in base]
        rollup, _ = self._rollup(priced)
        assert rollup["pct_no_price_data"] == 0.0
        assert rollup["pre_flags"]["SIN_DATO_PRECIO_MASIVO"] is False
        # Amazon's own share column agrees on 3 rows and is 5 pts off on one
        audited = [dict(r, exp_imp_share=10.0 * (i + 1)) for i, r in enumerate(base)]
        audited[2]["exp_imp_share"] = 35.0  # computed 30.0 -> off by 5 > 0.6 tolerance
        rollup, signals = self._rollup(audited)
        assert rollup["pct_integrity_ok"] == 75.0
        assert rollup["pre_flags"]["INTEGRIDAD_EXPORT"] is True  # 25% > 2
        assert bool(signals.set_index("query").loc["q2", "integrity_ok"]) is False

    def test_dominant_leak_stage_comes_from_gated_rows(self):
        rollup, _ = self._rollup(TestCascadeLeak()._rows())
        assert rollup["dominant_leak_stage"] == "pdp"
