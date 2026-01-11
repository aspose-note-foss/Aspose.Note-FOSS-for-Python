"""Tests for the public onenote API."""

import sys
import unittest
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onenote import Document, Element, Page, Outline, OutlineElement, RichText, Table  # noqa: E402


def _simpletable_path() -> Path | None:
    p = ROOT / "testfiles" / "SimpleTable.one"
    return p if p.exists() else None


class TestDocumentOpen(unittest.TestCase):
    """Test Document.open() functionality."""

    simpletable: ClassVar[Path]

    @classmethod
    def setUpClass(cls) -> None:
        p = _simpletable_path()
        if p is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.simpletable = p

    def test_open_file(self) -> None:
        """Document.open() should load a .one file."""
        doc = Document.open(self.simpletable)
        self.assertIsInstance(doc, Document)

    def test_open_nonexistent_raises(self) -> None:
        """Document.open() should raise FileNotFoundError for missing file."""
        with self.assertRaises(FileNotFoundError):
            Document.open("nonexistent.one")

    def test_from_bytes(self) -> None:
        """Document.from_bytes() should parse raw bytes."""
        data = self.simpletable.read_bytes()
        doc = Document.from_bytes(data)
        self.assertIsInstance(doc, Document)


class TestDocumentStructure(unittest.TestCase):
    """Test Document structure and navigation."""

    @classmethod
    def setUpClass(cls) -> None:
        path = _simpletable_path()
        if path is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.doc = Document.open(path)

    def test_has_pages(self) -> None:
        """Document should have at least one page."""
        self.assertGreaterEqual(len(self.doc.pages), 1)

    def test_page_count_property(self) -> None:
        """page_count property should match len(pages)."""
        self.assertEqual(self.doc.page_count, len(self.doc.pages))

    def test_iteration(self) -> None:
        """Document should be iterable over pages."""
        pages = list(self.doc)
        self.assertEqual(len(pages), len(self.doc.pages))

    def test_indexing(self) -> None:
        """Document should support indexing."""
        if self.doc.pages:
            page = self.doc[0]
            self.assertIsInstance(page, Page)

    def test_get_page(self) -> None:
        """get_page() should return page or None."""
        self.assertIsNotNone(self.doc.get_page(0))
        self.assertIsNone(self.doc.get_page(9999))


class TestPageStructure(unittest.TestCase):
    """Test Page structure and content access."""

    @classmethod
    def setUpClass(cls) -> None:
        path = _simpletable_path()
        if path is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.doc = Document.open(path)
        cls.page = cls.doc.pages[0] if cls.doc.pages else None

    def test_page_has_title(self) -> None:
        """Page should have a title attribute."""
        if self.page:
            self.assertIsInstance(self.page.title, str)

    def test_page_str(self) -> None:
        """str(page) should return title."""
        if self.page:
            self.assertEqual(str(self.page), self.page.title or "(Untitled)")

    def test_page_children(self) -> None:
        """Page should have children list."""
        if self.page:
            self.assertIsInstance(self.page.children, list)


class TestElementIterators(unittest.TestCase):
    """Test element iteration methods."""

    @classmethod
    def setUpClass(cls) -> None:
        path = _simpletable_path()
        if path is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.doc = Document.open(path)

    def test_iter_outlines(self) -> None:
        """iter_outlines() should yield Outline instances."""
        for page in self.doc.pages:
            for outline in page.iter_outlines():
                self.assertIsInstance(outline, Outline)

    def test_iter_elements(self) -> None:
        """iter_elements() should yield OutlineElement instances."""
        for page in self.doc.pages:
            for elem in page.iter_elements():
                self.assertIsInstance(elem, OutlineElement)

    def test_iter_text(self) -> None:
        """iter_text() should yield RichText instances."""
        for page in self.doc.pages:
            for rt in page.iter_text():
                self.assertIsInstance(rt, RichText)

    def test_page_all_elements(self) -> None:
        """all_elements should provide a debugger-friendly recursive view."""
        for page in self.doc.pages:
            all_elems = page.all_elements
            self.assertIsInstance(all_elems, list)
            for elem in all_elems:
                self.assertIsInstance(elem, Element)


class TestTableContent(unittest.TestCase):
    """Test that table content is extracted correctly."""

    @classmethod
    def setUpClass(cls) -> None:
        path = _simpletable_path()
        if path is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.doc = Document.open(path)

    def test_simpletable_cell_values(self) -> None:
        """SimpleTable.one should have a table with expected cell texts."""
        page = self.doc.pages[0]
        tables = list(page.iter_tables())
        self.assertGreaterEqual(len(tables), 1)

        table = tables[0]
        self.assertEqual((table.row_count, table.column_count), (4, 3))

        grid = [[cell.text for cell in row.cells] for row in table.rows]
        expected = [
            ["1", "22", "3"],
            ["6", "5", "4"],
            ["7", "8", "9"],
            ["b", "a", "0"],
        ]
        self.assertEqual(grid, expected)


class TestFindPages(unittest.TestCase):
    """Test page search functionality."""

    @classmethod
    def setUpClass(cls) -> None:
        path = _simpletable_path()
        if path is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.doc = Document.open(path)

    def test_find_pages_empty(self) -> None:
        """find_pages() with no match should return empty list."""
        results = self.doc.find_pages("ZZZZNONEXISTENT")
        self.assertEqual(results, [])

    def test_find_pages_case_insensitive(self) -> None:
        """find_pages() should be case-insensitive by default."""
        if self.doc.pages and self.doc.pages[0].title:
            title = self.doc.pages[0].title
            results_lower = self.doc.find_pages(title.lower())
            results_upper = self.doc.find_pages(title.upper())
            self.assertEqual(len(results_lower), len(results_upper))


class TestImports(unittest.TestCase):
    """Test that all public API symbols are importable."""

    def test_import_all(self) -> None:
        """All __all__ symbols should be importable."""
        from onenote import (
            Document,
            Element,
            Page,
            Title,
            Outline,
            OutlineElement,
            RichText,
            Image,
            Table,
            TableRow,
            TableCell,
            AttachedFile,
        )
        self.assertIsNotNone(Document)
        self.assertIsNotNone(Element)
        self.assertIsNotNone(Page)
        self.assertIsNotNone(Title)
        self.assertIsNotNone(Outline)
        self.assertIsNotNone(OutlineElement)
        self.assertIsNotNone(RichText)
        self.assertIsNotNone(Image)
        self.assertIsNotNone(Table)
        self.assertIsNotNone(TableRow)
        self.assertIsNotNone(TableCell)
        self.assertIsNotNone(AttachedFile)


if __name__ == "__main__":
    unittest.main()
