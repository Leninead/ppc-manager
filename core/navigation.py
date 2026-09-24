"""The destinations of the side rail, in one place.

Four things that used to live scattered and drift apart come from here: the
sidebar buttons, the per-section count, the search filter, and the icon that
goes with each destination.

Labels ARE the routing keys (`st.session_state["selected_page"]`, which
`app.py` compares literally, emoji included). Changing one here changes the
routing: touch it with the router or don't touch it at all. `visible_label()`
is the only place that strips the emoji for display; the routing key keeps it.

The icon is drawn separately, with `st.button(icon=":material/xxx:")`, not as
a character inside the label: that separates the visual signal (the icon) from
the identifier (the key). Before, both lived in the same string, and that is
why changing an emoji was a routing change.

`Section.title` is an identifier too — it is the lookup key of the section, not
a caption — so it is translated the same way a page is: by lookup at display
time, through `section_label()`. SECTIONS stays pure data in Spanish; nothing
here is ever translated in place.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from core.ui import i18n

HOME = "🏠 Inicio"
REQUEST_LOG = "🧾 Registro de solicitudes"


@dataclass(frozen=True)
class Section:
    title: str
    icon: str
    open_by_default: bool
    pages: tuple[str, ...]


SECTIONS: tuple[Section, ...] = (
    Section("PPC", ":material/query_stats:", True, (
        "📊 Search Term Report",
        "🔍 Search Query Performance",
        "🔗 Análisis Cruzado STR vs SQP",
        "📈 Tendencia Multi-Semana",
        "📁 Bulk Campañas",
        "💰 Business Report",
        "🔻 Análisis de Funnel",
        "🧠 Bid Optimizer",
        "🚀 Campaign Builder",
        "⚙️ Atom11 Rules Builder",
        "📂 SOPs / Drive PPC",
    )),
    Section("Research", ":material/science:", False, (
        "🧲 DataDive Analyzer",
        "🧲 Helium 10 Analyzer",
        "📢 SBH Recommendation",
        "🔎 PPC Insights",
        "📈 PPC Forecast",
        "🛡️ PPC Audit",
        "📊 Account Pulse",
    )),
    Section("Account", ":material/groups:", False, (
        "🔬 Reportes Atom 11",
        "🛡️ Reportes MerchanSpring",
        "📊 Weekly Client Report",
        "👁️ Listing Monitor",
        "🛡️ Listing Compliance",
        "📊 Gamboa Generator",
        "🧬 Variation Builder",
        "📈 Monthly Forecast",
        "📂 SOPs / Drive AM",
    )),
    Section("Sales Director", ":material/description:", False, (
        "📋 Proposal Studio",
        "🏆 Case Study Studio",
    )),
    Section("Dirección", ":material/dashboard:", False, (
        "🌐 Dashboard Global",
    )),
    Section("Knowledge", ":material/menu_book:", False, (
        "📚 Knowledge Base",
    )),
    Section("Account Health", ":material/monitor_heart:", False, (
        "🗂️ Flat File Migrator",
        "🏥 SKU Progress Report",
        "💲 Pricing Dashboard",
    )),
    Section("Supply Chain", ":material/inventory_2:", False, (
        "🚚 Proveedores",
        "📦 Órdenes de Compra",
    )),
    Section("Marketplaces", ":material/storefront:", False, (
        "🛒 Mercado Libre",
    )),
    Section("Sistema", ":material/settings:", False, (
        "🔑 Cuentas conectadas",
        "🔌 Integraciones",
        "🧠 Skills",
        REQUEST_LOG,
    )),
)


# Destinations the rail only offers to an admin. The page checks the role again
# on its own (`modules/pages/integrations.py` → `roles.is_admin`); this is what
# keeps the rail from advertising a door that answers "esta pantalla es sólo
# para admin". Both layers stay: hiding the button is not access control.
#
# `all_pages()` deliberately keeps listing these — it is the catalog every page
# name derives from (`core.constants._PAGES`), not the menu a given user gets.
# Only `visible_pages()` and `filter_pages()` know about roles.
ADMIN_ONLY: frozenset[str] = frozenset({
    "🔌 Integraciones", "🧠 Skills", REQUEST_LOG, "🌐 Dashboard Global",
})


# The emoji of a destination still lives in the routing key, but a Material
# icon is picked by hand for each one. The same emoji dresses ten destinations
# (📊 shows up four times, 📈 three, 🛡️ three); one icon per destination gives
# the signal the emoji cannot.
_ICONS: dict[str, str] = {
    HOME: ":material/home:",
    "📊 Search Term Report": ":material/query_stats:",
    "🔍 Search Query Performance": ":material/search:",
    "🔗 Análisis Cruzado STR vs SQP": ":material/join:",
    "📈 Tendencia Multi-Semana": ":material/trending_up:",
    "📁 Bulk Campañas": ":material/folder_open:",
    "💰 Business Report": ":material/attach_money:",
    "🔻 Análisis de Funnel": ":material/filter_alt:",
    "🧠 Bid Optimizer": ":material/psychology:",
    "🚀 Campaign Builder": ":material/rocket_launch:",
    "⚙️ Atom11 Rules Builder": ":material/tune:",
    "🧲 DataDive Analyzer": ":material/travel_explore:",
    "🧲 Helium 10 Analyzer": ":material/biotech:",
    "📢 SBH Recommendation": ":material/campaign:",
    "🔎 PPC Insights": ":material/insights:",
    "📈 PPC Forecast": ":material/auto_graph:",
    "🛡️ PPC Audit": ":material/verified_user:",
    "📊 Account Pulse": ":material/monitoring:",
    "🔬 Reportes Atom 11": ":material/science:",
    "🛡️ Reportes MerchanSpring": ":material/shield:",
    "📊 Weekly Client Report": ":material/summarize:",
    "👁️ Listing Monitor": ":material/visibility:",
    "🛡️ Listing Compliance": ":material/policy:",
    "📊 Gamboa Generator": ":material/table_view:",
    "🧬 Variation Builder": ":material/account_tree:",
    "📈 Monthly Forecast": ":material/calendar_month:",
    "📂 SOPs / Drive AM": ":material/folder_shared:",
    "📂 SOPs / Drive PPC": ":material/folder_special:",
    "📋 Proposal Studio": ":material/article:",
    "🏆 Case Study Studio": ":material/emoji_events:",
    "📚 Knowledge Base": ":material/menu_book:",
    "🗂️ Flat File Migrator": ":material/sync_alt:",
    "🏥 SKU Progress Report": ":material/local_hospital:",
    "💲 Pricing Dashboard": ":material/sell:",
    "🚚 Proveedores": ":material/local_shipping:",
    "📦 Órdenes de Compra": ":material/receipt_long:",
    "🛒 Mercado Libre": ":material/shopping_cart:",
    "🌐 Dashboard Global": ":material/dashboard:",
    "🔑 Cuentas conectadas": ":material/key:",
    "🔌 Integraciones": ":material/power:",
    "🧠 Skills": ":material/neurology:",
    REQUEST_LOG: ":material/history:",
}


def all_pages() -> list[str]:
    """Every destination of the rail, Home first."""
    return [HOME] + [page for section in SECTIONS for page in section.pages]


def icon_for(page: str) -> str:
    """The Material icon paired with a destination, or `home` as a safe default."""
    return _ICONS.get(page, ":material/home:")


def visible_label(page: str) -> str:
    """The routing key translated for display, without its leading emoji.

    Stripping the emoji from the label stops the row from showing two icons —
    the Material one and the unicode emoji — fighting for the same spot. The
    icon does that job.

    The routing key itself never changes: it is what `app.py` compares, so only
    the text it shows is looked up. A destination that isn't in the catalog —
    one added to `SECTIONS` and not yet translated — falls back to its Spanish
    key with the emoji stripped, which is exactly what this returned before
    i18n, composite emojis like `🛡️` (symbol + variation selector U+FE0F)
    included.
    """
    return i18n.page_label(page)


def section_label(title: str) -> str:
    """The title of a `SECTIONS` section, translated for display.

    The title doubles as the section's identifier, so it is looked up rather
    than translated in place; an unknown one comes back unchanged. Sections are
    displayed through here for the same reason pages go through
    `visible_label()`: the rail's display rules live in this module, and a
    render site should not have to know which of these strings are identifiers.
    """
    return i18n.section_title(title)


def visible_pages(section: Section, is_admin: bool = False) -> tuple[str, ...]:
    """The destinations of `section` that this role may actually open.

    Fails closed: a caller that forgets the role gets the plain-user rail, never
    the other way round. Returns a tuple like `Section.pages` so the caller can
    take `len()` for the section's count badge — reading that off `section.pages`
    instead is how a rail showing one button ends up captioned "Sistema 2".
    """
    if is_admin:
        return section.pages
    return tuple(page for page in section.pages if page not in ADMIN_ONLY)


def filter_pages(query: str, is_admin: bool = False) -> list[str]:
    """Destinations matching the typed query, ignoring accents and case.

    Without this, 33 destinations live behind eight closed cajones and are only
    reachable by opening the right one from memory.

    Role-filtered like the rail, and for the same reason: search is the *other*
    way into a destination, so gating only the expander would leave the
    admin-only ones one keystroke away.
    """
    needle = _strip_accents(query)
    if not needle:
        return []
    return [page for page in all_pages()
            if needle in _strip_accents(page)
            and (is_admin or page not in ADMIN_ONLY)]


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(letter for letter in decomposed if not unicodedata.combining(letter))
