"""Helpers de presentación compartidos por las vistas del módulo.

Replican las convenciones visuales del resto del Agency OS: acento naranja,
empty states con borde punteado y badges de color por estado.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from modules.mercado_libre import config


def empty_state(titulo: str, detalle: str) -> None:
    """Bloque de estado vacío con el estilo del resto de los módulos."""
    st.markdown(
        f"<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:32px;"
        f"text-align:center;background:#FFF8F0;'>"
        f"<h3 style='color:{config.COLOR_ACENTO};margin-top:0;'>{titulo}</h3>"
        f"<p style='color:#6B7280;margin:0;'>{detalle}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


def badge(texto: str, color: str) -> str:
    """Píldora de color para estados y niveles de alerta."""
    return (
        f"<span style='padding:3px 10px;border-radius:100px;"
        f"background:{color}18;border:1px solid {color}55;color:{color};"
        f"font-size:0.75rem;font-weight:600;'>{texto}</span>"
    )


def fmt_pct(valor, decimales: int = 1) -> str:
    """Formatea una fracción como porcentaje con signo explícito."""
    if valor is None or pd.isna(valor):
        return "—"
    signo = "+" if valor > 0 else ""
    return f"{signo}{valor * 100:.{decimales}f}%"


def fmt_num(valor) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{int(valor):,}".replace(",", ".")


def fmt_money(valor) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"${valor:,.0f}".replace(",", ".")


def fmt_decimal(valor, decimales: int = 2) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor:.{decimales}f}"


def color_variacion(valor):
    """Estilo de celda para columnas de variación."""
    if pd.isna(valor):
        return ""
    if valor > 0:
        return f"color: {config.COLOR_MEJORO}; font-weight: bold"
    if valor < 0:
        return f"color: {config.COLOR_EMPEORO}; font-weight: bold"
    return ""


def color_resultado(valor):
    """Estilo de celda para la columna de resultado del tracker."""
    color = config.COLOR_RESULTADO.get(valor)
    return f"color: {color}; font-weight: 600" if color else ""


def link_publicacion(mla: str) -> str:
    """Los MLA no son navegables directamente: se arma el link al panel."""
    return f"https://articulo.mercadolibre.com.ar/{mla[:3]}-{mla[3:]}"
