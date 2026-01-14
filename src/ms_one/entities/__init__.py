"""Compatibility wrapper for :mod:`ms_one.entities`.

One source of truth lives under :mod:`aspose.note._internal.ms_one.entities`.
"""

from __future__ import annotations

import importlib
import sys


_INTERNAL_PKG = "aspose.note._internal.ms_one.entities"

for _sub in ("base", "parsers", "structure"):
	sys.modules[f"{__name__}.{_sub}"] = importlib.import_module(f"{_INTERNAL_PKG}.{_sub}")

from aspose.note._internal.ms_one.entities.base import BaseNode, UnknownNode  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import Section  # noqa: E402

__all__ = ["BaseNode", "UnknownNode", "Section"]
