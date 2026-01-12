from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import reportlab  # noqa: F401

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def _fixture_path(name: str) -> Path | None:
    p = ROOT / "testfiles" / name
    return p if p.exists() else None


class TestAsposeNoteSaveOptions(unittest.TestCase):
    def test_pdf_save_options_roundtrip(self) -> None:
        from aspose.note import PdfSaveOptions, SaveFormat

        opts = PdfSaveOptions(SaveFormat.Pdf)
        self.assertEqual(opts.SaveFormat, SaveFormat.Pdf)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestAsposeNoteSaveWithOptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.path = p

    def test_save_pdf_with_pdfsaveoptions(self) -> None:
        from aspose.note import Document, PdfSaveOptions, SaveFormat

        doc = Document(self.path)
        buf = io.BytesIO()
        doc.Save(buf, PdfSaveOptions(SaveFormat.Pdf))
        self.assertTrue(buf.getvalue().startswith(b"%PDF"))


class TestAsposeNoteSaveUnsupportedFormats(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.path = p

    def test_save_one_raises(self) -> None:
        from aspose.note import Document, SaveFormat, UnsupportedSaveFormatException

        doc = Document(self.path)
        with self.assertRaises(UnsupportedSaveFormatException):
            doc.Save(io.BytesIO(), SaveFormat.One)
