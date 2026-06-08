"""Tests de la capa PDF de propuestas (S6).

Herméticos: construyen la Proposal en memoria vía
`instantiate_proposal_from_template` (igual que test_proposal_renderer.py), sin
depender de `data/sales/proposals/`. `render_proposal_pdf` es una función pura
sobre el renderer HTML que devuelve los bytes del PDF.

No se comparan tamaños exactos ni pixels (frágil): solo que el output es un PDF
no vacío y que el flujo corre en 'es' y 'en' sin levantar excepción.
"""

from __future__ import annotations

import re

import core.proposal_persistence as pp
from core.proposal_pdf import render_proposal_pdf, _sanitize_html_for_pdf


def _launch_proposal(client_name: str = "Capybaras Test Client") -> dict:
    """Proposal launch instanciada (todos los blocks con data={} por default)."""
    return pp.instantiate_proposal_from_template(
        archetype="launch",
        client_name=client_name,
        language="es",
        sales_director="Lenin Acosta",
    )


def test_render_pdf_returns_nonempty_bytes():
    """render_proposal_pdf devuelve bytes no vacíos."""
    p = _launch_proposal()
    pdf = render_proposal_pdf(p, "es")
    assert isinstance(pdf, bytes)
    assert len(pdf) > 0


def test_render_pdf_starts_with_pdf_magic():
    """Los bytes empiezan con el magic number b'%PDF'."""
    p = _launch_proposal()
    pdf = render_proposal_pdf(p, "es")
    assert pdf[:4] == b"%PDF"


def test_render_pdf_smoke_es_en():
    """Smoke: corre sobre el seed sin crashear en 'es' y en 'en'."""
    p = _launch_proposal()
    for lang in ("es", "en"):
        pdf = render_proposal_pdf(p, lang)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"


def test_sanitize_strips_em_letterspacing_and_flex_header():
    """Tras el sanitizado, el HTML que entra al motor PDF NO tiene letter-spacing en
    `em` ni el flex `display: flex; justify-content: space-between` (xhtml2pdf no los
    maneja). Se testea _sanitize_html_for_pdf directamente sobre un HTML mínimo."""
    raw = (
        "<style>.k { letter-spacing: 0.08em; } "
        ".j { letter-spacing: 0.02em; }</style>"
        '<div style="display: flex; justify-content: space-between; '
        'align-items: baseline; font-size: 0.83rem;">'
        "<span>label</span><span>value</span></div>"
    )
    out = _sanitize_html_for_pdf(raw)

    # Ninguna letter-spacing en em sobrevive (regex precisa: no confundir con `rem`).
    assert re.search(r"letter-spacing:\s*[\d.]+em", out) is None
    assert "letter-spacing: normal;" in out
    # El patrón flex roto desapareció.
    assert "display: flex; justify-content: space-between" not in out
    # El resto del style inline se preserva (degradación mínima, no destructiva).
    assert "align-items: baseline" in out
    assert "<span>label</span>" in out and "<span>value</span>" in out
