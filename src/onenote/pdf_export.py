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
            self._render_element(child, story, styles, body_style, indent_level=0)
    
    def _render_element(
        self, 
        element, 
        story: list, 
        styles, 
        body_style,
        indent_level: int = 0
    ) -> None:
        """Render any element to PDF flowables."""
        from .elements import Outline, OutlineElement, RichText, Image, Table, AttachedFile
        
        if isinstance(element, Outline):
            self._render_outline(element, story, styles, body_style)
        elif isinstance(element, OutlineElement):
            self._render_outline_element(element, story, styles, body_style, indent_level)
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
        
        for child in outline.children:
            self._render_outline_element(child, story, styles, body_style, indent_level=0)
        
        story.append(Spacer(1, 6))
    
    def _render_outline_element(
        self, 
        elem: "OutlineElement", 
        story: list, 
        styles, 
        body_style,
        indent_level: int = 0
    ) -> None:
        """Render an outline element (paragraph-like container)."""
        from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
        from reportlab.lib.styles import ParagraphStyle
        
        # Calculate indentation
        indent = 20 * indent_level
        
        # Create indented style
        indented_style = ParagraphStyle(
            f'Indented{indent_level}',
            parent=body_style,
            leftIndent=indent,
        )
        
        # Handle numbered/bulleted lists
        list_prefix = ""
        if elem.is_numbered and elem.list_format:
            # Replace the placeholder with a number indicator
            list_prefix = elem.list_format.replace('\ufffd', '#') + " "
        elif elem.list_format:
            # Bullet list
            list_prefix = "• "
        
        # Render tags if present
        if self.options.include_tags and elem.tags:
            tag_text = self._format_tags(elem.tags)
            if tag_text:
                story.append(Paragraph(tag_text, indented_style))
        
        # Render contents
        for content in elem.contents:
            if hasattr(content, '__class__'):
                from .elements import RichText, Image, Table
                
                if isinstance(content, RichText):
                    text = self._format_rich_text(content, list_prefix)
                    if text.strip():
                        story.append(Paragraph(text, indented_style))
                elif isinstance(content, Image):
                    self._render_image(content, story, styles)
                elif isinstance(content, Table):
                    self._render_table(content, story, styles, body_style)
                else:
                    self._render_element(content, story, styles, body_style, indent_level)
        
        # Render nested children
        for child in elem.children:
            self._render_element(child, story, styles, body_style, indent_level + 1)
    
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
        
        # Handle tags on the rich text
        if self.options.include_tags and rt.tags:
            tag_prefix = self._format_tags(rt.tags)
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
    
    def _format_tags(self, tags: list["NoteTag"]) -> str:
        """Format note tags as text."""
        if not tags:
            return ""
        
        tag_parts = []
        for tag in tags:
            if tag.label:
                # Show label
                tag_parts.append(f"[{self._escape_html(tag.label)}]")
            elif tag.shape is not None:
                # Show shape indicator
                tag_parts.append(f"[Tag:{tag.shape}]")
        
        return " ".join(tag_parts)
    
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
            tag_text = self._format_tags(table.tags)
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
