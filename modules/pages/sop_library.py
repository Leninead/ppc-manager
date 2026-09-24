"""📂 SOPs / Drive AM and 📂 SOPs / Drive PPC — one page per team over one SOP catalog, grouped by category."""
from __future__ import annotations

import html
from datetime import date

import streamlit as st

from core.sop_library import (
    ALL_CATEGORIES,
    CATEGORIES_BY_AREA,
    SOPS,
    badges,
    detect_doc_type,
    filter_sops,
    sops_for_area,
    validate_catalog,
)
from core.ui import i18n, palette
from core.ui.kpi_grid import Kpi, render_kpi_grid

_GRID_COLUMNS = 3


def _header(area: str) -> None:
    if area == "PPC":
        st.markdown(f"## {i18n.t('sop_library.header_title_ppc')}")
        st.caption(i18n.t("sop_library.header_caption_ppc"))
    else:
        st.markdown(f"## {i18n.t('sop_library.header_title')}")
        st.caption(i18n.t("sop_library.header_caption"))
    st.divider()


def _render_kpis(sops: list, today: date) -> None:
    categories_in_use = {sop["category"] for sop in sops}
    to_review = sum(1 for sop in sops if "review" in badges(sop, today))
    render_kpi_grid([
        Kpi(i18n.t("sop_library.kpi_total"), str(len(sops))),
        Kpi(i18n.t("sop_library.kpi_categories"), str(len(categories_in_use))),
        Kpi(i18n.t("sop_library.kpi_review"), str(to_review)),
    ])


def _category_options(sops: list, area: str) -> list[str]:
    in_use = {sop["category"] for sop in sops}
    return [ALL_CATEGORIES] + [category for category in CATEGORIES_BY_AREA[area] if category in in_use]


def _category_label(option: str) -> str:
    return i18n.t("sop_library.category_all") if option == ALL_CATEGORIES else option


def _badge_chip(text: str, ink: str, glow: str) -> str:
    return (
        f"<span style='display:inline-block;background:{glow};color:{ink};"
        f"border-radius:999px;padding:0.1rem 0.55rem;font-size:0.72rem;font-weight:600;"
        f"margin-right:0.3rem;'>{html.escape(text)}</span>"
    )


def _badges_html(sop: dict, today: date) -> str:
    chips = []
    for badge in badges(sop, today):
        if badge == "new":
            chips.append(_badge_chip(i18n.t("sop_library.badge_new"), palette.OK_INK, palette.OK_GLOW))
        elif badge == "review":
            chips.append(_badge_chip(i18n.t("sop_library.badge_review"), palette.WARN_INK, palette.WARN_GLOW))
    return f"<div style='margin:0.2rem 0 0.4rem;'>{''.join(chips)}</div>" if chips else ""


def _render_card(sop: dict, today: date) -> None:
    doc_type = detect_doc_type(sop["url"])
    with st.container(border=True):
        st.markdown(
            f"{doc_type['icon']} :gray[{i18n.t('sop_library.doc_type.' + doc_type['key'])}]"
        )
        st.markdown(
            f"<div style='font-weight:700;color:{palette.FG};line-height:1.3;'>"
            f"{html.escape(sop['title'])}</div>"
            f"{_badges_html(sop, today)}"
            f"<div style='color:{palette.FG_MUTED};font-size:0.88rem;margin:0.3rem 0;'>"
            f"{html.escape(sop['description'])}</div>"
            f"<div style='color:{palette.FG_SUBTLE};font-size:0.78rem;margin-bottom:0.5rem;'>"
            f"{html.escape(i18n.t('sop_library.owner_reviewed', owner=sop['owner'], date=sop['last_reviewed'].strftime('%d/%m/%Y')))}"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.link_button(
            i18n.t("sop_library.open"),
            sop["url"],
            icon=":material/open_in_new:",
            use_container_width=True,
        )


def _render_grid(sops: list, today: date) -> None:
    for start in range(0, len(sops), _GRID_COLUMNS):
        row = sops[start:start + _GRID_COLUMNS]
        for column, sop in zip(st.columns(_GRID_COLUMNS), row):
            with column:
                _render_card(sop, today)


def _render_by_category(sops: list, today: date, area: str) -> None:
    for category in CATEGORIES_BY_AREA[area]:
        in_category = [sop for sop in sops if sop["category"] == category]
        if not in_category:
            continue
        st.subheader(category)
        _render_grid(in_category, today)


def _empty_state() -> None:
    st.markdown(
        f"<div style='border:2px dashed {palette.LINE};border-radius:12px;padding:32px;"
        f"text-align:center;background:{palette.ATTENTION_GLOW};'>"
        f"<h3 style='color:{palette.ACCENT};margin-top:0;'>"
        f"{html.escape(i18n.t('sop_library.empty_title'))}</h3>"
        f"<p style='color:{palette.FG_MUTED};margin:0;'>"
        f"{html.escape(i18n.t('sop_library.empty_body'))}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_catalog_errors(sops: list) -> None:
    errors = validate_catalog(sops)
    if errors:
        st.warning(
            i18n.t("sop_library.catalog_errors") + "\n\n" + "\n".join(f"- {error}" for error in errors)
        )


def render(area: str = "AM") -> None:
    today = date.today()
    area_sops = sops_for_area(SOPS, area)
    query_key = f"sop_lib_query_{area.lower()}"
    category_key = f"sop_lib_cat_{area.lower()}"
    _header(area)
    _render_catalog_errors(area_sops)
    _render_kpis(area_sops, today)

    query = st.text_input(
        i18n.t("sop_library.search_label"),
        key=query_key,
        placeholder=i18n.t("sop_library.search_placeholder"),
    )
    # Seeded instead of passing `default=`: a widget with both key and default warns on rerun.
    st.session_state.setdefault(category_key, ALL_CATEGORIES)
    category = st.pills(
        i18n.t("sop_library.category_label"),
        _category_options(area_sops, area),
        format_func=_category_label,
        key=category_key,
    )

    matches = filter_sops(area_sops, query, category)
    if not matches:
        _empty_state()
        return
    _render_by_category(matches, today, area)
