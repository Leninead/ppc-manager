"""The areas of the home page: who owns each menu section and what a given role gets to see.

Keyed by `Section.title`, the same identifier the menu uses, so an area is always a menu
section and never a hand-written list of modules.
"""
from __future__ import annotations

from core import navigation

SYSTEM_SECTION = "Sistema"

# Owners are names, not copy: they are shown as-is in both languages.
AREA_OWNERS: dict[str, str] = {
    "PPC": "Guille Neuman",
    "Research": "Lenin Acosta",
    "Account": "Eduardo Maya",
    "Sales Director": "Adam y Remiro",
    "Dirección": "Guille Neuman",
    "Knowledge": "Lenin Acosta",
    "Account Health": "Marcos",
    "Supply Chain": "Julian López y Federico Valero",
    "Marketplaces": "Cleimery y Josefina",
    "Sistema": "Juan y Lenin",
}


def visible_sections(is_admin: bool = False) -> list[tuple[navigation.Section, tuple[str, ...]]]:
    """Each menu section with the pages this role sees, in menu order, skipping empty ones."""
    visible = []
    for section in navigation.SECTIONS:
        pages = navigation.visible_pages(section, is_admin)
        if pages:
            visible.append((section, pages))
    return visible


def home_counts(is_admin: bool = False) -> tuple[int, int]:
    """(modules, areas) as this role sees them in the side rail."""
    sections = visible_sections(is_admin)
    return sum(len(pages) for _, pages in sections), len(sections)
