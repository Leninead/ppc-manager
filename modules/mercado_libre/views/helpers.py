"""Presentation helpers shared by the module views.

Match the rest of the Agency OS: orange accent, dashed-border empty states,
colored status badges.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from modules.mercado_libre import config


def empty_state(title: str, detail: str) -> None:
    """Empty-state block matching the other modules."""
    st.markdown(
        f"<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:32px;"
        f"text-align:center;background:#FFF8F0;'>"
        f"<h3 style='color:{config.COLOR_ACENTO};margin-top:0;'>{title}</h3>"
        f"<p style='color:#6B7280;margin:0;'>{detail}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


def badge(text: str, color: str) -> str:
    """Color pill for statuses and alert levels."""
    return (
        f"<span style='padding:3px 10px;border-radius:100px;"
        f"background:{color}18;border:1px solid {color}55;color:{color};"
        f"font-size:0.75rem;font-weight:600;'>{text}</span>"
    )


def fmt_pct(value, decimals: int = 1) -> str:
    """Format a fraction as a signed percentage."""
    if value is None or pd.isna(value):
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.{decimals}f}%"


def fmt_num(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{int(value):,}".replace(",", ".")


def fmt_money(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"${value:,.0f}".replace(",", ".")


def fmt_decimal(value, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{decimals}f}"


def color_variation(value):
    """Cell style for delta columns."""
    if pd.isna(value):
        return ""
    if value > 0:
        return f"color: {config.COLOR_MEJORO}; font-weight: bold"
    if value < 0:
        return f"color: {config.COLOR_EMPEORO}; font-weight: bold"
    return ""


def color_result(value):
    """Cell style for the tracker's result column."""
    color = config.COLOR_RESULTADO.get(value)
    return f"color: {color}; font-weight: 600" if color else ""


def link_listing(mla: str) -> str:
    """MLA ids are not directly navigable: build the panel link."""
    return f"https://articulo.mercadolibre.com.ar/{mla[:3]}-{mla[3:]}"
