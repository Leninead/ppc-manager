"""
🏆 Case Study Studio — M32 (Sales Director)

Generador de casos de éxito: el AM responde preguntas (situación inicial →
qué hicimos → resultado) y Claude redacta el caso en 3 actos (EN → ES),
sin inventar métricas. Hermano de Proposal Studio (M29). Persistencia
prevista vía core/persistence.py (capa client-config).

Fase 0 — andamiaje mínimo navegable: sin lógica, sin Claude, sin persistencia.
"""

import streamlit as st

# Paleta Capybaras (unificada con M29 Proposal Studio).
_NARANJA = "#E84000"
_NEGRO = "#1F1F1F"
_GRIS_TXT = "#888888"

# SOP in-app: guía de uso embebida (expander al tope de render()).
# Stub Fase 0 — se completa en Fase 5.
_SOP_MD = """
### Case Study Studio — cómo usarlo

> 🚧 **Fase 0 — andamiaje.** La guía completa se documenta cuando el módulo esté funcional.

Genera casos de éxito a partir de tus notas: respondés tres preguntas
(situación inicial → qué hicimos → resultado) y el módulo redacta el caso
en tres actos, primero en inglés y después localizado a español. Regla dura:
**nunca inventa métricas** — si tus notas no traen números, el caso queda cualitativo.
"""


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
        f"M32 · Fase 0</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.divider()


def _render_empty_state() -> None:
    """Empty-state placeholder Fase 0 — módulo en construcción."""
    st.markdown(
        f"<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2.5rem 1.5rem;"
        f"text-align:center;background:#FFF9F4;'>"
        f"<div style='font-size:3rem;margin-bottom:0.5rem;'>🚧</div>"
        f"<div style='font-size:1.1rem;font-weight:700;color:{_NEGRO};margin-bottom:0.4rem;'>"
        f"Fase 0 — en construcción</div>"
        f"<div style='font-size:0.85rem;color:{_GRIS_TXT};'>"
        f"El andamiaje está listo y navegable. El generador (form + Claude), "
        f"la biblioteca de casos y los exports llegan en las próximas fases.</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render() -> None:
    """Entry point del módulo Case Study Studio (M32)."""
    _render_header()

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    _render_empty_state()
