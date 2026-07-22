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
from modules.pages import knowledge_base as kb


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


# ─────────────────────────────────────────────────────────────────────────────
# F2 — comentarios, pipeline de estado, render de prototipo
# ─────────────────────────────────────────────────────────────────────────────

def _publish_idea(at, titulo):
    """Publica una idea vía UI y devuelve su idea_id."""
    _by_key(at.text_input, "ib_new_titulo").set_value(titulo)
    at.run()
    _by_key(at.button, "ib_publicar").click()
    at.run()
    _clear_caches()
    ideas = [i for i in ip._list_ideas() if i.get("titulo") == titulo]
    assert ideas, f"no se publicó la idea {titulo}"
    return ideas[0]["id"]


def test_comentario_vacio_no_persiste(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    idea_id = _publish_idea(at, "Idea comentable")

    # Botón "Comentar" dentro del popover, con text_area vacío.
    _by_key(at.button, f"ib_com_btn_{idea_id}").click()
    at.run()
    assert not at.exception

    _clear_caches()
    assert ip._list_comentarios(idea_id) == []


def test_comentario_valido_persiste_y_aparece(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    idea_id = _publish_idea(at, "Idea comentable 2")

    _by_key(at.text_area, f"ib_com_txt_{idea_id}").set_value("gran aporte del equipo")
    at.run()
    _by_key(at.button, f"ib_com_btn_{idea_id}").click()
    at.run()
    assert not at.exception

    _clear_caches()
    coms = ip._list_comentarios(idea_id)
    assert len(coms) == 1
    assert coms[0]["cuerpo"] == "gran aporte del equipo"
    blob = " ".join(m.value for m in at.markdown)
    assert "gran aporte del equipo" in blob


def test_cambio_de_estado_persiste(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    idea_id = _publish_idea(at, "Idea con pipeline")

    # on_change del selectbox → _update_idea.
    _by_key(at.selectbox, f"ib_estado_{idea_id}").set_value("aprobada")
    at.run()
    assert not at.exception

    _clear_caches()
    assert ip._get_idea(idea_id)["estado"] == "aprobada"


def test_prototipo_render_en_flujo_principal(local_backend):
    """El render del prototipo va FUERA del popover (flujo principal).

    No se usa file_uploader (AppTest no lo maneja bien); el prototipo se crea por
    la capa de persistencia y el render se activa vía session_state. Verifica que
    `st.components.v1.html` en el flujo principal NO rompe headless — CAMINO
    ELEGIDO: render fuera del popover.
    """
    at = AppTest.from_string(_SCRIPT)
    at.run()
    idea_id = _publish_idea(at, "Idea con proto")

    ip._add_prototipo(idea_id, "mockup.html", "<h1>Prototipo</h1>", "Test User")
    _clear_caches()
    protos = ip._list_prototipos(idea_id)
    assert len(protos) == 1
    proto_id = protos[0]["id"]

    at.session_state["ib_active_proto"] = proto_id
    at.run()
    # Sin excepción = st.components.v1.html en el flujo principal NO rompió.
    assert not at.exception
    # El bloque de render se ejecutó completo: título + botón cerrar. Si st_html
    # (que va justo después) hubiera roto, at.exception no estaría vacío.
    blob = " ".join(m.value for m in at.markdown)
    assert "Prototipo:" in blob
    assert any(getattr(b, "key", None) == "ib_proto_close" for b in at.button)


# ─────────────────────────────────────────────────────────────────────────────
# F3 — prioridad, migración de estados, descarte, asignación, 3 vistas
# ─────────────────────────────────────────────────────────────────────────────

def test_prioridad_max_score_zero_no_explota():
    idea = {"impacto": "medio", "esfuerzo": "medio"}
    score = kb._ib_prioridad(idea, [], 0)  # max_score=0 → sin división por cero
    assert isinstance(score, int)
    assert score == 36  # 35*0.6 + 25*0.6 = 36


def test_prioridad_quick_win_votos_maximos_es_100():
    idea = {"impacto": "alto", "esfuerzo": "bajo"}
    votos = [{"valor": 1}, {"valor": 1}]  # score 2
    assert kb._ib_prioridad(idea, votos, max_score=2) == 100  # 40+35+25


def test_migracion_en_revision_a_en_debate(local_backend):
    idea_id = ip._create_idea({"titulo": "legacy", "area": "ppc"})
    ip._update_idea(idea_id, {"estado": "en revisión"})  # estado legacy en storage

    assert ip._get_idea(idea_id)["estado"] == "en debate"
    # _list_ideas también migra + filtra por el estado NUEVO.
    listed = ip._list_ideas(estado="en debate")
    assert any(i["id"] == idea_id for i in listed)


def test_update_idea_estado_sella_timestamp(local_backend):
    idea_id = ip._create_idea({"titulo": "x", "area": "ops"})
    ts0 = ip._get_idea(idea_id).get("estado_updated_at")

    # Update SIN estado → no toca estado_updated_at.
    ip._update_idea(idea_id, {"asignado_a": "Alguien"})
    ts1 = ip._get_idea(idea_id).get("estado_updated_at")
    assert ts1 == ts0

    # Update CON estado → sella un timestamp nuevo.
    ip._update_idea(idea_id, {"estado": "aprobada"})
    ts2 = ip._get_idea(idea_id).get("estado_updated_at")
    assert ts2 and ts2 != ts1


def test_descartar_sin_razon_no_persiste(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    idea_id = _publish_idea(at, "Idea a descartar")

    _by_key(at.selectbox, f"ib_estado_{idea_id}").set_value("descartada")
    at.run()
    # Confirmar sin razón → warning, no persiste.
    _by_key(at.button, f"ib_descarte_btn_{idea_id}").click()
    at.run()
    assert not at.exception

    _clear_caches()
    assert ip._get_idea(idea_id)["estado"] != "descartada"


def test_descartar_con_razon_persiste_y_guarda(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    idea_id = _publish_idea(at, "Idea a descartar 2")

    _by_key(at.selectbox, f"ib_estado_{idea_id}").set_value("descartada")
    at.run()
    _by_key(at.text_area, f"ib_descarte_razon_{idea_id}").set_value("duplicada de otra")
    at.run()
    _by_key(at.button, f"ib_descarte_btn_{idea_id}").click()
    at.run()
    assert not at.exception

    _clear_caches()
    idea = ip._get_idea(idea_id)
    assert idea["estado"] == "descartada"
    assert idea["razon_descarte"] == "duplicada de otra"


def test_asignar_usuario_persiste(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    idea_id = _publish_idea(at, "Idea a asignar")

    # Sin secrets, _ib_usuarios() → ["Usuario local"].
    _by_key(at.selectbox, f"ib_asignado_{idea_id}").set_value("Usuario local")
    at.run()
    assert not at.exception

    _clear_caches()
    assert ip._get_idea(idea_id)["asignado_a"] == "Usuario local"


def test_tres_vistas_renderizan_sin_excepcion(local_backend):
    at = AppTest.from_string(_SCRIPT)
    at.run()
    _publish_idea(at, "Idea multi-vista")

    for vista in ["📋 Lista", "🗂️ Kanban", "📊 Matriz"]:
        _by_key(at.radio, "ib_vista").set_value(vista)
        at.run()
        assert not at.exception, f"la vista {vista} rompió el render"
