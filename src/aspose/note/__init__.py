"""Aspose.Note-compatible public API (Python).

Goal: provide a Python surface that mirrors the *public API shape* of Aspose.Note for .NET,
backed by this repository's existing OneNote reader implementation.

This is intentionally a thin compatibility layer.
"""

from __future__ import annotations

from .enums import FileFormat, HorizontalAlignment, NodeType, SaveFormat
from .exceptions import (
    AsposeNoteError,
    FileCorruptedException,
    IncorrectDocumentStructureException,
    IncorrectPasswordException,
    UnsupportedFileFormatException,
    UnsupportedSaveFormatException,
)
from .model import (
    Document,
    Page,
    Title,
    Outline,
    OutlineElement,
    RichText,
    Image,
    Table,
    TableRow,
    TableCell,
    AttachedFile,
    NoteTag,
    NumberList,
    TextStyle,
    TextRun,
    DocumentVisitor,
    LoadOptions,
    License,
    Metered,
)

from .saving import HtmlSaveOptions, ImageSaveOptions, OneSaveOptions, PdfSaveOptions, SaveOptions

__all__ = [
    "SaveFormat",
    "FileFormat",
    "HorizontalAlignment",
    "NodeType",
    "AsposeNoteError",
    "FileCorruptedException",
    "IncorrectDocumentStructureException",
    "IncorrectPasswordException",
    "UnsupportedFileFormatException",
    "UnsupportedSaveFormatException",
    "Document",
    "Page",
    "Title",
    "Outline",
    "OutlineElement",
    "RichText",
    "Image",
    "Table",
    "TableRow",
    "TableCell",
    "AttachedFile",
    "NoteTag",
    "NumberList",
    "TextStyle",
    "TextRun",
    "DocumentVisitor",
    "LoadOptions",
    "License",
    "Metered",
    "SaveOptions",
    "OneSaveOptions",
    "PdfSaveOptions",
    "HtmlSaveOptions",
    "ImageSaveOptions",
]
