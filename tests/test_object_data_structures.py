import unittest

from onestore.common_types import CompactID
from onestore.errors import OneStoreFormatError
from onestore.io import BinaryReader
from onestore.object_data import (
    DecodedPropertySet,
    ObjectSpaceObjectStreamHeader,
    ObjectSpaceObjectStream,
    ObjectSpaceObjectPropSet,
    PropertyID,
    PropertySet,
    PrtFourBytesOfLengthFollowedByData,
    PrtArrayOfPropertyValues,
    decode_property_set,
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

    def test_decode_property_set_mixed_types_and_offsets(self) -> None:
        # Property sequence:
        # - bool (no rgData)
        # - fixed1
        # - fixed2
        # - four-bytes-length container
        # - oid
        # - oid array (len in rgData)
        # - nested property set
        # - prtArrayOfPropertyValues containing one property set

        def _prid(prop_id: int, prop_type: int, bool_value: int = 0) -> PropertyID:
            raw = (prop_id & 0x03FFFFFF) | ((prop_type & 0x1F) << 26) | ((bool_value & 1) << 31)
            return PropertyID.from_u32(raw)

        rg_prids = (
            _prid(1, 0x02, 1),
            _prid(2, 0x03),
            _prid(3, 0x04),
            _prid(4, 0x07),
            _prid(5, 0x08),
            _prid(6, 0x09),
            _prid(7, 0x11),
            _prid(8, 0x10),
        )

        fixed1 = b"\xAA"
        fixed2 = b"\x01\x02"
        blob = (3).to_bytes(4, "little") + b"xyz"  # 7 bytes total
        oid_array_len = (2).to_bytes(4, "little")

        # nested PropertySet: c=1, one prid (fixed4), and 4 bytes rgData
        nested_prid = _prid(9, 0x05)
        nested_bytes = (1).to_bytes(2, "little") + nested_prid.raw.to_bytes(4, "little") + b"\x10\x20\x30\x40"

        # prtArrayOfPropertyValues: c=1, elem prid (type=0x11), then one PropertySet element
        elem_prid_raw = (0x11 << 26)
        arr = (1).to_bytes(4, "little") + elem_prid_raw.to_bytes(4, "little") + nested_bytes

        rg_data = fixed1 + fixed2 + blob + oid_array_len + nested_bytes + arr

        ps = PropertySet(c_properties=len(rg_prids), rg_prids=rg_prids, rg_data=rg_data)

        # Three OIDs are consumed: one for type 0x08 and two for the array type 0x09.
        oids = (
            # CompactID values are little-endian u32: n=1, guidIndex=2 => 0x00000201
            # n=2, guidIndex=3 => 0x00000302
            # n=3, guidIndex=4 => 0x00000403
            # (These are synthetic; only structure matters.)
            CompactID.from_u32(0x00000201),
            CompactID.from_u32(0x00000302),
            CompactID.from_u32(0x00000403),
        )

        out = decode_property_set(ps, oids=oids, osids=None, context_ids=None, ctx=ParseContext(strict=True))
        self.assertIsInstance(out, DecodedPropertySet)
        self.assertEqual(out.c_properties, len(rg_prids))
        self.assertEqual(out.rgdata_size, len(rg_data))
        self.assertEqual(len(out.properties), len(rg_prids))

        # Offsets/lengths within rgData.
        self.assertEqual(out.properties[0].rgdata_offset, 0)
        self.assertEqual(out.properties[0].rgdata_length, 0)
        self.assertEqual(out.properties[0].value, True)

        self.assertEqual(out.properties[1].rgdata_offset, 0)
        self.assertEqual(out.properties[1].rgdata_length, 1)
        self.assertEqual(out.properties[1].value, fixed1)

        self.assertEqual(out.properties[2].rgdata_offset, 1)
        self.assertEqual(out.properties[2].rgdata_length, 2)
        self.assertEqual(out.properties[2].value, fixed2)

        self.assertEqual(out.properties[3].rgdata_offset, 3)
        self.assertEqual(out.properties[3].rgdata_length, 7)
        self.assertEqual(out.properties[3].value, b"xyz")

        # OID single does not consume rgData
        self.assertEqual(out.properties[4].rgdata_offset, 10)
        self.assertEqual(out.properties[4].rgdata_length, 0)

        # OID array consumes only the u32 count from rgData
        self.assertEqual(out.properties[5].rgdata_offset, 10)
        self.assertEqual(out.properties[5].rgdata_length, 4)
        self.assertEqual(len(out.properties[5].value), 2)

        # Nested PropertySet consumes its whole encoding.
        self.assertEqual(out.properties[6].rgdata_offset, 14)
        self.assertEqual(out.properties[6].rgdata_length, len(nested_bytes))

        # prtArrayOfPropertyValues consumes (4+4+len(nested_bytes)).
        self.assertEqual(out.properties[7].rgdata_offset, 14 + len(nested_bytes))
        self.assertEqual(out.properties[7].rgdata_length, 8 + len(nested_bytes))

    def test_decode_property_set_oob_fails(self) -> None:
        # One fixed8 property but only 4 bytes in rgData
        prid = PropertyID.from_u32((1) | (0x06 << 26))
        ps = PropertySet(c_properties=1, rg_prids=(prid,), rg_data=b"\x00\x00\x00\x00")
        with self.assertRaises(OneStoreFormatError):
            decode_property_set(ps, oids=(), osids=None, context_ids=None, ctx=ParseContext(strict=True))

    def test_decode_property_set_leftover_rgdata_strict_fails(self) -> None:
        # NoData property but rgData has bytes -> not fully consumed
        prid = PropertyID.from_u32((1) | (0x01 << 26))
        ps = PropertySet(c_properties=1, rg_prids=(prid,), rg_data=b"\xFF")
        with self.assertRaises(OneStoreFormatError):
            decode_property_set(ps, oids=(), osids=None, context_ids=None, ctx=ParseContext(strict=True))
