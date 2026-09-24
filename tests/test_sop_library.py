"""The AM and PPC SOP library: doc-type detection, badges, search, catalog validation and its place in the rail."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from core import navigation
from core.sop_library import (
    ALL_CATEGORIES,
    NEW_DAYS,
    REVIEW_DAYS,
    SOPS,
    badges,
    detect_doc_type,
    filter_sops,
    sops_for_area,
    validate_catalog,
)
from core.ui import i18n

ROUTING_KEY = "📂 SOPs / Drive AM"
PPC_ROUTING_KEY = "📂 SOPs / Drive PPC"
_PPC_SOP_IDS = ["ppc-launch-sop", "ppc-prompt-wow", "ppc-skills-sophie-hub", "ppc-prompts-sophie-hub"]
_PPC_DOC_TYPES = {
    "ppc-launch-sop": "doc",
    "ppc-prompt-wow": "doc",
    "ppc-skills-sophie-hub": "folder",
    "ppc-prompts-sophie-hub": "doc",
}
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TODAY = date(2026, 9, 23)


def _sop(**overrides) -> dict:
    sop = {
        "id": "sop-test",
        "area": "AM",
        "title": "SOP de Prueba",
        "description": "Descripción de prueba.",
        "category": "Listings",
        "url": "https://docs.google.com/document/d/abc/edit",
        "owner": "Owner Test",
        "added": _TODAY,
        "last_reviewed": _TODAY,
    }
    sop.update(overrides)
    return sop


@pytest.mark.parametrize("url, key", [
    ("https://docs.google.com/document/d/1opEPYOObU4ArV_g9M31M87cZOqmJIAtL/edit", "doc"),
    ("https://docs.google.com/spreadsheets/d/abc/edit", "sheet"),
    ("https://docs.google.com/presentation/d/abc/edit", "slides"),
    ("https://drive.google.com/drive/folders/abc", "folder"),
    ("https://www.loom.com/share/abc", "video"),
    ("https://drive.google.com/file/d/abc/view", "pdf"),
    ("https://example.com/manual.pdf", "pdf"),
    ("https://example.com/wiki", "link"),
])
def test_detect_doc_type_by_url(url, key):
    assert detect_doc_type(url)["key"] == key


def test_launch_sop_is_a_doc():
    launch = next(sop for sop in SOPS if sop["id"] == "sop-lanzamiento")
    assert detect_doc_type(launch["url"]) == {
        "key": "doc", "label": "Doc", "icon": ":material/description:",
    }


def test_new_badge_holds_up_to_new_days_inclusive():
    assert "new" in badges(_sop(added=_TODAY - timedelta(days=NEW_DAYS)), _TODAY)
    assert "new" not in badges(_sop(added=_TODAY - timedelta(days=NEW_DAYS + 1)), _TODAY)


def test_review_badge_starts_after_review_days():
    assert "review" not in badges(_sop(last_reviewed=_TODAY - timedelta(days=REVIEW_DAYS)), _TODAY)
    assert "review" in badges(_sop(last_reviewed=_TODAY - timedelta(days=REVIEW_DAYS + 1)), _TODAY)


def test_search_ignores_accents_and_case():
    sops = [_sop(id="a", title="SOP de Lanzamiento", category="Lanzamiento"),
            _sop(id="b", title="Reporte semanal", description="Métricas", category="Reporting")]
    assert [sop["id"] for sop in filter_sops(sops, "LANZAMIENTO", None)] == ["a"]
    assert [sop["id"] for sop in filter_sops(sops, "metricas", None)] == ["b"]


def test_category_filter_and_all():
    sops = [_sop(id="a", category="PPC"), _sop(id="b", category="Listings")]
    assert [sop["id"] for sop in filter_sops(sops, "", "Listings")] == ["b"]
    assert len(filter_sops(sops, "", ALL_CATEGORIES)) == 2
    assert len(filter_sops(sops, "", None)) == 2


def test_real_catalog_is_valid():
    assert validate_catalog(SOPS) == []


def test_duplicate_id_is_reported():
    errors = validate_catalog([_sop(id="dup"), _sop(id="dup")])
    assert any("duplicado" in error for error in errors)


def test_bad_category_url_and_missing_field_are_reported():
    errors = validate_catalog([_sop(category="Otra", url="http://x.com", owner="")])
    assert len(errors) == 3


def test_sops_for_area_splits_the_catalog():
    assert [sop["id"] for sop in sops_for_area(SOPS, "AM")] == ["sop-lanzamiento"]
    assert [sop["id"] for sop in sops_for_area(SOPS, "PPC")] == _PPC_SOP_IDS


def test_invalid_area_is_reported():
    errors = validate_catalog([_sop(area="Ventas")])
    assert errors == ["sop-test: área 'Ventas' no está en AREAS"]


def test_missing_area_is_reported():
    errors = validate_catalog([_sop(area="")])
    assert errors == ["sop-test: faltan campos area"]


def test_category_from_another_area_is_reported():
    errors = validate_catalog([_sop(area="PPC", category="Onboarding")])
    assert errors == ["sop-test: categoría 'Onboarding' no está en CATEGORIES_BY_AREA['PPC']"]


@pytest.mark.parametrize("sop_id, doc_type", _PPC_DOC_TYPES.items())
def test_ppc_sops_have_their_doc_type(sop_id, doc_type):
    sop = next(sop for sop in SOPS if sop["id"] == sop_id)
    assert detect_doc_type(sop["url"])["key"] == doc_type


def test_page_is_the_last_account_destination():
    account = next(section for section in navigation.SECTIONS if section.title == "Account")
    assert account.pages[-1] == ROUTING_KEY
    assert navigation.all_pages().count(ROUTING_KEY) == 1


def test_page_has_its_own_icon():
    assert navigation.icon_for(ROUTING_KEY) == ":material/folder_shared:"


@pytest.mark.parametrize("lang, expected", [("es", "SOPs / Drive AM"), ("en", "SOPs / AM Drive")])
def test_page_label_follows_the_language(monkeypatch, lang, expected):
    assert i18n._PAGE_KEYS[ROUTING_KEY] == "nav.page.sop_library"
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    assert navigation.visible_label(ROUTING_KEY) == expected


def test_every_page_text_exists_in_both_languages():
    source = (_REPO_ROOT / "modules" / "pages" / "sop_library.py").read_text(encoding="utf-8")
    # Complete keys only: the doc-type key is built at runtime and listed by hand below.
    used = set(re.findall(r"""i18n\.t\(\s*["'](sop_library\.[\w.]*\w)["']""", source))
    used |= {f"sop_library.doc_type.{key}"
             for key in ("doc", "sheet", "slides", "folder", "video", "pdf", "link")}
    spanish = {key for key in i18n._ES if key.startswith("sop_library.")}
    english = {key for key in i18n._EN if key.startswith("sop_library.")}
    assert used <= spanish
    assert spanish == english


def test_router_dispatches_the_page():
    source = (_REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert f'if selected == "{ROUTING_KEY}":\n    render_sop_library()' in source


def test_ppc_page_is_the_last_ppc_destination():
    ppc = next(section for section in navigation.SECTIONS if section.title == "PPC")
    account = next(section for section in navigation.SECTIONS if section.title == "Account")
    assert ppc.pages[-1] == PPC_ROUTING_KEY
    assert PPC_ROUTING_KEY not in account.pages
    assert ROUTING_KEY not in ppc.pages
    assert navigation.all_pages().count(PPC_ROUTING_KEY) == 1


def test_ppc_page_has_its_own_icon():
    assert navigation.icon_for(PPC_ROUTING_KEY) == ":material/folder_special:"


@pytest.mark.parametrize("lang, expected", [("es", "SOPs / Drive PPC"), ("en", "SOPs / PPC Drive")])
def test_ppc_page_label_follows_the_language(monkeypatch, lang, expected):
    assert i18n._PAGE_KEYS[PPC_ROUTING_KEY] == "nav.page.sop_library_ppc"
    monkeypatch.setattr(i18n, "current_lang", lambda: lang)
    assert navigation.visible_label(PPC_ROUTING_KEY) == expected


def test_ppc_header_texts_exist_in_both_languages():
    for key in ("sop_library.header_title_ppc", "sop_library.header_caption_ppc"):
        assert key in i18n._ES
        assert key in i18n._EN


def test_router_dispatches_the_ppc_page():
    source = (_REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert f'if selected == "{PPC_ROUTING_KEY}":\n    render_sop_library(area="PPC")' in source
