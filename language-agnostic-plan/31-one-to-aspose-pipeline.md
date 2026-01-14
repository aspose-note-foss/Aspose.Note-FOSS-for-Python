# Detailed pipeline: MS-ONE → Aspose.Note-like public API

This document describes a typical “adapter layer” that maps an internal OneNote model to a public Aspose-style DOM.

---

## Inputs

- `OneNoteDocumentModel` (internal normalized model)

## Outputs

- `AsposeDocument` (public DOM)

---

## Phase A — Create public Document

1) Allocate `Document`.
2) For each internal Page:
   - allocate `Page`
   - map title RichText
   - append to document

---

## Phase B — Map page content

For each Page:

1) Map Outlines in stable visual order.
2) For each internal OutlineElement:
   - dispatch by kind:
  - RichText  `RichText` with runs
    - Image → `Image` (resolve bytes lazily if possible)
    - Attachment → `AttachedFile`
    - Table → `Table`
  - Container → flatten or map to a `CompositeNode`
3) Map tags and list metadata into public fields.

---

## Phase C — Public behaviors

### Visitor/traversal

If the public API exposes visitors:

- implement deterministic traversal
- ensure all node types participate or document limitations

### Save/export

Implement `Document.Save(path, options)`.

- If `options` is `PdfSaveOptions`:
  - render to PDF
- If format unsupported:
  - raise `UnsupportedSaveFormatException`

---

## PDF export integration points

The export engine needs access to:

- resolved image bytes
- text + runs
- table structures
- layout coordinates (optional but improves fidelity)

Design recommendation:

- keep export logic separate from DOM classes
- export accepts the public DOM *or* internal model (choose one and keep stable)

---

## Error boundaries

- Parsing errors should not leak OneStore offsets into the public API unless the API explicitly supports it.
- Unsupported features should map to domain exceptions (e.g., `IncorrectPasswordException`, `UnsupportedSaveFormatException`).

---

## Reference mapping (this repo)

- Public DOM: `src/aspose/note/model.py`
- Public save: `src/aspose/note/model.py` + `src/aspose/note/saving/*`
- Internal adapter: `src/aspose/note/_internal/onenote/parser.py`, `src/aspose/note/_internal/onenote/document.py`, `src/aspose/note/_internal/onenote/elements.py`
- PDF exporter: `src/aspose/note/_internal/onenote/pdf_export.py`
