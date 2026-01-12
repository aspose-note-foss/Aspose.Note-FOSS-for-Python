from __future__ import annotations

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


class TestAsposeNoteRichTextFormatting(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.path = p

    def test_richtext_runs_preserved(self) -> None:
        from aspose.note import Document, RichText

        doc = Document(self.path)
        rts = doc.GetChildNodes(RichText)
        self.assertGreater(len(rts), 0)

        # At least one RichText node should carry extracted formatting runs.
        self.assertTrue(any(len(rt.Runs) > 0 for rt in rts))

    def test_richtext_has_some_non_default_style(self) -> None:
        from aspose.note import Document, RichText

        doc = Document(self.path)
        rts = doc.GetChildNodes(RichText)

        # Look for any run with a meaningful style attribute.
        def is_styled(rt: RichText) -> bool:
            for run in rt.Runs:
                s = run.Style
                if (
                    s.Bold
                    or s.Italic
                    or s.Underline
                    or s.Strikethrough
                    or s.Superscript
                    or s.Subscript
                    or (s.FontName is not None)
                    or (s.FontSize is not None)
                    or (s.FontColor is not None)
                    or (s.HighlightColor is not None)
                    or (s.HyperlinkAddress is not None)
                ):
                    return True
            return False

        if not any(rt.Runs for rt in rts):
            raise unittest.SkipTest("No RichText nodes with runs extracted")

        self.assertTrue(any(is_styled(rt) for rt in rts))
