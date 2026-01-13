# Aspose.Note for Python (Aspose.Note-compatible API)

This repository provides a Python library with an **Aspose.Note-shaped public API** for reading Microsoft OneNote files (`.one`).

The goal is to offer a familiar surface (`aspose.note.*`) inspired by [Aspose.Note for .NET](https://products.aspose.com/note/net/), backed by this repository’s built-in MS-ONE/OneStore parser.

## Features

- ✅ Read `.one` from a file path or a binary stream
- ✅ Aspose-like DOM (Document/Page/Outline/…): traversal + type-based search
- ✅ Content extraction
  - ✅ Rich text with formatting runs (TextRun/TextStyle) and hyperlinks
  - ✅ Images (bytes, file name, dimensions)
  - ✅ Attached files (bytes, file name)
  - ✅ Tables (rows/cells + cell content)
  - ✅ OneNote tags (NoteTag) on text/images/tables/list elements
  - ✅ Numbered lists (NumberList) and indent levels
- ✅ PDF export via `Document.Save(..., SaveFormat.Pdf)` (uses ReportLab)

## Quick start

```python
from aspose.note import Document

doc = Document("testfiles/SimpleTable.one")
print(doc.DisplayName)
print(doc.Count())

# pages are direct children of Document
for page in doc:
    print(page.Title.TitleText.Text)
```

### Export to PDF

```python
from aspose.note import Document, SaveFormat

doc = Document("testfiles/FormattedRichText.one")
doc.Save("out.pdf", SaveFormat.Pdf)
```

## Installation

From a local checkout:

```bash
python -m pip install -e .
```

PDF export requires ReportLab:

```bash
python -m pip install -e ".[pdf]"
```

## Public API (what is considered supported)

Only the `aspose.note` package is considered **public and supported**.
Everything under `aspose.note._internal` is internal implementation detail and may change.

Below is a complete list of objects exported from `aspose.note.__init__`.

### Document and traversal

- `Document(source=None, load_options=None)`
  - `DisplayName: str | None`
  - `CreationTime: datetime | None`
  - `Count() -> int` — number of pages (direct children of Document)
  - iteration: `for page in doc: ...`
  - `FileFormat -> FileFormat` (best-effort)
  - `GetPageHistory(page) -> list[Page]` (currently returns `[page]`)
  - `DetectLayoutChanges()` (compatibility stub)
  - `Save(target, format_or_options=None)`
    - supported: `SaveFormat.Pdf`
    - other `SaveFormat` values currently raise `UnsupportedSaveFormatException`

- `DocumentVisitor` — base visitor for traversal:
  - `VisitDocumentStart/End`, `VisitPageStart/End`, `VisitTitleStart/End`, `VisitOutlineStart/End`,
    `VisitOutlineElementStart/End`, `VisitRichTextStart/End`, `VisitImageStart/End`

- `Node`
  - `ParentNode`
  - `Document` (property) — walk up to the root `Document`
  - `Accept(visitor)`

- `CompositeNode(Node)`
  - `FirstChild`, `LastChild`
  - `AppendChildLast(node)`, `AppendChildFirst(node)`, `InsertChild(index, node)`, `RemoveChild(node)`
  - `GetEnumerator()` / iteration `for child in node: ...`
  - `GetChildNodes(Type) -> list[Type]` — recursive search by type

### Document structure

- `Page(CompositeNode)`
  - `Title: Title | None`
  - `Author: str | None`
  - `CreationTime: datetime | None`, `LastModifiedTime: datetime | None`
  - `Level: int | None`
  - `Clone(deep=False) -> Page` (minimal clone)

- `Title(CompositeNode)`
  - `TitleText: RichText | None`
  - `TitleDate: RichText | None`
  - `TitleTime: RichText | None`

- `Outline(CompositeNode)`
  - `X`, `Y`, `Width` (positioning)

- `OutlineElement(CompositeNode)`
  - `IndentLevel: int`
  - `NumberList: NumberList | None`
  - `Tags: list[NoteTag]`

### Content

- `RichText(CompositeNode)`
  - `Text: str`
  - `Runs: list[TextRun]` — formatted segments
  - `FontSize: float | None`
  - `Tags: list[NoteTag]`
  - `Append(text, style=None) -> RichText`
  - `Replace(old_value, new_value) -> None`

- `TextRun(Node)`
  - `Text: str`
  - `Style: TextStyle`
  - `Start: int | None`, `End: int | None`

- `TextStyle(Node)`
  - `Bold/Italic/Underline/Strikethrough/Superscript/Subscript: bool`
  - `FontName: str | None`, `FontSize: float | None`
  - `FontColor: int | None`, `HighlightColor: int | None`
  - `LanguageId: int | None`
  - `IsHyperlink: bool`, `HyperlinkAddress: str | None`

- `Image(CompositeNode)`
  - `FileName: str | None`, `Bytes: bytes`
  - `Width: float | None`, `Height: float | None`
  - `AlternativeTextTitle: str | None`, `AlternativeTextDescription: str | None`
  - `HyperlinkUrl: str | None`
  - `Tags: list[NoteTag]`
  - `Replace(image) -> None` — replace image contents

- `AttachedFile(CompositeNode)`
  - `FileName: str | None`, `Bytes: bytes`
  - `Tags: list[NoteTag]`

- `Table(CompositeNode)`
  - `ColumnWidths: list[float]`
  - `BordersVisible: bool`
  - `Tags: list[NoteTag]`

- `TableRow(CompositeNode)`, `TableCell(CompositeNode)`

- `NoteTag(Node)`
  - fields: `shape`, `label`, `text_color`, `highlight_color`, `created`, `completed`
  - `CreateYellowStar()` — convenience factory

- `NumberList(Node)`
  - `Format: str | None`, `Restart: int | None`, `IsNumbered: bool`

### Load/save options

- `LoadOptions`
  - `DocumentPassword: str | None` (password/encryption is **not supported**)
  - `LoadHistory: bool`

- `SaveOptions` (base)
  - `SaveFormat: SaveFormat`

- `PdfSaveOptions(SaveOptions)` (subset)
  - `PageIndex: int`, `PageCount: int | None`
  - `TagIconDir: str | None`, `TagIconSize: float | None`, `TagIconGap: float | None`

- `OneSaveOptions`, `HtmlSaveOptions`, `ImageSaveOptions` — declared for API compatibility but not implemented.

### Enums

- `SaveFormat`: `One`, `Pdf`, `Html`, plus raster formats (`Jpeg`, `Png`, `Gif`, `Bmp`, `Tiff`)
- `FileFormat`: `OneNote2010`, `OneNoteOnline`, `OneNote2007`
- `HorizontalAlignment`: `Left`, `Center`, `Right`
- `NodeType`: `Document`, `Page`, `Outline`, `OutlineElement`, `RichText`, `Image`, `Table`, `AttachedFile`

### Exceptions

- `AsposeNoteError` (base)
- `FileCorruptedException`
- `IncorrectDocumentStructureException`
- `IncorrectPasswordException`
- `UnsupportedFileFormatException` (has a `FileFormat` field)
- `UnsupportedSaveFormatException`

## Examples

### Extract all text from a document

```python
from aspose.note import Document, RichText

doc = Document("testfiles/FormattedRichText.one")
texts = [rt.Text for rt in doc.GetChildNodes(RichText)]
print("\n".join(texts))
```

### Save all images to disk

```python
from aspose.note import Document, Image

doc = Document("testfiles/3ImagesWithDifferentAlignment.one")
for i, img in enumerate(doc.GetChildNodes(Image), start=1):
    name = img.FileName or f"image_{i}.bin"
    with open(name, "wb") as f:
        f.write(img.Bytes)
```

### PDF export with custom tag icons

```python
from aspose.note import Document, PdfSaveOptions, SaveFormat

doc = Document("testfiles/TagSizes.one")
opts = PdfSaveOptions(
    SaveFormat=SaveFormat.Pdf,
    TagIconDir="./tag-icons",
    TagIconSize=10,
    TagIconGap=2,
)
doc.Save("out.pdf", opts)
```

### Load from a binary stream

```python
from pathlib import Path
from aspose.note import Document

one_path = Path("testfiles/SimpleTable.one")
with one_path.open("rb") as f:
  doc = Document(f)

print(doc.DisplayName)
print(doc.Count())
```

### Traverse the DOM and print a simple outline

```python
from aspose.note import Document, Page, Outline, OutlineElement, RichText

doc = Document("testfiles/SimpleTable.one")

for page in doc.GetChildNodes(Page):
  title = page.Title.TitleText.Text if page.Title and page.Title.TitleText else "(no title)"
  print(f"# {title}")

  for outline in page.GetChildNodes(Outline):
    for oe in outline.GetChildNodes(OutlineElement):
      # OutlineElement may contain RichText, Table, Image, etc.
      texts = [rt.Text for rt in oe.GetChildNodes(RichText)]
      if texts:
        print("-", " ".join(t.strip() for t in texts if t.strip()))
```

### Use `DocumentVisitor` to count nodes

```python
from aspose.note import Document, DocumentVisitor, Page, Image, RichText


class Counter(DocumentVisitor):
  def __init__(self) -> None:
    self.pages = 0
    self.rich_texts = 0
    self.images = 0

  def VisitPageStart(self, page: Page) -> None:  # noqa: N802
    self.pages += 1

  def VisitRichTextStart(self, rich_text: RichText) -> None:  # noqa: N802
    self.rich_texts += 1

  def VisitImageStart(self, image: Image) -> None:  # noqa: N802
    self.images += 1


doc = Document("testfiles/3ImagesWithDifferentAlignment.one")
counter = Counter()
doc.Accept(counter)
print(counter.pages, counter.rich_texts, counter.images)
```

### Extract hyperlinks from formatted text

```python
from aspose.note import Document, RichText

doc = Document("testfiles/FormattedRichText.one")
for rt in doc.GetChildNodes(RichText):
  for run in rt.Runs:
    if run.Style.IsHyperlink and run.Style.HyperlinkAddress:
      print(run.Text, "->", run.Style.HyperlinkAddress)
```

### Inspect tags (NoteTag) across the document

```python
from aspose.note import Document, RichText, Image, Table

doc = Document("testfiles/TagSizes.one")

def dump_tags(kind: str, tags) -> None:
  for t in tags:
    print(kind, "tag:", t.label)

for rt in doc.GetChildNodes(RichText):
  dump_tags("RichText", rt.Tags)

for img in doc.GetChildNodes(Image):
  dump_tags("Image", img.Tags)

for tbl in doc.GetChildNodes(Table):
  dump_tags("Table", tbl.Tags)
```

### Work with tables (rows/cells)

```python
from aspose.note import Document, Table, TableRow, TableCell, RichText

doc = Document("testfiles/SimpleTable.one")

for table in doc.GetChildNodes(Table):
  print("Table columns:", table.ColumnWidths)
  for row_index, row in enumerate(table.GetChildNodes(TableRow), start=1):
    cells = row.GetChildNodes(TableCell)
    values: list[str] = []
    for cell in cells:
      cell_text = " ".join(rt.Text for rt in cell.GetChildNodes(RichText)).strip()
      values.append(cell_text)
    print(f"Row {row_index}:", values)
```

### Extract attached files

```python
from aspose.note import Document, AttachedFile

doc = Document("testfiles/OnePageWithFile.one")

for i, af in enumerate(doc.GetChildNodes(AttachedFile), start=1):
  name = af.FileName or f"attachment_{i}.bin"
  with open(name, "wb") as f:
    f.write(af.Bytes)
  print("saved:", name)
```

### Inspect list formatting (NumberList) and indentation

```python
from aspose.note import Document, OutlineElement

doc = Document("testfiles/NumberedListWithTags.one")

for oe in doc.GetChildNodes(OutlineElement):
  nl = oe.NumberList
  if nl is None:
    continue
  print(
    "indent=", oe.IndentLevel,
    "is_numbered=", nl.IsNumbered,
    "format=", nl.Format,
    "restart=", nl.Restart,
  )
```

### Handle unsupported/encrypted documents explicitly

```python
from aspose.note import Document, LoadOptions, IncorrectPasswordException

try:
  doc = Document("some_encrypted.one", LoadOptions(DocumentPassword="secret"))
except IncorrectPasswordException as e:
  print("Encrypted documents are not supported:", e)
```

## Current limitations

- The implementation focuses on **reading** `.one` and building a DOM; writing back to `.one` is not implemented.
- `DocumentPassword` / encrypted documents are not supported (raises `IncorrectPasswordException`).
- Saving formats other than PDF (HTML/images/ONE) are declared for compatibility but not implemented.

## Other platforms (official Aspose.Note)

If you need the full-featured Aspose product (writing/conversion, broader compatibility, etc.), see the official libraries:

- Aspose.Note for .NET
  - Product: https://products.aspose.com/note/net/
  - Documentation: https://docs.aspose.com/note/net/

- Aspose.Note for Java
  - Product: https://products.aspose.com/note/java/
  - Documentation: https://docs.aspose.com/note/java/

## Development

Run tests:

```bash
python -m pip install -e ".[pdf]"
python -m unittest discover -s tests -p "test_*.py" -v
```
