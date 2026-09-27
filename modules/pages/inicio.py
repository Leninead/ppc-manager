"""Inicio: the home of Agency OS.

Nothing here is written by hand: the counts and areas mirror the side rail for the viewer's
role (`core.home_areas`), the news come from `core.home_news` and the resources from the SOP
catalog. Every chip and button navigates by setting the same routing key the rail uses.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

import streamlit as st

from core import navigation
from core.home_areas import AREA_OWNERS, SYSTEM_SECTION, home_counts, visible_sections
from core.home_news import NEWS, count_since, latest
from core.integrations import roles
from core.integrations.store import _Rest, _rest_credentials
from core.radar import store as radar_store
from core.sop_library import SOPS, sops_for_area
from core.ui import i18n, palette

log = logging.getLogger(__name__)

_TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
_NEWS_GRID_SIZE = 4
_RADAR_TOPICS = 5
# (ink, background) of the badge per confidence the Radar run computed.
_RADAR_BADGES: dict[str, tuple[str, str]] = {
    "official": (palette.OK_INK, palette.OK_GLOW),
    "confirmed": (palette.CHIP_MARKETPLACE_FG, palette.CHIP_MARKETPLACE_BG),
    "expert": (palette.FG_MUTED, palette.LINE_SOFT),
}
# Narrowest a grid card may get before the grid drops a column: below this the text wraps word by word.
_NEWS_CARD_MIN = "220px"
_RESOURCE_CARD_MIN = "240px"
_AREA_CARD_MIN = "300px"

# (routing key, SOP area or None when there is no real count, body text key)
_RESOURCES: tuple[tuple[str, str | None, str], ...] = (
    ("📂 SOPs / Drive PPC", "PPC", "home.resources.sops_ppc_body"),
    ("📂 SOPs / Drive AM", "AM", "home.resources.sops_am_body"),
    ("📚 Knowledge Base", None, "home.resources.kb_body"),
)

_CSS = f"""
<style>
.st-key-home_news {{
    background: {palette.NEWS_BG};
    border-radius: 26px;
    padding: 40px 44px;
    margin: 8px 0 12px 0;
}}
.st-key-home_news [data-testid="stMarkdownContainer"] p {{ margin: 0; }}
[class*="st-key-home_news_card_"] {{
    background: {palette.NEWS_CARD};
    border: 1px solid {palette.NEWS_LINE};
    border-radius: 18px;
    padding: 18px 20px;
    justify-content: space-between;
}}
.st-key-home_news_grid > [data-testid="stHorizontalBlock"] {{
    display: grid !important;
    grid-template-columns: repeat(auto-fit, minmax({_NEWS_CARD_MIN}, 1fr));
    gap: 14px;
}}
.st-key-home_resources_grid > [data-testid="stHorizontalBlock"] {{
    display: grid !important;
    grid-template-columns: repeat(auto-fit, minmax({_RESOURCE_CARD_MIN}, 1fr));
    gap: 14px;
}}
.st-key-home_areas_grid > [data-testid="stHorizontalBlock"] {{
    display: grid !important;
    grid-template-columns: repeat(auto-fit, minmax(max({_AREA_CARD_MIN}, calc((100% - 28px) / 3)), 1fr));
    gap: 14px;
}}
[class*="st-key-home_res_"] {{ justify-content: space-between; }}
[class*="st-key-home_"][class*="_grid"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    width: auto !important;
    min-width: 0 !important;
    flex: none !important;
}}
/* Only the column's own block and the card directly inside it stretch: a nested block (the chips)
   given height:100% spreads its rows down the card. */
[class*="st-key-home_"][class*="_grid"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"],
[class*="st-key-home_"][class*="_grid"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] > div,
[class*="st-key-home_"][class*="_grid"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"],
[class*="st-key-home_"][class*="_grid"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"],
[class*="st-key-home_"][class*="_grid"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] > div,
[class*="st-key-home_"][class*="_grid"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {{
    height: 100%;
}}
.st-key-home_news button[kind="tertiary"] p {{ color: {palette.ACCENT_SOFT}; font-weight: 600; }}
.st-key-home_news button[kind="tertiary"]:hover p {{ color: {palette.SIDEBAR_INK_ACTIVE}; }}
[class*="st-key-home_chips_"] {{
    flex-direction: row !important;
    flex-wrap: wrap !important;
    align-content: flex-start !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    gap: 6px 8px !important;
    height: auto !important;
}}
[class*="st-key-home_chips_"] > [data-testid="stElementContainer"] {{
    width: auto !important;
    max-width: 100%;
    flex: 0 0 auto !important;
}}
[class*="st-key-home_area_head_"] [data-testid="stMarkdownContainer"] p {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 8px;
}}
[class*="st-key-home_chip_"] button {{
    border: 1px solid {palette.LINE} !important;
    border-radius: 999px !important;
    background: {palette.CARD} !important;
    padding: 4px 12px !important;
    min-height: 34px;
}}
[class*="st-key-home_chip_"] button:hover {{ border-color: {palette.ACCENT} !important; }}
[class*="st-key-home_chip_"] button:hover p {{ color: {palette.ACCENT_HOVER} !important; }}
.st-key-home_system {{
    background: {palette.ROW_HOVER};
    border: 1px dashed {palette.FG_SUBTLE};
    border-radius: 16px;
    padding: 20px 24px;
    margin-top: 8px;
}}
@media (pointer: coarse) {{
    [class*="st-key-home_chip_"] button {{ min-height: 44px; }}
}}
@media (max-width: 640px) {{
    .st-key-home_news {{ padding: 24px 18px; border-radius: 20px; }}
    .st-key-home_system {{ padding: 16px; }}
}}
</style>
"""


def _go(page: str) -> None:
    st.session_state["selected_page"] = page


def _key_of_page(page: str) -> str:
    """Widget keys use the page's position in the menu: routing keys carry emojis."""
    return str(navigation.all_pages().index(page))


def _key_of_section(section: navigation.Section) -> str:
    return str(navigation.SECTIONS.index(section))


def _today() -> date:
    return datetime.now(_TIMEZONE).date()


def _today_label(today: date) -> str:
    weekdays = i18n.t("home.weekdays").split(",")
    months = i18n.t("home.months").split(",")
    return i18n.t("home.date", weekday=weekdays[today.weekday()], day=today.day,
                  month=months[today.month - 1])


def _news_meta(item: dict) -> str:
    news_date = i18n.t("home.news.date", day=item["date"].day,
                       month=i18n.months_short()[item["date"].month - 1])
    return i18n.t("home.news.meta", date=news_date, kind=i18n.t(f"home.kind.{item['kind']}"))


def _section_title_html(text: str) -> str:
    return (f"<div style='font-family:{palette.SERIF_STACK};font-size:clamp(24px,3vw,30px);font-weight:700;"
            f"color:{palette.FG};margin:28px 0 4px 0;'>{escape(text)}</div>")


def _kpi_html(value: int, label: str) -> str:
    return (
        f"<div style='flex:1 1 0;min-width:120px;background:{palette.CARD};border:1px solid {palette.LINE};"
        f"border-radius:16px;padding:12px 16px;'>"
        f"<div style='font-family:{palette.SERIF_STACK};font-size:34px;font-weight:700;line-height:1.1;"
        f"color:{palette.FG};font-variant-numeric:tabular-nums;'>{value}</div>"
        f"<div style='font-size:13px;color:{palette.FG_MUTED};white-space:nowrap;'>{escape(label)}</div>"
        f"</div>"
    )


def _render_header(today: date, modules: int, areas: int) -> None:
    """One flex row instead of st.columns: the KPIs share a row, so they stretch to one height,
    and the whole group drops under the title when the page is narrow."""
    st.markdown(
        f"<div style='display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;"
        f"gap:16px 32px;'>"
        f"<div style='flex:1 1 360px;min-width:0;'>"
        f"<div style='font-size:13px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;"
        f"color:{palette.ACCENT};'>{escape(_today_label(today))}</div>"
        f"<div style='font-family:{palette.SERIF_STACK};font-size:clamp(28px,4vw,42px);font-weight:700;"
        f"line-height:1.1;color:{palette.FG};margin:6px 0;'>{escape(i18n.t('home.title'))}</div>"
        f"<div style='font-size:16px;color:{palette.FG_MUTED};'>{escape(i18n.t('home.subtitle'))}</div>"
        f"</div>"
        f"<div style='display:flex;align-items:stretch;gap:12px;flex:0 1 auto;'>"
        f"{_kpi_html(modules, i18n.tn('home.kpi.modules', modules))}"
        f"{_kpi_html(areas, i18n.tn('home.kpi.areas', areas))}"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def _render_featured_news(item: dict, this_week: int) -> None:
    badge = ""
    if this_week:
        badge = (f"<span style='font-size:13px;font-weight:600;color:{palette.NEWS_BG};"
                 f"background:{palette.ACCENT_SOFT};border-radius:999px;padding:4px 12px;'>"
                 f"{escape(i18n.tn('home.news.this_week', this_week))}</span>")
    st.markdown(
        f"<div style='display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;margin-bottom:22px;'>"
        f"<span style='font-family:{palette.SERIF_STACK};font-size:clamp(30px,4vw,44px);font-weight:700;"
        f"color:{palette.ACCENT_SOFT};line-height:1.1;'>{escape(i18n.t('home.news.title'))}</span>{badge}</div>"
        f"<div style='font-size:14px;color:{palette.SIDEBAR_INK};margin-bottom:8px;'>"
        f"{escape(_news_meta(item))}</div>"
        f"<div style='font-family:{palette.SERIF_STACK};font-size:clamp(30px,5vw,56px);font-weight:700;line-height:1.05;"
        f"color:{palette.SIDEBAR_INK_ACTIVE};margin-bottom:14px;'>{escape(item['title'])}</div>"
        f"<div style='font-size:clamp(16px,2vw,20px);line-height:1.45;color:{palette.SIDEBAR_INK};"
        f"margin-bottom:22px;'>{escape(item['description'])}</div>",
        unsafe_allow_html=True,
    )
    if item["page"]:
        st.button(i18n.t("home.news.open"), key=f"home_news_open_{item['id']}", type="primary",
                  on_click=_go, args=(item["page"],))


def _render_news_card(item: dict) -> None:
    with st.container(key=f"home_news_card_{item['id']}"):
        st.markdown(
            f"<div style='font-size:12px;color:{palette.FG_SUBTLE};margin-bottom:6px;'>"
            f"{escape(_news_meta(item))}</div>"
            f"<div style='font-size:20px;font-weight:600;line-height:1.25;"
            f"color:{palette.SIDEBAR_INK_ACTIVE};margin-bottom:6px;'>{escape(item['title'])}</div>"
            f"<div style='font-size:14px;line-height:1.45;color:{palette.SIDEBAR_INK};'>"
            f"{escape(item['description'])}</div>",
            unsafe_allow_html=True,
        )
        if item["page"]:
            st.button(i18n.t("home.news.open_arrow"), key=f"home_news_open_{item['id']}", type="tertiary",
                      on_click=_go, args=(item["page"],))


def _render_news(today: date) -> None:
    items = latest(NEWS, 1 + _NEWS_GRID_SIZE)
    if not items:
        return
    featured, others = items[0], items[1:]
    with st.container(key="home_news"):
        _render_featured_news(featured, count_since(NEWS, today))
        if others:
            with st.container(key="home_news_grid"):
                for column, item in zip(st.columns(len(others)), others):
                    with column:
                        _render_news_card(item)


@st.cache_data(ttl=3600, show_spinner=False)
def _load_radar() -> list[dict]:
    """The latest week's Radar topics, or [] when there is no database, no table yet or no rows."""
    credentials = _rest_credentials()
    if credentials is None:
        return []
    try:
        return radar_store.latest_topics(_Rest(*credentials), limit=_RADAR_TOPICS)
    except Exception as exc:  # the home must render even when the Radar cannot be read
        log.warning("home: radar_items could not be read: %s", exc)
        return []


def _radar_week_label(week_start: str) -> str:
    day = date.fromisoformat(week_start)
    months = i18n.t("home.months").split(",")
    return i18n.t("home.radar.week", day=day.day, month=months[day.month - 1])


def _safe_link(url: str) -> str | None:
    """Feed links are third-party data: only http(s) becomes a clickable href."""
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else None


def _radar_source_html(source: dict) -> str:
    parts = [escape(str(source.get("person") or source.get("name") or ""))]
    try:
        published = date.fromisoformat(str(source.get("published_at", ""))[:10])
        parts.append(escape(i18n.t("home.news.date", day=published.day,
                                   month=i18n.months_short()[published.month - 1])))
    except ValueError:
        pass
    link = _safe_link(source.get("link"))
    if link:
        parts.append(f"<a href='{escape(link, quote=True)}' target='_blank' rel='noopener noreferrer' "
                     f"style='color:{palette.ACCENT_HOVER};'>{escape(i18n.t('home.radar.open_source'))}</a>")
    return f"<div style='font-size:13px;color:{palette.FG_MUTED};'>{' · '.join(parts)}</div>"


def _render_radar_topic(topic: dict) -> None:
    ink, background = _RADAR_BADGES.get(topic["confidence"], _RADAR_BADGES["expert"])
    badge = (f"<span style='font-size:12px;font-weight:600;color:{ink};background:{background};"
             f"border-radius:999px;padding:3px 10px;white-space:nowrap;'>"
             f"{escape(i18n.t('home.radar.confidence.' + topic['confidence']))}</span>")
    sources = "".join(_radar_source_html(source) for source in topic.get("sources") or [])
    with st.container(border=True, key=f"home_radar_topic_{topic['rank']}"):
        st.markdown(
            f"<div style='margin-bottom:8px;'>{badge}</div>"
            f"<div style='font-size:18px;font-weight:600;line-height:1.3;color:{palette.FG};margin-bottom:6px;'>"
            f"{escape(topic['title_es'])}</div>"
            f"<div style='font-size:15px;line-height:1.5;color:{palette.FG};margin-bottom:8px;'>"
            f"{escape(topic['summary_es'])}</div>"
            f"<div style='font-size:14px;line-height:1.5;color:{palette.FG};background:{palette.ATTENTION_GLOW};"
            f"border-radius:10px;padding:8px 12px;margin-bottom:8px;'>"
            f"<strong>{escape(i18n.t('home.radar.implications'))}</strong> {escape(topic['implications_es'])}</div>"
            f"{sources}",
            unsafe_allow_html=True,
        )


def _render_radar() -> None:
    topics = _load_radar()
    if not topics:
        return
    st.markdown(_section_title_html(i18n.t("home.radar.title")), unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:14px;color:{palette.FG_MUTED};margin-bottom:12px;'>"
                f"{escape(_radar_week_label(topics[0]['week_start']))} · "
                f"{escape(i18n.t('home.radar.disclaimer'))}</div>", unsafe_allow_html=True)
    with st.container(key="home_radar"):
        for topic in topics:
            _render_radar_topic(topic)


def _render_resources(visible: set[str]) -> None:
    resources = [resource for resource in _RESOURCES if resource[0] in visible]
    if not resources:
        return
    st.markdown(_section_title_html(i18n.t("home.resources.title")), unsafe_allow_html=True)
    with st.container(key="home_resources_grid"):
        columns = st.columns(len(resources))
    for column, (page, sop_area, body_key) in zip(columns, resources):
        page_key = _key_of_page(page)
        with column, st.container(border=True, key=f"home_res_{page_key}"):
            st.markdown(f"{navigation.icon_for(page)} **{navigation.visible_label(page)}**")
            if sop_area is not None:
                documents = len(sops_for_area(SOPS, sop_area))
                st.markdown(
                    f"<div style='font-size:14px;font-weight:600;color:{palette.ACCENT};'>"
                    f"{escape(i18n.tn('home.resources.docs', documents))}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown(f"<div style='font-size:14px;color:{palette.FG_MUTED};margin-bottom:8px;'>"
                        f"{escape(i18n.t(body_key))}</div>", unsafe_allow_html=True)
            st.button(i18n.t("home.resources.open"), key=f"home_res_open_{page_key}",
                      on_click=_go, args=(page,))


def _material_icon_html(shortcode: str) -> str:
    """A `:material/name:` icon as raw HTML.

    Mixed with HTML, st.markdown prints the shortcode's name as text. Streamlit loads the
    "Material Symbols Rounded" font globally but ships no class for it, so the ligature styles
    of its own icon component are repeated inline.
    """
    name = shortcode.removeprefix(":material/").removesuffix(":")
    return (
        "<span translate='no' style=\"font-family:'Material Symbols Rounded';font-weight:400;"
        "font-style:normal;font-size:1.25rem;line-height:1;display:inline-block;white-space:nowrap;"
        "word-wrap:normal;direction:ltr;font-feature-settings:'liga';-webkit-font-smoothing:antialiased;"
        f"color:{palette.FG};\">{escape(name)}</span>"
    )


def _render_area_body(section: navigation.Section, pages: tuple[str, ...]) -> None:
    """No nested st.columns here: the grid's column CSS would reach them and squeeze the header."""
    section_key = _key_of_section(section)
    with st.container(key=f"home_area_head_{section_key}"):
        st.markdown(
            f"{_material_icon_html(section.icon)}"
            f"<strong>{escape(navigation.section_label(section.title))}</strong>"
            f"<span style='margin-left:auto;font-size:12px;font-weight:600;color:{palette.OK_INK};"
            f"background:{palette.OK_GLOW};border-radius:999px;padding:3px 10px;white-space:nowrap;'>"
            f"{escape(i18n.tn('home.count.modules', len(pages)))}</span>",
            unsafe_allow_html=True,
        )
    owner = AREA_OWNERS.get(section.title)
    if owner:
        st.markdown(f"<div style='font-size:13px;color:{palette.FG_MUTED};margin-bottom:8px;'>"
                    f"{escape(i18n.t('home.areas.owner', owner=owner))}</div>", unsafe_allow_html=True)
    with st.container(key=f"home_chips_{section_key}"):
        for page in pages:
            st.button(navigation.visible_label(page), icon=navigation.icon_for(page), type="tertiary",
                      key=f"home_chip_{_key_of_page(page)}", on_click=_go, args=(page,))


def _render_areas(sections, modules: int, areas: int) -> None:
    st.markdown(_section_title_html(i18n.t("home.areas.title")), unsafe_allow_html=True)
    summary = i18n.t("home.areas.summary", areas=i18n.tn("home.count.areas", areas),
                     modules=i18n.tn("home.count.modules", modules))
    st.markdown(f"<div style='font-size:14px;color:{palette.FG_MUTED};margin-bottom:12px;'>"
                f"{escape(summary)}</div>", unsafe_allow_html=True)

    grid = [(section, pages) for section, pages in sections if section.title != SYSTEM_SECTION]
    if grid:
        with st.container(key="home_areas_grid"):
            columns = st.columns(len(grid))
        for column, (section, pages) in zip(columns, grid):
            with column, st.container(border=True, key=f"home_area_{_key_of_section(section)}"):
                _render_area_body(section, pages)

    system = next(((section, pages) for section, pages in sections if section.title == SYSTEM_SECTION), None)
    if system is not None:
        with st.container(key="home_system"):
            _render_area_body(*system)


def render(username: str = "", role: str = roles.USER) -> None:
    is_admin = roles.is_admin(role)
    sections = visible_sections(is_admin)
    modules, areas = home_counts(is_admin)
    visible = {page for _, pages in sections for page in pages}
    today = _today()

    st.markdown(_CSS, unsafe_allow_html=True)
    _render_header(today, modules, areas)
    _render_news(today)
    _render_radar()
    _render_resources(visible)
    _render_areas(sections, modules, areas)
