from __future__ import annotations

import sys
import unittest
import io
from pathlib import Path

from aspose.note.enums import SaveFormat

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _fixture_path(name: str) -> Path | None:
    p = ROOT / "testfiles" / name
    return p if p.exists() else None


def _tag_is_meaningful(tag) -> bool:
    return bool(getattr(tag, "label", None)) or (getattr(tag, "shape", None) is not None)


def _collect_all_tags(doc):
    from aspose.note import AttachedFile, Image, OutlineElement, RichText, Table

    tags = []
    for rt in doc.GetChildNodes(RichText):
        tags.extend(getattr(rt, "Tags", None) or [])
    for img in doc.GetChildNodes(Image):
        tags.extend(getattr(img, "Tags", None) or [])
    for tbl in doc.GetChildNodes(Table):
        tags.extend(getattr(tbl, "Tags", None) or [])
    for oe in doc.GetChildNodes(OutlineElement):
        tags.extend(getattr(oe, "Tags", None) or [])
    for af in doc.GetChildNodes(AttachedFile):
        tags.extend(getattr(af, "Tags", None) or [])
    return tags


def _rt_text_and_labels(node) -> tuple[str, set[str]]:
    """Return first RichText.Text under node and the set of tag labels on that RichText."""
    from aspose.note import RichText

    rts = node.GetChildNodes(RichText)
    if not rts:
        return "", set()
    rt = rts[0]
    labels = {getattr(t, "label", None) for t in (getattr(rt, "Tags", None) or [])}
    labels.discard(None)
    return getattr(rt, "Text", "") or "", labels


class TestAsposeNoteTags(unittest.TestCase):
    def test_image_with_tag_exposes_tags(self) -> None:
        p = _fixture_path("ImageWithTag.one")
        if p is None:
            raise unittest.SkipTest("ImageWithTag.one not found")

        from aspose.note import Document, Image

        doc = Document(p)
        images = doc.GetChildNodes(Image)
        self.assertGreaterEqual(len(images), 1)

        tagged = [img for img in images if getattr(img, "Tags", None)]
        self.assertGreaterEqual(len(tagged), 1)
        self.assertTrue(any(_tag_is_meaningful(t) for img in tagged for t in img.Tags))

    def test_table_with_tag_exposes_tags(self) -> None:
        p = _fixture_path("TableWithTag.one")
        if p is None:
            raise unittest.SkipTest("TableWithTag.one not found")

        from aspose.note import Document, Table

        doc = Document(p)
        tables = doc.GetChildNodes(Table)
        self.assertGreaterEqual(len(tables), 1)

        tagged = [t for t in tables if getattr(t, "Tags", None)]
        self.assertGreaterEqual(len(tagged), 1)
        self.assertTrue(any(_tag_is_meaningful(tag) for t in tagged for tag in t.Tags))

    def test_richtext_tags_exposed(self) -> None:
        p = _fixture_path("TagSizes.one")
        if p is None:
            raise unittest.SkipTest("TagSizes.one not found")

        from aspose.note import Document, OutlineElement, RichText

        doc = Document(p)
        rts = doc.GetChildNodes(RichText)
        self.assertGreaterEqual(len(rts), 1)

        tagged = [rt for rt in rts if getattr(rt, "Tags", None)]
        self.assertGreaterEqual(len(tagged), 1)
        self.assertTrue(any(_tag_is_meaningful(tag) for rt in tagged for tag in rt.Tags))

        # Concrete texts from the numbered list shown in the fixture UI.
        oes = doc.GetChildNodes(OutlineElement)
        oe_texts = [_rt_text_and_labels(oe)[0] for oe in oes]
        oe_texts = [t for t in oe_texts if t]
        self.assertGreaterEqual(len(oe_texts), 4)
        self.assertIn("66(6-9)", oe_texts)
        self.assertIn("10(10-17)", oe_texts)
        self.assertIn("18(18-23)", oe_texts)
        self.assertTrue(any(t in {"24(24-…)", "24(242-…)"} for t in oe_texts))

        # Each of these list items is expected to carry the "Важно" tag.
        for expected_text in ("66(6-9)", "10(10-17)", "18(18-23)"):
            oe = next(o for o in oes if _rt_text_and_labels(o)[0] == expected_text)
            _, labels = _rt_text_and_labels(oe)
            self.assertIn("Важно", labels)

        # For the last one, accept both variants but still require the tag.
        oe_last = next(o for o in oes if _rt_text_and_labels(o)[0] in {"24(24-…)", "24(242-…)"})
        _, labels_last = _rt_text_and_labels(oe_last)
        self.assertIn("Важно", labels_last)

    def test_outline_element_tags_and_list_metadata(self) -> None:
        p = _fixture_path("NumberedListWithTags.one")
        if p is None:
            raise unittest.SkipTest("NumberedListWithTags.one not found")

        from aspose.note import Document, Outline, OutlineElement, RichText

        doc = Document(p)

        # This fixture is expected to contain two Outline blocks.
        outlines = doc.GetChildNodes(Outline)
        self.assertEqual(len(outlines), 2)

        # The page also contains a TagSizes-style numbered list (as shown in the fixture UI).
        tag_sizes_outline = next(
            (o for o in outlines if any(rt.Text == "66(6-9)" for rt in o.GetChildNodes(RichText))),
            None,
        )
        self.assertIsNotNone(tag_sizes_outline)

        oes_tag_sizes = tag_sizes_outline.GetChildNodes(OutlineElement)  # type: ignore[union-attr]
        tag_sizes_map = {
            _rt_text_and_labels(oe)[0]: _rt_text_and_labels(oe)[1]
            for oe in oes_tag_sizes
            if _rt_text_and_labels(oe)[0]
        }
        self.assertIn("66(6-9)", tag_sizes_map)
        self.assertIn("10(10-17)", tag_sizes_map)
        self.assertIn("18(18-23)", tag_sizes_map)
        self.assertTrue(any(t in {"24(24-…)", "24(242-…)"} for t in tag_sizes_map))
        for t in ("66(6-9)", "10(10-17)", "18(18-23)"):
            self.assertIn("Важно", tag_sizes_map[t])
        last_key = next(k for k in tag_sizes_map if k in {"24(24-…)", "24(242-…)"})
        self.assertIn("Важно", tag_sizes_map[last_key])

        # Find the outline that contains the "First"/"Second" numbered list.
        # (The TagSizes-style list is also numbered, so we cannot select by NumberList presence alone.)
        list_outline = next(
            (o for o in outlines if any(rt.Text == "First" for rt in o.GetChildNodes(RichText))),
            None,
        )
        self.assertIsNotNone(list_outline)

        # This outline should contain two top-level list groups (as shown in the fixture UI).
        top_level = [c for c in list_outline if isinstance(c, OutlineElement)]  # type: ignore[union-attr]
        self.assertEqual(len(top_level), 2)

        # Verify concrete texts and concrete tag labels per top-level list group.
        text0, labels0 = _rt_text_and_labels(top_level[0])
        text1, labels1 = _rt_text_and_labels(top_level[1])
        self.assertEqual(text0, "First")
        self.assertEqual(text1, "Second")
        self.assertIn("Важно", labels0)
        self.assertIn("Вопрос", labels0)
        self.assertIn("Запланировать собрание", labels1)

        # Verify some nested items inside the first group.
        nested = [c for c in top_level[0] if isinstance(c, OutlineElement)]
        self.assertGreaterEqual(len(nested), 3)
        nested_map = {(_rt_text_and_labels(oe)[0]): _rt_text_and_labels(oe)[1] for oe in nested}
        self.assertIn("First-first", nested_map)
        self.assertIn("Важно", nested_map["First-first"])
        self.assertIn("Вопрос", nested_map["First-first"])
        self.assertIn("First-second", nested_map)
        self.assertIn("Важно", nested_map["First-second"])
        self.assertIn("Вопрос", nested_map["First-second"])
        self.assertIn("First-third", nested_map)
        self.assertIn("Контакт", nested_map["First-third"])
        self.assertIn("Послушать музыку", nested_map["First-third"])
        self.assertIn("Запланировать собрание", nested_map["First-third"])

        # Each top-level item should have list metadata.
        self.assertTrue(all(getattr(oe, "NumberList", None) is not None for oe in top_level))

        # The list should contain multiple distinct list formats (e.g., numeric/alpha/roman across nesting).
        all_oes = list_outline.GetChildNodes(OutlineElement)  # type: ignore[union-attr]
        formats = {
            getattr(getattr(oe, "NumberList", None), "Format", None)
            for oe in all_oes
            if getattr(oe, "NumberList", None) is not None
        }
        formats.discard(None)
        self.assertGreaterEqual(len(formats), 2)

        # Tags may be attached to RichText/Image/etc, not necessarily OutlineElement.
        tags = _collect_all_tags(doc)
        self.assertGreaterEqual(len(tags), 1)
        self.assertTrue(any(_tag_is_meaningful(t) for t in tags))
        doc.Save("NumberedListWithTags.pdf", SaveFormat.Pdf)

    def test_attachment_with_tag_fixture_has_tags_somewhere(self) -> None:
        p = _fixture_path("AttachedFileWithTag.one")
        if p is None:
            raise unittest.SkipTest("AttachedFileWithTag.one not found")

        from aspose.note import AttachedFile, Document

        doc = Document(p)
        atts = doc.GetChildNodes(AttachedFile)
        self.assertGreaterEqual(len(atts), 1)

        # Strict: this fixture is expected to include note tags.
        tags = _collect_all_tags(doc)
        self.assertGreaterEqual(len(tags), 1)
        self.assertTrue(any(_tag_is_meaningful(t) for t in tags))

        # Prefer that tags are attached directly to the attachment node.
        self.assertTrue(any(getattr(a, "Tags", None) for a in atts))
