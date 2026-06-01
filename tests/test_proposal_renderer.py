"""Tests del renderer HTML de propuestas (S5).

Herméticos: construyen la Proposal en memoria vía
`instantiate_proposal_from_template` (usa catálogo + templates versionados),
sin depender de `data/sales/proposals/` (que está gitignored y puede no existir
en CI). El renderer es una función pura que recibe el dict.
"""

from __future__ import annotations

import core.proposal_persistence as pp
from core.proposal_renderer import (
    _catalog_module_index,
    _effective_data,
    render_proposal_html,
)


def _launch_proposal(client_name: str = "Capybaras Test Client") -> dict:
    """Proposal launch instanciada (todos los blocks con data={} por default)."""
    return pp.instantiate_proposal_from_template(
        archetype="launch",
        client_name=client_name,
        language="es",
        sales_director="Lenin Acosta",
    )


def _proposal_with_v1_data() -> dict:
    """Proposal launch con el block V1 poblado con campos reales + vacíos/null."""
    p = _launch_proposal()
    for b in p["blocks"]:
        if b["module_id"] == "V1_brand_overview":
            b["data"] = {
                "brand_name": "ZEBRA_BRAND_MARKER",
                "sku_count": None,            # null → debe omitirse, NO "None"
                "categories": ["Cat X", "Cat Y"],
                "markets": ["US"],
                "amazon_account_type": "",    # "" → debe omitirse
                "ppc_maturity": "",           # "" → debe omitirse
                "hero_asins": ["B0TEST123"],
                "monthly_revenue_band": "100k-500k USD",
                "current_acos_band": "15-25%",
            }
    return p


def test_render_seed_no_crash():
    """Renderiza en 'es' y 'en' sin crashear; devuelve str no vacío."""
    p = _launch_proposal()
    for lang in ("es", "en"):
        html = render_proposal_html(p, lang)
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<!doctype html>" in html.lower()


def test_render_contains_client_name():
    """El client_name aparece en el HTML (portada F1 desde metadata)."""
    p = _launch_proposal("Marca Unica 123")
    html = render_proposal_html(p, "es")
    assert "Marca Unica 123" in html


def test_render_v1_fields():
    """Un campo real de V1 (brand_name) aparece y no se emite 'None' por null."""
    p = _proposal_with_v1_data()
    html = render_proposal_html(p, "es")
    assert "ZEBRA_BRAND_MARKER" in html
    assert "B0TEST123" in html
    # Gotcha B3-d-bis: sku_count=None y campos "" no deben aparecer como "None".
    assert "None" not in html


def test_render_empty_data_block():
    """Un block con data={} (los 8 FIXED + V17-V22) no rompe el render."""
    p = _launch_proposal()
    # Sanity: la launch trae blocks con data vacía por instanciación.
    assert any((b.get("data") or {}) == {} for b in p["blocks"])
    html = render_proposal_html(p, "es")
    assert isinstance(html, str) and len(html) > 0


def test_effective_data_inherits_default_when_no_block_data():
    """Un bloque sin data hereda el default del catálogo (F6.version = 'v3')."""
    f6 = _catalog_module_index()["F6_why_capybaras"]
    eff = _effective_data(f6, {})
    assert eff.get("version") == "v3"
    assert isinstance(eff.get("pillars"), list) and len(eff["pillars"]) == 4


def test_effective_data_block_data_overrides_default():
    """block.data pisa SIEMPRE el default del catálogo."""
    f6 = _catalog_module_index()["F6_why_capybaras"]
    eff = _effective_data(f6, {"version": "OVERRIDE_X", "pillars": ["only_one"]})
    assert eff["version"] == "OVERRIDE_X"
    assert eff["pillars"] == ["only_one"]


def test_effective_data_no_default_is_non_regressive():
    """Un módulo sin defaults (V1) devuelve la block.data tal cual (no-regresivo)."""
    v1 = _catalog_module_index()["V1_brand_overview"]
    block_data = {"brand_name": "X", "sku_count": None}
    assert _effective_data(v1, block_data) == block_data


def test_render_missing_template_uses_placeholder():
    """Un module_id sin template propio cae al placeholder (no rompe)."""
    p = _launch_proposal()
    # V2_category_overview aún no tiene template propio en S5 → placeholder.
    assert any(b["module_id"] == "V2_category_overview" for b in p["blocks"])
    html = render_proposal_html(p, "es")
    assert "contenido pendiente" in html
    # Y en inglés usa el texto en inglés del placeholder.
    html_en = render_proposal_html(p, "en")
    assert "content pending" in html_en
