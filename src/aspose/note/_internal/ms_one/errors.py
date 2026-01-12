from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MSOneFormatError(Exception):
    message: str
    oid: object | None = None
    gosid: object | None = None
    rid: object | None = None
    offset: int | None = None

    def __str__(self) -> str:  # pragma: no cover
        parts: list[str] = [self.message]
        if self.oid is not None:
            parts.append(f"oid={self.oid}")
        if self.gosid is not None:
            parts.append(f"gosid={self.gosid}")
        if self.rid is not None:
            parts.append(f"rid={self.rid}")
        if self.offset is not None:
            parts.append(f"offset=0x{self.offset:X}")
        return "; ".join(parts)
