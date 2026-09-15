"""Raw spSearchTerm downloads kept as gzip files, so a mapping bug found after Amazon's
65-day retention can still be replayed. Deletion is driven only by the request manifest."""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
import re
import shutil
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from core.integrations.store import _Rest

log = logging.getLogger(__name__)

RAW_DIR_ENV = "ADS_RAW_DIR"
DEFAULT_RAW_DIR = "/app/data/ads_raw"
RAW_RETENTION_DAYS = 180
REPORT_REQUESTS_TABLE = "ads_report_requests"
PRUNE_BATCH_SIZE = 500
GZIP_MAGIC = b"\x1f\x8b"
_COPY_CHUNK_BYTES = 1 << 20
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")


class RawReportError(RuntimeError):
    """The downloaded body is not a usable report file."""


@dataclass(frozen=True)
class StoredRaw:
    relative_path: str
    size_bytes: int
    sha256: str


class _HashingWriter:
    def __init__(self, target: BinaryIO):
        self._target = target
        self._digest = hashlib.sha256()
        self.size_bytes = 0

    def write(self, chunk: bytes) -> int:
        self._target.write(chunk)
        self._digest.update(chunk)
        self.size_bytes += len(chunk)
        return len(chunk)

    def flush(self) -> None:
        self._target.flush()

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()


def raw_root() -> Path:
    return Path(os.environ.get(RAW_DIR_ENV, "").strip() or DEFAULT_RAW_DIR)


def raw_relative_path(profile_id: str, report_id: str, requested_on: date) -> str:
    for segment in (profile_id, report_id):
        if not _SAFE_SEGMENT_RE.match(str(segment)):
            raise ValueError(f"unsafe path segment for a raw report: {segment!r}")
    return f"{profile_id}/{requested_on:%Y-%m}/{report_id}.json.gz"


def store_download(root: Path, relative_path: str, write_body: Callable[[BinaryIO], int]) -> StoredRaw:
    target = _inside_root(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    download_tmp = target.with_name(f"{target.name}.tmp")
    gzip_tmp = target.with_name(f"{target.name}.gz.tmp")
    try:
        with open(download_tmp, "wb") as body_file:
            writer = _HashingWriter(body_file)
            write_body(writer)
            body_file.flush()
            os.fsync(body_file.fileno())
        if writer.size_bytes == 0:
            raise RawReportError("the report download was empty")

        if _starts_with_gzip(download_tmp):
            _verify_gzip(download_tmp)
            stored_tmp, size_bytes, sha256 = download_tmp, writer.size_bytes, writer.sha256
        else:
            # Some transports decompress on the fly; the stored copy is gzip either way.
            _require_json_start(download_tmp)
            size_bytes, sha256 = _gzip_copy(download_tmp, gzip_tmp)
            stored_tmp = gzip_tmp
        os.replace(stored_tmp, target)
    finally:
        download_tmp.unlink(missing_ok=True)
        gzip_tmp.unlink(missing_ok=True)
    log.info("amazon_ads: raw report stored at %s (%d bytes)", relative_path, size_bytes)
    return StoredRaw(relative_path=relative_path, size_bytes=size_bytes, sha256=sha256)


def prune_expired(rest: _Rest, root: Path, now: datetime, retention_days: int = RAW_RETENTION_DAYS) -> int:
    cutoff = now - timedelta(days=retention_days)
    expired_requests = rest.select(
        REPORT_REQUESTS_TABLE,
        {
            "select": "id,raw_path",
            "raw_status": "eq.kept",
            "saved_at": f"lt.{cutoff.isoformat()}",
            "order": "saved_at.asc",
            "limit": str(PRUNE_BATCH_SIZE),
        },
    )
    pruned_count = 0
    for request in expired_requests:
        raw_path = str(request.get("raw_path") or "")
        if raw_path and not _unlink_raw(root, raw_path, request.get("id")):
            continue
        rest.update(
            REPORT_REQUESTS_TABLE,
            {"id": f"eq.{request['id']}"},
            {"raw_status": "pruned", "raw_pruned_at": now.isoformat()},
        )
        pruned_count += 1
    if pruned_count:
        log.info("amazon_ads: pruned %d raw reports saved before %s", pruned_count, cutoff.date())
    return pruned_count


def _unlink_raw(root: Path, raw_path: str, request_id) -> bool:
    try:
        target = _inside_root(root, raw_path)
    except ValueError:
        log.error("amazon_ads: request %s points outside the raw directory, not pruned", request_id)
        return False
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        log.error("amazon_ads: could not delete raw report of request %s: %s", request_id, exc)
        return False
    return True


def _inside_root(root: Path, relative_path: str) -> Path:
    resolved_root = Path(root).resolve()
    target = (resolved_root / relative_path).resolve()
    if not target.is_relative_to(resolved_root) or target == resolved_root:
        raise ValueError(f"raw report path escapes the raw directory: {relative_path!r}")
    return target


def _starts_with_gzip(path: Path) -> bool:
    with open(path, "rb") as body_file:
        return body_file.read(2) == GZIP_MAGIC


def _verify_gzip(path: Path) -> None:
    try:
        with gzip.open(path, "rb") as compressed:
            while compressed.read(_COPY_CHUNK_BYTES):
                pass
    except (OSError, EOFError, zlib.error) as exc:
        raise RawReportError(f"the report download is not a valid gzip file: {exc}") from exc


def _require_json_start(path: Path) -> None:
    with open(path, "rb") as body_file:
        first_bytes = body_file.read(64).lstrip()
    if not first_bytes.startswith((b"[", b"{")):
        raise RawReportError("the report download is neither gzip nor JSON")


def _gzip_copy(source: Path, destination: Path) -> tuple[int, str]:
    with open(destination, "wb") as destination_file:
        writer = _HashingWriter(destination_file)
        with open(source, "rb") as source_file, gzip.GzipFile(fileobj=writer, mode="wb") as compressed:
            shutil.copyfileobj(source_file, compressed, _COPY_CHUNK_BYTES)
        destination_file.flush()
        os.fsync(destination_file.fileno())
    return writer.size_bytes, writer.sha256
