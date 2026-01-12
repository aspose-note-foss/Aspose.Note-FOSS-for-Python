from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .chunk_refs import FileChunkReference64x32
from .errors import OneStoreFormatError
from .file_node_list import parse_file_node_list_typed_nodes
from .file_node_types import HashedChunkDescriptor2FND
from .header import Header
from .io import BinaryReader
from .parse_context import ParseContext
from .txn_log import parse_transaction_log


@dataclass(frozen=True, slots=True)
class HashedChunkListEntry:
    stp: int
    cb: int
    md5: bytes


def parse_hashed_chunk_list_entries(
    data: bytes | bytearray | memoryview,
    *,
    ctx: ParseContext | None = None,
    validate_md5: bool = False,
) -> tuple[HashedChunkListEntry, ...]:
    """Parse hashed chunk list referenced by Header.fcrHashedChunkList.

    Returns an empty tuple if the file does not contain a hashed chunk list.

    If `validate_md5` is True, MD5 is computed for each referenced blob and compared
    to the stored hash. In strict mode, mismatches raise OneStoreFormatError.
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    header = Header.parse(BinaryReader(data), ctx=ctx)
    if header.fcr_hashed_chunk_list.is_zero() or header.fcr_hashed_chunk_list.is_nil():
        return ()

    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    lst = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        FileChunkReference64x32(stp=int(header.fcr_hashed_chunk_list.stp), cb=int(header.fcr_hashed_chunk_list.cb)),
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    entries: list[HashedChunkListEntry] = []

    for tn in lst.nodes:
        if ctx.strict and tn.node.header.file_node_id != 0x0C2:
            raise OneStoreFormatError(
                "Hashed chunk list MUST contain only HashedChunkDescriptor2FND (0x0C2)",
                offset=tn.node.header.offset,
            )

        if not isinstance(tn.typed, HashedChunkDescriptor2FND):
            if ctx.strict:
                raise OneStoreFormatError(
                    "Hashed chunk list contains an unparsed or unknown node",
                    offset=tn.node.header.offset,
                )
            continue

        stp = int(tn.typed.blob_ref.stp)
        cb = int(tn.typed.blob_ref.cb)
        md5 = bytes(tn.typed.guid_hash)

        if stp < 0 or cb < 0:
            raise OneStoreFormatError("Hashed chunk BlobRef stp/cb MUST be non-negative", offset=tn.node.header.offset)

        # Ensure referenced blob is inside the file.
        if ctx.file_size is not None and stp + cb > int(ctx.file_size):
            raise OneStoreFormatError("Hashed chunk BlobRef is out of file bounds", offset=stp)

        if validate_md5:
            blob = BinaryReader(data).view(stp, cb).read_bytes(cb)
            actual = hashlib.md5(blob).digest()
            if actual != md5:
                msg = "HashedChunkDescriptor2FND.guidHash does not match MD5(blob)"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=tn.node.header.offset)
                ctx.warn(msg, offset=tn.node.header.offset)

        entries.append(HashedChunkListEntry(stp=stp, cb=cb, md5=md5))

    # Determinism: sort by (stp, cb, md5) so callers can rely on stable order.
    return tuple(sorted(entries, key=lambda e: (int(e.stp), int(e.cb), e.md5)))


def parse_hashed_chunk_list_index(
    data: bytes | bytearray | memoryview,
    *,
    ctx: ParseContext | None = None,
    validate_md5: bool = False,
) -> dict[tuple[int, int], bytes]:
    """Build a deterministic index (stp,cb) -> md5 for hashed chunk list."""

    entries = parse_hashed_chunk_list_entries(data, ctx=ctx, validate_md5=validate_md5)
    out: dict[tuple[int, int], bytes] = {}

    for e in entries:
        key = (int(e.stp), int(e.cb))
        if key in out:
            msg = "Hashed chunk list contains duplicate BlobRef entries"
            if ctx is not None and not ctx.strict:
                ctx.warn(msg, offset=e.stp)
                continue
            raise OneStoreFormatError(msg, offset=e.stp)
        out[key] = bytes(e.md5)

    # Determinism: dict insertion order follows sorted `entries`.
    return out
