from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _fixture_path(name: str) -> Path | None:
    p = ROOT / "testfiles" / name
    return p if p.exists() else None


class TestAsposeNoteStubs(unittest.TestCase):
    def test_license_and_metered_are_callable(self) -> None:
        from aspose.note import License, Metered

        lic = License()
        lic.SetLicense("dummy.lic")

        m = Metered()
        m.SetMeteredKey("pub", "priv")


class TestAsposeNoteLoadOptions(unittest.TestCase):
    def test_encrypted_load_raises_incorrect_password(self) -> None:
        from aspose.note import Document, IncorrectPasswordException, LoadOptions

        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")

        with self.assertRaises(IncorrectPasswordException):
            Document(p, LoadOptions(DocumentPassword="pass"))
