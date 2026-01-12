from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable, Sequence

from .errors import OneStoreFormatError


@dataclass(frozen=True)
class Bounds:
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start


class BinaryReader:
    """Cursor-based little-endian reader with strict bounds.

    Offsets reported in errors are absolute offsets relative to the original buffer.
    """

    def __init__(
        self,
        data: bytes | bytearray | memoryview,
        *,
        start: int = 0,
        size: int | None = None,
        cursor: int = 0,
    ) -> None:
        mv = data if isinstance(data, memoryview) else memoryview(data)
        if mv.ndim != 1:
            raise ValueError("BinaryReader expects a 1-D buffer")

        if start < 0:
            raise ValueError("start must be >= 0")

        data_len = len(mv)
        if start > data_len:
            raise ValueError("start beyond data")

        if size is None:
            end = data_len
        else:
            if size < 0:
                raise ValueError("size must be >= 0")
            end = start + size
            if end > data_len:
                raise ValueError("(start+size) beyond data")

        if cursor < 0:
            raise ValueError("cursor must be >= 0")

        abs_pos = start + cursor
        if abs_pos > end:
            raise ValueError("cursor beyond bounds")

        self._data = mv
        self._bounds = Bounds(start=start, end=end)
        self._pos = abs_pos

    @property
    def bounds(self) -> Bounds:
        return self._bounds

    def tell(self) -> int:
        return self._pos

    def tell_relative(self) -> int:
        return self._pos - self._bounds.start

    def seek(self, absolute_offset: int) -> None:
        if not (self._bounds.start <= absolute_offset <= self._bounds.end):
            raise OneStoreFormatError("Seek out of bounds", offset=absolute_offset)
        self._pos = absolute_offset

    def seek_relative(self, offset: int) -> None:
        self.seek(self._bounds.start + offset)

    def remaining(self) -> int:
        return self._bounds.end - self._pos

    def _require(self, n: int) -> None:
        if n < 0:
            raise ValueError("n must be >= 0")
        if self._pos + n > self._bounds.end:
            raise OneStoreFormatError("Read out of bounds", offset=self._pos)

    def read_bytes(self, n: int) -> bytes:
        self._require(n)
        start = self._pos
        self._pos += n
        return self._data[start : start + n].tobytes()

    def peek_bytes(self, n: int) -> bytes:
        self._require(n)
        return self._data[self._pos : self._pos + n].tobytes()

    def skip(self, n: int) -> None:
        self._require(n)
        self._pos += n

    def view(self, relative_offset: int, size: int) -> "BinaryReader":
        if relative_offset < 0:
            raise OneStoreFormatError("Negative view offset", offset=self._pos)
        if size < 0:
            raise OneStoreFormatError("Negative view size", offset=self._pos)

        start = self._bounds.start + relative_offset
        end = start + size
        if end > self._bounds.end:
            raise OneStoreFormatError("View out of bounds", offset=start)

        return BinaryReader(self._data, start=start, size=size)

    # --- Primitive reads (little-endian) ---

    def read_u8(self) -> int:
        self._require(1)
        value = struct.unpack_from("<B", self._data, self._pos)[0]
        self._pos += 1
        return int(value)

    def read_u16(self) -> int:
        return self._read_struct("<H", 2)

    def read_u32(self) -> int:
        return self._read_struct("<I", 4)

    def read_u64(self) -> int:
        return self._read_struct("<Q", 8)

    def _read_struct(self, fmt: str, size: int) -> int:
        self._require(size)
        value = struct.unpack_from(fmt, self._data, self._pos)[0]
        self._pos += size
        return int(value)

    # --- Bit helpers ---

    @staticmethod
    def unpack_bits(value: int, widths: Sequence[int]) -> tuple[int, ...]:
        """Unpacks bit fields from LSB to MSB.

        Example: widths [8, 24] -> (value & 0xFF, value >> 8)
        """
        out: list[int] = []
        shift = 0
        for w in widths:
            if w <= 0:
                raise ValueError("widths must be positive")
            mask = (1 << w) - 1
            out.append((value >> shift) & mask)
            shift += w
        return tuple(out)

    def read_u32_bits(self, widths: Sequence[int]) -> tuple[int, ...]:
        return self.unpack_bits(self.read_u32(), widths)


def iter_u32_bits(value: int, widths: Iterable[int]) -> Iterable[int]:
    shift = 0
    for w in widths:
        if w <= 0:
            raise ValueError("widths must be positive")
        mask = (1 << w) - 1
        yield (value >> shift) & mask
        shift += w
