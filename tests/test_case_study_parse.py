"""Tests del parser de JSON del case study (M32).

`_parse_json` limpia fences ```json/``` y hace json.loads con try/except (devuelve
{} en vez de romper). Importable sin runtime de Streamlit: las llamadas a st.error/
st.code fuera de runtime son no-ops (solo emiten un warning).
"""

from __future__ import annotations

from modules.pages.case_study_studio import _parse_json


def test_parse_valid_json():
    """Un JSON válido → dict con las keys."""
    d = _parse_json('{"en": {"headline": "H"}, "meta": {"brand": "x"}}')
    assert d == {"en": {"headline": "H"}, "meta": {"brand": "x"}}


def test_parse_with_fences():
    """JSON envuelto en fences ```json ... ``` → parsea igual (strip de fences)."""
    raw = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert _parse_json(raw) == {"a": 1, "b": [2, 3]}


def test_parse_malformed():
    """Texto no-JSON → devuelve {} (no excepción)."""
    assert _parse_json("esto no es json") == {}


# test_normalize_canmention: OMITIDO a propósito. La normalización
# canMention→can_mention vive INLINE en _render_paste_mode (no es función aislable).
# Per instrucción: NO reestructurar el módulo solo para testear esto.
