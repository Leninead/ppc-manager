"""The home's areas mirror the side rail, and every menu section has an owner."""
from __future__ import annotations

import pytest

from core import navigation
from core.home_areas import AREA_OWNERS, SYSTEM_SECTION, home_counts, visible_sections
from core.ui import i18n

def _app():
    testing = pytest.importorskip("streamlit.testing.v1")
    return testing.AppTest.from_file("app.py", default_timeout=120)


def test_every_menu_section_has_an_owner():
    for section in navigation.SECTIONS:
        assert AREA_OWNERS.get(section.title), f"la sección {section.title!r} no tiene owner en AREA_OWNERS"


def test_system_section_title_matches_the_menu():
    assert SYSTEM_SECTION in {section.title for section in navigation.SECTIONS}


def test_non_admin_sees_no_direccion_and_only_connected_accounts_in_sistema():
    sections = dict((section.title, pages) for section, pages in visible_sections(is_admin=False))
    assert "Dirección" not in sections
    assert sections[SYSTEM_SECTION] == ("🔑 Cuentas conectadas",)


def test_visible_sections_keep_menu_order():
    titles = [section.title for section, _ in visible_sections(is_admin=True)]
    assert titles == [section.title for section in navigation.SECTIONS]


def test_home_counts():
    assert home_counts(is_admin=True) == (41, 10)
    assert home_counts(is_admin=False) == (37, 9)


def test_home_keys_exist_in_both_languages():
    spanish = {key for key in i18n._ES if key.startswith("home.")}
    english = {key for key in i18n._EN if key.startswith("home.")}
    assert spanish and spanish == english


def test_home_lists_have_the_right_length_in_both_languages():
    for catalog in (i18n._ES, i18n._EN):
        assert len(catalog["home.weekdays"].split(",")) == 7
        assert len(catalog["home.months"].split(",")) == 12


@pytest.fixture
def _local_mode(monkeypatch):
    monkeypatch.setenv("AGENCY_OS_LOCAL_MODE", "1")


@pytest.mark.parametrize("language", ["Español", "English"])
def test_home_renders_without_exception(_local_mode, language):
    at = _app()
    at.session_state["app_lang"] = language
    at.run()
    assert not at.exception
    labels = {button.label for button in at.button}
    assert navigation.visible_label("📚 Knowledge Base") in labels
    assert not {"Inicio", "Home"} & {button.label for button in at.main.button}


def test_admin_home_shows_admin_only_chips(_local_mode, monkeypatch):
    monkeypatch.setenv("AGENCY_OS_LOCAL_ADMIN", "1")
    at = _app()
    at.run()
    assert not at.exception
    for page in ("🌐 Dashboard Global", "🔌 Integraciones"):
        assert at.button(key=f"home_chip_{navigation.all_pages().index(page)}").label == navigation.visible_label(page)


def test_non_admin_home_hides_admin_only_chips(_local_mode, monkeypatch):
    monkeypatch.delenv("AGENCY_OS_LOCAL_ADMIN", raising=False)
    at = _app()
    at.run()
    chip_keys = {button.key for button in at.main.button}
    for page in navigation.ADMIN_ONLY:
        assert f"home_chip_{navigation.all_pages().index(page)}" not in chip_keys


def test_a_home_chip_navigates(_local_mode):
    at = _app()
    at.run()
    chip_key = f"home_chip_{navigation.all_pages().index('📂 SOPs / Drive PPC')}"
    at.button(key=chip_key).click().run()
    assert not at.exception
    assert at.session_state["selected_page"] == "📂 SOPs / Drive PPC"
