from __future__ import annotations

from dataclasses import dataclass

from .errors import OneStoreFormatError
from .io import BinaryReader


@dataclass(frozen=True, slots=True)
class FileChunkReference32:
    stp: int
    cb: int

    @classmethod
    def parse(cls, reader: BinaryReader) -> "FileChunkReference32":
        return cls(stp=reader.read_u32(), cb=reader.read_u32())

    def is_nil(self) -> bool:
        return self.stp == 0xFFFFFFFF and self.cb == 0

    def is_zero(self) -> bool:
        return self.stp == 0 and self.cb == 0

    def validate_in_file(self, file_size: int) -> None:
        if self.is_nil() or self.is_zero():
            return
        if self.stp + self.cb > file_size:
            raise OneStoreFormatError("FileChunkReference32 out of bounds", offset=self.stp)


@dataclass(frozen=True, slots=True)
class FileChunkReference64:
    stp: int
    cb: int

    @classmethod
    def parse(cls, reader: BinaryReader) -> "FileChunkReference64":
        return cls(stp=reader.read_u64(), cb=reader.read_u64())

    def is_nil(self) -> bool:
        return self.stp == 0xFFFFFFFFFFFFFFFF and self.cb == 0

    def is_zero(self) -> bool:
        return self.stp == 0 and self.cb == 0

    def validate_in_file(self, file_size: int) -> None:
        if self.is_nil() or self.is_zero():
            return
        if self.stp + self.cb > file_size:
            raise OneStoreFormatError("FileChunkReference64 out of bounds", offset=self.stp)


@dataclass(frozen=True, slots=True)
class FileChunkReference64x32:
    stp: int
    cb: int

    @classmethod
    def parse(cls, reader: BinaryReader) -> "FileChunkReference64x32":
        stp = reader.read_u64()
        cb = reader.read_u32()
        return cls(stp=stp, cb=cb)

    def is_nil(self) -> bool:
        return self.stp == 0xFFFFFFFFFFFFFFFF and self.cb == 0

    def is_zero(self) -> bool:
        return self.stp == 0 and self.cb == 0

    def validate_in_file(self, file_size: int) -> None:
        if self.is_nil() or self.is_zero():
            return
        if self.stp + self.cb > file_size:
            raise OneStoreFormatError("FileChunkReference64x32 out of bounds", offset=self.stp)


@dataclass(frozen=True, slots=True)
class FileNodeChunkReference:
    stp_format: int
    cb_format: int
    raw_stp: int
    raw_cb: int
    stp: int
    cb: int


def parse_filenode_chunk_reference(
    reader: BinaryReader, *, stp_format: int, cb_format: int
) -> FileNodeChunkReference:
    # StpFormat
    if stp_format == 0:
        raw_stp = reader.read_u64()
        stp = raw_stp
    elif stp_format == 1:
        raw_stp = reader.read_u32()
        stp = raw_stp
    elif stp_format == 2:
        raw_stp = reader.read_u16()
        stp = raw_stp * 8
    elif stp_format == 3:
        raw_stp = reader.read_u32()
        stp = raw_stp * 8
    else:
        raise OneStoreFormatError(f"Unknown StpFormat {stp_format}", offset=reader.tell())

    # CbFormat
    if cb_format == 0:
        raw_cb = reader.read_u32()
        cb = raw_cb
    elif cb_format == 1:
        raw_cb = reader.read_u64()
        cb = raw_cb
    elif cb_format == 2:
        raw_cb = reader.read_u8()
        cb = raw_cb * 8
    elif cb_format == 3:
        raw_cb = reader.read_u16()
        cb = raw_cb * 8
    else:
        raise OneStoreFormatError(f"Unknown CbFormat {cb_format}", offset=reader.tell())

    return FileNodeChunkReference(
        stp_format=stp_format,
        cb_format=cb_format,
        raw_stp=raw_stp,
        raw_cb=raw_cb,
        stp=stp,
        cb=cb,
    )
