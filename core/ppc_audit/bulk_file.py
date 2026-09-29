"""A hand-uploaded Bulk File (Campaign Manager → Bulk Operations) read into AuditFrames, sheet by sheet."""
from __future__ import annotations

import io

import pandas as pd

from core.bulk.parser import _id_to_str
from core.ppc_audit.frames import ENTITY, AuditFrames, empty_frame
from core.search_term.frame import SOURCE_FILE

SP_SHEET = "Sponsored Products Campaigns"
SB_SHEET = "Sponsored Brands Campaigns"
SD_SHEET = "Sponsored Display Campaigns"
SP_SEARCH_TERM_SHEET = "SP Search Term Report"
SB_SEARCH_TERM_SHEET = "SB Search Term Report"
# One grain for SD's waste: the targets. Its ad group rows carry the sum of their targets.
SD_TARGET_ENTITIES = ("Product Targeting", "Audience Targeting", "Contextual Targeting")

_COUNT_METRICS = ("Impressions", "Clicks", "Spend", "Sales", "Orders", "Units")
_RATIO_METRICS = ("ACOS", "Click-through Rate", "Conversion Rate", "CPC", "ROAS")
_ID_COLUMNS = ("Campaign ID", "Ad Group ID", "Keyword ID", "Product Targeting ID", "Portfolio ID", "Ad ID")


def frames_from_bulk_file(file_bytes: bytes) -> AuditFrames:
    """Raises ValueError when the bytes are not a readable .xlsx."""
    workbook = pd.ExcelFile(io.BytesIO(file_bytes))
    sp = _sheet(workbook, SP_SHEET)
    sb = _sheet(workbook, SB_SHEET)
    sd = _sheet(workbook, SD_SHEET)
    return AuditFrames(
        sp_campaigns=_entities(sp, "Campaign"),
        sp_ad_groups=_entities(sp, "Ad Group"),
        sp_keywords=_entities(sp, "Keyword"),
        sp_product_targets=_entities(sp, "Product Targeting"),
        sp_product_ads=_entities(sp, "Product Ad"),
        sp_placements=_entities(sp, "Bidding Adjustment"),
        sp_search_terms=_sheet(workbook, SP_SEARCH_TERM_SHEET),
        sb_campaigns=_entities(sb, "Campaign"),
        sb_keywords=_entities(sb, "Keyword"),
        sb_search_terms=_sheet(workbook, SB_SEARCH_TERM_SHEET),
        sd_campaigns=_entities(sd, "Campaign"),
        sd_targets=_entities(sd, *SD_TARGET_ENTITIES),
        source=SOURCE_FILE,
    )


def _sheet(workbook: pd.ExcelFile, name: str) -> pd.DataFrame:
    if name not in workbook.sheet_names:
        return pd.DataFrame()
    sheet = pd.read_excel(workbook, sheet_name=name)
    sheet.columns = sheet.columns.str.strip()
    for column in _COUNT_METRICS:
        if column in sheet.columns:
            sheet[column] = pd.to_numeric(sheet[column], errors="coerce").fillna(0)
    for column in _RATIO_METRICS:
        if column in sheet.columns:
            sheet[column] = pd.to_numeric(sheet[column].astype(str).str.replace(r"[\$%,]", "", regex=True),
                                          errors="coerce").fillna(0)
    # Excel reads an id column with gaps as floats: as text they join across entities and sheets.
    for column in _ID_COLUMNS:
        if column in sheet.columns:
            sheet[column] = sheet[column].map(_id_to_str)
    return sheet


def _entities(sheet: pd.DataFrame, *labels: str) -> pd.DataFrame:
    if sheet.empty or ENTITY not in sheet.columns:
        return empty_frame((ENTITY,))
    return sheet[sheet[ENTITY].isin(labels)].reset_index(drop=True)
