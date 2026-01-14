"""Integration test: rich text formatting and hyperlinks.

Uses FormattedRichText.one fixture, which contains a single RichText paragraph with
multiple formatting runs and a hyperlink.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.onenote import Document, RichText  # noqa: E402


def _fixture_path() -> Path | None:
    p = ROOT / "testfiles" / "FormattedRichText.one"
    return p if p.exists() else None


class TestFormattedRichText(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path()
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.doc = Document.open(p)

    def _first_richtext(self) -> RichText:
        for page in self.doc.pages:
            for rt in page.iter_text():
                return rt
        raise AssertionError("No RichText found in document")

    def test_text_content(self) -> None:
        rt = self._first_richtext()
        self.assertIsInstance(rt.text, str)
        self.assertIn("www.google.com", rt.text)
        self.assertTrue(rt.text.endswith("not a hyperlink."))

    def test_runs_cover_text(self) -> None:
        rt = self._first_richtext()
        self.assertGreater(len(rt.runs), 0)

        # Runs should cover [0, len(text)) and be monotonic.
        self.assertEqual(rt.runs[0].start, 0)
        self.assertEqual(rt.runs[-1].end, len(rt.text))

        prev_end = 0
        for run in rt.runs:
            self.assertGreaterEqual(run.start, prev_end)
            self.assertGreater(run.end, run.start)
            self.assertLessEqual(run.end, len(rt.text))
            prev_end = run.end

        # Concatenating run slices should reconstruct the full text.
        rebuilt = "".join(rt.text[r.start : r.end] for r in rt.runs)
        self.assertEqual(rebuilt, rt.text)

    def test_has_hyperlink_run(self) -> None:
        rt = self._first_richtext()
        urls = [r.style.hyperlink for r in rt.runs if r.style.hyperlink]
        self.assertTrue(urls)
        self.assertTrue(any("google.com" in u for u in urls if u))

    def test_has_multiple_styles(self) -> None:
        rt = self._first_richtext()
        sigs = {
            (
                r.style.bold,
                r.style.italic,
                r.style.underline,
                r.style.strikethrough,
                r.style.superscript,
                r.style.subscript,
                r.style.font_name,
                r.style.font_size_pt,
                r.style.font_color,
                r.style.highlight_color,
                r.style.hyperlink,
            )
            for r in rt.runs
        }
        # Expect at least two distinct styles across the paragraph.
        self.assertGreater(len(sigs), 1)
