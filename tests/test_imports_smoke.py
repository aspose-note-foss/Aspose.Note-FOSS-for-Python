import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class TestImportsSmoke(unittest.TestCase):
    def test_imports_smoke(self) -> None:
        import aspose.note  # noqa: F401
        import aspose.note._internal.onestore  # noqa: F401
        import aspose.note._internal.ms_one  # noqa: F401
        import aspose.note._internal.onenote  # noqa: F401
        from aspose.note._internal.onenote import Document, Page, Outline, RichText  # noqa: F401
