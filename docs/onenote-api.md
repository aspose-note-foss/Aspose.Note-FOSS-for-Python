# OneNote Python Library - API Reference (`onenote`)

This document describes the API of the `onenote` module for reading OneNote section files (`.one`).

Important: this repository is published on PyPI as `aspose-note`, and the supported, Aspose-compatible public entrypoint is `aspose.note` (see repository README). The `onenote` module is a smaller, Pythonic convenience API built on the same parser.

## Architecture Overview

```
.one file (binary)
       │
       ▼
┌──────────────────┐
│   MS-ONESTORE    │  Low-level binary container parsing
│   (onestore/)    │  File nodes, object spaces, revisions
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│     MS-ONE       │  Entity extraction layer
│    (ms_one/)     │  Section, Page, Outline, RichText, etc.
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│     ONENOTE      │  Pythonic convenience API (`onenote`)
│    (onenote/)    │  Document, Page, Outline, RichText, etc.
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   ASPOSE.NOTE    │  Supported Aspose-compatible API (`aspose.note`)
│  (aspose/note/)  │  Document.Save(...), SaveFormat, DOM traversal, etc.
└──────────────────┘
```

## Quick Start

### Recommended: Aspose-compatible API (`aspose.note`)

```python
from aspose.note import Document, SaveFormat

doc = Document("MyNotes.one")

for page in doc:
    title = page.Title.TitleText.Text if page.Title and page.Title.TitleText else "(untitled)"
    print(title)

# Export (PDF is supported; other formats may raise UnsupportedSaveFormatException)
doc.Save("out.pdf", SaveFormat.Pdf)
```

### Convenience API (`onenote`)

```python
from onenote import Document

# Open a OneNote section file
doc = Document.open("MyNotes.one")

# Iterate over pages
for page in doc:
    print(f"Page: {page.title}")
    print(page.text)
    print()
```

## Object Model

### Document

The root container representing a `.one` section file.

```python
from onenote import Document

doc = Document.open("notes.one")

# Properties
doc.pages           # List[Page] - all pages
doc.page_count      # int - number of pages
doc.display_name    # str | None - section display name
doc.source_path     # Path | None - original file path

# Methods
doc.get_page(0)             # Page | None
doc.find_pages("keyword")   # List[Page] - search by title (partial match)
doc.find_pages("keyword", case_sensitive=True)
doc.iter_pages()            # Iterator[Page]

# Alternative constructors
doc = Document.from_bytes(data)
doc = Document.from_stream(stream)

# Export
doc.export_pdf("out.pdf")   # requires reportlab

# Iteration
for page in doc:
    ...
page = doc[0]  # indexing
len(doc)       # page count
```

### Page

A page within the document.

```python
page = doc.pages[0]

# Properties
page.title          # str - page title
page.title_element  # Title | None - full title with formatting
page.children       # List[Element] - page content
page.level          # int - hierarchy level (0=top, 1+=subpage)
page.created        # datetime | None
page.modified       # datetime | None
page.text           # str - all text content

# Additional metadata (best-effort)
page.author         # str | None
page.alternative_title  # str | None
page.is_conflict    # bool | None
page.is_read_only   # bool | None
page.width          # float | None (points)
page.height         # float | None (points)

# Iteration methods
page.iter_outlines()    # Iterator[Outline]
page.iter_elements()    # Iterator[OutlineElement]
page.iter_text()        # Iterator[RichText]
page.iter_images()      # Iterator[Image]
page.iter_tables()      # Iterator[Table]
page.iter_attachments() # Iterator[AttachedFile]

# Debug/introspection helpers
page.iter_all_elements()  # Iterator[Element] - recursive
page.all_elements         # List[Element] - eager list (useful in a debugger)
```

### Title

Page title element with formatting.

```python
title = page.title_element

title.text      # str - plain text
title.children  # List[Element] - formatted content
str(title)      # same as title.text
```

### Outline

A content block on the page (like a text box).

```python
for outline in page.iter_outlines():
    # Properties
    outline.children  # List[OutlineElement]
    outline.x         # float | None - position
    outline.y         # float | None
    outline.width     # float | None
    outline.text      # str - all text joined with newlines

    # Iteration
    outline.iter_elements()  # Iterator[OutlineElement]
    outline.iter_text()      # Iterator[RichText]
```

### OutlineElement

A paragraph-like element within an outline. Can be nested for lists.

```python
for elem in outline.iter_elements():
    # Properties
    elem.children       # List[Element] - nested elements (for lists)
    elem.contents       # List[Element] - actual content
    elem.indent_level   # int - indentation level
    elem.is_numbered    # bool - numbered list item?
    elem.list_format    # str | None - list marker format (best-effort)
    elem.list_restart   # int | None - explicit number override, when present
    elem.text           # str - text content

    # Iteration
    elem.iter_text()    # Iterator[RichText]
    elem.iter_all()     # Iterator[OutlineElement] - recursive
```

### RichText

Text content with formatting.

```python
for rt in page.iter_text():
    rt.text   # str - plain text content
    rt.runs   # List[TextRun] - formatting runs (may be empty)
    rt.tags   # List[NoteTag] - OneNote tags (may be empty)
    rt.font_size_pt  # float | None
    str(rt)   # same as rt.text
```

### TextRun, TextStyle

Formatting is represented as runs over `RichText.text`.

```python
from onenote import TextRun, TextStyle

run = rt.runs[0]
run.start     # int - character start (CP)
run.end       # int - character end (CP)
run.style     # TextStyle

style = run.style
style.bold, style.italic, style.underline
style.font_name, style.font_size_pt
style.font_color, style.highlight_color
style.hyperlink  # str | None
```

### NoteTag

OneNote tags are best-effort extracted and can appear on text, lists, images, tables, and attachments.

```python
from onenote import NoteTag

tag = rt.tags[0]
tag.shape            # int | None
tag.label            # str | None
tag.text_color       # int | None
tag.highlight_color  # int | None
tag.created          # int | None
tag.completed        # int | None
```

### Image

Embedded image.

```python
for image in page.iter_images():
    image.alt_text  # str | None
    image.filename  # str | None
    image.data      # bytes - raw image data
    image.width     # float | None
    image.height    # float | None
    image.format    # str | None - 'png', 'jpeg', etc.
    image.hyperlink # str | None
    image.tags      # List[NoteTag]
    image.x         # float | None - position on page (points), when available
    image.y         # float | None
```

### Table, TableRow, TableCell

Table structure.

```python
for table in page.iter_tables():
    # Properties
    table.rows          # List[TableRow]
    table.row_count     # int
    table.column_count  # int
    table.tags          # List[NoteTag]
    table.column_widths # List[float]
    table.borders_visible  # bool

    # Access
    table[0]            # first row
    table.cell(0, 1)    # row 0, column 1

    for row in table:
        row.cells       # List[TableCell]
        for cell in row:
            cell.children  # List[Element]
            cell.text      # str - cell text
```

### AttachedFile

Embedded file attachment.

```python
for attachment in page.iter_attachments():
    attachment.filename   # str
    attachment.extension  # str | None
    attachment.data       # bytes
    attachment.size       # int
    attachment.tags       # List[NoteTag]
```

## PDF Export

PDF export is available in the `onenote` API via `Document.export_pdf(...)`.

Prerequisites:
- Install ReportLab: `pip install reportlab`
- Or, if you installed this repository from PyPI: `pip install "aspose-note[pdf]"`

```python
from onenote import Document

doc = Document.open("notes.one")
doc.export_pdf("out.pdf")
```

Advanced usage:

```python
from onenote import PdfExportOptions, PdfExporter

options = PdfExportOptions(
    default_font_size=11,
    include_images=True,
    include_tags=True,
    tag_icon_dir="./tag-icons",  # optional custom icons (PNG)
)
PdfExporter(options).export(doc, "out.pdf")
```

## Common Patterns

### Extract all text from document

```python
doc = Document.open("notes.one")

for page in doc:
    print(f"=== {page.title} ===")
    print(page.text)
    print()
```

### Find pages containing specific text

```python
doc = Document.open("notes.one")

# Search in titles
pages = doc.find_pages("meeting")

# Search in content
for page in doc:
    if "important" in page.text.lower():
        print(page.title)
```

### Extract all images

```python
doc = Document.open("notes.one")

for i, page in enumerate(doc):
    for j, image in enumerate(page.iter_images()):
        if image.data:
            ext = image.format or "png"
            filename = f"page{i}_image{j}.{ext}"
            with open(filename, "wb") as f:
                f.write(image.data)
```

### Process tables

```python
doc = Document.open("notes.one")

for page in doc:
    for table in page.iter_tables():
        print(f"Table: {table.row_count}x{table.column_count}")
        for row in table:
            cells = [cell.text for cell in row]
            print(" | ".join(cells))
```

## Error Handling

```python
from onenote import Document

try:
    doc = Document.open("notes.one")
except FileNotFoundError:
    print("File not found")
except ValueError as e:
    print(f"Parse error: {e}")

# Strict mode - raises on format violations
doc = Document.open("notes.one", strict=True)

# Tolerant mode (default) - tries to recover
doc = Document.open("notes.one", strict=False)

Note: parsing errors are currently surfaced as `ValueError` from the public API.
```

## Element Base Class

All elements inherit from `Element`:

```python
class Element:
    id: str  # unique identifier (hex string); may be empty if not present

    def iter_children(self) -> Iterator[Element]:
        ...
```
