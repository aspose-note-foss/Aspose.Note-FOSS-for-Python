import struct
import unittest

from tests._bootstrap import ensure_src_on_path

ensure_src_on_path()

from aspose.note._internal.onestore.chunk_refs import FileChunkReference64x32  # noqa: E402
from aspose.note._internal.onestore.header import Header  # noqa: E402
from aspose.note._internal.onestore.io import BinaryReader  # noqa: E402
from aspose.note._internal.onestore.txn_log import parse_transaction_log  # noqa: E402


def _entry(src_id: int, value: int) -> bytes:
    return struct.pack("<II", src_id, value)


def _fcr64x32(stp: int, cb: int) -> bytes:
    return struct.pack("<QI", stp, cb)


class TestTransactionLog(unittest.TestCase):
    def test_parses_two_transactions_and_applies_limit(self) -> None:
        # Build a synthetic file with one fragment containing two transactions.
        # Limit is 1, so only first transaction is applied.
        frag_off = 0x100

        entries = b"".join(
            [
                _entry(10, 5),
                _entry(11, 1),
                _entry(1, 0),  # sentinel (CRC ignored)
                _entry(10, 999),
                _entry(1, 0),
            ]
        )
        frag = entries + _fcr64x32(0, 0)

        data = bytearray(b"\x00" * (frag_off + len(frag)))
        data[frag_off : frag_off + len(frag)] = frag

        header = Header(
            c_transactions_in_log=1,
            fcr_transaction_log=FileChunkReference64x32(stp=frag_off, cb=len(frag)),
        )

        out = parse_transaction_log(BinaryReader(bytes(data)), header)
        self.assertEqual(out, {10: 5, 11: 1})

    def test_ignores_next_fragment_after_reaching_limit(self) -> None:
        # Fragment 1 contains the only transaction we care about (limit=1).
        # nextFragment points out of bounds and MUST be ignored.
        frag1_off = 0x80
        frag2_off = 0x200

        frag1_entries = b"".join(
            [
                _entry(7, 3),
                _entry(1, 0),  # sentinel ends transaction #1
            ]
        )

        # Point to an out-of-bounds fragment (cb non-zero) to ensure we do not validate/follow it.
        bogus_next = _fcr64x32(0xFFFFFFFFFFFFFF00, 0x40)
        frag1 = frag1_entries + bogus_next

        # Provide a second fragment that would change the result if it were followed.
        frag2 = b"".join([_entry(7, 999), _entry(1, 0)]) + _fcr64x32(0, 0)

        data_len = frag2_off + len(frag2)
        data = bytearray(b"\x00" * data_len)
        data[frag1_off : frag1_off + len(frag1)] = frag1
        data[frag2_off : frag2_off + len(frag2)] = frag2

        header = Header(
            c_transactions_in_log=1,
            fcr_transaction_log=FileChunkReference64x32(stp=frag1_off, cb=len(frag1)),
        )

        out = parse_transaction_log(BinaryReader(bytes(data)), header)
        self.assertEqual(out, {7: 3})


if __name__ == "__main__":
    unittest.main()
