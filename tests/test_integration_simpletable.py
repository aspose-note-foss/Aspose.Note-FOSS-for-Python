import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onestore.chunk_refs import FileChunkReference32, parse_filenode_chunk_reference  # noqa: E402
from onestore.common_types import ExtendedGUID, StringInStorageBuffer  # noqa: E402
from onestore.crc import crc32_rfc3309  # noqa: E402
from onestore.errors import OneStoreFormatError  # noqa: E402
from onestore.header import GUID_FILE_FORMAT, GUID_FILE_TYPE_ONE, Header  # noqa: E402
from onestore.io import BinaryReader  # noqa: E402
from onestore.parse_context import ParseContext  # noqa: E402
from onestore.txn_log import TransactionLogFragment  # noqa: E402
from onestore.txn_log import parse_transaction_log  # noqa: E402
from onestore.file_node_list import parse_file_node_list, parse_file_node_list_nodes  # noqa: E402


def _simpletable_path() -> Path | None:
    p = ROOT / "SimpleTable.one"
    return p if p.exists() else None


class TestIntegrationSimpleTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.simpletable = _simpletable_path()
        if cls.simpletable is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.data = cls.simpletable.read_bytes()

    def test_file_sanity(self) -> None:
        self.assertGreater(len(self.data), 1024)

    def test_crc32_whole_file_matches_known_vector(self) -> None:
        # Regression guard: if the fixture changes, this will change.
        self.assertEqual(crc32_rfc3309(self.data), 0x77B62BD6)

    def test_parse_header_and_basic_invariants(self) -> None:
        r = BinaryReader(self.data)
        header = Header.parse(r)

        self.assertEqual(header.file_format_uuid, GUID_FILE_FORMAT)
        self.assertEqual(header.file_type_uuid, GUID_FILE_TYPE_ONE)
        self.assertNotEqual(header.c_transactions_in_log, 0)
        self.assertEqual(header.grf_debug_log_flags, 0)

        self.assertFalse(header.fcr_transaction_log.is_zero())
        self.assertFalse(header.fcr_transaction_log.is_nil())
        self.assertFalse(header.fcr_file_node_list_root.is_zero())
        self.assertFalse(header.fcr_file_node_list_root.is_nil())

        # Bounds are enforced during parsing, but keep explicit guards in the test.
        self.assertLessEqual(header.fcr_transaction_log.stp + header.fcr_transaction_log.cb, len(self.data))
        self.assertLessEqual(
            header.fcr_file_node_list_root.stp + header.fcr_file_node_list_root.cb,
            len(self.data),
        )

    def test_parse_transaction_log_and_basic_invariants(self) -> None:
        r = BinaryReader(self.data)
        header = Header.parse(r)

        last_count_by_list_id = parse_transaction_log(BinaryReader(self.data), header)

        # Basic invariants only: avoid brittle fixture-specific expectations.
        self.assertIsInstance(last_count_by_list_id, dict)
        self.assertGreater(len(last_count_by_list_id), 0)
        for k, v in last_count_by_list_id.items():
            self.assertIsInstance(k, int)
            self.assertIsInstance(v, int)
            self.assertGreater(k, 0)
            self.assertGreater(v, 0)
            self.assertNotEqual(k, 1)

    def test_transaction_log_is_deterministic(self) -> None:
        header = Header.parse(BinaryReader(self.data))

        ctx1 = ParseContext(strict=True)
        ctx2 = ParseContext(strict=True)

        out1 = parse_transaction_log(BinaryReader(self.data), header, ctx1)
        out2 = parse_transaction_log(BinaryReader(self.data), header, ctx2)

        self.assertEqual(out1, out2)
        self.assertEqual(ctx1.file_size, len(self.data))
        self.assertEqual(ctx2.file_size, len(self.data))

    def test_transaction_log_fragment_chain_has_enough_commits(self) -> None:
        header = Header.parse(BinaryReader(self.data))
        file_size = len(self.data)

        # Walk the fragment chain defensively: bounded steps + loop detection.
        visited_stp: set[int] = set()
        sentinels = 0

        current = header.fcr_transaction_log
        for _ in range(2048):
            # Protect against cyclic references.
            if current.stp in visited_stp:
                raise AssertionError("Transaction log fragment chain contains a loop")
            visited_stp.add(current.stp)

            frag = TransactionLogFragment.parse(
                BinaryReader(self.data),
                current,
                ctx=ParseContext(strict=True, file_size=file_size),
            )
            sentinels += sum(1 for e in frag.entries if e.is_sentinel)

            # Stop at end of chain.
            if frag.next_fragment.is_zero() or frag.next_fragment.is_nil() or frag.next_fragment.cb == 0:
                break
            frag.next_fragment.validate_in_file(file_size)
            current = frag.next_fragment
        else:
            raise AssertionError("Transaction log fragment chain is unexpectedly long")

        # The file should contain at least the committed number of transaction sentinels.
        self.assertGreaterEqual(sentinels, header.c_transactions_in_log)

    def test_parse_root_file_node_list_basic_invariants(self) -> None:
        data = self.data
        file_size = len(data)

        header = Header.parse(BinaryReader(data))
        ctx = ParseContext(strict=True, file_size=file_size)
        last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx)

        root_list = parse_file_node_list(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=file_size),
        )

        self.assertGreaterEqual(root_list.list_id, 0x10)
        self.assertGreater(root_list.node_count, 0)
        self.assertGreaterEqual(len(root_list.fragments), 1)

        # Determinism: structure-only equality.
        root_list2 = parse_file_node_list(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=file_size),
        )
        self.assertEqual(root_list.list_id, root_list2.list_id)
        self.assertEqual(root_list.node_count, root_list2.node_count)
        self.assertEqual(
            [(f.header.list_id, f.header.fragment_sequence, f.fcr.stp, f.fcr.cb) for f in root_list.fragments],
            [(f.header.list_id, f.header.fragment_sequence, f.fcr.stp, f.fcr.cb) for f in root_list2.fragments],
        )

    def test_parse_root_file_node_list_nodes_basic_invariants(self) -> None:
        data = self.data
        file_size = len(data)

        header = Header.parse(BinaryReader(data))
        last_count_by_list_id = parse_transaction_log(
            BinaryReader(data),
            header,
            ParseContext(strict=True, file_size=file_size),
        )

        # Parse as typed nodes.
        ctx = ParseContext(strict=True, file_size=file_size)
        out = parse_file_node_list_nodes(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        self.assertGreaterEqual(out.list.list_id, 0x10)
        self.assertGreater(out.list.node_count, 0)
        self.assertEqual(len(out.nodes), out.list.node_count)

        # Basic invariants: sizes and bounds.
        for n in out.nodes:
            self.assertGreaterEqual(n.header.size, 4)
            self.assertLessEqual(n.header.offset + n.header.size, file_size)
            if n.header.base_type in (1, 2):
                self.assertIsNotNone(n.chunk_ref)
            elif n.header.base_type == 0:
                self.assertIsNone(n.chunk_ref)

        # Determinism: parsing twice yields same structure and same headers sequence.
        out2 = parse_file_node_list_nodes(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=file_size),
        )

        self.assertEqual(out.list.list_id, out2.list.list_id)
        self.assertEqual(out.list.node_count, out2.list.node_count)
        self.assertEqual(
            [(n.header.file_node_id, n.header.size, n.header.base_type) for n in out.nodes],
            [(n.header.file_node_id, n.header.size, n.header.base_type) for n in out2.nodes],
        )

    def test_binary_reader_view_matches_slices(self) -> None:
        r = BinaryReader(self.data)
        prefix = r.peek_bytes(64)
        self.assertEqual(prefix, self.data[:64])

        v = r.view(0, 64)
        self.assertEqual(v.read_bytes(64), self.data[:64])

        # Nested view: bytes[16:32]
        vv = r.view(0, 64).view(16, 16)
        self.assertEqual(vv.read_bytes(16), self.data[16:32])

        # Out of bounds view should fail
        with self.assertRaises(OneStoreFormatError):
            r.view(len(self.data) - 4, 16)

    def test_extended_guid_parses_from_file_bytes(self) -> None:
        # We don't assume semantic meaning; just validate parser works on real bytes.
        eg = ExtendedGUID.parse(BinaryReader(self.data).view(0, 20))
        s = eg.as_str()
        self.assertEqual(len(s), 36)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", s))

    def test_parse_filenode_chunk_reference_from_file_bytes(self) -> None:
        # Use an arbitrary offset where we can safely read 12 bytes.
        if len(self.data) < 0x200 + 12:
            raise unittest.SkipTest("Fixture too small for this probe")
        r = BinaryReader(self.data).view(0x200, 12)
        ref = parse_filenode_chunk_reference(r, stp_format=0, cb_format=0)
        self.assertIsInstance(ref.stp, int)
        self.assertIsInstance(ref.cb, int)
        self.assertEqual(r.remaining(), 0)

    def test_find_and_parse_string_in_storage_buffer_somewhere(self) -> None:
        # Heuristic scan: find a small cch so that UTF-16LE decode works strictly.
        data = self.data
        scan_limit = min(len(data) - 8, 64 * 1024)

        for off in range(0, scan_limit, 2):
            r = BinaryReader(data).view(off, scan_limit - off)
            try:
                cch = r.read_u32()
            except OneStoreFormatError:
                break

            if not (1 <= cch <= 64):
                continue

            needed = cch * 2
            if r.remaining() < needed:
                continue

            try:
                sib = StringInStorageBuffer.parse(BinaryReader(data).view(off, 4 + needed))
                decoded = sib.decode()
            except (UnicodeDecodeError, OneStoreFormatError):
                continue

            self.assertEqual(len(decoded), cch)
            return

        raise unittest.SkipTest("No decodable StringInStorageBuffer found in scan window")

    def test_find_plausible_fcr32_and_validate_bounds(self) -> None:
        # Heuristic scan: locate a pair (stp,cb) that points inside the file.
        data = self.data
        file_size = len(data)
        scan_limit = min(len(data) - 8, 256 * 1024)

        for off in range(0, scan_limit, 4):
            r = BinaryReader(data).view(off, 8)
            stp = r.read_u32()
            cb = r.read_u32()

            # Skip sentinel-ish values and require a non-empty in-file region.
            if cb == 0 or stp == 0 or stp == 0xFFFFFFFF:
                continue
            if stp + cb > file_size:
                continue

            fcr = FileChunkReference32.parse(BinaryReader(data).view(off, 8))
            fcr.validate_in_file(file_size)
            return

        raise unittest.SkipTest("No plausible FileChunkReference32 found in scan window")
