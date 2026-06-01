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
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

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


def _build_env() -> Environment:
    """Environment Jinja2 anclado al dir absoluto de templates, autoescape ON."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ABS)),
        autoescape=select_autoescape(enabled_extensions=("html",), default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _catalog_title_index() -> dict:
    """{module_id: {en, es}} desde el catálogo (solo lectura, anclado a repo root)."""
    catalog = json.loads(_CATALOG_ABS.read_text(encoding="utf-8"))
    return {m["module_id"]: m.get("title", {}) for m in catalog.get("modules", [])}


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
    titles = _catalog_title_index()

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
        data = block.get("data") or {}  # {} es estado normal (FIXED + V17-V22)
        copy_overrides = block.get("copy_overrides") or {}
        # copy_overrides shape: {en: {...}, es: {...}} → el sub-dict del lang activo.
        copy = copy_overrides.get(lang) or copy_overrides.get("es") or {}
        title = _pick_lang(titles.get(module_id, {}), lang)

        template_name = f"{module_id}.html"
        if not _template_exists(template_name):
            template_name = _PLACEHOLDER_TEMPLATE

        tmpl = env.get_template(template_name)
        block_html = tmpl.render(
            data=data,
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
