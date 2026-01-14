# Save options

The Aspose-style API usually models save options per output format.

Recommended approach:

- Define a base `SaveOptions` with common fields.
- Define format-specific options, e.g. `PdfSaveOptions`, `ImageSaveOptions`.
- Validate unsupported combinations early.

Common PDF options:

- page size (A4/Letter/Custom)
- margins
- font fallback
- rasterization toggle (optional)

Common image options:

- image format (PNG/JPEG)
- resolution
- background color

Page selection:

- `PageIndex`, `PageCount` (optional)

## Reference mapping

- `src/aspose/note/saving/*`
- `src/aspose/note/enums.py`
- Tests: `tests/test_aspose_note_save_options.py`
