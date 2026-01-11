from __future__ import annotations

from dataclasses import dataclass, replace
import re
import uuid
from pathlib import PurePath
from typing import cast

from onestore.common_types import CompactID, ExtendedGUID
from onestore.file_data import parse_file_data_reference
from onestore.parse_context import ParseContext
from onestore.chunk_refs import FileNodeChunkReference

from ..compact_id import EffectiveGidTable, resolve_compact_id_array
from ..compact_id import resolve_compact_id
from ..object_index import ObjectIndex, ObjectRecord
from ..property_access import get_bytes, get_oid, get_oid_array, get_prop
from ..spec_ids import (
    JCID_EMBEDDED_FILE_NODE_INDEX,
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
    PID_FONT_SIZE,
    PID_NOTE_TAG_COMPLETED,
    PID_NOTE_TAG_CREATED,
    PID_NOTE_TAG_DEFINITION_OID,
    PID_NOTE_TAG_HIGHLIGHT_COLOR,
    PID_NOTE_TAG_LABEL,
    PID_NOTE_TAG_SHAPE,
    PID_NOTE_TAG_STATES,
    PID_NOTE_TAG_STATES_ALT,
    PID_NOTE_TAG_TEXT_COLOR,
    PID_PAGE_SERIES_CHILD_NODES,
    PID_RICH_EDIT_TEXT_UNICODE,
    PID_SECTION_DISPLAY_NAME,
    PID_TEXT_EXTENDED_ASCII,
    PID_TEXT_RUN_DATA_OBJECT,
    PID_TEXT_RUN_FORMATTING,
 )
from ..types import decode_text_extended_ascii, decode_wz_in_atom

from .base import BaseNode, UnknownNode
from .structure import (
    EmbeddedFile,
    Image,
    NoteTag,
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


def _u16_from_bytes(b: bytes | None) -> int | None:
    if b is None or len(b) < 2:
        return None
    return int.from_bytes(b[:2], "little", signed=False)


def _u32_from_bytes(b: bytes | None) -> int | None:
    if b is None or len(b) < 4:
        return None
    return int.from_bytes(b[:4], "little", signed=False)


def _first_font_size_pt_from_text_run_formatting(rec: ObjectRecord, *, state: "ParseState") -> float | None:
    """Best-effort font size for a RichText paragraph.

    Uses TextRunFormatting -> ParagraphStyleObject(s) -> FontSize (half-points).
    """

    if rec.properties is None:
        return None

    refs = get_oid_array(rec.properties, PID_TEXT_RUN_FORMATTING)
    if not refs:
        return None

    for oid in refs:
        if not isinstance(oid, ExtendedGUID):
            continue
        style_rec = state.index.get(oid)
        if style_rec is None or style_rec.properties is None:
            continue
        half_points = _u16_from_bytes(get_bytes(style_rec.properties, PID_FONT_SIZE))
        if half_points is None:
            continue
        return float(half_points) / 2.0

    return None


def _extract_note_tags(rec: ObjectRecord, *, state: "ParseState") -> tuple[NoteTag, ...]:
    return _extract_note_tags_from_properties(rec.properties, state=state)


def _extract_note_tags_from_properties(props, *, state: "ParseState") -> tuple[NoteTag, ...]:
    if props is None:
        return ()

    def _get_prop_by_low16(pset, low16: int):
        try:
            for p in pset.properties:
                if (int(p.prid.raw) & 0xFFFF) == (low16 & 0xFFFF):
                    return p
        except Exception:
            return None
        return None

    def _bytes_value(p) -> bytes | None:
        if p is None:
            return None
        v = getattr(p, "value", None)
        if isinstance(v, (bytes, bytearray, memoryview)):
            return bytes(v)
        return None

    def _iter_psets(value):
        stack = [value]
        while stack:
            cur = stack.pop()
            if cur is None:
                continue
            if isinstance(cur, tuple):
                stack.extend(list(cur))
                continue
            if hasattr(cur, "properties"):
                yield cur
                try:
                    stack.extend([p.value for p in cur.properties])
                except Exception:
                    pass

    # NoteTagStates may appear multiple times in a single PropertySet.
    # Each occurrence may hold one or more nested tag-state PropertySet(s).
    tag_states: list[object] = []
    for prop in props.properties:
        pid = int(prop.prid.raw)
        if (pid & 0xFFFF) != (PID_NOTE_TAG_STATES & 0xFFFF):
            continue
        v = prop.value
        if v is None:
            continue
        for pset in _iter_psets(v):
            # Heuristic: a tag-state set should contain the definition OID or timestamps.
            try:
                has_state = (
                    _get_prop_by_low16(pset, PID_NOTE_TAG_DEFINITION_OID) is not None
                    or _get_prop_by_low16(pset, PID_NOTE_TAG_CREATED) is not None
                    or _get_prop_by_low16(pset, PID_NOTE_TAG_COMPLETED) is not None
                )
            except Exception:
                has_state = False
            if has_state:
                tag_states.append(pset)

    if not tag_states:
        return ()

    tags: list[NoteTag] = []
    for tag_state in tag_states:
        if not hasattr(tag_state, "properties"):
            continue

        # State fields.
        definition_oid = None
        def_p = _get_prop_by_low16(tag_state, PID_NOTE_TAG_DEFINITION_OID)  # type: ignore[arg-type]
        oid_v = def_p.value if def_p is not None else None
        if isinstance(oid_v, ExtendedGUID):
            definition_oid = oid_v
        elif oid_v is not None:
            # CompactID fallback.
            try:
                definition_oid = resolve_compact_id(oid_v, state.gid_table, ctx=state.ctx)
            except Exception:
                definition_oid = None

        created_p = _get_prop_by_low16(tag_state, PID_NOTE_TAG_CREATED)  # type: ignore[arg-type]
        completed_p = _get_prop_by_low16(tag_state, PID_NOTE_TAG_COMPLETED)  # type: ignore[arg-type]
        created = _u32_from_bytes(_bytes_value(created_p))
        completed = _u32_from_bytes(_bytes_value(completed_p))

        shape = None
        label = None
        text_color = None
        highlight_color = None

        # Definition fields (best-effort).
        if definition_oid is not None:
            def_rec = state.index.get(definition_oid)
            if def_rec is not None and def_rec.properties is not None:
                shape_p = _get_prop_by_low16(def_rec.properties, PID_NOTE_TAG_SHAPE)
                shape = _u16_from_bytes(_bytes_value(shape_p))
                label_p = _get_prop_by_low16(def_rec.properties, PID_NOTE_TAG_LABEL)
                label_b = _bytes_value(label_p)
                if label_b is not None:
                    try:
                        label = decode_wz_in_atom(label_b, ctx=state.ctx)
                    except Exception:
                        label = None
                text_p = _get_prop_by_low16(def_rec.properties, PID_NOTE_TAG_TEXT_COLOR)
                hi_p = _get_prop_by_low16(def_rec.properties, PID_NOTE_TAG_HIGHLIGHT_COLOR)
                text_color = _u32_from_bytes(_bytes_value(text_p))
                highlight_color = _u32_from_bytes(_bytes_value(hi_p))

        tags.append(
            NoteTag(
                shape=shape,
                label=label,
                text_color=text_color,
                highlight_color=highlight_color,
                created=created,
                completed=completed,
            )
        )

    # Deduplicate while preserving order.
    seen: set[tuple[object, ...]] = set()
    out: list[NoteTag] = []
    for t in tags:
        k = (t.label, t.shape, t.created, t.completed, t.text_color, t.highlight_color)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)

    return tuple(out)


def _merge_tags(existing: tuple[NoteTag, ...], inherited: tuple[NoteTag, ...]) -> tuple[NoteTag, ...]:
    if not inherited:
        return existing
    if not existing:
        return inherited
    out: list[NoteTag] = list(existing)
    seen = set(existing)
    for t in inherited:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return tuple(out)


def _extract_embedded_objects_from_richtext(rt: RichText, *, state: "ParseState") -> tuple[BaseNode, ...]:
    """Extract embedded objects referenced from a RichText node.

    Some files store images/attachments as embedded objects referenced via TextRunDataObject
    rather than as separate content children.
    """

    props = rt.raw_properties
    if props is None:
        return ()

    refs = get_oid_array(props, PID_TEXT_RUN_DATA_OBJECT)
    if not refs:
        return ()

    out: list[BaseNode] = []
    seen: set[ExtendedGUID] = set()
    for oid in refs:
        if not isinstance(oid, ExtendedGUID):
            continue
        if oid in seen:
            continue
        seen.add(oid)
        out.append(parse_node(oid, state))

    return tuple(out)


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
        children_a = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        children_b = _children_from_pid(rec, PID_CONTENT_CHILD_NODES, state)
        if children_b:
            merged: list[BaseNode] = []
            seen: set[ExtendedGUID] = set()
            for ch in list(children_a) + list(children_b):
                if ch.oid in seen:
                    continue
                seen.add(ch.oid)
                merged.append(ch)
            children = tuple(merged)
        else:
            children = children_a
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
        children_a = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        children_b = _children_from_pid(rec, PID_CONTENT_CHILD_NODES, state)
        if children_b:
            merged: list[BaseNode] = []
            seen: set[ExtendedGUID] = set()
            for ch in list(children_a) + list(children_b):
                if ch.oid in seen:
                    continue
                seen.add(ch.oid)
                merged.append(ch)
            children = tuple(merged)
        else:
            children = children_a
        # Heuristic: some files keep outline element refs under a different property ID.
        # Scan all tuple-of-OID properties and merge any that mostly point at OutlineElement.
        if rec.properties is not None:
            existing_oe_oids: set[ExtendedGUID] = set(ch.oid for ch in children if isinstance(ch, OutlineElement))

            best_oids: tuple[ExtendedGUID, ...] | None = None
            best_hits = 0
            for prop in rec.properties.properties:
                v = prop.value
                if not (isinstance(v, tuple) and v and isinstance(v[0], ExtendedGUID)):
                    continue

                hits = 0
                new_hits = 0
                for x in v:
                    rr = state.index.get(x)
                    if rr is not None and rr.jcid is not None and int(rr.jcid.index) == JCID_OUTLINE_ELEMENT_NODE_INDEX:
                        hits += 1
                        if x not in existing_oe_oids:
                            new_hits += 1

                # Prefer properties that add new OutlineElement references.
                score = (new_hits, hits)
                best_score = (0, best_hits)
                if score > best_score:
                    best_hits = hits
                    best_oids = v

            if best_oids is not None and best_hits > 0:
                guessed = [parse_node(x, state) for x in best_oids]
                extra = [ch for ch in guessed if isinstance(ch, OutlineElement) and ch.oid not in existing_oe_oids]
                if extra:
                    children = tuple(list(children) + extra)

        return Outline(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_OUTLINE_ELEMENT_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        content_children = _children_from_pid(rec, PID_CONTENT_CHILD_NODES, state)

        tags = _extract_note_tags_from_properties(rec.properties, state=state)

        # Append embedded objects referenced from RichText runs.
        extra: list[BaseNode] = []
        seen_oids: set[ExtendedGUID] = set()
        for n in content_children:
            if hasattr(n, "oid") and isinstance(getattr(n, "oid"), ExtendedGUID):
                seen_oids.add(getattr(n, "oid"))
        for n in content_children:
            if isinstance(n, RichText):
                for emb in _extract_embedded_objects_from_richtext(n, state=state):
                    if emb.oid in seen_oids:
                        continue
                    seen_oids.add(emb.oid)
                    extra.append(emb)

        if extra:
            content_children = tuple(list(content_children) + extra)

        # Some files store tags on the OutlineElement container rather than the embedded object.
        # Propagate container tags to embedded objects to match OneNote UI expectations.
        if tags:
            propagated: list[BaseNode] = []
            for ch in content_children:
                if isinstance(ch, (EmbeddedFile, Image, Table)):
                    try:
                        propagated.append(replace(ch, tags=_merge_tags(ch.tags, tags)))
                        continue
                    except Exception:
                        pass
                propagated.append(ch)
            content_children = tuple(propagated)

        return OutlineElement(
            oid=oid,
            jcid_index=jidx,
            raw_properties=rec.properties,
            children=children,
            content_children=content_children,
            tags=tags,
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
        font_size_pt = _first_font_size_pt_from_text_run_formatting(rec, state=state)
        tags = _extract_note_tags(rec, state=state)
        return RichText(
            oid=oid,
            jcid_index=jidx,
            raw_properties=rec.properties,
            text=text,
            font_size_pt=font_size_pt,
            tags=tags,
        )

    if jidx == JCID_IMAGE_NODE_INDEX:
        # Alt text PID_IMAGE_ALT_TEXT exists in spec but not added to spec_ids v1.
        file_data_guids = _resolve_file_data_store_guids_via_references(rec, state=state)
        file_names = _resolve_file_names_via_references(rec, state=state)
        tags = _extract_note_tags_from_properties(rec.properties, state=state)
        return Image(
            oid=oid,
            jcid_index=jidx,
            raw_properties=rec.properties,
            alt_text=None,
            original_filename=file_names[0] if file_names else None,
            file_data_guids=file_data_guids,
            tags=tags,
        )

    if jidx == JCID_EMBEDDED_FILE_NODE_INDEX:
        file_data_guids = _resolve_file_data_store_guids_via_references(rec, state=state)
        file_names = _resolve_file_names_via_references(rec, state=state)
        tags = _extract_note_tags_from_properties(rec.properties, state=state)
        return EmbeddedFile(
            oid=oid,
            jcid_index=jidx,
            raw_properties=rec.properties,
            original_filename=file_names[0] if file_names else None,
            file_data_guids=file_data_guids,
            tags=tags,
        )

    if jidx == JCID_TABLE_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        tags = _extract_note_tags_from_properties(rec.properties, state=state)
        return Table(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children, tags=tags)

    if jidx == JCID_TABLE_ROW_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        return TableRow(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_TABLE_CELL_NODE_INDEX:
        children = _children_from_pid(rec, PID_ELEMENT_CHILD_NODES, state)
        return TableCell(oid=oid, jcid_index=jidx, raw_properties=rec.properties, children=children)

    if jidx == JCID_SECTION_METADATA_INDEX:
        return SectionMetaData(oid=oid, jcid_index=jidx, raw_properties=rec.properties, raw=rec.properties)

    return UnknownNode(oid=oid, jcid_index=jidx, raw_properties=rec.properties)
