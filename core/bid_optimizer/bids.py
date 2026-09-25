"""Las reglas del Bid Optimizer: el ASIN de cada término, el bid sugerido por ASIN y los placements del SOP.

Las leen la página, el worker de análisis y el servidor MCP: nada acá puede importar Streamlit ni un agente.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from core.amazon_ads.advertised_asins import asins_from_campaigns

DEFAULT_TARGET_ACOS = 25

# El reporte spSearchTerm de Amazon no trae el ASIN anunciado: cuando no viene en el archivo,
# el Bid Optimizer lo toma del nombre de la campaña.
ASIN_FROM_FILE = "columna Advertised ASIN del archivo"
ASIN_FROM_CAMPAIGN = "extraído del nombre de la campaña"

NO_ASIN_WARNING = (
    "El Search Term Report de Amazon Ads no incluye el ASIN anunciado, y ningún nombre de campaña "
    "de este período contiene uno (formato B0XXXXXXXX). Sin ASIN no se puede calcular el bid por "
    "producto. Si el naming de la cuenta no lleva el ASIN, usá el Campaign Builder para renombrar "
    "las campañas, o subí a mano un STR que traiga la columna Advertised ASIN."
)


def _limpiar_num(val):
    """Limpia $, %, comas y convierte a float. Retorna 0.0 si falla."""
    try:
        return float(str(val).replace("$", "").replace("%", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _numeric_column(series):
    """Columna como float. El frame de Amazon Ads ya llega numérico; el archivo a mano no.

    Una cuenta grande trae cientos de miles de filas, y limpiar cada celda a mano cuesta
    segundos sobre columnas que pandas ya sabe leer de una.
    """
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0.0).astype("float64")
    return series.apply(_limpiar_num)


# ── Placement modifiers por tipo de campaña (SOP Capybaras 2026) ────────
# El budget viaja como número: la moneda la pone la cuenta, no el SOP.
_PLACEMENT_RULES = [
    {"Tipo de Campaña": "Exact Ranking", "ToS Modifier %": 50, "PDP Modifier %": 0,
     "budget_min": 10, "budget_max": 15},
    {"Tipo de Campaña": "Exact Harvest / Profit", "ToS Modifier %": 25, "PDP Modifier %": 0,
     "budget_min": 8, "budget_max": 12},
    {"Tipo de Campaña": "Phrase Discovery", "ToS Modifier %": 10, "PDP Modifier %": 0,
     "budget_min": 8, "budget_max": 12},
    {"Tipo de Campaña": "Broad Discovery", "ToS Modifier %": 0, "PDP Modifier %": 0,
     "budget_min": 8, "budget_max": 12},
    {"Tipo de Campaña": "Auto All", "ToS Modifier %": 0, "PDP Modifier %": 0,
     "budget_min": 8, "budget_max": 12},
    {"Tipo de Campaña": "PAT Competitor", "ToS Modifier %": 0, "PDP Modifier %": 50,
     "budget_min": 5, "budget_max": 8},
    {"Tipo de Campaña": "Brand Defensive", "ToS Modifier %": 25, "PDP Modifier %": 0,
     "budget_min": 5, "budget_max": 8},
]


def detect_campaign_type(name):
    """Clasifica el tipo de campaña por naming convention."""
    n = str(name).lower()
    if "pat" in n or "asin" in n or "competitor" in n or "conquest" in n:
        return "PAT Competitor"
    if "brand" in n or "defensive" in n or "defense" in n:
        return "Brand Defensive"
    if "exact" in n and ("rank" in n or "hero" in n or "core" in n):
        return "Exact Ranking"
    if "exact" in n and ("harvest" in n or "profit" in n or "winner" in n):
        return "Exact Harvest / Profit"
    if "exact" in n:
        return "Exact Ranking"
    if "phrase" in n:
        return "Phrase Discovery"
    if "broad" in n:
        return "Broad Discovery"
    if "auto" in n or "discovery" in n:
        return "Auto All"
    return "Broad Discovery"


def placement_for_type(camp_type):
    """Retorna (tos%, pdp%) para un tipo de campaña."""
    for rule in _PLACEMENT_RULES:
        if rule["Tipo de Campaña"] == camp_type:
            return rule["ToS Modifier %"], rule["PDP Modifier %"]
    return 0, 0


def budget_midpoint(camp_type):
    """Punto medio del rango de budget del SOP para ese tipo, en unidades de la cuenta."""
    for rule in _PLACEMENT_RULES:
        if rule["Tipo de Campaña"] == camp_type:
            return (rule["budget_min"] + rule["budget_max"]) / 2
    return 10.0


def detect_columns(df):
    """Mapea las columnas del STR que el módulo necesita. Valor None = no encontrada."""
    def first(match):
        return next((c for c in df.columns if match(str(c).lower())), None)

    return {
        "asin": first(lambda c: "advertised asin" in c),
        "match_type": first(lambda c: "match type" in c),
        "campaign": first(lambda c: "campaign name" in c),
        "clicks": first(lambda c: "clicks" in c),
        "orders": first(lambda c: "orders" in c),
        # Ventas antes que ACoS: el nombre del ACoS también dice "sales".
        "sales": first(lambda c: "sales" in c and "other" not in c and "advertised" not in c),
        "spend": first(lambda c: "spend" in c),
    }


def resolve_asin_column(df, cols):
    """Devuelve (df, nombre de columna de ASIN o None, origen legible del ASIN).

    El frame de Amazon Ads nunca trae Advertised ASIN, así que el nombre de campaña deja de
    ser un fallback y pasa a ser el camino normal: de dónde salió el ASIN cambia cuánto vale
    la agrupación, y por eso se devuelve y se muestra.
    """
    if cols["asin"] is not None:
        return df, cols["asin"], ASIN_FROM_FILE
    if cols["campaign"] is None:
        return df, None, ""
    extracted = asins_from_campaigns(df[cols["campaign"]])
    if not extracted.notna().any():
        return df, None, ""
    with_asin = df.copy()
    with_asin["_extracted_asin"] = extracted
    return with_asin, "_extracted_asin", ASIN_FROM_CAMPAIGN


# Match types donde el targeting ya está validado: un ACoS alto ahí pesa distinto que en descubrimiento.
VALIDATED_MATCH_TYPES = ("exact", "phrase")


def validated_spend_share(df, cols, col_asin) -> dict:
    """ASIN -> % del spend que corre sobre match types ya validados (exact/phrase).

    Con esto el agente distingue "todavía paga por descubrir keywords" de "el ACoS alto es sobre
    targeting probado" con un campo de Amazon, en vez de adivinarlo del nombre de la campaña.
    """
    if cols.get("match_type") is None:
        return {}
    spend = _numeric_column(df[cols["spend"]])
    validated = df[cols["match_type"]].astype(str).str.lower().isin(VALIDATED_MATCH_TYPES)
    by_asin = pd.DataFrame({"asin": df[col_asin], "spend": spend, "validated": spend.where(validated, 0.0)})
    totals = by_asin.groupby("asin").agg({"spend": "sum", "validated": "sum"})
    return {asin: round(row["validated"] / row["spend"] * 100, 1) if row["spend"] > 0 else 0.0
            for asin, row in totals.iterrows()}


def estado_por_cvr(cvr, clicks, orders):
    """Semáforo del ASIN. Sin clicks no hay señal en ninguna dirección."""
    if clicks == 0:
        return "⚫ SIN DATA"
    if cvr > 15 and orders > 5:
        return "🟢 ESCALAR"
    if 8 <= cvr <= 15:
        return "🟡 OK"
    return "🔴 REVISAR"


def bids_by_asin(df, cols, col_asin, target_acos, precio_map=None):
    """Agrupa el STR por ASIN y calcula CVR, precio, ACoS, bid base y estado.

    bid base = CVR × precio × target ACoS. Sin órdenes no hay CVR medido, y el bid queda en 0.
    """
    precio_map = precio_map or {}
    clicks, orders, sales, spend = cols["clicks"], cols["orders"], cols["sales"], cols["spend"]
    numeric = df.copy()
    for column in (clicks, orders, sales, spend):
        numeric[column] = _numeric_column(numeric[column])

    grouped = numeric.groupby(col_asin, as_index=False).agg(
        {clicks: "sum", orders: "sum", sales: "sum", spend: "sum"})

    grouped["_cvr"] = [
        (o / c * 100) if c > 0 else 0.0 for c, o in zip(grouped[clicks], grouped[orders])]
    grouped["_precio"] = [
        _precio_de_lista(precio_map, asin) if _precio_de_lista(precio_map, asin) else
        (s / o if o > 0 else 0.0)
        for asin, s, o in zip(grouped[col_asin], grouped[sales], grouped[orders])]
    grouped["_acos"] = [
        (sp / s * 100) if s > 0 else 0.0 for sp, s in zip(grouped[spend], grouped[sales])]
    grouped["_bid_base"] = [
        round((cvr / 100) * price * (target_acos / 100), 2) if o > 0 else 0.0
        for cvr, price, o in zip(grouped["_cvr"], grouped["_precio"], grouped[orders])]
    grouped["Estado"] = [
        estado_por_cvr(cvr, c, o)
        for cvr, c, o in zip(grouped["_cvr"], grouped[clicks], grouped[orders])]
    return grouped


def previous_by_asin(df_asin, cols, col_asin) -> dict:
    """ASIN -> métricas del período anterior, con las mismas claves que la fila actual."""
    return {str(row[col_asin]).strip(): {
        "clicks": int(row[cols["clicks"]]),
        "orders": int(row[cols["orders"]]),
        "cvr": round(float(row["_cvr"]), 2),
        "price": round(float(row["_precio"]), 2),
        "spend": round(float(row[cols["spend"]]), 2),
        "acos": round(float(row["_acos"]), 1),
        "bid_base": float(row["_bid_base"]),
    } for _, row in df_asin.iterrows()}


def previous_bid_figures(previous_frame, target_acos: int, price_map: dict | None = None) -> dict:
    """Las métricas del período anterior por ASIN, o vacío si no hay con qué comparar."""
    if previous_frame is None or previous_frame.empty:
        return {}
    cols = detect_columns(previous_frame)
    if any(cols[key] is None for key in ("clicks", "orders", "sales", "spend")):
        return {}
    with_asin, col_asin, _ = resolve_asin_column(previous_frame, cols)
    if col_asin is None:
        return {}
    return previous_by_asin(bids_by_asin(with_asin, cols, col_asin, target_acos, price_map or {}), cols, col_asin)


def previous_window(start: date, end: date) -> tuple[date, date]:
    """El tramo inmediatamente anterior, del mismo largo: con qué se compara el período en pantalla."""
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def _precio_de_lista(precio_map, asin):
    price = precio_map.get(str(asin).strip(), 0.0)
    return price if price > 0 else 0.0


def campaign_placements(df, cols):
    """Una fila por campaña con su tipo detectado, placements del SOP y métricas del período."""
    campaign, spend, sales, orders = cols["campaign"], cols["spend"], cols["sales"], cols["orders"]
    # Un solo groupby: filtrar el frame una vez por campaña costaba 12s en una cuenta de
    # 177.000 términos con 1.841 campañas.
    numeric = df[[campaign, spend, sales, orders]].copy()
    for column in (spend, sales, orders):
        numeric[column] = _numeric_column(numeric[column])

    grouped = (numeric.dropna(subset=[campaign])
               .groupby(campaign, as_index=False)
               .agg({spend: "sum", sales: "sum", orders: "sum"})
               .sort_values(campaign))

    rows = []
    for name, camp_spend, camp_sales, camp_orders in zip(
            grouped[campaign], grouped[spend], grouped[sales], grouped[orders]):
        camp_type = detect_campaign_type(name)
        tos, pdp = placement_for_type(camp_type)
        rows.append({
            "Campaign": str(name)[:60],
            "Tipo Detectado": camp_type,
            "ToS %": tos,
            "PDP %": pdp,
            "Spend": round(camp_spend, 2),
            "Sales": round(camp_sales, 2),
            "ACoS %": round((camp_spend / camp_sales * 100) if camp_sales > 0 else 0, 1),
            "Orders": int(camp_orders),
        })
    return rows


@dataclass(frozen=True)
class BidAnalysisParams:
    """Lo único que el AM elige en la pantalla y cambia el análisis."""

    target_acos: int

    @classmethod
    def defaults(cls) -> BidAnalysisParams:
        return cls(DEFAULT_TARGET_ACOS)

    @classmethod
    def from_dict(cls, values: dict) -> BidAnalysisParams:
        try:
            target_acos = int(values.get("target_acos", DEFAULT_TARGET_ACOS))
        except (TypeError, ValueError):
            target_acos = DEFAULT_TARGET_ACOS
        return cls(target_acos)

    def as_dict(self) -> dict:
        return {"target_acos": self.target_acos}

    @property
    def digest(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
