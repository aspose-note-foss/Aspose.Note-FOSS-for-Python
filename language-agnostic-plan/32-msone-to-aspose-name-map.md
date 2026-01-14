# Naming alignment: MS-ONE → internal OneNote model → Aspose.Note-like DOM

This document exists to avoid “creative naming” during ports.

It maps:

1) **MS-ONE logical entities** (what you parse from OneStore object data)
2) **Internal normalized OneNote model** used by this repo (`src/aspose/note/_internal/onenote/*`)
3) **Public Aspose.Note-like API** used by this repo (`src/aspose/note/model.py`, `src/aspose/note/saving/*`, `src/aspose/note/exceptions.py`)

> Note: The internal MS-ONE layer may use generic terms like “attachment” and “tag”. The public API in this repo uses the concrete class names `AttachedFile` and `NoteTag`.

---

## 1) Document and structure

- MS-ONE: `Notebook/Section` (structure entities)
  - Internal model: `onenote.Document` (holds `pages`)
  - Public API: `Document` (a `CompositeNode` of `Page`)

- MS-ONE: `Page`
  - Internal model: `onenote.elements.Page`
  - Public API: `Page` (with `Title: Title | None` and children)

- MS-ONE: `Title`
  - Internal model: `onenote.elements.Title`
  - Public API: `Title` (node), with `TitleText/TitleDate/TitleTime: RichText | None`

- MS-ONE: `Outline`
  - Internal model: `onenote.elements.Outline`
  - Public API: `Outline`

- MS-ONE: `OutlineElement`
  - Internal model: `onenote.elements.OutlineElement`
  - Public API: `OutlineElement`

---

## 2) Text and formatting

- MS-ONE: Rich text block
  - Internal model: `onenote.elements.RichText`
  - Public API: `RichText`

- MS-ONE: Text style run (range + style)
  - Internal model: `onenote.elements.TextRun` + `onenote.elements.TextStyle` (stored as `RichText.runs`)
  - Public API: `TextRun` + `TextStyle` (stored as `RichText.Runs`)

Naming details (public API):

- `RichText.Text: str`
- `RichText.Runs: list[TextRun]`
- `TextRun.Start: int | None`, `TextRun.End: int | None` (ranges are `[Start, End)`)
- `TextRun.Style: TextStyle`
- hyperlink fields live in `TextStyle`:
  - `TextStyle.IsHyperlink: bool`
  - `TextStyle.HyperlinkAddress: str | None`

---

## 3) Resources (images and attachments)

- MS-ONE: Image
  - Internal model: `onenote.elements.Image`
  - Public API: `Image`
  - Public API key fields: `FileName`, `Bytes`, `Width`, `Height`, `HyperlinkUrl`, `Tags`

- MS-ONE: Attachment (embedded file)
  - Internal model: `onenote.elements.AttachedFile`
  - Public API: `AttachedFile`
  - Public API key fields: `FileName`, `Bytes`, `Tags`

> Terminology rule for docs/ports: use “attachment” as a concept, but when naming public API types, use `AttachedFile`.

---

## 4) Tables

- MS-ONE: Table
  - Internal model: `onenote.elements.Table`
  - Public API: `Table`

- MS-ONE: Row/Cell
  - Internal model: `onenote.elements.TableRow`, `onenote.elements.TableCell`
  - Public API: `TableRow`, `TableCell`

Public API table metadata:

- `Table.ColumnWidths: list[float]`
- `Table.BordersVisible: bool`
- `Table.Tags: list[NoteTag]`

---

## 5) Tags and lists

- MS-ONE: Tag
  - Internal model: `onenote.elements.NoteTag`
  - Public API: `NoteTag`

Public API tag fields:

- `NoteTag.shape`, `NoteTag.label`
- optional colors: `text_color`, `highlight_color`
- optional timestamps: `created`, `completed`

- MS-ONE: List formatting
  - Internal model: `onenote.elements.OutlineElement` carries list metadata
  - Public API: `OutlineElement.NumberList: NumberList | None`

Public API list fields:

- `NumberList.Format: str | None`
- `NumberList.Restart: int | None`
- `NumberList.IsNumbered: bool`

---

## 6) Node/container terminology

Public API base classes (this repo):

- `Node` (base)
- `CompositeNode` (has children)

Docs/ports should prefer these names instead of invented equivalents like “CompositeElement”.

---

## 7) Save options and formats

Public API types:

- `SaveFormat` enum: `One`, `Pdf`, `Html`, plus raster formats (`Png`, `Jpeg`, ...)
- `SaveOptions` base class with `SaveFormat: SaveFormat`
- `PdfSaveOptions`, `HtmlSaveOptions`, `ImageSaveOptions`, `OneSaveOptions`

Page selection fields (public API naming):

- `PageIndex`
- `PageCount`

Public entrypoint naming (public API):

- `Document.Save(target, format_or_options)`

---

## 8) Exceptions

Public API exceptions (this repo):

- `IncorrectPasswordException` (e.g., encrypted docs)
- `UnsupportedFileFormatException` (opening unsupported file format)
- `UnsupportedSaveFormatException` (saving unsupported format)
- `FileCorruptedException`, `IncorrectDocumentStructureException`

When documenting ports:

- Avoid invented names like `NotSupportedError`, `PasswordProtected`, `UnsupportedFormat`.
- Prefer the above names when describing the Aspose.Note-like layer.

---

## Reference implementation pointers

- Public DOM + mapping: `src/aspose/note/model.py`
- Save options: `src/aspose/note/saving/__init__.py`
- Exceptions: `src/aspose/note/exceptions.py`
- Internal normalized model: `src/aspose/note/_internal/onenote/elements.py`
- Internal document wrapper: `src/aspose/note/_internal/onenote/document.py`
