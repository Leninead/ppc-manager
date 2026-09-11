"""Tests del badge 'módulos activos' del módulo Inicio.

Anti-pattern documentado en modules/pages/CLAUDE.md M1: "No hardcodear el conteo de
módulos — leer de _PAGES". Estos tests blindan esa regla.
"""

from __future__ import annotations


def test_total_modulos_is_dynamic():
    """_TOTAL_MODULOS debe leerse de _PAGES, no ser literal."""
    from core.constants import _PAGES
    from modules.pages.inicio import _TOTAL_MODULOS

    expected = len([p for p in _PAGES if "Inicio" not in p])
    assert _TOTAL_MODULOS == expected


def test_total_modulos_excludes_inicio():
    """Inicio no debe contarse como módulo (es la home del dashboard)."""
    from core.constants import _PAGES
    from modules.pages.inicio import _TOTAL_MODULOS

    # _PAGES tiene Inicio + N módulos. _TOTAL_MODULOS debe ser N (no N+1).
    assert _TOTAL_MODULOS == len(_PAGES) - 1


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
