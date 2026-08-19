"""Single source of truth for the Agency OS data root.

From AGENCY_OS_DATA_DIR (absolute, e.g. a mounted volume); falls back to relative
Path("data") — bit-for-bit the historical local/Cloud behavior and the value the
tests monkeypatch. No .resolve() on the default, on purpose.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_data_root() -> Path:
    raw = os.environ.get("AGENCY_OS_DATA_DIR")
    return Path(raw).expanduser().resolve() if raw else Path("data")


DATA_ROOT = get_data_root()
