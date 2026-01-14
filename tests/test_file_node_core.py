import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.onestore.errors import OneStoreFormatError  # noqa: E402
from aspose.note._internal.onestore.file_node_core import parse_file_node  # noqa: E402
from aspose.note._internal.onestore.io import BinaryReader  # noqa: E402
from aspose.note._internal.onestore.parse_context import ParseContext  # noqa: E402


def _pack_filenode_header(
    *,
    file_node_id: int,
    size: int,
    stp_format: int = 0,
    cb_format: int = 0,
    base_type: int = 0,
    reserved: int = 1,
) -> bytes:
    # Bit layout (LSB->MSB): FileNodeID(10), Size(13), StpFormat(2), CbFormat(2), BaseType(4), Reserved(1)
    hdr = 0
    hdr |= file_node_id
    hdr |= size << 10
    hdr |= stp_format << (10 + 13)
    hdr |= cb_format << (10 + 13 + 2)
    hdr |= base_type << (10 + 13 + 2 + 2)
    hdr |= reserved << (10 + 13 + 2 + 2 + 4)
    return struct.pack("<I", hdr)


class TestFileNodeCore(unittest.TestCase):
    def test_reserved_bit_not_1_emits_warning(self) -> None:
        # Minimal node: Size==4, BaseType==0, but Reserved==0.
        data = _pack_filenode_header(file_node_id=1, size=4, reserved=0)
        ctx = ParseContext(strict=True, file_size=1024)
        node = parse_file_node(BinaryReader(data), ctx=ctx)

        self.assertEqual(node.header.reserved, 0)
        self.assertEqual(node.header.size, 4)
        self.assertEqual(node.payload, b"")
        self.assertGreaterEqual(len(ctx.warnings), 1)
        self.assertTrue(any("Reserved" in w.message for w in ctx.warnings))

    def test_basetype0_requires_cbformat0(self) -> None:
        # BaseType==0 with CbFormat!=0 MUST error.
        data = _pack_filenode_header(file_node_id=2, size=4, base_type=0, cb_format=1)
        with self.assertRaises(OneStoreFormatError):
            parse_file_node(BinaryReader(data), ctx=ParseContext(strict=True, file_size=1024))

    def test_size_must_be_at_least_4(self) -> None:
        data = _pack_filenode_header(file_node_id=3, size=0, base_type=0)
        with self.assertRaises(OneStoreFormatError):
            parse_file_node(BinaryReader(data), ctx=ParseContext(strict=True, file_size=1024))

    def test_size_bounds_enforced(self) -> None:
        # Declares Size=8 but only 4 bytes exist in container.
        data = _pack_filenode_header(file_node_id=4, size=8, base_type=0)
        with self.assertRaises(OneStoreFormatError):
            parse_file_node(BinaryReader(data), ctx=ParseContext(strict=True, file_size=1024))

    def test_basetype1_parses_chunk_reference_and_rest_payload(self) -> None:
        # BaseType==1: payload starts with FileNodeChunkReference.
        # Use stp_format=1 (u32), cb_format=0 (u32)
        stp = 0x20
        cb = 0x10
        rest = b"AB"
        payload = struct.pack("<II", stp, cb) + rest
        size = 4 + len(payload)
        data = _pack_filenode_header(
            file_node_id=0x123,
            size=size,
            stp_format=1,
            cb_format=0,
            base_type=1,
        ) + payload

        ctx = ParseContext(strict=True, file_size=0x1000)
        node = parse_file_node(BinaryReader(data), ctx=ctx)
        self.assertIsNotNone(node.chunk_ref)
        assert node.chunk_ref is not None
        self.assertEqual(node.chunk_ref.stp, stp)
        self.assertEqual(node.chunk_ref.cb, cb)
        self.assertEqual(node.fnd, rest)

    def test_chunk_reference_out_of_file_errors(self) -> None:
        stp = 0x20
        cb = 0x40  # stp+cb=0x60
        payload = struct.pack("<II", stp, cb)
        size = 4 + len(payload)
        data = _pack_filenode_header(
            file_node_id=0x124,
            size=size,
            stp_format=1,
            cb_format=0,
            base_type=1,
        ) + payload

        # file_size smaller than stp+cb.
        ctx = ParseContext(strict=True, file_size=0x50)
        with self.assertRaises(OneStoreFormatError):
            parse_file_node(BinaryReader(data), ctx=ctx)
