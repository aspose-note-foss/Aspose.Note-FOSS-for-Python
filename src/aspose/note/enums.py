from __future__ import annotations

import enum


class SaveFormat(enum.Enum):
    """Indicates the format in which the document is saved.

    Mirrors Aspose.Note for .NET `Aspose.Note.SaveFormat`.
    """

    One = "one"
    Pdf = "pdf"
    Html = "html"

    # Raster formats (not fully implemented in this repo yet)
    Jpeg = "jpeg"
    Png = "png"
    Gif = "gif"
    Bmp = "bmp"
    Tiff = "tiff"


class FileFormat(enum.Enum):
    """Represents OneNote file format (compatibility stub)."""

    OneNote2010 = "onenote2010"
    OneNoteOnline = "onenoteonline"
    OneNote2007 = "onenote2007"


class HorizontalAlignment(enum.Enum):
    Left = "left"
    Center = "center"
    Right = "right"


class NodeType(enum.Enum):
    Document = "document"
    Page = "page"
    Outline = "outline"
    OutlineElement = "outline_element"
    RichText = "rich_text"
    Image = "image"
    Table = "table"
    AttachedFile = "attached_file"
