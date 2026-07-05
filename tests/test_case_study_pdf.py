"""Tests de la capa PDF del case study (M32 Fase 3).

Herméticos: `render_case_study_pdf` es una función pura sobre el HTML del caso.
No se comparan tamaños ni pixels (frágil): solo que el output es un PDF no vacío
que corre en 'es' y 'en' sin excepción y empieza con el magic b'%PDF'.
"""

from __future__ import annotations

from core.case_study_pdf import render_case_study_pdf

CS_SAMPLE = {
    "en": {
        "headline": "10% CTR Lift",
        "subhead": "sub",
        "metrics": [{"value": "10%", "label": "CTR"}],
        "challenge": "challenge body en",
        "approach": "approach body en",
        "approach_steps": [{"title": "Audit", "text": "t"}],
        "results": "results body en",
    },
    "es": {
        "headline": "Aumento 10%",
        "subhead": "sub es",
        "metrics": [{"value": "10%", "label": "CTR"}],
        "challenge": "challenge body es",
        "approach": "approach body es",
        "approach_steps": [],
        "results": "results body es",
    },
    "meta": {"brand": "lenovo", "can_mention": True, "market": ""},
}


def test_returns_nonempty_bytes():
    """render_case_study_pdf devuelve bytes no vacíos."""
    pdf = render_case_study_pdf(CS_SAMPLE, "en")
    assert isinstance(pdf, bytes)
    assert len(pdf) > 0


def test_starts_with_pdf_magic():
    """Los bytes empiezan con el magic number b'%PDF'."""
    pdf = render_case_study_pdf(CS_SAMPLE, "en")
    assert pdf[:4] == b"%PDF"


def test_smoke_es_en():
    """Smoke: corre en 'es' y 'en' sin crashear, ambos %PDF."""
    for lang in ("es", "en"):
        pdf = render_case_study_pdf(CS_SAMPLE, lang)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"


def test_no_font_import_in_pdf_path():
    """El @import de Google Fonts se remueve antes de entrar al motor PDF.

    El sanitizer de M29 solo quita <link> remotos; el @import lo remueve el strip
    local de case_study_pdf. Sin esto xhtml2pdf intenta bajar la fuente por red.
    """
    from core.case_study_html import render_case_study_html
    from core.case_study_pdf import _FONT_IMPORT_RE
    from core.proposal_pdf import _sanitize_html_for_pdf

    html = _sanitize_html_for_pdf(render_case_study_html(CS_SAMPLE, "en"))
    html = _FONT_IMPORT_RE.sub("", html)
    assert "@import" not in html
