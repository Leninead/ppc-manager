"""The home's Radar Amazon section: hidden without data, rendered from the loader when there is some."""
from __future__ import annotations

import pytest

from core.ui import i18n

TOPICS = [
    {"week_start": "2026-09-21", "rank": 1, "confidence": "official", "title_es": "Amazon cambia los reportes",
     "summary_es": "Resumen oficial.", "implications_es": "Revisar los reportes.", "created_at": "t",
     "sources": [{"person": "Amazon", "published_at": "2026-09-24T00:00:00+00:00",
                  "link": "https://advertising.amazon.com/API/docs/en-us/release-notes/index#x"}]},
    {"week_start": "2026-09-21", "rank": 2, "confidence": "expert", "title_es": "Táctica de bids para Prime",
     "summary_es": "Según Ad Badger...", "implications_es": "Probar en una cuenta.", "created_at": "t",
     "sources": [{"person": "Michael Erickson Facchin", "published_at": "2026-09-25T17:07:32+00:00",
                  "link": "javascript:alert(1)"}]},
]


def _app():
    testing = pytest.importorskip("streamlit.testing.v1")
    return testing.AppTest.from_file("app.py", default_timeout=120)


def _markdown(at) -> str:
    return "\n".join(block.value for block in at.markdown)


@pytest.fixture
def _local_mode(monkeypatch):
    monkeypatch.setenv("AGENCY_OS_LOCAL_MODE", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)


def test_home_without_database_renders_and_hides_the_radar(_local_mode):
    from modules.pages import inicio

    inicio._load_radar.clear()
    at = _app()
    at.run()
    assert not at.exception
    text = _markdown(at)
    assert i18n._ES["home.radar.title"] not in text
    assert i18n._ES["home.radar.disclaimer"] not in text


def test_home_shows_topics_badges_and_only_safe_links(_local_mode, monkeypatch):
    from modules.pages import inicio

    monkeypatch.setattr(inicio, "_load_radar", lambda: TOPICS)
    at = _app()
    at.run()
    assert not at.exception
    text = _markdown(at)
    assert i18n._ES["home.radar.title"] in text
    assert "Semana del 21 de septiembre" in text
    for topic in TOPICS:
        assert topic["title_es"] in text
    assert "Oficial Amazon" in text and "Opinión de experto" in text
    assert "target='_blank'" in text and "release-notes/index#x" in text
    assert "javascript:" not in text


def test_the_loader_returns_nothing_without_credentials(_local_mode):
    from modules.pages import inicio

    inicio._load_radar.clear()
    assert inicio._load_radar() == []


def test_radar_keys_exist_in_both_languages():
    spanish = {key for key in i18n._ES if key.startswith("home.radar.")}
    english = {key for key in i18n._EN if key.startswith("home.radar.")}
    assert spanish and spanish == english
    for confidence in ("official", "confirmed", "expert"):
        assert f"home.radar.confidence.{confidence}" in spanish
