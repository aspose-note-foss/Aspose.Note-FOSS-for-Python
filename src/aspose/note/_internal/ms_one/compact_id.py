from __future__ import annotations

from dataclasses import dataclass

from ..onestore.common_types import CompactID, ExtendedGUID
from ..onestore.errors import OneStoreFormatError
from ..onestore.parse_context import ParseContext


@dataclass(frozen=True, slots=True)
class EffectiveGidTable:
    """Convenience wrapper around a revision's effective GID table."""

    by_index: dict[int, bytes]

    @classmethod
    def from_sorted_items(cls, items: tuple[tuple[int, bytes], ...]) -> "EffectiveGidTable":
        return cls(by_index={int(k): bytes(v) for k, v in items})


def resolve_compact_id(
    compact_id: CompactID,
    gid_table: EffectiveGidTable | None,
    *,
    ctx: ParseContext,
    offset: int | None = None,
) -> ExtendedGUID:
    """Resolve CompactID -> ExtendedGUID using a revision's effective Global ID Table."""

    if gid_table is None:
        msg = "CompactID resolution requires an in-scope Global ID Table"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=offset)
        ctx.warn(msg, offset=offset)
        return ExtendedGUID(guid=b"\x00" * 16, n=int(compact_id.n))

    guid = gid_table.by_index.get(int(compact_id.guid_index))
    if guid is None:
        msg = f"CompactID.guidIndex {int(compact_id.guid_index)} is not present in the effective Global ID Table"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=offset)
        ctx.warn(msg, offset=offset)
        return ExtendedGUID(guid=b"\x00" * 16, n=int(compact_id.n))

    return ExtendedGUID(guid=bytes(guid), n=int(compact_id.n))


def resolve_compact_id_array(
    compact_ids: tuple[CompactID, ...],
    gid_table: EffectiveGidTable | None,
    *,
    ctx: ParseContext,
    offset: int | None = None,
) -> tuple[ExtendedGUID, ...]:
    return tuple(resolve_compact_id(c, gid_table, ctx=ctx, offset=offset) for c in compact_ids)
