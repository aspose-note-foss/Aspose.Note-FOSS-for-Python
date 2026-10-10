from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.ms_one.loader import _decode_ascii_text  # noqa: E402


class TestDecodeAsciiText(unittest.TestCase):
    """Covers TextExtendedAscii decoding (cp1252 for Windows single-byte text)."""

    def test_decodes_cp1252_umlauts(self) -> None:
        # Previously UTF-8-with-ignore silently dropped these high bytes.
        self.assertEqual(_decode_ascii_text(b"caf\xe9 \xc4\xf6\xfc\xdf"), "caf\u00e9 \u00c4\u00f6\u00fc\u00df")

    def test_decodes_cp1252_typography(self) -> None:
        # Smart quotes, em-dash and euro sign live in the 0x80-0x9F range that
        # latin-1 would turn into control characters.
        self.assertEqual(_decode_ascii_text(b"\x93x\x94 \x97 \x80"), "\u201cx\u201d \u2014 \u20ac")

    def test_prefers_genuine_utf8(self) -> None:
        # Valid UTF-8 is still decoded as UTF-8 (not mojibaked through cp1252).
        self.assertEqual(_decode_ascii_text("caf\u00e9".encode("utf-8")), "caf\u00e9")

    def test_strips_trailing_nul(self) -> None:
        self.assertEqual(_decode_ascii_text(b"caf\xe9\x00"), "caf\u00e9")

    def test_empty_bytes_returns_none(self) -> None:
        self.assertIsNone(_decode_ascii_text(b""))

    def test_none_returns_none(self) -> None:
        self.assertIsNone(_decode_ascii_text(None))

    def test_str_passthrough(self) -> None:
        self.assertEqual(_decode_ascii_text("hello"), "hello")


if __name__ == "__main__":
    unittest.main()
