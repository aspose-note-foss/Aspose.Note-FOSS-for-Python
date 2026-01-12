from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from aspose.note.enums import SaveFormat

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _fixture_path(name: str) -> Path | None:
    p = ROOT / "testfiles" / name
    return p if p.exists() else None


class TestAsposeNoteDocumentBasics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.path = p
        cls.data = p.read_bytes()

    def test_construct_from_path(self) -> None:
        from aspose.note import Document

        doc = Document(self.path)
        self.assertGreater(doc.Count(), 0)
        self.assertIsNotNone(doc.FirstChild)
        self.assertIsNotNone(doc.LastChild)

    def test_construct_from_stream(self) -> None:
        from aspose.note import Document

        doc = Document(io.BytesIO(self.data))
        self.assertGreater(doc.Count(), 0)

    def test_document_file_format_enum(self) -> None:
        from aspose.note import Document, FileFormat

        doc = Document(self.path)
        self.assertIsInstance(doc.FileFormat, FileFormat)

    def test_get_child_nodes_page_and_title(self) -> None:
        from aspose.note import Document, Page, Title

        doc = Document(self.path)
        pages = doc.GetChildNodes(Page)
        self.assertGreaterEqual(len(pages), 1)

        titles = doc.GetChildNodes(Title)
        # Each page should have a Title node.
        self.assertGreaterEqual(len(titles), len(pages))

        # Page.Title property should match first Title in its children.
        page0 = pages[0]
        self.assertIsNotNone(page0.Title)
        self.assertIs(page0.FirstChild, page0.Title)


class TestAsposeNoteRichTextOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.path = p

    def test_richtext_replace_changes_text(self) -> None:
        from aspose.note import Document, RichText

        doc = Document(self.path)
        rts = doc.GetChildNodes(RichText)
        self.assertGreater(len(rts), 0)

        # Pick a non-empty node with a replaceable substring.
        target = None
        for rt in rts:
            if rt.Text and " " in rt.Text:
                target = rt
                break
        if target is None:
            raise unittest.SkipTest("No RichText nodes with replaceable content found")

        before = target.Text
        target.Replace(" ", "  ")
        after = target.Text
        self.assertNotEqual(before, after)
        doc.Save("FormattedRichText.pdf", SaveFormat.Pdf)


class TestAsposeNoteVisitor(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("SimpleTable.one")
        if p is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.path = p

    def test_accept_visits_document_and_pages(self) -> None:
        from aspose.note import Document, DocumentVisitor, Page

        class CountingVisitor(DocumentVisitor):
            def __init__(self) -> None:
                self.pages = 0
                self.doc_start = 0

            def VisitDocumentStart(self, document):  # noqa: N802
                self.doc_start += 1

            def VisitPageStart(self, page: Page):  # noqa: N802
                self.pages += 1

        doc = Document(self.path)
        v = CountingVisitor()
        doc.Accept(v)

        self.assertEqual(v.doc_start, 1)
        self.assertGreaterEqual(v.pages, 1)
