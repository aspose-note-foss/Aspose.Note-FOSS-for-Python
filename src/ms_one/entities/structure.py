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


@dataclass(frozen=True, slots=True)
class Title(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class Outline(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class OutlineElement(BaseNode):
    children: tuple[BaseNode, ...]
    content_children: tuple[BaseNode, ...]
    # Zero or more note tags associated with this outline element (container).
    tags: tuple["NoteTag", ...] = ()


@dataclass(frozen=True, slots=True)
class RichText(BaseNode):
    text: str | None
    # Best-effort paragraph font size in points (from ParagraphStyleObject FontSize).
    font_size_pt: float | None = None
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
    # Zero or more note tags associated with this image object.
    tags: tuple["NoteTag", ...] = ()


@dataclass(frozen=True, slots=True)
class EmbeddedFile(BaseNode):
    """An embedded/attached file object."""

    original_filename: str | None = None
    # Zero or more file-data references extracted from properties.
    # Values are canonical UUID strings (lowercase, 36 chars) extracted from `<ifndf>{GUID}</ifndf>`.
    file_data_guids: tuple[str, ...] = ()
    # Zero or more note tags associated with this embedded object.
    tags: tuple["NoteTag", ...] = ()


@dataclass(frozen=True, slots=True)
class Table(BaseNode):
    children: tuple[BaseNode, ...]
    # Zero or more note tags associated with this table object.
    tags: tuple["NoteTag", ...] = ()


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
