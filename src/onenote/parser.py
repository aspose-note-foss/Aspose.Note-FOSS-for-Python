"""Parser that converts ms_one internal entities to public onenote model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms_one.reader import parse_section_file
from ms_one.entities.base import BaseNode as MsBaseNode, UnknownNode as MsUnknownNode
from ms_one.entities import structure as ms

from .document import Document
from .elements import (
    Element,
    Page,
    Title,
    Outline,
    OutlineElement,
    RichText,
    Image,
    Table,
    TableRow,
    TableCell,
    AttachedFile,
)


def parse_document(data: bytes | bytearray | memoryview, *, strict: bool = False) -> Document:
    """Parse raw .one file bytes into a Document.

    This is the main conversion function that bridges ms_one internal
    representation to the public onenote API.
    """
    section = parse_section_file(data, strict=strict)
    return _convert_section(section)


def _convert_section(section: ms.Section) -> Document:
    """Convert ms_one Section to public Document."""
    pages: list[Page] = []

    for child in section.children:
        if isinstance(child, ms.PageSeries):
            pages.extend(_convert_page_series(child))
        elif isinstance(child, ms.Page):
            pages.append(_convert_page(child))
        # PageMetaData entries are also converted as pages (observed in SimpleTable.one)

    return Document(
        pages=pages,
        display_name=section.display_name,
    )


def _convert_page_series(series: ms.PageSeries) -> list[Page]:
    """Convert PageSeries to list of Pages."""
    pages: list[Page] = []
    for child in series.children:
        if isinstance(child, ms.Page):
            pages.append(_convert_page(child))
        elif isinstance(child, ms.PageSeries):
            # Nested page series (subpages)
            pages.extend(_convert_page_series(child))
    return pages


def _convert_page(page: ms.Page) -> Page:
    """Convert ms_one Page to public Page."""
    children: list[Element] = []
    title_element: Title | None = None

    for child in page.children:
        converted = _convert_node(child)
        if converted is not None:
            if isinstance(converted, Title):
                title_element = converted
            else:
                children.append(converted)

    return Page(
        _oid=page.oid.guid if page.oid else b"",
        title=page.title or "",
        title_element=title_element,
        children=children,
    )


def _convert_node(node: MsBaseNode) -> Element | None:
    """Convert any ms_one node to appropriate public Element."""
    if isinstance(node, MsUnknownNode):
        return None

    if isinstance(node, ms.Title):
        return _convert_title(node)
    if isinstance(node, ms.Outline):
        return _convert_outline(node)
    if isinstance(node, ms.OutlineElement):
        return _convert_outline_element(node)
    if isinstance(node, ms.RichText):
        return _convert_rich_text(node)
    if isinstance(node, ms.Image):
        return _convert_image(node)
    if isinstance(node, ms.Table):
        return _convert_table(node)
    if isinstance(node, ms.TableRow):
        return _convert_table_row(node)
    if isinstance(node, ms.TableCell):
        return _convert_table_cell(node)

    # For other node types, return None (skip)
    return None


def _convert_title(title: ms.Title) -> Title:
    """Convert ms_one Title to public Title."""
    children: list[Element] = []
    for child in title.children:
        converted = _convert_node(child)
        if converted is not None:
            children.append(converted)

    return Title(
        _oid=title.oid.guid if title.oid else b"",
        children=children,
    )


def _convert_outline(outline: ms.Outline) -> Outline:
    """Convert ms_one Outline to public Outline."""
    children: list[OutlineElement] = []
    for child in outline.children:
        if isinstance(child, ms.OutlineElement):
            children.append(_convert_outline_element(child))

    return Outline(
        _oid=outline.oid.guid if outline.oid else b"",
        children=children,
    )


def _convert_outline_element(elem: ms.OutlineElement) -> OutlineElement:
    """Convert ms_one OutlineElement to public OutlineElement."""
    # children are nested OutlineElements (hierarchical structure)
    children: list[Element] = []
    for child in elem.children:
        if isinstance(child, ms.OutlineElement):
            children.append(_convert_outline_element(child))

    # content_children are the actual content (RichText, Image, Table, etc.)
    contents: list[Element] = []
    for content in elem.content_children:
        converted = _convert_node(content)
        if converted is not None:
            contents.append(converted)

    return OutlineElement(
        _oid=elem.oid.guid if elem.oid else b"",
        children=children,
        contents=contents,
    )


def _convert_rich_text(rt: ms.RichText) -> RichText:
    """Convert ms_one RichText to public RichText."""
    return RichText(
        _oid=rt.oid.guid if rt.oid else b"",
        text=rt.text or "",
    )


def _convert_image(img: ms.Image) -> Image:
    """Convert ms_one Image to public Image."""
    # TODO: Extract actual image data from file data store
    return Image(
        _oid=img.oid.guid if img.oid else b"",
        alt_text=img.alt_text,
    )


def _convert_table(table: ms.Table) -> Table:
    """Convert ms_one Table to public Table."""
    rows: list[TableRow] = []
    for child in table.children:
        if isinstance(child, ms.TableRow):
            rows.append(_convert_table_row(child))

    return Table(
        _oid=table.oid.guid if table.oid else b"",
        rows=rows,
    )


def _convert_table_row(row: ms.TableRow) -> TableRow:
    """Convert ms_one TableRow to public TableRow."""
    cells: list[TableCell] = []
    for child in row.children:
        if isinstance(child, ms.TableCell):
            cells.append(_convert_table_cell(child))

    return TableRow(
        _oid=row.oid.guid if row.oid else b"",
        cells=cells,
    )


def _convert_table_cell(cell: ms.TableCell) -> TableCell:
    """Convert ms_one TableCell to public TableCell."""
    children: list[Element] = []
    for child in cell.children:
        converted = _convert_node(child)
        if converted is not None:
            children.append(converted)

    return TableCell(
        _oid=cell.oid.guid if cell.oid else b"",
        children=children,
    )
