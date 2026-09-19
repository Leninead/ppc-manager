"""Generador de HTML del case study (M32) — fuente única para WordPress y PDF.

Función pura, sin Streamlit: recibe el `cs_result` completo ({en, es, meta}) y un
idioma, y devuelve un bloque `<div class="capybaras-cs">` self-contained (con
`<style>` inline) listo para pegar en WordPress o para pasar al motor de PDF.

Identidad visual propia del export (decisión registrada en el .md de M31): paleta
Ramiro `#F4F1EC` fondo · `#0E0E0E` texto · `#FF3300` acento · Hanken Grotesk. NO
se unifica con la paleta M29 acá (eso aplica solo al render del bloque V7 dentro
de una Proposal).

PDF-compat desde el arranque (para no pelear con el sanitizer de M29 después):
- Sin `var(--x)` — se emite hex directo.
- Sin `letter-spacing` en `em` — se usa `px`/`normal`.
- La `.metricband` usa `display:flex` SIN `justify-content:space-between`, así que
  sobrevive al sanitizer (que solo remueve ese patrón puntual). En PDF el flex se
  ignora y las métricas apilan — degradación aceptada, igual que M29.
- El `@import` de Google Fonts carga en WordPress/browser; para PDF el motor lo
  ignora (y el sanitizer del lado PDF lo neutraliza). El texto cae a la fuente
  default del motor sin romper.
"""

from __future__ import annotations

import html

# ─────────────────────────────────────────────────────────────────────────────
# CSS del bloque .capybaras-cs (paleta Ramiro, PDF-compat)
# ─────────────────────────────────────────────────────────────────────────────

_CS_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;700;800&display=swap');
.capybaras-cs{background:#F4F1EC;color:#0E0E0E;padding:36px 32px;
 font-family:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;}
.capybaras-cs .doc{max-width:760px;margin:0 auto;}
.capybaras-cs .eyebrow{display:flex;align-items:center;gap:12px;margin-bottom:20px;}
.capybaras-cs .eyebrow span{font-size:12px;font-weight:700;text-transform:uppercase;
 color:#FF3300;letter-spacing:normal;}
.capybaras-cs .eyebrow .bar{flex:1;height:2px;background:#FF3300;}
.capybaras-cs .head{font-size:40px;font-weight:800;line-height:1.05;
 margin:0 0 14px 0;color:#0E0E0E;}
.capybaras-cs .subhead{font-size:17px;line-height:1.5;color:#444444;margin:0 0 28px 0;}
.capybaras-cs .metricband{display:flex;flex-wrap:wrap;margin:0 0 30px 0;}
.capybaras-cs .metric{background:#0E0E0E;color:#F4F1EC;padding:16px 22px;
 border-radius:10px;margin:0 14px 12px 0;}
.capybaras-cs .metric .val{font-size:28px;font-weight:800;color:#FF3300;line-height:1;}
.capybaras-cs .metric .lab{font-size:12px;font-weight:500;text-transform:uppercase;
 color:#F4F1EC;margin-top:6px;}
.capybaras-cs .block{margin:0 0 28px 0;}
.capybaras-cs .block-tag{font-size:13px;font-weight:800;color:#FF3300;
 margin-bottom:4px;letter-spacing:normal;}
.capybaras-cs .block h2{font-size:22px;font-weight:800;margin:0 0 10px 0;color:#0E0E0E;}
.capybaras-cs .block .body{font-size:15px;line-height:1.6;color:#1A1A1A;}
.capybaras-cs .block .body p{margin:0 0 10px 0;}
.capybaras-cs .steps{list-style:none;padding:0;margin:14px 0 0 0;}
.capybaras-cs .steps li{margin-bottom:12px;}
.capybaras-cs .steps .n{display:inline-block;background:#FF3300;color:#F4F1EC;
 font-weight:800;font-size:12px;width:22px;height:22px;border-radius:11px;
 text-align:center;line-height:22px;margin-right:10px;}
.capybaras-cs .steps .stxt{font-size:15px;line-height:1.5;color:#1A1A1A;}
"""

# Etiquetas por idioma. Tupla por sección: (kicker numérico del block-tag, título h2).
# El "01 / The Challenge" del spec se logra visualmente con el kicker "01" sobre el
# h2 "The Challenge" (número + nombre), sin duplicar texto.
_SECTIONS = {
    "en": {
        "eyebrow": "Case Study",
        "challenge": ("01", "The Challenge"),
        "approach": ("02", "The Approach"),
        "results": ("03", "The Results"),
    },
    "es": {
        "eyebrow": "Caso de Éxito",
        "challenge": ("01", "El Desafío"),
        "approach": ("02", "El Enfoque"),
        "results": ("03", "Los Resultados"),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privados
# ─────────────────────────────────────────────────────────────────────────────


def _p(text: str) -> str:
    """Párrafo escapado. Cadena vacía si no hay texto (no emite <p> vacío)."""
    text = (text or "").strip()
    return f"<p>{html.escape(text)}</p>" if text else ""


def _metricband_html(metrics: list) -> str:
    """`.metricband` con una `.metric` por item. Vacío si no hay métricas."""
    if not metrics:
        return ""
    cells = "".join(
        f'<div class="metric"><div class="val">'
        f'{html.escape(str(m.get("value", "")))}</div>'
        f'<div class="lab">{html.escape(str(m.get("label", "")))}</div></div>'
        for m in metrics
    )
    return f'<div class="metricband">{cells}</div>'


def _steps_html(steps: list) -> str:
    """`<ul class="steps">` numerada. Vacío si no hay steps."""
    if not steps:
        return ""
    items = "".join(
        f'<li><span class="n">{i}</span>'
        f'<span class="stxt"><b>{html.escape(str(s.get("title", "")))}</b> — '
        f'{html.escape(str(s.get("text", "")))}</span></li>'
        for i, s in enumerate(steps, start=1)
    )
    return f'<ul class="steps">{items}</ul>'


def _block_html(tag: str, title: str, body: str, extra: str = "") -> str:
    """Bloque Challenge/Approach/Results: kicker + h2 + body (+ steps opcional)."""
    return (
        f'<div class="block">'
        f'<div class="block-tag">{tag}</div>'
        f'<h2>{html.escape(title)}</h2>'
        f'<div class="body">{_p(body)}</div>'
        f"{extra}"
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────


def render_case_study_html(data: dict, lang: str) -> str:
    """Arma el bloque `<div class="capybaras-cs">` del case study desde el JSON.

    Args:
        data: el cs_result completo `{en, es, meta}`.
        lang: 'en' | 'es'. Cae a 'en' si el idioma pedido no tiene contenido.

    Returns:
        HTML self-contained (con `<style>` inline) listo para WordPress o PDF.
    """
    lang = "es" if str(lang).lower() == "es" else "en"
    data = data or {}
    d = data.get(lang) or data.get("en") or {}
    labels = _SECTIONS[lang]

    headline = html.escape((d.get("headline") or "").strip())
    subhead = html.escape((d.get("subhead") or "").strip())

    ch_tag, ch_title = labels["challenge"]
    ap_tag, ap_title = labels["approach"]
    re_tag, re_title = labels["results"]

    doc = (
        f'<div class="eyebrow"><span>{html.escape(labels["eyebrow"])}</span>'
        f'<span class="bar"></span></div>'
        f'<h1 class="head">{headline}</h1>'
        f'<p class="subhead">{subhead}</p>'
        f"{_metricband_html(d.get('metrics') or [])}"
        f"{_block_html(ch_tag, ch_title, d.get('challenge', ''))}"
        f"{_block_html(ap_tag, ap_title, d.get('approach', ''), _steps_html(d.get('approach_steps') or []))}"
        f"{_block_html(re_tag, re_title, d.get('results', ''))}"
    )

    return (
        f"<style>{_CS_CSS}</style>"
        f'<div class="capybaras-cs"><div class="doc">{doc}</div></div>'
    )
