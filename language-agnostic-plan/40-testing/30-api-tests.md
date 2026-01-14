# Public API tests

## 1) DOM shape tests

- Construct Document from file; assert:
  - page count
  - title text
  - outline counts
  - presence of images/attachments/tables

## 2) RichText formatting tests

- Verify runs are stable and cover the whole text.
- Verify styles map to public fields.

## 3) Tags and lists

- Ensure tags appear in the right elements.
- Ensure list metadata is exposed in a stable way.

## 4) Save/export tests

- PDF export smoke test:
  - creates a PDF
  - file size > minimal threshold
- Option tests:
  - unsupported formats raise `UnsupportedSaveFormatException`
  - options are accepted/ignored in a documented way

## 5) Compatibility tests

If you aim to match Aspose.Note behavior:

- verify exception types and messages for known failure modes
- verify that unsupported features fail gracefully

## Reference mapping

- DOM tests: `tests/test_aspose_note_dom_*`
- Save options: `tests/test_aspose_note_save_options.py`
- PDF export: `tests/test_pdf_export.py`
- Compatibility smoke: `tests/test_aspose_note_compat_smoke.py`
