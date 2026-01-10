import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onestore.chunk_refs import FileChunkReference64x32  # noqa: E402
from onestore.file_node_list import (  # noqa: E402
    CHUNK_TERMINATOR_FND_ID,
    FNL_FOOTER_MAGIC,
    FNL_HEADER_MAGIC,
    parse_file_node_list,
)
from onestore.io import BinaryReader  # noqa: E402
from onestore.parse_context import ParseContext  # noqa: E402


def _pack_filenode_header(
    *,
    file_node_id: int,
    size: int = 4,
    stp_format: int = 0,
    cb_format: int = 0,
    base_type: int = 0,
    reserved: int = 1,
) -> bytes:
    # Bit layout (LSB->MSB):
    # FileNodeID(10), Size(13), StpFormat(2), CbFormat(2), BaseType(4), Reserved(1)
    if not (0 <= file_node_id < (1 << 10)):
        raise ValueError("file_node_id out of range")
    if not (0 <= size < (1 << 13)):
        raise ValueError("size out of range")
    if not (0 <= stp_format < 4):
        raise ValueError("stp_format out of range")
    if not (0 <= cb_format < 4):
        raise ValueError("cb_format out of range")
    if not (0 <= base_type < 16):
        raise ValueError("base_type out of range")
    if reserved not in (0, 1):
        raise ValueError("reserved out of range")

    hdr = 0
    hdr |= file_node_id
    hdr |= size << 10
    hdr |= stp_format << (10 + 13)
    hdr |= cb_format << (10 + 13 + 2)
    hdr |= base_type << (10 + 13 + 2 + 2)
    hdr |= reserved << (10 + 13 + 2 + 2 + 4)
    return struct.pack("<I", hdr)


def _build_fragment(
    *,
    list_id: int,
    seq: int,
    node_headers: list[bytes],
    next_fcr: FileChunkReference64x32,
    cb: int,
) -> bytes:
    # Keep padding at 2 bytes so that the parser must stop
    # because fewer than 4 bytes remain before nextFragment.
    node_stream = b"".join(node_headers)

    header = struct.pack("<QII", FNL_HEADER_MAGIC, list_id, seq)
    footer = struct.pack("<Q", FNL_FOOTER_MAGIC)
    next_fragment_bytes = struct.pack("<QI", next_fcr.stp, next_fcr.cb)

    # nextFragment position is determined by cb.
    next_fragment_pos = cb - (12 + 8)
    if next_fragment_pos < 16:
        raise ValueError("cb too small")

    padding_len = next_fragment_pos - len(header) - len(node_stream)
    if padding_len != 2:
        raise ValueError("Test fragments expect exactly 2 bytes of padding")

    padding = b"\xAA\xBB"
    out = header + node_stream + padding + next_fragment_bytes + footer

    if len(out) != cb:
        raise AssertionError("fragment size mismatch")
    return out


def _build_synthetic_file() -> tuple[bytes, FileChunkReference64x32, int]:
    # Fragment layout:
    # - fragment0: 2 nodes + terminator
    # - fragment1: 1 node + terminator
    # - fragment2: 1 node, no terminator, nextFragment = fcrNil

    list_id = 0x10

    node_a = _pack_filenode_header(file_node_id=0x001)
    node_b = _pack_filenode_header(file_node_id=0x002)
    term = _pack_filenode_header(file_node_id=CHUNK_TERMINATOR_FND_ID)
    node_c = _pack_filenode_header(file_node_id=0x003)
    node_d = _pack_filenode_header(file_node_id=0x004)

    stp0 = 0x100
    stp1 = 0x200
    stp2 = 0x300

    cb0 = 38 + 12  # header(16) + nodes(12) + padding(2) + next(12) + footer(8)
    cb1 = 38 + 8
    cb2 = 38 + 4

    fcr0 = FileChunkReference64x32(stp=stp0, cb=cb0)
    fcr1 = FileChunkReference64x32(stp=stp1, cb=cb1)
    fcr2 = FileChunkReference64x32(stp=stp2, cb=cb2)
    fcr_nil = FileChunkReference64x32(stp=0xFFFFFFFFFFFFFFFF, cb=0)

    frag0 = _build_fragment(list_id=list_id, seq=0, node_headers=[node_a, node_b, term], next_fcr=fcr1, cb=cb0)
    frag1 = _build_fragment(list_id=list_id, seq=1, node_headers=[node_c, term], next_fcr=fcr2, cb=cb1)
    frag2 = _build_fragment(list_id=list_id, seq=2, node_headers=[node_d], next_fcr=fcr_nil, cb=cb2)

    size = stp2 + cb2
    data = bytearray(size)
    data[stp0 : stp0 + cb0] = frag0
    data[stp1 : stp1 + cb1] = frag1
    data[stp2 : stp2 + cb2] = frag2

    return bytes(data), fcr0, list_id


class TestFileNodeList(unittest.TestCase):
    def test_parse_file_node_list_full_chain(self) -> None:
        data, first, list_id = _build_synthetic_file()

        ctx = ParseContext(strict=True)
        out = parse_file_node_list(BinaryReader(data), first, ctx=ctx)

        self.assertEqual(out.list_id, list_id)
        self.assertEqual(out.node_count, 4)
        self.assertEqual(len(out.fragments), 3)
        self.assertEqual([n.file_node_id for n in out.file_nodes], [1, 2, 3, 4])

        # Terminators are not included in aggregated nodes.
        self.assertNotIn(CHUNK_TERMINATOR_FND_ID, [n.file_node_id for n in out.file_nodes])

    def test_parse_file_node_list_respects_committed_count_limit(self) -> None:
        data, first, list_id = _build_synthetic_file()

        # Only 3 committed nodes: parser must stop after reading 3 nodes and ignore further fragments.
        last_count_by_list_id = {list_id: 3}

        out = parse_file_node_list(
            BinaryReader(data),
            first,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True),
        )

        self.assertEqual(out.list_id, list_id)
        self.assertEqual(out.node_count, 3)
        self.assertEqual([n.file_node_id for n in out.file_nodes], [1, 2, 3])
        self.assertEqual(len(out.fragments), 2)
