from __future__ import annotations

from dataclasses import dataclass

from .chunk_refs import FileNodeChunkReference, parse_filenode_chunk_reference
from .errors import OneStoreFormatError
from .io import BinaryReader
from .parse_context import ParseContext


CHUNK_TERMINATOR_FND_ID = 0x0FF


@dataclass(frozen=True, slots=True)
class FileNodeHeader:
    file_node_id: int
    size: int
    stp_format: int
    cb_format: int
    base_type: int
    reserved: int
    offset: int

    @property
    def is_chunk_terminator(self) -> bool:
        return self.file_node_id == CHUNK_TERMINATOR_FND_ID


def parse_file_node_header(reader: BinaryReader, *, ctx: ParseContext) -> FileNodeHeader:
    start = reader.tell()
    hdr = reader.read_u32()

    file_node_id, size, stp_format, cb_format, base_type, reserved = BinaryReader.unpack_bits(
        hdr, [10, 13, 2, 2, 4, 1]
    )

    return FileNodeHeader(
        file_node_id=int(file_node_id),
        size=int(size),
        stp_format=int(stp_format),
        cb_format=int(cb_format),
        base_type=int(base_type),
        reserved=int(reserved),
        offset=start,
    )


@dataclass(frozen=True, slots=True)
class FileNode:
    header: FileNodeHeader
    chunk_ref: FileNodeChunkReference | None
    payload: bytes
    fnd: bytes


def _validate_chunk_ref_in_file(ref: FileNodeChunkReference, *, file_size: int) -> None:
    # The spec treats fcrNil/fcrZero as special; mirror existing behavior for chunk refs.
    if ref.cb == 0 and ref.stp in (0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return
    if ref.stp + ref.cb > file_size:
        raise OneStoreFormatError("FileNodeChunkReference out of bounds", offset=ref.stp)


def parse_file_node(
    reader: BinaryReader,
    *,
    ctx: ParseContext,
    warn_unknown_ids: set[int] | None = None,
) -> FileNode:
    """Parse a single FileNode (2.4.3) from the current position.

    This is a *generic* parser: it decodes the header, enforces MUST bounds and
    BaseType rules, and optionally parses the leading FileNodeChunkReference.
    Unknown FileNodeIDs are preserved as raw bytes with a warning.
    """

    start = reader.tell()
    header = parse_file_node_header(reader, ctx=ctx)

    if header.reserved != 1:
        ctx.warn("FileNode.Reserved bit is not 1", offset=header.offset)

    if header.size < 4:
        raise OneStoreFormatError("FileNode.Size MUST be >= 4", offset=header.offset)

    payload_size = header.size - 4
    if payload_size > reader.remaining():
        raise OneStoreFormatError("FileNode exceeds container bounds", offset=header.offset)

    if header.base_type == 0 and header.cb_format != 0:
        raise OneStoreFormatError("FileNode.CbFormat MUST be 0 when BaseType==0", offset=header.offset)

    if header.is_chunk_terminator:
        if header.size != 4:
            raise OneStoreFormatError("ChunkTerminatorFND MUST contain no data", offset=header.offset)
        if reader.tell() != start + 4:
            raise OneStoreFormatError("Internal cursor mismatch", offset=reader.tell())
        return FileNode(header=header, chunk_ref=None, payload=b"", fnd=b"")

    payload_view = reader.view(reader.tell_relative(), payload_size)
    payload = payload_view.peek_bytes(payload_size)

    chunk_ref: FileNodeChunkReference | None = None
    fnd: bytes
    if header.base_type in (1, 2):
        chunk_ref = parse_filenode_chunk_reference(
            payload_view, stp_format=header.stp_format, cb_format=header.cb_format
        )
        if ctx.file_size is not None:
            _validate_chunk_ref_in_file(chunk_ref, file_size=ctx.file_size)
        fnd = payload_view.read_bytes(payload_view.remaining())
    else:
        if header.base_type not in (0, 1, 2):
            ctx.warn(f"Unknown FileNode.BaseType {header.base_type}", offset=header.offset)
        fnd = payload

    # Consume payload from the main reader.
    reader.skip(payload_size)
    if reader.tell() != start + header.size:
        raise OneStoreFormatError("FileNode did not consume declared Size", offset=header.offset)

    # Unknown handler: warn but keep raw bytes.
    if warn_unknown_ids is None:
        ctx.warn(f"Unknown FileNodeID 0x{header.file_node_id:03X}", offset=header.offset)
    else:
        if header.file_node_id not in warn_unknown_ids:
            warn_unknown_ids.add(header.file_node_id)
            ctx.warn(f"Unknown FileNodeID 0x{header.file_node_id:03X}", offset=header.offset)

    return FileNode(header=header, chunk_ref=chunk_ref, payload=payload, fnd=fnd)
