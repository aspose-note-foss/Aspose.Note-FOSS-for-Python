# MS OneNote Examples

Minimal, runnable scripts that use the PyPI package `aspose-note` to open and process **Microsoft OneNote** `.one` documents from `../testfiles`.

## Install

Create a dedicated virtual environment under `examples/` and install dependencies from `examples/pyproject.toml`:

```bash
python -m pip install -U pip
python -m pip install -e .
```

## Examples

Run (from `examples/`):

```bash
python extract_text.py
python save_images.py
python export_pdf.py
```

What each script does:

- `extract_text.py` — extract all text from an MS OneNote document (opens `../testfiles/FormattedRichText.one` and prints all `RichText.Text` nodes).
- `save_images.py` — save all images from an MS OneNote document to disk (opens `../testfiles/3ImagesWithDifferentAlignment.one` and writes image blobs to `out_images/`).
- `export_pdf.py` — export an MS OneNote document to PDF (opens `../testfiles/SimpleTable.one` and saves `out.pdf`).
