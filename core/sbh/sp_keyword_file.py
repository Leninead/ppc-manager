"""The Sponsored Products keywords that run, read from a file the AM uploads by hand instead of the account's listing.

A Bulk File (Campaign Manager → Bulk Operations) carries every keyword with its campaign and ad group, so it is read
with the listing's own rule. A flat keyword export carries each keyword's own state, Campaign Manager's delivery
status (which also says when the campaign or the ad group is paused), both, or neither: the result says which states
the file let the reader check, so the page and the AI never claim more than the file says.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import pandas as pd

from core.amazon_ads.active_keywords import active_keyword_texts, normalized_keyword
from core.amazon_ads.structure_provider import AD_GROUP, CAMPAIGN, KEYWORD
from core.bulk.parser import SHEET_CAMPAIGNS, parse_bulk_campaigns
from core.csv_io import encoding_csv, sep_csv

SP_SHEET = SHEET_CAMPAIGNS
CHECKED_KEYWORD_CAMPAIGN_AD_GROUP = "keyword_campaign_ad_group"
CHECKED_KEYWORD = "keyword"
CHECKED_NONE = "none"
CHECKED_STATES_PHRASES = {
    CHECKED_KEYWORD_CAMPAIGN_AD_GROUP: "keyword, campaña y ad group habilitados",
    CHECKED_KEYWORD: "keyword habilitada; el archivo no dice si su campaña y su ad group lo están",
    CHECKED_NONE: "el archivo no dice si la keyword está habilitada, así que cuenta todas las que trae",
}

_BULK_ENTITIES = {"Campaign": CAMPAIGN, "Ad Group": AD_GROUP, "Keyword": KEYWORD}
_BULK_COLUMNS = ("Entity", "State", "Campaign ID", "Ad Group ID", "Keyword Text")
_KEYWORD_COLUMN_NAMES = ("keyword text", "keyword", "targeting")
# A campaign grid's Targeting column says how each campaign targets, not which keywords it runs.
_CAMPAIGN_TARGETING_TYPES = {"manual", "automatic"}
_STATE_COLUMN = "state"
_RUNNING_STATES = ("enabled", "active")
# Campaign Manager's Status is the delivery status: "Delivering", "Out of budget", "Campaign paused", "Ad group archived".
_DELIVERY_STATUS_COLUMN = "status"
_STOPPED_DELIVERY = r"\b(?:paused|archived|ended|inactive|disabled)\b"
# ImportError: pandas asks for xlrd when the bytes are an encrypted workbook or a renamed .xls.
_READ_ERRORS = (ValueError, KeyError, zipfile.BadZipFile, OSError, ImportError)

NOT_READABLE_MESSAGE = "no es un Excel ni un CSV que se pueda leer."
NO_SP_SHEET_MESSAGE = f"tiene varias hojas y ninguna se llama «{SP_SHEET}»."
BULK_COLUMNS_MESSAGE = (f"la hoja «{SP_SHEET}» no trae las columnas {', '.join(_BULK_COLUMNS[:-1])} y "
                        f"{_BULK_COLUMNS[-1]}.")
NO_KEYWORD_COLUMN_MESSAGE = "no trae una columna con el texto de las keywords (Keyword Text, Keyword o Targeting)."


class SpKeywordFileError(ValueError):
    """The file cannot say which SP keywords run; the message says why, in words for the AM."""


@dataclass(frozen=True)
class SpKeywordFile:
    keyword_texts: frozenset[str]
    # Which states the file let the reader check before counting a keyword: a CHECKED_* value.
    checked_states: str


def read_sp_keyword_file(file_bytes: bytes, file_name: str) -> SpKeywordFile:
    """The normalized text of every SP keyword the file says runs; raises SpKeywordFileError when it cannot tell."""
    if file_name.lower().endswith(".csv"):
        return _keyword_export(_read(lambda: _read_csv(file_bytes)))
    workbook = _read(lambda: pd.ExcelFile(io.BytesIO(file_bytes)))
    if SP_SHEET in workbook.sheet_names:
        return _bulk_file(_read(lambda: parse_bulk_campaigns(workbook)))
    if len(workbook.sheet_names) != 1:
        raise SpKeywordFileError(NO_SP_SHEET_MESSAGE)
    return _keyword_export(_read(lambda: pd.read_excel(workbook, sheet_name=0)))


def _read_csv(file_bytes: bytes) -> pd.DataFrame:
    # Excel in a Spanish locale re-saves a CSV with ";" and cp1252.
    encoding = encoding_csv(file_bytes)
    return pd.read_csv(io.BytesIO(file_bytes), encoding=encoding, sep=sep_csv(file_bytes, encoding))


def _read(reader):
    try:
        return reader()
    except _READ_ERRORS as exc:
        raise SpKeywordFileError(NOT_READABLE_MESSAGE) from exc


def _bulk_file(sheet: pd.DataFrame) -> SpKeywordFile:
    if not set(_BULK_COLUMNS) <= set(sheet.columns):
        raise SpKeywordFileError(BULK_COLUMNS_MESSAGE)
    # The Bulk rows under the listing's names, so the rule that decides what runs is the listing's own.
    structure_rows = pd.DataFrame({
        "entity": sheet["Entity"].astype(str).str.strip().map(_BULK_ENTITIES),
        "state": sheet["State"],
        "campaign_id": sheet["Campaign ID"],
        "ad_group_id": sheet["Ad Group ID"],
        "target_text": sheet["Keyword Text"].fillna(""),
    })
    return SpKeywordFile(active_keyword_texts(structure_rows), CHECKED_KEYWORD_CAMPAIGN_AD_GROUP)


def _keyword_export(export: pd.DataFrame) -> SpKeywordFile:
    keyword_column = _keyword_column(export.columns)
    if keyword_column is None or _campaign_targeting(export[keyword_column]):
        raise SpKeywordFileError(NO_KEYWORD_COLUMN_MESSAGE)
    rows = export[~_negative_rows(export)]
    state_column = _named_column(export.columns, (_STATE_COLUMN,))
    if state_column is not None:
        rows = rows[_lowered(rows[state_column]).isin(_RUNNING_STATES)]
    status_column = _named_column(export.columns, (_DELIVERY_STATUS_COLUMN,))
    if status_column is not None:
        rows = rows[~_lowered(rows[status_column]).str.contains(_STOPPED_DELIVERY, regex=True)]
    texts = (normalized_keyword(text) for text in rows[keyword_column].dropna())
    return SpKeywordFile(frozenset(text for text in texts if text),
                         _checked_states(state_column is not None, status_column is not None))


def _checked_states(has_state: bool, has_delivery_status: bool) -> str:
    if has_state and has_delivery_status:
        return CHECKED_KEYWORD_CAMPAIGN_AD_GROUP
    # A Status alone may be another tool's enabled/paused, so it vouches for the keyword and nothing more.
    return CHECKED_KEYWORD if has_state or has_delivery_status else CHECKED_NONE


def _campaign_targeting(keyword_column: pd.Series) -> bool:
    values = set(_lowered(keyword_column.dropna())) - {""}
    return bool(values) and values <= _CAMPAIGN_TARGETING_TYPES


def _lowered(column: pd.Series) -> pd.Series:
    return column.astype(str).str.strip().str.lower()


def _keyword_column(columns: pd.Index):
    named = _named_column(columns, _KEYWORD_COLUMN_NAMES)
    if named is not None:
        return named
    lowered = {column: str(column).strip().lower() for column in columns}
    return (next((column for column, name in lowered.items() if "keyword" in name and "text" in name), None)
            or next((column for column, name in lowered.items() if "targeting" in name and "type" not in name), None))


def _named_column(columns: pd.Index, names: tuple[str, ...]):
    by_name = {str(column).strip().lower(): column for column in columns}
    return next((by_name[name] for name in names if name in by_name), None)


def _negative_rows(export: pd.DataFrame) -> pd.Series:
    negative = pd.Series(False, index=export.index)
    for column in (_named_column(export.columns, ("entity",)), _named_column(export.columns, ("match type",))):
        if column is not None:
            negative |= export[column].astype(str).str.lower().str.contains("negative", regex=False)
    return negative
