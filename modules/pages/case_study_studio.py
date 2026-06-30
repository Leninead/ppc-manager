"""
🏆 Case Study Studio — M32 (Sales Director)

Generador de casos de éxito: el AM responde preguntas (situación inicial →
qué hicimos → resultado) y Claude redacta el caso en 3 actos (EN → ES),
sin inventar métricas. Hermano de Proposal Studio (M29). Persistencia
prevista vía core/persistence.py (capa client-config).

Fase 1 — form de input + doble llamada Claude (EN→ES) + render del resultado.
Sin persistencia (Fase 2), sin exports (Fase 3), sin imágenes (diferido),
sin importer a M29 (v2).
"""

import json

import streamlit as st

from core.ai_analyze import _claude_analyze

# Paleta Capybaras (unificada con M29 Proposal Studio).
_NARANJA = "#E84000"
_NEGRO = "#1F1F1F"
_GRIS_TXT = "#888888"

# Marketplaces disponibles en el selector (opcional). "—" = no especificado.
_MARKETS = [
    "—", "Amazon US", "Amazon MX", "Amazon BR", "MercadoLibre",
    "Walmart", "TikTok Shop", "Shopify",
]

# SOP in-app: guía de uso embebida (expander al tope de render()).
# Stub Fase 1 — se completa en Fase 5.
_SOP_MD = """
### Case Study Studio — cómo usarlo

Genera casos de éxito a partir de tus notas: respondés tres preguntas
(situación inicial → qué hicimos → resultado) y el módulo redacta el caso
en tres actos, primero en inglés y después localizado a español. Regla dura:
**nunca inventa métricas** — si tus notas no traen números, el caso queda cualitativo.

**Pasos:**
1. *¿Sobre quién es esto?* — elegí si se puede mencionar la marca. Si no, el caso
   queda anónimo y se refiere al cliente por su categoría.
2. Completá los tres recuadros (escenario · proceso · resultados). Incluí los
   números reales en el de resultados.
3. *Generar case study* → el módulo escribe el caso en inglés y lo traduce a español.
4. Revisá el resultado con el toggle EN / ES.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers UI
# ─────────────────────────────────────────────────────────────────────────────


def _render_header() -> None:
    """Header del módulo con título + descripción + badge versión."""
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:1rem;margin-bottom:0.25rem;'>"
        f"<span style='font-size:2rem;'>🏆</span>"
        f"<div>"
        f"<div style='font-size:1.5rem;font-weight:800;color:{_NEGRO};'>Case Study Studio</div>"
        f"<div style='font-size:0.85rem;color:{_GRIS_TXT};'>"
        f"Generador de casos de éxito — Sales Director module</div>"
        f"</div>"
        f"<div style='margin-left:auto;background:#1A1A1A;color:{_NARANJA};"
        f"padding:0.4rem 0.8rem;border-radius:8px;font-weight:700;font-size:0.85rem;'>"
        f"M32 · Fase 1</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# Prompts (portados FIELES del HTML de Ramiro — no reescribir)
# ─────────────────────────────────────────────────────────────────────────────


def _build_prompt_en(brand: str, can_mention: bool, market: str,
                     t1: str, t2: str, t3: str) -> str:
    """Prompt EN — 3 actos, voz 'we', regla dura de métricas. JSON-only."""
    if can_mention:
        subject_mode = (
            f'The client may be named. Their name is "{brand}". '
            f"Use it naturally throughout."
        )
    else:
        subject_mode = (
            f"The client must stay ANONYMOUS. Never invent or use a real name. "
            f'Refer to them by the category the user gave: "{brand}" — '
            f'e.g. "a {brand}", "the brand", "this {brand}". '
            f"Build the headline and copy around the category, not a name."
        )

    market_txt = market if market and market != "—" else "(not specified)"

    return f"""You are a senior copywriter at Capybaras Agency, a full-service marketplace growth agency (Amazon, MercadoLibre, Walmart, TikTok Shop, Shopify). Write a concise, confident agency case study from the rough notes below.

VOICE & STRUCTURE (modeled on top agencies like SellerSlice, Sophie Society, Canopy):
- Three acts: the Challenge (vivid framing of the problem), the Approach (what WE did, written in first person plural — "we", "our team"), the Results (outcome, lead with the numbers).
- In the Approach, tie each action to why it mattered. If there are 2-4 distinct moves, you may return them as "steps".
- Results-forward headline. Punchy, human, professional — never hypey or cringe.
- {subject_mode}
- Write ALL output in professional English (US). If the notes are written in Spanish, translate them into English.

HARD RULES:
- NEVER fabricate metrics, percentages, dollar amounts, dates or facts. Use ONLY figures that appear in the notes. If the notes contain no numbers, return an empty "metrics" array and keep the results section qualitative.
- Keep every section body between 40 and 90 words. Tight and skimmable.
- Output ONLY valid JSON. No markdown, no backticks, no commentary.

NOTES
Marketplace: {market_txt}
Initial scenario (problem): {t1}
The process (what we did): {t2}
The results (outcome): {t3}

Return exactly this JSON shape:
{{
  "headline": "results-forward title, max ~9 words",
  "subhead": "one sentence positioning line",
  "metrics": [{{"value":"2%","label":"short metric label"}}],
  "challenge": "paragraph (40-90 words)",
  "approach": "paragraph (40-90 words)",
  "approach_steps": [{{"title":"3-5 word bold lead","text":"one sentence on the move and its payoff"}}],
  "results": "paragraph (40-90 words)"
}}"""


def _build_translate_es(en_json: dict) -> str:
    """Prompt ES — localiza el JSON EN preservando estructura y métricas intactas."""
    return f"""Localize this Capybaras Agency case study JSON from English into neutral, professional Latin-American Spanish.
Rules:
- Translate all human-readable text: headline, subhead, metric "label" fields, challenge, approach, every approach_steps "title" and "text", and results.
- Keep each metric "value" EXACTLY as-is (numbers, %, $, arrows — never translate or alter them).
- Keep brand and product proper names unchanged.
- Preserve the JSON structure and keys exactly.
- Output ONLY the JSON, same shape. No markdown, no backticks, no commentary.

JSON:
{json.dumps(en_json, ensure_ascii=False)}"""


# ─────────────────────────────────────────────────────────────────────────────
# Generación
# ─────────────────────────────────────────────────────────────────────────────


def _parse_json(raw: str) -> dict:
    """Parser robusto: strip de fences ```json/``` + json.loads con try/except."""
    txt = raw.strip()
    if txt.startswith("```"):
        lines = txt.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        txt = "\n".join(lines).strip()
    try:
        return json.loads(txt)
    except Exception:
        st.error("No se pudo parsear el JSON devuelto por Claude. Respuesta cruda:")
        st.code(raw)
        return {}


def _generate_case_study(brand: str, can_mention: bool, market: str,
                        t1: str, t2: str, t3: str) -> dict | None:
    """Doble llamada Claude: EN (3 actos) → ES (localización). Devuelve dict o None."""
    prompt_en = _build_prompt_en(brand, can_mention, market, t1, t2, t3)
    raw_en = _claude_analyze(prompt_en, max_tokens=1500)
    if raw_en.startswith("⚠️"):
        st.error(raw_en)
        return None
    en = _parse_json(raw_en)
    if not en:
        return None

    prompt_es = _build_translate_es(en)
    raw_es = _claude_analyze(prompt_es, max_tokens=1500)
    es: dict = {}
    if raw_es.startswith("⚠️"):
        st.warning(
            "Se generó el caso en inglés, pero falló la traducción al español: "
            + raw_es
        )
    else:
        es = _parse_json(raw_es)

    return {
        "en": en,
        "es": es,
        "meta": {"brand": brand, "can_mention": can_mention, "market": market},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Form de input (Plan D: buffer mutable en session_state, sin value=+key= juntos)
# ─────────────────────────────────────────────────────────────────────────────


def _init_buf() -> None:
    """Inicializa el buffer del form (idempotente)."""
    if "cs_buf" not in st.session_state:
        st.session_state["cs_buf"] = {
            "can_mention": True,
            "brand": "",
            "market": "—",
            "t1": "",
            "t2": "",
            "t3": "",
        }


def _render_form() -> None:
    """Form de 3 secciones: SETUP + escenario + proceso + resultados."""
    buf = st.session_state["cs_buf"]

    # SETUP — ¿Sobre quién es esto?
    st.markdown("#### ¿Sobre quién es esto?")
    can_mention = st.toggle(
        "¿Podemos mencionar la marca?", value=buf["can_mention"]
    )
    buf["can_mention"] = can_mention

    if can_mention:
        brand_label = "Nombre de la marca"
        brand_ph = "Escribí el nombre — ej. Lenovo"
        brand_cap = "Se usará el nombre real de la marca a lo largo del caso."
    else:
        brand_label = "Categoría de la marca"
        brand_ph = "Categoría — ej. marca de skincare"
        brand_cap = (
            "El caso queda anónimo: se refiere al cliente por su categoría, "
            "nunca por un nombre."
        )
    brand = st.text_input(brand_label, value=buf["brand"], placeholder=brand_ph)
    buf["brand"] = brand
    st.caption(brand_cap)

    market_idx = _MARKETS.index(buf["market"]) if buf["market"] in _MARKETS else 0
    market = st.selectbox("Marketplace (opcional)", _MARKETS, index=market_idx)
    buf["market"] = market

    st.divider()

    # 01 — Escenario inicial
    st.markdown("#### 01 · Escenario inicial")
    t1 = st.text_area(
        "En 1-2 líneas, ¿qué estaba pasando?",
        value=buf["t1"],
        placeholder=(
            "ej. CTR bajo en su producto estrella — alrededor de 1%, "
            "arrastrando las ventas."
        ),
    )
    buf["t1"] = t1

    # 02 — El proceso
    st.markdown("#### 02 · El proceso")
    t2 = st.text_area(
        "En 1-2 líneas, ¿qué hizo el equipo?",
        value=buf["t2"],
        placeholder=(
            "ej. Rediseñamos la imagen principal — referencia de escala, "
            "beneficio clave y hero más limpio."
        ),
    )
    buf["t2"] = t2

    # 03 — Los resultados
    st.markdown("#### 03 · Los resultados")
    t3 = st.text_area(
        "En 1-2 líneas, ¿qué cambió?",
        value=buf["t3"],
        placeholder=(
            "ej. El CTR se duplicó de 1% a 2% en tres semanas, "
            "subiendo sesiones y unidades."
        ),
    )
    buf["t3"] = t3
    st.caption(
        "Incluí los números reales (1% → 2%). El generador solo usa cifras "
        "que vos le das — nunca las inventa."
    )

    st.divider()

    # Botón — deshabilitado hasta tener marca + los 3 textos
    ready = bool(brand.strip()) and bool(t1.strip()) and bool(t2.strip()) and bool(t3.strip())
    if st.button(
        "✨ Generar case study", type="primary",
        disabled=not ready, use_container_width=True,
    ):
        with st.spinner("Generando case study…"):
            result = _generate_case_study(brand, can_mention, market, t1, t2, t3)
        if result:
            st.session_state["cs_result"] = result
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Render del resultado
# ─────────────────────────────────────────────────────────────────────────────


def _render_metric_band(metrics: list) -> None:
    """Band de métricas: cards horizontales con value grande + label. Condicional."""
    if not metrics:
        return
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.markdown(
                f"<div style='border:1px solid #FFD9B3;border-radius:10px;"
                f"padding:1rem;text-align:center;background:#FFF9F4;'>"
                f"<div style='font-size:1.8rem;font-weight:800;color:{_NARANJA};'>"
                f"{m.get('value', '')}</div>"
                f"<div style='font-size:0.8rem;color:{_GRIS_TXT};'>"
                f"{m.get('label', '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _render_section(title: str, body: str) -> None:
    """Sección de texto (Challenge / Approach / Results)."""
    st.markdown(
        f"<div style='font-size:0.78rem;font-weight:700;letter-spacing:0.06em;"
        f"text-transform:uppercase;color:{_NARANJA};margin-top:1rem;'>{title}</div>"
        f"<div style='font-size:0.95rem;color:{_NEGRO};line-height:1.5;'>{body}</div>",
        unsafe_allow_html=True,
    )


def _render_result(result: dict) -> None:
    """Render del case study generado, con toggle EN / ES."""
    # Idiomas disponibles: EN siempre; ES solo si la traducción funcionó.
    has_es = bool(result.get("es"))
    if has_es:
        lang = st.radio("Idioma", ["EN", "ES"], horizontal=True, index=0)
    else:
        lang = "EN"
        st.caption("Solo disponible en inglés (la traducción al español falló).")

    data = result["en"] if lang == "EN" else result["es"]
    if not data:
        data = result["en"]

    # Headline + subhead
    st.markdown(
        f"<div style='font-size:1.9rem;font-weight:800;color:{_NEGRO};"
        f"line-height:1.2;margin-top:0.5rem;'>{data.get('headline', '')}</div>"
        f"<div style='font-size:1.05rem;color:{_GRIS_TXT};margin-bottom:0.5rem;'>"
        f"{data.get('subhead', '')}</div>",
        unsafe_allow_html=True,
    )

    # Band de métricas (condicional — vacía si no hay números)
    _render_metric_band(data.get("metrics", []))

    # Challenge
    st.markdown("---")
    _render_section(
        "The Challenge" if lang == "EN" else "El desafío",
        data.get("challenge", ""),
    )

    # Approach (+ steps si hay)
    _render_section(
        "The Approach" if lang == "EN" else "El proceso",
        data.get("approach", ""),
    )
    for step in data.get("approach_steps", []) or []:
        st.markdown(
            f"<div style='margin:0.4rem 0 0.4rem 0.5rem;'>"
            f"<span style='font-weight:700;color:{_NEGRO};'>"
            f"{step.get('title', '')}</span> — "
            f"<span style='color:{_NEGRO};'>{step.get('text', '')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Results
    _render_section(
        "The Results" if lang == "EN" else "Los resultados",
        data.get("results", ""),
    )

    st.divider()
    if st.button("↻ Generar otro", use_container_width=True):
        st.session_state.pop("cs_result", None)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def render() -> None:
    """Entry point del módulo Case Study Studio (M32)."""
    _render_header()

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    _init_buf()

    if st.session_state.get("cs_result"):
        _render_result(st.session_state["cs_result"])
    else:
        _render_form()
