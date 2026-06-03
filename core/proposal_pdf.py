"""Capa PDF de propuestas (S6).

Función pura `render_proposal_pdf(proposal, lang) -> bytes` construida ENCIMA del
renderer HTML (`core.proposal_renderer.render_proposal_html`). Mismo contrato puro:
sin streamlit, sin escritura a disco, sin side effects.

Se mantiene en un módulo separado a propósito: importar xhtml2pdf arrastra un stack
pesado (reportlab / svglib / lxml / pypdf), y no queremos cargar ese peso dentro del
renderer HTML puro (que se usa en tests herméticos y en el preview liviano). Quien
necesita PDF importa explícitamente desde acá.

El motor xhtml2pdf (reportlab) NO soporta dos cosas que el template HTML moderno usa:
remote web-fonts (`<link>` a Google Fonts → descarga woff2 que reportlab no parsea) y
CSS custom properties (`var(--x)` → ValueError duro en propiedades de color). Como NO
podemos tocar el renderer ni su template (contrato S5), la adaptación a las
limitaciones del motor PDF vive acá, en `_sanitize_html_for_pdf`: el HTML que el
cliente recibe en el browser sigue intacto; solo el que entra al motor PDF se ajusta.
"""

from __future__ import annotations

import io
import re

from xhtml2pdf import pisa

from core.proposal_renderer import render_proposal_html


# Remote web-fonts: xhtml2pdf intenta bajar el CSS de Google Fonts y sus woff2;
# reportlab no parsea woff2 como TTF → TTFError. Los quitamos (cae a fuentes default).
_REMOTE_FONT_LINK_RE = re.compile(
    r"<link\b[^>]*fonts\.(?:googleapis|gstatic)\.com[^>]*>",
    re.IGNORECASE,
)

# Definiciones de CSS custom properties: `--name: value;`.
_CSS_VAR_DEF_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+);")

# Usos `var(--name)` o `var(--name, fallback)`.
_CSS_VAR_USE_RE = re.compile(r"var\(\s*(--[^)]*)\)")


def _sanitize_html_for_pdf(html: str) -> str:
    """Ajusta el HTML a las limitaciones del motor xhtml2pdf, sin cambiar semántica.

    1. Quita los `<link>` a fuentes remotas (Google Fonts) que reportlab no puede
       cargar; el texto cae a las fuentes default del motor.
    2. Resuelve las CSS custom properties: junta las definiciones `--name: value;`
       y reemplaza cada `var(--name[, fallback])` por su valor resuelto (o el
       fallback). xhtml2pdf no entiende `var()` y rompe en propiedades de color.
    """
    html = _REMOTE_FONT_LINK_RE.sub("", html)

    var_defs = {
        m.group(1).strip(): m.group(2).strip()
        for m in _CSS_VAR_DEF_RE.finditer(html)
    }

    def _resolve(match: "re.Match") -> str:
        inner = match.group(1)
        name, _, fallback = inner.partition(",")
        return var_defs.get(name.strip(), fallback.strip())

    # Loop acotado: cubre el caso (raro acá) de variables que referencian variables.
    for _ in range(5):
        resolved = _CSS_VAR_USE_RE.sub(_resolve, html)
        if resolved == html:
            break
        html = resolved

    return html


def render_proposal_pdf(proposal: dict, lang: str) -> bytes:
    """Renderiza una Proposal a PDF (bytes). Función pura.

    Genera el HTML con `render_proposal_html`, lo adapta a las limitaciones del
    motor PDF (`_sanitize_html_for_pdf`) y lo convierte vía
    `xhtml2pdf.pisa.CreatePDF`, escribiendo a un buffer en memoria.

    Args:
        proposal: dict con shape proposal-v1.
        lang: 'es' | 'en'.

    Returns:
        bytes del PDF.

    Raises:
        RuntimeError: si xhtml2pdf reporta error durante la conversión.
    """
    html = render_proposal_html(proposal, lang)
    html = _sanitize_html_for_pdf(html)

    buffer = io.BytesIO()
    status = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")

    if status.err:
        raise RuntimeError(
            f"xhtml2pdf falló al generar el PDF (err={status.err})."
        )

    return buffer.getvalue()
