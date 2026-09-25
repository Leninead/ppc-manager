"""SBH Recommendation's target rules, moved out of the page unchanged: shares, priority, clusters and headlines."""
import pandas as pd
import pytest

from core.sbh.targets import (
    CLUSTER_COLUMNS,
    NO,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    TARGET_COLUMNS,
    UNKNOWN,
    YES,
    QueryShare,
    SqpFormatError,
    query_shares,
    recommend_targets,
    root_words,
)


def _mkl(*rows) -> pd.DataFrame:
    """rows: (term, sv) or (term, sv, relevance, launch score)."""
    records = []
    for row in rows:
        term, sv, relevance, launch = (*row, 3.0, 10.0) if len(row) == 2 else row
        records.append({"Search Term": term, "SV": sv, "Relevance": relevance, "Sugg. Bid": 1.0,
                        "Launch Score": launch})
    return pd.DataFrame(records)


def _share(impression_share=0.0, purchases=10) -> QueryShare:
    return QueryShare(impression_share=impression_share, purchase_share=0.0, total_impressions=1000,
                      total_purchases=purchases)


def _priority(term="vitamin a cream", *, sv, share=None, in_sp=frozenset()):
    targets = recommend_targets(_mkl((term, sv)), {term: share} if share else {}, in_sp)
    return targets.keywords["Prioridad"].iloc[0] if not targets.keywords.empty else None


def test_query_shares_are_the_brand_share_of_each_query_rounded_to_one_decimal():
    sqp = pd.DataFrame({"Search Query": ["  Vitamin A Cream ", "retinol"],
                        "Impressions: Total Count": [3000, 0], "Impressions: Brand Count": [100, 0],
                        "Purchases: Total Count": [30, 0], "Purchases: Brand Count": [1, 0],
                        "Reporting Date": ["2026-09-20", "2026-09-20"]})

    shares = query_shares(sqp)

    assert shares["vitamin a cream"] == QueryShare(impression_share=3.3, purchase_share=3.3, total_impressions=3000,
                                                   total_purchases=30)
    assert shares["retinol"] == QueryShare(0, 0, 0, 0)


def test_counts_that_are_not_numbers_count_as_zero():
    sqp = pd.DataFrame({"Search Query": ["x"], "Impressions: Total Count": ["n/a"],
                        "Impressions: Brand Count": ["5"], "Purchases: Total Count": [""],
                        "Purchases: Brand Count": ["1"]})

    assert query_shares(sqp)["x"] == QueryShare(0, 0, 0, 0)


def test_an_sqp_without_a_search_query_column_is_a_format_error():
    with pytest.raises(SqpFormatError, match="Search Query"):
        query_shares(pd.DataFrame({"Query": ["x"], "Impressions: Total Count": [1]}))


@pytest.mark.parametrize(("sv", "share", "in_sp", "expected"), [
    (1000, _share(9.9), frozenset(), PRIORITY_HIGH),
    (1000, _share(10.0), frozenset(), PRIORITY_MEDIUM),
    (1000, _share(9.9, purchases=0), frozenset(), PRIORITY_MEDIUM),
    (999, _share(1.0), frozenset(), PRIORITY_MEDIUM),
    (1000, _share(4.9), frozenset({"vitamin a cream"}), PRIORITY_MEDIUM),
    (1000, _share(5.0), frozenset({"vitamin a cream"}), PRIORITY_LOW),
    (500, _share(19.9), frozenset(), PRIORITY_MEDIUM),
    (500, _share(20.0), frozenset(), PRIORITY_LOW),
    (300, None, frozenset(), PRIORITY_LOW),
    (299, None, frozenset(), None),
])
def test_the_priority_rules(sv, share, in_sp, expected):
    assert _priority(sv=sv, share=share, in_sp=in_sp) == expected


def test_an_unknown_coverage_says_so_and_prioritizes_as_not_in_sp():
    targets = recommend_targets(_mkl(("vitamin a cream", 1000)), {"vitamin a cream": _share(1.0)}, None)

    row = targets.keywords.iloc[0]
    assert (row["En SP"], row["Prioridad"]) == (UNKNOWN, PRIORITY_HIGH)


def test_a_keyword_is_in_sp_by_its_normalized_text():
    targets = recommend_targets(_mkl(("Vitamin A  Cream", 400), ("retinol", 400)), {},
                                frozenset({"vitamin a cream"}))

    assert dict(zip(targets.keywords["Keyword"], targets.keywords["En SP"])) == {"Vitamin A  Cream": YES,
                                                                                  "retinol": NO}


def test_targets_come_by_priority_then_by_search_volume():
    mkl = _mkl(("baja chica", 300), ("alta", 2000), ("baja grande", 450), ("media", 600))
    shares = {"alta": _share(1.0), "media": _share(1.0, purchases=0)}

    targets = recommend_targets(mkl, shares, frozenset())

    assert list(targets.keywords["Keyword"]) == ["alta", "media", "baja grande", "baja chica"]
    assert list(targets.keywords.columns) == TARGET_COLUMNS


def test_a_root_shared_by_three_keywords_is_a_cluster_and_the_rest_fall_in_other():
    mkl = _mkl(("vitamin a cream", 900), ("vitamin c serum", 800), ("night vitamin oil", 700), ("baby lotion", 600))

    keywords = recommend_targets(mkl, {}, frozenset()).keywords

    assert dict(zip(keywords["Keyword"], keywords["Cluster"])) == {
        "vitamin a cream": "vitamin", "vitamin c serum": "vitamin", "night vitamin oil": "vitamin",
        "baby lotion": "other"}


def test_without_a_shared_root_every_keyword_is_in_one_general_cluster():
    keywords = recommend_targets(_mkl(("vitamin cream", 900), ("baby lotion", 800)), {}, frozenset()).keywords

    assert set(keywords["Cluster"]) == {"general"}


def test_the_headline_joins_the_most_repeated_roots_of_the_cluster_first_keywords():
    mkl = _mkl(("vitamin cream face", 900), ("vitamin cream night", 800), ("vitamin serum", 700))

    targets = recommend_targets(mkl, {}, frozenset())

    assert set(targets.keywords["Headline Sugerido"]) == {"Vitamin Cream Face Night"}


def test_the_cluster_summary_counts_keywords_search_volume_and_high_priority():
    mkl = _mkl(("vitamin a cream", 2000), ("vitamin c serum", 800), ("night vitamin oil", 700), ("baby lotion", 3000))
    shares = {"vitamin a cream": _share(1.0), "baby lotion": _share(1.0)}

    clusters = recommend_targets(mkl, shares, frozenset()).clusters

    assert list(clusters.columns) == CLUSTER_COLUMNS
    assert clusters[["Cluster", "KWs", "SV_Total", "Alta"]].values.tolist() == [["vitamin", 3, 3500, 1],
                                                                                ["other", 1, 3000, 1]]


def test_nothing_above_the_minimum_search_volume_leaves_empty_tables():
    targets = recommend_targets(_mkl(("tiny", 10)), {}, frozenset())

    assert targets.keywords.empty and targets.clusters.empty
    assert list(targets.keywords.columns) == TARGET_COLUMNS


def test_root_words_drop_stop_words_short_words_and_non_letters():
    assert root_words("Crema de vitamina A para la piel 50ml") == ["crema", "vitamina", "piel"]
