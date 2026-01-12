from __future__ import annotations

from uuid import UUID

from ..onestore.io import BinaryReader
from ..onestore.parse_context import ParseContext


def decode_wz_in_atom(data: bytes, *, ctx: ParseContext | None = None, offset: int | None = None) -> str:
    """Decode MS-ONE WzInAtom: null-terminated UTF-16LE string."""

    try:
        s = data.decode("utf-16le", errors="strict")
    except UnicodeDecodeError as e:
        if ctx is None or ctx.strict:
            raise
        ctx.warn(f"WzInAtom decode failed: {e}", offset=offset)
        s = data.decode("utf-16le", errors="replace")

    return s[:-1] if s.endswith("\x00") else s


def decode_text_extended_ascii(data: bytes, *, ctx: ParseContext | None = None, offset: int | None = None) -> str:
    """Decode MS-ONE TextExtendedAscii.

    The spec describes this as an extended ASCII byte sequence (not UTF-16LE).
    In practice OneNote uses a Windows code page compatible with cp1252 for these
    values; we decode with cp1252.
    """

    try:
        return data.decode("cp1252", errors="strict")
    except UnicodeDecodeError as e:
        if ctx is None or ctx.strict:
            raise
        ctx.warn(f"TextExtendedAscii decode failed: {e}", offset=offset)
        return data.decode("cp1252", errors="replace")


def decode_guid_in_atom(data: bytes, *, ctx: ParseContext | None = None, offset: int | None = None) -> UUID:
    """Decode MS-ONE GuidInAtom: MS-DTYP GUID (little-endian fields)."""

    if len(data) != 16:
        msg = f"GuidInAtom must be 16 bytes, got {len(data)}"
        if ctx is not None and not ctx.strict:
            ctx.warn(msg, offset=offset)
        else:
            raise ValueError(msg)

    return UUID(bytes_le=data[:16])


def decode_color_u32_abgr(value: int) -> tuple[int, int, int, int]:
    """Decode MS-ONE Color/COLORREF-ish u32 as (a,b,g,r) bytes."""

    value &= 0xFFFFFFFF
    a = (value >> 24) & 0xFF
    b = (value >> 16) & 0xFF
    g = (value >> 8) & 0xFF
    r = value & 0xFF
    return (a, b, g, r)


def read_u32_le(data: bytes) -> int:
    return int(BinaryReader(data).read_u32())
