import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onenote import Document  # noqa: E402
from onenote.elements import OutlineElement  # noqa: E402


def _fixture_path() -> Path | None:
    p = ROOT / "testfiles" / "NumberedListWithTags.one"
    return p if p.exists() else None


class TestOneNoteNumberedLists(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = _fixture_path()
        if cls.path is None:
            raise unittest.SkipTest("NumberedListWithTags.one not found")
        cls.data = cls.path.read_bytes()

    def test_parse_does_not_crash(self) -> None:
        doc = Document.from_bytes(self.data, strict=True)
        self.assertGreaterEqual(len(doc.pages), 1)

    def test_outline_elements_expose_numbered_list_metadata(self) -> None:
        doc = Document.from_bytes(self.data, strict=True)

        elems: list[OutlineElement] = []
        for page in doc.pages:
            elems.extend(list(page.iter_elements()))

        self.assertGreaterEqual(len(elems), 1)

        numbered = [e for e in elems if getattr(e, "is_numbered", False)]
        self.assertGreaterEqual(len(numbered), 1)

        # For numbered items we expect list_format to be present and contain U+FFFD.
        for e in numbered:
            self.assertIsNotNone(e.list_format)
            self.assertIn("\uFFFD", e.list_format or "")
            if e.list_restart is not None:
                self.assertIsInstance(e.list_restart, int)
