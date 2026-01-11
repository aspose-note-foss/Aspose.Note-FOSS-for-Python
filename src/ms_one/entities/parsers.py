from __future__ import annotations

from dataclasses import dataclass
import re
import uuid
from pathlib import PurePath
from typing import cast

from onestore.common_types import CompactID, ExtendedGUID
from onestore.file_data import parse_file_data_reference
from onestore.parse_context import ParseContext
from onestore.chunk_refs import FileNodeChunkReference

from ..compact_id import EffectiveGidTable, resolve_compact_id_array
from ..object_index import ObjectIndex, ObjectRecord
from ..property_access import get_bytes, get_oid_array
from ..spec_ids import (
    JCID_IMAGE_NODE_INDEX,
    JCID_OUTLINE_ELEMENT_NODE_INDEX,
    JCID_OUTLINE_NODE_INDEX,
    JCID_PAGE_MANIFEST_NODE_INDEX,
    JCID_PAGE_NODE_INDEX,
    JCID_PAGE_METADATA_INDEX,
    JCID_PAGE_SERIES_NODE_INDEX,
    JCID_RICH_TEXT_OE_NODE_INDEX,
    JCID_SECTION_METADATA_INDEX,
    JCID_SECTION_NODE_INDEX,
    JCID_TABLE_CELL_NODE_INDEX,
    JCID_TABLE_NODE_INDEX,
    JCID_TABLE_ROW_NODE_INDEX,
    JCID_TITLE_NODE_INDEX,
    PID_CACHED_TITLE_STRING,
    PID_CACHED_TITLE_STRING_FROM_PAGE,
    PID_CONTENT_CHILD_NODES,
    PID_ELEMENT_CHILD_NODES,
    PID_PAGE_SERIES_CHILD_NODES,
    PID_RICH_EDIT_TEXT_UNICODE,
    PID_SECTION_DISPLAY_NAME,
    PID_TEXT_EXTENDED_ASCII,
 )
from ..types import decode_text_extended_ascii, decode_wz_in_atom

from .base import BaseNode, UnknownNode
from .structure import (
    Image,
    Outline,
    OutlineElement,
    Page,
    PageManifest,
    PageMetaData,
    PageSeries,
    RichText,
    Section,
    SectionMetaData,
    Table,
    TableCell,
    TableRow,
    Title,
)


_IFNDF_GUID_RE = re.compile(r"<ifndf>\{(?P<guid>[0-9a-fA-F\-]{36})\}</ifndf>")


def _iter_property_bytes(value) -> "list[bytes]":
    out: list[bytes] = []
    stack = [value]
    while stack:
        cur = stack.pop()
        if cur is None:
            continue
        if isinstance(cur, bytes):
            out.append(cur)
            continue
        if isinstance(cur, tuple):
            stack.extend(list(cur))
            continue
        # DecodedPropertySet
        if hasattr(cur, "properties"):
            try:
                stack.extend([p.value for p in cur.properties])
            except Exception:
                pass
    return out


def _iter_property_scalars(value):
    """Yield all scalar values inside a DecodedPropertySet/tuple tree."""

    stack = [value]
    while stack:
        cur = stack.pop()
        if cur is None:
            continue
        if isinstance(cur, tuple):
            stack.extend(list(cur))
            continue
        if hasattr(cur, "properties"):
            try:
                stack.extend([p.value for p in cur.properties])
            except Exception:
                pass
            continue
        yield cur


def _extract_ifndf_guids_from_properties(props) -> tuple[str, ...]:
    if props is None:
        return ()

    found: set[str] = set()
    for b in _iter_property_bytes(props):
        # ASCII scan
        if b"<ifndf>" in b:
            try:
                s = b.decode("ascii", errors="ignore")
            except Exception:
                s = ""
            for m in _IFNDF_GUID_RE.finditer(s):
                try:
                    found.add(str(uuid.UUID(m.group("guid"))))
                except Exception:
                    continue

        # UTF-16LE scan
        if b"<\x00i\x00f\x00n\x00d\x00f\x00" in b:
            s = b.decode("utf-16le", errors="ignore")
            for m in _IFNDF_GUID_RE.finditer(s):
                try:
                    found.add(str(uuid.UUID(m.group("guid"))))
                except Exception:
                    continue

    return tuple(sorted(found))


def _extract_file_data_store_guids_from_properties(
    props,
    *,
    file_data_store_index: dict[bytes, FileNodeChunkReference] | None,
) -> tuple[str, ...]:
    """Extract FileDataStore GUIDs from properties.

    - Prefer explicit `<ifndf>{GUID}</ifndf>` strings.
    - If a FileDataStore index is available, also match raw 16-byte GUID values
      against known GUID keys to avoid false positives.
    """

    explicit = set(_extract_ifndf_guids_from_properties(props))
    if props is None or file_data_store_index is None:
        return tuple(sorted(explicit))

    keys = set(file_data_store_index.keys())
    matched: set[str] = set(explicit)
    for b in _iter_property_bytes(props):
        if len(b) < 16:
            continue
        for i in range(0, len(b) - 15):
            chunk = b[i : i + 16]
            if chunk in keys:
                try:
                    matched.add(str(uuid.UUID(bytes_le=bytes(chunk))))
                except Exception:
                    continue

    return tuple(sorted(matched))


def _resolve_file_data_store_guids_via_references(
    record: ObjectRecord,
    *,
    state: "ParseState",
    max_depth: int = 4,
    max_nodes: int = 200,
) -> tuple[str, ...]:
    """Best-effort resolver for Image file-data GUIDs.

    Some files don't keep the `<ifndf>` reference on the Image node itself.
    In that case, follow ExtendedGUID references to reachable objects and scan
    their properties for FileDataStore GUIDs.
    """

    # Always include anything we can extract locally.
    local = set(
        _extract_file_data_store_guids_from_properties(
            record.properties,
            file_data_store_index=state.file_data_store_index,
        )
    )
    if local:
        return tuple(sorted(local))

    if state.file_data_store_index is None:
        return ()

    visited: set[ExtendedGUID] = set()
    queue: list[tuple[ExtendedGUID, int]] = []

    # Seed with any ExtendedGUID references directly on the Image node.
    if record.properties is not None:
        for v in _iter_property_scalars(record.properties):
            if isinstance(v, ExtendedGUID):
                queue.append((v, 1))

    found: set[str] = set(local)
    steps = 0
    while queue and steps < max_nodes:
        steps += 1
        oid, depth = queue.pop(0)
        if oid in visited:
            continue
        visited.add(oid)

        rec = state.index.get(oid)
        if rec is None or rec.properties is None:
            continue

        found.update(
            _extract_file_data_store_guids_from_properties(
                rec.properties,
                file_data_store_index=state.file_data_store_index,
            )
        )

        if depth >= max_depth:
            continue

        for v in _iter_property_scalars(rec.properties):
            if isinstance(v, ExtendedGUID) and v not in visited:
                queue.append((v, depth + 1))

    return tuple(sorted(found))


_FILE_REF_ASCII_RE = re.compile(rb"<file>[^<\r\n]{1,4096}")
_FILE_REF_TEXT_RE = re.compile(r"<file>[^<\r\n]{1,4096}")
_IMAGE_FILENAME_TEXT_RE = re.compile(r"(?i)(?:^|[^A-Za-z0-9_.-])(?P<name>[A-Za-z0-9][A-Za-z0-9 _()\-\.]{0,254}\.(?:png|jpe?g|gif|bmp|tiff?))(?:$|[^A-Za-z0-9_.-])")


def _extract_file_names_from_properties(props) -> tuple[str, ...]:
    """Extract original file names from `<file>...` references in properties.

    References can appear as ASCII/UTF-8 bytes or as UTF-16LE strings.
    """

    if props is None:
        return ()

    found: set[str] = set()
    for b in _iter_property_bytes(props):
        # ASCII/UTF-8 scan
        if b"<file>" in b:
            for m in _FILE_REF_ASCII_RE.finditer(b):
                try:
                    s = m.group(0).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                parsed = parse_file_data_reference(s)
                if parsed.kind == "file" and parsed.file_name:
                    found.add(parsed.file_name.strip())

        # UTF-16LE scan
        if b"<\x00f\x00i\x00l\x00e\x00>\x00" in b:
            s = b.decode("utf-16le", errors="ignore")
            for m in _FILE_REF_TEXT_RE.finditer(s):
                parsed = parse_file_data_reference(m.group(0))
                if parsed.kind == "file" and parsed.file_name:
                    found.add(parsed.file_name.strip())

        # Standalone filename scan (common for embedded images like 'Tulips.jpg').
        s16 = b.decode("utf-16le", errors="ignore")
        for m in _IMAGE_FILENAME_TEXT_RE.finditer(s16):
            found.add(m.group("name").strip())

        s8 = b.decode("utf-8", errors="ignore")
        for m in _IMAGE_FILENAME_TEXT_RE.finditer(s8):
            found.add(m.group("name").strip())

    # Normalize to basename when a full path is stored.
    normalized: set[str] = set()
    for name in found:
        base = PurePath(name).name
        normalized.add(base or name)

    return tuple(sorted(n for n in normalized if n))


def _resolve_file_names_via_references(
    record: ObjectRecord,
    *,
    state: "ParseState",
    max_depth: int = 4,
    max_nodes: int = 200,
) -> tuple[str, ...]:
    """Best-effort resolver for `<file>...` names.

    Some files store the `<file>` reference on an object reachable via
    ExtendedGUID references rather than on the Image node itself.
    """

    local = set(_extract_file_names_from_properties(record.properties))
    if local:
        return tuple(sorted(local))

    visited: set[ExtendedGUID] = set()
    queue: list[tuple[ExtendedGUID, int]] = []

    if record.properties is not None:
        for v in _iter_property_scalars(record.properties):
            if isinstance(v, ExtendedGUID):
                queue.append((v, 1))

    found: set[str] = set(local)
    steps = 0
    while queue and steps < max_nodes:
        steps += 1
        oid, depth = queue.pop(0)
        if oid in visited:
            continue
        visited.add(oid)

        rec = state.index.get(oid)
        if rec is None or rec.properties is None:
            continue

        found.update(_extract_file_names_from_properties(rec.properties))

        if depth >= max_depth:
            continue

        for v in _iter_property_scalars(rec.properties):
            if isinstance(v, ExtendedGUID) and v not in visited:
                queue.append((v, depth + 1))

    return tuple(sorted(found))


@dataclass(frozen=True, slots=True)
class ParseState:
    index: ObjectIndex
    gid_table: EffectiveGidTable | None
    ctx: ParseContext
    file_data_store_index: dict[bytes, FileNodeChunkReference] | None = None


def _children_from_pid(record: ObjectRecord, pid_raw: int, state: ParseState) -> tuple[BaseNode, ...]:
    if record.properties is None:
        return ()
    oids = get_oid_array(record.properties, pid_raw)
    if not oids:
        return ()
    if oids and isinstance(oids[0], ExtendedGUID):
        resolved = cast(tuple[ExtendedGUID, ...], oids)
    else:
        resolved = resolve_compact_id_array(cast(tuple[CompactID, ...], oids), state.gid_table, ctx=state.ctx)
    out: list[BaseNode] = []
    for oid in resolved:
        child = parse_node(oid, state)
        out.append(child)
    return tuple(out)


def _wz_prop(record: ObjectRecord, pid_raw: int, state: ParseState) -> str | None:
    if record.properties is None:
        return None
    b = get_bytes(record.properties, pid_raw)
    if b is None:
        return None
    return decode_wz_in_atom(b, ctx=state.ctx)


def parse_node(oid: ExtendedGUID, state: ParseState) -> BaseNode:
    rec = state.index.get(oid)
    if rec is None or rec.jcid is None:
        return UnknownNode(oid=oid, jcid_index=-1, raw_properties=None)

    jidx = int(rec.jcid.index)

    # Structural nodes (tree)
    if jidx == JCID_SECTION_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        display = _wz_prop(rec, PID_SECTION_DISPLAY_NAME, state)
        return Section(oid=oid, jcid_index=jidx, raw_properties=rec.properties, display_name=display, children=children)

    if jidx == JCID_PAGE_SERIES_NODE_INDEX:
        children = _children_from_pid(rec, PID_PAGE_SERIES_CHILD_NODES, state)
        return PageSeries(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_PAGE_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        title = _wz_prop(rec, PID_CACHED_TITLE_STRING, state) or _wz_prop(rec, PID_CACHED_TITLE_STRING_FROM_PAGE, state)
        return Page(oid=oid, jcid_index=jidx, raw_properties=rec.properties, title=title, children=children)

    # Some files (e.g. SimpleTable.one) expose pages via PageMetaData entries referenced from PageSeries.
    # For v1 extraction, treat PageMetaData as a Page leaf (title only).
    if jidx == JCID_PAGE_METADATA_INDEX:
        title = _wz_prop(rec, PID_CACHED_TITLE_STRING, state) or _wz_prop(rec, PID_CACHED_TITLE_STRING_FROM_PAGE, state)
        return Page(oid=oid, jcid_index=jidx, raw_properties=rec.properties, title=title, children=())

    if jidx == JCID_TITLE_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        return Title(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_OUTLINE_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        return Outline(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_OUTLINE_ELEMENT_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        content_children = _children_from_pid(rec, PID_CONTENT_CHILD_NODES, state)
        return OutlineElement(
            oid=oid,
            jcid_index=jidx,
            raw_properties=rec.properties,
            children=children,
            content_children=content_children,
        )

    if jidx == JCID_PAGE_MANIFEST_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        content_children = _children_from_pid(rec, PID_CONTENT_CHILD_NODES, state)
        return PageManifest(
            oid=oid,
            jcid_index=jidx,
            raw_properties=rec.properties,
            children=children,
            content_children=content_children,
        )

    if jidx == JCID_RICH_TEXT_OE_NODE_INDEX:
        text = _wz_prop(rec, PID_RICH_EDIT_TEXT_UNICODE, state)
        if text is None and rec.properties is not None:
            b = get_bytes(rec.properties, PID_TEXT_EXTENDED_ASCII)
            if b is not None:
                text = decode_text_extended_ascii(b, ctx=state.ctx)
        return RichText(oid=oid, jcid_index=jidx, raw_properties=rec.properties, text=text)

    if jidx == JCID_IMAGE_NODE_INDEX:
        # Alt text PID_IMAGE_ALT_TEXT exists in spec but not added to spec_ids v1.
        file_data_guids = _resolve_file_data_store_guids_via_references(rec, state=state)
        file_names = _resolve_file_names_via_references(rec, state=state)
        return Image(
            oid=oid,
            jcid_index=jidx,
            raw_properties=rec.properties,
            alt_text=None,
            original_filename=file_names[0] if file_names else None,
            file_data_guids=file_data_guids,
        )

    if jidx == JCID_TABLE_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        return Table(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_TABLE_ROW_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        return TableRow(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_TABLE_CELL_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        return TableCell(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_SECTION_METADATA_INDEX:
        return SectionMetaData(oid=oid, jcid_index=jidx, raw_properties=rec.properties, raw=rec.properties)

    return UnknownNode(oid=oid, jcid_index=jidx, raw_properties=rec.properties)
