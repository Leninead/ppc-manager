"""A Bulk File uploaded by hand (Campaign Manager → Bulk Operations) read into what Análisis Cruzado reads from an
Amazon Ads account: the search terms as the canonical frame, the enabled exact keywords and each ad group's ASINs.

The same objects the account hands the tabs, so the plan, both exports and INV-11's marks run on the file unchanged.
"""
from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from dataclasses import dataclass

import pandas as pd

from core.amazon_ads.active_keywords import normalized_keyword
from core.amazon_ads.report_provider import (
    KEYWORD_MATCH_TYPES,
    NOT_A_KEYWORD_MATCH,
    ORIGIN_AUTO,
    ORIGIN_PRODUCT_TARGETING,
)
from core.bulk.parser import SHEET_CAMPAIGNS, SHEET_STR, _ids_a_string, _norm_col, get_exact_activas
from core.search_term import frame as canonical
from core.search_term.file import DEFAULT_ATTRIBUTION_DAYS
from core.search_term.frame import (
    ANY_WINDOW_PURCHASES,
    HIDDEN_ID_COLUMNS,
    PORTFOLIO_NAME_MISSING,
    SOURCE_FILE,
    SearchTermSource,
    add_ratios,
    console_columns,
)

log = logging.getLogger(__name__)

# The predefined targets of an auto campaign: a term they bring can be negated, one from a product target cannot.
AUTO_EXPRESSIONS = frozenset({"close-match", "loose-match", "substitutes", "complements"})
# Amazon's keyword type of a target, as the synced search terms carry it.
_TARGET_KEYWORD_TYPES = {ORIGIN_AUTO: "TARGETING_EXPRESSION_PREDEFINED",
                         ORIGIN_PRODUCT_TARGETING: "TARGETING_EXPRESSION"}
_EXACT_KEYWORD_COLUMNS = {"Entity", "Match Type", "State", "Keyword Text"}
_PRODUCT_AD_COLUMNS = {"Entity", "Ad Group ID", "ASIN"}

UNREADABLE_MESSAGE = ("No se pudo leer «{file}». Subí el Bulk File (.xlsx) tal como lo exporta Campaign Manager → "
                      "Bulk Operations, sin abrirlo ni guardarlo de nuevo.")
MISSING_SEARCH_TERMS_MESSAGE = (
    f"**El archivo no tiene la hoja «{SHEET_STR}».** Parece el Search Term Report standalone, que no trae los IDs "
    "de Amazon con los que se arma un bulk, o un Bulk File bajado sin los search terms.\n\n"
    "**Cómo bajar el correcto:** Campaign Manager → **Bulk Operations** → en *Create & download custom spreadsheet* "
    "elegí un rango de **30 días o más**, tildá **Sponsored Products** y, en las opciones de datos, **Search term "
    "data**; en *Exclude*, destildá **Campaign items with zero impressions** → Download."
)
MISSING_SEARCH_TERM_COLUMN_MESSAGE = (f"La hoja «{SHEET_STR}» no tiene la columna «{canonical.SEARCH_TERM}». Al bajar "
                                      "el Bulk File faltó tildar **Search term data**.")


class BulkFileError(ValueError):
    """The Bulk File cannot be analyzed; the message says why and how to export the right one."""


@dataclass(frozen=True, eq=False)
class BulkFileAccount:
    search_terms: SearchTermSource
    # None without the campaigns sheet or its keyword columns: which exact keywords exist is unknown, never "none".
    exact_keywords: frozenset[str] | None
    ad_group_asins: dict[str, frozenset[str]]


def read_bulk_file(file_bytes: bytes, file_name: str) -> BulkFileAccount:
    """Raises BulkFileError when the bytes are not an .xlsx or the file has no search terms sheet."""
    try:
        with pd.ExcelFile(io.BytesIO(file_bytes)) as workbook:
            search_term_sheet = _bulk_sheet(workbook, SHEET_STR)
            campaigns = _bulk_sheet(workbook, SHEET_CAMPAIGNS)
    # ImportError: an OLE file (an .xls renamed, an encrypted .xlsx) wants xlrd; KeyError: a zip that is no workbook.
    except (ValueError, KeyError, ImportError, zipfile.BadZipFile, OSError) as exc:
        log.warning("Bulk file %r could not be read: %s: %s", file_name, type(exc).__name__, exc)
        raise BulkFileError(UNREADABLE_MESSAGE.format(file=file_name)) from exc
    if search_term_sheet is None:
        raise BulkFileError(MISSING_SEARCH_TERMS_MESSAGE)
    if canonical.SEARCH_TERM not in search_term_sheet.columns:
        raise BulkFileError(MISSING_SEARCH_TERM_COLUMN_MESSAGE)

    search_terms = SearchTermSource(
        frame=canonical_search_terms(search_term_sheet), source=SOURCE_FILE, currency_code="", label=file_name,
        signature=f"{hashlib.sha256(file_bytes).hexdigest()[:16]}:bulk", attribution_days=DEFAULT_ATTRIBUTION_DAYS,
        bulk_ready=True,
    )
    if campaigns is None or not _EXACT_KEYWORD_COLUMNS <= set(campaigns.columns):
        return BulkFileAccount(search_terms, exact_keywords=None, ad_group_asins={})
    return BulkFileAccount(search_terms, exact_keywords=enabled_exact_keywords(campaigns),
                           ad_group_asins=ad_group_asins(campaigns))


def _bulk_sheet(workbook: pd.ExcelFile, sheet_name: str) -> pd.DataFrame | None:
    """The sheet as Amazon wrote it: a "nan" or "NA" cell is a search term or a keyword; only an empty cell is none."""
    if sheet_name not in workbook.sheet_names:
        return None
    sheet = workbook.parse(sheet_name, keep_default_na=False, na_values=[""])
    sheet.columns = [_norm_col(column) for column in sheet.columns]
    return _ids_a_string(sheet)


def canonical_search_terms(search_term_sheet: pd.DataFrame) -> pd.DataFrame:
    """The sheet shaped as ReportProvider shapes an account's search terms: its columns, IDs as text, 7-day names.

    A keyword row keeps its match type as origin; a target row is AUTO when an auto campaign's predefined target
    brought it, PRODUCT_TARGETING otherwise.
    """
    sheet = search_term_sheet[_texts(search_term_sheet, canonical.SEARCH_TERM).ne("")]
    days = DEFAULT_ATTRIBUTION_DAYS
    match_types = _texts(sheet, "Match Type").str.upper()
    keyword_ids, target_ids = _texts(sheet, "Keyword ID"), _texts(sheet, "Product Targeting ID")
    is_keyword = match_types.isin(KEYWORD_MATCH_TYPES) & ~(keyword_ids.eq("") & target_ids.ne(""))
    expressions = _texts(sheet, "Product Targeting Expression")
    origins = pd.Series(ORIGIN_PRODUCT_TARGETING, index=sheet.index, dtype="object")
    origins[expressions.str.casefold().isin(AUTO_EXPRESSIONS)] = ORIGIN_AUTO
    origins[is_keyword] = match_types[is_keyword]
    targeting = _texts(sheet, "Keyword Text").where(is_keyword, expressions)
    portfolio_names = _texts(sheet, "Portfolio Name")
    orders = _counts(sheet, "Orders")
    frame = pd.DataFrame({
        canonical.SEARCH_TERM: _texts(sheet, canonical.SEARCH_TERM),
        canonical.CAMPAIGN_NAME: _texts(sheet, "Campaign Name"),
        canonical.AD_GROUP_NAME: _texts(sheet, "Ad Group Name"),
        canonical.PORTFOLIO_NAME: portfolio_names,
        canonical.MATCH_TYPE: match_types.where(is_keyword, NOT_A_KEYWORD_MATCH),
        canonical.TARGETING: targeting,
        canonical.IMPRESSIONS: _counts(sheet, "Impressions"),
        canonical.CLICKS: _counts(sheet, "Clicks"),
        canonical.SPEND: _amounts(sheet, "Spend"),
        canonical.sales_column(days): _amounts(sheet, "Sales"),
        canonical.orders_column(days): orders,
        canonical.units_column(days): _counts(sheet, "Units"),
        "_campaign_id": _texts(sheet, "Campaign ID"),
        "_ad_group_id": _texts(sheet, "Ad Group ID"),
        "_keyword_id": keyword_ids.where(is_keyword, target_ids),
        "_keyword_type": origins.where(is_keyword, origins.map(_TARGET_KEYWORD_TYPES)),
        "_origin_match_type": origins,
        "_campaign_status": _texts(sheet, "Campaign State").str.upper(),
        "_ad_keyword_status": _texts(sheet, "State").str.upper(),
        "_keyword_text": targeting,
        ANY_WINDOW_PURCHASES: orders,
        PORTFOLIO_NAME_MISSING: _texts(sheet, "Portfolio ID").ne("") & portfolio_names.eq(""),
    })
    # The provider's order, so a file reads like an account: most spend first, ties broken by the ids.
    frame = frame.sort_values(
        [canonical.SPEND, canonical.CLICKS, canonical.SEARCH_TERM, "_campaign_id", "_ad_group_id", "_keyword_type",
         "_keyword_id", "_origin_match_type", canonical.TARGETING],
        ascending=[False, False, True, True, True, True, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return add_ratios(frame, days)[console_columns(days) + list(HIDDEN_ID_COLUMNS)]


def enabled_exact_keywords(campaigns: pd.DataFrame) -> frozenset[str]:
    """INV-11.2's universe from the campaigns sheet, normalized as the account's listing gives it."""
    return frozenset(normalized_keyword(text) for text in get_exact_activas(campaigns))


def ad_group_asins(campaigns: pd.DataFrame) -> dict[str, frozenset[str]]:
    """ad group id -> every ASIN its product ads advertise, as the account's product ads listing says it."""
    if not _PRODUCT_AD_COLUMNS <= set(campaigns.columns):
        return {}
    product_ads = campaigns[_texts(campaigns, "Entity").str.casefold().eq("product ad")]
    by_ad_group: dict[str, set[str]] = {}
    for ad_group_id, asin in zip(_texts(product_ads, "Ad Group ID"), _texts(product_ads, "ASIN").str.upper()):
        if ad_group_id and asin:
            by_ad_group.setdefault(ad_group_id, set()).add(asin)
    return {ad_group_id: frozenset(asins) for ad_group_id, asins in by_ad_group.items()}


def _texts(sheet: pd.DataFrame, column: str) -> pd.Series:
    if column not in sheet.columns:
        return pd.Series("", index=sheet.index, dtype="object")
    return sheet[column].fillna("").astype(str).str.strip()


def _amounts(sheet: pd.DataFrame, column: str) -> pd.Series:
    if column not in sheet.columns:
        return pd.Series(0.0, index=sheet.index, dtype="float64")
    values = sheet[column]
    if not pd.api.types.is_numeric_dtype(values):
        # A money cell typed as text ("MX$5,796.55") keeps only its number.
        values = values.astype(str).str.replace(r"[^\d.\-]", "", regex=True)
    return pd.to_numeric(values, errors="coerce").fillna(0).astype("float64")


def _counts(sheet: pd.DataFrame, column: str) -> pd.Series:
    return _amounts(sheet, column).round().astype("int64")
