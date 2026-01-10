from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from .chunk_refs import FileChunkReference32, FileChunkReference64x32
from .errors import OneStoreFormatError
from .io import BinaryReader
from .parse_context import ParseContext


GUID_FILE_FORMAT = UUID("{109ADD3F-911B-49F5-A5D0-1791EDC8AED8}")
GUID_FILE_TYPE_ONE = UUID("{7B5C52E4-D88C-4DA7-AEB1-5378D02996D3}")
GUID_FILE_TYPE_ONETOC2 = UUID("{43FF2FA1-EFD9-4C76-9EE2-10EA5722765F}")


_FCR32_ZERO = FileChunkReference32(stp=0, cb=0)
_FCR32_NIL = FileChunkReference32(stp=0xFFFFFFFF, cb=0)
_FCR64X32_ZERO = FileChunkReference64x32(stp=0, cb=0)


def _guid_from_bytes_le(guid_le: bytes) -> UUID:
    if len(guid_le) != 16:
        raise ValueError("GUID bytes must be 16 bytes")
    return UUID(bytes_le=guid_le)


@dataclass(frozen=True, slots=True)
class Header:
    """MS-ONESTORE Header (2.3.1).

    Stored values are raw primitives (GUIDs as 16 bytes in MS-DTYP bytes_le form)
    to keep parsing deterministic and representation-agnostic.
    """

    SIZE: ClassVar[int] = 1024

    guid_file_type: bytes = b""  # 16
    guid_file: bytes = b""  # 16
    guid_legacy_file_version: bytes = b""  # 16
    guid_file_format: bytes = b""  # 16

    ffv_last_code_that_wrote_to_this_file: int = 0
    ffv_oldest_code_that_has_written_to_this_file: int = 0
    ffv_newest_code_that_has_written_to_this_file: int = 0
    ffv_oldest_code_that_may_read_this_file: int = 0

    fcr_legacy_free_chunk_list: FileChunkReference32 = _FCR32_ZERO
    fcr_legacy_transaction_log: FileChunkReference32 = _FCR32_NIL
    c_transactions_in_log: int = 0
    cb_legacy_expected_file_length: int = 0
    rgb_placeholder: int = 0
    fcr_legacy_file_node_list_root: FileChunkReference32 = _FCR32_NIL
    cb_legacy_free_space_in_free_chunk_list: int = 0

    f_needs_defrag: int = 0
    f_repaired_file: int = 0
    f_needs_garbage_collect: int = 0
    f_has_no_embedded_file_objects: int = 0

    guid_ancestor: bytes = b""  # 16
    crc_name: int = 0

    fcr_hashed_chunk_list: FileChunkReference64x32 = _FCR64X32_ZERO
    fcr_transaction_log: FileChunkReference64x32 = _FCR64X32_ZERO
    fcr_file_node_list_root: FileChunkReference64x32 = _FCR64X32_ZERO
    fcr_free_chunk_list: FileChunkReference64x32 = _FCR64X32_ZERO

    cb_expected_file_length: int = 0
    cb_free_space_in_free_chunk_list: int = 0

    guid_file_version: bytes = b""  # 16
    n_file_version_generation: int = 0
    guid_deny_read_file_version: bytes = b""  # 16

    grf_debug_log_flags: int = 0
    fcr_debug_log: FileChunkReference64x32 = _FCR64X32_ZERO
    fcr_alloc_verification_free_chunk_list: FileChunkReference64x32 = _FCR64X32_ZERO

    bn_created: int = 0
    bn_last_wrote_to_this_file: int = 0
    bn_oldest_written: int = 0
    bn_newest_written: int = 0

    rgb_reserved: bytes = b""  # 728

    @property
    def file_type_uuid(self) -> UUID:
        return _guid_from_bytes_le(self.guid_file_type)

    @property
    def file_format_uuid(self) -> UUID:
        return _guid_from_bytes_le(self.guid_file_format)

    @classmethod
    def parse(cls, reader: BinaryReader, ctx: ParseContext | None = None) -> "Header":
        if ctx is None:
            ctx = ParseContext(strict=True)

        if reader.bounds.start != 0:
            # Header offsets and chunk references are defined relative to file start.
            raise OneStoreFormatError("Header must be parsed from file start", offset=reader.bounds.start)

        file_size = reader.bounds.end
        if ctx.file_size is None:
            ctx.file_size = file_size
        else:
            file_size = ctx.file_size

        reader.seek(0)
        hdr = reader.view(0, cls.SIZE)

        guid_file_type = hdr.read_bytes(16)
        guid_file = hdr.read_bytes(16)
        guid_legacy_file_version = hdr.read_bytes(16)
        guid_file_format = hdr.read_bytes(16)

        ffv_last = hdr.read_u32()
        ffv_oldest_written = hdr.read_u32()
        ffv_newest_written = hdr.read_u32()
        ffv_oldest_read = hdr.read_u32()

        fcr_legacy_free = FileChunkReference32.parse(hdr)
        fcr_legacy_txn = FileChunkReference32.parse(hdr)
        c_transactions_in_log = hdr.read_u32()
        cb_legacy_expected = hdr.read_u32()
        rgb_placeholder = hdr.read_u64()
        fcr_legacy_fnl_root = FileChunkReference32.parse(hdr)
        cb_legacy_free_space = hdr.read_u32()

        f_needs_defrag = hdr.read_u8()
        f_repaired_file = hdr.read_u8()
        f_needs_gc = hdr.read_u8()
        f_has_no_embedded = hdr.read_u8()

        guid_ancestor = hdr.read_bytes(16)
        crc_name = hdr.read_u32()

        fcr_hashed_chunk_list = FileChunkReference64x32.parse(hdr)
        fcr_transaction_log = FileChunkReference64x32.parse(hdr)
        fcr_file_node_list_root = FileChunkReference64x32.parse(hdr)
        fcr_free_chunk_list = FileChunkReference64x32.parse(hdr)

        cb_expected_file_length = hdr.read_u64()
        cb_free_space_in_free_chunk_list = hdr.read_u64()

        guid_file_version = hdr.read_bytes(16)
        n_file_version_generation = hdr.read_u64()
        guid_deny_read_file_version = hdr.read_bytes(16)

        grf_debug_log_flags = hdr.read_u32()
        fcr_debug_log = FileChunkReference64x32.parse(hdr)
        fcr_alloc_verification_free_chunk_list = FileChunkReference64x32.parse(hdr)

        bn_created = hdr.read_u32()
        bn_last_wrote_to_this_file = hdr.read_u32()
        bn_oldest_written_build = hdr.read_u32()
        bn_newest_written_build = hdr.read_u32()

        rgb_reserved = hdr.read_bytes(728)

        if hdr.remaining() != 0:
            raise OneStoreFormatError("Header parse did not consume 1024 bytes", offset=hdr.tell())

        # --- MUST validations (Step 4 baseline) ---

        if _guid_from_bytes_le(guid_file_format) != GUID_FILE_FORMAT:
            raise OneStoreFormatError("Invalid guidFileFormat", offset=48)

        if c_transactions_in_log == 0:
            raise OneStoreFormatError("cTransactionsInLog MUST NOT be 0", offset=96)

        if grf_debug_log_flags != 0:
            raise OneStoreFormatError("grfDebugLogFlags MUST be 0", offset=252)
        if not fcr_debug_log.is_zero():
            raise OneStoreFormatError("fcrDebugLog MUST be fcrZero", offset=256)
        if not fcr_alloc_verification_free_chunk_list.is_zero():
            raise OneStoreFormatError("fcrAllocVerificationFreeChunkList MUST be fcrZero", offset=268)

        # Key references MUST exist.
        if fcr_transaction_log.is_zero() or fcr_transaction_log.is_nil():
            raise OneStoreFormatError("fcrTransactionLog MUST NOT be fcrZero/fcrNil", offset=160)
        if fcr_file_node_list_root.is_zero() or fcr_file_node_list_root.is_nil():
            raise OneStoreFormatError("fcrFileNodeListRoot MUST NOT be fcrZero/fcrNil", offset=172)

        # Enforce chunk reference bounds.
        fcr_transaction_log.validate_in_file(file_size)
        fcr_file_node_list_root.validate_in_file(file_size)
        fcr_hashed_chunk_list.validate_in_file(file_size)
        fcr_free_chunk_list.validate_in_file(file_size)
        # Legacy refs are 32-bit but still must be in-bounds if non-sentinel.
        fcr_legacy_free.validate_in_file(file_size)
        fcr_legacy_txn.validate_in_file(file_size)
        fcr_legacy_fnl_root.validate_in_file(file_size)

        # Legacy fixed-value MUSTs (kept strict; tolerant mode later).
        if guid_legacy_file_version != b"\x00" * 16:
            raise OneStoreFormatError("guidLegacyFileVersion MUST be zero GUID", offset=32)
        if not fcr_legacy_free.is_zero():
            raise OneStoreFormatError("fcrLegacyFreeChunkList MUST be fcrZero", offset=80)
        if not fcr_legacy_txn.is_nil():
            raise OneStoreFormatError("fcrLegacyTransactionLog MUST be fcrNil", offset=88)
        if cb_legacy_expected != 0:
            raise OneStoreFormatError("cbLegacyExpectedFileLength MUST be 0", offset=100)
        if rgb_placeholder != 0:
            raise OneStoreFormatError("rgbPlaceholder MUST be 0", offset=104)
        if not fcr_legacy_fnl_root.is_nil():
            raise OneStoreFormatError("fcrLegacyFileNodeListRoot MUST be fcrNil", offset=112)
        if cb_legacy_free_space != 0:
            raise OneStoreFormatError("cbLegacyFreeSpaceInFreeChunkList MUST be 0", offset=120)
        if f_has_no_embedded != 0:
            raise OneStoreFormatError("fHasNoEmbeddedFileObjects MUST be 0", offset=127)

        if rgb_reserved != b"\x00" * 728:
            raise OneStoreFormatError("rgbReserved MUST be all zero", offset=296)

        # Expected file length mismatch is not a hard error in practice.
        if cb_expected_file_length not in (0, file_size):
            ctx.warn(
                "cbExpectedFileLength does not match actual file size",
                offset=196,
            )

        return cls(
            guid_file_type=guid_file_type,
            guid_file=guid_file,
            guid_legacy_file_version=guid_legacy_file_version,
            guid_file_format=guid_file_format,
            ffv_last_code_that_wrote_to_this_file=ffv_last,
            ffv_oldest_code_that_has_written_to_this_file=ffv_oldest_written,
            ffv_newest_code_that_has_written_to_this_file=ffv_newest_written,
            ffv_oldest_code_that_may_read_this_file=ffv_oldest_read,
            fcr_legacy_free_chunk_list=fcr_legacy_free,
            fcr_legacy_transaction_log=fcr_legacy_txn,
            c_transactions_in_log=c_transactions_in_log,
            cb_legacy_expected_file_length=cb_legacy_expected,
            rgb_placeholder=rgb_placeholder,
            fcr_legacy_file_node_list_root=fcr_legacy_fnl_root,
            cb_legacy_free_space_in_free_chunk_list=cb_legacy_free_space,
            f_needs_defrag=f_needs_defrag,
            f_repaired_file=f_repaired_file,
            f_needs_garbage_collect=f_needs_gc,
            f_has_no_embedded_file_objects=f_has_no_embedded,
            guid_ancestor=guid_ancestor,
            crc_name=crc_name,
            fcr_hashed_chunk_list=fcr_hashed_chunk_list,
            fcr_transaction_log=fcr_transaction_log,
            fcr_file_node_list_root=fcr_file_node_list_root,
            fcr_free_chunk_list=fcr_free_chunk_list,
            cb_expected_file_length=cb_expected_file_length,
            cb_free_space_in_free_chunk_list=cb_free_space_in_free_chunk_list,
            guid_file_version=guid_file_version,
            n_file_version_generation=n_file_version_generation,
            guid_deny_read_file_version=guid_deny_read_file_version,
            grf_debug_log_flags=grf_debug_log_flags,
            fcr_debug_log=fcr_debug_log,
            fcr_alloc_verification_free_chunk_list=fcr_alloc_verification_free_chunk_list,
            bn_created=bn_created,
            bn_last_wrote_to_this_file=bn_last_wrote_to_this_file,
            bn_oldest_written=bn_oldest_written_build,
            bn_newest_written=bn_newest_written_build,
            rgb_reserved=rgb_reserved,
        )
