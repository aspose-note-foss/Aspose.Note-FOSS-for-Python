"""Parser that converts ms_one internal entities to public onenote model."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from ms_one.reader import parse_section_file
from ms_one.entities.base import BaseNode as MsBaseNode, UnknownNode as MsUnknownNode
from ms_one.entities import structure as ms
from onestore.chunk_refs import FileNodeChunkReference
from onestore.file_data import (
    get_file_data_by_reference,
    parse_file_data_store_index,
    parse_file_data_store_object_from_ref,
)
from onestore.parse_context import ParseContext

from .document import Document
from .elements import (
    Element,
    Page,
    Title,
    Outline,
    OutlineElement,
    RichText,
    TextRun,
    TextStyle,
    Image,
    Table,
    TableRow,
    TableCell,
    AttachedFile,
    NoteTag,
)


_IFNDF_TEXT_RE = re.compile(r"<ifndf>\{(?P<guid>[0-9a-fA-F\-]{36})\}</ifndf>")


if TYPE_CHECKING:
    from onestore.object_data import DecodedPropertySet


def _extract_file_data_store_guids_from_ms_one_properties(
    props: "DecodedPropertySet | None",
    *,
    index_keys: "set[bytes] | None",
) -> tuple[str, ...]:
    """Extract FileDataStore GUIDs from ms_one raw_properties.

    This is a public-layer fallback for fixtures where ms_one doesn't surface
    file_data_guids but the raw properties still contain:
    - textual `<ifndf>{GUID}</ifndf>` references (ASCII or UTF-16LE)
    - raw 16-byte GUID values (little-endian) that match FileDataStore index keys
    """

    if props is None:
        return ()

    ordered: list[str] = []
    seen: set[str] = set()

    # Local import to avoid a hard dependency cycle at import time.
    from onestore.object_data import DecodedPropertySet
    from onestore.common_types import ExtendedGUID

    def iter_property_bytes(pset: DecodedPropertySet):
        stack: list[DecodedPropertySet] = [pset]
        while stack:
            cur = stack.pop()
            for prop in cur.properties:
                v = prop.value
                if isinstance(v, bytes):
                    yield v
                elif isinstance(v, DecodedPropertySet):
                    stack.append(v)
                elif isinstance(v, tuple):
                    for item in v:
                        if isinstance(item, bytes):
                            yield item
                        elif isinstance(item, DecodedPropertySet):
                            stack.append(item)

    def iter_property_scalars(pset: DecodedPropertySet):
        stack: list[object] = [pset]
        while stack:
            cur = stack.pop()
            if cur is None:
                continue
            if isinstance(cur, tuple):
                stack.extend(list(cur))
                continue
            if isinstance(cur, DecodedPropertySet):
                stack.extend([p.value for p in cur.properties])
                continue
            yield cur

    # First pass: explicit textual `<ifndf>` references, in discovery order.
    for b in iter_property_bytes(props):
        if b"<ifndf>" in b:
            s = b.decode("ascii", errors="ignore")
            for m in _IFNDF_TEXT_RE.finditer(s):
                try:
                    g = str(uuid.UUID(m.group("guid")))
                except Exception:
                    continue
                if g not in seen:
                    seen.add(g)
                    ordered.append(g)

        if b"<\x00i\x00f\x00n\x00d\x00f\x00" in b:
            s = b.decode("utf-16le", errors="ignore")
            for m in _IFNDF_TEXT_RE.finditer(s):
                try:
                    g = str(uuid.UUID(m.group("guid")))
                except Exception:
                    continue
                if g not in seen:
                    seen.add(g)
                    ordered.append(g)

    # Second pass: raw GUID bytes, only if we can validate against known index keys.
    if index_keys:
        # Some files store guidReference as an ExtendedGUID scalar.
        for v in iter_property_scalars(props):
            if isinstance(v, ExtendedGUID) and v.guid in index_keys:
                try:
                    g = str(uuid.UUID(bytes_le=bytes(v.guid)))
                except Exception:
                    continue
                if g not in seen:
                    seen.add(g)
                    ordered.append(g)

        for b in iter_property_bytes(props):
            if len(b) < 16:
                continue
            for i in range(0, len(b) - 15):
                chunk = b[i : i + 16]
                if chunk not in index_keys:
                    continue
                try:
                    g = str(uuid.UUID(bytes_le=bytes(chunk)))
                except Exception:
                    continue
                if g not in seen:
                    seen.add(g)
                    ordered.append(g)

    return tuple(ordered)


def _convert_note_tags(tags: tuple[ms.NoteTag, ...] | None) -> list[NoteTag]:
    if not tags:
        return []
    return [
        NoteTag(
            shape=t.shape,
            label=t.label,
            text_color=t.text_color,
            highlight_color=t.highlight_color,
            created=t.created,
            completed=t.completed,
        )
        for t in tags
    ]


def parse_document(data: bytes | bytearray | memoryview, *, strict: bool = False) -> Document:
    """Parse raw .one file bytes into a Document.

    This is the main conversion function that bridges ms_one internal
    representation to the public onenote API.
    """
    section = parse_section_file(data, strict=strict)

    # Best-effort FileDataStore index to resolve embedded blobs (images, attachments).
    # Always parse it in non-strict mode; some fixtures violate MUST-level constraints.
    fds_ctx = ParseContext(strict=False, file_size=len(data))
    try:
        file_data_store_index = parse_file_data_store_index(data, ctx=fds_ctx)
    except Exception:
        file_data_store_index = {}

    doc = _convert_section(section, source_data=data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
    _populate_missing_image_data_from_file_data_store(doc, source_data=data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
    return doc


_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _looks_like_image_bytes(blob: bytes) -> bool:
    if not blob:
        return False
    return (
        blob.startswith(_PNG_SIG)
        or blob.startswith(b"\xff\xd8\xff")
        or blob.startswith(b"GIF87a")
        or blob.startswith(b"GIF89a")
        or blob.startswith(b"BM")
        or blob.startswith(b"II*\x00")
        or blob.startswith(b"MM\x00*")
    )


def _png_size(blob: bytes) -> tuple[int, int] | None:
    # PNG: width/height are big-endian u32 at offsets 16..24 of the file.
    if len(blob) < 24 or not blob.startswith(_PNG_SIG):
        return None
    w = int.from_bytes(blob[16:20], "big", signed=False)
    h = int.from_bytes(blob[20:24], "big", signed=False)
    if w <= 0 or h <= 0:
        return None
    return (w, h)


def _aspect_ratio_from_bytes(blob: bytes) -> float | None:
    s = _png_size(blob)
    if s is None:
        return None
    w, h = s
    return float(w) / float(h) if h else None


def _aspect_ratio_from_image(img: "Image") -> float | None:
    if img.width and img.height and img.height != 0:
        return float(img.width) / float(img.height)
    return None


def _populate_missing_image_data_from_file_data_store(
    doc: Document,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index,
    fds_ctx: ParseContext,
) -> None:
    """Best-effort: populate Image.data from FileDataStore when references are missing.

    Some .one files (including fixtures) contain image bytes in the OneStore FileDataStore,
    but do not expose `<ifndf>` references on the Image node (or reachable objects) in a way
    we can currently resolve. In that case, we pair remaining image-like FileDataStore blobs
    to Images with empty data using a simple aspect-ratio heuristic.
    """

    missing: list[Image] = []
    for page in doc.pages:
        for img in page.iter_images():
            if not img.data:
                missing.append(img)

    if not missing:
        return

    # Collect image-like blobs from the file data store.
    blobs: list[bytes] = []
    for _guid, ref in (file_data_store_index or {}).items():
        try:
            obj = parse_file_data_store_object_from_ref(
                source_data,
                stp=int(ref.stp),
                cb=int(ref.cb),
                ctx=fds_ctx,
            )
        except Exception:
            continue
        b = bytes(getattr(obj, "file_data", b""))
        if _looks_like_image_bytes(b):
            blobs.append(b)

    if not blobs:
        return

    # Group missing images by underlying MS-ONE object id.
    # Some files (including fixtures) reuse the same Image object multiple times
    # with different layout; in that case we MUST assign identical bytes.
    by_oid: dict[bytes, list[Image]] = {}
    for img in missing:
        by_oid.setdefault(getattr(img, "_oid", b""), []).append(img)

    def score(image: Image, blob: bytes) -> float:
        ir = _aspect_ratio_from_image(image)
        br = _aspect_ratio_from_bytes(blob)
        if ir is None or br is None:
            return 0.0
        return abs(ir - br)

    # For each OID group, pick a best-matching blob once and reuse it for the group.
    # Do not "consume" blobs: different logical images may legitimately reuse bytes,
    # and consuming can incorrectly mix historical blobs into current layout.
    for _oid, images in by_oid.items():
        if not images:
            continue

        best_blob: bytes | None = None
        best_s = float("inf")

        for blob in blobs:
            # Skip non-image blobs defensively.
            if not _looks_like_image_bytes(blob):
                continue

            # Score by the first image (layout-driven) as a stable heuristic.
            s = score(images[0], blob)
            if s < best_s:
                best_s = s
                best_blob = blob

        if best_blob is None:
            continue

        for image in images:
            image.data = best_blob
            if image.data.startswith(_PNG_SIG):
                image.format = "png"


def _resolve_embedded_data(
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
    file_data_guids: tuple[str, ...] | None,
) -> bytes:
    if not file_data_guids:
        return b""

    # `ms_one` stores canonical UUID strings (lowercase, 36 chars).
    # Resolve using OneStore's `<ifndf>{GUID}</ifndf>` reference syntax.
    for g in file_data_guids:
        if not g:
            continue
        ref = f"<ifndf>{{{g}}}</ifndf>"
        try:
            blob = get_file_data_by_reference(
                source_data,
                ref,
                ctx=fds_ctx,
                index=file_data_store_index,
            )
        except Exception:
            blob = None
        if blob:
            return bytes(blob)
    return b""


def _convert_section(
    section: ms.Section,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> Document:
    """Convert ms_one Section to public Document."""
    pages: list[Page] = []

    for child in section.children:
        if isinstance(child, ms.PageSeries):
            pages.extend(
                _convert_page_series(
                    child,
                    source_data=source_data,
                    file_data_store_index=file_data_store_index,
                    fds_ctx=fds_ctx,
                )
            )
        elif isinstance(child, ms.Page):
            pages.append(
                _convert_page(
                    child,
                    source_data=source_data,
                    file_data_store_index=file_data_store_index,
                    fds_ctx=fds_ctx,
                )
            )
        # PageMetaData entries are also converted as pages (observed in SimpleTable.one)

    return Document(
        pages=pages,
        display_name=section.display_name,
    )


def _convert_page_series(
    series: ms.PageSeries,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> list[Page]:
    """Convert PageSeries to list of Pages."""
    pages: list[Page] = []
    for child in series.children:
        if isinstance(child, ms.Page):
            pages.append(
                _convert_page(
                    child,
                    source_data=source_data,
                    file_data_store_index=file_data_store_index,
                    fds_ctx=fds_ctx,
                )
            )
        elif isinstance(child, ms.PageSeries):
            # Nested page series (subpages)
            pages.extend(
                _convert_page_series(
                    child,
                    source_data=source_data,
                    file_data_store_index=file_data_store_index,
                    fds_ctx=fds_ctx,
                )
            )
    return pages


def _convert_page(
    page: ms.Page,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> Page:
    """Convert ms_one Page to public Page."""
    children: list[Element] = []
    title_element: Title | None = None

    for child in page.children:
        converted = _convert_node(
            child,
            source_data=source_data,
            file_data_store_index=file_data_store_index,
            fds_ctx=fds_ctx,
        )
        if converted is not None:
            if isinstance(converted, Title):
                title_element = converted
            else:
                children.append(converted)

    # Convert page dimensions to points.
    # MS-ONE PageWidth/PageHeight are stored as floats in inches.
    page_width = page.page_width * 72.0 if page.page_width is not None else None
    page_height = page.page_height * 72.0 if page.page_height is not None else None

    return Page(
        _oid=page.oid.guid if page.oid else b"",
        title=page.title or "",
        title_element=title_element,
        children=children,
        width=page_width,
        height=page_height,
    )


def _convert_node(
    node: MsBaseNode,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> Element | None:
    """Convert any ms_one node to appropriate public Element."""
    if isinstance(node, MsUnknownNode):
        return None

    if isinstance(node, ms.Title):
        return _convert_title(node, source_data=source_data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
    if isinstance(node, ms.Outline):
        return _convert_outline(node, source_data=source_data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
    if isinstance(node, ms.OutlineElement):
        return _convert_outline_element(node, source_data=source_data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
    if isinstance(node, ms.RichText):
        return _convert_rich_text(node)
    if isinstance(node, ms.Image):
        return _convert_image(node, source_data=source_data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
    if isinstance(node, ms.Table):
        return _convert_table(node, source_data=source_data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
        if isinstance(node, ms.TableRow):
            return _convert_table_row(node, source_data=source_data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
    if isinstance(node, ms.TableCell):
        return _convert_table_cell(node, source_data=source_data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)
    if isinstance(node, ms.EmbeddedFile):
        return _convert_attached_file(node, source_data=source_data, file_data_store_index=file_data_store_index, fds_ctx=fds_ctx)

    # For other node types, return None (skip)
    return None


def _convert_title(
    title: ms.Title,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> Title:
    """Convert ms_one Title to public Title."""
    children: list[Element] = []
    for child in title.children:
        converted = _convert_node(
            child,
            source_data=source_data,
            file_data_store_index=file_data_store_index,
            fds_ctx=fds_ctx,
        )
        if converted is not None:
            children.append(converted)

    return Title(
        _oid=title.oid.guid if title.oid else b"",
        children=children,
    )


def _convert_outline(
    outline: ms.Outline,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> Outline:
    """Convert ms_one Outline to public Outline."""
    children: list[OutlineElement] = []
    for child in outline.children:
        converted = _convert_node(
            child,
            source_data=source_data,
            file_data_store_index=file_data_store_index,
            fds_ctx=fds_ctx,
        )
        if converted is None:
            continue

        if isinstance(converted, OutlineElement):
            children.append(converted)
        else:
            # Some files place content nodes directly under an Outline.
            # Wrap them into a synthetic OutlineElement so the public API
            # can still surface them via iter_text/page.text.
            children.append(
                OutlineElement(
                    _oid=b"",
                    children=[],
                    contents=[converted],
                )
            )

    # Convert layout offsets to points.
    # MS-ONE: OffsetFromParentHoriz/Vert and LayoutMaxWidth are stored as floats in inches.
    # PDF/reportlab use points (1 inch = 72 points).
    x = outline.offset_horizontal * 72.0 if outline.offset_horizontal is not None else None
    y = outline.offset_vertical * 72.0 if outline.offset_vertical is not None else None
    width = outline.layout_max_width * 72.0 if outline.layout_max_width is not None else None

    return Outline(
        _oid=outline.oid.guid if outline.oid else b"",
        children=children,
        x=x,
        y=y,
        width=width,
    )


def _convert_outline_element(
    elem: ms.OutlineElement,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> OutlineElement:
    """Convert ms_one OutlineElement to public OutlineElement."""
    # children are nested OutlineElements (hierarchical structure)
    children: list[Element] = []
    contents: list[Element] = []
    for child in elem.children:
        converted = _convert_node(
            child,
            source_data=source_data,
            file_data_store_index=file_data_store_index,
            fds_ctx=fds_ctx,
        )
        if converted is None:
            continue
        if isinstance(converted, OutlineElement):
            children.append(converted)
        else:
            # Some real-world files place content nodes under ElementChildNodes;
            # keep them instead of dropping.
            contents.append(converted)

    # content_children are the actual content (RichText, Image, Table, etc.)
    for content in elem.content_children:
        converted = _convert_node(
            content,
            source_data=source_data,
            file_data_store_index=file_data_store_index,
            fds_ctx=fds_ctx,
        )
        if converted is not None:
            contents.append(converted)

    list_format = None
    list_restart = None
    is_numbered = False
    # MS-ONE represents list markers as jcidNumberListNode entries attached to OutlineElement.
    # Keep this simple in the public API: use the first marker when multiple are present.
    if getattr(elem, "list_nodes", None):
        ln = elem.list_nodes[0]
        list_format = getattr(ln, "number_list_format", None)
        list_restart = getattr(ln, "restart", None)
        is_numbered = bool(getattr(ln, "is_numbered", False))

    return OutlineElement(
        _oid=elem.oid.guid if elem.oid else b"",
        children=children,
        contents=contents,
        list_format=list_format,
        list_restart=list_restart,
        is_numbered=is_numbered,
        tags=_convert_note_tags(getattr(elem, "tags", None)),
    )


def _convert_rich_text(rt: ms.RichText) -> RichText:
    """Convert ms_one RichText to public RichText."""
    runs: list[TextRun] = []
    for r in getattr(rt, "runs", ()) or ():
        style = getattr(r, "style", None)
        runs.append(
            TextRun(
                start=int(getattr(r, "start", 0)),
                end=int(getattr(r, "end", 0)),
                style=TextStyle(
                    bold=getattr(style, "bold", None),
                    italic=getattr(style, "italic", None),
                    underline=getattr(style, "underline", None),
                    strikethrough=getattr(style, "strikethrough", None),
                    superscript=getattr(style, "superscript", None),
                    subscript=getattr(style, "subscript", None),
                    font_name=getattr(style, "font_name", None),
                    font_size_pt=getattr(style, "font_size_pt", None),
                    font_color=getattr(style, "font_color", None),
                    highlight_color=getattr(style, "highlight_color", None),
                    language_id=getattr(style, "language_id", None),
                    hyperlink=getattr(style, "hyperlink", None),
                ),
            )
        )

    return RichText(
        _oid=rt.oid.guid if rt.oid else b"",
        text=rt.text or "",
        runs=runs,
        font_size_pt=getattr(rt, "font_size_pt", None),
        tags=_convert_note_tags(getattr(rt, "tags", None)),
    )


def _convert_image(
    img: ms.Image,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> Image:
    """Convert ms_one Image to public Image."""
    # Convert dimensions: PictureWidth/Height are in half-inch increments -> points (1 inch = 72 points)
    # half-inch = 36 points
    width = img.picture_width * 36.0 if img.picture_width is not None else None
    height = img.picture_height * 36.0 if img.picture_height is not None else None
    
    # Offsets are in half-points
    x = img.offset_horizontal / 2.0 if img.offset_horizontal is not None else None
    y = img.offset_vertical / 2.0 if img.offset_vertical is not None else None

    data = bytes(getattr(img, "data", b"") or b"")
    if not data:
        # Prefer discovery-ordered GUIDs from raw_properties.
        raw_guids = _extract_file_data_store_guids_from_ms_one_properties(
            getattr(img, "raw_properties", None),
            index_keys=set(file_data_store_index.keys()) if file_data_store_index else None,
        )
        ms_one_guids: tuple[str, ...] = getattr(img, "file_data_guids", None) or ()
        if raw_guids:
            seen = set(raw_guids)
            guid_candidates = (*raw_guids, *(g for g in ms_one_guids if g and g not in seen))
        else:
            guid_candidates = ms_one_guids

        # Resolve in candidate order and require the payload to look like an image.
        for g in guid_candidates:
            if not g:
                continue
            ref = f"<ifndf>{{{g}}}</ifndf>"
            try:
                blob = get_file_data_by_reference(
                    source_data,
                    ref,
                    ctx=fds_ctx,
                    index=file_data_store_index,
                )
            except Exception:
                blob = None
            if blob and _looks_like_image_bytes(bytes(blob)):
                data = bytes(blob)
                break

    return Image(
        _oid=img.oid.guid if img.oid else b"",
        alt_text=img.alt_text,
        filename=img.original_filename,
        tags=_convert_note_tags(getattr(img, "tags", None)),
        data=data,
        width=width,
        height=height,
        x=x,
        y=y,
        hyperlink=img.hyperlink,
    )


def _convert_table(
    table: ms.Table,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> Table:
    """Convert ms_one Table to public Table."""
    rows: list[TableRow] = []
    for child in table.children:
        if isinstance(child, ms.TableRow):
            rows.append(
                _convert_table_row(
                    child,
                    source_data=source_data,
                    file_data_store_index=file_data_store_index,
                    fds_ctx=fds_ctx,
                )
            )

    # Convert column widths (half-points to points)
    column_widths = [w / 2.0 for w in table.column_widths] if table.column_widths else []
    borders_visible = table.borders_visible if table.borders_visible is not None else True

    return Table(
        _oid=table.oid.guid if table.oid else b"",
        rows=rows,
        tags=_convert_note_tags(getattr(table, "tags", None)),
        column_widths=column_widths,
        borders_visible=borders_visible,
    )


def _convert_table_row(
    row: ms.TableRow,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> TableRow:
    """Convert ms_one TableRow to public TableRow."""
    cells: list[TableCell] = []
    for child in row.children:
        if isinstance(child, ms.TableCell):
            cells.append(
                _convert_table_cell(
                    child,
                    source_data=source_data,
                    file_data_store_index=file_data_store_index,
                    fds_ctx=fds_ctx,
                )
            )

    return TableRow(
        _oid=row.oid.guid if row.oid else b"",
        cells=cells,
    )


def _convert_table_cell(
    cell: ms.TableCell,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> TableCell:
    """Convert ms_one TableCell to public TableCell."""
    children: list[Element] = []
    for child in cell.children:
        converted = _convert_node(
            child,
            source_data=source_data,
            file_data_store_index=file_data_store_index,
            fds_ctx=fds_ctx,
        )
        if converted is not None:
            children.append(converted)

    return TableCell(
        _oid=cell.oid.guid if cell.oid else b"",
        children=children,
    )


def _convert_attached_file(
    f: ms.EmbeddedFile,
    *,
    source_data: bytes | bytearray | memoryview,
    file_data_store_index: dict[bytes, FileNodeChunkReference],
    fds_ctx: ParseContext,
) -> AttachedFile:
    data = bytes(getattr(f, "data", b"") or b"")
    if not data:
        file_data_guids = getattr(f, "file_data_guids", None)
        if not file_data_guids:
            file_data_guids = _extract_file_data_store_guids_from_ms_one_properties(
                getattr(f, "raw_properties", None),
                index_keys=set(file_data_store_index.keys()) if file_data_store_index else None,
            )

        data = _resolve_embedded_data(
            source_data,
            file_data_store_index,
            fds_ctx,
            file_data_guids,
        )

    return AttachedFile(
        _oid=f.oid.guid if f.oid else b"",
        filename=f.original_filename or "",
        data=data,
        tags=_convert_note_tags(getattr(f, "tags", None)),
    )
