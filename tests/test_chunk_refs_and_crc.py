import struct
import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.onestore.chunk_refs import (  # noqa: E402
    FileChunkReference32,
    FileChunkReference64,
    FileChunkReference64x32,
    parse_filenode_chunk_reference,
)
from aspose.note._internal.onestore.crc import crc32_rfc3309  # noqa: E402
from aspose.note._internal.onestore.errors import OneStoreFormatError  # noqa: E402
from aspose.note._internal.onestore.io import BinaryReader  # noqa: E402


class TestChunkRefsAndCrc(unittest.TestCase):
    def test_fcr_nil_and_zero(self) -> None:
        fcr0 = FileChunkReference32(stp=0, cb=0)
        self.assertTrue(fcr0.is_zero())
        self.assertFalse(fcr0.is_nil())

        fcrn = FileChunkReference32(stp=0xFFFFFFFF, cb=0)
        self.assertTrue(fcrn.is_nil())
        self.assertFalse(fcrn.is_zero())

    def test_fcr_validate_in_file_bounds(self) -> None:
        fcr = FileChunkReference64x32(stp=100, cb=20)
        fcr.validate_in_file(200)
        with self.assertRaises(OneStoreFormatError):
            fcr.validate_in_file(110)

    def test_parse_filenode_chunk_reference_formats(self) -> None:
        # stp_format=2 => u16 compressed (x8), cb_format=2 => u8 compressed (x8)
        data = struct.pack("<HB", 5, 7)  # raw_stp=5 -> stp=40, raw_cb=7 -> cb=56
        r = BinaryReader(data)
        ref = parse_filenode_chunk_reference(r, stp_format=2, cb_format=2)
        self.assertEqual(ref.raw_stp, 5)
        self.assertEqual(ref.stp, 40)
        self.assertEqual(ref.raw_cb, 7)
        self.assertEqual(ref.cb, 56)
        self.assertEqual(r.remaining(), 0)

    def test_filechunkreference_parse_sizes(self) -> None:
        data32 = struct.pack("<II", 1, 2)
        f32 = FileChunkReference32.parse(BinaryReader(data32))
        self.assertEqual((f32.stp, f32.cb), (1, 2))

        data64 = struct.pack("<QQ", 3, 4)
        f64 = FileChunkReference64.parse(BinaryReader(data64))
        self.assertEqual((f64.stp, f64.cb), (3, 4))

    def test_crc32_rfc3309_vectors(self) -> None:
        self.assertEqual(crc32_rfc3309(b""), 0x00000000)
        self.assertEqual(crc32_rfc3309(b"123456789"), 0xCBF43926)
