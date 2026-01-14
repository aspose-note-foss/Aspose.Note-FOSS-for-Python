# Mapping MS-ONE model → public DOM

## 1) Define public DOM types

Recommended core types:

- `Document`
  - pages: list<Page>
  - metadata: title, authors, etc. (optional)
- `Page`
  - title: RichText
  - elements: list<Outline>
- `Outline`
  - elements: list<OutlineElement>
- `OutlineElement`
  - one of: RichText, Image, AttachedFile, Table, CompositeNode content
  - layout: position/size (optional)
- `RichText`
  - text: string
  - Runs: list<TextRun> where TextRun has `Start/End` + `Style: TextStyle`
- `Image`
  - bytes (or lazy ref)
  - filename (optional)
  - width/height (optional)
- `AttachedFile`
  - bytes (or lazy ref)
  - filename
- `Table`
  - rows/cells; each cell contains elements
- `NoteTag`
  - shape/label + optional colors/timestamps

## 2) Mapping rules

- Preserve order deterministically.
- Normalize missing fields to safe defaults.
- Preserve unknown entities as generic `Node`/`CompositeNode` placeholders (optional) so exports can still run.

## 3) Formatting and runs

- Convert MS-ONE style run representation to public `TextRun` values.
- Normalize ranges to `[start, end)` and validate boundaries.
- Keep hyperlink in `TextStyle` (e.g., `IsHyperlink` + `HyperlinkAddress`).

## Reference mapping

- Adapter: `src/aspose/note/_internal/onenote/document.py` and `src/aspose/note/model.py`
- RichText conversion: `src/aspose/note/_internal/onenote/elements.py`
- Parser: `src/aspose/note/_internal/onenote/parser.py`
