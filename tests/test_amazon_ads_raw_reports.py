"""raw_reports: atomic gzip storage with sha256 and manifest-driven pruning. tmp_path and a fake rest only."""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from core.amazon_ads.raw_reports import (
    DEFAULT_RAW_DIR,
    RAW_DIR_ENV,
    REPORT_REQUESTS_TABLE,
    RawReportError,
    prune_expired,
    raw_relative_path,
    raw_root,
    store_download,
)

REPORT_JSON = json.dumps([{"date": "2026-09-01", "searchTerm": "demo", "clicks": 1}]).encode("utf-8")
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def _body_writer(*chunks: bytes):
    def write_body(target) -> int:
        for chunk in chunks:
            target.write(chunk)
        return sum(len(chunk) for chunk in chunks)
    return write_body


class _FakeRest:
    def __init__(self, requests_rows=()):
        self._requests_rows = list(requests_rows)
        self.selects = []
        self.updates = []

    def select(self, table, params):
        self.selects.append((table, params))
        return [dict(row) for row in self._requests_rows]

    def update(self, table, params, changes, stamp=True):
        self.updates.append((table, params, changes))


def test_raw_root_defaults_and_honors_env(monkeypatch, tmp_path):
    monkeypatch.delenv(RAW_DIR_ENV, raising=False)
    assert str(raw_root()).replace("\\", "/") == DEFAULT_RAW_DIR

    monkeypatch.setenv(RAW_DIR_ENV, str(tmp_path))
    assert raw_root() == tmp_path


def test_relative_path_groups_by_profile_and_month():
    assert raw_relative_path("555", "7df1ef5d-45ba", date(2026, 9, 3)) == "555/2026-09/7df1ef5d-45ba.json.gz"


@pytest.mark.parametrize("profile_id, report_id", [("../etc", "r1"), ("555", "a/b"), ("555", ".."), ("", "r1")])
def test_relative_path_rejects_unsafe_segments(profile_id, report_id):
    with pytest.raises(ValueError):
        raw_relative_path(profile_id, report_id, date(2026, 9, 3))


def test_store_keeps_gzip_body_as_downloaded(tmp_path):
    gzip_body = gzip.compress(REPORT_JSON)
    relative_path = "555/2026-09/r1.json.gz"

    stored = store_download(tmp_path, relative_path, _body_writer(gzip_body[:10], gzip_body[10:]))

    stored_file = tmp_path / "555" / "2026-09" / "r1.json.gz"
    assert stored_file.read_bytes() == gzip_body
    assert stored.relative_path == relative_path
    assert stored.size_bytes == len(gzip_body)
    assert stored.sha256 == hashlib.sha256(gzip_body).hexdigest()
    assert list(stored_file.parent.iterdir()) == [stored_file]


def test_store_regzips_a_plain_json_body(tmp_path):
    stored = store_download(tmp_path, "555/2026-09/r2.json.gz", _body_writer(REPORT_JSON))

    stored_file = tmp_path / "555" / "2026-09" / "r2.json.gz"
    stored_bytes = stored_file.read_bytes()
    assert gzip.decompress(stored_bytes) == REPORT_JSON
    assert stored.size_bytes == len(stored_bytes)
    assert stored.sha256 == hashlib.sha256(stored_bytes).hexdigest()
    assert list(stored_file.parent.iterdir()) == [stored_file]


def test_store_replaces_an_existing_file_atomically(tmp_path):
    relative_path = "555/2026-09/r1.json.gz"
    store_download(tmp_path, relative_path, _body_writer(gzip.compress(b"[]")))

    store_download(tmp_path, relative_path, _body_writer(gzip.compress(REPORT_JSON)))

    assert gzip.decompress((tmp_path / relative_path).read_bytes()) == REPORT_JSON


@pytest.mark.parametrize("body", [b"", b"\x1f\x8b\x08\x00corrupted", gzip.compress(REPORT_JSON)[:-6], b"<html>denied"])
def test_store_rejects_unusable_bodies_and_leaves_no_files(tmp_path, body):
    with pytest.raises(RawReportError):
        store_download(tmp_path, "555/2026-09/bad.json.gz", _body_writer(body))

    assert list((tmp_path / "555" / "2026-09").iterdir()) == []


def test_store_cleans_the_temp_file_when_the_download_breaks(tmp_path):
    def broken_download(target) -> int:
        target.write(b"\x1f\x8b partial")
        raise ConnectionError("stream reset")

    with pytest.raises(ConnectionError):
        store_download(tmp_path, "555/2026-09/r3.json.gz", broken_download)

    assert list((tmp_path / "555" / "2026-09").iterdir()) == []


def test_store_refuses_paths_outside_the_root(tmp_path):
    with pytest.raises(ValueError):
        store_download(tmp_path / "raw", "../outside.json.gz", _body_writer(gzip.compress(REPORT_JSON)))

    assert not (tmp_path / "outside.json.gz").exists()


def test_prune_selects_only_kept_reports_older_than_retention(tmp_path):
    rest = _FakeRest()

    prune_expired(rest, tmp_path, NOW, retention_days=180)

    table, params = rest.selects[0]
    assert table == REPORT_REQUESTS_TABLE
    assert params["raw_status"] == "eq.kept"
    assert params["saved_at"] == f"lt.{(NOW - timedelta(days=180)).isoformat()}"


def test_prune_deletes_listed_files_and_marks_them_pruned(tmp_path):
    expired_file = tmp_path / "555" / "2026-02" / "old.json.gz"
    expired_file.parent.mkdir(parents=True)
    expired_file.write_bytes(gzip.compress(b"[]"))
    unlisted_file = tmp_path / "555" / "2026-02" / "unlisted.json.gz"
    unlisted_file.write_bytes(gzip.compress(b"[]"))
    rest = _FakeRest([{"id": 11, "raw_path": "555/2026-02/old.json.gz"}])

    pruned = prune_expired(rest, tmp_path, NOW)

    assert pruned == 1
    assert not expired_file.exists()
    assert unlisted_file.exists()
    assert rest.updates == [(REPORT_REQUESTS_TABLE, {"id": "eq.11"},
                             {"raw_status": "pruned", "raw_pruned_at": NOW.isoformat()})]


def test_prune_marks_a_missing_file_as_pruned(tmp_path):
    rest = _FakeRest([{"id": 12, "raw_path": "555/2026-01/gone.json.gz"}])

    assert prune_expired(rest, tmp_path, NOW) == 1
    assert rest.updates[0][1] == {"id": "eq.12"}


def test_prune_never_touches_paths_outside_the_root(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    victim = tmp_path / "victim.json.gz"
    victim.write_bytes(b"keep me")
    rest = _FakeRest([{"id": 13, "raw_path": "../victim.json.gz"}])

    assert prune_expired(rest, raw_dir, NOW) == 0
    assert victim.exists()
    assert rest.updates == []


def test_prune_with_nothing_expired_changes_nothing(tmp_path):
    kept_file = tmp_path / "555" / "2026-09" / "recent.json.gz"
    kept_file.parent.mkdir(parents=True)
    kept_file.write_bytes(b"x")
    rest = _FakeRest([])

    assert prune_expired(rest, tmp_path, NOW) == 0
    assert kept_file.exists()
    assert rest.updates == []
