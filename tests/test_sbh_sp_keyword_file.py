"""The SP keywords that run, read from a hand-uploaded Bulk File or keyword export: SBH's «En SP» without an account."""
import io
from datetime import date

import pandas as pd
import pytest

from core.amazon_ads.active_keywords import active_keyword_texts
from core.amazon_ads.report_provider import ProfileOption
from core.amazon_ads.structure_provider import (
    AD_GROUP,
    CAMPAIGN,
    KEYWORD,
    NEGATIVE_KEYWORD,
    ROW_COLUMNS,
    StructureProvider,
    bulk_frame,
)
from core.sbh.sp_keyword_file import (
    CHECKED_KEYWORD,
    CHECKED_KEYWORD_CAMPAIGN_AD_GROUP,
    CHECKED_NONE,
    SP_SHEET,
    SpKeywordFileError,
    read_sp_keyword_file,
)

CAMPAIGN_ID = 132313349237695
AD_GROUP_ID = 900000000000101
BULK_COLUMNS = ["Product", "Entity", "Operation", "Campaign ID", "Ad Group ID", "Keyword ID", "Campaign Name",
                "State", "Keyword Text", "Match Type"]
PROFILE = ProfileOption.from_row({"profile_id": "p-1", "cliente": "Luna", "country_code": "US",
                                  "currency_code": "USD", "account_type": "seller"})


class _StructureRest:
    """The account's SP listing, answered from these rows."""

    def __init__(self, rows):
        self._rows = rows

    def rpc_csv(self, name, args, *, timeout_s=8):
        return pd.DataFrame(self._rows, columns=list(ROW_COLUMNS)).to_csv(index=False).encode("utf-8")


def _structure_row(entity, **values) -> dict:
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({"entity": entity, "campaign_id": "1", "state": "ENABLED", "metrics_known": "f",
                "listed_at": "2026-09-24 06:00:01+00"})
    row.update(values)
    return row


def _bulk_row(entity, *, campaign_id=CAMPAIGN_ID, ad_group_id=AD_GROUP_ID, state="enabled", text="",
              match_type="") -> dict:
    return {"Product": "Sponsored Products", "Entity": entity, "Operation": "", "Campaign ID": campaign_id,
            "Ad Group ID": ad_group_id, "Keyword ID": 409151500000001 if text else None, "Campaign Name": "LK - SP",
            "State": state, "Keyword Text": text, "Match Type": match_type}


def _campaign(campaign_id=CAMPAIGN_ID, state="enabled") -> dict:
    return _bulk_row("Campaign", campaign_id=campaign_id, ad_group_id=None, state=state)


def _ad_group(ad_group_id=AD_GROUP_ID, campaign_id=CAMPAIGN_ID, state="enabled") -> dict:
    return _bulk_row("Ad Group", campaign_id=campaign_id, ad_group_id=ad_group_id, state=state)


def _keyword(text, *, campaign_id=CAMPAIGN_ID, ad_group_id=AD_GROUP_ID, state="enabled", match_type="Exact",
             entity="Keyword") -> dict:
    return _bulk_row(entity, campaign_id=campaign_id, ad_group_id=ad_group_id, state=state, text=text,
                     match_type=match_type)


def _workbook(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def _bulk(*rows, extra_sheets=None) -> bytes:
    # A real Bulk File carries other sheets before and after the Sponsored Products one.
    sheets = {"Portfolios": pd.DataFrame({"Portfolio ID": [1], "Portfolio Name": ["Core"]})}
    sheets[SP_SHEET] = pd.DataFrame(list(rows), columns=BULK_COLUMNS)
    sheets.update(extra_sheets or {})
    return _workbook(sheets)


def _texts(*rows) -> frozenset[str]:
    return read_sp_keyword_file(_bulk(*rows), "bulk-luna.xlsx").keyword_texts


def _csv(frame: pd.DataFrame, *, encoding="utf-8") -> bytes:
    return frame.to_csv(index=False).encode(encoding)


def test_a_bulk_keyword_runs_when_it_its_campaign_and_its_ad_group_are_enabled():
    sp_file = read_sp_keyword_file(_bulk(_campaign(), _ad_group(), _keyword("vitamin a cream")), "bulk.xlsx")

    assert sp_file.keyword_texts == {"vitamin a cream"}
    assert sp_file.checked_states == CHECKED_KEYWORD_CAMPAIGN_AD_GROUP


def test_a_paused_or_archived_keyword_campaign_or_ad_group_leaves_its_keywords_out():
    texts = _texts(_campaign(), _campaign(2, state="paused"), _campaign(3, state="archived"),
                   _ad_group(), _ad_group(20, state="paused"), _ad_group(30, state="archived"),
                   _keyword("live one"), _keyword("paused one", state="paused"),
                   _keyword("archived one", state="archived"), _keyword("in paused campaign", campaign_id=2),
                   _keyword("in archived campaign", campaign_id=3), _keyword("in paused ad group", ad_group_id=20),
                   _keyword("in archived ad group", ad_group_id=30))

    assert texts == {"live one"}


def test_negative_keywords_never_count_as_running():
    texts = _texts(_campaign(), _ad_group(), _keyword("luna"),
                   _keyword("cheap", entity="Negative Keyword", match_type="Negative Exact"),
                   _keyword("free", entity="Campaign Negative Keyword", match_type="Negative Phrase", ad_group_id=None))

    assert texts == {"luna"}


def test_an_unlisted_ad_group_counts_as_enabled_and_an_unlisted_campaign_does_not():
    texts = _texts(_campaign(), _keyword("in unlisted ad group", ad_group_id=77),
                   _keyword("in unlisted campaign", campaign_id=5))

    assert texts == {"in unlisted ad group"}


def test_texts_are_compared_case_folded_with_single_spaces_in_any_match_type():
    texts = _texts(_campaign(), _ad_group(), _keyword("  Vitamin   C Serum ", match_type="Broad"),
                   _keyword("NIGHT oil", match_type="phrase"))

    assert texts == {"vitamin c serum", "night oil"}


def test_only_the_sponsored_products_sheet_is_read():
    brands = pd.DataFrame([_keyword("brand only keyword")], columns=BULK_COLUMNS)

    texts = read_sp_keyword_file(_bulk(_campaign(), _keyword("sp keyword"),
                                       extra_sheets={"Sponsored Brands Campaigns": brands}), "bulk.xlsx").keyword_texts

    assert texts == {"sp keyword"}


def test_a_bulk_without_keywords_has_none_of_them_running():
    assert _texts(_campaign(), _ad_group()) == frozenset()


def test_the_bulk_reads_the_same_running_keywords_as_the_account_listing():
    rows = [_structure_row(CAMPAIGN, campaign_id="1", entity_id="1"),
            _structure_row(CAMPAIGN, campaign_id="2", entity_id="2", state="PAUSED"),
            _structure_row(AD_GROUP, ad_group_id="10", entity_id="10"),
            _structure_row(AD_GROUP, ad_group_id="11", entity_id="11", state="ARCHIVED"),
            _structure_row(KEYWORD, ad_group_id="10", entity_id="k1", target_text="Vitamin C Serum",
                           match_type="EXACT"),
            _structure_row(KEYWORD, ad_group_id="10", entity_id="k2", target_text="night oil", match_type="BROAD",
                           state="PAUSED"),
            _structure_row(KEYWORD, ad_group_id="11", entity_id="k3", target_text="in archived group",
                           match_type="PHRASE"),
            _structure_row(KEYWORD, campaign_id="2", ad_group_id="20", entity_id="k4", target_text="in paused campaign",
                           match_type="EXACT"),
            _structure_row(KEYWORD, ad_group_id="12", entity_id="k5", target_text="unlisted group", match_type="EXACT"),
            _structure_row(NEGATIVE_KEYWORD, ad_group_id="10", entity_id="n1", target_text="cheap",
                           match_type="NEGATIVE_EXACT")]
    structure = StructureProvider(_StructureRest(rows)).sp_structure(PROFILE, date(2026, 9, 24), date(2026, 9, 24))
    bulk = _workbook({SP_SHEET: bulk_frame(structure.rows, 7)})

    from_file = read_sp_keyword_file(bulk, "bulk.xlsx").keyword_texts

    assert from_file == active_keyword_texts(structure.rows)
    assert from_file == {"vitamin c serum", "unlisted group"}


def test_a_bulk_sheet_without_the_keyword_columns_is_an_error():
    sheet = pd.DataFrame([{"Entity": "Campaign", "State": "enabled", "Campaign ID": 1}])

    with pytest.raises(SpKeywordFileError, match="Keyword Text"):
        read_sp_keyword_file(_workbook({SP_SHEET: sheet}), "bulk.xlsx")


def test_a_keyword_export_counts_the_enabled_or_active_keywords_by_their_own_state():
    export = pd.DataFrame({"Campaign Name": ["A", "A", "B", "B"],
                           "Keyword Text": ["Vitamin A Cream", "night oil", "baby lotion", "  Luna  Kids "],
                           "Match Type": ["Exact", "Broad", "Phrase", "Exact"],
                           "State": ["enabled", "paused", "ACTIVE", " Enabled "]})

    sp_file = read_sp_keyword_file(_csv(export), "keywords.csv")

    assert sp_file.keyword_texts == {"vitamin a cream", "baby lotion", "luna kids"}
    assert sp_file.checked_states == CHECKED_KEYWORD


def test_a_delivery_status_next_to_the_state_leaves_out_keywords_whose_campaign_or_ad_group_is_paused():
    export = pd.DataFrame({"Keyword": ["vitamin a cream", "night oil", "baby lotion", "luna kids", "old one"],
                           "State": ["enabled", "enabled", "enabled", "enabled", "paused"],
                           "Status": ["Delivering", "Campaign paused", "Ad group archived", "Out of budget",
                                      "Paused"]})

    sp_file = read_sp_keyword_file(_csv(export), "keywords.csv")

    assert sp_file.keyword_texts == {"vitamin a cream", "luna kids"}
    assert sp_file.checked_states == CHECKED_KEYWORD_CAMPAIGN_AD_GROUP


def test_a_delivery_status_alone_keeps_what_delivers_and_is_never_read_as_enabled_or_paused():
    export = pd.DataFrame({"Keyword": ["vitamin a cream", "night oil", "baby lotion", "luna kids"],
                           "Status": ["Delivering", "Campaign paused", "Out of budget", "Campaign ended"]})

    sp_file = read_sp_keyword_file(_csv(export), "keywords.csv")

    assert sp_file.keyword_texts == {"vitamin a cream", "baby lotion"}
    assert sp_file.checked_states == CHECKED_KEYWORD


def test_a_status_that_says_inactive_or_disabled_stops_the_keyword_like_paused():
    export = pd.DataFrame({"Keyword": ["foo", "bar", "baz", "qux"],
                           "Status": ["enabled", "paused", "inactive", "disabled"]})

    sp_file = read_sp_keyword_file(_csv(export), "keywords.csv")

    assert sp_file.keyword_texts == {"foo"}


def test_a_keyword_export_without_a_state_column_counts_every_keyword_and_says_so():
    export = pd.DataFrame({"Targeting": ["vitamin a cream", "night oil", None, ""],
                           "Targeting type": ["Keyword", "Keyword", "Keyword", "Keyword"]})

    sp_file = read_sp_keyword_file(_csv(export), "targeting.csv")

    assert sp_file.keyword_texts == {"vitamin a cream", "night oil"}
    assert sp_file.checked_states == CHECKED_NONE


def test_a_keyword_export_leaves_negative_keywords_out():
    export = pd.DataFrame({"Keyword Text": ["luna", "cheap", "free"],
                           "Match Type": ["Exact", "Negative Exact", "negativePhrase"],
                           "State": ["enabled", "enabled", "enabled"]})

    assert read_sp_keyword_file(_csv(export), "keywords.csv").keyword_texts == {"luna"}


def test_a_keyword_export_with_a_byte_order_mark_reads_its_first_column():
    export = pd.DataFrame({"Keyword Text": ["vitamin a cream"], "State": ["enabled"]})

    assert read_sp_keyword_file(_csv(export, encoding="utf-8-sig"), "keywords.csv").keyword_texts == {
        "vitamin a cream"}


@pytest.mark.parametrize("separator", [";", "\t"], ids=["semicolon", "tab"])
def test_a_keyword_export_saved_with_another_separator_reads_its_columns_not_one_merged_keyword(separator):
    export = pd.DataFrame({"Campaign Name": ["LK - SP - Exact", "LK - SP - Exact"],
                           "Keyword Text": ["vitamin c serum", "night vitamin oil"], "Match Type": ["exact", "exact"],
                           "State": ["enabled", "paused"]})

    sp_file = read_sp_keyword_file(export.to_csv(index=False, sep=separator).encode("utf-8"), "keywords.csv")

    assert sp_file.keyword_texts == {"vitamin c serum"}
    assert sp_file.checked_states == CHECKED_KEYWORD


def test_a_keyword_export_resaved_by_a_spanish_excel_reads_its_accents_and_semicolons():
    export = pd.DataFrame({"Keyword Text": ["crema para niño", "loción"], "State": ["Enabled", "Paused"]})

    sp_file = read_sp_keyword_file(export.to_csv(index=False, sep=";").encode("cp1252"), "keywords.csv")

    assert sp_file.keyword_texts == {"crema para niño"}


def test_a_single_sheet_workbook_is_read_as_a_keyword_export():
    export = pd.DataFrame({"Keyword Text": ["vitamin a cream", "night oil"], "State": ["enabled", "paused"]})

    sp_file = read_sp_keyword_file(_workbook({"Targeting": export}), "targeting.xlsx")

    assert sp_file.keyword_texts == {"vitamin a cream"}
    assert sp_file.checked_states == CHECKED_KEYWORD


def test_a_file_without_a_keyword_column_is_an_error_not_an_empty_list():
    export = pd.DataFrame({"Campaign Name": ["A"], "Spend": [12.5], "Targeting type": ["Keyword"]})

    with pytest.raises(SpKeywordFileError, match="texto de las keywords"):
        read_sp_keyword_file(_csv(export), "campaigns.csv")


@pytest.mark.parametrize("export", [
    pd.DataFrame({"Campaigns": ["LK - SP - Auto", "LK - SP - Exact"], "State": ["Enabled", "Enabled"],
                  "Status": ["Delivering", "Delivering"], "Type": ["Sponsored Products", "Sponsored Products"],
                  "Targeting": ["Automatic", "Manual"], "Portfolio": ["Core", "Core"]}),
    pd.DataFrame({"Campaign Name": ["LK - SP - Auto", "LK - SP - Exact"], "Targeting": ["automatic", " MANUAL "],
                  "Spend": [12.5, 4.0]}),
], ids=["campaign manager grid", "legacy campaign export"])
def test_a_campaign_export_whose_targeting_says_manual_or_automatic_is_not_a_keyword_list(export):
    with pytest.raises(SpKeywordFileError, match="texto de las keywords"):
        read_sp_keyword_file(_csv(export), "campaigns.csv")


def test_a_targeting_export_with_a_manual_keyword_among_others_is_still_read():
    export = pd.DataFrame({"Targeting": ["manual", "vitamin a cream"], "Match type": ["Exact", "Broad"],
                           "State": ["Enabled", "Enabled"]})

    assert read_sp_keyword_file(_csv(export), "targeting.csv").keyword_texts == {"manual", "vitamin a cream"}


def test_a_workbook_with_several_sheets_and_no_sponsored_products_one_is_an_error():
    other = pd.DataFrame({"Keyword Text": ["vitamin a cream"]})

    with pytest.raises(SpKeywordFileError, match=SP_SHEET):
        read_sp_keyword_file(_workbook({"Sponsored Brands Campaigns": other, "Portfolios": other}), "bulk.xlsx")


@pytest.mark.parametrize("file_bytes, file_name", [(b"not a workbook at all", "bulk.xlsx"),
                                                   (b"PK\x03\x04broken zip", "bulk.xlsx"),
                                                   # An encrypted .xlsx or a renamed .xls: pandas asks for xlrd.
                                                   (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(504),
                                                    "bulk-protegido.xlsx"),
                                                   (b"\xff\xfe\x00\xd8 not text", "keywords.csv"),
                                                   (b"", "keywords.csv")],
                         ids=["not a workbook", "broken zip", "encrypted workbook", "not text", "empty"])
def test_bytes_that_are_not_a_readable_file_are_an_error(file_bytes, file_name):
    with pytest.raises(SpKeywordFileError):
        read_sp_keyword_file(file_bytes, file_name)
