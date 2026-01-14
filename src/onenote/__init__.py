"""Compatibility wrapper for the OneNote parser package.

One source of truth lives under :mod:`aspose.note._internal.onenote`.
This top-level package exists for developer convenience and backward-compatible
imports (e.g. ``from onenote import Document``).
"""

from __future__ import annotations

import importlib
import sys


_INTERNAL_PKG = "aspose.note._internal.onenote"

# Ensure submodule imports like `import onenote.parser` resolve to internal code
# even though the real implementation is vendored under aspose.note._internal.
for _sub in ("document", "elements", "parser", "pdf_export"):
    sys.modules[f"{__name__}.{_sub}"] = importlib.import_module(f"{_INTERNAL_PKG}.{_sub}")

_internal = importlib.import_module(_INTERNAL_PKG)

__all__ = list(getattr(_internal, "__all__", []))
__version__ = getattr(_internal, "__version__", "0.0.0")

for _name in __all__:
    globals()[_name] = getattr(_internal, _name)
