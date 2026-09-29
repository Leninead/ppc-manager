"""A Bulk File uploaded by hand read into what Análisis Cruzado reads from an account. No network.

The synthetic Bulk File of tests/fixtures/make_bulk_fixture.py, plus rows it lacks built here in memory: the other
predefined auto targets, a second ASIN in one ad group and an exact keyword with inner double spaces.
"""
import hashlib
import io
import zipfile

import pandas as pd
import pytest

from core.bulk.export import build_bid_update, build_keyword_create
from core.bulk.parser import validate_bulk
from core.cross_analysis.action_plan import (
    ACTION,
    ACTION_DEFEND,
    ACTION_SCALE,
    QUERY,
    QUERY_TYPE,
    ActionPlanParams,
    build_action_plan,
    numeric_sqp,
    query_types,
)
from core.cross_analysis.bulk_file import BulkFileError, read_bulk_file
from core.cross_analysis.plan_exports import bulk_rows
from core.cross_analysis.ranking_guards import NOT_NEGATABLE, ORIGIN, RANKING_KEYWORD, exact_marks, with_ranking_guards
from core.search_term.frame import (
    ACOS,
    HIDDEN_ID_COLUMNS,
    PORTFOLIO_NAME,
    SEARCH_TERM,
    SOURCE_FILE,
    SPEND,
    conversion_rate_column,
    console_columns,
    orders_column,
    sales_column,
)
from tests.cross_analysis_data import sqp, sqp_row
from tests.fixtures import make_bulk_fixture as fixture
from tests.test_bulk_parser import _asegurar_fixture as synthetic_bulk_file

C1_AD_GROUP = str(fixture.AG[fixture.C1])
C3_AD_GROUP = str(fixture.AG[fixture.C3])


def _target_row(expression: str, term: str, index: int) -> dict:
    return fixture._fila_str(campaign=fixture.C4, keyword_id=None, pt_id=fixture._pt(index), keyword_text="",
                             match_type="", pt_expression=expression, cst=term, impressions=900, clicks=9, spend=6.3,
                             sales=0.0, orders=0)


EXTRA_SEARCH_TERMS = [_target_row("loose-match", "sleeping bag kids", 21),
                      _target_row("Substitutes", "b0rival0021", 22),
                      _target_row("complements", "baby monitor", 23)]
EXTRA_CAMPAIGN_ROWS = [
    fixture._fila_camp(Entity="Product Ad", **{"Campaign ID": fixture.C1, "Ad Group ID": float(fixture.AG[fixture.C1]),
                                              "Ad ID": 880000000000999.0, "State": "enabled", "ASIN": "b0test00005"}),
    fixture._fila_camp(Entity="Keyword", **{"Campaign ID": fixture.C1, "Ad Group ID": float(fixture.AG[fixture.C1]),
                                           "Keyword ID": 409151500000950.0, "State": "enabled",
                                           "Keyword Text": "Nordic  Sleep   Sack", "Match Type": "Exact"}),
]


# NAN is a baby formula brand: "nan" is a real query, and pandas reads these four as missing cells by default.
MISSING_VALUE_LOOKALIKES = ("nan", "null", "NA", "n/a")
# What an .xls renamed to .xlsx, or an .xlsx encrypted by a password or a sensitivity label, starts with.
OLE_COMPOUND_FILE = bytes.fromhex("D0CF11E0A1B11AE1") + bytes(504)


def bulk_workbook(*, search_terms=True, campaigns=True, extra_search_terms=(), extra_campaign_rows=()) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if search_terms:
            rows = fixture.build_str_df().to_dict("records") + EXTRA_SEARCH_TERMS + list(extra_search_terms)
            pd.DataFrame(rows, columns=fixture.STR_COLS).to_excel(writer, sheet_name=fixture.SHEET_STR, index=False)
        if campaigns:
            rows = fixture.build_campaigns_df().to_dict("records") + EXTRA_CAMPAIGN_ROWS + list(extra_campaign_rows)
            pd.DataFrame(rows, columns=fixture.CAMP_COLS).to_excel(writer, sheet_name=fixture.SHEET_CAMPAIGNS,
                                                                   index=False)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def fixture_bytes() -> bytes:
    return synthetic_bulk_file().read_bytes()


@pytest.fixture(scope="module")
def bulk(fixture_bytes):
    return read_bulk_file(fixture_bytes, "bulk.xlsx")


@pytest.fixture(scope="module")
def extended():
    return read_bulk_file(bulk_workbook(), "bulk_extended.xlsx")


def _row(frame: pd.DataFrame, term: str) -> pd.Series:
    (row,) = [row for _, row in frame.iterrows() if row[SEARCH_TERM] == term]
    return row


def test_the_search_terms_have_the_columns_of_the_amazon_ads_frame_and_ids_as_text(bulk):
    frame = bulk.search_terms.frame

    assert list(frame.columns) == console_columns(7) + list(HIDDEN_ID_COLUMNS)
    assert len(frame) == 14
    row = _row(frame, "nordic sleep bag")
    assert (row["_campaign_id"], row["_ad_group_id"], row["_keyword_id"]) == (
        "132313349237695", "900000000000101", "409151500000001")


def test_a_keyword_row_keeps_its_match_type_keyword_id_and_text(bulk):
    frame = bulk.search_terms.frame

    exact = _row(frame, "nordic sleep bag")
    assert (exact["Match Type"], exact["_origin_match_type"], exact["_keyword_type"]) == ("EXACT", "EXACT", "EXACT")
    phrase = _row(frame, "merino wool swaddle blanket")
    assert (phrase["_origin_match_type"], phrase["_keyword_text"], phrase["Targeting"]) == (
        "PHRASE", "merino swaddle", "merino swaddle")
    lower_case_broad = _row(frame, "crema nocturna bebé")
    assert (lower_case_broad["Match Type"], lower_case_broad["_keyword_id"]) == ("BROAD", "409151500000014")


def test_an_auto_target_is_negatable_and_a_product_target_is_not(bulk):
    guarded = with_ranking_guards(bulk.search_terms.frame, bulk.exact_keywords)

    auto = _row(guarded, "b0test00099")
    assert (auto[ORIGIN], auto[NOT_NEGATABLE], auto["Match Type"]) == ("Auto", False, "-")
    assert (auto["_keyword_type"], auto["_keyword_id"], auto["_keyword_text"]) == (
        "TARGETING_EXPRESSION_PREDEFINED", "715151500000011", "close-match")
    product_target = _row(guarded, "b0test00042")
    assert (product_target[ORIGIN], product_target[NOT_NEGATABLE]) == ("Product Targeting", True)
    assert (product_target["_keyword_type"], product_target["_keyword_text"]) == (
        "TARGETING_EXPRESSION", 'asin="B0TEST00042"')


def test_every_predefined_target_of_an_auto_campaign_reads_as_auto(extended):
    frame = extended.search_terms.frame

    origins = {term: _row(frame, term)["_origin_match_type"]
               for term in ("sleeping bag kids", "b0rival0021", "baby monitor", "b0test00099")}
    assert set(origins.values()) == {"AUTO"}


def test_the_portfolio_name_reaches_the_ranking_guard(bulk):
    guarded = with_ranking_guards(bulk.search_terms.frame, bulk.exact_keywords)

    assert _row(guarded, "merino wool swaddle blanket")[PORTFOLIO_NAME] == "RANKING"
    assert bool(_row(guarded, "merino wool swaddle blanket")[RANKING_KEYWORD])
    assert not bool(_row(guarded, "organic cotton sleep sack")[RANKING_KEYWORD])


def test_sales_and_orders_take_the_seven_day_names_and_the_ratios_follow(bulk):
    row = _row(bulk.search_terms.frame, "organic cotton sleep sack")

    assert (row[sales_column(7)], row[orders_column(7)]) == (120.0, 5)
    assert (row[ACOS], row[conversion_rate_column(7)]) == (15.0, 25.0)


def test_the_exact_keywords_are_the_enabled_ones_normalized(bulk, extended):
    assert bulk.exact_keywords == frozenset({"sleep sack winter", "merino wool swaddle", "organic cotton sleep sack",
                                             "nordic sleep bag"})
    assert "nordic sleep sack" in extended.exact_keywords
    marks = exact_marks(pd.Series(["Nordic sleep  sack", "picnic blanket waterproof"]), extended.exact_keywords)
    assert marks.tolist() == [True, False]


def test_each_ad_group_keeps_every_asin_it_advertises(bulk, extended):
    assert bulk.ad_group_asins == {C1_AD_GROUP: frozenset({"B0TEST00001"}), C3_AD_GROUP: frozenset({"B0TEST00002"})}
    assert extended.ad_group_asins[C1_AD_GROUP] == frozenset({"B0TEST00001", "B0TEST00005"})


def test_without_the_campaigns_sheet_the_exact_keywords_are_unknown_not_none():
    without_campaigns = read_bulk_file(bulk_workbook(campaigns=False), "bulk.xlsx")

    assert without_campaigns.exact_keywords is None
    assert without_campaigns.ad_group_asins == {}
    assert len(without_campaigns.search_terms.frame) == 17


def test_without_the_search_term_sheet_the_error_says_how_to_download_it():
    with pytest.raises(BulkFileError) as raised:
        read_bulk_file(bulk_workbook(search_terms=False), "bulk.xlsx")

    assert isinstance(raised.value, ValueError)
    assert "SP Search Term Report" in str(raised.value) and "Search term data" in str(raised.value)
    assert "Campaign items with zero impressions" in str(raised.value)


def test_bytes_that_are_not_a_workbook_are_an_error_that_names_the_file():
    with pytest.raises(BulkFileError, match="notas.xlsx"):
        read_bulk_file(b"not a workbook", "notas.xlsx")


def _word_document() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


@pytest.mark.parametrize("file_bytes", [OLE_COMPOUND_FILE, _word_document()], ids=["ole", "docx"])
def test_a_legacy_encrypted_or_non_workbook_xlsx_is_an_error_that_names_the_file(file_bytes):
    with pytest.raises(BulkFileError, match="bulk-protegido.xlsx"):
        read_bulk_file(file_bytes, "bulk-protegido.xlsx")


def test_a_term_or_keyword_that_reads_like_a_missing_value_keeps_its_row_and_spend():
    lookalikes = [fixture._fila_str(campaign=fixture.C1, keyword_id=fixture._kw(60 + index), pt_id=None,
                                    keyword_text="nan", match_type="Exact", pt_expression="", cst=term,
                                    impressions=1000, clicks=20, spend=10.0, sales=50.0, orders=2)
                  for index, term in enumerate(MISSING_VALUE_LOOKALIKES)]
    nan_keyword = fixture._fila_camp(Entity="Keyword", **{"Campaign ID": fixture.C1, "Ad Group ID": float(C1_AD_GROUP),
                                                          "Keyword ID": fixture._kw(60), "State": "enabled",
                                                          "Keyword Text": "nan", "Match Type": "Exact"})

    account = read_bulk_file(bulk_workbook(extra_search_terms=lookalikes, extra_campaign_rows=[nan_keyword]),
                             "bulk.xlsx")

    frame = account.search_terms.frame
    kept = frame[frame[SEARCH_TERM].isin(MISSING_VALUE_LOOKALIKES)]
    assert sorted(kept[SEARCH_TERM]) == sorted(MISSING_VALUE_LOOKALIKES)
    assert kept[SPEND].sum() == 40.0
    assert set(kept["_keyword_text"]) == {"nan"}
    assert "nan" in account.exact_keywords


def test_the_file_has_no_account_and_its_digest_signs_it(bulk, fixture_bytes, extended):
    source = bulk.search_terms

    assert (source.source, source.label, source.currency_code, source.profile_id) == (SOURCE_FILE, "bulk.xlsx", "", "")
    assert (source.attribution_days, source.bulk_ready, source.window_start) == (7, True, None)
    assert source.signature.startswith(hashlib.sha256(fixture_bytes).hexdigest()[:16])
    assert extended.search_terms.signature != source.signature


def test_a_plan_from_the_bulk_file_exports_bid_updates_and_keyword_creates_amazon_takes(bulk):
    params = ActionPlanParams(target_acos=35.0, brand_terms=("merino",))
    table = sqp(sqp_row("organic cotton sleep sack", purchases=40, brand_purchases=5, brand_share=12.5),
                sqp_row("merino wool swaddle blanket", purchases=30, brand_purchases=3, brand_share=10.0))
    table[QUERY_TYPE] = query_types(table[QUERY], params.brand_terms)
    guarded = with_ranking_guards(bulk.search_terms.frame, bulk.exact_keywords)
    plan = build_action_plan(numeric_sqp(table), guarded, bulk.exact_keywords, params, sales_column=sales_column(7),
                             orders_column=orders_column(7))
    assert dict(zip(plan[QUERY], plan[ACTION])) == {"organic cotton sleep sack": ACTION_SCALE,
                                                    "merino wool swaddle blanket": ACTION_DEFEND}

    rows = bulk_rows(plan, 0.5)
    updates, invalid_updates = build_bid_update(rows.updates)
    creates, invalid_creates = build_keyword_create(rows.creates)

    assert invalid_updates.empty and invalid_creates.empty
    assert updates[["Campaign ID", "Ad Group ID", "Keyword ID", "Keyword Text", "Match Type"]].values.tolist() == [
        ["214785693021447", "900000000000202", "409151500000006", "sleep sack", "Broad"]]
    assert creates[["Campaign ID", "Ad Group ID", "Keyword Text", "Match Type"]].values.tolist() == [
        ["132313349237695", "900000000000101", "merino wool swaddle blanket", "Exact"]]
    errors = validate_bulk(pd.concat([creates, updates], ignore_index=True))
    assert [error for error in errors if error.severidad == "error"] == []
