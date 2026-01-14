"""Compatibility wrapper for the MS-ONE reader package.

One source of truth lives under :mod:`aspose.note._internal.ms_one`.
This top-level package exists for developer convenience and backward-compatible
imports.
"""

from __future__ import annotations

import importlib
import sys


_INTERNAL_PKG = "aspose.note._internal.ms_one"

for _sub in (
    "compact_id",
    "errors",
    "object_index",
    "property_access",
    "reader",
    "spec_ids",
    "types",
):
    sys.modules[f"{__name__}.{_sub}"] = importlib.import_module(f"{_INTERNAL_PKG}.{_sub}")

_internal = importlib.import_module(_INTERNAL_PKG)

__all__ = list(getattr(_internal, "__all__", []))

for _name in __all__:
    globals()[_name] = getattr(_internal, _name)
