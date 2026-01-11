from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from onestore.common_types import CompactID, ExtendedGUID
from onestore.parse_context import ParseContext

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


@dataclass(frozen=True, slots=True)
class ParseState:
    index: ObjectIndex
    gid_table: EffectiveGidTable | None
    ctx: ParseContext


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
        return Image(oid=oid, jcid_index=jidx, raw_properties=rec.properties, alt_text=None)

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
