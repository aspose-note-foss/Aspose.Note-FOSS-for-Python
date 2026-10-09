from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
import struct
import uuid

from ...exceptions import FileCorruptedException, UnsupportedFileFormatException

STP_SIZES = {0: 8, 1: 4, 2: 2, 3: 4}
CB_SIZES = {0: 4, 1: 8, 2: 1, 3: 2}
FILE_NODE_LIST_MAGIC = 0xA4567AB1F5F7F4C4
FILE_NODE_LIST_FOOTER_MAGIC = 0x8BC215C38233BA4B
SECTION_FILE_TYPE = "7b5c52e4-d88c-4da7-aeb1-5378d02996d3"

PROPERTY_NAMES: dict[int, str] = {
    0x1C01: "PageWidth",
    0x1C02: "PageHeight",
    0x1C03: "OutlineElementChildLevel",
    0x1C04: "Bold",
    0x1C05: "Italic",
    0x1C06: "Underline",
    0x1C07: "Strikethrough",
    0x1C08: "Superscript",
    0x1C09: "Subscript",
    0x1C0A: "Font",
    0x1C0B: "FontSize",
    0x1C0C: "FontColor",
    0x1C0D: "Highlight",
    0x1C14: "OffsetFromParentHoriz",
    0x1C15: "OffsetFromParentVert",
    0x1C1A: "NumberListFormat",
    0x1C1B: "LayoutMaxWidth",
    0x1C1C: "LayoutMaxHeight",
    0x1C1F: "ContentChildNodes",
    0x1C20: "ElementChildNodes",
    0x1C22: "RichEditTextUnicode",
    0x1C26: "ListNodes",
    0x1C30: "NotebookManagementEntityGuid",
    0x1C3B: "LanguageID",
    0x1C3E: "LayoutAlignmentInParent",
    0x1C3F: "PictureContainer",
    0x1C65: "TopologyCreationTimeStamp",
    0x1C84: "LayoutAlignmentSelf",
    0x1C87: "IsTitleTime",
    0x1C88: "IsBoilerText",
    0x1CB4: "IsTitleText",
    0x1CB5: "IsTitleDate",
    0x1CB7: "ListRestart",
    0x1CF3: "CachedTitleString",
    0x1CFE: "RichEditTextLangID",
    0x1D09: "CreationTimeStamp",
    0x1D3C: "CachedTitleStringFromPage",
    0x1D57: "RowCount",
    0x1D58: "ColumnCount",
    0x1D5E: "TableBordersVisible",
    0x1D5F: "StructureElementChildNodes",
    0x1D63: "ChildGraphSpaceElementNodes",
    0x1D66: "TableColumnWidths",
    0x1D75: "Author",
    0x1D77: "LastModifiedTimeStamp",
    0x1D78: "AuthorOriginal",
    0x1D79: "AuthorMostRecent",
    0x1D7A: "LastModifiedTime",
    0x1D9B: "EmbeddedFileContainer",
    0x1D9C: "EmbeddedFileName",
    0x1D9D: "SourceFilepath",
    0x1DD7: "ImageFilename",
    0x1DFF: "PageLevel",
    0x1E12: "TextRunIndex",
    0x1E13: "TextRunFormatting",
    0x1E14: "Hyperlink",
    0x1E20: "WzHyperlinkUrl",
    0x1E58: "ImageAltText",
    0x342C: "ParagraphStyle",
    0x3442: "MetaDataObjectsAboveGraphSpace",
    0x3458: "TextRunDataObject",
    0x3498: "TextExtendedAscii",
    0x3499: "TextRunData",
    0x345A: "ParagraphStyleId",
    0x3462: "HasVersionPages",
    0x3463: "ActionItemType",
    0x3464: "NoteTagShape",
    0x3465: "NoteTagHighlightColor",
    0x3466: "NoteTagTextColor",
    0x3467: "NoteTagPropertyStatus",
    0x3468: "NoteTagLabel",
    0x346E: "NoteTagCreated",
    0x346F: "NoteTagCompleted",
    0x3470: "ActionItemStatus",
    0x3473: "ActionItemSchemaVersion",
    0x3477: "ParagraphAlignment",
    0x347B: "VersionHistoryGraphSpaceContextNodes",
    0x3480: "DisplayedPageNumber",
    0x3488: "NoteTagDefinitionOid",
    0x3489: "NoteTagStates",
    0x349B: "SectionDisplayName",
    0x34C8: "WebPictureContainer14",
    0x34CD: "PictureWidth",
    0x34CE: "PictureHeight",
}

PROPERTY_TYPE_OVERRIDES_RAW: dict[int, int] = {
    0x3400347B: 0x11,
}

JCID_NAMES: dict[int, str] = {
    0x0001: "ReadOnlyPersistablePropertyContainerForAuthor",
    0x0007: "SectionNode",
    0x0008: "PageSeriesNode",
    0x000B: "PageNode",
    0x000C: "OutlineNode",
    0x000D: "OutlineElementNode",
    0x000E: "RichTextOENode",
    0x0011: "ImageNode",
    0x0012: "NumberListNode",
    0x0019: "OutlineGroup",
    0x0022: "TableNode",
    0x0023: "TableRowNode",
    0x0024: "TableCellNode",
    0x002C: "TitleNode",
    0x0030: "PageMetaData",
    0x0031: "SectionMetaData",
    0x0035: "EmbeddedFileNode",
    0x0037: "PageManifestNode",
    0x0038: "ConflictPageMetaData",
    0x003C: "VersionHistoryContent",
    0x003D: "VersionProxy",
    0x0043: "NoteTagSharedDefinitionContainer",
    0x0044: "RevisionMetaData",
    0x0046: "VersionHistoryMetaData",
    0x004D: "ParagraphStyleObject",
}


@dataclass(frozen=True, slots=True)
class ExtendedGUID:
    guid: str
    n: int


@dataclass(frozen=True, slots=True)
class JCID:
    index: int
    IsBinary: bool
    IsPropertySet: bool
    IsGraphNode: bool
    IsFileData: bool
    IsReadOnly: bool


@dataclass(slots=True)
class FileNode:
    file_node_id: int
    payload: bytes
    stp_format: int
    cb_format: int
    base_type: int


@dataclass(slots=True)
class OneStoreObject:
    oid: ExtendedGUID
    jcid: JCID
    jcid_name: str
    properties: dict[str, Any]
    raw_properties: list[tuple[str, Any]]
    file_data_reference: str | None = None
    file_extension: str | None = None


@dataclass(slots=True)
class RevisionManifestRecord:
    rid: ExtendedGUID
    rid_dependent: ExtendedGUID | None
    context_id: ExtendedGUID | None
    root_roles: dict[int, ExtendedGUID] = field(default_factory=dict)
    objects: dict[ExtendedGUID, OneStoreObject] = field(default_factory=dict)
    section_display_name: str | None = None
    order_index: int = 0


@dataclass(slots=True)
class RevisionRoleBinding:
    rid: ExtendedGUID
    context_id: ExtendedGUID | None
    role: int
    order_index: int


@dataclass(slots=True)
class ObjectSpaceState:
    gosid: ExtendedGUID
    root_roles: dict[int, ExtendedGUID] = field(default_factory=dict)
    objects: dict[ExtendedGUID, OneStoreObject] = field(default_factory=dict)
    section_display_name: str | None = None
    revisions: list[RevisionManifestRecord] = field(default_factory=list)
    role_bindings: list[RevisionRoleBinding] = field(default_factory=list)
    latest_roots_by_context_role: dict[tuple[ExtendedGUID | None, int], ExtendedGUID] = field(default_factory=dict)
    latest_revision_indices_by_context_role: dict[tuple[ExtendedGUID | None, int], int] = field(default_factory=dict)

    def get_latest_root(self, role: int, context_id: ExtendedGUID | None = None) -> ExtendedGUID | None:
        if self.latest_roots_by_context_role:
            return self.latest_roots_by_context_role.get((context_id, role))
        if context_id is None:
            return self.root_roles.get(role)
        return None

    def iter_latest_roots(self, role: int) -> list[tuple[ExtendedGUID | None, ExtendedGUID]]:
        if not self.latest_roots_by_context_role:
            root = self.root_roles.get(role)
            return [] if root is None else [(None, root)]
        result: list[tuple[ExtendedGUID | None, ExtendedGUID]] = []
        for (context_id, current_role), root in self.latest_roots_by_context_role.items():
            if current_role == role:
                result.append((context_id, root))
        return result

    def get_latest_revision_index(self, role: int, context_id: ExtendedGUID | None = None) -> int | None:
        if self.latest_revision_indices_by_context_role:
            return self.latest_revision_indices_by_context_role.get((context_id, role))
        for index in range(len(self.revisions) - 1, -1, -1):
            revision = self.revisions[index]
            if revision.context_id != context_id:
                continue
            if _resolve_revision_root(self, revision, role) is not None:
                return index
        return None


@dataclass(slots=True)
class OneStoreFile:
    data: bytes
    object_spaces: list[ObjectSpaceState]
    file_data_store: dict[str, bytes]
    display_name: str | None = None


@dataclass(slots=True)
class _PropertyState:
    object_ids: list[ExtendedGUID]
    oid_cursor: int = 0


def _read_guid(data: bytes, offset: int) -> str:
    chunk = data[offset : offset + 16]
    if len(chunk) < 16:
        # Best-effort: a truncated GUID in a corrupt file is zero-padded so
        # parsing continues instead of raising ValueError.
        chunk = chunk.ljust(16, b"\x00")
    return str(uuid.UUID(bytes_le=chunk))


def _read_extended_guid(data: bytes, offset: int) -> ExtendedGUID:
    return ExtendedGUID(_read_guid(data, offset), struct.unpack_from("<I", data, offset + 16)[0])


def _read_compact_id(data: bytes, offset: int) -> tuple[int, int]:
    raw = struct.unpack_from("<I", data, offset)[0]
    return raw >> 8, raw & 0xFF


def _read_jcid(raw: int) -> JCID:
    return JCID(
        index=raw & 0xFFFF,
        IsBinary=bool((raw >> 16) & 0x1),
        IsPropertySet=bool((raw >> 17) & 0x1),
        IsGraphNode=bool((raw >> 18) & 0x1),
        IsFileData=bool((raw >> 19) & 0x1),
        IsReadOnly=bool((raw >> 20) & 0x1),
    )


def _decode_chunk_reference(data: bytes, offset: int, stp_format: int, cb_format: int) -> tuple[int, int, int]:
    stp_size = STP_SIZES[stp_format]
    cb_size = CB_SIZES[cb_format]
    stp_raw = int.from_bytes(data[offset : offset + stp_size], "little")
    cb_raw = int.from_bytes(data[offset + stp_size : offset + stp_size + cb_size], "little")
    stp = stp_raw * 8 if stp_format >= 2 else stp_raw
    cb = cb_raw * 8 if cb_format >= 2 else cb_raw
    return stp, cb, stp_size + cb_size


def _merge_property(target: dict[str, Any], name: str, value: Any) -> None:
    if name not in target:
        target[name] = value
        return
    existing = target[name]
    if isinstance(existing, list):
        existing.append(value)
    else:
        target[name] = [existing, value]


def _resolve_object_id(compact_id: tuple[int, int], gid_table: dict[int, str]) -> ExtendedGUID | None:
    guid = gid_table.get(compact_id[0])
    if guid is None:
        return None
    return ExtendedGUID(guid, compact_id[1])


def _parse_scalar_from_array(data: bytes, offset: int, property_type: int) -> tuple[Any, int]:
    if property_type == 0x3:
        return data[offset], offset + 1
    if property_type == 0x4:
        return struct.unpack_from("<H", data, offset)[0], offset + 2
    if property_type == 0x5:
        return struct.unpack_from("<I", data, offset)[0], offset + 4
    if property_type == 0x6:
        return struct.unpack_from("<Q", data, offset)[0], offset + 8
    if property_type == 0x7:
        cb = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        return bytes(data[offset : offset + cb]), offset + cb
    return None, offset


def _parse_property_set(data: bytes, offset: int, state: _PropertyState) -> tuple[dict[str, Any], list[tuple[str, Any]], int]:
    start = offset
    if offset + 2 > len(data):
        return {}, [], 0
    property_count = struct.unpack_from("<H", data, offset)[0]
    offset += 2
    # Best-effort: clamp to the property ids actually present so a truncated
    # declaration does not read past the end of the buffer.
    available_property_ids = max((len(data) - offset) // 4, 0)
    if property_count > available_property_ids:
        property_count = available_property_ids
    property_ids = [struct.unpack_from("<I", data, offset + index * 4)[0] for index in range(property_count)]
    offset += property_count * 4
    data_offset = offset
    properties: dict[str, Any] = {}
    raw_properties: list[tuple[str, Any]] = []

    for raw_property_id in property_ids:
        property_id = raw_property_id & 0x03FFFFFF
        default_property_type = (raw_property_id >> 26) & 0x1F
        property_type = PROPERTY_TYPE_OVERRIDES_RAW.get(raw_property_id, default_property_type)
        name = PROPERTY_NAMES.get(property_id, hex(property_id))

        def read_value(selected_type: int) -> Any:
            nonlocal data_offset
            if selected_type == 0x2:
                return bool((raw_property_id >> 31) & 0x1)
            if selected_type == 0x3:
                value_inner = data[data_offset]
                data_offset += 1
                return value_inner
            if selected_type == 0x4:
                value_inner = struct.unpack_from("<H", data, data_offset)[0]
                data_offset += 2
                return value_inner
            if selected_type == 0x5:
                value_inner = struct.unpack_from("<I", data, data_offset)[0]
                data_offset += 4
                return value_inner
            if selected_type == 0x6:
                value_inner = struct.unpack_from("<Q", data, data_offset)[0]
                data_offset += 8
                return value_inner
            if selected_type == 0x7:
                cb = struct.unpack_from("<I", data, data_offset)[0]
                data_offset += 4
                value_inner = bytes(data[data_offset : data_offset + cb])
                data_offset += cb
                return value_inner
            if selected_type == 0x8:
                value_inner = state.object_ids[state.oid_cursor] if state.oid_cursor < len(state.object_ids) else None
                state.oid_cursor += 1
                return value_inner
            if selected_type == 0x9:
                count = struct.unpack_from("<I", data, data_offset)[0]
                data_offset += 4
                value_inner = state.object_ids[state.oid_cursor : state.oid_cursor + count]
                state.oid_cursor += count
                return value_inner
            if selected_type == 0x10:
                count = struct.unpack_from("<I", data, data_offset)[0]
                data_offset += 4
                items: list[Any] = []
                if count:
                    array_property_id = struct.unpack_from("<I", data, data_offset)[0]
                    data_offset += 4
                    array_type = PROPERTY_TYPE_OVERRIDES_RAW.get(array_property_id, (array_property_id >> 26) & 0x1F)
                    if array_type == 0x11:
                        for _ in range(count):
                            child_props, _, consumed = _parse_property_set(data, data_offset, state)
                            items.append(child_props)
                            data_offset += consumed
                    else:
                        for _ in range(count):
                            item, data_offset = _parse_scalar_from_array(data, data_offset, array_type)
                            items.append(item)
                return items
            if selected_type == 0x11:
                value_inner, _, consumed = _parse_property_set(data, data_offset, state)
                data_offset += consumed
                return value_inner
            return None

        snapshot_offset = data_offset
        snapshot_oid_cursor = state.oid_cursor
        try:
            value = read_value(property_type)
        except Exception:
            # Best-effort: on a truncated/corrupt buffer, retry with the declared
            # type when an override was applied, otherwise stop reading the rest
            # of the set instead of letting struct.error reach the caller.
            data_offset = snapshot_offset
            state.oid_cursor = snapshot_oid_cursor
            if property_type == default_property_type:
                break
            try:
                value = read_value(default_property_type)
            except Exception:
                data_offset = snapshot_offset
                state.oid_cursor = snapshot_oid_cursor
                break

        _merge_property(properties, name, value)
        raw_properties.append((name, value))

    return properties, raw_properties, data_offset - start


def _parse_object_blob(blob: bytes, gid_table: dict[int, str]) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    offset = 0
    header = struct.unpack_from("<I", blob, offset)[0]
    offset += 4
    oid_count = header & 0x00FFFFFF
    has_extended_streams = bool((header >> 30) & 0x1)
    no_osid_stream = bool((header >> 31) & 0x1)

    object_ids: list[ExtendedGUID] = []
    for index in range(oid_count):
        resolved = _resolve_object_id(_read_compact_id(blob, offset + index * 4), gid_table)
        if resolved is not None:
            object_ids.append(resolved)
    offset += oid_count * 4

    if not no_osid_stream:
        osid_header = struct.unpack_from("<I", blob, offset)[0]
        offset += 4
        osid_count = osid_header & 0x00FFFFFF
        osid_has_extended_streams = bool((osid_header >> 30) & 0x1)
        offset += osid_count * 4
        if osid_has_extended_streams:
            context_header = struct.unpack_from("<I", blob, offset)[0]
            offset += 4
            context_count = context_header & 0x00FFFFFF
            offset += context_count * 4
    elif has_extended_streams:
        # Defensive: malformed files occasionally preserve the flag even without OSIDs.
        pass

    state = _PropertyState(object_ids=object_ids)
    properties, raw_properties, _ = _parse_property_set(blob, offset, state)
    return properties, raw_properties


def _decode_storage_string(data: bytes, offset: int) -> tuple[str, int]:
    char_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    byte_count = char_count * 2
    if offset + byte_count > len(data):
        byte_count = char_count
    raw = bytes(data[offset : offset + byte_count])
    offset += byte_count
    return raw.decode("utf-16le", errors="ignore").rstrip("\x00"), offset


def _normalize_guid_token(value: str) -> str:
    return value.strip().strip("{}").lower()


def _parse_file_data_store_object(blob: bytes) -> bytes:
    if len(blob) < 52:
        return b""
    length = struct.unpack_from("<Q", blob, 16)[0]
    data_offset = 36
    return bytes(blob[data_offset : data_offset + length])


def _parse_file_node_list(data: bytes, start_offset: int, size: int) -> list[FileNode]:
    result: list[FileNode] = []
    current_offset = start_offset
    current_size = size

    while current_size:
        fragment = data[current_offset : current_offset + current_size]
        if len(fragment) < 24:
            break
        if struct.unpack_from("<Q", fragment, 0)[0] != FILE_NODE_LIST_MAGIC:
            raise FileCorruptedException("Invalid FileNodeListFragment magic")

        offset = 16
        while offset + 4 <= len(fragment) - 20:
            header = struct.unpack_from("<I", fragment, offset)[0]
            file_node_id = header & 0x3FF
            node_size = (header >> 10) & 0x1FFF
            stp_format = (header >> 23) & 0x3
            cb_format = (header >> 25) & 0x3
            base_type = (header >> 27) & 0xF
            if node_size < 4 or offset + node_size > len(fragment) - 8:
                break
            result.append(
                FileNode(
                    file_node_id=file_node_id,
                    payload=bytes(fragment[offset + 4 : offset + node_size]),
                    stp_format=stp_format,
                    cb_format=cb_format,
                    base_type=base_type,
                )
            )
            offset += node_size
            if file_node_id == 0x0FF:
                break

        if struct.unpack_from("<Q", fragment, len(fragment) - 8)[0] != FILE_NODE_LIST_FOOTER_MAGIC:
            break
        next_offset = int.from_bytes(fragment[-20:-12], "little")
        next_size = int.from_bytes(fragment[-12:-8], "little")
        current_offset = next_offset
        current_size = next_size

    return result


def _parse_object_declaration(node: FileNode, gid_table: dict[int, str], data: bytes) -> OneStoreObject | None:
    payload = node.payload

    if node.file_node_id in {0x0A4, 0x0A5, 0x0C4, 0x0C5}:
        blob_offset, blob_size, ref_size = _decode_chunk_reference(payload, 0, node.stp_format, node.cb_format)
        oid = _resolve_object_id(_read_compact_id(payload, ref_size), gid_table)
        if oid is None:
            return None
        jcid = _read_jcid(struct.unpack_from("<I", payload, ref_size + 4)[0])
        properties, raw_properties = _parse_object_blob(data[blob_offset : blob_offset + blob_size], gid_table)
        return OneStoreObject(
            oid=oid,
            jcid=jcid,
            jcid_name=JCID_NAMES.get(jcid.index, hex(jcid.index)),
            properties=properties,
            raw_properties=raw_properties,
        )

    if node.file_node_id in {0x072, 0x073}:
        offset = 0
        oid = _resolve_object_id(_read_compact_id(payload, offset), gid_table)
        if oid is None:
            return None
        offset += 4
        jcid = _read_jcid(struct.unpack_from("<I", payload, offset)[0])
        offset += 4
        offset += 4 if node.file_node_id == 0x073 else 1
        file_data_reference, offset = _decode_storage_string(payload, offset)
        file_extension, offset = _decode_storage_string(payload, offset)
        return OneStoreObject(
            oid=oid,
            jcid=jcid,
            jcid_name=JCID_NAMES.get(jcid.index, hex(jcid.index)),
            properties={},
            raw_properties=[],
            file_data_reference=file_data_reference,
            file_extension=file_extension,
        )

    return None


def _process_group(data: bytes, state: ObjectSpaceState, group_ref: tuple[int, int], gid_table: dict[int, str]) -> None:
    local_gid_table = dict(gid_table)
    for node in _parse_file_node_list(data, group_ref[0], group_ref[1]):
        if node.file_node_id == 0x024:
            index = struct.unpack_from("<I", node.payload, 0)[0]
            local_gid_table[index] = _read_guid(node.payload, 4)
            continue
        if node.file_node_id == 0x025:
            source = struct.unpack_from("<I", node.payload, 0)[0]
            target = struct.unpack_from("<I", node.payload, 4)[0]
            if source in local_gid_table:
                local_gid_table[target] = local_gid_table[source]
            continue
        if node.file_node_id == 0x026:
            source_start, count, target_start = struct.unpack_from("<III", node.payload, 0)
            for index in range(count):
                source = source_start + index
                if source in local_gid_table:
                    local_gid_table[target_start + index] = local_gid_table[source]
            continue
        if node.file_node_id not in {0x0A4, 0x0A5, 0x0C4, 0x0C5, 0x072, 0x073}:
            continue
        parsed = _parse_object_declaration(node, local_gid_table, data)
        if parsed is not None:
            state.objects[parsed.oid] = parsed
            if parsed.jcid_name == "SectionMetaData" and "SectionDisplayName" in parsed.properties:
                value = parsed.properties["SectionDisplayName"]
                if isinstance(value, bytes):
                    state.section_display_name = value.decode("utf-16le", errors="ignore").rstrip("\x00") or state.section_display_name


def _process_revision_manifest(data: bytes, gosid: ExtendedGUID, nodes: list[FileNode], order_index: int) -> RevisionManifestRecord | None:
    gid_table: dict[int, str] = {}
    temporary_state = ObjectSpaceState(gosid=gosid)
    revision: RevisionManifestRecord | None = None

    for node in nodes:
        if node.file_node_id in {0x01B, 0x01E, 0x01F}:
            rid = _read_extended_guid(node.payload, 0)
            rid_dependent = _read_extended_guid(node.payload, 20) if len(node.payload) >= 40 else None
            context_id = _read_extended_guid(node.payload, 40) if node.file_node_id == 0x01F and len(node.payload) >= 60 else None
            revision = RevisionManifestRecord(
                rid=rid,
                rid_dependent=rid_dependent,
                context_id=context_id,
                order_index=order_index,
            )
        elif node.file_node_id == 0x024:
            index = struct.unpack_from("<I", node.payload, 0)[0]
            gid_table[index] = _read_guid(node.payload, 4)
        elif node.file_node_id == 0x025:
            source = struct.unpack_from("<I", node.payload, 0)[0]
            target = struct.unpack_from("<I", node.payload, 4)[0]
            if source in gid_table:
                gid_table[target] = gid_table[source]
        elif node.file_node_id == 0x026:
            source_start, count, target_start = struct.unpack_from("<III", node.payload, 0)
            for index in range(count):
                source = source_start + index
                if source in gid_table:
                    gid_table[target_start + index] = gid_table[source]
        elif node.file_node_id == 0x05A:
            if revision is None:
                continue
            root = _read_extended_guid(node.payload, 0)
            role = struct.unpack_from("<I", node.payload, 20)[0]
            revision.root_roles[role] = root
        elif node.file_node_id == 0x059:
            if revision is None:
                continue
            compact_id = _read_compact_id(node.payload, 0)
            root = _resolve_object_id(compact_id, gid_table)
            role = struct.unpack_from("<I", node.payload, 4)[0]
            if root is not None:
                revision.root_roles[role] = root
        elif node.file_node_id == 0x0B0:
            if revision is None:
                continue
            group_offset, group_size, _ = _decode_chunk_reference(node.payload, 0, node.stp_format, node.cb_format)
            _process_group(data, temporary_state, (group_offset, group_size), gid_table)

    if revision is None:
        return None

    revision.objects = temporary_state.objects
    revision.section_display_name = temporary_state.section_display_name
    return revision


def _is_zero_extended_guid(value: ExtendedGUID | None) -> bool:
    return value is None or (value.guid == "00000000-0000-0000-0000-000000000000" and value.n == 0)


def _iter_revision_chain(state: ObjectSpaceState, revision: RevisionManifestRecord) -> list[RevisionManifestRecord]:
    revision_by_rid = {item.rid: item for item in state.revisions}
    chain: list[RevisionManifestRecord] = []
    seen: set[ExtendedGUID] = set()
    current: RevisionManifestRecord | None = revision
    while current is not None and current.rid not in seen:
        seen.add(current.rid)
        chain.append(current)
        if _is_zero_extended_guid(current.rid_dependent):
            break
        current = revision_by_rid.get(current.rid_dependent)
    chain.reverse()
    return chain


def _effective_revision_roots(state: ObjectSpaceState, revision: RevisionManifestRecord) -> dict[int, ExtendedGUID]:
    roots: dict[int, ExtendedGUID] = {}
    for item in _iter_revision_chain(state, revision):
        roots.update(item.root_roles)
    return roots


def _resolve_revision_root(state: ObjectSpaceState, revision: RevisionManifestRecord, role: int) -> ExtendedGUID | None:
    return _effective_revision_roots(state, revision).get(role)


def _build_revision_snapshot(state: ObjectSpaceState, revision: RevisionManifestRecord) -> dict[ExtendedGUID, OneStoreObject]:
    snapshot: dict[ExtendedGUID, OneStoreObject] = {}
    for item in _iter_revision_chain(state, revision):
        snapshot.update(item.objects)
    return snapshot


def _materialize_latest_roots(state: ObjectSpaceState) -> None:
    latest: dict[tuple[ExtendedGUID | None, int], ExtendedGUID] = {}
    revision_by_rid = {revision.rid: revision for revision in state.revisions}
    revision_index_by_rid = {revision.rid: index for index, revision in enumerate(state.revisions)}
    latest_revision_indices: dict[tuple[ExtendedGUID | None, int], int] = {}
    ordered_events: list[tuple[int, str, object]] = []

    for revision in state.revisions:
        ordered_events.append((revision.order_index, "revision", revision))
    for binding in state.role_bindings:
        ordered_events.append((binding.order_index, "binding", binding))

    for _, kind, payload in sorted(ordered_events, key=lambda item: item[0]):
        if kind == "revision":
            revision = payload
            assert isinstance(revision, RevisionManifestRecord)
            revision_index = revision_index_by_rid[revision.rid]
            for role, root in _effective_revision_roots(state, revision).items():
                latest[(revision.context_id, role)] = root
                latest_revision_indices[(revision.context_id, role)] = revision_index
            continue

        binding = payload
        assert isinstance(binding, RevisionRoleBinding)
        revision = revision_by_rid.get(binding.rid)
        if revision is None:
            continue
        root = _resolve_revision_root(state, revision, binding.role)
        if root is not None:
            latest[(binding.context_id, binding.role)] = root
            latest_revision_indices[(binding.context_id, binding.role)] = revision_index_by_rid[revision.rid]

    state.latest_roots_by_context_role = latest
    state.latest_revision_indices_by_context_role = latest_revision_indices
    state.root_roles = {role: root for (context_id, role), root in latest.items() if context_id is None}


def _process_revision_manifest_list(data: bytes, state: ObjectSpaceState, nodes: list[FileNode]) -> None:
    current_manifest: list[FileNode] | None = None
    order_index = 0

    for node in nodes:
        if node.file_node_id in {0x01B, 0x01E, 0x01F}:
            current_manifest = [node]
            continue

        if current_manifest is not None:
            current_manifest.append(node)
            if node.file_node_id == 0x01C:
                revision = _process_revision_manifest(data, state.gosid, current_manifest, order_index)
                if revision is not None:
                    state.revisions.append(revision)
                    if state.section_display_name is None and revision.section_display_name:
                        state.section_display_name = revision.section_display_name
                order_index += 1
                current_manifest = None
            continue

        if node.file_node_id == 0x05C:
            rid = _read_extended_guid(node.payload, 0)
            role = struct.unpack_from("<I", node.payload, 20)[0]
            state.role_bindings.append(RevisionRoleBinding(rid=rid, context_id=None, role=role, order_index=order_index))
            order_index += 1
        elif node.file_node_id == 0x05D:
            rid = _read_extended_guid(node.payload, 0)
            role = struct.unpack_from("<I", node.payload, 20)[0]
            context_id = _read_extended_guid(node.payload, 24)
            state.role_bindings.append(RevisionRoleBinding(rid=rid, context_id=context_id, role=role, order_index=order_index))
            order_index += 1

    _materialize_latest_roots(state)
    preferred_revision_index = state.get_latest_revision_index(1)
    if preferred_revision_index is None and state.revisions:
        preferred_revision_index = len(state.revisions) - 1
    if preferred_revision_index is not None:
        preferred_revision = state.revisions[preferred_revision_index]
        state.objects = _build_revision_snapshot(state, preferred_revision)


def _parse_object_space(data: bytes, gosid: ExtendedGUID, list_ref: tuple[int, int]) -> ObjectSpaceState:
    state = ObjectSpaceState(gosid=gosid)
    manifest_nodes = _parse_file_node_list(data, list_ref[0], list_ref[1])
    for node in manifest_nodes:
        if node.file_node_id != 0x010:
            continue
        revision_offset, revision_size, _ = _decode_chunk_reference(node.payload, 0, node.stp_format, node.cb_format)
        revision_nodes = _parse_file_node_list(data, revision_offset, revision_size)
        _process_revision_manifest_list(data, state, revision_nodes)
    return state


def _process_file_data_store_list(data: bytes, file_data_store: dict[str, bytes], ref: tuple[int, int]) -> None:
    for node in _parse_file_node_list(data, ref[0], ref[1]):
        if node.file_node_id != 0x094:
            continue
        blob_offset, blob_size, ref_size = _decode_chunk_reference(node.payload, 0, node.stp_format, node.cb_format)
        guid_reference = _normalize_guid_token(_read_guid(node.payload, ref_size))
        file_data_store[guid_reference] = _parse_file_data_store_object(data[blob_offset : blob_offset + blob_size])


def parse_onestore_file(source: str | Path | BinaryIO) -> OneStoreFile:
    if isinstance(source, (str, Path)):
        path = Path(source)
        data = path.read_bytes()
        display_name = path.stem
    else:
        data = source.read()
        display_name = None

    if len(data) < 1024:
        raise FileCorruptedException("File is too small to be a OneNote section")

    file_type_guid = _read_guid(data, 0)
    if file_type_guid.lower() != SECTION_FILE_TYPE:
        raise UnsupportedFileFormatException(file_format=file_type_guid)

    root_offset = struct.unpack_from("<Q", data, 172)[0]
    root_size = struct.unpack_from("<I", data, 180)[0]
    root_nodes = _parse_file_node_list(data, root_offset, root_size)

    file_data_store: dict[str, bytes] = {}
    object_spaces: list[ObjectSpaceState] = []

    for node in root_nodes:
        if node.file_node_id == 0x090:
            list_offset, list_size, _ = _decode_chunk_reference(node.payload, 0, node.stp_format, node.cb_format)
            _process_file_data_store_list(data, file_data_store, (list_offset, list_size))
        elif node.file_node_id == 0x008:
            list_offset, list_size, ref_size = _decode_chunk_reference(node.payload, 0, node.stp_format, node.cb_format)
            gosid = _read_extended_guid(node.payload, ref_size)
            object_spaces.append(_parse_object_space(data, gosid, (list_offset, list_size)))

    return OneStoreFile(data=data, object_spaces=object_spaces, file_data_store=file_data_store, display_name=display_name)