"""The request log in the rail: last of Sistema, admin-only, with its own icon and a label in both languages."""
from __future__ import annotations

import re

import pytest

from core import navigation
from core.ui import i18n

REQUEST_LOG = "🧾 Registro de solicitudes"
_SLOT = re.compile(r"\{(\w+)\}")


def _sistema() -> navigation.Section:
    return next(section for section in navigation.SECTIONS if section.title == "Sistema")


def _request_log_keys(catalog: dict[str, str]) -> set[str]:
    return {key for key in catalog
            if key.startswith("request_log.") or key == "nav.page.registro_solicitudes"}


def test_request_log_is_the_last_sistema_destination():
    assert navigation.REQUEST_LOG == REQUEST_LOG
    assert _sistema().pages[-1] == REQUEST_LOG


def test_request_log_is_in_the_page_catalog_exactly_once():
    from core.constants import _PAGES

    assert navigation.all_pages().count(REQUEST_LOG) == 1
    assert REQUEST_LOG in _PAGES


def test_request_log_is_hidden_from_a_plain_user_rail():
    assert REQUEST_LOG in navigation.ADMIN_ONLY
    assert REQUEST_LOG not in navigation.visible_pages(_sistema(), is_admin=False)
    assert REQUEST_LOG in navigation.visible_pages(_sistema(), is_admin=True)


def test_rail_without_a_role_fails_closed_on_the_request_log():
    assert REQUEST_LOG not in navigation.visible_pages(_sistema())


def test_search_does_not_reveal_the_request_log_to_a_plain_user():
    assert navigation.filter_pages("registro", is_admin=False) == []
    assert navigation.filter_pages("registro de solicitudes", is_admin=True) == [REQUEST_LOG]


def test_request_log_has_the_history_icon():
    assert navigation.icon_for(REQUEST_LOG) == ":material/history:"


@pytest.mark.parametrize("lang, expected", [("es", "Registro de solicitudes"), ("en", "Request log")])
def test_request_log_label_follows_the_language(monkeypatch, lang, expected):
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    assert navigation.visible_label(REQUEST_LOG) == expected


def test_every_request_log_key_exists_in_both_languages():
    spanish = _request_log_keys(i18n._ES)
    assert "nav.page.registro_solicitudes" in spanish
    assert "request_log.admin_only" in spanish
    assert spanish == _request_log_keys(i18n._EN)


def test_request_log_translations_are_not_empty():
    for catalog in (i18n._ES, i18n._EN):
        for key in _request_log_keys(catalog):
            assert catalog[key].strip(), key


def test_request_log_keys_share_interpolation_slots_across_languages():
    for key in _request_log_keys(i18n._ES):
        assert set(_SLOT.findall(i18n._ES[key])) == set(_SLOT.findall(i18n._EN[key])), key


def test_every_snapshot_listing_has_its_title_and_count_in_both_languages():
    from modules.pages import request_log

    assert {"sp_ad_groups", "sp_negatives"} <= request_log._SNAPSHOT_COUNT_KEYS.keys()
    for job_kind, count_key in request_log._SNAPSHOT_COUNT_KEYS.items():
        for catalog in (i18n._ES, i18n._EN):
            assert f"request_log.kind.{job_kind}" in catalog, job_kind
            assert {f"{count_key}_one", f"{count_key}_other"} <= catalog.keys(), count_key


def test_request_log_plural_keys_come_in_pairs():
    keys = _request_log_keys(i18n._ES)
    for key in keys:
        if key.endswith("_one"):
            assert f"{key[:-len('_one')]}_other" in keys, key
        if key.endswith("_other"):
            assert f"{key[:-len('_other')]}_one" in keys, key


def _boot_app(monkeypatch, *, admin: bool, alert_counts: tuple[int, int], selected_page: str | None = None):
    testing = pytest.importorskip("streamlit.testing.v1")
    from core.integrations import notice

    calls: list[int] = []

    def fake_counts() -> tuple[int, int]:
        calls.append(1)
        return alert_counts

    monkeypatch.setenv("AGENCY_OS_LOCAL_MODE", "1")
    if admin:
        monkeypatch.setenv("AGENCY_OS_LOCAL_ADMIN", "1")
    else:
        monkeypatch.delenv("AGENCY_OS_LOCAL_ADMIN", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setattr(notice, "sync_alert_counts", fake_counts)
    app = testing.AppTest.from_file("app.py", default_timeout=120)
    if selected_page:
        app.session_state["selected_page"] = selected_page
    app.run()
    assert not app.exception
    return app, calls


@pytest.mark.parametrize("alert_counts, expected_label", [
    ((2, 1), "Registro de solicitudes :red[●]"),
    ((0, 3), "Registro de solicitudes :orange[●]"),
    ((0, 0), "Registro de solicitudes"),
])
def test_sidebar_dot_on_the_request_log_follows_the_alert_severity(monkeypatch, alert_counts, expected_label):
    app, _ = _boot_app(monkeypatch, admin=True, alert_counts=alert_counts)
    assert app.button(key=f"nav_{REQUEST_LOG}").label == expected_label


def test_plain_user_sidebar_has_no_request_log_and_never_counts_alerts(monkeypatch):
    app, calls = _boot_app(monkeypatch, admin=False, alert_counts=(5, 0))
    assert f"nav_{REQUEST_LOG}" not in {button.key for button in app.button}
    assert calls == []


def test_app_dispatches_the_request_log_page(monkeypatch):
    app, _ = _boot_app(monkeypatch, admin=True, alert_counts=(0, 0), selected_page=REQUEST_LOG)
    assert any(str(block.value) == f"## {i18n.t('request_log.header_title')}" for block in app.markdown)
    assert i18n.t("request_log.error_db_unavailable") in [block.value for block in app.warning]
