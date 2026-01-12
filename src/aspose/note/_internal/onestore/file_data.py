from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from .chunk_refs import FileChunkReference64x32
from .chunk_refs import FileNodeChunkReference
from .errors import OneStoreFormatError
from .file_node_list import parse_file_node_list_typed_nodes
from .file_node_types import FileDataStoreListReferenceFND, FileDataStoreObjectReferenceFND, build_root_file_node_list_manifests
from .header import Header
from .io import BinaryReader
from .parse_context import ParseContext
from .txn_log import parse_transaction_log


# FileDataStoreObject (2.6.13)
_FILE_DATA_STORE_OBJECT_GUID_HEADER = uuid.UUID("BDE316E7-2665-4511-A4C4-8D4D0B7A9EAC").bytes_le
_FILE_DATA_STORE_OBJECT_GUID_FOOTER = uuid.UUID("71FBA722-0F79-4A0B-BB13-899256426B24").bytes_le


@dataclass(frozen=True, slots=True)
class FileDataStoreObject:
    cb_length: int
    file_data: bytes
    padding: bytes


def parse_file_data_store_object_from_ref(
    data: bytes | bytearray | memoryview,
    *,
    stp: int,
    cb: int,
    ctx: ParseContext,
) -> FileDataStoreObject:
    """Parse FileDataStoreObject (2.6.13) from a file offset/size.

    This is a structural parser focused on safe bounds checks and MUST validations.
    """

    if stp < 0 or cb < 0:
        raise OneStoreFormatError("stp/cb MUST be non-negative", offset=None)

    r = BinaryReader(data).view(int(stp), int(cb))
    start = r.tell()

    if r.remaining() < 16 + 8 + 4 + 8 + 16:
        raise OneStoreFormatError("FileDataStoreObject is too small", offset=start)

    guid_header = bytes(r.read_bytes(16))
    if guid_header != _FILE_DATA_STORE_OBJECT_GUID_HEADER:
        msg = "FileDataStoreObject.guidHeader MUST match expected GUID"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=start)
        ctx.warn(msg, offset=start)

    cb_length = int(r.read_u64())
    _unused = int(r.read_u32())
    _reserved = int(r.read_u64())

    # Ensure we can read cbLength bytes plus the footer GUID.
    if cb_length < 0:
        raise OneStoreFormatError("FileDataStoreObject.cbLength MUST be non-negative", offset=r.tell() - 8)

    if r.remaining() < cb_length + 16:
        raise OneStoreFormatError("FileDataStoreObject.FileData exceeds available data", offset=r.tell())

    file_data = bytes(r.read_bytes(cb_length))

    # Remaining bytes must be: padding (0..7) + footer GUID.
    if r.remaining() < 16:
        raise OneStoreFormatError("FileDataStoreObject missing guidFooter", offset=r.tell())

    padding_len = int(r.remaining() - 16)
    if padding_len < 0 or padding_len > 7:
        msg = "FileDataStoreObject padding length MUST be between 0 and 7"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=r.tell())
        ctx.warn(msg, offset=r.tell())
        # Best-effort: clamp to range to keep parsing deterministic.
        padding_len = max(0, min(7, padding_len))

    padding = bytes(r.read_bytes(padding_len))

    guid_footer = bytes(r.read_bytes(16))
    if guid_footer != _FILE_DATA_STORE_OBJECT_GUID_FOOTER:
        msg = "FileDataStoreObject.guidFooter MUST match expected GUID"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=r.tell() - 16)
        ctx.warn(msg, offset=r.tell() - 16)

    if r.remaining() != 0:
        msg = "FileDataStoreObject parse did not consume full referenced payload"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=r.tell())
        ctx.warn(msg, offset=r.tell())

    return FileDataStoreObject(cb_length=cb_length, file_data=file_data, padding=padding)


@dataclass(frozen=True, slots=True)
class FileDataStoreIndex:
    """Deterministic index guidReference -> FileNodeChunkReference."""

    by_guid: dict[bytes, FileNodeChunkReference]


def parse_file_data_store_index(
    data: bytes | bytearray | memoryview,
    *,
    ctx: ParseContext | None = None,
) -> dict[bytes, FileNodeChunkReference]:
    """Build guidReference -> FileNodeChunkReference index from root list.

    Returns an empty dict if the root list has no FileDataStoreListReferenceFND.
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    header = Header.parse(BinaryReader(data), ctx=ctx)
    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    root_typed = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        header.fcr_file_node_list_root,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    manifests = build_root_file_node_list_manifests(root_typed.nodes, ctx=ctx)
    file_data_ref: FileDataStoreListReferenceFND | None = manifests.file_data_store_list_ref
    if file_data_ref is None:
        return {}

    fcr = FileChunkReference64x32(stp=int(file_data_ref.ref.stp), cb=int(file_data_ref.ref.cb))
    lst = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        fcr,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    by_guid: dict[bytes, FileNodeChunkReference] = {}

    for tn in lst.nodes:
        if ctx.strict and tn.node.header.file_node_id != 0x094:
            raise OneStoreFormatError(
                "File data store list MUST contain only FileDataStoreObjectReferenceFND (0x094)",
                offset=tn.node.header.offset,
            )

        if not isinstance(tn.typed, FileDataStoreObjectReferenceFND):
            # Unknown IDs are already warned by typed parsing; in strict mode, treat as hard error.
            if ctx.strict:
                raise OneStoreFormatError(
                    "File data store list contains an unparsed or unknown node",
                    offset=tn.node.header.offset,
                )
            continue

        guid = bytes(tn.typed.guid_reference)
        if guid in by_guid:
            msg = "FileDataStoreObjectReferenceFND.guidReference MUST be unique"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=tn.node.header.offset)
            ctx.warn(msg, offset=tn.node.header.offset)
            continue

        by_guid[guid] = tn.typed.ref

    # Determinism: rebuild dict in sorted GUID order.
    return {k: by_guid[k] for k in sorted(by_guid.keys())}


_IFNDF_RE = re.compile(r"^<ifndf>\{(?P<guid>[0-9a-fA-F\-]{36})\}</ifndf>$")
_FILE_RE = re.compile(r"^<file>(?P<name>.*)$")
_INVFDO_RE = re.compile(r"^<invfdo>(?P<tail>.*)$")


@dataclass(frozen=True, slots=True)
class ParsedFileDataReference:
    kind: str  # 'ifndf' | 'file' | 'invfdo' | 'unknown'
    guid: bytes | None
    file_name: str | None


def parse_file_data_reference(value: str) -> ParsedFileDataReference:
    v = value.strip()

    m = _IFNDF_RE.match(v)
    if m:
        g = uuid.UUID(m.group("guid"))
        return ParsedFileDataReference(kind="ifndf", guid=g.bytes_le, file_name=None)

    m = _INVFDO_RE.match(v)
    if m:
        # Spec says tail MUST be empty; caller can validate if desired.
        return ParsedFileDataReference(kind="invfdo", guid=None, file_name=None)

    m = _FILE_RE.match(v)
    if m:
        return ParsedFileDataReference(kind="file", guid=None, file_name=m.group("name"))

    return ParsedFileDataReference(kind="unknown", guid=None, file_name=None)


def get_file_data_by_reference(
    data: bytes | bytearray | memoryview,
    reference: str,
    *,
    ctx: ParseContext,
    index: dict[bytes, FileNodeChunkReference] | None = None,
) -> bytes | None:
    """Resolve a file data reference string.

    - For `<ifndf>{GUID}</ifndf>`: returns the embedded bytes if present in the file data store.
    - For `<file>`: returns None (external file; not loaded at this step).
    - For `<invfdo>` or unknown: returns None.
    """

    parsed = parse_file_data_reference(reference)
    if parsed.kind != "ifndf" or parsed.guid is None:
        return None

    if index is None:
        index = parse_file_data_store_index(data, ctx=ctx)

    ref = index.get(parsed.guid)
    if ref is None:
        return None

    # FileNodeChunkReference stores absolute stp/cb (already expanded by the parser).
    stp = int(ref.stp)
    cb = int(ref.cb)
    obj = parse_file_data_store_object_from_ref(data, stp=stp, cb=cb, ctx=ctx)
    return bytes(obj.file_data)
