"""Tests del badge 'módulos activos' del módulo Inicio.

Anti-pattern documentado en modules/pages/CLAUDE.md M1: "No hardcodear el conteo de
módulos — leer de _PAGES". Estos tests blindan esa regla.
"""

from __future__ import annotations


def test_admin_module_count_is_every_page_but_inicio():
    """Un admin ve todo el menú: el conteo es _PAGES sin Inicio, no un literal."""
    from core.constants import _PAGES
    from core.home_areas import home_counts

    modules, _ = home_counts(is_admin=True)
    assert modules == len(_PAGES) - 1 == 41


def test_non_admin_module_count_skips_admin_only_pages():
    """Un no-admin no ve las páginas de ADMIN_ONLY: el badge no se las cuenta."""
    from core.constants import _PAGES
    from core.home_areas import home_counts
    from core.navigation import ADMIN_ONLY

    modules, _ = home_counts(is_admin=False)
    assert modules == len(_PAGES) - 1 - len(ADMIN_ONLY) == 37


def test_pages_includes_listing_monitor():
    """Listing Monitor debe estar en _PAGES (deuda del 2026-04-22 resuelta)."""
    from core.constants import _PAGES

    assert any("Listing Monitor" in p for p in _PAGES)


def test_pages_includes_mercado_libre():
    """Mercado Libre debe estar en _PAGES (M36, 2026-07-28)."""
    from core.constants import _PAGES
    assert any("Mercado Libre" in p for p in _PAGES)


def test_pages_includes_case_study_studio():
    """Case Study Studio debe estar en _PAGES (faltaba desde M32)."""
    from core.constants import _PAGES
    assert any("Case Study Studio" in p for p in _PAGES)


def test_pages_includes_supply_proveedores():
    """Proveedores debe estar en _PAGES (M37 Supply Chain, B1)."""
    from core.constants import _PAGES
    assert any("Proveedores" in p for p in _PAGES)


def test_pages_includes_supply_ordenes():
    """Órdenes de Compra debe estar en _PAGES (M37 Supply Chain, B1)."""
    from core.constants import _PAGES
    assert any("Órdenes de Compra" in p for p in _PAGES)
