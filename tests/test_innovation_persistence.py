"""Tests de la capa de persistencia M24 Innovation Board.

Estrategia: se ejerce la API pública (`_create_idea`, `_upsert_voto`, ...) a
través de un `_SupabaseBackend` con un transport fake en memoria — mismo patrón
que el test transport-level de `test_revenue_forecast_persistence.py`. NINGÚN
test pega a red real ni escribe a disco real (`data/`).

Cobertura:
    1. _create_idea → _get_idea round-trip
    2. _upsert_voto dos veces mismo votante → un solo voto, valor actualizado
    3. _upsert_voto con razón vacía → ValueError
    4. _list_ideas filtrado por area y por estado
    5. _add_prototipo mismo nombre dos veces → version 1 y 2
    6. _add_comentario + _toggle_destacado
"""

from __future__ import annotations

import uuid

import pytest

from core import innovation_persistence as ip


# ─────────────────────────────────────────────────────────────────────────────
# Transport fake — emulador PostgREST mínimo en memoria (get/post/patch/delete)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeTransport:
    """Transport-in-memory: soporta los filtros `eq.` + select/limit/order que
    usa `_SupabaseBackend`, y genera id/created_at en el post (como la DB)."""

    def __init__(self):
        self.storage: dict[str, list[dict]] = {}
        self.calls: list[dict] = []

    @staticmethod
    def _matches(row: dict, params: dict) -> bool:
        for k, v in params.items():
            if k in ("select", "limit", "order"):
                continue
            if isinstance(v, str) and v.startswith("eq."):
                if str(row.get(k)) != v[len("eq."):]:
                    return False
        return True

    def get(self, table, params):
        self.calls.append({"op": "get", "table": table, "params": params})
        rows = [r for r in self.storage.get(table, []) if self._matches(r, params)]
        if "limit" in params:
            try:
                rows = rows[: int(params["limit"])]
            except (ValueError, TypeError):
                pass
        return rows

    def post(self, table, rows, upsert=False):
        self.calls.append({"op": "post", "table": table, "rows": rows, "upsert": upsert})
        stored = []
        for r in rows:
            row = dict(r)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", "2026-01-01T00:00:00+00:00")
            self.storage.setdefault(table, []).append(row)
            stored.append(row)
        return stored

    def patch(self, table, params, patch):
        self.calls.append({"op": "patch", "table": table, "params": params, "patch": patch})
        updated = []
        for row in self.storage.get(table, []):
            if self._matches(row, params):
                row.update(patch)
                updated.append(row)
        return updated

    def delete(self, table, params):
        self.calls.append({"op": "delete", "table": table, "params": params})
        return []


def _clear_all_caches():
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
def fake_transport():
    """Inyecta un `_SupabaseBackend` con transport fake y limpia caches alrededor."""
    _clear_all_caches()
    fake = _FakeTransport()
    ip._set_backend_for_testing(ip._SupabaseBackend(transport=fake))
    try:
        yield fake
    finally:
        ip._set_backend_for_testing(None)
        _clear_all_caches()


# ─────────────────────────────────────────────────────────────────────────────
# 1. _create_idea → _get_idea round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_create_idea_get_idea_roundtrip(fake_transport):
    idea_id = ip._create_idea(
        {
            "titulo": "Auto-negativizar términos",
            "descripcion": "desc",
            "problema": "gasto sin conversión",
            "area": "ppc",
            "impacto": "alto",
            "esfuerzo": "bajo",
            "autor": "Lenin Acosta",
        }
    )

    assert isinstance(idea_id, str) and idea_id

    got = ip._get_idea(idea_id)
    assert got["id"] == idea_id
    assert got["titulo"] == "Auto-negativizar términos"
    assert got["area"] == "ppc"
    assert got["impacto"] == "alto"
    assert got["esfuerzo"] == "bajo"
    # estado default aplicado por el backend
    assert got["estado"] == "nueva"


# ─────────────────────────────────────────────────────────────────────────────
# 2. _upsert_voto dos veces mismo votante → un solo voto, valor actualizado
# ─────────────────────────────────────────────────────────────────────────────

def test_upsert_voto_is_idempotent_per_votante(fake_transport):
    idea_id = ip._create_idea({"titulo": "Idea", "area": "ppc"})

    ip._upsert_voto(idea_id, "lenin", 1, "me convence")
    ip._upsert_voto(idea_id, "lenin", -1, "cambié de opinión")

    votos = ip._list_votos(idea_id)
    assert len(votos) == 1
    assert votos[0]["votante"] == "lenin"
    assert votos[0]["valor"] == -1
    assert votos[0]["razon"] == "cambié de opinión"


# ─────────────────────────────────────────────────────────────────────────────
# 3. _upsert_voto con razón vacía → ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_upsert_voto_empty_razon_raises(fake_transport):
    idea_id = ip._create_idea({"titulo": "Idea", "area": "ppc"})

    with pytest.raises(ValueError):
        ip._upsert_voto(idea_id, "lenin", 1, "   ")

    # No debe haber quedado ningún voto persistido.
    assert ip._list_votos(idea_id) == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. _list_ideas filtrado por area y por estado
# ─────────────────────────────────────────────────────────────────────────────

def test_list_ideas_filtered_by_area_and_estado(fake_transport):
    a = ip._create_idea({"titulo": "A", "area": "ppc", "estado": "nueva"})
    b = ip._create_idea({"titulo": "B", "area": "account", "estado": "nueva"})
    ip._create_idea({"titulo": "C", "area": "ppc", "estado": "nueva"})

    ip._update_idea(b, {"estado": "aprobada"})

    ppc = ip._list_ideas(area="ppc")
    assert sorted(i["titulo"] for i in ppc) == ["A", "C"]

    aprobadas = ip._list_ideas(estado="aprobada")
    assert [i["titulo"] for i in aprobadas] == ["B"]

    # combinado: ppc + nueva → A y C (b ya no es 'nueva')
    ppc_nuevas = ip._list_ideas(area="ppc", estado="nueva")
    assert sorted(i["titulo"] for i in ppc_nuevas) == ["A", "C"]
    assert a  # sanity: id devuelto


# ─────────────────────────────────────────────────────────────────────────────
# 5. _add_prototipo mismo nombre dos veces → version 1 y 2
# ─────────────────────────────────────────────────────────────────────────────

def test_add_prototipo_versions_same_nombre(fake_transport):
    idea_id = ip._create_idea({"titulo": "Idea", "area": "research"})

    ip._add_prototipo(idea_id, "mockup", "<html>v1</html>", "lenin")
    ip._add_prototipo(idea_id, "mockup", "<html>v2</html>", "lenin")

    protos = ip._list_prototipos(idea_id)
    assert sorted(p["version"] for p in protos) == [1, 2]
    # El listado liviano NO trae html_content
    assert all("html_content" not in p for p in protos)


# ─────────────────────────────────────────────────────────────────────────────
# 6. _add_comentario + _toggle_destacado
# ─────────────────────────────────────────────────────────────────────────────

def test_add_comentario_and_toggle_destacado(fake_transport):
    idea_id = ip._create_idea({"titulo": "Idea", "area": "ops"})

    ip._add_comentario(idea_id, "lenin", "gran punto")
    coms = ip._list_comentarios(idea_id)
    assert len(coms) == 1
    assert coms[0]["cuerpo"] == "gran punto"
    assert coms[0]["destacado"] is False

    cid = coms[0]["id"]
    ip._toggle_destacado(cid, True)

    coms2 = ip._list_comentarios(idea_id)
    assert coms2[0]["destacado"] is True
