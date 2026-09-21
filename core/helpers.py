import html
import streamlit as st
import pandas as pd
import re


def _color_pct(val):
    """Cell style for % change columns."""
    if pd.isna(val):
        return ""
    if val > 0:
        return "color: #28a745; font-weight: bold"
    if val < 0:
        return "color: #dc3545; font-weight: bold"
    return "color: gray"


def extract_sqp_brand(file):
    """Extrae el nombre de marca de la fila de metadata del SQP de Amazon."""
    try:
        first_row = pd.read_csv(file, nrows=0, header=None).columns[0] if not file.name.endswith(".xlsx") else str(pd.read_excel(file, nrows=1, header=None).iloc[0, 0])
        file.seek(0)
        match = re.search(r'Brand=\["([^"]+)"\]', first_row, re.IGNORECASE)
        if match:
            return match.group(1).lower().strip()
    except Exception:
        pass
    file.seek(0)
    return None


@st.cache_data(max_entries=5, ttl=3600, show_spinner=False)
def read_sqp(file):
    """Lee un archivo SQP de Amazon, saltando la fila de metadata inicial."""
    if file.name.endswith(".xlsx"):
        return pd.read_excel(file, skiprows=1)
    return pd.read_csv(file, skiprows=1)


def kpi_card(label, value, delta=None, delta_good=True, caption=None):
    """Genera HTML de KPI card estilo Capybaras. Usar con st.markdown(..., unsafe_allow_html=True).

    `caption` es una línea chica debajo del valor (texto plano)."""
    delta_html = ""
    if delta is not None:
        try:
            d = float(delta)
            color = "#1B6B2F" if (delta_good and d > 0) or (not delta_good and d < 0) else "#B71C1C"
            if d == 0:
                color = "#888"
            arrow = "↑" if d > 0 else "↓" if d < 0 else "→"
            delta_html = (
                f"<div style='font-size:0.72rem;color:{color};font-weight:600;'>"
                f"{arrow} {abs(d):.1f}%</div>"
            )
        except (ValueError, TypeError):
            pass
    # "$" escaped so Streamlit never reads two amounts as a LaTeX span.
    caption_html = (f"<div style='font-size:0.72rem;color:#888;font-weight:600;'>"
                    f"{html.escape(str(caption)).replace('$', '&#36;')}</div>" if caption else "")
    return (
        f"<div style='background:#FFF3E0;border:1px solid #FFD9B3;border-radius:10px;"
        f"padding:0.8rem 1rem;text-align:center;'>"
        f"<div style='font-size:0.72rem;color:#888;font-weight:600;text-transform:uppercase;"
        f"letter-spacing:0.05em;'>{label}</div>"
        f"<div style='font-size:1.4rem;font-weight:800;color:#1F1F1F;margin:0.2rem 0;'>{value}</div>"
        f"{delta_html}{caption_html}"
        f"</div>"
    )
