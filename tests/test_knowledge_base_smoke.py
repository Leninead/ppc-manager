"""Smoke test headless del tab Innovation Board (M24) vía Streamlit AppTest.

NO levanta `streamlit run` (evita procesos huérfanos sobre el .venv compartido
entre worktrees). Usa `streamlit.testing.v1.AppTest.from_string` para correr
`render()` en proceso, con backend LOCAL inyectado sobre un tmp_path.

Si AppTest no está disponible, el módulo entero se skipea (importorskip).

Verifica:
    - render() sin excepción
    - 3 tabs
    - publicar una idea → queda visible en el board
    - votar sin razón → NO persiste el voto
"""

from __future__ import annotations

import pytest

# Skipea el módulo completo si AppTest no está en esta versión de Streamlit.
_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = _testing.AppTest

from core import innovation_persistence as ip


# ─────────────────────────────────────────────────────────────────────────────
# Script + helpers
# ─────────────────────────────────────────────────────────────────────────────

# Script como STRING (no from_function): la extracción de fuente de
# `from_function` se rompe bajo el assertion-rewriting de pytest y produce un
# script vacío. `from_string` es robusto.
_SCRIPT = (
    "from modules.pages.knowledge_base import render\n"
    "render(user_name='Test User', user_slug='test')\n"
)


def _by_key_prefix(widgets, prefix):
    return [w for w in widgets if (getattr(w, "key", None) or "").startswith(prefix)]


def _by_key(widgets, key):
    for w in widgets:
        if getattr(w, "key", None) == key:
            return w
    raise KeyError(key)


def _clear_caches():
    for fn in (
        ip._list_ideas,
        ip._get_idea,
        ip._list_votos,
        ip._list_comentarios,
        ip._list_prototipos,
        ip._get_prototipo,
    ):
        if hasattr(fn, "clear"):
            fn.clear()


@pytest.fixture
def local_backend(tmp_path, monkeypatch):
    """Backend LOCAL sobre tmp_path — nada toca `data/` real ni la red."""
    monkeypatch.setattr(ip, "DATA_ROOT", tmp_path)
    ip._set_backend_for_testing(ip._LocalBackend())
    _clear_caches()
    try:
        yield tmp_path
    finally:
        ip._set_backend_for_testing(None)
        _clear_caches()


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_render_ok_and_three_tabs(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 3


def test_publish_idea_shows_in_board(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    assert not at.exception

    _by_key(at.text_input, "ib_new_titulo").set_value("Idea smoke test")
    at.run()
    _by_key(at.button, "ib_publicar").click()
    at.run()
    assert not at.exception

    # La card del board se dibuja con st.markdown (HTML) que embebe el título.
    blob = " ".join(m.value for m in at.markdown)
    assert "Idea smoke test" in blob

    # Y quedó persistida en el backend local.
    _clear_caches()
    ideas = ip._list_ideas()
    assert any(i.get("titulo") == "Idea smoke test" for i in ideas)


def test_vote_without_reason_does_not_persist(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()

    _by_key(at.text_input, "ib_new_titulo").set_value("Idea a votar")
    at.run()
    _by_key(at.button, "ib_publicar").click()
    at.run()
    assert not at.exception

    # Botón de voto dentro del popover de la card (key = ib_vote_btn_<idea_id>).
    vote_btns = _by_key_prefix(at.button, "ib_vote_btn_")
    if not vote_btns:
        pytest.skip("AppTest no expone widgets dentro de st.popover en esta versión.")

    btn = vote_btns[0]
    idea_id = btn.key[len("ib_vote_btn_"):]

    # Click con razón vacía (default "") → debe avisar y NO guardar.
    btn.click()
    at.run()
    assert not at.exception

    _clear_caches()
    assert ip._list_votos(idea_id) == []
