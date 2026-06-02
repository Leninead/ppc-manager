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
    _compute_bar_chart,
    _effective_data,
    _md_bold,
    _normalize_asset,
    _normalize_assets,
    _template_exists,
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


# ─────────────────────────────────────────────────────────────────────────────
# COMMIT G — normalización assets V5 (renderer) + template V5_listing_comparison
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_asset_string():
    """str → {url: str, caption: '', alt: ''}."""
    assert _normalize_asset("http://x/img.jpg") == {
        "url": "http://x/img.jpg", "caption": "", "alt": ""
    }


def test_normalize_asset_dict_defaults():
    """dict → campos con defaults; alt cae a caption si no viene."""
    assert _normalize_asset({"url": "u", "caption": "cap"}) == {
        "url": "u", "caption": "cap", "alt": "cap"
    }
    # alt explícito gana sobre caption
    assert _normalize_asset({"url": "u", "caption": "cap", "alt": "ALT"})["alt"] == "ALT"
    # dict vacío → todo ""
    assert _normalize_asset({}) == {"url": "", "caption": "", "alt": ""}


def test_normalize_assets_empty_and_nonlist():
    """None / no-lista → []; lista mixta str+dict → todas forma única."""
    assert _normalize_assets(None) == []
    assert _normalize_assets("not a list") == []
    assert _normalize_assets([]) == []
    out = _normalize_assets(["http://x.jpg", {"url": "u", "caption": "c"}])
    assert out == [
        {"url": "http://x.jpg", "caption": "", "alt": ""},
        {"url": "u", "caption": "c", "alt": "c"},
    ]


def _proposal_with_v5_data() -> dict:
    """Proposal launch + block V5 inyectado con assets heterogéneos (str + dict + vacío)."""
    p = _launch_proposal()
    return _inject_block(p, "V5_listing_comparison_competitor", {
        "comparison_groups": [
            {
                "type": "main_image",
                "client_assets": ["https://example.com/ZEBRA-client-main.jpg"],   # str
                "competitor_assets": [
                    {"url": "https://example.com/comp-main.jpg", "caption": "ZEBRA_CAPTION"}  # dict
                ],
                "commentary": "El competidor satura el fondo; nuestro main queda más limpio.",
            },
            {
                "type": "a_plus",
                "client_assets": [],                                              # vacío → "Sin assets"
                "competitor_assets": [{"url": "https://example.com/comp-aplus.jpg", "caption": "A+ comp"}],
                "commentary": {"en": "Competitor has A+, we don't.", "es": "El competidor tiene A+, nosotros no."},
            },
        ]
    })


def test_render_v5_assets_normalized():
    """V5: str→<img>, dict→<img>+caption, array vacío→'Sin assets', sin 'None'."""
    p = _proposal_with_v5_data()
    html = render_proposal_html(p, "es")
    # str asset → <img src=...>
    assert "ZEBRA-client-main.jpg" in html
    assert "<img" in html
    # dict asset → caption renderizada
    assert "ZEBRA_CAPTION" in html
    # array vacío (client_assets de a_plus) → "Sin assets"
    assert "Sin assets" in html
    # subtítulo de tipo lang-aware
    assert "Imagen principal" in html
    assert "Contenido A+" in html
    # commentary (str y {en,es} resuelto por pick_lang)
    assert "El competidor satura el fondo" in html
    assert "El competidor tiene A+, nosotros no." in html
    # defensivo: onerror presente para degradar a caption
    assert "onerror" in html
    # Gotcha B3-d-bis
    assert "None" not in html


def test_render_v5_english_labels():
    """V5: type subtitle y column heads en inglés con lang='en'."""
    p = _proposal_with_v5_data()
    html = render_proposal_html(p, "en")
    assert "Main image" in html
    assert "A+ Content" in html
    assert "No assets" in html
    # El apóstrofo se autoescapa (&#39;) — correcto; asserto la parte sin comilla.
    assert "Competitor has A+, we don" in html
    assert "None" not in html


# ─────────────────────────────────────────────────────────────────────────────
# COMMIT H — smoke combinado V4/V5/V6 + verificación del reparto own/placeholder
# ─────────────────────────────────────────────────────────────────────────────

# Reparto esperado (espejo del seed completo): 14 con template propio, 6 placeholder.
# V1–V6 (todos los CORE launch) + F1–F8 tienen template propio; V17–V22 al placeholder.
_OWN_TEMPLATE_IDS = [
    "F1_cover", "F2_about_stats", "F3_brand_stages", "F4_operation_pillars",
    "F5_case_studies", "F6_why_capybaras", "F7_team", "F8_lets_scale",
    "V1_brand_overview", "V2_category_overview", "V3_seo_opportunity",
    "V4_listing_improvements_current_state", "V5_listing_comparison_competitor",
    "V6_growth_plan_phases",
]
_PLACEHOLDER_IDS = [
    "V17_made_in_country_advantage", "V18_modular_launch_strategy",
    "V19_amazon_launch_grid", "V20_shopify_d2c_channel",
    "V21_meta_ads_growth", "V22_walmart_marketplaces",
]


def test_template_split_14_own_6_placeholder():
    """Reparto del seed: 14 module_ids con template propio, 6 caen al placeholder."""
    assert len(_OWN_TEMPLATE_IDS) == 14
    assert len(_PLACEHOLDER_IDS) == 6
    for mid in _OWN_TEMPLATE_IDS:
        assert _template_exists(f"{mid}.html"), f"{mid} debería tener template propio"
    for mid in _PLACEHOLDER_IDS:
        assert not _template_exists(f"{mid}.html"), f"{mid} debería caer al placeholder"


def test_smoke_v4_v5_v6_render_clean():
    """Smoke combinado: V4+V5+V6 poblados renderizan limpio (0 None/{{}}/dicts crudos)."""
    p = _proposal_with_v4_data()  # V4 ya poblado (está en el archetype launch)
    # Inyecto V5 y V6 reutilizando las mismas formas de datos de G/E.
    for b in _proposal_with_v5_data()["blocks"]:
        if b["module_id"] == "V5_listing_comparison_competitor":
            _inject_block(p, b["module_id"], b["data"])
    for b in _proposal_with_v6_data("**Fase 1.** Base.")["blocks"]:
        if b["module_id"] == "V6_growth_plan_phases":
            _inject_block(p, b["module_id"], b["data"])

    html = render_proposal_html(p, "es")
    # Conteos esperados 0/0/0 (espejo del smoke manual sobre el seed).
    assert "None" not in html                       # B3-d-bis
    assert "{{" not in html and "{%" not in html    # nada de Jinja sin renderizar
    assert "{'en'" not in html and "{&#39;en&#39;" not in html  # sin dicts crudos
    assert "{'es'" not in html and "{&#39;es&#39;" not in html
    # Las 3 secciones con template propio presentes.
    assert 'data-module="V4_listing_improvements_current_state"' in html
    assert 'data-module="V5_listing_comparison_competitor"' in html
    assert 'data-module="V6_growth_plan_phases"' in html


# ─────────────────────────────────────────────────────────────────────────────
# COMMIT I — helper _compute_bar_chart + template V3_seo_opportunity
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_bar_chart_share_of_total():
    """width_pct = value / SUMA × 100 (share del total, no del máximo)."""
    bars = _compute_bar_chart(
        [{"label": "Tu marca", "value": 3},
         {"label": "Competidor A", "value": 8},
         {"label": "Competidor B", "value": 5}],
        "Tu marca",
    )
    # 3/16=18.75 · 8/16=50.0 · 5/16=31.25
    assert [b["width_pct"] for b in bars] == [18.75, 50.0, 31.25]
    assert bars[0]["is_client"] is True
    assert bars[1]["is_client"] is False and bars[2]["is_client"] is False


def test_compute_bar_chart_client_match_not_first():
    """is_client matchea por label (laxo, case-insensitive), no solo la primera."""
    bars = _compute_bar_chart(
        [{"label": "Competidor A", "value": 8}, {"label": "Acme Co", "value": 2}],
        "acme co",
    )
    assert bars[0]["is_client"] is False
    assert bars[1]["is_client"] is True


def test_compute_bar_chart_client_fallback_first():
    """Si ningún label matchea client_name → la primera barra es el cliente."""
    bars = _compute_bar_chart(
        [{"label": "A", "value": 1}, {"label": "B", "value": 1}],
        "marca inexistente",
    )
    assert bars[0]["is_client"] is True
    assert bars[1]["is_client"] is False


def test_compute_bar_chart_sum_zero():
    """Todos los values 0 → width_pct 0 (sin división por cero)."""
    bars = _compute_bar_chart(
        [{"label": "A", "value": 0}, {"label": "B", "value": 0}], "A"
    )
    assert all(b["width_pct"] == 0.0 for b in bars)


def test_compute_bar_chart_empty_and_invalid():
    """None/no-lista → []; filtra puntos sin label, value negativo o bool."""
    assert _compute_bar_chart([], "X") == []
    assert _compute_bar_chart(None, "X") == []
    assert _compute_bar_chart("nope", "X") == []
    bars = _compute_bar_chart(
        [{"value": 5},                       # sin label → fuera
         {"label": "ok", "value": 4},        # válido
         {"label": "neg", "value": -1},      # negativo → fuera
         {"label": "booly", "value": True}], # bool → fuera
        "ok",
    )
    assert len(bars) == 1 and bars[0]["label"] == "ok"


def _proposal_with_v3_data(chart_data) -> dict:
    """Proposal launch (client='Tu Marca') + block V3 inyectado con los 3 campos."""
    p = _launch_proposal("Tu Marca")
    return _inject_block(p, "V3_seo_opportunity", {
        "missing_keywords": [
            {"keyword": "saco para dormir bebe", "sv": 46836,
             "current_rank": None, "opportunity_score": 0.92},   # null rank → "No rankea"
            {"keyword": "swaddle", "sv": 12450,
             "current_rank": 18, "opportunity_score": 0.78},
        ],
        "launch_score_table": [
            {"asin": "B09MG1J3LC", "phase": "Launch", "score": 82, "status": "ready"},
            {"asin": "B0CK2KCBLS", "phase": "Launch", "score": 71, "status": "needs_listing"},
        ],
        "page1_domination_chart_data": chart_data,
    })


def test_render_v3_tables_and_chart_es():
    """V3 ES: tablas + chart con barra del cliente flaggeada; sin 'None'."""
    chart = [{"label": "Tu Marca", "value": 3},
             {"label": "Competidor A", "value": 8},
             {"label": "Competidor B", "value": 5}]
    p = _proposal_with_v3_data(chart)
    html = render_proposal_html(p, "es")
    # missing_keywords
    assert "saco para dormir bebe" in html
    assert "No rankea" in html          # current_rank None → label, no "None"
    assert "#18" in html                # rank presente
    # launch_score_table badges (ES)
    assert "Listo" in html
    assert "Falta listing" in html
    assert "B09MG1J3LC" in html
    # chart: la barra del cliente sale marcada "(vos)"
    assert "(vos)" in html
    # B3-d-bis
    assert "None" not in html


def test_render_v3_empty_chart_shows_sin_datos():
    """page1_domination_chart_data=[] (como el seed) → 'Sin datos de chart'."""
    p = _proposal_with_v3_data([])
    html = render_proposal_html(p, "es")
    assert "Sin datos de chart" in html
    assert "None" not in html


def test_render_v3_english():
    """V3 EN: labels de rank/status/chart en inglés."""
    p = _proposal_with_v3_data([{"label": "Tu Marca", "value": 1}])
    html = render_proposal_html(p, "en")
    assert "Not ranking" in html
    assert "Ready" in html
    assert "Needs listing" in html
    assert "(you)" in html
    assert "None" not in html
