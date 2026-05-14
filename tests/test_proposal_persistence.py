"""Tests de la capa de persistencia Sales Proposals.

Cubre:
- Round-trip: save_proposal → get_proposal devuelve idéntico.
- Auto-version: save_proposal con mismo id incrementa version.
- Soft delete: delete_proposal marca status=archived, no borra del disco.
- Hard delete: borra todas las versiones del id.
- Template instantiation: genera Proposal válida con 8 FIXED + variables.
- Vote log: append-only, get_module_vote_count cuenta correcto.
- Validación FK: rechaza module_id inexistentes.
- Validación FIXED: rechaza propuestas sin todos los FIXED.
- list_proposals: filtros por cliente, status, archetype.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import proposal_persistence as pp
from core.proposal_paths import PROPOSALS_DIR, VOTES_LOG_FILE


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: storage en directorio temporal (aislado por test)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Aísla cada test: redirige PROPOSALS_DIR y VOTES_LOG_FILE a un tmp_path.

    Esto evita que los tests escriban en data/sales/proposals/ del repo y
    permite tests reproducibles e independientes.
    """
    tmp_proposals = tmp_path / "proposals"
    tmp_votes = tmp_path / "interested-votes.parquet"

    monkeypatch.setattr(pp, "PROPOSALS_DIR", tmp_proposals)
    monkeypatch.setattr(pp, "VOTES_LOG_FILE", tmp_votes)

    # Reset storage singleton para que use los paths nuevos.
    pp._set_storage_for_testing(None)
    # Forzar reconstrucción del LocalJsonStorage con los paths parcheados.
    # Como LocalJsonStorage no captura los paths en __init__, basta con
    # invalidar el singleton — _default_storage lo reconstruirá.

    class _ScopedStorage(pp.LocalJsonStorage):
        def write_proposal(self, proposal):
            tmp_proposals.mkdir(parents=True, exist_ok=True)
            path = tmp_proposals / f"{proposal['id']}__v{proposal['version']}.json"
            from core.proposal_persistence import _write_json
            _write_json(path, proposal)
            return path

        def read_proposal(self, proposal_id, version):
            from core.proposal_persistence import _read_json
            return _read_json(tmp_proposals / f"{proposal_id}__v{version}.json")

        def list_proposal_files(self):
            from core.proposal_persistence import _read_json
            if not tmp_proposals.exists():
                return
            for f in sorted(tmp_proposals.glob("*__v*.json")):
                data = _read_json(f)
                if data is not None:
                    yield data

        def max_version_for(self, proposal_id):
            if not tmp_proposals.exists():
                return 0
            max_v = 0
            for f in tmp_proposals.glob(f"{proposal_id}__v*.json"):
                try:
                    v = int(f.stem.split("__v")[-1])
                    if v > max_v:
                        max_v = v
                except (ValueError, IndexError):
                    continue
            return max_v

        def append_vote(self, vote_row):
            import pandas as pd
            new_df = pd.DataFrame([vote_row])
            if tmp_votes.exists():
                existing = pd.read_parquet(tmp_votes)
                combined = pd.concat([existing, new_df], ignore_index=True)
            else:
                combined = new_df
            combined.to_parquet(tmp_votes, compression="snappy", index=False)

        def read_votes(self):
            import pandas as pd
            if not tmp_votes.exists():
                return pd.DataFrame(
                    columns=["id", "module_id", "voter_name", "voted_at", "proposal_id"]
                )
            return pd.read_parquet(tmp_votes)

    pp._set_storage_for_testing(_ScopedStorage())

    yield

    # Cleanup del singleton después del test
    pp._set_storage_for_testing(None)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_minimal_proposal_from_launch_template() -> dict:
    """Crea una Proposal válida usando el template Launch."""
    return pp.instantiate_proposal_from_template(
        archetype="launch",
        client_name="Test Client SA",
        language="en",
        sales_director="Lenin Acosta",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo + templates accesibles
# ─────────────────────────────────────────────────────────────────────────────


def test_load_catalog():
    catalog = pp.load_catalog()
    assert "modules" in catalog
    assert len(catalog["modules"]) >= 37


def test_list_templates():
    templates = pp.list_templates()
    assert len(templates) == 4


def test_get_template_returns_dict_for_each_archetype():
    for archetype in ("launch", "scale_seo", "defense", "cvr"):
        t = pp.get_template(archetype)
        assert t is not None, f"Template para {archetype} no se encontró"
        assert t["archetype"] == archetype


def test_get_template_returns_none_for_custom():
    assert pp.get_template("custom") is None


def test_get_template_returns_none_for_invalid_archetype():
    assert pp.get_template("nonsense") is None


# ─────────────────────────────────────────────────────────────────────────────
# Template instantiation
# ─────────────────────────────────────────────────────────────────────────────


def test_instantiate_from_launch_template():
    p = _make_minimal_proposal_from_launch_template()
    assert p["archetype"] == "launch"
    assert p["client_name"] == "Test Client SA"
    assert p["language"] == "en"
    assert p["created_by"] == "Lenin Acosta"
    assert p["status"] == "draft"
    assert p["version"] == 1
    assert p["id"], "id debe estar populado"
    assert len(p["blocks"]) >= 8


def test_instantiated_proposal_has_all_8_fixed():
    p = _make_minimal_proposal_from_launch_template()
    fixed_in_blocks = [b["module_id"] for b in p["blocks"] if b["is_fixed"]]
    expected = {
        "F1_cover",
        "F2_about_stats",
        "F3_brand_stages",
        "F4_operation_pillars",
        "F5_case_studies",
        "F6_why_capybaras",
        "F7_team",
        "F8_lets_scale",
    }
    assert set(fixed_in_blocks) == expected


def test_instantiate_from_custom_raises():
    with pytest.raises(ValueError):
        pp.instantiate_proposal_from_template(
            archetype="custom",
            client_name="X",
            language="en",
            sales_director="Y",
        )


def test_instantiated_blocks_have_unique_ids():
    p = _make_minimal_proposal_from_launch_template()
    ids = [b["id"] for b in p["blocks"]]
    assert len(ids) == len(set(ids))


def test_instantiated_block_proposal_id_matches():
    p = _make_minimal_proposal_from_launch_template()
    for b in p["blocks"]:
        assert b["proposal_id"] == p["id"]


# ─────────────────────────────────────────────────────────────────────────────
# Save / Get round-trip
# ─────────────────────────────────────────────────────────────────────────────


def test_save_proposal_assigns_version_1_first_time():
    p = _make_minimal_proposal_from_launch_template()
    saved = pp.save_proposal(p)
    assert saved["version"] == 1


def test_save_proposal_round_trip():
    p = _make_minimal_proposal_from_launch_template()
    saved = pp.save_proposal(p)
    fetched = pp.get_proposal(saved["id"])
    assert fetched is not None
    assert fetched["id"] == saved["id"]
    assert fetched["version"] == saved["version"]
    assert fetched["client_name"] == saved["client_name"]
    assert len(fetched["blocks"]) == len(saved["blocks"])


def test_save_proposal_auto_increments_version():
    p = _make_minimal_proposal_from_launch_template()
    v1 = pp.save_proposal(p)
    assert v1["version"] == 1
    v2 = pp.save_proposal(v1)
    assert v2["version"] == 2
    v3 = pp.save_proposal(v2)
    assert v3["version"] == 3


def test_get_proposal_returns_none_if_not_found():
    assert pp.get_proposal("does-not-exist") is None


def test_get_proposal_specific_version():
    p = _make_minimal_proposal_from_launch_template()
    v1 = pp.save_proposal(p)
    v2 = pp.save_proposal(v1)
    fetched_v1 = pp.get_proposal(v1["id"], version=1)
    fetched_v2 = pp.get_proposal(v1["id"], version=2)
    assert fetched_v1["version"] == 1
    assert fetched_v2["version"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Validación FK + reglas de negocio
# ─────────────────────────────────────────────────────────────────────────────


def test_save_proposal_rejects_unknown_module_id():
    p = _make_minimal_proposal_from_launch_template()
    p["blocks"][0]["module_id"] = "Z99_does_not_exist"
    with pytest.raises(ValueError, match="module_id"):
        pp.save_proposal(p)


def test_save_proposal_rejects_is_fixed_mismatch():
    p = _make_minimal_proposal_from_launch_template()
    # Encontrá un block no-fixed y marcalo como fixed.
    for b in p["blocks"]:
        if not b["is_fixed"]:
            b["is_fixed"] = True
            break
    with pytest.raises(ValueError, match="is_fixed"):
        pp.save_proposal(p)


def test_save_proposal_rejects_missing_fixed_block():
    p = _make_minimal_proposal_from_launch_template()
    # Sacamos un fixed
    p["blocks"] = [b for b in p["blocks"] if b["module_id"] != "F1_cover"]
    with pytest.raises(ValueError, match="FIXED"):
        pp.save_proposal(p)


def test_save_proposal_rejects_bad_copy_override_keys():
    p = _make_minimal_proposal_from_launch_template()
    p["blocks"][0]["copy_overrides"] = {"fr": "..."}
    with pytest.raises(ValueError, match="copy_overrides"):
        pp.save_proposal(p)


def test_save_proposal_rejects_block_proposal_id_mismatch():
    p = _make_minimal_proposal_from_launch_template()
    p["blocks"][0]["proposal_id"] = "wrong-id"
    with pytest.raises(ValueError, match="proposal_id"):
        pp.save_proposal(p)


def test_save_proposal_rejects_invalid_language():
    p = _make_minimal_proposal_from_launch_template()
    p["language"] = "fr"
    with pytest.raises(ValueError, match="language"):
        pp.save_proposal(p)


def test_save_proposal_rejects_invalid_archetype():
    p = _make_minimal_proposal_from_launch_template()
    p["archetype"] = "nonsense"
    with pytest.raises(ValueError, match="archetype"):
        pp.save_proposal(p)


def test_save_proposal_rejects_invalid_status():
    p = _make_minimal_proposal_from_launch_template()
    p["status"] = "weird"
    with pytest.raises(ValueError, match="status"):
        pp.save_proposal(p)


# ─────────────────────────────────────────────────────────────────────────────
# Delete (soft + hard)
# ─────────────────────────────────────────────────────────────────────────────


def test_soft_delete_marks_archived_without_removing_files():
    p = _make_minimal_proposal_from_launch_template()
    saved = pp.save_proposal(p)
    pid = saved["id"]

    ok = pp.delete_proposal(pid, hard_delete=False)
    assert ok

    # La latest version ahora tiene status=archived
    latest = pp.get_proposal(pid)
    assert latest["status"] == "archived"

    # Pero v1 sigue accesible
    v1 = pp.get_proposal(pid, version=1)
    assert v1 is not None
    assert v1["status"] == "draft"


def test_hard_delete_removes_all_versions():
    p = _make_minimal_proposal_from_launch_template()
    v1 = pp.save_proposal(p)
    v2 = pp.save_proposal(v1)
    pid = v1["id"]

    ok = pp.delete_proposal(pid, hard_delete=True)
    assert ok

    assert pp.get_proposal(pid, version=1) is None
    assert pp.get_proposal(pid, version=2) is None


def test_delete_nonexistent_returns_false():
    assert pp.delete_proposal("does-not-exist", hard_delete=False) is False
    assert pp.delete_proposal("does-not-exist", hard_delete=True) is False


# ─────────────────────────────────────────────────────────────────────────────
# list_proposals + filtros
# ─────────────────────────────────────────────────────────────────────────────


def test_list_proposals_returns_only_latest_versions():
    p = _make_minimal_proposal_from_launch_template()
    pp.save_proposal(p)
    pp.save_proposal(p)  # v2
    pp.save_proposal(p)  # v3

    all_proposals = pp.list_proposals()
    assert len(all_proposals) == 1
    assert all_proposals[0]["version"] == 3


def test_list_proposals_filters_by_client():
    p1 = _make_minimal_proposal_from_launch_template()
    p1["client_name"] = "Cliente A"
    pp.save_proposal(p1)

    p2 = _make_minimal_proposal_from_launch_template()
    p2["client_name"] = "Cliente B"
    pp.save_proposal(p2)

    only_a = pp.list_proposals(client_filter="Cliente A")
    assert len(only_a) == 1
    assert only_a[0]["client_name"] == "Cliente A"


def test_list_proposals_filters_by_status():
    p1 = _make_minimal_proposal_from_launch_template()
    pp.save_proposal(p1)

    p2 = _make_minimal_proposal_from_launch_template()
    p2["status"] = "sent"
    pp.save_proposal(p2)

    sent = pp.list_proposals(status_filter="sent")
    assert len(sent) == 1


def test_list_proposals_filters_by_archetype():
    p_launch = pp.instantiate_proposal_from_template("launch", "X", "en", "L")
    pp.save_proposal(p_launch)

    p_cvr = pp.instantiate_proposal_from_template("cvr", "Y", "en", "L")
    pp.save_proposal(p_cvr)

    only_cvr = pp.list_proposals(archetype_filter="cvr")
    assert len(only_cvr) == 1
    assert only_cvr[0]["archetype"] == "cvr"


# ─────────────────────────────────────────────────────────────────────────────
# Vote log
# ─────────────────────────────────────────────────────────────────────────────


def test_log_interested_vote_appends():
    row = pp.log_interested_vote("V17_made_in_country_advantage", "Marcos")
    assert row["module_id"] == "V17_made_in_country_advantage"
    assert row["voter_name"] == "Marcos"
    assert row["id"]
    assert row["voted_at"]


def test_log_interested_vote_rejects_unknown_module():
    with pytest.raises(ValueError):
        pp.log_interested_vote("ZZ_fake", "Lenin")


def test_get_module_vote_count_zero_when_no_votes():
    assert pp.get_module_vote_count("V17_made_in_country_advantage") == 0


def test_get_module_vote_count_counts_correctly():
    pp.log_interested_vote("V17_made_in_country_advantage", "Marcos")
    pp.log_interested_vote("V17_made_in_country_advantage", "Lenin")
    pp.log_interested_vote("V18_modular_launch_strategy", "Marcos")

    assert pp.get_module_vote_count("V17_made_in_country_advantage") == 2
    assert pp.get_module_vote_count("V18_modular_launch_strategy") == 1
    assert pp.get_module_vote_count("V19_amazon_launch_grid") == 0


def test_log_vote_with_proposal_id_context():
    p = _make_minimal_proposal_from_launch_template()
    saved = pp.save_proposal(p)
    row = pp.log_interested_vote(
        "V17_made_in_country_advantage", "Marcos", proposal_id=saved["id"]
    )
    assert row["proposal_id"] == saved["id"]


# ─────────────────────────────────────────────────────────────────────────────
# Seed proposals
# ─────────────────────────────────────────────────────────────────────────────


def test_get_seed_proposal_returns_none_if_missing():
    # Aún si _seed/ existe con archivos reales, un id falso debe devolver None.
    assert pp.get_seed_proposal("this-seed-does-not-exist-xyz") is None


# ─────────────────────────────────────────────────────────────────────────────
# V1_brand_overview — round-trip de data y copy_overrides (B3-b Step 4)
# ─────────────────────────────────────────────────────────────────────────────


def test_save_proposal_persists_v1_brand_overview_data():
    """data de V1_brand_overview persiste idéntico tras save + get."""
    p = _make_minimal_proposal_from_launch_template()
    v1 = next(b for b in p["blocks"] if b["module_id"] == "V1_brand_overview")
    v1["data"] = {
        "brand_name": "Love To Dream",
        "sku_count": 12,
        "categories": ["Sleep accessories", "Babywear"],
        "markets": ["US", "MX"],
        "amazon_account_type": "seller_fba",
        "ppc_maturity": "intermediate",
        "hero_asins": ["B005ULUZIQ", "B07XYZ1234"],
        "monthly_revenue_band": "100k-500k USD",
        "current_acos_band": "15-25%",
    }

    saved = pp.save_proposal(p)
    assert saved["version"] == 1

    loaded = pp.get_proposal(saved["id"])
    assert loaded is not None
    loaded_v1 = next(b for b in loaded["blocks"] if b["module_id"] == "V1_brand_overview")

    assert loaded_v1["data"] == v1["data"]


def test_save_proposal_persists_v1_brand_overview_copy_overrides_es_en():
    """copy_overrides con ambos idiomas persiste y respeta el contrato i18n."""
    p = _make_minimal_proposal_from_launch_template()
    v1 = next(b for b in p["blocks"] if b["module_id"] == "V1_brand_overview")
    v1["copy_overrides"] = {
        "es": {
            "brand_description": "Marca australiana de sleep solutions.",
            "positioning": "Premium en sueño infantil.",
            "goals": "Crecer 30% YoY en MX.",
            "constraints": "Restock irregular en B005ULUZIQ.",
        },
        "en": {
            "brand_description": "Australian sleep solutions brand.",
            "positioning": "Premium in infant sleep.",
            "goals": "Grow 30% YoY in MX.",
            "constraints": "Irregular restock on B005ULUZIQ.",
        },
    }

    saved = pp.save_proposal(p)
    loaded = pp.get_proposal(saved["id"])
    loaded_v1 = next(b for b in loaded["blocks"] if b["module_id"] == "V1_brand_overview")

    assert loaded_v1["copy_overrides"]["es"] == v1["copy_overrides"]["es"]
    assert loaded_v1["copy_overrides"]["en"] == v1["copy_overrides"]["en"]
    assert set(loaded_v1["copy_overrides"].keys()) == {"es", "en"}


def test_save_proposal_v2_preserves_other_blocks_unchanged():
    """Anti-regresión: al guardar v2 mutando solo V1, los otros blocks quedan idénticos."""
    import copy as _copy

    p = _make_minimal_proposal_from_launch_template()

    # Save inicial (v1) — capturar estado de blocks no-V1
    saved_v1 = pp.save_proposal(p)
    v1_id = saved_v1["id"]
    other_blocks_snapshot = [
        dict(b) for b in saved_v1["blocks"]
        if b["module_id"] != "V1_brand_overview"
    ]

    # Mutar solo V1 en una copia y guardar v2
    mutated = _copy.deepcopy(saved_v1)
    v1 = next(b for b in mutated["blocks"] if b["module_id"] == "V1_brand_overview")
    v1["data"] = {"brand_name": "Test Brand", "markets": ["US"]}

    saved_v2 = pp.save_proposal(mutated)
    assert saved_v2["version"] == 2

    # Verificar que los blocks no-V1 quedaron idénticos
    loaded_v2 = pp.get_proposal(v1_id)
    loaded_others = [
        b for b in loaded_v2["blocks"]
        if b["module_id"] != "V1_brand_overview"
    ]

    assert len(loaded_others) == len(other_blocks_snapshot)
    for original, after in zip(other_blocks_snapshot, loaded_others):
        assert original == after, f"Block {original.get('module_id')} cambió entre v1 y v2"
