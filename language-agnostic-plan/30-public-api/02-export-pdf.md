# PDF export (high-level plan)

PDF export is usually the first “real” output format because it exercises:

- layout ordering
- text rendering
- images/attachments placeholders
- table rendering
- tags and list numbering

## Recommended design

- Keep PDF generation in a separate `export/pdf` module.
- Use a PDF library appropriate for the language (ReportLab, iText, PdfBox, Cairo, etc.).

## Rendering pipeline

1) Traverse Document → Pages.
2) For each page:
   - compute page size (fixed default or auto-fit content extents)
   - order outlines by their layout coordinates (top-to-bottom, left-to-right)
   - render title
   - render outlines:
     - RichText → paragraphs
     - Image → raster placement
    - AttachedFile → icon + filename + optional embedded bytes not shown
     - Table → grid layout
3) Apply options:
   - page size
   - margins
   - font embedding

## Lists and numbering

- Convert list metadata into a “numbering context”.
- Render markers (decimal/alpha/roman) consistently.

## Tags

- Provide a tag icon registry:
  - builtin fallback rendering
  - optional user-supplied images

## Reference mapping

- `src/aspose/note/_internal/onenote/pdf_export.py`
- Tests: `tests/test_pdf_export.py`
