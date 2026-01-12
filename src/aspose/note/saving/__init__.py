from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..enums import SaveFormat


@dataclass
class SaveOptions:
    """Base save options class (compatibility stub)."""

    SaveFormat: SaveFormat  # noqa: N815


@dataclass
class OneSaveOptions(SaveOptions):
    """Options for saving to OneNote format (not implemented)."""

    DocumentPassword: str | None = None  # noqa: N815


@dataclass
class PdfSaveOptions(SaveOptions):
    """Options for saving to PDF (subset)."""

    PageIndex: int = 0  # noqa: N815
    PageCount: int | None = None  # noqa: N815

    TagIconDir: str | None = None  # noqa: N815
    """Optional directory containing custom tag icons (PNG).

    See `onenote.pdf_export.PdfExportOptions.tag_icon_dir` for naming rules.
    """

    TagIconSize: float | None = None  # noqa: N815
    """Override tag icon size in points."""

    TagIconGap: float | None = None  # noqa: N815
    """Override horizontal gap between tag icons in points."""


@dataclass
class HtmlSaveOptions(SaveOptions):
    """Options for saving to HTML (not implemented)."""

    PageIndex: int = 0  # noqa: N815
    PageCount: int | None = None  # noqa: N815


@dataclass
class ImageSaveOptions(SaveOptions):
    """Options for saving to raster images (not implemented)."""

    PageIndex: int = 0  # noqa: N815
    PageCount: int | None = None  # noqa: N815
    Quality: int | None = None  # noqa: N815
    Resolution: int | None = None  # noqa: N815


__all__ = [
    "SaveOptions",
    "OneSaveOptions",
    "PdfSaveOptions",
    "HtmlSaveOptions",
    "ImageSaveOptions",
]
