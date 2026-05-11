"""Configuración pytest para tests del Agency OS.

Asegura que la raíz del repo está en sys.path antes de cualquier import de tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
