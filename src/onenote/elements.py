"""Public API element classes for OneNote documents.

This module provides a clean, user-friendly object model for working with
OneNote document structure. These classes are the public API that users
interact with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from .document import Document


@dataclass
class Element:
    """Base class for all OneNote document elements."""

    _oid: bytes = field(repr=False, default=b"")

    @property
    def id(self) -> str:
        """Unique identifier for this element (hex string)."""
        return self._oid.hex() if self._oid else ""

    def iter_children(self) -> Iterator["Element"]:
        """Iterate over direct child elements.

        This is primarily intended for debugging/introspection and for building
        generic tree walkers across the public element model.
        """
        return iter(())


def _walk_elements(root: "Element") -> Iterator["Element"]:
    """Depth-first walk over all descendants of an element (excluding root)."""
    for child in root.iter_children():
        yield child
        yield from _walk_elements(child)


@dataclass
class RichText(Element):
    """A rich text element containing formatted text content."""

    text: str = ""
    """The plain text content."""

    # Future: style runs, fonts, colors, etc.

    def __str__(self) -> str:
        return self.text


@dataclass
class Image(Element):
    """An embedded image element."""

    alt_text: str | None = None
    """Alternative text description for the image."""

    filename: str | None = None
    """Original source filename for the image (if available)."""

    data: bytes = field(default=b"", repr=False)
    """Raw image data (PNG, JPEG, etc.)."""

    width: float | None = None
    """Image width in points."""

    height: float | None = None
    """Image height in points."""

    format: str | None = None
    """Image format (e.g., 'png', 'jpeg')."""


@dataclass
class AttachedFile(Element):
    """An attached file (embedded file object)."""

    filename: str = ""
    """Original filename of the attachment."""

    data: bytes = field(default=b"", repr=False)
    """Raw file data."""

    extension: str | None = None
    """File extension (without dot)."""

    @property
    def size(self) -> int:
        """Size of the attached file in bytes."""
        return len(self.data)


@dataclass
class TableCell(Element):
    """A single cell in a table."""

    children: list[Element] = field(default_factory=list)
    """Content elements within this cell (typically OutlineElements)."""

    def iter_text(self) -> Iterator[RichText]:
        """Iterate over all RichText elements in this cell."""
        for child in self.children:
            if isinstance(child, RichText):
                yield child
            elif isinstance(child, OutlineElement):
                yield from child.iter_text()

    @property
    def text(self) -> str:
        """Get concatenated plain text from all RichText in this cell."""
        return "".join(rt.text for rt in self.iter_text())

    def iter_children(self) -> Iterator[Element]:
        return iter(self.children)


@dataclass
class TableRow(Element):
    """A row in a table."""

    cells: list[TableCell] = field(default_factory=list)
    """Cells in this row."""

    def __len__(self) -> int:
        return len(self.cells)

    def __getitem__(self, index: int) -> TableCell:
        return self.cells[index]

    def __iter__(self) -> Iterator[TableCell]:
        return iter(self.cells)

    def iter_children(self) -> Iterator[Element]:
        return iter(self.cells)


@dataclass
class Table(Element):
    """A table element with rows and cells."""

    rows: list[TableRow] = field(default_factory=list)
    """Rows in the table."""

    @property
    def row_count(self) -> int:
        """Number of rows in the table."""
        return len(self.rows)

    @property
    def column_count(self) -> int:
        """Number of columns (based on first row)."""
        return len(self.rows[0].cells) if self.rows else 0

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> TableRow:
        return self.rows[index]

    def __iter__(self) -> Iterator[TableRow]:
        return iter(self.rows)

    def cell(self, row: int, col: int) -> TableCell:
        """Get cell at specific row and column index."""
        return self.rows[row].cells[col]

    def iter_children(self) -> Iterator[Element]:
        return iter(self.rows)


@dataclass
class OutlineElement(Element):
    """A single element within an outline (paragraph-like container).

    OutlineElements can contain content (RichText, Image, Table, etc.)
    and can have nested child OutlineElements for hierarchical lists.
    """

    children: list[Element] = field(default_factory=list)
    """Nested child OutlineElements (for hierarchical lists)."""

    contents: list[Element] = field(default_factory=list)
    """Content elements (RichText, Image, Table, AttachedFile)."""

    indent_level: int = 0
    """Indentation level (0 = top level)."""

    list_format: str | None = None
    """List marker format for this element, when it is part of a list.

    For numbered lists this typically contains the replacement character (U+FFFD)
    which OneNote replaces with the item number.
    """

    list_restart: int | None = None
    """Explicit number override for this list item, when present."""

    is_numbered: bool = False
    """True if this element is a numbered list item (vs bulleted)."""

    def iter_text(self) -> Iterator[RichText]:
        """Iterate over all RichText elements in contents."""
        for elem in self.contents:
            if isinstance(elem, RichText):
                yield elem

    @property
    def text(self) -> str:
        """Get concatenated plain text from all RichText in contents."""
        return "".join(rt.text for rt in self.iter_text())

    def iter_all(self) -> Iterator["OutlineElement"]:
        """Recursively iterate over this and all nested OutlineElements."""
        yield self
        for child in self.children:
            if isinstance(child, OutlineElement):
                yield from child.iter_all()

    def iter_children(self) -> Iterator[Element]:
        # Expose both structural children and content nodes for easy debugging.
        # Order is stable: children first, then contents.
        return iter([*self.children, *self.contents])


@dataclass
class Outline(Element):
    """An outline container (a content block on a page).

    Outlines are the main content containers on a OneNote page.
    They contain OutlineElements which hold the actual content.
    """

    children: list[OutlineElement] = field(default_factory=list)
    """OutlineElements in this outline."""

    x: float | None = None
    """X position on page (in points)."""

    y: float | None = None
    """Y position on page (in points)."""

    width: float | None = None
    """Width of the outline (in points)."""

    def iter_elements(self) -> Iterator[OutlineElement]:
        """Recursively iterate over all OutlineElements."""
        for child in self.children:
            yield from child.iter_all()

    def iter_text(self) -> Iterator[RichText]:
        """Iterate over all RichText in the outline."""
        for elem in self.iter_elements():
            yield from elem.iter_text()

    @property
    def text(self) -> str:
        """Get all text content joined with newlines."""
        return "\n".join(elem.text for elem in self.iter_elements() if elem.text)

    def iter_children(self) -> Iterator[Element]:
        return iter(self.children)


@dataclass
class Title(Element):
    """Page title element."""

    children: list[Element] = field(default_factory=list)
    """Content of the title (typically RichText and OutlineElements)."""

    @property
    def text(self) -> str:
        """Get the title text."""
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, RichText):
                parts.append(child.text)
            elif isinstance(child, OutlineElement):
                parts.append(child.text)
        return "".join(parts)

    def __str__(self) -> str:
        return self.text

    def iter_children(self) -> Iterator[Element]:
        return iter(self.children)


@dataclass
class Page(Element):
    """A page in a OneNote document."""

    title: str = ""
    """Page title as plain text."""

    title_element: Title | None = None
    """Full Title element with formatting (if available)."""

    children: list[Element] = field(default_factory=list)
    """Page content: Outlines, Images, etc."""

    created: datetime | None = None
    """Page creation timestamp."""

    modified: datetime | None = None
    """Last modification timestamp."""

    level: int = 0
    """Page hierarchy level (0 = top-level page, 1+ = subpage)."""

    def iter_children(self) -> Iterator[Element]:
        return iter(self.children)

    def iter_all_elements(self) -> Iterator[Element]:
        """Iterate over all elements on the page (recursive).

        Useful for debugging: lets you quickly see Tables/Images/OutlineElements
        without manually expanding each intermediate container.
        """
        return _walk_elements(self)

    @property
    def all_elements(self) -> list[Element]:
        """Flat list of all elements on the page (recursive).

        This property is intentionally eager so you can expand it in a debugger.
        """
        return list(self.iter_all_elements())

    def iter_outlines(self) -> Iterator[Outline]:
        """Iterate over all Outline elements on this page."""
        for child in self.children:
            if isinstance(child, Outline):
                yield child

    def iter_elements(self) -> Iterator[OutlineElement]:
        """Iterate over all OutlineElements on this page."""
        for outline in self.iter_outlines():
            yield from outline.iter_elements()

    def iter_text(self) -> Iterator[RichText]:
        """Iterate over all RichText elements on this page."""
        for outline in self.iter_outlines():
            yield from outline.iter_text()

    def iter_images(self) -> Iterator[Image]:
        """Iterate over all Image elements on this page."""
        # Images can appear either inside OutlineElements (as contents)
        # or directly on the page (ElementChildNodesOfPage).
        for elem in self.iter_all_elements():
            if isinstance(elem, Image):
                yield elem

    def iter_tables(self) -> Iterator[Table]:
        """Iterate over all Table elements on this page."""
        for elem in self.iter_all_elements():
            if isinstance(elem, Table):
                yield elem

    def iter_attachments(self) -> Iterator[AttachedFile]:
        """Iterate over all AttachedFile elements on this page."""
        for elem in self.iter_all_elements():
            if isinstance(elem, AttachedFile):
                yield elem

    @property
    def text(self) -> str:
        """Get all text content from the page."""
        parts: list[str] = []
        if self.title:
            parts.append(self.title)
        for outline in self.iter_outlines():
            t = outline.text
            if t:
                parts.append(t)
        return "\n\n".join(parts)

    def __str__(self) -> str:
        return self.title or "(Untitled)"
