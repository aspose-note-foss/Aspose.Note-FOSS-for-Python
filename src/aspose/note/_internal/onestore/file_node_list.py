from __future__ import annotations

from dataclasses import dataclass

from .chunk_refs import FileChunkReference64x32
from .errors import OneStoreFormatError
from .file_node_core import FileNode, parse_file_node
from .file_node_types import TypedFileNode, parse_typed_file_node
from .io import BinaryReader
from .parse_context import ParseContext


FNL_HEADER_MAGIC = 0xA4567AB1F5F7F4C4
FNL_FOOTER_MAGIC = 0x8BC215C38233BA4B

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


def _parse_file_node_header(reader: BinaryReader, *, ctx: ParseContext) -> FileNodeHeader:
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
class FileNodeRaw:
    header: FileNodeHeader
    raw_bytes: bytes

    @property
    def payload(self) -> bytes:
        return self.raw_bytes[4:]


@dataclass(frozen=True, slots=True)
class FileNodeListHeader:
    magic: int
    list_id: int
    fragment_sequence: int

    @classmethod
    def parse(cls, reader: BinaryReader, *, ctx: ParseContext) -> "FileNodeListHeader":
        start = reader.tell()
        magic = reader.read_u64()
        list_id = reader.read_u32()
        fragment_sequence = reader.read_u32()

        if magic != FNL_HEADER_MAGIC:
            raise OneStoreFormatError("Invalid FileNodeListHeader magic", offset=start)
        if list_id < 0x10:
            raise OneStoreFormatError("FileNodeListID MUST be >= 0x10", offset=start + 8)

        return cls(magic=int(magic), list_id=int(list_id), fragment_sequence=int(fragment_sequence))


@dataclass(frozen=True, slots=True)
class FileNodeListFragment:
    fcr: FileChunkReference64x32
    header: FileNodeListHeader
    file_nodes: tuple[FileNodeHeader, ...]
    raw_nodes: tuple[FileNodeRaw, ...]
    node_count: int
    found_chunk_terminator: bool
    next_fragment: FileChunkReference64x32

    @classmethod
    def parse(
        cls,
        reader: BinaryReader,
        fcr: FileChunkReference64x32,
        *,
        remaining_nodes: int | None,
        capture_node_bytes: bool = False,
        ctx: ParseContext | None = None,
    ) -> "FileNodeListFragment":
        if ctx is None:
            ctx = ParseContext(strict=True)

        if reader.bounds.start != 0:
            raise OneStoreFormatError(
                "FileNodeListFragment must be parsed from file start",
                offset=reader.bounds.start,
            )

        file_size = reader.bounds.end
        if ctx.file_size is None:
            ctx.file_size = file_size
        else:
            file_size = ctx.file_size

        fcr.validate_in_file(file_size)

        # Minimum: 16 header + 12 nextFragment + 8 footer
        if fcr.cb < 16 + 12 + 8:
            raise OneStoreFormatError("FileNodeListFragment too small", offset=fcr.stp)

        r = reader.view(fcr.stp, fcr.cb)

        header = FileNodeListHeader.parse(r, ctx=ctx)

        next_fragment_pos = fcr.cb - (12 + 8)
        if next_fragment_pos < 16:
            raise OneStoreFormatError("FileNodeListFragment nextFragment position invalid", offset=fcr.stp)

        file_nodes: list[FileNodeHeader] = []
        raw_nodes: list[FileNodeRaw] = []
        node_count = 0
        found_terminator = False

        while True:
            # Enforce bounds: do not read into nextFragment/footer area.
            if r.tell_relative() + 4 > next_fragment_pos:
                break

            if remaining_nodes is not None and remaining_nodes <= 0:
                break

            # Heuristic for padding: in real files the region between the last FileNode
            # and nextFragment is often zero-filled. A zero header would decode to Size=0
            # which is not a valid FileNode, so treat it as padding.
            if r.peek_bytes(4) == b"\x00\x00\x00\x00":
                break

            node_start_rel = r.tell_relative()
            node = _parse_file_node_header(r, ctx=ctx)

            if node.reserved != 1:
                ctx.warn("FileNode.Reserved bit is not 1", offset=node.offset)

            if node.size < 4:
                raise OneStoreFormatError("FileNode.Size MUST be >= 4", offset=node.offset)

            node_end_rel = node_start_rel + node.size
            if node_end_rel > next_fragment_pos:
                raise OneStoreFormatError("FileNode exceeds fragment bounds", offset=node.offset)

            # Validate BaseType==0 invariants early (Step 13 MUSTs).
            if node.base_type == 0 and node.cb_format != 0:
                raise OneStoreFormatError("FileNode.CbFormat MUST be 0 when BaseType==0", offset=node.offset)

            if node.is_chunk_terminator:
                # Spec: ChunkTerminatorFND MUST contain no data.
                if node.size != 4:
                    raise OneStoreFormatError("ChunkTerminatorFND MUST contain no data", offset=node.offset)
                found_terminator = True
                if capture_node_bytes:
                    raw = r.view(node_start_rel, node.size).peek_bytes(node.size)
                    raw_nodes.append(FileNodeRaw(header=node, raw_bytes=raw))
                file_nodes.append(node)
                break

            payload = node.size - 4
            if payload:
                if capture_node_bytes:
                    raw = r.view(node_start_rel, node.size).peek_bytes(node.size)
                    raw_nodes.append(FileNodeRaw(header=node, raw_bytes=raw))
                r.skip(payload)
            else:
                if capture_node_bytes:
                    raw = r.view(node_start_rel, node.size).peek_bytes(node.size)
                    raw_nodes.append(FileNodeRaw(header=node, raw_bytes=raw))

            file_nodes.append(node)
            node_count += 1
            if remaining_nodes is not None:
                remaining_nodes -= 1

        # Skip padding up to nextFragment.
        if r.tell_relative() > next_fragment_pos:
            raise OneStoreFormatError("FileNodeListFragment parse overran nextFragment", offset=r.tell())
        if r.tell_relative() < next_fragment_pos:
            r.seek_relative(next_fragment_pos)

        next_fragment = FileChunkReference64x32.parse(r)
        footer = r.read_u64()
        if footer != FNL_FOOTER_MAGIC:
            raise OneStoreFormatError("Invalid FileNodeListFragment footer", offset=r.tell() - 8)

        if r.remaining() != 0:
            raise OneStoreFormatError("FileNodeListFragment parse did not consume full chunk", offset=r.tell())

        return cls(
            fcr=fcr,
            header=header,
            file_nodes=tuple(file_nodes),
            raw_nodes=tuple(raw_nodes),
            node_count=int(node_count),
            found_chunk_terminator=bool(found_terminator),
            next_fragment=next_fragment,
        )


@dataclass(frozen=True, slots=True)
class FileNodeList:
    list_id: int
    fragments: tuple[FileNodeListFragment, ...]
    file_nodes: tuple[FileNodeHeader, ...]
    node_count: int


@dataclass(frozen=True, slots=True)
class FileNodeListWithRaw:
    list: FileNodeList
    raw_nodes: tuple[FileNodeRaw, ...]


@dataclass(frozen=True, slots=True)
class FileNodeListWithNodes:
    list: FileNodeList
    nodes: tuple[FileNode, ...]


@dataclass(frozen=True, slots=True)
class FileNodeListWithTypedNodes:
    list: FileNodeList
    nodes: tuple[TypedFileNode, ...]


def parse_file_node_list(
    reader: BinaryReader,
    first_fragment: FileChunkReference64x32,
    *,
    last_count_by_list_id: dict[int, int] | None = None,
    ctx: ParseContext | None = None,
) -> FileNodeList:
    """Parse a File Node List (2.4) starting from the first fragment reference.

    Applies committed-count limiting using last_count_by_list_id[list_id] when available.
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    if reader.bounds.start != 0:
        raise OneStoreFormatError("FileNodeList must be parsed from file start", offset=reader.bounds.start)

    file_size = reader.bounds.end
    if ctx.file_size is None:
        ctx.file_size = file_size
    else:
        file_size = ctx.file_size

    first_fragment.validate_in_file(file_size)

    fragments: list[FileNodeListFragment] = []
    nodes: list[FileNodeHeader] = []

    visited: set[tuple[int, int]] = set()

    current = first_fragment
    expected_seq = 0
    list_id: int | None = None
    remaining_nodes: int | None = None

    for _ in range(4096):
        key = (current.stp, current.cb)
        if key in visited:
            raise OneStoreFormatError("FileNodeList fragment chain contains a loop", offset=current.stp)
        visited.add(key)

        frag = FileNodeListFragment.parse(reader, current, remaining_nodes=remaining_nodes, ctx=ctx)

        if frag.header.fragment_sequence != expected_seq:
            raise OneStoreFormatError(
                "FileNodeListFragment sequence mismatch",
                offset=frag.fcr.stp,
            )

        if list_id is None:
            list_id = frag.header.list_id
            if last_count_by_list_id is not None and list_id in last_count_by_list_id:
                remaining_nodes = int(last_count_by_list_id[list_id])
            else:
                remaining_nodes = None
        else:
            if frag.header.list_id != list_id:
                raise OneStoreFormatError("FileNodeListID mismatch across fragments", offset=frag.fcr.stp + 8)

        fragments.append(frag)

        # Append non-terminator nodes only.
        for n in frag.file_nodes:
            if not n.is_chunk_terminator:
                nodes.append(n)

        if remaining_nodes is not None:
            remaining_nodes -= frag.node_count
            if remaining_nodes <= 0:
                # Once the committed count is reached, nextFragment MUST be ignored.
                break

        if frag.found_chunk_terminator:
            # Terminator indicates list continues; nextFragment MUST be valid.
            if frag.next_fragment.is_nil() or frag.next_fragment.is_zero() or frag.next_fragment.cb == 0:
                raise OneStoreFormatError(
                    "ChunkTerminatorFND requires a valid nextFragment",
                    offset=frag.fcr.stp,
                )
            frag.next_fragment.validate_in_file(file_size)
            current = frag.next_fragment
            expected_seq += 1
            continue

        # No terminator: this should be the last fragment of the list.
        if not frag.next_fragment.is_nil():
            # Some files may use fcrZero as end marker, but spec prefers fcrNil.
            if frag.next_fragment.is_zero() or frag.next_fragment.cb == 0:
                break
            frag.next_fragment.validate_in_file(file_size)
            current = frag.next_fragment
            expected_seq += 1
            continue

        break
    else:
        raise OneStoreFormatError("FileNodeList fragment chain is unexpectedly long", offset=first_fragment.stp)

    if list_id is None:
        raise OneStoreFormatError("FileNodeList has no fragments", offset=first_fragment.stp)

    return FileNodeList(
        list_id=int(list_id),
        fragments=tuple(fragments),
        file_nodes=tuple(nodes),
        node_count=len(nodes),
    )


def parse_file_node_list_with_raw(
    reader: BinaryReader,
    first_fragment: FileChunkReference64x32,
    *,
    last_count_by_list_id: dict[int, int] | None = None,
    ctx: ParseContext | None = None,
) -> FileNodeListWithRaw:
    """Parse a File Node List (2.4) and also capture raw bytes per node.

    This keeps the same control flow and bounds validations as parse_file_node_list,
    but additionally returns raw node bytes (header+payload) for each non-terminator
    node that was included in the committed-count-limited output.
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    if reader.bounds.start != 0:
        raise OneStoreFormatError("FileNodeList must be parsed from file start", offset=reader.bounds.start)

    file_size = reader.bounds.end
    if ctx.file_size is None:
        ctx.file_size = file_size
    else:
        file_size = ctx.file_size

    first_fragment.validate_in_file(file_size)

    fragments: list[FileNodeListFragment] = []
    nodes: list[FileNodeHeader] = []
    raw_nodes: list[FileNodeRaw] = []

    visited: set[tuple[int, int]] = set()

    current = first_fragment
    expected_seq = 0
    list_id: int | None = None
    remaining_nodes: int | None = None

    for _ in range(4096):
        key = (current.stp, current.cb)
        if key in visited:
            raise OneStoreFormatError("FileNodeList fragment chain contains a loop", offset=current.stp)
        visited.add(key)

        frag = FileNodeListFragment.parse(
            reader,
            current,
            remaining_nodes=remaining_nodes,
            capture_node_bytes=True,
            ctx=ctx,
        )

        if frag.header.fragment_sequence != expected_seq:
            raise OneStoreFormatError(
                "FileNodeListFragment sequence mismatch",
                offset=frag.fcr.stp,
            )

        if list_id is None:
            list_id = frag.header.list_id
            if last_count_by_list_id is not None and list_id in last_count_by_list_id:
                remaining_nodes = int(last_count_by_list_id[list_id])
            else:
                remaining_nodes = None
        else:
            if frag.header.list_id != list_id:
                raise OneStoreFormatError("FileNodeListID mismatch across fragments", offset=frag.fcr.stp + 8)

        fragments.append(frag)

        for rn in frag.raw_nodes:
            if not rn.header.is_chunk_terminator:
                nodes.append(rn.header)
                raw_nodes.append(rn)

        if remaining_nodes is not None:
            remaining_nodes -= frag.node_count
            if remaining_nodes <= 0:
                break

        if frag.found_chunk_terminator:
            if frag.next_fragment.is_nil() or frag.next_fragment.is_zero() or frag.next_fragment.cb == 0:
                raise OneStoreFormatError(
                    "ChunkTerminatorFND requires a valid nextFragment",
                    offset=frag.fcr.stp,
                )
            frag.next_fragment.validate_in_file(file_size)
            current = frag.next_fragment
            expected_seq += 1
            continue

        if not frag.next_fragment.is_nil():
            if frag.next_fragment.is_zero() or frag.next_fragment.cb == 0:
                break
            frag.next_fragment.validate_in_file(file_size)
            current = frag.next_fragment
            expected_seq += 1
            continue

        break
    else:
        raise OneStoreFormatError("FileNodeList fragment chain is unexpectedly long", offset=first_fragment.stp)

    if list_id is None:
        raise OneStoreFormatError("FileNodeList has no fragments", offset=first_fragment.stp)

    base_list = FileNodeList(
        list_id=int(list_id),
        fragments=tuple(fragments),
        file_nodes=tuple(nodes),
        node_count=len(nodes),
    )

    return FileNodeListWithRaw(list=base_list, raw_nodes=tuple(raw_nodes))


def parse_file_node_list_nodes(
    reader: BinaryReader,
    first_fragment: FileChunkReference64x32,
    *,
    last_count_by_list_id: dict[int, int] | None = None,
    ctx: ParseContext | None = None,
) -> FileNodeListWithNodes:
    """Parse a File Node List (2.4) and parse each node via the generic FileNode core parser."""

    if ctx is None:
        ctx = ParseContext(strict=True)

    if reader.bounds.start != 0:
        raise OneStoreFormatError("FileNodeList must be parsed from file start", offset=reader.bounds.start)

    # First pass: collect the list structure + node raw bytes.
    out = parse_file_node_list_with_raw(
        reader,
        first_fragment,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    warn_once: set[int] = set()
    nodes: list[FileNode] = []
    for rn in out.raw_nodes:
        node_reader = reader.view(rn.header.offset, rn.header.size)
        nodes.append(parse_file_node(node_reader, ctx=ctx, warn_unknown_ids=warn_once))

    return FileNodeListWithNodes(list=out.list, nodes=tuple(nodes))


def parse_file_node_list_typed_nodes(
    reader: BinaryReader,
    first_fragment: FileChunkReference64x32,
    *,
    last_count_by_list_id: dict[int, int] | None = None,
    ctx: ParseContext | None = None,
) -> FileNodeListWithTypedNodes:
    """Parse a File Node List (2.4) and route FileNodes into known typed structures.

    This does not change the existing core parsing behavior; it builds on top of
    parse_file_node_list_with_raw and parse_file_node.

    Unknown FileNodeIDs produce a warning (once per id) and keep raw bytes.
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    if reader.bounds.start != 0:
        raise OneStoreFormatError("FileNodeList must be parsed from file start", offset=reader.bounds.start)

    out = parse_file_node_list_with_raw(
        reader,
        first_fragment,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    warn_once: set[int] = set()
    typed_nodes: list[TypedFileNode] = []
    for rn in out.raw_nodes:
        node_reader = reader.view(rn.header.offset, rn.header.size)
        node = parse_file_node(node_reader, ctx=ctx)
        tn = parse_typed_file_node(node, ctx=ctx, warn_unknown_ids=warn_once)
        typed_nodes.append(TypedFileNode(node=tn.node, typed=tn.typed, raw_bytes=rn.raw_bytes))

    return FileNodeListWithTypedNodes(list=out.list, nodes=tuple(typed_nodes))
