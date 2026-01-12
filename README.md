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

## Installation

From a local checkout:

```bash
python -m pip install -e .
```

PDF export uses ReportLab:

```bash
python -m pip install -e ".[pdf]"
```

## Publish to PyPI

1) Pick a unique distribution name (PyPI may already have `aspose-note`).

2) Build distributions:

```bash
python -m pip install -U build
python -m build
```

3) Upload (use TestPyPI first):

```bash
python -m pip install -U twine
python -m twine upload --repository testpypi dist/*
python -m twine upload dist/*
```

## Notes

- Other modules in this repository (including parsing internals) are implementation details and are not part of the supported public API surface.
- PDF export is supported via `Document.Save(..., SaveFormat.Pdf)`.
