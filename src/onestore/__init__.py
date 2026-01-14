"""Compatibility wrapper for the OneStore reader package.

One source of truth lives under :mod:`aspose.note._internal.onestore`.
This top-level package exists for developer convenience and backward-compatible
imports.
"""

from __future__ import annotations

import importlib
import sys


_INTERNAL_PKG = "aspose.note._internal.onestore"

for _sub in (
    "chunk_refs",
    "common_types",
    "crc",
    "errors",
    "file_data",
    "file_node_core",
    "file_node_list",
    "file_node_types",
    "hashed_chunk_list",
    "header",
    "io",
    "object_data",
    "object_space",
    "parse_context",
    "summary",
    "txn_log",
):
    sys.modules[f"{__name__}.{_sub}"] = importlib.import_module(f"{_INTERNAL_PKG}.{_sub}")

_internal = importlib.import_module(_INTERNAL_PKG)

__all__ = list(getattr(_internal, "__all__", []))

for _name in __all__:
    globals()[_name] = getattr(_internal, _name)
