from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Iterator, TypeVar

from .enums import FileFormat, SaveFormat
from .exceptions import IncorrectPasswordException, UnsupportedSaveFormatException


TNode = TypeVar("TNode", bound="Node")


class DocumentVisitor:
    """Visitor base class (subset) compatible with Aspose.Note for .NET patterns."""

    def VisitDocumentStart(self, document: "Document") -> None:  # noqa: N802
        return None

    def VisitDocumentEnd(self, document: "Document") -> None:  # noqa: N802
        return None

    def VisitPageStart(self, page: "Page") -> None:  # noqa: N802
        return None

    def VisitPageEnd(self, page: "Page") -> None:  # noqa: N802
        return None

    def VisitTitleStart(self, title: "Title") -> None:  # noqa: N802
        return None

    def VisitTitleEnd(self, title: "Title") -> None:  # noqa: N802
        return None

    def VisitOutlineStart(self, outline: "Outline") -> None:  # noqa: N802
        return None

    def VisitOutlineEnd(self, outline: "Outline") -> None:  # noqa: N802
        return None

    def VisitOutlineElementStart(self, outline_element: "OutlineElement") -> None:  # noqa: N802
        return None

    def VisitOutlineElementEnd(self, outline_element: "OutlineElement") -> None:  # noqa: N802
        return None

    def VisitRichTextStart(self, rich_text: "RichText") -> None:  # noqa: N802
        return None

    def VisitRichTextEnd(self, rich_text: "RichText") -> None:  # noqa: N802
        return None

    def VisitImageStart(self, image: "Image") -> None:  # noqa: N802
        return None

    def VisitImageEnd(self, image: "Image") -> None:  # noqa: N802
        return None


class License:
    """Compatibility stub for Aspose.Note.License."""

    def SetLicense(self, license_path_or_stream: Any) -> None:  # noqa: N802
        # Licensing is product-specific and not implemented in this repository.
        return None


class Metered:
    """Compatibility stub for Aspose.Note.Metered."""

    def SetMeteredKey(self, public_key: str, private_key: str) -> None:  # noqa: N802
        return None


@dataclass
class LoadOptions:
    """Load options stub compatible with Aspose.Note.LoadOptions."""

    DocumentPassword: str | None = None
    LoadHistory: bool = False


@dataclass
class Node:
    """Base node for Aspose.Note-like DOM."""

    ParentNode: "Node | None" = field(default=None, repr=False)  # noqa: N815

    @property
    def Document(self) -> "Document | None":  # noqa: N802
        cur: Node | None = self
        while cur is not None and not isinstance(cur, Document):
            cur = cur.ParentNode
        return cur if isinstance(cur, Document) else None

    def Accept(self, visitor: DocumentVisitor) -> None:  # noqa: N802
        self._accept(visitor)

    def _accept(self, visitor: DocumentVisitor) -> None:
        # Default leaf node: nothing to traverse.
        return None


@dataclass
class CompositeNode(Node):
    """A node that can contain other nodes (subset of .NET CompositeNode<T>)."""

    _children: list[Node] = field(default_factory=list, repr=False)

    @property
    def FirstChild(self) -> Node | None:  # noqa: N802
        return self._children[0] if self._children else None

    @property
    def LastChild(self) -> Node | None:  # noqa: N802
        return self._children[-1] if self._children else None

    def AppendChildLast(self, node: TNode) -> TNode:  # noqa: N802
        node.ParentNode = self
        self._children.append(node)
        return node

    def AppendChildFirst(self, node: TNode) -> TNode:  # noqa: N802
        node.ParentNode = self
        self._children.insert(0, node)
        return node

    def InsertChild(self, index: int, node: TNode) -> TNode:  # noqa: N802
        node.ParentNode = self
        self._children.insert(index, node)
        return node

    def RemoveChild(self, node: Node) -> None:  # noqa: N802
        self._children.remove(node)
        node.ParentNode = None

    def GetEnumerator(self) -> Iterator[Node]:  # noqa: N802
        return iter(self._children)

    def __iter__(self) -> Iterator[Node]:
        return iter(self._children)

    def GetChildNodes(self, node_type: type[TNode]) -> list[TNode]:  # noqa: N802
        out: list[TNode] = []

        def walk(n: Node) -> None:
            if isinstance(n, node_type):
                out.append(n)
            if isinstance(n, CompositeNode):
                for c in n._children:
                    walk(c)

        walk(self)
        return out


@dataclass
class NoteTag(Node):
    shape: int | None = None
    label: str | None = None
    text_color: int | None = None
    highlight_color: int | None = None
    created: int | None = None
    completed: int | None = None

    @staticmethod
    def CreateYellowStar() -> "NoteTag":  # noqa: N802
        # Common .NET convenience factory.
        return NoteTag(shape=None, label="Yellow Star")


@dataclass
class TextStyle(Node):
    IsHyperlink: bool = False  # noqa: N815
    HyperlinkAddress: str | None = None  # noqa: N815

    FontName: str | None = None  # noqa: N815
    FontSize: float | None = None  # noqa: N815
    FontColor: int | None = None  # noqa: N815
    HighlightColor: int | None = None  # noqa: N815
    LanguageId: int | None = None  # noqa: N815

    Bold: bool = False  # noqa: N815
    Italic: bool = False  # noqa: N815
    Underline: bool = False  # noqa: N815
    Strikethrough: bool = False  # noqa: N815
    Superscript: bool = False  # noqa: N815
    Subscript: bool = False  # noqa: N815


@dataclass
class TextRun(Node):
    Text: str = ""  # noqa: N815
    Style: TextStyle = field(default_factory=TextStyle)  # noqa: N815
    Start: int | None = None  # noqa: N815
    End: int | None = None  # noqa: N815


@dataclass
class RichText(CompositeNode):
    Text: str = ""  # noqa: N815
    Runs: list[TextRun] = field(default_factory=list)  # noqa: N815
    FontSize: float | None = None  # noqa: N815
    Tags: list[NoteTag] = field(default_factory=list)  # noqa: N815

    def Append(self, text: str, style: TextStyle | None = None) -> "RichText":  # noqa: N802
        self.Text += text
        if style is not None:
            self.Runs.append(TextRun(Text=text, Style=style))
        return self

    def Replace(self, old_value: str, new_value: str) -> None:  # noqa: N802
        self.Text = self.Text.replace(old_value, new_value)

    def _accept(self, visitor: DocumentVisitor) -> None:
        visitor.VisitRichTextStart(self)
        visitor.VisitRichTextEnd(self)


@dataclass
class Title(CompositeNode):
    TitleText: RichText | None = None  # noqa: N815
    TitleDate: RichText | None = None  # noqa: N815
    TitleTime: RichText | None = None  # noqa: N815

    def _accept(self, visitor: DocumentVisitor) -> None:
        visitor.VisitTitleStart(self)
        for child in self._children:
            child._accept(visitor)
        visitor.VisitTitleEnd(self)


@dataclass
class OutlineElement(CompositeNode):
    Tags: list[NoteTag] = field(default_factory=list)  # noqa: N815
    IndentLevel: int = 0  # noqa: N815
    NumberList: "NumberList | None" = None  # noqa: N815

    def _accept(self, visitor: DocumentVisitor) -> None:
        visitor.VisitOutlineElementStart(self)
        for child in self._children:
            child._accept(visitor)
        visitor.VisitOutlineElementEnd(self)


@dataclass
class Outline(CompositeNode):
    X: float | None = None  # noqa: N815
    Y: float | None = None  # noqa: N815
    Width: float | None = None  # noqa: N815

    def _accept(self, visitor: DocumentVisitor) -> None:
        visitor.VisitOutlineStart(self)
        for child in self._children:
            child._accept(visitor)
        visitor.VisitOutlineEnd(self)


@dataclass
class Image(CompositeNode):
    FileName: str | None = None  # noqa: N815
    Bytes: bytes = b""  # noqa: N815
    Width: float | None = None  # noqa: N815
    Height: float | None = None  # noqa: N815

    AlternativeTextTitle: str | None = None  # noqa: N815
    AlternativeTextDescription: str | None = None  # noqa: N815
    HyperlinkUrl: str | None = None  # noqa: N815

    Tags: list[NoteTag] = field(default_factory=list)  # noqa: N815

    def Replace(self, image: "Image") -> None:  # noqa: N802
        self.Bytes = image.Bytes
        self.FileName = image.FileName

    def _accept(self, visitor: DocumentVisitor) -> None:
        visitor.VisitImageStart(self)
        visitor.VisitImageEnd(self)


@dataclass
class AttachedFile(CompositeNode):
    FileName: str | None = None  # noqa: N815
    Bytes: bytes = b""  # noqa: N815
    Tags: list[NoteTag] = field(default_factory=list)  # noqa: N815


@dataclass
class NumberList(Node):
    """Compatibility representation of list formatting.

    This is not a full Aspose.Note for .NET implementation, but it preserves
    MS-ONE list metadata already parsed by this repository.
    """

    Format: str | None = None  # noqa: N815
    Restart: int | None = None  # noqa: N815
    IsNumbered: bool = False  # noqa: N815


@dataclass
class TableCell(CompositeNode):
    pass


@dataclass
class TableRow(CompositeNode):
    pass


@dataclass
class Table(CompositeNode):
    Tags: list[NoteTag] = field(default_factory=list)  # noqa: N815
    ColumnWidths: list[float] = field(default_factory=list)  # noqa: N815
    BordersVisible: bool = True  # noqa: N815


@dataclass
class Page(CompositeNode):
    Title: Title | None = None  # noqa: N815

    Author: str | None = None  # noqa: N815
    CreationTime: datetime | None = None  # noqa: N815
    LastModifiedTime: datetime | None = None  # noqa: N815
    Level: int | None = None  # noqa: N815

    def Clone(self, deep: bool = False) -> "Page":  # noqa: N802
        # Minimal clone.
        cloned = Page(
            Title=self.Title,
            Author=self.Author,
            CreationTime=self.CreationTime,
            LastModifiedTime=self.LastModifiedTime,
            Level=self.Level,
        )
        if deep:
            for child in self._children:
                cloned.AppendChildLast(child)
        return cloned

    def _accept(self, visitor: DocumentVisitor) -> None:
        visitor.VisitPageStart(self)
        for child in self._children:
            child._accept(visitor)
        visitor.VisitPageEnd(self)


@dataclass
class Document(CompositeNode):
    """Aspose.Note-like Document.

    Can be constructed empty, from path, or from a binary stream.
    """

    DisplayName: str | None = None  # noqa: N815
    CreationTime: datetime | None = None  # noqa: N815

    _onenote_doc: Any | None = field(default=None, repr=False)

    def __init__(self, source: str | Path | BinaryIO | None = None, load_options: LoadOptions | None = None):
        super().__init__()
        self.DisplayName = None
        self.CreationTime = None
        self._onenote_doc = None

        if source is None:
            return

        # Load from file or stream using the existing parser.
        import onenote  # local import to avoid dependency at import time

        strict = False
        if load_options is not None and getattr(load_options, "DocumentPassword", None):
            # Password-protected docs are not implemented in this repository.
            # Keep surface compatible but fail explicitly.
            raise IncorrectPasswordException("Encrypted documents are not supported in this Python implementation")

        if isinstance(source, (str, Path)):
            o = onenote.Document.open(source, strict=strict)
        else:
            o = onenote.Document.from_stream(source, strict=strict)

        self._onenote_doc = o
        self.DisplayName = getattr(o, "display_name", None)

        for p in getattr(o, "pages", []):
            self.AppendChildLast(_convert_page(p))

    def Count(self) -> int:  # noqa: N802
        return len(self._children)

    def _accept(self, visitor: DocumentVisitor) -> None:
        visitor.VisitDocumentStart(self)
        for child in self._children:
            child._accept(visitor)
        visitor.VisitDocumentEnd(self)

    @property
    def FileFormat(self) -> FileFormat:  # noqa: N802
        # Best-effort; the underlying parser currently focuses on OneNote 2010/Online.
        return FileFormat.OneNote2010

    def DetectLayoutChanges(self) -> None:  # noqa: N802
        # Layout detection is not required for the current reader-only implementation.
        return None

    def GetPageHistory(self, page: Page) -> list[Page]:  # noqa: N802
        # History parsing exists internally for MS-ONE; public compatibility layer returns current only.
        return [page]

    def Save(self, target: str | Path | BinaryIO, format_or_options: Any = None) -> None:  # noqa: N802
        """Save document to a file/stream.

        Supported in this Python implementation:
        - `SaveFormat.Pdf` via the existing PDF exporter.

        Everything else raises UnsupportedSaveFormatException for now.
        """

        from .saving import PdfSaveOptions, SaveOptions

        fmt: SaveFormat | None
        opts: SaveOptions | None = None

        if isinstance(format_or_options, SaveFormat):
            fmt = format_or_options
        elif format_or_options is None:
            fmt = SaveFormat.One
        elif isinstance(format_or_options, SaveOptions):
            opts = format_or_options
            fmt = opts.SaveFormat
        else:
            raise UnsupportedSaveFormatException("Unsupported format/options argument")

        if fmt == SaveFormat.Pdf:
            if self._onenote_doc is None:
                raise UnsupportedSaveFormatException("Cannot export empty Document to PDF")

            # PdfSaveOptions is a compatibility stub; pass through a small subset of exporter options.
            if isinstance(opts, PdfSaveOptions):
                from onenote.pdf_export import PdfExportOptions

                pdf_opts = PdfExportOptions()
                if getattr(opts, "TagIconDir", None):
                    pdf_opts.tag_icon_dir = opts.TagIconDir
                if getattr(opts, "TagIconSize", None) is not None:
                    pdf_opts.tag_icon_size = float(opts.TagIconSize)
                if getattr(opts, "TagIconGap", None) is not None:
                    pdf_opts.tag_icon_gap = float(opts.TagIconGap)

                self._onenote_doc.export_pdf(target, options=pdf_opts)
            else:
                self._onenote_doc.export_pdf(target)
            return

        raise UnsupportedSaveFormatException(f"SaveFormat '{fmt.name}' is not supported in this Python implementation")


def _convert_page(p: Any) -> Page:
    # Convert from onenote.elements.Page
    title_text = getattr(p, "title", "") or ""
    title = Title()
    title_rich = RichText(Text=title_text)
    title.TitleText = title_rich
    title.AppendChildLast(title_rich)

    page = Page(
        Title=title,
        Author=getattr(p, "author", None),
        CreationTime=getattr(p, "created", None),
        LastModifiedTime=getattr(p, "modified", None),
        Level=getattr(p, "level", None),
    )

    # In Aspose.Note for .NET, Title is a real node in the Page subtree.
    # Keep it accessible both as a property and via traversal/GetChildNodes().
    page.AppendChildFirst(title)

    for child in getattr(p, "children", []) or []:
        converted = _convert_element(child)
        if converted is not None:
            page.AppendChildLast(converted)

    return page


def _convert_element(elem: Any) -> Node | None:
    # Convert from onenote.elements.* to Aspose-like node types.
    import onenote.elements as oe

    if isinstance(elem, oe.Outline):
        o = Outline()
        o.X = getattr(elem, "x", None)
        o.Y = getattr(elem, "y", None)
        o.Width = getattr(elem, "width", None)
        for ch in getattr(elem, "children", []) or []:
            ce = _convert_element(ch)
            if ce is not None:
                o.AppendChildLast(ce)
        return o

    if isinstance(elem, oe.OutlineElement):
        oe_node = OutlineElement()
        for content in getattr(elem, "contents", []) or []:
            ce = _convert_element(content)
            if ce is not None:
                oe_node.AppendChildLast(ce)
        for child in getattr(elem, "children", []) or []:
            ce = _convert_element(child)
            if ce is not None:
                oe_node.AppendChildLast(ce)
        oe_node.IndentLevel = int(getattr(elem, "indent_level", 0) or 0)

        list_format = getattr(elem, "list_format", None)
        list_restart = getattr(elem, "list_restart", None)
        is_numbered = bool(getattr(elem, "is_numbered", False))
        if list_format is not None or list_restart is not None or is_numbered:
            oe_node.NumberList = NumberList(Format=list_format, Restart=list_restart, IsNumbered=is_numbered)

        # tags
        tags: list[NoteTag] = []
        for t in getattr(elem, "tags", []) or []:
            tags.append(
                NoteTag(
                    shape=getattr(t, "shape", None),
                    label=getattr(t, "label", None),
                    text_color=getattr(t, "text_color", None),
                    highlight_color=getattr(t, "highlight_color", None),
                    created=getattr(t, "created", None),
                    completed=getattr(t, "completed", None),
                )
            )
        oe_node.Tags = tags
        return oe_node

    if isinstance(elem, oe.RichText):
        rt = RichText(
            Text=getattr(elem, "text", "") or "",
            FontSize=getattr(elem, "font_size_pt", None),
        )

        # tags
        rt_tags: list[NoteTag] = []
        for t in getattr(elem, "tags", []) or []:
            rt_tags.append(
                NoteTag(
                    shape=getattr(t, "shape", None),
                    label=getattr(t, "label", None),
                    text_color=getattr(t, "text_color", None),
                    highlight_color=getattr(t, "highlight_color", None),
                    created=getattr(t, "created", None),
                    completed=getattr(t, "completed", None),
                )
            )
        rt.Tags = rt_tags

        # runs/styles (preserve formatting extracted by the parser)
        full_text = rt.Text
        for run in getattr(elem, "runs", []) or []:
            start = int(getattr(run, "start", 0) or 0)
            end = int(getattr(run, "end", 0) or 0)
            seg = full_text[start:end] if 0 <= start <= end <= len(full_text) else ""

            s = getattr(run, "style", None)
            style = TextStyle(
                Bold=bool(getattr(s, "bold", False)) if s is not None else False,
                Italic=bool(getattr(s, "italic", False)) if s is not None else False,
                Underline=bool(getattr(s, "underline", False)) if s is not None else False,
                Strikethrough=bool(getattr(s, "strikethrough", False)) if s is not None else False,
                Superscript=bool(getattr(s, "superscript", False)) if s is not None else False,
                Subscript=bool(getattr(s, "subscript", False)) if s is not None else False,
                FontName=getattr(s, "font_name", None) if s is not None else None,
                FontSize=getattr(s, "font_size_pt", None) if s is not None else None,
                FontColor=getattr(s, "font_color", None) if s is not None else None,
                HighlightColor=getattr(s, "highlight_color", None) if s is not None else None,
                LanguageId=getattr(s, "language_id", None) if s is not None else None,
                HyperlinkAddress=getattr(s, "hyperlink", None) if s is not None else None,
                IsHyperlink=bool(getattr(s, "hyperlink", None)) if s is not None else False,
            )

            rt.Runs.append(TextRun(Text=seg, Style=style, Start=start, End=end))
        return rt

    if isinstance(elem, oe.Image):
        img = Image(
            FileName=getattr(elem, "filename", None),
            Bytes=bytes(getattr(elem, "data", b"") or b""),
            Width=getattr(elem, "width", None),
            Height=getattr(elem, "height", None),
            AlternativeTextDescription=getattr(elem, "alt_text", None),
            HyperlinkUrl=getattr(elem, "hyperlink", None),
        )
        # tags
        tags: list[NoteTag] = []
        for t in getattr(elem, "tags", []) or []:
            tags.append(
                NoteTag(
                    shape=getattr(t, "shape", None),
                    label=getattr(t, "label", None),
                    text_color=getattr(t, "text_color", None),
                    highlight_color=getattr(t, "highlight_color", None),
                    created=getattr(t, "created", None),
                    completed=getattr(t, "completed", None),
                )
            )
        img.Tags = tags
        return img

    if isinstance(elem, oe.AttachedFile):
        af = AttachedFile(
            FileName=getattr(elem, "filename", None),
            Bytes=bytes(getattr(elem, "data", b"") or b""),
        )
        tags: list[NoteTag] = []
        for t in getattr(elem, "tags", []) or []:
            tags.append(
                NoteTag(
                    shape=getattr(t, "shape", None),
                    label=getattr(t, "label", None),
                    text_color=getattr(t, "text_color", None),
                    highlight_color=getattr(t, "highlight_color", None),
                    created=getattr(t, "created", None),
                    completed=getattr(t, "completed", None),
                )
            )
        af.Tags = tags
        return af

    if isinstance(elem, oe.Table):
        table = Table()

        # Table metadata
        table.ColumnWidths = list(getattr(elem, "column_widths", []) or [])
        table.BordersVisible = bool(getattr(elem, "borders_visible", True))

        # tags
        tags: list[NoteTag] = []
        for t in getattr(elem, "tags", []) or []:
            tags.append(
                NoteTag(
                    shape=getattr(t, "shape", None),
                    label=getattr(t, "label", None),
                    text_color=getattr(t, "text_color", None),
                    highlight_color=getattr(t, "highlight_color", None),
                    created=getattr(t, "created", None),
                    completed=getattr(t, "completed", None),
                )
            )
        table.Tags = tags

        for row in getattr(elem, "rows", []) or []:
            r = TableRow()
            for cell in getattr(row, "cells", []) or []:
                c = TableCell()
                for cc in getattr(cell, "children", []) or []:
                    ce = _convert_element(cc)
                    if ce is not None:
                        c.AppendChildLast(ce)
                r.AppendChildLast(c)
            table.AppendChildLast(r)
        return table

    if isinstance(elem, oe.Title):
        # Title nodes usually belong to Page.Title; keep as RichText fallback.
        return None

    return None
