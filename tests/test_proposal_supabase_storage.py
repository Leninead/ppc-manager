"""Tests M29 Fase 2 — SupabaseStorage contra un transport en memoria (mock PostgREST).

Sin red: `FakeTransport` replica la semántica de los queries que usa SupabaseStorage
(filtros `eq`, `select`, `order=version.desc`, `limit`, upsert por PK (id, version)).
Valida los 6 métodos del contrato ProposalStorage + round-trip jsonb + auto-versionado,
y la lógica del selector de backend `_storage_config`.
"""

from __future__ import annotations

import pandas as pd
import pytest

from core.proposals.persistence import SupabaseStorage, _PROPOSALS_TABLE


class FakeTransport:
    """Mock en memoria de PostgREST para los patrones de query que usa SupabaseStorage."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {}

    def post(self, table: str, rows: list[dict], upsert: bool = False) -> list[dict]:
        bucket = self.tables.setdefault(table, [])
        for row in rows:
            if upsert and table == _PROPOSALS_TABLE:
                # PK (id, version): reemplazar la fila existente, si la hay.
                for i, existing in enumerate(bucket):
                    if (
                        existing["id"] == row["id"]
                        and existing["version"] == row["version"]
                    ):
                        bucket[i] = row
                        break
                else:
                    bucket.append(row)
            else:
                bucket.append(row)
        return rows

    def get(self, table: str, params: dict) -> list[dict]:
        rows = list(self.tables.get(table, []))
        # filtros eq.<valor>
        for key, val in params.items():
            if key in ("select", "order", "limit"):
                continue
            if isinstance(val, str) and val.startswith("eq."):
                target = val[3:]
                rows = [r for r in rows if str(r.get(key)) == target]
        # order=<col>.<dir>
        order = params.get("order")
        if order:
            col, _, direction = order.partition(".")
            rows.sort(key=lambda r: r.get(col), reverse=(direction == "desc"))
        # limit
        limit = params.get("limit")
        if limit is not None:
            rows = rows[: int(limit)]
        # select projection
        select = params.get("select", "*")
        if select == "*":
            return [dict(r) for r in rows]
        cols = [c.strip() for c in select.split(",")]
        return [{c: r.get(c) for c in cols} for r in rows]


def _minimal_proposal(pid: str = "p1", version: int = 1, **over) -> dict:
    p = {
        "id": pid,
        "version": version,
        "client_name": "Acme",
        "status": "draft",
        "archetype": "launch",
        "updated_at": f"2026-06-09T00:00:0{version}",
        "blocks": [{"module_id": "F1_cover", "data": {"x": version}}],
        "meta": {},
    }
    p.update(over)
    return p


@pytest.fixture
def storage():
    return SupabaseStorage(transport=FakeTransport())


class TestSupabaseStorageProposals:
    def test_write_read_roundtrip(self, storage):
        p = _minimal_proposal()
        ref = storage.write_proposal(p)
        assert ref == "p1__v1"
        got = storage.read_proposal("p1", 1)
        assert got == p  # round-trip jsonb completo (no se pierde nada del dict)

    def test_read_missing_returns_none(self, storage):
        assert storage.read_proposal("nope", 1) is None

    def test_max_version_zero_when_absent(self, storage):
        assert storage.max_version_for("p1") == 0

    def test_max_version_tracks_highest(self, storage):
        storage.write_proposal(_minimal_proposal(version=1))
        storage.write_proposal(_minimal_proposal(version=3))
        storage.write_proposal(_minimal_proposal(version=2))
        assert storage.max_version_for("p1") == 3

    def test_upsert_same_pk_no_duplicate(self, storage):
        storage.write_proposal(_minimal_proposal(version=1, client_name="A"))
        storage.write_proposal(_minimal_proposal(version=1, client_name="B"))
        assert storage.max_version_for("p1") == 1  # sigue habiendo 1 sola versión
        assert storage.read_proposal("p1", 1)["client_name"] == "B"  # última gana

    def test_list_proposal_files_yields_data(self, storage):
        storage.write_proposal(_minimal_proposal(pid="p1", version=1))
        storage.write_proposal(_minimal_proposal(pid="p2", version=1))
        datas = list(storage.list_proposal_files())
        assert sorted(d["id"] for d in datas) == ["p1", "p2"]
        assert all("blocks" in d for d in datas)  # devuelve el dict completo


class TestSupabaseStorageVotes:
    def test_append_and_read(self, storage):
        storage.append_vote(
            {
                "id": "v1",
                "module_id": "F1_cover",
                "voter_name": "Lenin",
                "voted_at": "2026-06-09",
                "proposal_id": "p1",
            }
        )
        df = storage.read_votes()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]["module_id"] == "F1_cover"

    def test_read_votes_empty_has_columns(self, storage):
        df = storage.read_votes()
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert list(df.columns) == [
            "id",
            "module_id",
            "voter_name",
            "voted_at",
            "proposal_id",
        ]


class TestStorageSelector:
    def test_config_none_without_env(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        from core.proposals import persistence as pp

        # Sin env y sin [supabase] en secrets → None (no rompe fuera de runtime Streamlit).
        assert pp._storage_config() is None

    def test_config_from_env(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "k123")
        from core.proposals import persistence as pp

        assert pp._storage_config() == ("https://proj.supabase.co", "k123")
