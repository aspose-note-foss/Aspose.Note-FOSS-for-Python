# Aspose.Note for Python (compatibility API)

This repository provides an **Aspose.Note-compatible** public API in Python for reading Microsoft OneNote section files (`.one`).

## Public API

Only the `aspose.note` package is considered public and supported.

```python
from aspose.note import Document

doc = Document("testfiles/SimpleTable.one")
print(doc.DisplayName)
print(doc.Count())
```

## Notes

- Other modules in this repository (including parsing internals) are implementation details and are not part of the supported public API surface.
- PDF export is supported via `Document.Save(..., SaveFormat.Pdf)`.
