from __future__ import annotations

import struct
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.onestore import parser  # noqa: E402

# Object blob header with oid_count=0 and the no_osid_stream flag (bit 31) set,
# so parsing jumps straight to the property set.
_BLOB_HEADER = struct.pack("<I", 0x80000000)


def _uint32_property(property_id: int) -> int:
    # Property id carrying an inline uint32 value (property type 0x5 in bits 26-30).
    return (0x5 << 26) | property_id


class TestParserTruncationRegression(unittest.TestCase):
    """Regression tests for GitHub issue #4 (out-of-bounds reads on corrupt files)."""

    def test_read_guid_zero_pads_truncated_payload(self) -> None:
        payload = struct.pack("<I", 0) + b"\x11\x22\x33"  # only 3 of 16 GUID bytes
        result = parser._read_guid(payload, 4)
        self.assertEqual(result, str(uuid.UUID(bytes_le=b"\x11\x22\x33" + b"\x00" * 13)))

    def test_read_guid_preserves_full_payload(self) -> None:
        guid_bytes = bytes(range(16))
        payload = struct.pack("<I", 0) + guid_bytes
        self.assertEqual(parser._read_guid(payload, 4), str(uuid.UUID(bytes_le=guid_bytes)))

    def test_parse_object_blob_handles_truncated_array_count(self) -> None:
        # One property of type 0x9 (ObjectIDArray) whose 4-byte count sits exactly
        # at the end of the buffer -> previously raised struct.error.
        blob = _BLOB_HEADER + struct.pack("<H", 1) + struct.pack("<I", 0x24000001)
        properties, raw_properties = parser._parse_object_blob(blob, {})
        self.assertEqual(properties, {})
        self.assertEqual(raw_properties, [])

    def test_parse_object_blob_keeps_properties_before_truncation(self) -> None:
        blob = (
            _BLOB_HEADER
            + struct.pack("<H", 2)
            + struct.pack("<I", _uint32_property(0x1C01))  # PageWidth
            + struct.pack("<I", _uint32_property(0x1C02))  # PageHeight
            + struct.pack("<I", 42)  # complete value for PageWidth
            + struct.pack("<H", 7)  # truncated value for PageHeight (2 of 4 bytes)
        )
        properties, raw_properties = parser._parse_object_blob(blob, {})
        self.assertEqual(properties, {"PageWidth": 42})
        self.assertEqual(raw_properties, [("PageWidth", 42)])

    def test_parse_object_blob_clamps_overlong_property_count(self) -> None:
        # Declares 1000 properties but carries no property ids at all.
        blob = _BLOB_HEADER + struct.pack("<H", 1000)
        properties, raw_properties = parser._parse_object_blob(blob, {})
        self.assertEqual(properties, {})
        self.assertEqual(raw_properties, [])


if __name__ == "__main__":
    unittest.main()
