from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
import re
import struct

from ..onestore.parser import ExtendedGUID, OneStoreFile, OneStoreObject, parse_onestore_file
from ...enums import HorizontalAlignment
from .entities import LogicalDocument, LogicalNode
from ...model import (
    AttachedFile,
    Document,
    Image,
    NoteTag,
    NumberList,
    Outline,
    OutlineElement,
    ParagraphStyle,
    Page,
    RichText,
    Table,
    TableColumn,
    TableCell,
    TableRow,
    TextRun,
    TextStyle,
    Title,
    _filetime_to_datetime,
    _time32_to_datetime,
)

ROOT_ROLE_DEFAULT_CONTENT = 0x00000001
ROOT_ROLE_METADATA = 0x00000002
STRUCTURE_PROPERTIES = {
    "ElementChildNodes",
    "ContentChildNodes",
    "StructureElementChildNodes",
    "ChildGraphSpaceElementNodes",
    "ListNodes",
    "TextRunDataObject",
}
METADATA_PROPERTIES = {"MetaDataObjectsAboveGraphSpace"}
PUBLIC_CONTAINER_KINDS = {"SectionNode", "PageSeriesNode", "OutlineGroup", "PageManifestNode", "VersionHistoryContent", "VersionProxy"}


@dataclass(slots=True)
class LoadedOneNoteDocument:
    display_name: str | None
    logical_document: LogicalDocument
    pages: list[Page]
    page_histories: list[list[Page]]


@dataclass(slots=True)
class _BuiltPageEntry:
    oid: ExtendedGUID
    page: Page
    history: list[Page]
    notebook_guid: bytes | None
    topology_timestamp: int | None
    section_order: int | None
    space_order: int
    page_order: int


def _decode_utf16(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-16le", errors="ignore").rstrip("\x00") or None
    return str(value)


def _decode_ascii_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        for encoding in ("utf-8", "latin-1"):
            try:
                return value.decode(encoding, errors="ignore").rstrip("\x00") or None
            except Exception:
                continue
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _u32_to_float(value: int | None) -> float | None:
    if value is None:
        return None
    return struct.unpack("<f", struct.pack("<I", int(value)))[0]


def _bytes_to_float_list(value: Any) -> list[float]:
    if not isinstance(value, (bytes, bytearray)):
        return []
    result: list[float] = []
    for offset in range(0, len(value) - (len(value) % 4), 4):
        result.append(struct.unpack("<f", value[offset : offset + 4])[0])
    return result


def _decode_paragraph_alignment(value: Any) -> HorizontalAlignment | None:
    if not isinstance(value, int):
        return None
    return {
        0: HorizontalAlignment.Left,
        1: HorizontalAlignment.Center,
        2: HorizontalAlignment.Right,
    }.get(value)


def _decode_layout_alignment(value: Any) -> HorizontalAlignment | None:
    if not isinstance(value, int) or value == 0:
        return None
    horizontal_alignment = value & 0x7
    return {
        1: HorizontalAlignment.Left,
        2: HorizontalAlignment.Center,
        3: HorizontalAlignment.Right,
        4: HorizontalAlignment.Left,
        5: HorizontalAlignment.Right,
    }.get(horizontal_alignment)


def _flatten_refs(value: Any) -> list[ExtendedGUID]:
    if isinstance(value, ExtendedGUID):
        return [value]
    if isinstance(value, list):
        result: list[ExtendedGUID] = []
        for item in value:
            result.extend(_flatten_refs(item))
        return result
    if isinstance(value, dict):
        result: list[ExtendedGUID] = []
        for item in value.values():
            result.extend(_flatten_refs(item))
        return result
    return []


def _decode_number_list_format(value: Any) -> str | None:
    text = _decode_utf16(value)
    if text:
        return text
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return None


def _unique_tags(tags: list[NoteTag]) -> list[NoteTag]:
    seen: set[tuple[Any, ...]] = set()
    result: list[NoteTag] = []
    for tag in tags:
        key = (tag.Label, tag.Icon, tag.FontColor, tag.Highlight, tag.CreationTime, tag.CompletedTime)
        if key in seen:
            continue
        seen.add(key)
        result.append(tag)
    return result


class _Builder:
    def __init__(self, parsed: OneStoreFile, include_page_history: bool = False) -> None:
        self.parsed = parsed
        self.include_page_history = include_page_history
        self._snapshot_cache: dict[int, dict[int, dict[ExtendedGUID, OneStoreObject]]] = {}
        self._revision_index_cache: dict[int, dict[ExtendedGUID, int]] = {}
        self.section_space = self._select_section_space(parsed)
        self.content_spaces = self._select_content_spaces(parsed)
        self.content_space = self.content_spaces[0] if self.content_spaces else self._select_content_space(parsed)
        self.space = self.content_space or self.section_space
        self.current_revision_index = None
        self.objects = self.space.objects if self.space is not None else {}
        self.current_revision_index = self._select_current_revision_index(self.space)
        self.objects = self._get_snapshot_objects(self.space, self.current_revision_index)

    def build(self) -> LoadedOneNoteDocument:
        logical_root = self._build_logical_root()
        page_entries = self._build_current_page_entries()
        pages = [entry.page for entry in page_entries]
        page_histories = [entry.history for entry in page_entries]
        display_name = None
        if self.section_space and self.section_space.section_display_name:
            display_name = self.section_space.section_display_name
        elif self.content_space and self.content_space.section_display_name:
            display_name = self.content_space.section_display_name
        else:
            display_name = self.parsed.display_name
        if display_name is None and pages:
            display_name = pages[0].Title.TitleText.Text if pages[0].Title and pages[0].Title.TitleText else None
        return LoadedOneNoteDocument(
            display_name=display_name,
            logical_document=LogicalDocument(logical_root),
            pages=pages,
            page_histories=page_histories,
        )

    def _run_in_space(self, space, revision_index: int | None, callback):
        saved_objects = self.objects
        saved_space = self.space
        saved_revision_index = self.current_revision_index
        try:
            self.space = space
            self.current_revision_index = revision_index
            self.objects = self._get_snapshot_objects(space, revision_index)
            return callback()
        finally:
            self.objects = saved_objects
            self.space = saved_space
            self.current_revision_index = saved_revision_index

    def _select_current_revision_index(self, space):
        if space is None or not getattr(space, "revisions", None):
            return None
        preferred = getattr(space, "get_latest_revision_index", lambda role: None)(ROOT_ROLE_DEFAULT_CONTENT)
        if preferred is not None and self._is_page_revision(space, preferred):
            return preferred
        for revision_index in range(len(space.revisions) - 1, -1, -1):
            if not self._is_page_revision(space, revision_index):
                continue
            if space.revisions[revision_index].context_id is None:
                return revision_index
        for revision_index in range(len(space.revisions) - 1, -1, -1):
            if self._is_page_revision(space, revision_index):
                return revision_index
        return len(space.revisions) - 1

    def _is_zero_extended_guid(self, value: ExtendedGUID | None) -> bool:
        return value is None or (value.guid == "00000000-0000-0000-0000-000000000000" and value.n == 0)

    def _get_revision_index_map(self, space) -> dict[ExtendedGUID, int]:
        if space is None:
            return {}
        return self._revision_index_cache.setdefault(id(space), {revision.rid: index for index, revision in enumerate(space.revisions)})

    def _get_parent_revision_index(self, space, revision_index: int) -> int | None:
        if space is None or not (0 <= revision_index < len(space.revisions)):
            return None
        dependent_rid = space.revisions[revision_index].rid_dependent
        if self._is_zero_extended_guid(dependent_rid):
            return None
        return self._get_revision_index_map(space).get(dependent_rid)

    def _revision_direct_root(self, space, revision_index: int) -> ExtendedGUID | None:
        if space is None or not (0 <= revision_index < len(space.revisions)):
            return None
        return space.revisions[revision_index].root_roles.get(ROOT_ROLE_DEFAULT_CONTENT)

    def _revision_direct_objects(self, space, revision_index: int) -> dict[ExtendedGUID, OneStoreObject]:
        if space is None or not (0 <= revision_index < len(space.revisions)):
            return {}
        return space.revisions[revision_index].objects

    def _is_page_revision(self, space, revision_index: int, direct_only: bool = False) -> bool:
        if space is None or not (0 <= revision_index < len(space.revisions)):
            return False
        if direct_only:
            root = self._revision_direct_root(space, revision_index)
            objects = self._revision_direct_objects(space, revision_index)
        else:
            root = self._get_snapshot_root(space, revision_index)
            objects = self._get_snapshot_objects(space, revision_index)
        if root is None:
            return False
        record = objects.get(root)
        return bool(record and record.jcid_name in {"PageManifestNode", "PageNode"})

    def _page_identity_from_objects(self, oid: ExtendedGUID, objects: dict[ExtendedGUID, OneStoreObject]) -> ExtendedGUID | bytes:
        record = objects.get(oid)
        if record is None:
            return oid
        notebook_guid = record.properties.get("NotebookManagementEntityGuid")
        if isinstance(notebook_guid, bytes) and notebook_guid:
            return notebook_guid
        return oid

    def _page_identity_keys_from_objects(self, oid: ExtendedGUID, objects: dict[ExtendedGUID, OneStoreObject]) -> tuple[ExtendedGUID | bytes, ...]:
        record = objects.get(oid)
        keys: list[ExtendedGUID | bytes] = [oid]
        if record is not None:
            notebook_guid = record.properties.get("NotebookManagementEntityGuid")
            if isinstance(notebook_guid, bytes) and notebook_guid:
                keys.append(notebook_guid)
        return tuple(keys)

    def _revision_last_modified_timestamp(self, space, revision_index: int) -> int | None:
        if space is None or not (0 <= revision_index < len(space.revisions)):
            return None
        for record in space.revisions[revision_index].objects.values():
            if record.jcid_name != "RevisionMetaData":
                continue
            value = record.properties.get("LastModifiedTimeStamp")
            if isinstance(value, int):
                return value
        return None

    def _get_snapshot_objects(self, space, revision_index: int | None) -> dict[ExtendedGUID, OneStoreObject]:
        if space is None:
            return {}
        if revision_index is not None and 0 <= revision_index < len(space.revisions):
            space_cache = self._snapshot_cache.setdefault(id(space), {})
            cached = space_cache.get(revision_index)
            if cached is not None:
                return cached
            parent_revision_index = self._get_parent_revision_index(space, revision_index)
            if parent_revision_index is None:
                merged = dict(space.revisions[revision_index].objects)
            else:
                merged = dict(self._get_snapshot_objects(space, parent_revision_index))
                merged.update(space.revisions[revision_index].objects)
            space_cache[revision_index] = merged
            return merged
        return space.objects

    def _get_snapshot_root(self, space, revision_index: int | None) -> ExtendedGUID | None:
        if space is None:
            return None
        if revision_index is not None and 0 <= revision_index < len(space.revisions):
            current_index: int | None = revision_index
            seen: set[int] = set()
            while current_index is not None and current_index not in seen:
                seen.add(current_index)
                root = space.revisions[current_index].root_roles.get(ROOT_ROLE_DEFAULT_CONTENT)
                if root is not None:
                    return root
                current_index = self._get_parent_revision_index(space, current_index)
        return space.get_latest_root(ROOT_ROLE_DEFAULT_CONTENT)

    def _page_text_signature(self, page: Page) -> str:
        parts: list[str] = []
        for rich_text in page.GetChildNodes(RichText):
            text = rich_text.Text.strip()
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _published_page_revision_indices(self) -> list[int]:
        if self.space is None:
            return []

        latest_root_entries = getattr(self.space, "iter_latest_roots", lambda role: [])(ROOT_ROLE_DEFAULT_CONTENT)
        candidates: list[tuple[int | None, int]] = []
        seen_indices: set[int] = set()
        for context_id, root in latest_root_entries:
            revision_index = getattr(self.space, "get_latest_revision_index", lambda role, ctx=None: None)(
                ROOT_ROLE_DEFAULT_CONTENT,
                context_id,
            )
            if revision_index is None or revision_index in seen_indices:
                continue
            revision_objects = self._get_snapshot_objects(self.space, revision_index)
            record = revision_objects.get(root)
            if record is None or record.jcid_name not in {"PageManifestNode", "PageNode"}:
                continue
            seen_indices.add(revision_index)
            timestamp = self._revision_last_modified_timestamp(self.space, revision_index)
            candidates.append((int(timestamp) if timestamp is not None else None, revision_index))

        candidates.sort(key=lambda item: (item[0] is None, item[0] if item[0] is not None else 0, item[1]))
        return [revision_index for _, revision_index in candidates]

    def _build_page_histories(self, current_page_pairs: list[tuple[ExtendedGUID, Page]]) -> list[list[Page]]:
        if not self.include_page_history or self.space is None or not current_page_pairs:
            return [[page] for _, page in current_page_pairs]

        if not getattr(self.space, "revisions", None):
            return [[page] for _, page in current_page_pairs]

        current_revision_index = self.current_revision_index
        if current_revision_index is None:
            return [[page] for _, page in current_page_pairs]

        histories_by_identity: dict[int, list[tuple[int | None, int, Page]]] = {id(page): [] for _, page in current_page_pairs}
        current_pages_by_key: dict[ExtendedGUID | bytes, int] = {}
        for oid, page in current_page_pairs:
            for key in self._page_identity_keys_from_objects(oid, self.objects):
                current_pages_by_key.setdefault(key, id(page))

        for revision_index in self._published_page_revision_indices():
            page_pairs = self._build_page_pairs_for_revision(self.space, revision_index)
            timestamp = self._revision_last_modified_timestamp(self.space, revision_index)
            revision_objects = self._get_snapshot_objects(self.space, revision_index)
            for oid, page in page_pairs:
                page_id = None
                for key in self._page_identity_keys_from_objects(oid, revision_objects):
                    page_id = current_pages_by_key.get(key)
                    if page_id is not None:
                        break
                if page_id is None:
                    continue
                histories_by_identity[page_id].append((int(timestamp) if timestamp is not None else None, revision_index, page))

        result: list[list[Page]] = []
        for oid, current_page in current_page_pairs:
            revisions = histories_by_identity.get(id(current_page), [])
            if not revisions:
                result.append([current_page])
                continue

            ordered_pages = [
                page
                for _, _, page in sorted(
                    revisions,
                    key=lambda item: (item[0] is None, item[0] if item[0] is not None else 0, item[1]),
                )
            ]
            unique: list[Page] = []
            last_signature: str | None = None
            for page in ordered_pages:
                signature = self._page_text_signature(page)
                if last_signature is None or signature != last_signature:
                    unique.append(page)
                    last_signature = signature

            if unique:
                unique[-1] = current_page
                result.append(unique)
            else:
                result.append([current_page])

        return result

    def _select_section_space(self, parsed: OneStoreFile):
        for space in parsed.object_spaces:
            root = space.get_latest_root(ROOT_ROLE_DEFAULT_CONTENT)
            if root is None:
                continue
            record = space.objects.get(root)
            if record and record.jcid_name == "SectionNode":
                return space
        return None

    def _select_content_space(self, parsed: OneStoreFile):
        best_space = None
        best_score = -1
        for space in parsed.object_spaces:
            snapshots = [space.objects]
            snapshots.extend(revision.objects for revision in getattr(space, "revisions", []))
            score = max(
                (
                    sum(
                        1
                        for obj in snapshot.values()
                        if obj.jcid_name in {"PageNode", "OutlineNode", "RichTextOENode", "ImageNode", "TableNode", "EmbeddedFileNode"}
                    )
                    for snapshot in snapshots
                ),
                default=0,
            )
            if score > best_score:
                best_space = space
                best_score = score
        return best_space or self._select_section_space(parsed)

    def _select_content_spaces(self, parsed: OneStoreFile) -> list:
        candidates: list[tuple[int, int, Any]] = []
        for index, space in enumerate(parsed.object_spaces):
            if space is self.section_space:
                continue
            revision_index = self._select_current_revision_index(space)
            if not self._is_page_revision(space, revision_index):
                continue
            snapshots = [space.objects]
            snapshots.extend(revision.objects for revision in getattr(space, "revisions", []))
            score = max(
                (
                    sum(
                        1
                        for obj in snapshot.values()
                        if obj.jcid_name in {"PageNode", "OutlineNode", "RichTextOENode", "ImageNode", "TableNode", "EmbeddedFileNode"}
                    )
                    for snapshot in snapshots
                ),
                default=0,
            )
            candidates.append((index, score, space))

        candidates.sort(key=lambda item: item[0])
        return [space for _, _, space in candidates]

    def _build_logical_root(self) -> LogicalNode | None:
        if self.space is None:
            return None
        root = self._get_snapshot_root(self.space, self.current_revision_index)
        if root is None:
            return None
        return self._build_logical_node(root, set())

    def _ordered_property_refs(self, record: OneStoreObject, allowed: set[str]) -> list[ExtendedGUID]:
        refs: list[ExtendedGUID] = []
        for name, value in record.raw_properties:
            if name not in allowed:
                continue
            refs.extend(_flatten_refs(value))
        return refs

    def _build_logical_node(self, oid: ExtendedGUID, stack: set[ExtendedGUID]) -> LogicalNode | None:
        record = self.objects.get(oid)
        if record is None:
            return None
        if oid in stack:
            return LogicalNode(kind=record.jcid_name, oid=oid, properties=record.properties)
        next_stack = set(stack)
        next_stack.add(oid)
        children = [child for child in (self._build_logical_node(ref, next_stack) for ref in self._ordered_property_refs(record, STRUCTURE_PROPERTIES)) if child is not None]
        metadata = [child for child in (self._build_logical_node(ref, next_stack) for ref in self._ordered_property_refs(record, METADATA_PROPERTIES)) if child is not None]
        return LogicalNode(kind=record.jcid_name, oid=oid, properties=record.properties, children=children, metadata=metadata)

    def _find_metadata_record(self, node: LogicalNode | None, kind: str) -> OneStoreObject | None:
        if node is None:
            return None
        for metadata in node.metadata:
            record = self.objects.get(metadata.oid)
            if record and record.jcid_name == kind:
                return record
        return None

    def _descendants(self, node: LogicalNode | None) -> list[LogicalNode]:
        if node is None:
            return []
        result: list[LogicalNode] = []
        stack = [node]
        while stack:
            current = stack.pop()
            result.append(current)
            stack.extend(reversed(current.children))
        return result

    def _build_page_pairs(self, root: LogicalNode | None) -> list[tuple[ExtendedGUID, Page]]:
        return [(oid, page) for oid, _, page in self._build_page_infos(root)]

    def _build_page_infos(self, root: LogicalNode | None) -> list[tuple[ExtendedGUID, LogicalNode, Page]]:
        pages: list[tuple[ExtendedGUID, LogicalNode, Page]] = []
        for node in self._descendants(root):
            if node.kind == "PageNode":
                pages.append((node.oid, node, self._build_page(node)))
        if pages:
            return pages

        page_nodes = [obj.oid for obj in self.objects.values() if obj.jcid_name == "PageNode"]
        for oid in page_nodes:
            logical_page = self._build_logical_node(oid, set())
            if logical_page is not None:
                pages.append((oid, logical_page, self._build_page(logical_page)))
        return pages

    def _build_page_infos_for_space(self, space, revision_index: int | None) -> list[tuple[ExtendedGUID, LogicalNode, Page]]:
        def build_page_infos() -> list[tuple[ExtendedGUID, LogicalNode, Page]]:
            root = self._get_snapshot_root(space, revision_index)
            logical_root = self._build_logical_node(root, set()) if root is not None else None
            return self._build_page_infos(logical_root)

        return self._run_in_space(space, revision_index, build_page_infos)

    def _build_page_histories_for_space(self, space, revision_index: int | None, page_pairs: list[tuple[ExtendedGUID, Page]]) -> list[list[Page]]:
        return self._run_in_space(space, revision_index, lambda: self._build_page_histories(page_pairs))

    def _page_metadata_candidates(self) -> list[OneStoreObject]:
        return [record for record in self.objects.values() if record.jcid_name == "PageMetaData"]

    def _page_metadata_from_node(self, node: LogicalNode) -> OneStoreObject | None:
        metadata = self._find_metadata_record(node, "PageMetaData")
        if metadata is not None:
            return metadata

        candidates = self._page_metadata_candidates()
        if len(candidates) == 1:
            return candidates[0]

        record = self.objects.get(node.oid)
        notebook_guid = record.properties.get("NotebookManagementEntityGuid") if record is not None else None
        if isinstance(notebook_guid, bytes) and notebook_guid:
            for candidate in candidates:
                if candidate.properties.get("NotebookManagementEntityGuid") == notebook_guid:
                    return candidate

        return None

    def _page_notebook_guid(self, node: LogicalNode) -> bytes | None:
        metadata = self._page_metadata_from_node(node)
        if metadata is not None:
            notebook_guid = metadata.properties.get("NotebookManagementEntityGuid")
            if isinstance(notebook_guid, bytes) and notebook_guid:
                return notebook_guid
        record = self.objects.get(node.oid)
        if record is not None:
            notebook_guid = record.properties.get("NotebookManagementEntityGuid")
            if isinstance(notebook_guid, bytes) and notebook_guid:
                return notebook_guid
        return None

    def _page_topology_timestamp(self, node: LogicalNode) -> int | None:
        metadata = self._page_metadata_from_node(node)
        if metadata is None:
            return None
        value = metadata.properties.get("TopologyCreationTimeStamp")
        return int(value) if isinstance(value, int) else None

    def _should_synthesize_page_title(self, node: LogicalNode) -> bool:
        metadata = self._find_metadata_record(node, "PageMetaData")
        if metadata is not None:
            return True

        section_orders = self._section_page_orders()
        if len(section_orders) > 1:
            return True

        return False

    def _section_page_orders(self) -> dict[bytes, int]:
        if self.section_space is None:
            return {}

        section_revision_index = self._select_current_revision_index(self.section_space)

        def collect_orders() -> dict[bytes, int]:
            root = self._get_snapshot_root(self.section_space, section_revision_index)
            logical_root = self._build_logical_node(root, set()) if root is not None else None
            result: dict[bytes, int] = {}
            next_order = 0
            for node in self._descendants(logical_root):
                if node.kind != "PageSeriesNode":
                    continue
                for metadata in node.metadata:
                    record = self.objects.get(metadata.oid)
                    if record is None or record.jcid_name != "PageMetaData":
                        continue
                    notebook_guid = record.properties.get("NotebookManagementEntityGuid")
                    if not isinstance(notebook_guid, bytes) or not notebook_guid or notebook_guid in result:
                        continue
                    result[notebook_guid] = next_order
                    next_order += 1
            return result

        return self._run_in_space(self.section_space, section_revision_index, collect_orders)

    def _build_current_page_entries(self) -> list[_BuiltPageEntry]:
        section_orders = self._section_page_orders()
        candidate_spaces = self.content_spaces or ([self.content_space] if self.content_space is not None else [])
        entries: list[_BuiltPageEntry] = []

        for space_order, space in enumerate(candidate_spaces):
            revision_index = self._select_current_revision_index(space)
            page_infos = self._build_page_infos_for_space(space, revision_index)
            if not page_infos:
                continue
            page_pairs = [(oid, page) for oid, _, page in page_infos]
            histories = self._build_page_histories_for_space(space, revision_index, page_pairs)
            for page_order, ((oid, logical_page, page), history) in enumerate(zip(page_infos, histories, strict=False)):
                notebook_guid = self._page_notebook_guid(logical_page)
                entries.append(
                    _BuiltPageEntry(
                        oid=oid,
                        page=page,
                        history=history,
                        notebook_guid=notebook_guid,
                        topology_timestamp=self._page_topology_timestamp(logical_page),
                        section_order=section_orders.get(notebook_guid) if notebook_guid is not None else None,
                        space_order=space_order,
                        page_order=page_order,
                    )
                )

        entries.sort(
            key=lambda entry: (
                entry.section_order is None,
                entry.section_order if entry.section_order is not None else 0,
                entry.space_order,
                entry.page_order,
            )
        )
        return entries

    def _build_page_pairs_for_revision(self, space, revision_index: int) -> list[tuple[ExtendedGUID, Page]]:
        saved_objects = self.objects
        saved_space = self.space
        saved_revision_index = self.current_revision_index
        try:
            self.space = space
            self.current_revision_index = revision_index
            self.objects = self._get_snapshot_objects(space, revision_index)
            root = self._get_snapshot_root(space, revision_index)
            logical_root = self._build_logical_node(root, set()) if root is not None else None
            return self._build_page_pairs(logical_root)
        finally:
            self.objects = saved_objects
            self.space = saved_space
            self.current_revision_index = saved_revision_index

    def _build_page_pairs_for_manifest_revision(self, space, revision_index: int) -> list[tuple[ExtendedGUID, Page]]:
        saved_objects = self.objects
        saved_space = self.space
        saved_revision_index = self.current_revision_index
        try:
            self.space = space
            self.current_revision_index = revision_index
            self.objects = self._revision_direct_objects(space, revision_index)
            root = self._revision_direct_root(space, revision_index)
            logical_root = self._build_logical_node(root, set()) if root is not None else None
            return self._build_page_pairs(logical_root)
        finally:
            self.objects = saved_objects
            self.space = saved_space
            self.current_revision_index = saved_revision_index

    def _build_page(self, node: LogicalNode) -> Page:
        page = Page()
        record = self.objects.get(node.oid)
        metadata = self._page_metadata_from_node(node)
        if record is not None:
            page.Author = _decode_utf16(record.properties.get("Author"))
            page.CreationTime = _time32_to_datetime(record.properties.get("CreationTimeStamp"))
            page.LastModifiedTime = _filetime_to_datetime(record.properties.get("LastModifiedTimeStamp")) or _time32_to_datetime(record.properties.get("LastModifiedTime"))
            level = record.properties.get("PageLevel")
            page.Level = int(level) if isinstance(level, int) else None
        if metadata is not None:
            page.Author = page.Author or _decode_utf16(metadata.properties.get("Author"))
            page.CreationTime = page.CreationTime or _time32_to_datetime(metadata.properties.get("CreationTimeStamp"))
            page.LastModifiedTime = page.LastModifiedTime or _filetime_to_datetime(metadata.properties.get("LastModifiedTimeStamp")) or _time32_to_datetime(metadata.properties.get("LastModifiedTime"))
            level = metadata.properties.get("PageLevel")
            if page.Level is None and isinstance(level, int):
                page.Level = int(level)

        title_node = next((child for child in node.children if child.kind == "TitleNode"), None)
        if title_node is not None:
            page.Title = self._build_title(title_node)
            page.AppendChildLast(page.Title)

        for child in node.children:
            if child.kind == "TitleNode":
                continue
            public_child = self._build_public_node(child)
            if public_child is not None:
                page.AppendChildLast(public_child)

        if page.Title is None and self._should_synthesize_page_title(node):
            title_text = None
            if metadata is not None:
                title_text = _decode_utf16(metadata.properties.get("CachedTitleString")) or _decode_utf16(metadata.properties.get("CachedTitleStringFromPage"))
            if title_text:
                title = Title()
                title.TitleText = RichText(Text=title_text, TextRuns=[TextRun(Text=title_text)])
                page.Title = title
                page.AppendChildFirst(title)

        return page

    def _collect_richtexts(self, node: LogicalNode) -> list[LogicalNode]:
        return [candidate for candidate in self._descendants(node) if candidate.kind == "RichTextOENode"]

    def _build_title(self, node: LogicalNode) -> Title:
        title = Title()
        richtexts = self._collect_richtexts(node)
        if richtexts:
            title.TitleText = self._build_richtext(richtexts[0])
        if len(richtexts) > 1:
            title.TitleDate = self._build_richtext(richtexts[1])
        if len(richtexts) > 2:
            title.TitleTime = self._build_richtext(richtexts[2])
        return title

    def _build_public_node(self, node: LogicalNode):
        if node.kind in PUBLIC_CONTAINER_KINDS:
            return None
        if node.kind == "OutlineNode":
            return self._build_outline(node)
        if node.kind == "OutlineElementNode":
            return self._build_outline_element(node)
        if node.kind == "RichTextOENode":
            return self._build_richtext(node)
        if node.kind == "ImageNode":
            return self._build_image(node)
        if node.kind == "EmbeddedFileNode":
            return self._build_attached_file(node)
        if node.kind == "TableNode":
            return self._build_table(node)
        if node.kind == "TableRowNode":
            return self._build_table_row(node)
        if node.kind == "TableCellNode":
            return self._build_table_cell(node)
        return None

    def _append_public_children(self, parent, node: LogicalNode) -> None:
        for child in node.children:
            public_child = self._build_public_node(child)
            if public_child is not None:
                parent.AppendChildLast(public_child)
            elif child.kind in PUBLIC_CONTAINER_KINDS:
                self._append_public_children(parent, child)

    def _build_outline(self, node: LogicalNode) -> Outline:
        record = self.objects[node.oid]
        outline = Outline(
            HorizontalOffset=_u32_to_float(record.properties.get("OffsetFromParentHoriz")),
            VerticalOffset=_u32_to_float(record.properties.get("OffsetFromParentVert")),
            MaxWidth=_u32_to_float(record.properties.get("LayoutMaxWidth")),
        )
        self._append_public_children(outline, node)
        return outline

    def _build_outline_element(self, node: LogicalNode) -> OutlineElement:
        record = self.objects[node.oid]
        outline_element = OutlineElement()
        outline_tags = self._collect_tags(record)

        list_nodes = [child for child in node.children if child.kind == "NumberListNode"]
        if list_nodes:
            outline_element.NumberList = self._build_number_list(list_nodes[0])

        ordered_children = [child for child in node.children if child.kind not in {"NumberListNode", "OutlineElementNode"}]
        ordered_children.extend(child for child in node.children if child.kind == "OutlineElementNode")

        for child in ordered_children:
            public_child = self._build_public_node(child)
            if public_child is not None:
                if isinstance(public_child, RichText) and not public_child.Tags and outline_tags:
                    public_child.Tags.extend(outline_tags)
                outline_element.AppendChildLast(public_child)
        return outline_element

    def _resolve_style_properties(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, ExtendedGUID):
            target = self.objects.get(value)
            if target is not None:
                return target.properties
        return {}

    def _paragraph_style_from_properties(self, properties: Any) -> ParagraphStyle:
        resolved = self._resolve_style_properties(properties)
        return ParagraphStyle(
            FontName=_decode_utf16(resolved.get("Font")),
            FontSize=(float(resolved["FontSize"]) / 2.0) if isinstance(resolved.get("FontSize"), int) else None,
            FontColor=resolved.get("FontColor") if isinstance(resolved.get("FontColor"), int) else None,
            Highlight=resolved.get("Highlight") if isinstance(resolved.get("Highlight"), int) else None,
            IsBold=bool(resolved.get("Bold")),
            IsItalic=bool(resolved.get("Italic")),
            IsUnderline=bool(resolved.get("Underline")),
            IsStrikethrough=bool(resolved.get("Strikethrough")),
            IsSuperscript=bool(resolved.get("Superscript")),
            IsSubscript=bool(resolved.get("Subscript")),
        )

    def _paragraph_alignment_from_properties(self, properties: Any) -> HorizontalAlignment | None:
        resolved = self._resolve_style_properties(properties)
        return _decode_paragraph_alignment(resolved.get("ParagraphAlignment"))

    def _text_style_from_properties(self, properties: Any) -> TextStyle:
        resolved = self._resolve_style_properties(properties)
        return TextStyle(
            IsHyperlink=bool(resolved.get("Hyperlink") or resolved.get("WzHyperlinkUrl")),
            HyperlinkAddress=_decode_utf16(resolved.get("WzHyperlinkUrl")),
            FontName=_decode_utf16(resolved.get("Font")),
            FontSize=(float(resolved["FontSize"]) / 2.0) if isinstance(resolved.get("FontSize"), int) else None,
            FontColor=resolved.get("FontColor") if isinstance(resolved.get("FontColor"), int) else None,
            Highlight=resolved.get("Highlight") if isinstance(resolved.get("Highlight"), int) else None,
            Language=resolved.get("LanguageID") if isinstance(resolved.get("LanguageID"), int) else None,
            IsBold=bool(resolved.get("Bold")),
            IsItalic=bool(resolved.get("Italic")),
            IsUnderline=bool(resolved.get("Underline")),
            IsStrikethrough=bool(resolved.get("Strikethrough")),
            IsSuperscript=bool(resolved.get("Superscript")),
            IsSubscript=bool(resolved.get("Subscript")),
        )

    def _decode_run_boundaries(self, raw: Any, run_count: int, text_length: int) -> list[int]:
        if not isinstance(raw, (bytes, bytearray)) or run_count <= 0:
            return [0] * run_count
        for width in (4, 2):
            if len(raw) % width != 0:
                continue
            values = [int.from_bytes(raw[index : index + width], "little") for index in range(0, len(raw), width)]
            if len(values) not in {run_count - 1, run_count}:
                continue
            if values and all(0 <= value <= text_length for value in values) and values == sorted(values):
                return values[:run_count]
        return [0] * run_count

    def _build_richtext(self, node: LogicalNode) -> RichText:
        record = self.objects[node.oid]
        text = _decode_utf16(record.properties.get("RichEditTextUnicode")) or _decode_ascii_text(record.properties.get("TextExtendedAscii")) or ""
        base_style = self._text_style_from_properties(record.properties)
        rich_text = RichText(
            Text=text,
            TextRuns=[TextRun(Text=text, Style=base_style)] if text else None,
            ParagraphStyle=self._paragraph_style_from_properties(record.properties),
            Alignment=self._paragraph_alignment_from_properties(record.properties),
            Tags=self._collect_tags(record),
        )

        run_styles_raw = record.properties.get("TextRunFormatting")

        if isinstance(run_styles_raw, list) and run_styles_raw:
            text_runs: list[TextRun] = []
            boundaries = self._decode_run_boundaries(record.properties.get("TextRunIndex"), len(run_styles_raw), len(text))
            if not boundaries or boundaries[0] != 0:
                boundaries = [0] + boundaries
            boundaries = sorted(boundaries[: len(run_styles_raw)] + [len(text)])
            for index, style_props in enumerate(run_styles_raw):
                start = boundaries[index] if index < len(boundaries) else 0
                end = boundaries[index + 1] if index + 1 < len(boundaries) else len(text)
                run_text = text[start:end]
                text_runs.append(TextRun(Text=run_text, Style=self._text_style_from_properties(style_props)))
            rich_text._replace_text_runs(text_runs)

        return rich_text

    def _resolve_file_bytes(self, record: OneStoreObject, property_name: str) -> bytes:
        ref = record.properties.get(property_name)
        if not isinstance(ref, ExtendedGUID):
            return b""
        target = self.objects.get(ref)
        if target is None:
            return b""
        reference = target.file_data_reference or ""
        if reference.lower().startswith("<ifndf>"):
            match = re.search(r"([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})", reference)
            if match is not None:
                return self.parsed.file_data_store.get(match.group(1).lower(), b"")
        return b""

    def _build_image(self, node: LogicalNode) -> Image:
        record = self.objects[node.oid]
        width = _u32_to_float(record.properties.get("PictureWidth"))
        height = _u32_to_float(record.properties.get("PictureHeight"))
        image = Image(
            FileName=_decode_utf16(record.properties.get("ImageFilename")),
            Bytes=self._resolve_file_bytes(record, "PictureContainer") or self._resolve_file_bytes(record, "WebPictureContainer14"),
            Width=width,
            Height=height,
            OriginalWidth=width,
            OriginalHeight=height,
            Alignment=_decode_layout_alignment(record.properties.get("LayoutAlignmentSelf"))
            or _decode_layout_alignment(record.properties.get("LayoutAlignmentInParent")),
            AlternativeTextDescription=_decode_utf16(record.properties.get("ImageAltText")),
            HyperlinkUrl=_decode_utf16(record.properties.get("WzHyperlinkUrl")),
            Tags=self._collect_tags(record),
        )
        return image

    def _build_attached_file(self, node: LogicalNode) -> AttachedFile:
        record = self.objects[node.oid]
        return AttachedFile(
            FileName=_decode_utf16(record.properties.get("EmbeddedFileName")) or _decode_utf16(record.properties.get("SourceFilepath")),
            Bytes=self._resolve_file_bytes(record, "EmbeddedFileContainer"),
            Tags=self._collect_tags(record),
        )

    def _build_table(self, node: LogicalNode) -> Table:
        record = self.objects[node.oid]
        column_widths = _bytes_to_float_list(record.properties.get("TableColumnWidths"))
        table = Table(
            Tags=self._collect_tags(record),
            Columns=[TableColumn(Width=width) for width in column_widths],
            IsBordersVisible=bool(record.properties.get("TableBordersVisible", True)),
        )
        for child in node.children:
            if child.kind == "TableRowNode":
                table.AppendChildLast(self._build_table_row(child))
        return table

    def _build_table_row(self, node: LogicalNode) -> TableRow:
        row = TableRow()
        for child in node.children:
            if child.kind == "TableCellNode":
                row.AppendChildLast(self._build_table_cell(child))
        return row

    def _build_table_cell(self, node: LogicalNode) -> TableCell:
        cell = TableCell()
        self._append_public_children(cell, node)
        return cell

    def _build_number_list(self, node: LogicalNode) -> NumberList:
        record = self.objects[node.oid]
        fmt = _decode_number_list_format(record.properties.get("NumberListFormat"))
        restart = record.properties.get("ListRestart") if isinstance(record.properties.get("ListRestart"), int) else None
        return NumberList(Format=fmt, NumberFormat=fmt, Restart=restart)

    def _tag_from_record(self, record: OneStoreObject | None) -> list[NoteTag]:
        if record is None:
            return []
        label = _decode_utf16(record.properties.get("NoteTagLabel"))
        tag = NoteTag._create(
            Icon=record.properties.get("NoteTagShape") if isinstance(record.properties.get("NoteTagShape"), int) else None,
            Label=label,
            FontColor=record.properties.get("NoteTagTextColor") if isinstance(record.properties.get("NoteTagTextColor"), int) else None,
            Highlight=record.properties.get("NoteTagHighlightColor") if isinstance(record.properties.get("NoteTagHighlightColor"), int) else None,
            CreationTime=record.properties.get("NoteTagCreated") if isinstance(record.properties.get("NoteTagCreated"), int) else None,
            CompletedTime=record.properties.get("NoteTagCompleted") if isinstance(record.properties.get("NoteTagCompleted"), int) else None,
        )
        if tag.Label or tag.Icon is not None:
            return [tag]
        return []

    def _tag_from_state(self, state_value: Any) -> list[NoteTag]:
        if not isinstance(state_value, dict):
            return []
        tags: list[NoteTag] = []
        definition_ref = state_value.get("NoteTagDefinitionOid")
        if isinstance(definition_ref, ExtendedGUID):
            tags.extend(self._tag_from_record(self.objects.get(definition_ref)))
        inline = NoteTag._create(
            Icon=state_value.get("NoteTagShape") if isinstance(state_value.get("NoteTagShape"), int) else None,
            Label=_decode_utf16(state_value.get("NoteTagLabel")),
            FontColor=state_value.get("NoteTagTextColor") if isinstance(state_value.get("NoteTagTextColor"), int) else None,
            Highlight=state_value.get("NoteTagHighlightColor") if isinstance(state_value.get("NoteTagHighlightColor"), int) else None,
            CreationTime=state_value.get("NoteTagCreated") if isinstance(state_value.get("NoteTagCreated"), int) else None,
            CompletedTime=state_value.get("NoteTagCompleted") if isinstance(state_value.get("NoteTagCompleted"), int) else None,
        )
        if inline.Label or inline.Icon is not None:
            tags.append(inline)
        return tags

    def _collect_tags(self, record: OneStoreObject) -> list[NoteTag]:
        tags = self._tag_from_record(record)
        note_tag_states = record.properties.get("NoteTagStates")
        if isinstance(note_tag_states, list):
            for state in note_tag_states:
                tags.extend(self._tag_from_state(state))
        for name, value in record.raw_properties:
            if name not in {"NoteTagDefinitionOid", "MetaDataObjectsAboveGraphSpace", "NoteTagStates"}:
                continue
            for ref in _flatten_refs(value):
                target = self.objects.get(ref)
                if target is None:
                    continue
                tags.extend(self._tag_from_record(target))
                nested_ref = target.properties.get("NoteTagDefinitionOid")
                if isinstance(nested_ref, ExtendedGUID):
                    tags.extend(self._tag_from_record(self.objects.get(nested_ref)))
        return _unique_tags(tags)


def load_onenote_document(source: str | Path | BinaryIO, include_page_history: bool = False) -> LoadedOneNoteDocument:
    parsed = parse_onestore_file(source)
    return _Builder(parsed, include_page_history=include_page_history).build()