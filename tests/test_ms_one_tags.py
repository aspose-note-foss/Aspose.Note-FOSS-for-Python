import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.ms_one.reader import parse_section_file  # noqa: E402
from aspose.note._internal.ms_one.entities.base import BaseNode  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import EmbeddedFile, RichText, Section, Table  # noqa: E402


def _tagsizes_path() -> Path | None:
    p = ROOT / "testfiles" / "TagSizes.one"
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


class TestMSOneTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tagsizes = _tagsizes_path()
        if cls.tagsizes is None:
            raise unittest.SkipTest("TagSizes.one not found")
        cls.data = cls.tagsizes.read_bytes()

    def test_parse_does_not_crash(self) -> None:
        section = parse_section_file(self.data, strict=True)
        self.assertIsInstance(section, Section)

    def test_extracts_note_tags_with_font_sizes(self) -> None:
        section = parse_section_file(self.data, strict=True)

        expected = {
            "66(6-9)": 6.0,
            "10(10-17)": 10.0,
            "18(18-23)": 18.0,
            "24(24-…)": 24.0,
        }

        by_text: dict[str, RichText] = {}
        for n in _iter_nodes(section):
            if isinstance(n, RichText) and n.text in expected:
                by_text[n.text] = n

        self.assertEqual(set(by_text.keys()), set(expected.keys()))

        for text, size_pt in expected.items():
            rt = by_text[text]
            self.assertIsNotNone(rt.font_size_pt)
            self.assertAlmostEqual(float(rt.font_size_pt or 0.0), size_pt, places=3)

            self.assertEqual(len(rt.tags), 1)
            tag = rt.tags[0]
            # Important tag (as shown in the fixture, Russian locale)
            self.assertEqual(tag.label, "Важно")
            self.assertEqual(tag.shape, 13)

    def test_table_with_tag(self) -> None:
        p = ROOT / "testfiles" / "TableWithTag.one"
        if not p.exists():
            raise unittest.SkipTest("TableWithTag.one not found")

        section = parse_section_file(p.read_bytes(), strict=True)
        tables = [n for n in _iter_nodes(section) if isinstance(n, Table)]
        self.assertGreaterEqual(len(tables), 1)

        tagged = [t for t in tables if t.tags]
        self.assertEqual(len(tagged), 1)
        self.assertEqual(len(tagged[0].tags), 1)
        self.assertEqual(tagged[0].tags[0].label, "Дела")
        self.assertEqual(tagged[0].tags[0].shape, 3)

    def test_attached_file_with_tag(self) -> None:
        p = ROOT / "testfiles" / "AttachedFileWithTag.one"
        if not p.exists():
            raise unittest.SkipTest("AttachedFileWithTag.one not found")

        section = parse_section_file(p.read_bytes(), strict=True)

        files = [n for n in _iter_nodes(section) if isinstance(n, EmbeddedFile)]
        self.assertGreaterEqual(len(files), 1)
        tagged = [f for f in files if f.tags]
        self.assertEqual(len(tagged), 1)
        labels = {t.label for t in tagged[0].tags}
        self.assertIn("Дела", labels)
        self.assertIn("Важно", labels)

        by_label = {t.label: t for t in tagged[0].tags if t.label is not None}
        self.assertEqual(by_label["Дела"].shape, 3)
        self.assertEqual(by_label["Важно"].shape, 13)

    def test_image_with_tag_exposes_embedded_object(self) -> None:
        p = ROOT / "testfiles" / "ImageWithTag.one"
        if not p.exists():
            raise unittest.SkipTest("ImageWithTag.one not found")

        section = parse_section_file(p.read_bytes(), strict=True)
        files = [n for n in _iter_nodes(section) if isinstance(n, EmbeddedFile)]
        # The fixture stores the image as an embedded file object.
        self.assertGreaterEqual(len(files), 1)

        tagged = [f for f in files if f.tags]
        self.assertEqual(len(tagged), 1)
        self.assertEqual(tagged[0].original_filename, "TestOneNoteSaveAsTiffByFormat.tiff")
        self.assertEqual(len(tagged[0].tags), 1)
        self.assertEqual(tagged[0].tags[0].label, "Дела")
        self.assertEqual(tagged[0].tags[0].shape, 3)
