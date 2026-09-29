"""INV-11's marks on the Amazon Ads search terms Análisis Cruzado reads. No network."""
import pandas as pd

from core.cross_analysis.ranking_guards import (
    ALREADY_EXACT,
    NOT_NEGATABLE,
    ORIGIN,
    RANKING_KEYWORD,
    exact_marks,
    with_ranking_guards,
)
from tests.cross_analysis_data import search_terms, term_row


def _marks(*rows, exact=frozenset()):
    guarded = with_ranking_guards(search_terms(*rows), exact)
    return {term: (origin, not_negatable) for term, origin, not_negatable in
            zip(guarded["Customer Search Term"], guarded[ORIGIN], guarded[NOT_NEGATABLE])}


def test_exact_keywords_and_product_targets_are_not_negatable_but_auto_terms_are():
    marks = _marks(term_row("from exact", keyword_type="EXACT"), term_row("from phrase", keyword_type="PHRASE"),
                   term_row("from broad", keyword_type="BROAD"),
                   term_row("b0rival0001", keyword_type="TARGETING_EXPRESSION", keyword_text='asin="B0RIVAL0001"'),
                   term_row("from auto", keyword_type="TARGETING_EXPRESSION_PREDEFINED",
                            keyword_text="close-match"))

    assert marks == {"from exact": ("Exact", True), "from phrase": ("Phrase", False),
                     "from broad": ("Broad", False), "b0rival0001": ("Product Targeting", True),
                     "from auto": ("Auto", False)}


def test_ranking_and_unnamed_portfolios_are_protected():
    guarded = with_ranking_guards(search_terms(
        term_row("in ranking", portfolio="Ranking - Core", portfolio_id="9"),
        term_row("in unnamed", campaign_id="3002", portfolio="", portfolio_id="10"),
        term_row("in discovery", campaign_id="3003", portfolio="Discovery", portfolio_id="11"),
        term_row("without portfolio", campaign_id="3004"),
    ), frozenset())

    assert dict(zip(guarded["Customer Search Term"], guarded[RANKING_KEYWORD])) == {
        "in ranking": True, "in unnamed": True, "in discovery": False, "without portfolio": False}


def test_the_exact_mark_reads_the_term_against_the_accounts_enabled_exact_keywords():
    guarded = with_ranking_guards(search_terms(term_row("luna  Pajamas"), term_row("sleep sack", campaign_id="3002")),
                                  frozenset({"luna pajamas"}))

    assert dict(zip(guarded["Customer Search Term"], guarded[ALREADY_EXACT])) == {"luna  Pajamas": True,
                                                                                  "sleep sack": False}


def test_without_a_listing_the_exact_mark_is_unknown_never_false():
    marks = exact_marks(pd.Series(["luna pajamas", "sleep sack"]), None)

    assert marks.isna().all()
    assert str(marks.dtype) == "boolean"


def test_the_marks_leave_the_search_terms_untouched():
    frame = search_terms(term_row("luna pajamas"))

    with_ranking_guards(frame, frozenset())

    assert ALREADY_EXACT not in frame.columns
