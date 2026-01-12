from __future__ import annotations

from dataclasses import dataclass

from onestore.common_types import ExtendedGUID
from onestore.object_data import DecodedPropertySet

from .base import BaseNode


@dataclass(frozen=True, slots=True)
class Section(BaseNode):
    display_name: str | None
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class PageSeries(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class Page(BaseNode):
    title: str | None
    children: tuple[BaseNode, ...]
    # Newest-to-oldest snapshots of this page in previous revisions.
    # Empty by default; populated by ms_one.reader.parse_section_file_with_page_history.
    history: tuple["Page", ...] = ()
    # Layout properties (all floats in half-points unless otherwise noted)
    page_width: float | None = None
    page_height: float | None = None


@dataclass(frozen=True, slots=True)
class Title(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class Outline(BaseNode):
    children: tuple[BaseNode, ...]
    # Layout properties (float in half-points)
    offset_horizontal: float | None = None
    offset_vertical: float | None = None
    layout_max_width: float | None = None


@dataclass(frozen=True, slots=True)
class OutlineElement(BaseNode):
    children: tuple[BaseNode, ...]
    content_children: tuple[BaseNode, ...]
    # Zero or more list item nodes (jcidNumberListNode) associated with this outline element.
    # Typically 0 or 1; present for both bulleted and numbered lists.
    list_nodes: tuple["ListNode", ...] = ()
    # Zero or more note tags associated with this outline element (container).
    tags: tuple["NoteTag", ...] = ()


@dataclass(frozen=True, slots=True)
class ListNode(BaseNode):
    """A list marker definition for an outline element (bullet or number).

    Backed by MS-ONE jcidNumberListNode.
    """

    number_list_format: str | None
    # Explicit number for this item (overrides automatic numbering) when present.
    restart: int | None = None
    # Accessibility string index for the list item, when present.
    msaa_index: int | None = None

    @property
    def is_numbered(self) -> bool:
        # MS-ONE: numbered list if NumberListFormat contains U+FFFD.
        return bool(self.number_list_format and "\uFFFD" in self.number_list_format)


@dataclass(frozen=True, slots=True)
class TextStyle:
    """Best-effort style information for a text run."""

    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strikethrough: bool | None = None
    superscript: bool | None = None
    subscript: bool | None = None

    font_name: str | None = None
    font_size_pt: float | None = None
    font_color: int | None = None
    highlight_color: int | None = None
    language_id: int | None = None

    hyperlink: str | None = None


@dataclass(frozen=True, slots=True)
class TextRun:
    """A contiguous run of characters in a RichText node."""

    start: int
    end: int
    style: TextStyle


@dataclass(frozen=True, slots=True)
class RichText(BaseNode):
    text: str | None
    # Best-effort paragraph font size in points (from ParagraphStyleObject FontSize).
    font_size_pt: float | None = None
    # Per-run formatting extracted from TextRunIndex/TextRunFormatting.
    runs: tuple[TextRun, ...] = ()
    # Zero or more note tags associated with this paragraph.
    tags: tuple["NoteTag", ...] = ()


@dataclass(frozen=True, slots=True)
class NoteTag:
    """A note tag associated with a paragraph or other object (best-effort)."""

    # Tag shape/icon id (MS-ONE NoteTagShape). Exact mapping to UI icon is OneNote-specific.
    shape: int | None = None
    # Human-readable label for normal tags (MS-ONE NoteTagLabel) when available.
    label: str | None = None
    # Text/highlight colors as raw 32-bit values (when present in the definition).
    text_color: int | None = None
    highlight_color: int | None = None
    # Created/completed timestamps as raw 32-bit values (when present in the state).
    created: int | None = None
    completed: int | None = None


@dataclass(frozen=True, slots=True)
class Image(BaseNode):
    alt_text: str | None
    original_filename: str | None = None
    # Zero or more file-data references extracted from properties.
    # Values are canonical UUID strings (lowercase, 36 chars) extracted from `<ifndf>{GUID}</ifndf>`.
    file_data_guids: tuple[str, ...] = ()
    # Best-effort embedded bytes (PNG/JPEG/etc.) extracted from PictureContainer when present.
    data: bytes = b""
    # Zero or more note tags associated with this image object.
    tags: tuple["NoteTag", ...] = ()
    # Layout properties (float; width/height in half-inch increments)
    offset_horizontal: float | None = None
    offset_vertical: float | None = None
    layout_max_width: float | None = None
    layout_max_height: float | None = None
    picture_width: float | None = None
    picture_height: float | None = None
    hyperlink: str | None = None


@dataclass(frozen=True, slots=True)
class EmbeddedFile(BaseNode):
    """An embedded/attached file object."""

    original_filename: str | None = None
    # Zero or more file-data references extracted from properties.
    # Values are canonical UUID strings (lowercase, 36 chars) extracted from `<ifndf>{GUID}</ifndf>`.
    file_data_guids: tuple[str, ...] = ()
    # Best-effort embedded bytes extracted from PictureContainer when present.
    data: bytes = b""
    # Zero or more note tags associated with this embedded object.
    tags: tuple["NoteTag", ...] = ()


@dataclass(frozen=True, slots=True)
class Table(BaseNode):
    children: tuple[BaseNode, ...]
    # Zero or more note tags associated with this table object.
    tags: tuple["NoteTag", ...] = ()
    # Table layout properties
    row_count: int | None = None
    column_count: int | None = None
    column_widths: tuple[float, ...] = ()
    borders_visible: bool | None = None


@dataclass(frozen=True, slots=True)
class TableRow(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class TableCell(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class SectionMetaData(BaseNode):
    raw: DecodedPropertySet | None


@dataclass(frozen=True, slots=True)
class PageMetaData(BaseNode):
    raw: DecodedPropertySet | None


@dataclass(frozen=True, slots=True)
class PageManifest(BaseNode):
    children: tuple[BaseNode, ...]
    content_children: tuple[BaseNode, ...]
