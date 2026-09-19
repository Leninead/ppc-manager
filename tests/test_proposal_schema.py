"""Tests del schema y catálogo Sales Proposals.

Cubre:
- Catálogo es schema-valid (estructura mínima, tiers, frequency, status, etc.).
- 4 templates son schema-valid.
- Cada template referencia solo module_ids existentes en el catálogo (FK).
- Cada template incluye los 8 FIXED.
- Catálogo no tiene module_ids duplicados.
- Why Capybaras v3 está presente y bien armado (4 pilares con slug y body bilingüe).
"""

from __future__ import annotations

import json

import pytest

from core.proposals.paths import (
    CATALOG_FILE,
    PROPOSAL_SCHEMA_FILE,
    TEMPLATES_DIR,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog_index(catalog: dict) -> dict[str, dict]:
    return {m["module_id"]: m for m in catalog["modules"]}


@pytest.fixture(scope="module")
def templates() -> list[dict]:
    files = sorted(TEMPLATES_DIR.glob("*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


@pytest.fixture(scope="module")
def schema_proposal() -> dict:
    return json.loads(PROPOSAL_SCHEMA_FILE.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo
# ─────────────────────────────────────────────────────────────────────────────


def test_catalog_loads_and_has_modules(catalog: dict):
    assert "modules" in catalog
    assert isinstance(catalog["modules"], list)
    assert len(catalog["modules"]) >= 37, "Esperaba al menos 37 módulos (8 FIXED + 29 VARIABLES)"


def test_catalog_no_duplicate_module_ids(catalog: dict):
    ids = [m["module_id"] for m in catalog["modules"]]
    assert len(ids) == len(set(ids)), "Hay module_ids duplicados en el catálogo"


def test_catalog_all_modules_have_required_fields(catalog: dict):
    required = {
        "module_id",
        "tier",
        "frequency",
        "title",
        "description",
        "schema",
        "applicable_archetypes",
        "status",
        "interested_votes",
    }
    for m in catalog["modules"]:
        missing = required - m.keys()
        assert not missing, f"Módulo {m.get('module_id', '?')} sin campos: {missing}"


def test_catalog_tiers_valid(catalog: dict):
    valid = {"fixed", "core_variable", "common_variable", "specialized_variable"}
    for m in catalog["modules"]:
        assert m["tier"] in valid, f"Tier inválido en {m['module_id']}: {m['tier']}"


def test_catalog_frequency_range(catalog: dict):
    for m in catalog["modules"]:
        assert 1 <= m["frequency"] <= 5, f"frequency fuera de [1,5] en {m['module_id']}"


def test_catalog_status_valid(catalog: dict):
    valid = {"active", "placeholder_coming_soon", "deprecated"}
    for m in catalog["modules"]:
        assert m["status"] in valid, f"Status inválido en {m['module_id']}: {m['status']}"


def test_catalog_titles_and_descriptions_bilingual(catalog: dict):
    for m in catalog["modules"]:
        assert "en" in m["title"] and "es" in m["title"], (
            f"{m['module_id']}: title sin en/es"
        )
        assert "en" in m["description"] and "es" in m["description"], (
            f"{m['module_id']}: description sin en/es"
        )


def test_catalog_applicable_archetypes_valid(catalog: dict):
    valid = {"launch", "scale_seo", "defense", "cvr", "custom"}
    for m in catalog["modules"]:
        bad = set(m["applicable_archetypes"]) - valid
        assert not bad, f"{m['module_id']}: archetypes inválidos: {bad}"


def test_catalog_has_exactly_8_fixed(catalog: dict):
    fixed = [m for m in catalog["modules"] if m["tier"] == "fixed"]
    assert len(fixed) == 8, f"Esperaba 8 fixed, encontré {len(fixed)}"

    expected_ids = {
        "F1_cover",
        "F2_about_stats",
        "F3_brand_stages",
        "F4_operation_pillars",
        "F5_case_studies",
        "F6_why_capybaras",
        "F7_team",
        "F8_lets_scale",
    }
    assert {m["module_id"] for m in fixed} == expected_ids


def test_catalog_fixed_have_frequency_5(catalog: dict):
    for m in catalog["modules"]:
        if m["tier"] == "fixed":
            assert m["frequency"] == 5, f"{m['module_id']} fixed con frequency != 5"


def test_why_capybaras_v3_pillars(catalog: dict, catalog_index):
    mod = catalog_index["F6_why_capybaras"]
    pillars = mod["schema"]["pillars"]["default"]
    assert len(pillars) == 4, "Why Capybaras v3 debe tener 4 pilares"
    slugs = {p["slug"] for p in pillars}
    expected_slugs = {
        "end_of_amateur_hour",
        "proprietary_operating_system",
        "intellectual_capital",
        "ceo_bandwidth_recovery",
    }
    assert slugs == expected_slugs, (
        f"Why Capybaras v3 pillars slugs incorrectos: {slugs}"
    )
    for p in pillars:
        assert "en" in p["title"] and "es" in p["title"]
        assert "en" in p["body"] and "es" in p["body"]


# ─────────────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────────────


def test_templates_count(templates: list[dict]):
    assert len(templates) == 4, f"Esperaba 4 templates, encontré {len(templates)}"


def test_templates_have_required_fields(templates: list[dict]):
    required = {"archetype", "name", "description", "default_blocks"}
    for t in templates:
        missing = required - t.keys()
        assert not missing, f"Template {t.get('archetype', '?')} sin campos: {missing}"


def test_templates_archetypes_are_the_4_valid(templates: list[dict]):
    archetypes = sorted([t["archetype"] for t in templates])
    assert archetypes == ["cvr", "defense", "launch", "scale_seo"]


def test_templates_bilingual_name_and_description(templates: list[dict]):
    for t in templates:
        assert "en" in t["name"] and "es" in t["name"], (
            f"Template {t['archetype']}: name sin en/es"
        )
        assert "en" in t["description"] and "es" in t["description"], (
            f"Template {t['archetype']}: description sin en/es"
        )


def test_templates_reference_only_existing_module_ids(
    templates: list[dict], catalog_index: dict[str, dict]
):
    for t in templates:
        for module_id in t["default_blocks"]:
            assert module_id in catalog_index, (
                f"Template {t['archetype']}: module_id '{module_id}' no existe en catálogo"
            )


def test_templates_include_all_8_fixed(
    templates: list[dict], catalog_index: dict[str, dict]
):
    fixed_ids = {
        mid for mid, m in catalog_index.items() if m["tier"] == "fixed"
    }
    for t in templates:
        block_set = set(t["default_blocks"])
        missing = fixed_ids - block_set
        assert not missing, (
            f"Template {t['archetype']} no incluye fixed: {sorted(missing)}"
        )


def test_templates_have_at_least_8_blocks(templates: list[dict]):
    for t in templates:
        assert len(t["default_blocks"]) >= 8, (
            f"Template {t['archetype']} tiene menos de 8 bloques"
        )


def test_templates_no_duplicate_blocks_in_default(templates: list[dict]):
    for t in templates:
        blocks = t["default_blocks"]
        assert len(blocks) == len(set(blocks)), (
            f"Template {t['archetype']} tiene module_ids duplicados en default_blocks"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Schema proposal-v1.json
# ─────────────────────────────────────────────────────────────────────────────


def test_proposal_schema_file_exists(schema_proposal: dict):
    assert schema_proposal["module"] == "proposal"
    assert schema_proposal["version"] == 1
    assert "entities" in schema_proposal


def test_proposal_schema_has_5_entities(schema_proposal: dict):
    expected = {"proposal", "block", "catalog_module", "template", "interested_vote"}
    assert set(schema_proposal["entities"].keys()) == expected
