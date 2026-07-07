"""Case study → PDF (bytes). Reusa el sanitizer de M29 (`core/proposal_pdf`).

Función pura, sin Streamlit. El HTML lo produce `core/case_study_html`; acá solo
se pasa por el sanitizer de xhtml2pdf de M29 (quita fuentes remotas, resuelve
`var()`, normaliza `letter-spacing` em, remueve el flex `space-between`) y se
renderiza con pisa. Mismo motor que M29 para consistencia (decisión del .md M31).
"""

from __future__ import annotations

import io
import re

from xhtml2pdf import pisa

from core.case_study_html import render_case_study_html
from core.proposal_pdf import _sanitize_html_for_pdf  # REUSO del sanitizer de M29

# `@import url(...Google Fonts...)` dentro de <style>. El sanitizer de M29 solo
# remueve <link> a fuentes remotas, NO el @import; sin esto xhtml2pdf intenta
# bajar la fuente por red y escupe un traceback (no fatal, pero ruidoso y lento).
# Se remueve SOLO en el camino PDF — el HTML de WordPress conserva su @import.
_FONT_IMPORT_RE = re.compile(r"@import\s+url\([^)]*\)\s*;", re.IGNORECASE)

# xhtml2pdf no renderiza el círculo .steps .n (border-radius + inline-block fijo): sale un
# cuadrado roto con el número pegado al título. En el camino PDF reemplazamos el <span class="n">
# por el número en negrita naranja + punto, y forzamos que el <li> no muestre bullet.
_STEP_N_RE = re.compile(r'<span class="n">(\d+)</span>')


def _simplify_steps_for_pdf(html: str) -> str:
    """Reemplaza el círculo numerado (roto en xhtml2pdf) por '<b>N.</b>' naranja.

    También fuerza list-style:none inline en los <li> de .steps para matar el bullet
    que reportlab a veces mete igual. Seguro globalmente: en el HTML del case study
    los únicos <li>/<ul> son los de .steps (ver core/case_study_html._steps_html).
    """
    html = _STEP_N_RE.sub(r'<b><font color="#FF3300">\1.</font></b> ', html)
    # el <li> del step: forzar sin bullet (reportlab ignora el list-style del CSS a veces)
    html = html.replace('<ul class="steps">', '<ul class="steps" style="list-style-type:none;">')
    html = html.replace("<li>", '<li style="list-style-type:none;">')
    return html


def render_case_study_pdf(data: dict, lang: str) -> bytes:
    """Renderiza el case study a PDF (bytes). Función pura.

    Args:
        data: el cs_result completo `{en, es, meta}`.
        lang: 'en' | 'es'.

    Returns:
        Los bytes del PDF.

    Raises:
        RuntimeError: si xhtml2pdf reporta errores de render.
    """
    html = render_case_study_html(data, lang)
    html = _sanitize_html_for_pdf(html)
    html = _FONT_IMPORT_RE.sub("", html)  # evita el fetch de fuente por red en PDF
    html = _simplify_steps_for_pdf(html)  # arregla el círculo numerado roto en xhtml2pdf
    buf = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"xhtml2pdf falló: {result.err} errores")
    return buf.getvalue()
