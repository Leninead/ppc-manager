"""El payload del agente del Bid Optimizer, armado con sus reglas (core/bid_optimizer/bids.py), sin Streamlit.

Lo usan la página y el worker de análisis, así que no puede vivir en `modules/pages/`: mismos
datos y mismos parámetros tienen que dar la misma huella corra donde corra.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ai.agents.bid_optimizer.context import MAX_ASINS, MAX_CAMPAIGNS, BidData
from core.bid_optimizer.bids import (
    bids_by_asin,
    campaign_placements,
    detect_columns,
    previous_bid_figures,
    resolve_asin_column,
    validated_spend_share,
)

ANALYSIS_MODULE = "bid_optimizer"
CANONICAL_LANG = "es"
# La misma ventana en la que abre el picker: si difieren, lo que ve el AM nunca encuentra su análisis.
CANONICAL_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 60


def bid_ai_records(df_asin, cols, col_asin, keep, *, validated_share=None, previous=None):
    """Serializa las filas por ASIN para el agente — tipos nativos, las de mayor spend primero.

    `validated_share` y `previous` son opcionales: cuando faltan, sus campos NO viajan, y el prompt
    tiene la regla de no comparar contra lo que no está en el documento.
    """
    validated_share = validated_share or {}
    previous = previous or {}
    top = df_asin.sort_values(cols["spend"], ascending=False).head(keep)
    records = []
    for _, row in top.iterrows():
        asin = str(row[col_asin]).strip()
        record = {
        "asin": asin,
        "clicks": int(row[cols["clicks"]]),
        "orders": int(row[cols["orders"]]),
        "cvr": round(float(row["_cvr"]), 2),
        "price": round(float(row["_precio"]), 2),
        "spend": round(float(row[cols["spend"]]), 2),
        "sales": round(float(row[cols["sales"]]), 2),
        "acos": round(float(row["_acos"]), 1),
        "bid_base": float(row["_bid_base"]),
        "estado": str(row["Estado"]).split(" ", 1)[-1],
        }
        if asin in validated_share:
            record["pct_spend_validado"] = validated_share[asin]
        before = previous.get(asin)
        if before is not None:
            record.update({f"{key}_previo": value for key, value in before.items()})
        records.append(record)
    return records


def bid_row_labels(records):
    """row_id -> ASIN, para anotar los ids que la síntesis y el chat citan (A03)."""
    return {f"A{i + 1:02d}": str(rec.get("asin", "")).strip()
            for i, rec in enumerate(records or [])}


def canonical_analysis_window(data_from: date | None, data_through: date) -> tuple[date, date]:
    earliest = data_from or data_through - timedelta(days=MAX_WINDOW_DAYS - 1)
    return max(earliest, data_through - timedelta(days=CANONICAL_WINDOW_DAYS - 1)), data_through


@dataclass(frozen=True)
class BidAnalysisInput:
    """El payload del agente más las filas a las que apuntan sus row_ids."""

    data: BidData | None
    records: list


def build_analysis_input(frame, *, target_acos: int, account_label: str, period_label: str,
                         currency_code: str, lang: str = CANONICAL_LANG,
                         price_map: dict | None = None, previous_frame=None) -> BidAnalysisInput:
    """Arma el payload del agente desde el frame canónico del Search Term Report."""
    if frame.empty:
        return BidAnalysisInput(None, [])
    cols = detect_columns(frame)
    if any(cols[key] is None for key in ("clicks", "orders", "sales", "spend")):
        return BidAnalysisInput(None, [])
    with_asin, col_asin, asin_source = resolve_asin_column(frame, cols)
    if col_asin is None:
        return BidAnalysisInput(None, [])

    by_asin = bids_by_asin(with_asin, cols, col_asin, target_acos, price_map or {})
    records = bid_ai_records(by_asin, cols, col_asin, MAX_ASINS,
                             validated_share=validated_spend_share(with_asin, cols, col_asin),
                             previous=previous_bid_figures(previous_frame, target_acos, price_map))
    if not records:
        return BidAnalysisInput(None, [])
    campaigns = campaign_placements(with_asin, cols)[:MAX_CAMPAIGNS] if cols["campaign"] else []
    return BidAnalysisInput(
        BidData(
            account_label=account_label,
            period_label=period_label,
            currency_code=currency_code,
            target_acos=target_acos,
            price_source="Inventory Report" if price_map else "STR (precio promedio de venta)",
            asin_source=asin_source,
            total_asins=len(by_asin),
            asins=records,
            campaigns=campaigns,
            has_previous=any("clicks_previo" in record for record in records),
            idioma=lang,
        ),
        records,
    )
