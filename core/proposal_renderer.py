"""Renderer HTML de propuestas (S5).

Convierte una Proposal (dict, shape proposal-v1) en un documento HTML light que
el cliente recibe y que en S6 se imprimirá a PDF.

Diseño:
- Función PURA `render_proposal_html(proposal, lang) -> str`: sin streamlit, sin
  escritura a disco, sin side effects. Lee el catálogo (solo lectura) para los
  títulos bilingües de sección.
- Jinja2 con un template por bloque (`{module_id}.html`) + `_base.html` de layout.
  Si un module_id no tiene template propio → cae a `_placeholder.html` (no rompe).
- La lógica "qué template toca cada bloque + fallback a placeholder" vive ACÁ
  (Python). El template solo itera e inyecta el HTML pre-renderizado de cada bloque.
- Autoescape ACTIVO: los datos de cliente que van DENTRO de cada sub-template se
  escapan contra HTML injection. El HTML pre-renderizado de cada bloque se marca
  como seguro en el punto de inyección (`markupsafe.Markup`), así Jinja2 no lo
  re-escapa al meterlo en `_base.html`.
- cwd-independiente: TEMPLATES_HTML_DIR y CATALOG_FILE (relativos en
  proposal_paths) se resuelven a absoluto anclados contra la raíz del repo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from core.proposal_paths import CATALOG_FILE, TEMPLATES_HTML_DIR

# ─────────────────────────────────────────────────────────────────────────────
# Anclaje cwd-independiente: core/ → raíz del repo
# ─────────────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES_ABS = (_REPO_ROOT / TEMPLATES_HTML_DIR).resolve()
_CATALOG_ABS = (_REPO_ROOT / CATALOG_FILE).resolve()

_BASE_TEMPLATE = "_base.html"
_PLACEHOLDER_TEMPLATE = "_placeholder.html"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privados
# ─────────────────────────────────────────────────────────────────────────────


def _pick_lang(field, lang):
    """Cascada bilingüe para campos {en, es}. Réplica de _v6_pick_lang del módulo.

    None → "" · str → tal cual (legacy) · dict → lang → 'es' → primer valor → "".
    Otros tipos → tal cual (los maneja el template).
    """
    if field is None:
        return ""
    if isinstance(field, str):
        return field
    if isinstance(field, dict):
        if lang in field and field[lang]:
            return field[lang]
        if "es" in field and field["es"]:
            return field["es"]
        for v in field.values():
            if v:
                return v
        return ""
    return field


# Markdown-mínimo: solo **bold**. Non-greedy, multilínea (re.DOTALL) por si el
# narrative trae saltos de línea dentro de un par de asteriscos.
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _md_bold(text):
    """`**x**` → `<strong>x</strong>`, seguro contra inyección HTML.

    ORDEN DE SEGURIDAD (no invertir — al revés abre XSS):
      1. escape() PRIMERO → neutraliza HTML hostil del input (`<script>` →
         `&lt;script&gt;`). Los `**` son asteriscos literales, no chars
         especiales de HTML, así que sobreviven intactos al escape.
      2. regex `**x**`→`<strong>x</strong>` DESPUÉS, sobre el texto YA escapado
         → inyectamos NUESTROS `<strong>` de confianza, no los del cliente.
      3. Markup() AL FINAL → marca el resultado como seguro para que Jinja2 (con
         autoescape ON) no re-escape nuestros tags y el bold renderice.

    None → "". Otros tipos → se castean a str antes de escapar.
    """
    if text is None:
        return Markup("")
    escaped = str(escape(str(text)))            # paso 1: <script> ya neutralizado
    bolded = _MD_BOLD_RE.sub(r"<strong>\1</strong>", escaped)  # paso 2: bold de confianza
    return Markup(bolded)                        # paso 3: seguro en el punto de inyección


def _build_env() -> Environment:
    """Environment Jinja2 anclado al dir absoluto de templates, autoescape ON.

    Registra dos filtros compartidos por todos los sub-templates:
    - `pick_lang`: resuelve campos bilingües {en, es} → `{{ campo | pick_lang(lang) }}`.
    - `md_bold`: markdown-mínimo `**x**`→<strong>, escape-first (anti-XSS) →
      `{{ campo | pick_lang(lang) | md_bold }}`.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ABS)),
        autoescape=select_autoescape(enabled_extensions=("html",), default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["pick_lang"] = _pick_lang
    env.filters["md_bold"] = _md_bold
    return env


def _catalog_module_index() -> dict:
    """{module_id: module_def} desde el catálogo (solo lectura, anclado a repo root)."""
    catalog = json.loads(_CATALOG_ABS.read_text(encoding="utf-8"))
    return {m["module_id"]: m for m in catalog.get("modules", [])}


def _schema_defaults(schema: dict) -> dict:
    """Extrae los `default` por campo del schema del módulo: {field: default_value}.

    Los FIXED (F4 pillars, F6 version+pillars, F7 cross_support_team) declaran su
    contenido fijo acá. Si un campo no tiene `default`, no aparece en el dict.
    """
    if not isinstance(schema, dict):
        return {}
    return {
        field: spec["default"]
        for field, spec in schema.items()
        if isinstance(spec, dict) and "default" in spec
    }


def _effective_data(module: dict, block_data: dict) -> dict:
    """Overlay (approach B): default del catálogo como base, block.data lo pisa.

    - FIXED con data={} → heredan el contenido fijo del schema (F4/F6/F7-cross).
    - Variables sin default → quedan con su block.data tal cual (no-regresivo).
    - Si un campo está en ambos, gana SIEMPRE block.data (el override del operador).
    """
    defaults = _schema_defaults((module or {}).get("schema", {}))
    return {**defaults, **(block_data or {})}


def _normalize_asset(asset) -> dict:
    """Normaliza UN asset a la forma única {url, caption, alt}.

    El template recibe siempre esta forma y solo decide "¿hay url? <img> : caption-solo".
    - str  → {url: str, caption: "", alt: ""}      (URL pelada legacy)
    - dict → {url, caption, alt} con defaults "";  alt cae a caption si no viene
             (decisión: <img alt=caption).
    - otro → {url: "", caption: "", alt: ""}        (defensivo, nunca rompe el for)
    """
    if isinstance(asset, str):
        return {"url": asset, "caption": "", "alt": ""}
    if isinstance(asset, dict):
        caption = asset.get("caption") or ""
        return {
            "url": asset.get("url") or "",
            "caption": caption,
            "alt": asset.get("alt") or caption,
        }
    return {"url": "", "caption": "", "alt": ""}


def _normalize_assets(assets) -> list:
    """Lista de assets heterogéneos → lista de formas {url,caption,alt}.

    None / no-lista → [] (el template muestra "Sin assets", nunca un <img> vacío).
    """
    if not isinstance(assets, list):
        return []
    return [_normalize_asset(a) for a in assets]


_V5_MODULE_ID = "V5_listing_comparison_competitor"
_V3_MODULE_ID = "V3_seo_opportunity"


def _transform_v5_assets(effective_data: dict, proposal_meta: dict) -> dict:
    """V5: normaliza client_assets/competitor_assets de cada comparison_group.

    Pura: devuelve estructuras nuevas, no muta el input. El template recibe assets
    ya uniformados a {url,caption,alt}, sin tener que distinguir str vs dict.
    (proposal_meta no se usa acá — firma uniforme de transform.)
    """
    groups = effective_data.get("comparison_groups")
    if not isinstance(groups, list):
        return effective_data
    new_groups = []
    for g in groups:
        g = dict(g) if isinstance(g, dict) else {}
        g["client_assets"] = _normalize_assets(g.get("client_assets"))
        g["competitor_assets"] = _normalize_assets(g.get("competitor_assets"))
        new_groups.append(g)
    out = dict(effective_data)
    out["comparison_groups"] = new_groups
    return out


def _compute_bar_chart(data, client_name) -> list:
    """page1_domination_chart_data → barras horizontales listas para pintar.

    Cada barra: {label, value, width_pct, is_client}.
    - width_pct = value / SUMA de values válidos × 100 (SHARE DEL TOTAL — cuánto
      ocupa cada marca, no quién tiene el máximo). sum==0 → todos 0% (sin /0).
    - is_client: label matchea client_name (laxo, case-insensitive: uno contenido
      en el otro). Si NINGUNO matchea, la primera barra es el cliente.
    - filtra puntos inválidos: label vacío o value no-numérico/negativo/bool.
    None / no-lista / sin puntos válidos → [] (el template muestra "Sin datos").
    """
    if not isinstance(data, list):
        return []
    pts = []
    for d in data:
        if not isinstance(d, dict):
            continue
        label = d.get("label")
        value = d.get("value")
        if not label:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            continue
        pts.append({"label": label, "value": value})
    if not pts:
        return []
    total = sum(p["value"] for p in pts)
    cname = (client_name or "").strip().lower()
    matched = False
    for p in pts:
        p["width_pct"] = round(p["value"] / total * 100, 2) if total else 0.0
        lbl = p["label"].strip().lower()
        p["is_client"] = bool(cname) and (cname in lbl or lbl in cname)
        if p["is_client"]:
            matched = True
    if not matched:
        pts[0]["is_client"] = True
    return pts


def _transform_v3_chart(effective_data: dict, proposal_meta: dict) -> dict:
    """V3: deriva page1_domination_chart_data → barras pre-computadas (share+is_client).

    Pura. La barra del cliente se detecta contra proposal_meta.client_name. El
    template solo pinta width_pct y elige color según is_client.
    """
    out = dict(effective_data)
    out["page1_domination_chart_data"] = _compute_bar_chart(
        effective_data.get("page1_domination_chart_data"),
        (proposal_meta or {}).get("client_name", ""),
    )
    return out


# Transforms Python por módulo: normalizan/derivan effective_data antes de renderizar.
# La lógica de forma vive en Python (no en el template), por decisión de S5.
# Firma uniforme: transform(effective_data, proposal_meta) -> dict.
_BLOCK_TRANSFORMS = {
    _V5_MODULE_ID: _transform_v5_assets,
    _V3_MODULE_ID: _transform_v3_chart,
}


def _template_exists(name: str) -> bool:
    """¿Existe un sub-template propio para este module_id?"""
    return (_TEMPLATES_ABS / name).is_file()


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────


def render_proposal_html(proposal: dict, lang: str) -> str:
    """Renderiza una Proposal completa a HTML (string). Función pura.

    Args:
        proposal: dict shape proposal-v1 (con 'blocks' en orden).
        lang: 'en' | 'es'. Cualquier otro valor cae a la cascada bilingüe.

    Returns:
        HTML completo del documento como string.
    """
    if lang not in ("en", "es"):
        lang = "es"

    env = _build_env()
    catalog = _catalog_module_index()

    # Metadata de la propuesta — la usan bloques sin data propia (ej. F1_cover).
    proposal_meta = {
        "client_name": proposal.get("client_name", ""),
        "client_industry": proposal.get("client_industry", ""),
        "language": proposal.get("language", lang),
        "archetype": proposal.get("archetype", ""),
        "version": proposal.get("version"),
        "created_at": proposal.get("created_at", ""),
        "updated_at": proposal.get("updated_at", ""),
    }

    rendered_blocks = []
    for block in proposal.get("blocks", []):
        module_id = block.get("module_id", "")
        module = catalog.get(module_id, {})
        block_data = block.get("data") or {}  # {} es estado normal (FIXED + V17-V22)
        # Overlay (approach B): default del catálogo como base, block.data lo pisa.
        effective_data = _effective_data(module, block_data)
        # Transform Python por módulo (ej. V5 normaliza assets a {url,caption,alt}).
        transform = _BLOCK_TRANSFORMS.get(module_id)
        if transform:
            effective_data = transform(effective_data, proposal_meta)
        copy_overrides = block.get("copy_overrides") or {}
        # copy_overrides shape: {en: {...}, es: {...}} → el sub-dict del lang activo.
        copy = copy_overrides.get(lang) or copy_overrides.get("es") or {}
        title = _pick_lang(module.get("title", {}), lang)

        template_name = f"{module_id}.html"
        if not _template_exists(template_name):
            template_name = _PLACEHOLDER_TEMPLATE

        tmpl = env.get_template(template_name)
        block_html = tmpl.render(
            data=effective_data,
            copy=copy,
            module_id=module_id,
            title=title,
            lang=lang,
            proposal=proposal_meta,
        )
        # Markup → seguro en el punto de inyección; _base.html no lo re-escapa.
        rendered_blocks.append({"module_id": module_id, "html": Markup(block_html)})

    base = env.get_template(_BASE_TEMPLATE)
    return base.render(
        rendered_blocks=rendered_blocks,
        lang=lang,
        client_name=proposal_meta["client_name"],
        proposal=proposal_meta,
    )
