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


class TestAsposeNoteImports(unittest.TestCase):
    def test_imports(self) -> None:
        import aspose  # noqa: F401
        import aspose.note  # noqa: F401

        from aspose.note import (  # noqa: F401
            Document,
            SaveFormat,
            FileFormat,
            License,
            Metered,
            PdfSaveOptions,
        )


class TestAsposeNoteTitleIsTraversable(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.path = p

    def test_title_nodes_are_visible(self) -> None:
        from aspose.note import Document, Title

        doc = Document(self.path)
        titles = doc.GetChildNodes(Title)
        self.assertGreaterEqual(len(titles), 1)


class TestAsposeNoteOutlineCoordinatesAreExposed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.path = p

    def test_outline_has_coordinates_properties(self) -> None:
        from aspose.note import Document, Outline

        doc = Document(self.path)
        outlines = doc.GetChildNodes(Outline)
        self.assertGreaterEqual(len(outlines), 1)

        o = outlines[0]
        self.assertTrue(hasattr(o, "X"))
        self.assertTrue(hasattr(o, "Y"))
        self.assertTrue(hasattr(o, "Width"))

        self.assertTrue(o.X is None or isinstance(o.X, float))
        self.assertTrue(o.Y is None or isinstance(o.Y, float))
        self.assertTrue(o.Width is None or isinstance(o.Width, float))


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestAsposeNoteDocumentSavePdf(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one") or _fixture_path("SimpleTable.one")
        if p is None:
            raise unittest.SkipTest("No .one fixtures found")
        cls.path = p

    def test_open_and_save_pdf_to_stream(self) -> None:
        from aspose.note import Document, SaveFormat

        doc = Document(self.path)
        self.assertGreater(doc.Count(), 0)

        buf = io.BytesIO()
        doc.Save(buf, SaveFormat.Pdf)
        data = buf.getvalue()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 100)

    def test_get_child_nodes_image(self) -> None:
        from aspose.note import Document, Image

        doc = Document(self.path)
        images = doc.GetChildNodes(Image)
        self.assertIsInstance(images, list)
