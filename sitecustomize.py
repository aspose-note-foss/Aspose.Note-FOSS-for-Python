"""Test/dev convenience: allow importing `onestore` from `src/` without installation.

Python auto-imports `sitecustomize` (if present on sys.path) during startup.
Keeping this tiny helps local runs that don't install the project.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
