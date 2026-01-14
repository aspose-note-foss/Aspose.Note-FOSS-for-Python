import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.ms_one import parse_section_file_with_page_history  # noqa: E402
from aspose.note._internal.ms_one.entities.base import BaseNode  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import Page as MsPage  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import RichText as MsRichText  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import Section as MsSection  # noqa: E402


def _fixture_path() -> Path | None:
    p = ROOT / "testfiles" / "SimpleHistory.one"
    return p if p.exists() else None


def _iter_nodes(root: BaseNode):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        for attr in ("children", "content_children"):
            kids = getattr(n, attr, None)
            if kids:
                stack.extend(reversed(list(kids)))


def _page_texts(page: MsPage) -> list[str]:
    texts: list[str] = []
    for n in _iter_nodes(page):
        if isinstance(n, MsRichText) and n.text is not None:
            t = n.text.strip()
            if t:
                texts.append(t)
    return texts


class TestSimpleHistoryPageHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path()
        if p is None:
            raise unittest.SkipTest("SimpleHistory.one not found")
        cls.path = p
        cls.data = p.read_bytes()

    def test_ms_one_page_history_exposes_three_previous_revisions(self) -> None:
        section = parse_section_file_with_page_history(self.data, strict=True)
        self.assertIsInstance(section, MsSection)

        pages = [n for n in _iter_nodes(section) if isinstance(n, MsPage)]
        self.assertEqual(len(pages), 1, "Expected exactly one page in SimpleHistory.one")

        page = pages[0]
        self.assertEqual(_page_texts(page), ["Third text"])

        self.assertTrue(hasattr(page, "history"), "Page.history must exist in public MS-ONE API")
        self.assertEqual(len(page.history), 3, "Expected 3 previous revisions")

        # Newest-to-oldest previous revisions
        self.assertEqual(_page_texts(page.history[0]), ["Second text"])
        self.assertEqual(_page_texts(page.history[1]), ["First text"])
        self.assertEqual(_page_texts(page.history[2]), [])
