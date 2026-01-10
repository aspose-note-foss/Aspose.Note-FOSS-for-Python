import struct
import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onestore.common_types import CompactID, ExtendedGUID, StringInStorageBuffer  # noqa: E402
from onestore.io import BinaryReader  # noqa: E402


class TestCommonTypes(unittest.TestCase):
    def test_compact_id_unpack(self) -> None:
        # n=0x12, guid_index=0x345678
        value = (0x345678 << 8) | 0x12
        cid = CompactID.from_u32(value)
        self.assertEqual(cid.n, 0x12)
        self.assertEqual(cid.guid_index, 0x345678)

    def test_extended_guid_parse_and_uuid_roundtrip(self) -> None:
        # bytes_le for UUID 00112233-4455-6677-8899-aabbccddeeff
        guid_le = bytes.fromhex("33221100554477668899aabbccddeeff")
        data = guid_le + struct.pack("<I", 7)
        eg = ExtendedGUID.parse(BinaryReader(data))
        self.assertEqual(eg.n, 7)
        self.assertEqual(eg.as_str(), "00112233-4455-6677-8899-aabbccddeeff")

    def test_string_in_storage_buffer_keeps_trailing_null(self) -> None:
        s = "Hi\x00"
        raw = s.encode("utf-16le")
        data = struct.pack("<I", len(s)) + raw
        sib = StringInStorageBuffer.parse(BinaryReader(data))
        self.assertEqual(sib.cch, len(s))
        self.assertEqual(sib.decode(), s)
        self.assertEqual(sib.decode_trim_trailing_null(), "Hi")
