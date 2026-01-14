import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.ms_one.reader import parse_section_file  # noqa: E402
from aspose.note._internal.ms_one.entities.base import BaseNode  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import Page, Section  # noqa: E402


def _simpletable_path() -> Path | None:
    p = ROOT / "testfiles" / "SimpleTable.one"
    return p if p.exists() else None


def _iter_nodes(root: BaseNode):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        # Generic children fields on various nodes
        for attr in ("children", "content_children"):
            kids = getattr(n, attr, None)
            if kids:
                stack.extend(reversed(list(kids)))


def _summary(section: Section) -> dict:
    pages: list[dict] = []
    for n in _iter_nodes(section):
        if isinstance(n, Page):
            pages.append({"oid": n.oid.as_str() + f":{int(n.oid.n)}", "title": n.title})

    return {
        "section": {
            "oid": section.oid.as_str() + f":{int(section.oid.n)}",
            "displayName": section.display_name,
        },
        "pageCount": len(pages),
        "pages": pages,
    }


class TestMSOneSimpleTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.simpletable = _simpletable_path()
        if cls.simpletable is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.data = cls.simpletable.read_bytes()

    def test_parse_does_not_crash(self) -> None:
        section = parse_section_file(self.data, strict=True)
        self.assertIsInstance(section, Section)

    def test_extracts_some_pages(self) -> None:
        section = parse_section_file(self.data, strict=True)
        s = _summary(section)
        self.assertGreaterEqual(s["pageCount"], 1)

    def test_snapshot_is_deterministic(self) -> None:
        snap_path = ROOT / "tests" / "snapshots" / "ms_one_simpletable.json"
        if not snap_path.exists():
            raise unittest.SkipTest("Snapshot file missing: tests/snapshots/ms_one_simpletable.json")

        a = _summary(parse_section_file(self.data, strict=True))
        b = _summary(parse_section_file(self.data, strict=True))
        self.assertEqual(a, b)

        expected = json.loads(snap_path.read_text(encoding="utf-8"))
        self.assertEqual(a, expected)
