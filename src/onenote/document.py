"""OneNote Document class - main entry point for the public API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, BinaryIO, TYPE_CHECKING

from .elements import Page, Element

if TYPE_CHECKING:
    from .pdf_export import PdfExportOptions


@dataclass
class Document:
    """A OneNote section document (.one file).

    This is the main entry point for reading OneNote documents.

    Example usage::

        from onenote import Document

        # Open a document
        doc = Document.open("notebook.one")

        # Access pages
        for page in doc.pages:
            print(page.title)
            for outline in page.iter_outlines():
                print(outline.text)

        # Get specific page
        page = doc.pages[0]
        print(page.text)
    """

    pages: list[Page] = field(default_factory=list)
    """All pages in this document/section."""

    display_name: str | None = None
    """Display name of the section (if available)."""

    _source_path: Path | None = field(default=None, repr=False)
    """Original file path (for reference)."""

    @classmethod
    def open(cls, path: str | Path, *, strict: bool = False) -> "Document":
        """Open and parse a OneNote section file (.one).

        Args:
            path: Path to the .one file.
            strict: If True, raise errors on format violations.
                   If False (default), try to recover from minor issues.

        Returns:
            Parsed Document instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file cannot be parsed.

        Example::

            doc = Document.open("MyNotes.one")
            for page in doc.pages:
                print(page.title)
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")

        data = p.read_bytes()
        doc = cls.from_bytes(data, strict=strict)
        doc._source_path = p
        return doc

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, strict: bool = False) -> "Document":
        """Parse a OneNote document from raw bytes.

        Args:
            data: Raw bytes of a .one file.
            strict: If True, raise errors on format violations.

        Returns:
            Parsed Document instance.
        """
        from .parser import parse_document
        return parse_document(data, strict=strict)

    @classmethod
    def from_stream(cls, stream: BinaryIO, *, strict: bool = False) -> "Document":
        """Parse a OneNote document from a binary stream.

        Args:
            stream: Binary stream containing .one file data.
            strict: If True, raise errors on format violations.

        Returns:
            Parsed Document instance.
        """
        data = stream.read()
        return cls.from_bytes(data, strict=strict)

    def __len__(self) -> int:
        """Number of pages in the document."""
        return len(self.pages)

    def __getitem__(self, index: int) -> Page:
        """Get page by index."""
        return self.pages[index]

    def __iter__(self) -> Iterator[Page]:
        """Iterate over pages."""
        return iter(self.pages)

    def iter_pages(self) -> Iterator[Page]:
        """Iterate over all pages in the document."""
        return iter(self.pages)

    def get_page(self, index: int) -> Page | None:
        """Get page by index, or None if out of range."""
        if 0 <= index < len(self.pages):
            return self.pages[index]
        return None

    def find_pages(self, title: str, *, case_sensitive: bool = False) -> list[Page]:
        """Find pages by title (partial match).

        Args:
            title: Text to search for in page titles.
            case_sensitive: Whether search is case-sensitive.

        Returns:
            List of matching pages.
        """
        results: list[Page] = []
        search = title if case_sensitive else title.lower()
        for page in self.pages:
            page_title = page.title if case_sensitive else page.title.lower()
            if search in page_title:
                results.append(page)
        return results

    @property
    def page_count(self) -> int:
        """Number of pages in the document."""
        return len(self.pages)

    @property
    def source_path(self) -> Path | None:
        """Original file path if opened from file."""
        return self._source_path

    def export_pdf(
        self, 
        output: str | Path | BinaryIO,
        *,
        options: "PdfExportOptions | None" = None
    ) -> None:
        """Export the document to PDF format.

        Requires the reportlab library. Install with: pip install reportlab

        Args:
            output: Output file path or file-like object.
            options: Export options (page size, margins, fonts, etc.).
                    If None, uses default options.

        Raises:
            ImportError: If reportlab is not installed.

        Example::

            doc = Document.open("notes.one")
            doc.export_pdf("output.pdf")

            # With custom options
            from onenote.pdf_export import PdfExportOptions
            options = PdfExportOptions(
                margin_left=50,
                margin_right=50,
                default_font_size=12,
            )
            doc.export_pdf("output.pdf", options=options)
        """
        from .pdf_export import export_pdf
        export_pdf(self, output, options)

    def __repr__(self) -> str:
        name = self.display_name or (self._source_path.name if self._source_path else "Document")
        return f"Document({name!r}, pages={len(self.pages)})"
