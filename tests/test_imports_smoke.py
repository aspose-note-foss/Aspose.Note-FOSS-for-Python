import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class TestImportsSmoke(unittest.TestCase):
    def test_imports_smoke(self) -> None:
        import onestore  # noqa: F401
