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

        # Include tag icons (plain) before the list marker, matching OneNote's layout.
        # Prefer rich-text tags when present on the first paragraph.
        tags: list["NoteTag"] = []
        if getattr(elem, "tags", None):
            tags.extend(list(elem.tags))
        try:
            for rt in elem.iter_text():
                if getattr(rt, "tags", None):
                    tags.extend(list(rt.tags))
                    break
        except Exception:
            pass

        # De-duplicate by (shape, label)
        seen: set[tuple[int | None, str | None]] = set()
        deduped: list["NoteTag"] = []
        for t in tags:
            key = (getattr(t, "shape", None), getattr(t, "label", None))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(t)

        tag_prefix = ""
        if deduped:
            # ASCII only.
            shape_map: dict[int, str] = {
                13: "*",
                15: "?",
                3: "[]",
                12: "cal",
                118: "@",
                121: "music",
            }
            icons: list[str] = []
            for t in deduped:
                if t.shape is not None and t.shape in shape_map:
                    icons.append(shape_map[t.shape])
            if icons:
                tag_prefix = " ".join(icons)

        return f"{tag_prefix} {marker}".strip()

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
            page_width = self.options.page_width
            page_height = self.options.page_height
            
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
        
        # Page title
        if page.title:
            title_text = self._escape_html(page.title)
            story.append(Paragraph(title_text, title_style))
            story.append(Spacer(1, 12))
        
        # Process outlines and other content
        for child in page.children:
            self._render_element(child, story, styles, body_style, indent_level=0, list_state=None)
    
    def _render_element(
        self, 
        element, 
        story: list, 
        styles, 
        body_style,
        indent_level: int = 0,
        list_state: "_ListState | None" = None,
    ) -> None:
        """Render any element to PDF flowables."""
        from .elements import Outline, OutlineElement, RichText, Image, Table, AttachedFile
        
        if isinstance(element, Outline):
            self._render_outline(element, story, styles, body_style)
        elif isinstance(element, OutlineElement):
            self._render_outline_element(element, story, styles, body_style, indent_level, list_state)
        elif isinstance(element, RichText):
            # RichText at top level - render directly with paragraph style
            text = self._format_rich_text(element)
            if text.strip():
                from reportlab.platypus import Paragraph
                from reportlab.lib.styles import ParagraphStyle
                indent = 20 * indent_level
                indented_style = ParagraphStyle(
                    f'Indented{indent_level}',
                    parent=body_style,
                    leftIndent=indent,
                )
                story.append(Paragraph(text, indented_style))
        elif isinstance(element, Image):
            self._render_image(element, story, styles)
        elif isinstance(element, Table):
            self._render_table(element, story, styles, body_style)
        elif isinstance(element, AttachedFile):
            self._render_attached_file(element, story, styles, body_style)
    
    def _render_outline(
        self, 
        outline: "Outline", 
        story: list, 
        styles, 
        body_style
    ) -> None:
        """Render an outline container."""
        from reportlab.platypus import Spacer

        list_state = _ListState()
        
        for child in outline.children:
            self._render_outline_element(child, story, styles, body_style, indent_level=0, list_state=list_state)
        
        story.append(Spacer(1, 6))
    
    def _render_outline_element(
        self, 
        elem: "OutlineElement", 
        story: list, 
        styles, 
        body_style,
        indent_level: int = 0,
        list_state: "_ListState | None" = None,
    ) -> None:
        """Render an outline element (paragraph-like container)."""
        from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
        from reportlab.lib.styles import ParagraphStyle
        
        # Calculate indentation
        indent = 20 * indent_level
        
        # Determine list marker (and sanitize MS-ONE control bytes).
        bullet_text: str | None = None
        if list_state is not None:
            bullet_text = list_state.next_bullet(elem, indent_level)

        # Styles: use a dedicated bullet indent so multi-line items align.
        # Reserve enough space for markers like "* ? 12." or "* [] ? @ music cal a.".
        # ReportLab core fonts don't provide precise glyph metrics here, so use a simple heuristic.
        bullet_gap = 0
        if bullet_text:
            bullet_gap = max(18, min(80, 6 + (len(bullet_text) * 4)))
        indented_style = ParagraphStyle(
            f'Indented{indent_level}',
            parent=body_style,
            leftIndent=indent + bullet_gap,
            bulletIndent=indent,
        )
        
        # Render contents
        bullet_used = False
        tags_rendered_in_bullet = bool(bullet_text and self.options.include_tags)
        for content in elem.contents:
            if hasattr(content, '__class__'):
                from .elements import RichText, Image, Table
                
                if isinstance(content, RichText):
                    text = self._format_rich_text(
                        content,
                        prefix="",
                        include_tag_prefix=(self.options.include_tags and not tags_rendered_in_bullet and not bullet_used),
                    )
                    if text.strip():
                        if not bullet_used and bullet_text:
                            story.append(Paragraph(text, indented_style, bulletText=bullet_text))
                            bullet_used = True
                        else:
                            story.append(Paragraph(text, indented_style))
                elif isinstance(content, Image):
                    self._render_image(content, story, styles)
                elif isinstance(content, Table):
                    self._render_table(content, story, styles, body_style)
                else:
                    self._render_element(content, story, styles, body_style, indent_level, list_state=list_state)
        
        # Render nested children
        for child in elem.children:
            self._render_element(child, story, styles, body_style, indent_level + 1, list_state=list_state)
    
    def _format_rich_text(self, rt: "RichText", prefix: str = "", *, include_tag_prefix: bool = True) -> str:
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
        
        # Handle tags on the rich text
        if include_tag_prefix and self.options.include_tags and rt.tags:
            tag_prefix = self._format_tags(rt.tags, rich=True)
            if tag_prefix:
                text = tag_prefix + " " + text
        
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
    
    def _format_tags(self, tags: list["NoteTag"], *, rich: bool) -> str:
        """Format note tags as icon-like prefixes.

        ReportLab core fonts are not fully Unicode-capable, so we prefer ASCII
        markers that render consistently in PDF viewers.
        """
        if not tags:
            return ""

        # Common MS-ONE tag shapes observed in fixtures.
        # Keep to ASCII so it works with ReportLab core fonts.
        shape_map: dict[int, tuple[str, str]] = {
            13: ("*", "#f39c12"),  # Important
            15: ("?", "#8e44ad"),  # Question
            3: ("[]", "#2980b9"),  # To-do
            12: ("cal", "#16a085"),  # Meeting
            118: ("@", "#2980b9"),  # Contact
            121: ("music", "#7f8c8d"),  # Music
        }

        parts: list[str] = []
        for tag in tags:
            icon = None
            color = None
            if tag.shape is not None and tag.shape in shape_map:
                icon, color = shape_map[tag.shape]
            if icon is None:
                # Fallback: show label (if any), otherwise the raw shape id.
                if tag.label:
                    icon = f"[{self._escape_html(tag.label)}]" if rich else f"[{tag.label}]"
                elif tag.shape is not None:
                    icon = f"[Tag:{tag.shape}]"
                else:
                    continue

            if rich and color and not icon.startswith("["):
                parts.append(f'<font color="{color}"><b>{self._escape_html(icon)}</b></font>')
            else:
                parts.append(icon)

        return " ".join(parts)
    
    def _render_image(self, img: "Image", story: list, styles) -> None:
        """Render an image to PDF."""
        from reportlab.platypus import Paragraph, Spacer
        
        if not self.options.include_images:
            return
        
        rl_img = self._build_rl_image(img, styles, max_width=self._available_width(), max_height=self.options.image_max_height)
        if rl_img is None:
            return
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
        body_style
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
        
        # Render table tags if present
        if self.options.include_tags and table.tags:
            tag_text = self._format_tags(table.tags, rich=True)
            if tag_text:
                story.append(Paragraph(tag_text, body_style))
        
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
