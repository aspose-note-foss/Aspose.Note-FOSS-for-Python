from __future__ import annotations

import hashlib
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


class TestAsposeNoteImages(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("3ImagesWithDifferentAlignment.one")
        if p is None:
            raise unittest.SkipTest("3ImagesWithDifferentAlignment.one not found")
        cls.path = p

    def test_images_exposed_and_have_bytes(self) -> None:
        from aspose.note import Document, Image

        doc = Document(self.path)
        images = doc.GetChildNodes(Image)
        self.assertEqual(len(images), 3)
        self.assertTrue(all(isinstance(img.Bytes, (bytes, bytearray)) for img in images))
        self.assertTrue(all(len(img.Bytes) > 1024 for img in images))

    def test_images_are_identical_by_hash(self) -> None:
        from aspose.note import Document, Image

        doc = Document(self.path)
        images = doc.GetChildNodes(Image)
        self.assertEqual(len(images), 3)

        digests = [hashlib.sha256(bytes(img.Bytes)).digest() for img in images]
        self.assertEqual(len(set(digests)), 1)


class TestAsposeNoteTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("SimpleTable.one")
        if p is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.path = p

    def test_tables_exposed_with_rows_and_cells(self) -> None:
        from aspose.note import Document, Table, TableRow, TableCell

        doc = Document(self.path)
        tables = doc.GetChildNodes(Table)
        self.assertGreaterEqual(len(tables), 1)

        rows = doc.GetChildNodes(TableRow)
        cells = doc.GetChildNodes(TableCell)
        self.assertGreater(len(rows), 0)
        self.assertGreater(len(cells), 0)

        # Basic structural sanity: each TableRow should have at least 1 cell.
        for row in rows[:10]:
            self.assertGreaterEqual(len(list(row)), 1)


class TestAsposeNoteAttachments(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("OnePageWithFile.one") or _fixture_path("AttachedFileWithTag.one")
        if p is None:
            raise unittest.SkipTest("No attachment fixtures found")
        cls.path = p

    def test_attached_files_exposed_and_have_bytes(self) -> None:
        from aspose.note import AttachedFile, Document

        doc = Document(self.path)
        atts = doc.GetChildNodes(AttachedFile)
        self.assertGreaterEqual(len(atts), 1)

        # Filename should be present.
        self.assertTrue(any((a.FileName or "").strip() for a in atts))

        # Bytes are best-effort in current implementation (may be empty for some fixtures).
        self.assertTrue(all(isinstance(a.Bytes, (bytes, bytearray)) for a in atts))
