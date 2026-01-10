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
