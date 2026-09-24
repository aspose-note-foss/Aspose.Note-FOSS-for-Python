# aspose-note has been renamed to aspose-note-foss

**This package is deprecated.** Aspose.Note FOSS for Python is now published on PyPI as
[`aspose-note-foss`](https://pypi.org/project/aspose-note-foss/), consistent with other Aspose FOSS packages.

This release of `aspose-note` contains no code — it only installs `aspose-note-foss` as a dependency,
and will not receive further updates.

## How to migrate

```bash
pip uninstall -y aspose-note
pip install aspose-note-foss            # or: pip install "aspose-note-foss[pdf]"
```

Replace `aspose-note` with `aspose-note-foss` in `requirements.txt`, `pyproject.toml`, etc.

Your code does not change — the import package is still `aspose.note`:

```python
from aspose.note import Document
```

## Troubleshooting: `ModuleNotFoundError: No module named 'aspose'` after upgrading

If you ran `pip install -U aspose-note` over an older `aspose-note` (26.3.2 or earlier), pip removes the old
package's files after installing `aspose-note-foss`, and both packages ship the same `aspose/note` files.
Restore them with:

```bash
pip install --force-reinstall --no-deps aspose-note-foss
```

Fresh installs are not affected.

Source code and issues: https://github.com/aspose-note-foss/Aspose.Note-FOSS-for-Python
