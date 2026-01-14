import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.onestore.errors import OneStoreFormatError  # noqa: E402
from aspose.note._internal.onestore.header import GUID_FILE_FORMAT, GUID_FILE_TYPE_ONE, Header  # noqa: E402
from aspose.note._internal.onestore.io import BinaryReader  # noqa: E402


def _pack_fcr32(stp: int, cb: int) -> bytes:
    return struct.pack("<II", stp, cb)


def _pack_fcr64x32(stp: int, cb: int) -> bytes:
    return struct.pack("<QI", stp, cb)


def _build_min_valid_file(*, file_size: int = 4096) -> bytes:
    if file_size < Header.SIZE + 64:
        raise ValueError("file_size too small")

    header = b"".join(
        [
            GUID_FILE_TYPE_ONE.bytes_le,
            b"\x00" * 16,  # guidFile
            b"\x00" * 16,  # guidLegacyFileVersion
            GUID_FILE_FORMAT.bytes_le,
            struct.pack("<IIII", 0x2A, 0x2A, 0x2A, 0x2A),
            _pack_fcr32(0, 0),  # fcrLegacyFreeChunkList (fcrZero)
            _pack_fcr32(0xFFFFFFFF, 0),  # fcrLegacyTransactionLog (fcrNil)
            struct.pack("<I", 1),  # cTransactionsInLog
            struct.pack("<I", 0),  # cbLegacyExpectedFileLength
            struct.pack("<Q", 0),  # rgbPlaceholder
            _pack_fcr32(0xFFFFFFFF, 0),  # fcrLegacyFileNodeListRoot (fcrNil)
            struct.pack("<I", 0),  # cbLegacyFreeSpaceInFreeChunkList
            struct.pack("<BBBB", 0, 0, 0, 0),  # legacy flags
            b"\x00" * 16,  # guidAncestor
            struct.pack("<I", 0),  # crcName
            _pack_fcr64x32(0, 0),  # fcrHashedChunkList (none)
            _pack_fcr64x32(Header.SIZE, 32),  # fcrTransactionLog (dummy in-file)
            _pack_fcr64x32(Header.SIZE + 32, 32),  # fcrFileNodeListRoot (dummy in-file)
            _pack_fcr64x32(0, 0),  # fcrFreeChunkList (none)
            struct.pack("<Q", file_size),  # cbExpectedFileLength
            struct.pack("<Q", 0),  # cbFreeSpaceInFreeChunkList
            b"\x00" * 16,  # guidFileVersion
            struct.pack("<Q", 0),  # nFileVersionGeneration
            b"\x00" * 16,  # guidDenyReadFileVersion
            struct.pack("<I", 0),  # grfDebugLogFlags
            _pack_fcr64x32(0, 0),  # fcrDebugLog
            _pack_fcr64x32(0, 0),  # fcrAllocVerificationFreeChunkList
            struct.pack("<IIII", 0, 0, 0, 0),  # build numbers
            b"\x00" * 728,  # rgbReserved
        ]
    )

    if len(header) != Header.SIZE:
        raise AssertionError(f"Header size mismatch: {len(header)}")

    return header + (b"\x00" * (file_size - len(header)))


class TestHeaderParsing(unittest.TestCase):
    def test_parse_minimal_valid_header(self) -> None:
        data = _build_min_valid_file(file_size=8192)
        header = Header.parse(BinaryReader(data))
        self.assertEqual(header.file_format_uuid, GUID_FILE_FORMAT)
        self.assertEqual(header.file_type_uuid, GUID_FILE_TYPE_ONE)
        self.assertEqual(header.c_transactions_in_log, 1)

    def test_invalid_guid_file_format_raises(self) -> None:
        data = bytearray(_build_min_valid_file())
        # guidFileFormat is at offset 48..63.
        data[48:64] = b"\x11" * 16
        with self.assertRaises(OneStoreFormatError):
            Header.parse(BinaryReader(bytes(data)))

    def test_out_of_bounds_fcr_transaction_log_raises(self) -> None:
        data = bytearray(_build_min_valid_file(file_size=4096))
        # fcrTransactionLog at offset 160..171 (stp:u64, cb:u32)
        stp = 4096 - 8
        cb = 32
        data[160:172] = _pack_fcr64x32(stp, cb)
        with self.assertRaises(OneStoreFormatError) as ex:
            Header.parse(BinaryReader(bytes(data)))
        self.assertEqual(ex.exception.offset, stp)
