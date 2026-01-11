# OneNote Python Library - Public API

This document describes the public object model for reading OneNote section files (`.one`).

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
│     ONENOTE      │  ◄── Public API
│    (onenote/)    │  Document, Page, Outline, RichText, etc.
└──────────────────┘
```

## Quick Start

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
doc.find_pages("keyword")   # List[Page] - search by title

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

# Iteration methods
page.iter_outlines()    # Iterator[Outline]
page.iter_elements()    # Iterator[OutlineElement]
page.iter_text()        # Iterator[RichText]
page.iter_images()      # Iterator[Image]
page.iter_tables()      # Iterator[Table]
page.iter_attachments() # Iterator[AttachedFile]
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
    str(rt)   # same as rt.text
```

### Image

Embedded image.

```python
for image in page.iter_images():
    image.alt_text  # str | None
    image.data      # bytes - raw image data
    image.width     # float | None
    image.height    # float | None
    image.format    # str | None - 'png', 'jpeg', etc.
```

### Table, TableRow, TableCell

Table structure.

```python
for table in page.iter_tables():
    # Properties
    table.rows          # List[TableRow]
    table.row_count     # int
    table.column_count  # int

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
```

## Element Base Class

All elements inherit from `Element`:

```python
class Element:
    id: str  # unique identifier (hex string)
```
