"""OneNote document parsing library.

This package provides a clean, user-friendly API for reading Microsoft OneNote
section files (.one format).

Basic Usage
-----------

Open and read a OneNote document::

    from onenote import Document

    # Open a .one file
    doc = Document.open("MyNotes.one")

    # Access pages
    for page in doc.pages:
        print(f"Page: {page.title}")
        print(page.text)

    # Get page count
    print(f"Total pages: {len(doc)}")

Working with Page Content
-------------------------

Iterate over page structure::

    page = doc.pages[0]

    # Get all outlines (content blocks)
    for outline in page.iter_outlines():
        print(outline.text)

    # Get all images
    for image in page.iter_images():
        print(f"Image: {image.alt_text}")

    # Get all tables
    for table in page.iter_tables():
        print(f"Table: {table.row_count}x{table.column_count}")

Element Types
-------------

- ``Document``: Root container (a .one section file)
- ``Page``: A page with title and content
- ``Title``: Page title element
- ``Outline``: Content block container
- ``OutlineElement``: Paragraph-like element within outline
- ``RichText``: Text content with formatting
- ``Image``: Embedded image
- ``Table``, ``TableRow``, ``TableCell``: Table structure
- ``AttachedFile``: Embedded file attachment

Example: Extract All Text
-------------------------

::

    doc = Document.open("notes.one")
    for page in doc:
        print(f"=== {page.title} ===")
        print(page.text)
        print()
"""

from .document import Document
from .elements import (
    Element,
    NoteTag,
    TextStyle,
    TextRun,
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
from .pdf_export import PdfExporter, PdfExportOptions, export_pdf

__all__ = [
    "Document",
    "Element",
    "NoteTag",
    "TextStyle",
    "TextRun",
    "Page",
    "Title",
    "Outline",
    "OutlineElement",
    "RichText",
    "Image",
    "Table",
    "TableRow",
    "TableCell",
    "AttachedFile",
    "PdfExporter",
    "PdfExportOptions",
    "export_pdf",
]

__version__ = "0.1.0"
