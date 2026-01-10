import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onestore.errors import OneStoreFormatError  # noqa: E402
from onestore.io import BinaryReader  # noqa: E402


class TestBinaryReader(unittest.TestCase):
    def test_read_primitives_le(self) -> None:
        data = bytes(
            [
                0x01,
                0x02,
                0x00,
                0x04,
                0x03,
                0x02,
                0x01,
                0x08,
                0x07,
                0x06,
                0x05,
                0x04,
                0x03,
                0x02,
                0x01,
            ]
        )
        r = BinaryReader(data)
        self.assertEqual(r.read_u8(), 0x01)
        self.assertEqual(r.read_u16(), 0x0002)
        self.assertEqual(r.read_u32(), 0x01020304)
        self.assertEqual(r.read_u64(), 0x0102030405060708)

    def test_view_bounds_enforced(self) -> None:
        r = BinaryReader(b"abcdef")
        v = r.view(1, 3)  # "bcd"
        self.assertEqual(v.read_bytes(3), b"bcd")
        with self.assertRaises(OneStoreFormatError):
            v.read_u8()

    def test_view_out_of_bounds_fails(self) -> None:
        r = BinaryReader(b"abcdef")
        with self.assertRaises(OneStoreFormatError):
            r.view(4, 3)

    def test_unpack_bits_lsb_first(self) -> None:
        # value = 0xAABBCCDD -> low 8 bits DD, next 24 bits AABBCC
        parts = BinaryReader.unpack_bits(0xAABBCCDD, [8, 24])
        self.assertEqual(parts, (0xDD, 0xAABBCC))

    def test_read_out_of_bounds_reports_offset(self) -> None:
        r = BinaryReader(b"\x00\x01")
        r.read_u16()
        with self.assertRaises(OneStoreFormatError) as ex:
            r.read_u8()
        self.assertEqual(ex.exception.offset, 2)
