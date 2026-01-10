from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .errors import OneStoreFormatError
from .io import BinaryReader


@dataclass(frozen=True, slots=True)
class ExtendedGUID:
    guid: bytes  # 16 bytes, MS-DTYP GUID layout
    n: int       # u32

    @classmethod
    def parse(cls, reader: BinaryReader) -> "ExtendedGUID":
        guid = reader.read_bytes(16)
        if len(guid) != 16:
            raise OneStoreFormatError("ExtendedGUID: invalid guid length", offset=reader.tell())
        n = reader.read_u32()
        return cls(guid=guid, n=n)

    def is_zero(self) -> bool:
        return self.guid == b"\x00" * 16 and self.n == 0

    def to_uuid(self) -> UUID:
        # MS-DTYP GUIDs are little-endian for the first 3 fields.
        return UUID(bytes_le=self.guid)

    def as_str(self) -> str:
        return str(self.to_uuid())


@dataclass(frozen=True, slots=True)
class CompactID:
    n: int
    guid_index: int

    @classmethod
    def from_u32(cls, value: int) -> "CompactID":
        n = value & 0xFF
        guid_index = (value >> 8) & 0xFFFFFF
        return cls(n=n, guid_index=guid_index)

    @classmethod
    def parse(cls, reader: BinaryReader) -> "CompactID":
        return cls.from_u32(reader.read_u32())


@dataclass(frozen=True, slots=True)
class StringInStorageBuffer:
    cch: int
    raw_utf16le: bytes

    @classmethod
    def parse(cls, reader: BinaryReader) -> "StringInStorageBuffer":
        cch = reader.read_u32()
        raw = reader.read_bytes(cch * 2)
        return cls(cch=cch, raw_utf16le=raw)

    def decode(self) -> str:
        return self.raw_utf16le.decode("utf-16le", errors="strict")

    def decode_trim_trailing_null(self) -> str:
        s = self.decode()
        return s[:-1] if s.endswith("\x00") else s


@dataclass(frozen=True, slots=True)
class JCID:
    """JCID (2.6.14).

    Parsed from a u32, with a u16 index and flag bits.

    Layout (little-endian u32):
    - bits 0..15: index
    - bit 16: IsBinary
    - bit 17: IsPropertySet
    - bit 18: IsGraphNode (MUST be ignored)
    - bit 19: IsFileData
    - bit 20: IsReadOnly
    - bits 21..31: Reserved (MUST be 0)
    """

    raw: int
    index: int
    is_binary: bool
    is_property_set: bool
    is_graph_node: bool
    is_file_data: bool
    is_read_only: bool

    @classmethod
    def from_u32(cls, value: int) -> "JCID":
        value &= 0xFFFFFFFF
        index = value & 0xFFFF
        is_binary = bool((value >> 16) & 1)
        is_property_set = bool((value >> 17) & 1)
        is_graph_node = bool((value >> 18) & 1)
        is_file_data = bool((value >> 19) & 1)
        is_read_only = bool((value >> 20) & 1)
        return cls(
            raw=value,
            index=int(index),
            is_binary=is_binary,
            is_property_set=is_property_set,
            is_graph_node=is_graph_node,
            is_file_data=is_file_data,
            is_read_only=is_read_only,
        )

    @classmethod
    def parse(cls, reader: BinaryReader) -> "JCID":
        return cls.from_u32(reader.read_u32())

    def reserved_bits(self) -> int:
        return (self.raw >> 21) & 0x7FF

    def validate(self) -> None:
        if self.reserved_bits() != 0:
            raise OneStoreFormatError("JCID.Reserved MUST be 0", offset=None)

        # Invariant: IsFileData implies the other flags MUST be false.
        if self.is_file_data and (self.is_binary or self.is_property_set or self.is_graph_node or self.is_read_only):
            raise OneStoreFormatError(
                "JCID: if IsFileData is set, other JCID flags MUST be false",
                offset=None,
            )
