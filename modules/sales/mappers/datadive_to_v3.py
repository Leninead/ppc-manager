"""Mapper DataDive MKL → bloque V3_seo_opportunity.

Convierte el output de `modules.parsers.datadive.parse_mkl` (DataFrame + lista de
ASINs competidores) en un `ImportReport` con UN `BlockDraft` para el módulo
`V3_seo_opportunity`. El report es consumible tal cual por `merge_blocks` del
importer B7 — no se duplica lógica de merge ni de persistencia.

Función pura: NO importa Streamlit, NO toca disco.

Decisiones (Lenin 2026-05-26):
  D1  opportunity_score = min(launch_score / 10, 1.0)  (None si no hay launch_score)
  D3  "missing keyword" = current_rank > 30 OR current_rank ausente (NaN/None)
  D6  launch_score_table y page1_domination_chart_data = [] en v1
  D8  cap interno a top _MAX_MISSING_KEYWORDS por SV desc (evita inflar la propuesta)
"""
from __future__ import annotations

import re

import pandas as pd

from modules.parsers.datadive import COL_LAUNCH_SCORE, COL_SEARCH_TERM, COL_SV
from modules.sales.b7_importer import (
    BlockDraft,
    ImportError,
    ImportReport,
    ImportWarning,
)

V3_MODULE_ID = "V3_seo_opportunity"
WEAK_RANK_THRESHOLD = 30
_MAX_MISSING_KEYWORDS = 50
_ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")


def datadive_to_v3_block(
    mkl_df: pd.DataFrame,
    competitor_asins: list[str],
    client_asin: str,
    language: str = "es",
) -> ImportReport:
    """DataDive MKL → ImportReport(1 BlockDraft V3_seo_opportunity).

    Args:
        mkl_df: DataFrame de parse_mkl (cols Search Term/SV/.../<ASIN ranks>).
        competitor_asins: ASINs detectados por parse_mkl (columnas de rank).
        client_asin: ASIN del cliente; se valida contra ^B0[A-Z0-9]{8}$.
        language: reservado — el data de V3 es numérico/keyword, no se traduce.

    Returns:
        ImportReport. Si client_asin es inválido → report con error 'invalid_asin'
        (sin blocks). Si es válido → 1 BlockDraft con missing_keywords filtradas.
    """
    asin = (client_asin or "").strip().upper()
    if not _ASIN_RE.match(asin):
        return ImportReport(errors=[ImportError(
            code="invalid_asin",
            block_index=0,
            module_id=V3_MODULE_ID,
            message=f"client_asin {client_asin!r} no matchea ^B0[A-Z0-9]{{8}}$.",
        )])

    warnings: list[ImportWarning] = []
    if asin not in (competitor_asins or []):
        warnings.append(ImportWarning(
            code="client_asin_not_in_mkl",
            block_index=0,
            module_id=V3_MODULE_ID,
            field_path="missing_keywords",
            message=(
                f"client_asin {asin} no está entre los ASINs del MKL "
                f"({competitor_asins}); todas las keywords se tratan como missing "
                f"(current_rank=None)."
            ),
        ))

    missing: list[dict] = []
    has_client_col = (
        isinstance(mkl_df, pd.DataFrame)
        and not mkl_df.empty
        and asin in mkl_df.columns
    )

    if isinstance(mkl_df, pd.DataFrame) and not mkl_df.empty and COL_SEARCH_TERM in mkl_df.columns:
        df = mkl_df.copy()
        if COL_SV in df.columns:
            df = df.sort_values(COL_SV, ascending=False, kind="stable")

        for _, row in df.iterrows():
            keyword = str(row.get(COL_SEARCH_TERM, "")).strip()
            if not keyword or keyword.lower() == "nan":
                continue

            current_rank = None
            if has_client_col:
                rv = row.get(asin)
                if pd.notna(rv):
                    current_rank = int(rv)

            # D3: missing si no rankea (None) o rankea débil (> 30).
            is_missing = current_rank is None or current_rank > WEAK_RANK_THRESHOLD
            if not is_missing:
                continue

            sv_raw = row.get(COL_SV)
            sv = int(sv_raw) if pd.notna(sv_raw) else None

            launch_raw = row.get(COL_LAUNCH_SCORE)
            opportunity_score = None
            if pd.notna(launch_raw):
                opportunity_score = round(min(float(launch_raw) / 10.0, 1.0), 2)  # D1

            missing.append({
                "keyword": keyword,
                "sv": sv,
                "current_rank": current_rank,
                "opportunity_score": opportunity_score,
            })

    # D8: cap a top N (ya viene ordenado por SV desc).
    if len(missing) > _MAX_MISSING_KEYWORDS:
        warnings.append(ImportWarning(
            code="missing_keywords_truncated",
            block_index=0,
            module_id=V3_MODULE_ID,
            field_path="missing_keywords",
            message=(
                f"{len(missing)} missing keywords detectadas; se truncan a las "
                f"top {_MAX_MISSING_KEYWORDS} por SV."
            ),
        ))
        missing = missing[:_MAX_MISSING_KEYWORDS]

    data = {
        "missing_keywords": missing,
        "launch_score_table": [],          # D6
        "page1_domination_chart_data": [],  # D6
    }
    draft = BlockDraft(
        module_id=V3_MODULE_ID,
        data=data,
        block_index=0,
        contract_version="1.0",
    )
    return ImportReport(blocks=[draft], warnings=warnings)
