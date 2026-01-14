# Public API layer overview (Aspose.Note-like)

This layer provides a user-facing Document Object Model (DOM) and saving/export functions.

## Goals

- Provide stable, ergonomic classes:
  - Document, Page, Outline, OutlineElement
  - RichText (with runs)
  - Image, AttachedFile
  - Table
  - NoteTag
- Provide export:
  - PDF export
  - image extraction
  - text extraction

## Key constraint

The public API layer must not depend on OneStore parsing details.

It consumes only the internal OneNote document model produced by the MS-ONE layer.

## Reference mapping

- Public API: `src/aspose/note/model.py`, `src/aspose/note/saving/*`, `src/aspose/note/enums.py`
- Internal OneNote model + adapter: `src/aspose/note/_internal/onenote/*`
- Tests: `tests/test_aspose_note_*`, `tests/test_pdf_export.py`
