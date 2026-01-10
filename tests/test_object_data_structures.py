import unittest

from onestore.errors import OneStoreFormatError
from onestore.io import BinaryReader
from onestore.object_data import (
    ObjectSpaceObjectStreamHeader,
    ObjectSpaceObjectStream,
    ObjectSpaceObjectPropSet,
    PropertyID,
    PropertySet,
    PrtFourBytesOfLengthFollowedByData,
    PrtArrayOfPropertyValues,
)
from onestore.parse_context import ParseContext


class TestObjectDataStructures(unittest.TestCase):
    def test_object_stream_header_bits(self) -> None:
        # count=3, reserved=0, extended=1, osidNotPresent=0
        raw = (3) | (0 << 24) | (1 << 30) | (0 << 31)
        h = ObjectSpaceObjectStreamHeader.from_u32(raw)
        self.assertEqual(h.count, 3)
        self.assertEqual(h.reserved, 0)
        self.assertTrue(h.extended_streams_present)
        self.assertFalse(h.osid_stream_not_present)

    def test_property_id_bits(self) -> None:
        # prop_id=0x123, type=0x11, bool=1
        raw = (0x123) | (0x11 << 26) | (1 << 31)
        p = PropertyID.from_u32(raw)
        self.assertEqual(p.prop_id, 0x123)
        self.assertEqual(p.prop_type, 0x11)
        self.assertTrue(p.bool_value)

    def test_property_set_structural_parse(self) -> None:
        # cProperties=1, one prid, rgData arbitrary
        c = (1).to_bytes(2, "little")
        prid = (0x01).to_bytes(4, "little")
        rgdata = b"abcd"
        ps = PropertySet.parse_from_tail(BinaryReader(c + prid + rgdata), ctx=ParseContext(strict=True))
        self.assertEqual(ps.c_properties, 1)
        self.assertEqual(len(ps.rg_prids), 1)
        self.assertEqual(ps.rg_data, rgdata)

    def test_prt_four_bytes_length_followed_by_data(self) -> None:
        b = (3).to_bytes(4, "little") + b"xyz"
        out = PrtFourBytesOfLengthFollowedByData.parse(BinaryReader(b), ctx=ParseContext(strict=True))
        self.assertEqual(out.cb, 3)
        self.assertEqual(out.data, b"xyz")

    def test_prt_array_of_property_values_structural(self) -> None:
        # c=2, prid(type=0x11), raw payload
        prid_raw = (0x11 << 26)
        b = (2).to_bytes(4, "little") + prid_raw.to_bytes(4, "little") + b"payload"
        out = PrtArrayOfPropertyValues.parse(BinaryReader(b), ctx=ParseContext(strict=True))
        self.assertEqual(out.c_properties, 2)
        self.assertIsNotNone(out.prid)
        assert out.prid is not None
        self.assertEqual(out.prid.prop_type, 0x11)
        self.assertEqual(out.raw_data, b"payload")

    def test_object_prop_set_inconsistent_header_strict_fails(self) -> None:
        # OIDs header: count=0, reserved=0, extended=1, osidNotPresent=1 => inconsistent
        raw = (0) | (0 << 24) | (1 << 30) | (1 << 31)
        b = raw.to_bytes(4, "little")
        # PropertySet tail (minimal): cProperties=0
        b += (0).to_bytes(2, "little")
        with self.assertRaises(OneStoreFormatError):
            ObjectSpaceObjectPropSet.parse(BinaryReader(b), ctx=ParseContext(strict=True))

    def test_object_stream_body_bounds(self) -> None:
        # count=1 but no body
        raw = (1).to_bytes(4, "little")
        with self.assertRaises(OneStoreFormatError):
            ObjectSpaceObjectStream.parse(BinaryReader(raw), ctx=ParseContext(strict=True))
