# MS-ONE logical layer overview

This layer turns OneStore container structures into a **logical OneNote document model**.

It includes:

- selecting the active revision
- building an object index (resolved IDs + properties)
- parsing entity graph (page tree, outlines, rich text, images, attachments, tables, tags, lists)
- resolving external/embedded data (FileDataStore)

## Key design principle

Keep a **normalized internal model** separate from the public API.

This makes it easier to:

- test parsing independently of export/layout
- support multiple public API styles
- evolve entity parsers without breaking user-facing classes

## Recommended internal model

Define immutable-ish structures:

- Document → Sections → Pages
- Page → Title + Outlines
- Outline → OutlineElements (text/image/attachment/table/container)
- RichText  text + runs (style runs)
- Image/Attachment → metadata + blob reference (lazy bytes)
- Table → rows/cells, each cell contains element list
- Tags + list metadata (numbering)

## Reference mapping

- MS-ONE code: `src/aspose/note/_internal/ms_one/*`
- Internal OneNote model: `src/aspose/note/_internal/onenote/*`
- MS-ONE docs: `docs/ms-one/*`
- Tests: `tests/test_ms_one_*`, plus integration tests `tests/test_integration_*`
