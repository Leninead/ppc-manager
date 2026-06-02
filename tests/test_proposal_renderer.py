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
    _md_bold,
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


def test_render_includes_fixed_catalog_content():
    """El render incluye contenido de los defaults del catálogo (F4/F6 pillars)."""
    p = _launch_proposal()
    html = render_proposal_html(p, "es")
    assert "Strategic Management" in html          # F4 pillar name (plano)
    assert "Sistema Operativo Propio" in html      # F6 pillar title.es resuelto


def test_render_pick_lang_no_raw_dict():
    """Los campos bilingües {en,es} se resuelven; no aparecen dicts crudos."""
    p = _launch_proposal()
    for lang in ("es", "en"):
        html = render_proposal_html(p, lang)
        assert "{'en'" not in html
        assert "{'es'" not in html
        assert "{&#39;en&#39;" not in html  # por si autoescape escapa las comillas


def test_render_v2_fields():
    """V2 renderiza sus campos data-driven; omite vacíos, sin 'None'."""
    p = _launch_proposal()
    for b in p["blocks"]:
        if b["module_id"] == "V2_category_overview":
            b["data"] = {
                "category_name": "ZEBRA_CATEGORY",
                "category_size_band": "$10-100M",
                "competition_density": "",          # "" → debe omitirse
                "top_competitors": ["CompA", "CompB"],
                "weaknesses": ["Weak1"],
            }
    html = render_proposal_html(p, "es")
    assert "ZEBRA_CATEGORY" in html
    assert "CompA" in html
    assert "Weak1" in html
    assert "None" not in html


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


# ─────────────────────────────────────────────────────────────────────────────
# COMMIT E — filtro md_bold + template V6_growth_plan_phases
# ─────────────────────────────────────────────────────────────────────────────


def test_md_bold_converts_bold():
    """`**x**` → `<strong>x</strong>` (markdown-mínimo)."""
    out = str(_md_bold("**Phase 1** del plan"))
    assert "<strong>Phase 1</strong>" in out
    assert "**" not in out  # los marcadores se consumieron


def test_md_bold_escapes_html_injection():
    """TEST DE SEGURIDAD: HTML hostil del input queda escapado, NO inyectado.

    Orden escape→bold→Markup: el <script> se neutraliza ANTES del bold, así que
    nunca llega crudo al HTML final.
    """
    out = str(_md_bold("**Hola** <script>alert(1)</script>"))
    assert "&lt;script&gt;" in out          # escapado
    assert "<script>" not in out            # NO inyectado crudo
    assert "<strong>Hola</strong>" in out   # el bold legítimo sí renderiza


def test_md_bold_none_is_empty():
    """None → Markup vacío (no 'None')."""
    assert str(_md_bold(None)) == ""


def _inject_block(proposal: dict, module_id: str, data: dict) -> dict:
    """Agrega un block {module_id, data} a la proposal (el render solo necesita eso).

    Algunos módulos (V5, V6) no están en el archetype 'launch', así que se inyectan
    directos para testear su template sin depender de qué archetype los incluye.
    """
    proposal["blocks"].append({"module_id": module_id, "data": data})
    return proposal


def _proposal_with_v6_data(narrative_es: str) -> dict:
    """Proposal launch + block V6 inyectado: 3 fases, narrative bilingüe con **bold**."""
    p = _launch_proposal()
    return _inject_block(p, "V6_growth_plan_phases", {
        "phases": [
            {
                "number": 1,
                "name": {"en": "Foundations", "es": "Fundaciones"},
                "duration": "Mes 1-2",
                "narrative": {"en": "**Phase 1.** Base.", "es": narrative_es},
            },
            {
                "number": 2,
                "name": {"en": "Expansion", "es": "Expansión"},
                "duration": "Mes 3-6",
                "narrative": {"en": "Scale.", "es": "Escalar."},
            },
            {
                "number": 3,
                "name": {"en": "Defense", "es": "Defensa"},
                "duration": "Mes 7+",
                "narrative": {"en": "Hold.", "es": "Sostener."},
            },
        ]
    })


def test_render_v6_bold_renders():
    """V6 renderiza el narrative con **bold** → <strong> en el HTML."""
    p = _proposal_with_v6_data("**Fase 1 — Fundaciones.** Estabilizar ASINs core.")
    html = render_proposal_html(p, "es")
    assert "<strong>Fase 1 — Fundaciones.</strong>" in html
    assert "Fundaciones" in html       # name.es resuelto por pick_lang
    assert "Mes 1-2" in html           # duration
    assert "None" not in html


def test_render_v6_narrative_xss_escaped():
    """TEST DE SEGURIDAD end-to-end: un <script> en el narrative queda escapado."""
    p = _proposal_with_v6_data("**Ok** <script>steal()</script>")
    html = render_proposal_html(p, "es")
    assert "&lt;script&gt;" in html
    assert "<script>steal()</script>" not in html
    assert "<strong>Ok</strong>" in html


# ─────────────────────────────────────────────────────────────────────────────
# COMMIT F — template V4_listing_improvements_current_state
# ─────────────────────────────────────────────────────────────────────────────


def _proposal_with_v4_data() -> dict:
    """Proposal launch con V4 poblado: url + items con los 3 status + notes null."""
    p = _launch_proposal()
    for b in p["blocks"]:
        if b["module_id"] == "V4_listing_improvements_current_state":
            b["data"] = {
                "current_state_url": "https://example.com/ZEBRA-shot.jpg",
                "items": [
                    {"name": "Main image", "status": "present", "notes": "1500x1500 OK"},
                    {"name": "Infographics", "status": "weak", "notes": "2 de 7 slots"},
                    {"name": "A+ content", "status": "missing", "notes": None},  # null → omitir
                ],
            }
    return p


def test_render_v4_badges_and_url():
    """V4: badges lang-aware con LABEL de texto + URL como link; notes null omitido."""
    p = _proposal_with_v4_data()
    html = render_proposal_html(p, "es")
    # LABEL de texto dentro del badge (no solo color) — ES
    assert "Presente" in html
    assert "Débil" in html
    assert "Falta" in html
    # name + notes presentes
    assert "Main image" in html
    assert "1500x1500 OK" in html
    # URL como link clickeable
    assert "ZEBRA-shot.jpg" in html
    # Gotcha B3-d-bis: notes=None NO debe aparecer como 'None'.
    assert "None" not in html


def test_render_v4_badges_english():
    """V4: los labels de status cambian a inglés con lang='en'."""
    p = _proposal_with_v4_data()
    html = render_proposal_html(p, "en")
    assert "Present" in html
    assert "Weak" in html
    assert "Missing" in html
    assert "None" not in html
