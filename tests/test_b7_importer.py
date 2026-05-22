"""Tests del B7 Importer (extract_blocks + merge_blocks).

Cubre 4 gaps documentados:
  1. contract_version_major_mismatch  (extract)
  2. no_blocks                          (extract — HTML sin bloques)
  3. duplicate_module_id_in_html        (extract — fix del 2026-05-22)
  4. copy_overrides poblado preservado  (merge — edge case Obs #7 audit)
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from modules.sales.b7_importer import (
    extract_blocks,
    merge_blocks,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "data" / "sales" / "_catalog.json"
DEMO_PROPOSAL_PATH = (
    REPO_ROOT / "data" / "sales" / "proposals"
    / "01fbf5c2-1fd9-44dd-9806-742e5deb8f71__v12.json"
)
FIXTURE_V3V4 = REPO_ROOT / "tests" / "fixtures" / "b7_sample_v3v4.html"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalog() -> dict:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def demo_proposal() -> dict:
    with open(DEMO_PROPOSAL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Helpers — HTMLs inline
# ---------------------------------------------------------------------------


def _html_with_version_and_dummy_v3(version_attr: str | None) -> str:
    """HTML mínimo con un V3 válido y la contract-version dada en <html>.

    Si version_attr is None, se omite el atributo (test del default '1.0').
    """
    version = (
        f' data-proposal-contract-version="{version_attr}"'
        if version_attr is not None
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en"{version}>
<body>
<section data-proposal-block="V3_seo_opportunity">
  <div data-proposal-array="missing_keywords">
    <div data-proposal-item>
      <span data-proposal-item-field="keyword">dummy_kw</span>
      <span data-proposal-item-field="sv">100</span>
      <span data-proposal-item-field="current_rank">10</span>
      <span data-proposal-item-field="opportunity_score">5.0</span>
    </div>
  </div>
</section>
</body>
</html>"""


def _v3_section(keyword: str) -> str:
    """Fragment de un V3_seo_opportunity con 1 sola missing_keyword."""
    return f"""<section data-proposal-block="V3_seo_opportunity">
  <div data-proposal-array="missing_keywords">
    <div data-proposal-item>
      <span data-proposal-item-field="keyword">{keyword}</span>
      <span data-proposal-item-field="sv">1</span>
      <span data-proposal-item-field="current_rank">1</span>
      <span data-proposal-item-field="opportunity_score">1.0</span>
    </div>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Gap 1 — contract_version_major_mismatch
# ---------------------------------------------------------------------------


class TestContractVersionMismatch:

    def test_major_version_2_emits_error(self, catalog):
        html = _html_with_version_and_dummy_v3("2.0")
        report = extract_blocks(html, catalog)
        assert not report.ok
        codes = [e.code for e in report.errors]
        assert "contract_version_major_mismatch" in codes
        # El bloque V3 NO debe procesarse cuando hay version mismatch.
        assert not any(
            b.module_id == "V3_seo_opportunity" for b in report.blocks
        )

    def test_major_version_1_minor_5_passes(self, catalog):
        html = _html_with_version_and_dummy_v3("1.5")
        report = extract_blocks(html, catalog)
        assert report.ok
        codes_in_err = [e.code for e in report.errors]
        assert "contract_version_major_mismatch" not in codes_in_err
        assert any(
            b.module_id == "V3_seo_opportunity" for b in report.blocks
        )

    def test_default_version_when_absent(self, catalog):
        html = _html_with_version_and_dummy_v3(None)
        report = extract_blocks(html, catalog)
        assert report.ok
        v3 = next(
            b for b in report.blocks if b.module_id == "V3_seo_opportunity"
        )
        # Fallback default §3 del contrato: "1.0".
        assert v3.contract_version == "1.0"


# ---------------------------------------------------------------------------
# Gap 2 — no_blocks
# ---------------------------------------------------------------------------


class TestNoBlocks:

    def test_empty_html_emits_error(self, catalog):
        html = "<html><body><h1>Sin bloques M29</h1></body></html>"
        report = extract_blocks(html, catalog)
        assert not report.ok
        codes = [e.code for e in report.errors]
        assert "no_blocks" in codes
        assert report.blocks == []

    def test_html_with_only_random_divs(self, catalog):
        html = """<html><body>
            <div class="hero">Hero text</div>
            <div data-some-other-attr="x">Other attr no relacionado</div>
            <p>Texto suelto</p>
        </body></html>"""
        report = extract_blocks(html, catalog)
        assert not report.ok
        codes = [e.code for e in report.errors]
        assert "no_blocks" in codes
        assert report.blocks == []


# ---------------------------------------------------------------------------
# Gap 3 — duplicate_module_id_in_html (fix 2026-05-22)
# ---------------------------------------------------------------------------


class TestDuplicateModuleIdInHtml:

    def test_duplicate_emits_warning_not_error(self, catalog):
        html = f"""<html data-proposal-contract-version="1.0"><body>
            {_v3_section("kw_first")}
            {_v3_section("kw_second")}
        </body></html>"""
        report = extract_blocks(html, catalog)
        assert report.ok  # warning, NO error
        v3_blocks = [
            b for b in report.blocks if b.module_id == "V3_seo_opportunity"
        ]
        assert len(v3_blocks) == 1
        dup_warnings = [
            w for w in report.warnings
            if w.code == "duplicate_module_id_in_html"
        ]
        assert len(dup_warnings) == 1

    def test_first_block_wins(self, catalog):
        html = f"""<html data-proposal-contract-version="1.0"><body>
            {_v3_section("FIRST")}
            {_v3_section("SECOND")}
        </body></html>"""
        report = extract_blocks(html, catalog)
        v3 = next(
            b for b in report.blocks if b.module_id == "V3_seo_opportunity"
        )
        mk = v3.data.get("missing_keywords", [])
        assert len(mk) == 1
        assert mk[0]["keyword"] == "FIRST"

    def test_three_duplicates_emit_two_warnings(self, catalog):
        html = f"""<html data-proposal-contract-version="1.0"><body>
            {_v3_section("first")}
            {_v3_section("second")}
            {_v3_section("third")}
        </body></html>"""
        report = extract_blocks(html, catalog)
        assert report.ok
        v3_blocks = [
            b for b in report.blocks if b.module_id == "V3_seo_opportunity"
        ]
        assert len(v3_blocks) == 1
        dup_warnings = [
            w for w in report.warnings
            if w.code == "duplicate_module_id_in_html"
        ]
        # Uno por cada duplicado después del primero.
        assert len(dup_warnings) == 2


# ---------------------------------------------------------------------------
# Gap 4 — copy_overrides preservado en merge
# ---------------------------------------------------------------------------


class TestCopyOverridesPreserved:

    def test_merge_preserves_existing_copy_overrides(
        self, catalog, demo_proposal
    ):
        with open(FIXTURE_V3V4, "r", encoding="utf-8") as f:
            html = f.read()

        # Popular copy_overrides del V3 del target con un sentinel.
        target = copy.deepcopy(demo_proposal)
        v3_target = next(
            b for b in target["blocks"]
            if b.get("module_id") == "V3_seo_opportunity"
        )
        v3_target["copy_overrides"] = {
            "en": {"section_title": "TEST_OVERRIDE_EN"},
        }
        v3_data_before = copy.deepcopy(v3_target.get("data", {}))

        # Pipeline completo: extract + merge.
        report = extract_blocks(html, catalog)
        assert report.ok
        result = merge_blocks(report, target, catalog)
        assert result.ok
        assert "V3_seo_opportunity" in result.applied_blocks

        v3_after = next(
            b for b in result.proposal_updated["blocks"]
            if b.get("module_id") == "V3_seo_opportunity"
        )
        # copy_overrides intacto.
        assert v3_after["copy_overrides"] == {
            "en": {"section_title": "TEST_OVERRIDE_EN"},
        }
        # data sí cambió (overwrite con el del HTML).
        assert v3_after["data"] != v3_data_before
        # Sanity: primer kw del nuevo data viene del fixture v3v4.
        mk = v3_after["data"].get("missing_keywords", [])
        assert len(mk) >= 1
        assert mk[0]["keyword"] == "moringa powder organic"

    def test_merge_preserves_identity_fields(self, catalog, demo_proposal):
        with open(FIXTURE_V3V4, "r", encoding="utf-8") as f:
            html = f.read()

        target = copy.deepcopy(demo_proposal)
        v3_target = next(
            b for b in target["blocks"]
            if b.get("module_id") == "V3_seo_opportunity"
        )
        v3_id_before = v3_target["id"]
        v3_proposal_id_before = v3_target["proposal_id"]
        v3_is_fixed_before = v3_target["is_fixed"]
        v3_module_id_before = v3_target["module_id"]

        report = extract_blocks(html, catalog)
        result = merge_blocks(report, target, catalog)
        assert result.ok

        v3_after = next(
            b for b in result.proposal_updated["blocks"]
            if b.get("module_id") == "V3_seo_opportunity"
        )
        assert v3_after["id"] == v3_id_before
        assert v3_after["proposal_id"] == v3_proposal_id_before
        assert v3_after["is_fixed"] == v3_is_fixed_before
        assert v3_after["module_id"] == v3_module_id_before
