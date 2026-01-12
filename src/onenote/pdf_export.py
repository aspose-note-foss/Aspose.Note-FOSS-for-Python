"""PDF export functionality for OneNote documents.

This module provides PDF export using the ReportLab library.
Install with: pip install reportlab

Example usage::

    from onenote import Document
    
    doc = Document.open("notes.one")
    doc.export_pdf("output.pdf")
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO


def _number_to_alpha(n: int, *, upper: bool) -> str:
    if n <= 0:
        return ""
    chars: list[str] = []
    while n > 0:
        n -= 1
        chars.append(chr((n % 26) + (ord('A') if upper else ord('a'))))
        n //= 26
    return "".join(reversed(chars))


def _number_to_roman(n: int, *, upper: bool) -> str:
    if n <= 0:
        return ""
    # Best-effort; OneNote lists rarely exceed this.
    n = min(n, 3999)
    parts: list[str] = []
    mapping = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    for value, token in mapping:
        while n >= value:
            parts.append(token)
            n -= value
    s = "".join(parts)
    return s if upper else s.lower()


def _parse_ms_one_number_list_format(fmt: str | None) -> tuple[int | None, str, str]:
    """Parse MS-ONE NumberListFormat into (style_code, prefix, suffix).

    Observed formats often include control bytes (e.g. '\x03', '\x00') around
    the U+FFFD placeholder; ReportLab will render those as black squares.
    """
    if not fmt:
        return None, "", "."

    placeholder = "\uFFFD"
    idx = fmt.find(placeholder)
    if idx < 0:
        # Not a numbered format; return printable content only.
        printable = "".join(ch for ch in fmt if ord(ch) >= 32)
        return None, printable, ""

    prefix = "".join(ch for ch in fmt[:idx] if ord(ch) >= 32)

    style_code: int | None = None
    if idx + 1 < len(fmt) and ord(fmt[idx + 1]) < 32:
        style_code = ord(fmt[idx + 1])

    suffix = "".join(ch for ch in fmt[idx + 1 :] if ord(ch) >= 32 and ch != placeholder)
    if not suffix:
        suffix = "."

    return style_code, prefix, suffix


def _format_list_number(n: int, style_code: int | None) -> str:
    """Format list item number based on observed MS-ONE style codes."""
    # Observed in fixtures:
    # - 0x00: decimal
    # - 0x04: lower alpha
    # - 0x02: lower roman
    if style_code == 0x04:
        return _number_to_alpha(n, upper=False)
    if style_code == 0x03:
        return _number_to_alpha(n, upper=True)
    if style_code == 0x02:
        return _number_to_roman(n, upper=False)
    if style_code == 0x01:
        return _number_to_roman(n, upper=True)
    return str(n)


def _compute_list_marker(fmt: str | None, n: int) -> str:
    style_code, prefix, suffix = _parse_ms_one_number_list_format(fmt)
    return f"{prefix}{_format_list_number(n, style_code)}{suffix}".strip()


@dataclass
class _ListState:
    """Tracks list numbering across nested OutlineElements during PDF rendering."""

    counters: dict[int, int] = field(default_factory=dict)
    formats: dict[int, str] = field(default_factory=dict)

    def reset_from_level(self, indent_level: int) -> None:
        for level in list(self.counters.keys()):
            if level >= indent_level:
                self.counters.pop(level, None)
                self.formats.pop(level, None)

    def next_bullet(self, elem: "OutlineElement", indent_level: int) -> str | None:
        """Return bullet text for this element, or None if not a list item."""
        fmt = elem.list_format
        if not fmt:
            # Breaks the list chain at this indent level.
            self.reset_from_level(indent_level)
            return None

        # Bulleted lists: render a simple bullet.
        if not elem.is_numbered:
            # Reset deeper levels when continuing at this level.
            self.reset_from_level(indent_level + 1)
            return "•"

        # Numbered lists.
        # If format changes at this level, restart numbering.
        fmt_key = "".join(ch for ch in fmt if ord(ch) >= 32 or ch == "\uFFFD")
        if self.formats.get(indent_level) != fmt_key:
            self.counters[indent_level] = 0
            self.formats[indent_level] = fmt_key

        # Apply restart override if present.
        if elem.list_restart is not None:
            self.counters[indent_level] = elem.list_restart
        else:
            self.counters[indent_level] = self.counters.get(indent_level, 0) + 1

        # Reset deeper nested counters when we emit a marker at this level.
        self.reset_from_level(indent_level + 1)
        marker = _compute_list_marker(fmt, self.counters[indent_level])

        return marker

if TYPE_CHECKING:
    from .document import Document
    from .elements import (
        Page, Outline, OutlineElement, RichText, Image, 
        Table, TableRow, TableCell, AttachedFile, NoteTag, TextRun
    )

# Default page dimensions in points (Letter size)
DEFAULT_PAGE_WIDTH = 612.0  # 8.5 inches
DEFAULT_PAGE_HEIGHT = 792.0  # 11 inches
DEFAULT_MARGIN = 72.0  # 1 inch


# Map Windows font names to ReportLab core fonts
_FONT_MAP = {
    "times new roman": "Times-Roman",
    "times": "Times-Roman",
    "arial": "Helvetica",
    "helvetica": "Helvetica",
    "courier new": "Courier",
    "courier": "Courier",
    "verdana": "Helvetica",
    "georgia": "Times-Roman",
    "tahoma": "Helvetica",
    "trebuchet ms": "Helvetica",
    "comic sans ms": "Helvetica",
    "impact": "Helvetica-Bold",
    "calibri": "Helvetica",
    "cambria": "Times-Roman",
    "segoe ui": "Helvetica",
    "consolas": "Courier",
    "lucida console": "Courier",
}


@dataclass
class PdfExportOptions:
    """Options for PDF export."""
    
    page_width: float = DEFAULT_PAGE_WIDTH
    """Default page width in points if not specified in document."""
    
    page_height: float = DEFAULT_PAGE_HEIGHT
    """Default page height in points if not specified in document."""
    
    margin_left: float = DEFAULT_MARGIN
    """Left margin in points."""
    
    margin_right: float = DEFAULT_MARGIN
    """Right margin in points."""
    
    margin_top: float = DEFAULT_MARGIN
    """Top margin in points."""
    
    margin_bottom: float = DEFAULT_MARGIN
    """Bottom margin in points."""
    
    default_font_name: str = "Helvetica"
    """Default font family name."""
    
    default_font_size: float = 11.0
    """Default font size in points."""
    
    title_font_size: float = 18.0
    """Font size for page titles."""
    
    include_tags: bool = True
    """Whether to render note tags."""

    tag_icon_dir: str | Path | None = None
    """Optional directory with custom tag icon images (PNG).

    If provided, the exporter will try to load icons by:
    - shape id:   shape_<id>.png  (e.g. shape_13.png)
    - label text: label_<slug>.png (e.g. label_important.png)

    This enables using user-supplied icon sets (e.g. extracted from OneNote)
    without shipping Microsoft-owned icon assets in this repository.
    """

    tag_icon_size: float = 10.0
    """Rendered tag icon size in points."""

    tag_icon_gap: float = 2.0
    """Horizontal gap between tag icons in points."""
    
    include_images: bool = True
    """Whether to include images in export."""
    
    image_max_width: float | None = None
    """Maximum width for images (None = use available width)."""
    
    image_max_height: float | None = 400.0
    """Maximum height for images."""


class PdfExporter:
    """Export OneNote documents to PDF format.
    
    Uses ReportLab for PDF generation.
    """
    
    def __init__(self, options: PdfExportOptions | None = None):
        """Initialize exporter with options.
        
        Args:
            options: Export options. If None, uses defaults.
        """
        self.options = options or PdfExportOptions()
        self._check_reportlab()
        self._tag_icon_image_cache: dict[str, object] = {}
    
    def _check_reportlab(self) -> None:
        """Check if reportlab is available."""
        try:
            import reportlab
        except ImportError:
            raise ImportError(
                "ReportLab is required for PDF export. "
                "Install it with: pip install reportlab"
            )
    
    def export(self, document: "Document", output: str | Path | BinaryIO) -> None:
        """Export document to PDF.
        
        Args:
            document: OneNote document to export.
            output: Output path or file-like object.
        """
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
            Table as RLTable, TableStyle, PageBreak, ListFlowable, ListItem
        )
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
        
        # Prepare output
        if isinstance(output, (str, Path)):
            output_path = Path(output)
            output_file: BinaryIO = open(output_path, 'wb')
            should_close = True
        else:
            output_file = output
            should_close = False
        
        try:
            # Create document
            page_width = float(self.options.page_width)
            page_height = float(self.options.page_height)

            # If document provides page dimensions or layout coordinates exceed defaults,
            # auto-expand the PDF page size so content is not clipped.
            doc_page_width = 0.0
            doc_page_height = 0.0
            try:
                for p in getattr(document, "pages", []) or []:
                    w = getattr(p, "width", None)
                    h = getattr(p, "height", None)
                    if w is not None:
                        doc_page_width = max(doc_page_width, float(w))
                    if h is not None:
                        doc_page_height = max(doc_page_height, float(h))
            except Exception:
                pass

            required_width = 0.0
            required_height = 0.0
            try:
                for p in getattr(document, "pages", []) or []:
                    # Outline extents
                    for o in getattr(p, "iter_outlines", lambda: [])() or []:
                        ox = getattr(o, "x", None)
                        ow = getattr(o, "width", None)
                        oy = getattr(o, "y", None)
                        if ox is not None and ow is not None:
                            left = max(float(self.options.margin_left), float(ox))
                            required_width = max(required_width, left + float(ow) + float(self.options.margin_right))
                        if oy is not None:
                            required_height = max(required_height, max(float(self.options.margin_top), float(oy)) + float(self.options.margin_bottom))

                    # Image extents (height is known)
                    for img in getattr(p, "iter_images", lambda: [])() or []:
                        ix = getattr(img, "x", None)
                        iw = getattr(img, "width", None)
                        iy = getattr(img, "y", None)
                        ih = getattr(img, "height", None)
                        if ix is not None and iw is not None:
                            left = max(float(self.options.margin_left), float(ix))
                            required_width = max(required_width, left + float(iw) + float(self.options.margin_right))
                        if iy is not None and ih is not None:
                            top = max(float(self.options.margin_top), float(iy))
                            required_height = max(required_height, top + float(ih) + float(self.options.margin_bottom))
            except Exception:
                pass

            page_width = max(page_width, doc_page_width, required_width)
            page_height = max(page_height, doc_page_height, required_height)
            
            doc = SimpleDocTemplate(
                output_file,
                pagesize=(page_width, page_height),
                leftMargin=self.options.margin_left,
                rightMargin=self.options.margin_right,
                topMargin=self.options.margin_top,
                bottomMargin=self.options.margin_bottom,
            )
            
            # Build story (list of flowables)
            story = []
            styles = getSampleStyleSheet()
            
            # Create custom styles
            title_style = ParagraphStyle(
                'OneNoteTitle',
                parent=styles['Heading1'],
                fontSize=self.options.title_font_size,
                spaceAfter=12,
            )
            
            body_style = ParagraphStyle(
                'OneNoteBody',
                parent=styles['Normal'],
                fontSize=self.options.default_font_size,
                fontName=self.options.default_font_name,
                leading=float(self.options.default_font_size) * 1.2,
                autoLeading='max',
                spaceAfter=6,
            )
            
            # Process each page
            for i, page in enumerate(document.pages):
                if i > 0:
                    story.append(PageBreak())
                
                self._render_page(page, story, styles, title_style, body_style)
            
            # Build PDF
            doc.build(story)
            
        finally:
            if should_close:
                output_file.close()
    
    def _render_page(
        self, 
        page: "Page", 
        story: list, 
        styles, 
        title_style, 
        body_style
    ) -> None:
        """Render a page to PDF flowables."""
        from reportlab.platypus import Paragraph, Spacer
        from .elements import Outline
        
        # Page title
        if page.title:
            title_text = self._escape_html(page.title)
            story.append(Paragraph(title_text, title_style))
            story.append(Spacer(1, 12))
        
        # Process outlines and other content.
        # Prefer a visual order for outlines when coordinates exist.
        outlines: list[Outline] = []
        other: list = []
        for ch in page.children:
            if isinstance(ch, Outline):
                outlines.append(ch)
            else:
                other.append(ch)

        def _sort_key(o: Outline) -> tuple[float, float]:
            y = o.y if o.y is not None else 1e18
            x = o.x if o.x is not None else 1e18
            return (y, x)

        for child in sorted(outlines, key=_sort_key) + other:
            self._render_element(
                child,
                story,
                styles,
                body_style,
                indent_level=0,
                list_state=None,
                outline_x_offset=0.0,
                max_width=None,
            )
    
    def _render_element(
        self, 
        element, 
        story: list, 
        styles, 
        body_style,
        indent_level: int = 0,
        list_state: "_ListState | None" = None,
        outline_x_offset: float = 0.0,
        max_width: float | None = None,
    ) -> None:
        """Render any element to PDF flowables."""
        from .elements import Outline, OutlineElement, RichText, Image, Table, AttachedFile
        
        if isinstance(element, Outline):
            # element.x/width are page-layout coordinates. ReportLab indents are relative
            # to the frame (inside margins), so translate and clamp to avoid producing
            # near-zero usable line widths.
            x_page = float(element.x or 0.0)
            x_frame = max(0.0, x_page - float(self.options.margin_left or 0.0))

            effective_max_width = element.width
            if effective_max_width is not None:
                effective_max_width = float(effective_max_width)
                effective_max_width = min(effective_max_width, self._available_width() - x_frame)
                if effective_max_width <= 1.0:
                    effective_max_width = None

            self._render_outline(
                element,
                story,
                styles,
                body_style,
                outline_x_offset=x_frame,
                max_width=effective_max_width,
            )
        elif isinstance(element, OutlineElement):
            self._render_outline_element(
                element,
                story,
                styles,
                body_style,
                indent_level,
                list_state,
                outline_x_offset=outline_x_offset,
                max_width=max_width,
            )
        elif isinstance(element, RichText):
            # RichText at top level - render directly with paragraph style
            text = self._format_rich_text(element)
            if text.strip():
                from reportlab.platypus import Paragraph
                from reportlab.lib.styles import ParagraphStyle
                indent = 20 * indent_level
                base_left = max(0.0, float(outline_x_offset or 0.0))
                right_indent = 0.0
                if max_width is not None:
                    # ReportLab usable width = frameWidth - leftIndent - rightIndent.
                    # max_width is the outline width measured from its x offset, so the
                    # right indent must account for the left offset; otherwise the usable
                    # width becomes (max_width - base_left - ...), causing per-character wraps.
                    right_indent = max(0.0, self._available_width() - base_left - max_width)
                indented_style = ParagraphStyle(
                    f'Indented{indent_level}',
                    parent=body_style,
                    leftIndent=base_left + indent,
                    rightIndent=right_indent,
                )

                # Prevent line/item overlap when RichText uses large inline font sizes.
                max_fs = self._max_font_size_pt(element)
                indented_style.autoLeading = 'max'
                indented_style.leading = max(float(getattr(indented_style, 'leading', 0.0) or 0.0), max_fs * 1.2)
                rt_tags = self._dedupe_tags(list(getattr(element, "tags", None) or []))
                if self.options.include_tags and rt_tags:
                    marker_font = self.options.default_font_name
                    marker_size = float(self.options.default_font_size)
                    prefix_w = self._prefix_width(rt_tags, None, marker_font, marker_size)
                    style2 = ParagraphStyle(
                        f'TagPrefixedTop{indent_level}',
                        parent=indented_style,
                        leftIndent=base_left + indent + (prefix_w + 6.0),
                    )
                    para = Paragraph(text, style2)
                    story.append(
                        _prefixed_paragraph_flowable(
                            para,
                            prefix_x=base_left + indent,
                            tags=rt_tags,
                            marker=None,
                            marker_font=marker_font,
                            marker_size=marker_size,
                            icon_size=float(self.options.tag_icon_size),
                            icon_gap=float(self.options.tag_icon_gap),
                            draw_tag_icon=self._draw_tag_icon,
                        )
                    )
                else:
                    story.append(Paragraph(text, indented_style))
        elif isinstance(element, Image):
            self._render_image(element, story, styles, max_width=max_width)
        elif isinstance(element, Table):
            self._render_table(element, story, styles, body_style, max_width=max_width)
        elif isinstance(element, AttachedFile):
            self._render_attached_file(element, story, styles, body_style)
    
    def _render_outline(
        self, 
        outline: "Outline", 
        story: list, 
        styles, 
        body_style,
        *,
        outline_x_offset: float = 0.0,
        max_width: float | None = None,
    ) -> None:
        """Render an outline container."""
        from reportlab.platypus import Spacer

        list_state = _ListState()
        
        for child in outline.children:
            self._render_outline_element(
                child,
                story,
                styles,
                body_style,
                indent_level=0,
                list_state=list_state,
                outline_x_offset=outline_x_offset,
                max_width=max_width,
            )
        
        story.append(Spacer(1, 6))
    
    def _render_outline_element(
        self, 
        elem: "OutlineElement", 
        story: list, 
        styles, 
        body_style,
        indent_level: int = 0,
        list_state: "_ListState | None" = None,
        *,
        outline_x_offset: float = 0.0,
        max_width: float | None = None,
    ) -> None:
        """Render an outline element (paragraph-like container)."""
        from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
        from reportlab.lib.styles import ParagraphStyle
        
        # Calculate indentation
        indent = 20 * indent_level
        base_left = max(0.0, float(outline_x_offset or 0.0))
        
        # Determine list marker (and sanitize MS-ONE control bytes).
        bullet_text: str | None = None
        if list_state is not None:
            bullet_text = list_state.next_bullet(elem, indent_level)

        # Compute prefix width (tag icons + list marker), so wrapped lines align.
        # OneNote-like layout: tag icons should appear before the list marker.
        marker_font = self.options.default_font_name
        marker_size = float(self.options.default_font_size)
        prefix_tags: list["NoteTag"] = []
        if self.options.include_tags and bullet_text:
            try:
                if getattr(elem, "tags", None):
                    prefix_tags.extend(list(elem.tags))
                for rt in elem.iter_text():
                    if getattr(rt, "tags", None):
                        prefix_tags.extend(list(rt.tags))
                        break
            except Exception:
                pass
        prefix_tags = self._dedupe_tags(prefix_tags)
        bullet_gap = 0.0
        if bullet_text:
            bullet_gap = self._prefix_width(prefix_tags, bullet_text, marker_font, marker_size)
            if bullet_gap:
                bullet_gap += 6.0

        right_indent = 0.0
        if max_width is not None:
            # See comment in _render_element(RichText): max_width is measured from outline_x_offset.
            right_indent = max(0.0, self._available_width() - base_left - max_width)
        indented_style = ParagraphStyle(
            f'Indented{indent_level}',
            parent=body_style,
            leftIndent=base_left + indent + bullet_gap,
            rightIndent=right_indent,
        )
        indented_style.autoLeading = 'max'
        
        # Render contents
        bullet_used = False
        for content in elem.contents:
            if hasattr(content, '__class__'):
                from .elements import RichText, Image, Table
                
                if isinstance(content, RichText):
                    text = self._format_rich_text(content, prefix="")
                    if text.strip():
                        # Scale leading for this paragraph based on the largest inline font.
                        max_fs_rt = self._max_font_size_pt(content)
                        para_style = ParagraphStyle(
                            f'{indented_style.name}FS{int(max_fs_rt)}',
                            parent=indented_style,
                            leading=max(float(getattr(indented_style, 'leading', 0.0) or 0.0), max_fs_rt * 1.2),
                            autoLeading='max',
                        )
                        if not bullet_used and bullet_text:
                            para = Paragraph(text, para_style)
                            story.append(
                                _prefixed_paragraph_flowable(
                                    para,
                                    prefix_x=base_left + indent,
                                    tags=prefix_tags,
                                    marker=bullet_text,
                                    marker_font=marker_font,
                                    marker_size=marker_size,
                                    icon_size=float(self.options.tag_icon_size),
                                    icon_gap=float(self.options.tag_icon_gap),
                                    draw_tag_icon=self._draw_tag_icon,
                                )
                            )
                            bullet_used = True
                        else:
                            # Non-list paragraph: draw tags as an icon prefix before the text.
                            rt_tags = self._dedupe_tags(list(getattr(content, "tags", None) or []))
                            if self.options.include_tags and rt_tags and not bullet_text:
                                prefix_w2 = self._prefix_width(rt_tags, None, marker_font, marker_size)
                                style2 = ParagraphStyle(
                                    f'TagPrefixed{indent_level}',
                                    parent=para_style,
                                    leftIndent=base_left + indent + (prefix_w2 + 6.0),
                                )
                                para2 = Paragraph(text, style2)
                                story.append(
                                    _prefixed_paragraph_flowable(
                                        para2,
                                        prefix_x=base_left + indent,
                                        tags=rt_tags,
                                        marker=None,
                                        marker_font=marker_font,
                                        marker_size=marker_size,
                                        icon_size=float(self.options.tag_icon_size),
                                        icon_gap=float(self.options.tag_icon_gap),
                                        draw_tag_icon=self._draw_tag_icon,
                                    )
                                )
                            else:
                                story.append(Paragraph(text, para_style))
                elif isinstance(content, Image):
                    self._render_image(content, story, styles, max_width=max_width)
                elif isinstance(content, Table):
                    self._render_table(content, story, styles, body_style, max_width=max_width)
                else:
                    self._render_element(
                        content,
                        story,
                        styles,
                        body_style,
                        indent_level,
                        list_state=list_state,
                        outline_x_offset=outline_x_offset,
                        max_width=max_width,
                    )
        
        # Render nested children
        for child in elem.children:
            self._render_element(
                child,
                story,
                styles,
                body_style,
                indent_level + 1,
                list_state=list_state,
                outline_x_offset=outline_x_offset,
                max_width=max_width,
            )
    
    def _format_rich_text(self, rt: "RichText", prefix: str = "") -> str:
        """Format rich text with HTML tags for ReportLab."""
        if not rt.text:
            return prefix
        
        text = rt.text
        
        # If we have runs, apply formatting
        if rt.runs:
            formatted_parts = []
            last_end = 0
            
            for run in rt.runs:
                # Add any text before this run
                if run.start > last_end:
                    formatted_parts.append(self._escape_html(text[last_end:run.start]))
                
                # Format the run
                run_text = text[run.start:run.end]
                formatted_run = self._format_text_run(run_text, run.style)
                formatted_parts.append(formatted_run)
                
                last_end = run.end
            
            # Add any remaining text
            if last_end < len(text):
                formatted_parts.append(self._escape_html(text[last_end:]))
            
            text = "".join(formatted_parts)
        else:
            text = self._escape_html(text)
        
        return prefix + text
    
    def _format_text_run(self, text: str, style) -> str:
        """Format a text run with its style."""
        if not text:
            return ""
        
        result = self._escape_html(text)
        
        # Apply formatting
        if style.bold:
            result = f"<b>{result}</b>"
        if style.italic:
            result = f"<i>{result}</i>"
        if style.underline:
            result = f"<u>{result}</u>"
        if style.strikethrough:
            result = f"<strike>{result}</strike>"
        if style.superscript:
            result = f"<super>{result}</super>"
        if style.subscript:
            result = f"<sub>{result}</sub>"
        
        # Font styling
        font_attrs = []
        if style.font_name:
            # Map font name to ReportLab-compatible font
            mapped_font = self._map_font_name(style.font_name)
            font_attrs.append(f'face="{mapped_font}"')
        if style.font_size_pt:
            font_attrs.append(f'size="{int(style.font_size_pt)}"')
        if style.font_color:
            color = self._color_to_hex(style.font_color)
            if color:
                font_attrs.append(f'color="{color}"')
        
        if font_attrs:
            result = f'<font {" ".join(font_attrs)}>{result}</font>'
        
        # Hyperlink
        if style.hyperlink:
            result = f'<a href="{self._escape_html(style.hyperlink)}">{result}</a>'
        
        return result

    def _max_font_size_pt(self, rt: "RichText") -> float:
        """Return the maximum font size (pt) used by a RichText.

        ReportLab Paragraph does not automatically increase line leading when inline
        <font size="..."> is used, so we compute a per-paragraph leading.
        """
        max_size = float(self.options.default_font_size)
        try:
            runs = getattr(rt, "runs", None) or []
            for run in runs:
                st = getattr(run, "style", None)
                fs = getattr(st, "font_size_pt", None) if st is not None else None
                if fs:
                    max_size = max(max_size, float(fs))
        except Exception:
            pass
        return max_size
    
    def _dedupe_tags(self, tags: list["NoteTag"]) -> list["NoteTag"]:
        if not tags:
            return []
        seen: set[tuple[int | None, str | None]] = set()
        deduped: list["NoteTag"] = []
        for t in tags:
            key = (getattr(t, "shape", None), getattr(t, "label", None))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(t)
        return deduped

    def _slugify_label(self, s: str) -> str:
        s = (s or "").strip().lower()
        out: list[str] = []
        for ch in s:
            if ch.isalnum():
                out.append(ch)
            elif ch in {" ", "-", "_"}:
                out.append("_")
        slug = "".join(out)
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug.strip("_")

    def _resolve_tag_icon_path(self, tag: "NoteTag") -> Path | None:
        base = self.options.tag_icon_dir
        if not base:
            return None
        try:
            base_path = Path(base)
        except Exception:
            return None

        candidates: list[Path] = []
        shape = getattr(tag, "shape", None)
        if shape is not None:
            candidates.append(base_path / f"shape_{int(shape)}.png")
        if getattr(tag, "label", None):
            slug = self._slugify_label(tag.label or "")
            if slug:
                candidates.append(base_path / f"label_{slug}.png")

        for p in candidates:
            if p.exists() and p.is_file():
                return p
        return None

    def _get_tag_icon_image(self, tag: "NoteTag") -> object | None:
        """Return a cached ReportLab ImageReader for a tag icon path (PNG)."""
        p = self._resolve_tag_icon_path(tag)
        if p is None:
            return None
        key = str(p)
        cached = self._tag_icon_image_cache.get(key)
        if cached is not None:
            return cached
        try:
            from reportlab.lib.utils import ImageReader

            reader = ImageReader(str(p))
            self._tag_icon_image_cache[key] = reader
            return reader
        except Exception:
            return None

    def _tag_style_for_shape(self, shape: int | None) -> tuple[str, str]:
        """(kind, color_hex) for known tag shapes."""
        if shape == 13:
            return ("star", "#f39c12")
        if shape == 15:
            return ("question", "#8e44ad")
        if shape == 3:
            return ("todo", "#2980b9")
        if shape == 12:
            return ("calendar", "#16a085")
        if shape == 118:
            return ("contact", "#2980b9")
        if shape == 121:
            return ("music", "#7f8c8d")
        return ("unknown", "#7f8c8d")

    def _estimate_text_width(self, text: str, font_name: str, font_size: float) -> float:
        if not text:
            return 0.0
        try:
            from reportlab.pdfbase.pdfmetrics import stringWidth

            return float(stringWidth(text, font_name, font_size))
        except Exception:
            return float(len(text)) * float(font_size) * 0.55

    def _prefix_width(self, tags: list["NoteTag"], marker: str | None, font_name: str, font_size: float) -> float:
        icon_size = float(self.options.tag_icon_size)
        icon_gap = float(self.options.tag_icon_gap)
        tags = self._dedupe_tags(tags)
        icon_w = 0.0
        if tags:
            icon_w = len(tags) * icon_size + max(0, len(tags) - 1) * icon_gap
        marker_w = self._estimate_text_width(marker or "", font_name, font_size)
        gap = 4.0 if (tags and marker) else (3.0 if (tags or marker) else 0.0)
        return icon_w + gap + marker_w

    def _draw_tag_icon(self, canv, tag: "NoteTag", x: float, y: float, size: float) -> None:
        """Draw a tag icon at (x, y) with a size (points)."""
        img = self._get_tag_icon_image(tag)
        if img is not None:
            try:
                canv.drawImage(img, x, y, width=size, height=size, mask='auto', preserveAspectRatio=True)
                return
            except Exception:
                pass

        from reportlab.lib import colors

        kind, color_hex = self._tag_style_for_shape(getattr(tag, "shape", None))
        fill = colors.HexColor(color_hex)

        def draw_star() -> None:
            import math

            cx = x + size / 2
            cy = y + size / 2
            r_outer = size * 0.48
            r_inner = size * 0.22
            pts = []
            for i in range(10):
                a = math.pi / 2 + i * (math.pi / 5)
                r = r_outer if i % 2 == 0 else r_inner
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            p = canv.beginPath()
            p.moveTo(*pts[0])
            for px, py in pts[1:]:
                p.lineTo(px, py)
            p.close()
            canv.setFillColor(fill)
            canv.setStrokeColor(fill)
            canv.drawPath(p, stroke=1, fill=1)

        def draw_checkbox() -> None:
            canv.setStrokeColor(fill)
            canv.setFillColor(colors.white)
            canv.rect(x + 0.5, y + 0.5, size - 1.0, size - 1.0, stroke=1, fill=1)
            canv.setStrokeColor(fill)
            canv.setLineWidth(max(1.0, size * 0.12))
            canv.line(x + size * 0.22, y + size * 0.52, x + size * 0.42, y + size * 0.30)
            canv.line(x + size * 0.42, y + size * 0.30, x + size * 0.78, y + size * 0.72)

        def draw_calendar() -> None:
            canv.setStrokeColor(fill)
            canv.setFillColor(colors.white)
            canv.rect(x + 0.5, y + 0.5, size - 1.0, size - 1.0, stroke=1, fill=1)
            canv.setFillColor(fill)
            header_h = size * 0.26
            canv.rect(x + 0.5, y + size - header_h - 0.5, size - 1.0, header_h, stroke=0, fill=1)
            canv.setFillColor(colors.white)
            dot_r = max(0.8, size * 0.05)
            canv.circle(x + size * 0.28, y + size - header_h / 2, dot_r, stroke=0, fill=1)
            canv.circle(x + size * 0.72, y + size - header_h / 2, dot_r, stroke=0, fill=1)

        def draw_text_glyph(glyph: str) -> None:
            canv.setFillColor(fill)
            canv.setStrokeColor(fill)
            canv.setLineWidth(1)
            canv.circle(x + size / 2, y + size / 2, size * 0.48, stroke=1, fill=0)
            fsize = max(6.0, size * 0.78)
            canv.setFont("Helvetica-Bold", fsize)
            w = self._estimate_text_width(glyph, "Helvetica-Bold", fsize)
            canv.drawString(x + (size - w) / 2, y + size * 0.10, glyph)

        def draw_music() -> None:
            canv.setStrokeColor(fill)
            canv.setFillColor(fill)
            lw = max(1.0, size * 0.10)
            canv.setLineWidth(lw)
            canv.line(x + size * 0.62, y + size * 0.20, x + size * 0.62, y + size * 0.82)
            canv.line(x + size * 0.62, y + size * 0.82, x + size * 0.80, y + size * 0.76)
            canv.circle(x + size * 0.45, y + size * 0.24, size * 0.16, stroke=1, fill=1)

        if kind == "star":
            draw_star()
        elif kind == "todo":
            draw_checkbox()
        elif kind == "calendar":
            draw_calendar()
        elif kind == "question":
            draw_text_glyph("?")
        elif kind == "contact":
            draw_text_glyph("@")
        elif kind == "music":
            draw_music()
        else:
            canv.setStrokeColor(fill)
            canv.setFillColor(colors.white)
            canv.rect(x + 0.5, y + 0.5, size - 1.0, size - 1.0, stroke=1, fill=1)
    
    def _render_image(self, img: "Image", story: list, styles, *, max_width: float | None = None) -> None:
        """Render an image to PDF."""
        from reportlab.platypus import Paragraph, Spacer
        
        if not self.options.include_images:
            return
        
        effective_max_width = self._available_width()
        if max_width is not None:
            effective_max_width = min(effective_max_width, max_width)
        rl_img = self._build_rl_image(img, styles, max_width=effective_max_width, max_height=self.options.image_max_height)
        if rl_img is None:
            return

        if self.options.include_tags and getattr(img, "tags", None):
            tags = self._dedupe_tags(list(img.tags))
            if tags:
                story.append(
                    _icon_only_flowable(
                        tags=tags,
                        height=float(self.options.tag_icon_size) + 2.0,
                        prefix_x=0.0,
                        icon_size=float(self.options.tag_icon_size),
                        icon_gap=float(self.options.tag_icon_gap),
                        draw_tag_icon=self._draw_tag_icon,
                    )
                )
        story.append(rl_img)
        story.append(Spacer(1, 6))

    def _available_width(self) -> float:
        return self.options.page_width - self.options.margin_left - self.options.margin_right

    def _build_rl_image(self, img: "Image", styles, max_width: float | None, max_height: float | None):
        """Build a ReportLab Image flowable (or a placeholder Paragraph).

        Returns None when images are disabled.
        """
        if not self.options.include_images:
            return None

        from reportlab.platypus import Paragraph

        if not img.data:
            if img.filename:
                return Paragraph(f"[Image: {self._escape_html(img.filename)}]", styles['Normal'])
            return Paragraph("[Image]", styles['Normal'])

        try:
            from reportlab.platypus import Image as RLImage
            import io

            img_buffer = io.BytesIO(img.data)

            width = img.width
            height = img.height

            effective_max_width = max_width
            if effective_max_width is None:
                effective_max_width = self.options.image_max_width or self._available_width()

            effective_max_height = max_height
            if effective_max_height is None:
                effective_max_height = self.options.image_max_height

            if width and height:
                if effective_max_width and width > effective_max_width:
                    scale = effective_max_width / width
                    width = effective_max_width
                    height = height * scale
                if effective_max_height and height > effective_max_height:
                    scale = effective_max_height / height
                    height = effective_max_height
                    width = width * scale
            else:
                width = None
                height = None

            return RLImage(img_buffer, width=width, height=height)
        except Exception:
            return Paragraph(f"[Image: {img.filename or 'unnamed'}]", styles['Normal'])
    
    def _render_table(
        self, 
        table: "Table", 
        story: list, 
        styles, 
        body_style,
        *,
        max_width: float | None = None,
    ) -> None:
        """Render a table to PDF."""
        from reportlab.platypus import Table as RLTable, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        
        if not table.rows:
            return
        
        # Calculate column widths
        col_widths = None
        if table.column_widths:
            valid_widths = [w for w in table.column_widths if w and w > 1.0]
            if valid_widths and len(valid_widths) == len(table.column_widths):
                col_widths = valid_widths

        available_width = self._available_width()
        if max_width is not None:
            available_width = min(available_width, max_width)
        approx_col_width = None
        if table.column_count:
            approx_col_width = available_width / table.column_count

        # Build table data
        table_data = []
        for row in table.rows:
            row_data = []
            for col_index, cell in enumerate(row.cells):
                cell_width = None
                if col_widths and col_index < len(col_widths):
                    cell_width = col_widths[col_index]
                elif approx_col_width:
                    cell_width = approx_col_width

                # Account for left/right padding (see TableStyle below)
                if cell_width:
                    cell_width = max(cell_width - 8.0, 20.0)

                cell_content = self._get_cell_content(cell, body_style, styles, max_width=cell_width)
                row_data.append(cell_content)
            table_data.append(row_data)

        if not table_data:
            return
        
        # Create table
        rl_table = RLTable(table_data, colWidths=col_widths)
        
        # Apply style
        style_commands = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, -1), self.options.default_font_name),
            ('FONTSIZE', (0, 0), (-1, -1), self.options.default_font_size),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]
        
        if table.borders_visible:
            style_commands.extend([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ])
        
        rl_table.setStyle(TableStyle(style_commands))
        
        # Render table tags (icons) if present
        if self.options.include_tags and table.tags:
            tags = self._dedupe_tags(list(table.tags))
            if tags:
                story.append(
                    _icon_only_flowable(
                        tags=tags,
                        height=float(self.options.tag_icon_size) + 2.0,
                        prefix_x=0.0,
                        icon_size=float(self.options.tag_icon_size),
                        icon_gap=float(self.options.tag_icon_gap),
                        draw_tag_icon=self._draw_tag_icon,
                    )
                )
        
        story.append(rl_table)
        story.append(Spacer(1, 12))
    
    def _get_cell_content(self, cell: "TableCell", body_style, styles, max_width: float | None):
        """Build ReportLab cell content from a table cell.

        Returns a Flowable, a list-wrapped Flowable, or an empty string.
        """
        from reportlab.platypus import Paragraph, KeepInFrame
        from .elements import OutlineElement, RichText, Image, Table, AttachedFile

        flowables = []

        def add_element(elem) -> None:
            if isinstance(elem, RichText):
                text = self._format_rich_text(elem)
                if text.strip():
                    rt_tags = self._dedupe_tags(list(getattr(elem, "tags", None) or []))
                    if self.options.include_tags and rt_tags:
                        from reportlab.lib.styles import ParagraphStyle

                        marker_font = self.options.default_font_name
                        marker_size = float(self.options.default_font_size)
                        prefix_w = self._prefix_width(rt_tags, None, marker_font, marker_size)
                        style2 = ParagraphStyle(
                            'CellTagPrefixed',
                            parent=body_style,
                            leftIndent=(prefix_w + 6.0),
                        )
                        para = Paragraph(text, style2)
                        flowables.append(
                            _prefixed_paragraph_flowable(
                                para,
                                prefix_x=0.0,
                                tags=rt_tags,
                                marker=None,
                                marker_font=marker_font,
                                marker_size=marker_size,
                                icon_size=float(self.options.tag_icon_size),
                                icon_gap=float(self.options.tag_icon_gap),
                                draw_tag_icon=self._draw_tag_icon,
                            )
                        )
                    else:
                        flowables.append(Paragraph(text, body_style))
            elif isinstance(elem, Image):
                img_flow = self._build_rl_image(elem, styles, max_width=max_width, max_height=self.options.image_max_height)
                if img_flow is not None:
                    flowables.append(img_flow)
            elif isinstance(elem, Table):
                # Nested tables are rare; render as plain text placeholder for now.
                flowables.append(Paragraph("[Table]", body_style))
            elif isinstance(elem, AttachedFile):
                filename = elem.filename or "unknown"
                flowables.append(Paragraph(f"[Attachment: {self._escape_html(filename)}]", body_style))
            elif isinstance(elem, OutlineElement):
                # Preserve the typical OutlineElement order: tags/text/images in contents, then nested children.
                for content in elem.contents:
                    add_element(content)
                for child in elem.children:
                    add_element(child)

        for child in cell.children:
            add_element(child)

        if not flowables:
            return ""
        if len(flowables) == 1:
            return flowables[0]

        frame_width = max_width or 9999.0
        return KeepInFrame(frame_width, 9999.0, flowables, mode='shrink')
    
    def _render_attached_file(
        self, 
        attachment: "AttachedFile", 
        story: list, 
        styles, 
        body_style
    ) -> None:
        """Render an attached file reference."""
        from reportlab.platypus import Paragraph, Spacer
        
        if self.options.include_tags and getattr(attachment, "tags", None):
            tags = self._dedupe_tags(list(attachment.tags))
            if tags:
                story.append(
                    _icon_only_flowable(
                        tags=tags,
                        height=float(self.options.tag_icon_size) + 2.0,
                        prefix_x=0.0,
                        icon_size=float(self.options.tag_icon_size),
                        icon_gap=float(self.options.tag_icon_gap),
                        draw_tag_icon=self._draw_tag_icon,
                    )
                )

        filename = attachment.filename or "unknown"
        size_kb = attachment.size / 1024 if attachment.size else 0
        
        text = f"📎 <b>Attachment:</b> {self._escape_html(filename)} ({size_kb:.1f} KB)"
        story.append(Paragraph(text, body_style))
        story.append(Spacer(1, 6))
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
    
    def _map_font_name(self, font_name: str) -> str:
        """Map Windows font name to ReportLab-compatible font."""
        if not font_name:
            return self.options.default_font_name
        
        lower_name = font_name.lower().strip()
        
        # Check direct mapping
        if lower_name in _FONT_MAP:
            return _FONT_MAP[lower_name]
        
        # If already a core font, return as-is
        core_fonts = {"times-roman", "helvetica", "courier", "symbol", "zapfdingbats"}
        if lower_name in core_fonts:
            return font_name
        
        # Fallback to default
        return self.options.default_font_name
    
    def _color_to_hex(self, color: int | None) -> str | None:
        """Convert COLORREF to hex string."""
        if color is None:
            return None
        
        # COLORREF format: 0x00BBGGRR
        r = color & 0xFF
        g = (color >> 8) & 0xFF
        b = (color >> 16) & 0xFF
        
        return f"#{r:02x}{g:02x}{b:02x}"


def export_pdf(
    document: "Document", 
    output: str | Path | BinaryIO,
    options: PdfExportOptions | None = None
) -> None:
    """Export a OneNote document to PDF.
    
    This is a convenience function. For more control, use PdfExporter directly.
    
    Args:
        document: OneNote document to export.
        output: Output file path or file-like object.
        options: Export options.
        
    Example::
    
        from onenote import Document
        from onenote.pdf_export import export_pdf
        
        doc = Document.open("notes.one")
        export_pdf(doc, "output.pdf")
    """
    exporter = PdfExporter(options)
    exporter.export(document, output)


def _prefixed_paragraph_flowable(
    paragraph,
    *,
    prefix_x: float,
    tags: list["NoteTag"],
    marker: str | None,
    marker_font: str,
    marker_size: float,
    icon_size: float,
    icon_gap: float,
    draw_tag_icon,
):
    """Factory: returns a real ReportLab Flowable that draws prefix + Paragraph."""
    from reportlab.platypus import Flowable
    from reportlab.lib import colors

    class _Impl(Flowable):
        def __init__(self) -> None:
            super().__init__()
            self.paragraph = paragraph
            self.prefix_x = float(prefix_x)
            self.tags = list(tags)
            self.marker = marker
            self.marker_font = marker_font
            self.marker_size = float(marker_size)
            self.icon_size = float(icon_size)
            self.icon_gap = float(icon_gap)
            self.draw_tag_icon = draw_tag_icon
            self._w = 0.0
            self._h = 0.0

        def getSpaceBefore(self):
            return self.paragraph.getSpaceBefore()

        def getSpaceAfter(self):
            return self.paragraph.getSpaceAfter()

        def split(self, aW, aH):
            parts = self.paragraph.split(aW, aH)
            if not parts:
                return []
            out = []
            for i, p in enumerate(parts):
                out.append(
                    _prefixed_paragraph_flowable(
                        p,
                        prefix_x=self.prefix_x,
                        tags=(self.tags if i == 0 else []),
                        marker=(self.marker if i == 0 else None),
                        marker_font=self.marker_font,
                        marker_size=self.marker_size,
                        icon_size=self.icon_size,
                        icon_gap=self.icon_gap,
                        draw_tag_icon=self.draw_tag_icon,
                    )
                )
            return out

        def wrap(self, aW, aH):
            w, h = self.paragraph.wrap(aW, aH)
            self._w, self._h = w, h
            return w, h

        def draw(self):
            canv = self.canv
            # ReportLab Paragraph draws text starting near the *top* of its box.
            # In the PDF stream this often manifests as a negative Tm Y (e.g. -13)
            # when fontSize > leading. To align our marker/icons with the paragraph's
            # first line, compute baseline from the wrapped height.
            style = self.paragraph.style
            line_font_size = None
            frag_font_size = None
            try:
                bl_para = getattr(self.paragraph, "blPara", None)
                if bl_para is not None:
                    lines = getattr(bl_para, "lines", None)
                    if lines:
                        line_font_size = getattr(lines[0], "fontSize", None)
                frags = getattr(self.paragraph, "frags", None)
                if frags:
                    frag_font_size = getattr(frags[0], "fontSize", None)
            except Exception:
                line_font_size = None
                frag_font_size = None

            font_size = float(
                line_font_size
                or frag_font_size
                or getattr(style, "fontSize", None)
                or self.marker_size
            )
            leading = float(getattr(style, "leading", None) or (font_size * 1.2))
            baseline_y = leading - font_size

            # Center icons on the first line box using font ascent/descent if possible.
            try:
                from reportlab.pdfbase import pdfmetrics

                font_name = str(getattr(style, "fontName", "Helvetica") or "Helvetica")
                ascent = (pdfmetrics.getAscent(font_name) / 1000.0) * font_size
                descent = (pdfmetrics.getDescent(font_name) / 1000.0) * font_size
            except Exception:
                ascent = 0.7 * font_size
                descent = -0.2 * font_size

            line_top = baseline_y + ascent
            line_bottom = baseline_y + descent
            icon_y = line_bottom + ((line_top - line_bottom) - self.icon_size) / 2.0

            cur_x = float(self.prefix_x)
            for t in self.tags:
                self.draw_tag_icon(canv, t, cur_x, icon_y, self.icon_size)
                cur_x += self.icon_size + self.icon_gap

            if self.marker:
                if self.tags:
                    cur_x += 4.0
                canv.setFillColor(colors.black)
                try:
                    canv.setFont(self.marker_font, self.marker_size)
                except Exception:
                    canv.setFont("Helvetica", self.marker_size)
                canv.drawString(cur_x, baseline_y, self.marker)

            self.paragraph.drawOn(canv, 0, 0)

    return _Impl()


def _icon_only_flowable(
    *,
    tags: list["NoteTag"],
    height: float,
    prefix_x: float,
    icon_size: float,
    icon_gap: float,
    draw_tag_icon,
):
    from reportlab.platypus import Flowable

    class _Impl(Flowable):
        def __init__(self) -> None:
            super().__init__()
            self.tags = list(tags)
            self.height = float(height)
            self.prefix_x = float(prefix_x)
            self.icon_size = float(icon_size)
            self.icon_gap = float(icon_gap)
            self.draw_tag_icon = draw_tag_icon

        def wrap(self, aW, aH):
            return (aW, self.height)

        def draw(self):
            canv = self.canv
            icon_y = (self.height - self.icon_size) / 2
            cur_x = float(self.prefix_x)
            for t in self.tags:
                self.draw_tag_icon(canv, t, cur_x, icon_y, self.icon_size)
                cur_x += self.icon_size + self.icon_gap

    return _Impl()
