"""The sidebar language toggle must survive the rerun that follows the click.

It did not, and the failure was invisible to every check we had: the catalog was
complete, both languages rendered correctly when session state was set by hand,
and no exception was raised. What broke was the widget's IDENTITY.

Streamlit derives a widget's element id from its own arguments — for a radio,
`streamlit/elements/widgets/radio.py` feeds `label`, the format_func'd `options`
and `help` into `compute_and_register_element_id`. The toggle translated all
three. So on the run right after the click, the sidebar above it had already
switched to English, the radio was then registered under a DIFFERENT id, its
stored value was orphaned, and it fell back to its default — writing "Español"
back over the user's choice. The interface was English and the check said
Spanish, and the next interaction flipped everything back.

These tests pin both halves: the behaviour a user sees, and the invariant that
causes it.
"""
from __future__ import annotations

import pytest

_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = _testing.AppTest

LANG_KEY = "app_lang"
SPANISH = "Español"
ENGLISH = "English"


@pytest.fixture(autouse=True)
def _skip_login(monkeypatch):
    """app.py gates on a login form unless local mode is on."""
    monkeypatch.setenv("AGENCY_OS_LOCAL_MODE", "1")


def _boot() -> AppTest:
    at = AppTest.from_file("app.py", default_timeout=120)
    at.run()
    return at


def test_choosing_english_survives_the_next_reruns():
    """Click English, then let the app rerun. The choice has to hold."""
    at = _boot()
    assert at.radio(key=LANG_KEY).value == SPANISH

    at.radio(key=LANG_KEY).set_value(ENGLISH).run()
    assert at.radio(key=LANG_KEY).value == ENGLISH

    # The regression lived here: the run after the click is the one that used to
    # reset the widget, because that is the first run whose sidebar is English.
    for _ in range(3):
        at.run()
        assert at.radio(key=LANG_KEY).value == ENGLISH, (
            "the language radio reset itself on a rerun — something it renders "
            "now varies with the language, so its element id is no longer stable"
        )


def test_interface_follows_the_toggle():
    """The point of the toggle: the screens actually change language."""
    at = _boot()
    at.radio(key=LANG_KEY).set_value(ENGLISH).run()
    labels = {b.label for b in at.button}
    assert "Home" in labels and "Inicio" not in labels

    at.radio(key=LANG_KEY).set_value(SPANISH).run()
    labels = {b.label for b in at.button}
    assert "Inicio" in labels and "Home" not in labels


def test_the_toggles_element_id_does_not_depend_on_the_language():
    """The invariant behind both tests above.

    A translated `label`, `help` or `format_func` output on this widget changes
    its element id, which silently orphans the stored choice. Keep the widget's
    own arguments constant and render the translated label beside it.
    """
    ids = {}
    for choice in (SPANISH, ENGLISH):
        at = AppTest.from_file("app.py", default_timeout=120)
        at.session_state[LANG_KEY] = choice
        at.run()
        ids[choice] = at.radio(key=LANG_KEY)._widget_state.id

    assert ids[SPANISH] == ids[ENGLISH], (
        "the language radio's element id changes with the language "
        f"({ids[SPANISH]} vs {ids[ENGLISH]}). Streamlit hashes `label`, the "
        "format_func'd `options` and `help` into the id — none of them may be "
        "translated on this widget."
    )
