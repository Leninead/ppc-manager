"""Tests for the single data-root resolver (core/data_root.py)."""

from pathlib import Path

import core.data_root as dr


def test_default_es_relativo_data(monkeypatch):
    # No env var → relative Path("data"), same as before the VPS work.
    monkeypatch.delenv("AGENCY_OS_DATA_DIR", raising=False)
    root = dr.get_data_root()
    assert root == Path("data")
    assert not root.is_absolute()


def test_env_override_es_absoluto(monkeypatch, tmp_path):
    # AGENCY_OS_DATA_DIR set → that path, absolute and resolved.
    monkeypatch.setenv("AGENCY_OS_DATA_DIR", str(tmp_path))
    root = dr.get_data_root()
    assert root.is_absolute()
    assert root == tmp_path.resolve()


def test_env_vacio_cae_al_default(monkeypatch):
    # Empty env var falls back to the relative default.
    monkeypatch.setenv("AGENCY_OS_DATA_DIR", "")
    assert dr.get_data_root() == Path("data")


def test_los_4_modulos_comparten_la_raiz():
    # persistence / forecast / innovation / proposal_paths share one resolver.
    import core.forecast.persistence as f
    import core.innovation.persistence as i
    import core.persistence as p
    import core.proposal_paths as pp

    assert p.DATA_ROOT == dr.DATA_ROOT
    assert f.DATA_ROOT == dr.DATA_ROOT
    assert i.DATA_ROOT == dr.DATA_ROOT
    assert p.SCHEMAS_ROOT == dr.DATA_ROOT / "_schemas"
    assert pp.SALES_ROOT == dr.DATA_ROOT / "sales"
    assert pp.SCHEMAS_DIR == dr.DATA_ROOT / "_schemas"
