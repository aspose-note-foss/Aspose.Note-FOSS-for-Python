"""Tests for PDF export functionality.

Tests export of various OneNote test files to PDF format.
Requires reportlab to be installed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
import io

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Check if reportlab is available
try:
    import reportlab
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

from onenote import Document  # noqa: E402


def _fixture_path(name: str) -> Path | None:
    """Get path to test fixture file."""
    p = ROOT / "testfiles" / name
    return p if p.exists() else None


def _output_dir() -> Path:
    """Get/create output directory for PDF files."""
    out_dir = ROOT / "tests" / "out" / "pdf_export"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportFormattedRichText(unittest.TestCase):
    """Test PDF export of FormattedRichText.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "FormattedRichText.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)
    
    def test_export_to_bytes_io(self) -> None:
        """Test export to BytesIO stream."""
        buffer = io.BytesIO()
        self.doc.export_pdf(buffer)
        buffer.seek(0)
        data = buffer.read()
        self.assertTrue(data.startswith(b'%PDF'))
        self.assertGreater(len(data), 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExport3Images(unittest.TestCase):
    """Test PDF export of 3ImagesWithDifferentAlignment.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("3ImagesWithDifferentAlignment.one")
        if p is None:
            raise unittest.SkipTest("3ImagesWithDifferentAlignment.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "3ImagesWithDifferentAlignment.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)

    def test_images_embedded(self) -> None:
        """Ensure embedded images are resolved from the .one file and written into the PDF."""
        from onenote.elements import Image

        images_with_data = 0
        for page in self.doc.pages:
            for img in page.iter_images():
                if isinstance(img, Image) and img.data:
                    images_with_data += 1

        # This fixture is expected to contain embedded images.
        self.assertGreater(images_with_data, 0)

        # Smoke-check the resulting PDF contains image XObjects.
        buffer = io.BytesIO()
        self.doc.export_pdf(buffer)
        pdf = buffer.getvalue()
        self.assertIn(b"/Subtype /Image", pdf)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportSimpleTable(unittest.TestCase):
    """Test PDF export of SimpleTable.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("SimpleTable.one")
        if p is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "SimpleTable.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportTableWithTag(unittest.TestCase):
    """Test PDF export of TableWithTag.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("TableWithTag.one")
        if p is None:
            raise unittest.SkipTest("TableWithTag.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "TableWithTag.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportNumberedListWithTags(unittest.TestCase):
    """Test PDF export of NumberedListWithTags.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("NumberedListWithTags.one")
        if p is None:
            raise unittest.SkipTest("NumberedListWithTags.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "NumberedListWithTags.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportAttachedFile(unittest.TestCase):
    """Test PDF export of AttachedFileWithTag.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("AttachedFileWithTag.one")
        if p is None:
            raise unittest.SkipTest("AttachedFileWithTag.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "AttachedFileWithTag.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportImageWithTag(unittest.TestCase):
    """Test PDF export of ImageWithTag.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("ImageWithTag.one")
        if p is None:
            raise unittest.SkipTest("ImageWithTag.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "ImageWithTag.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportSimpleHistory(unittest.TestCase):
    """Test PDF export of SimpleHistory.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("SimpleHistory.one")
        if p is None:
            raise unittest.SkipTest("SimpleHistory.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "SimpleHistory.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportOnePageWithFile(unittest.TestCase):
    """Test PDF export of OnePageWithFile.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("OnePageWithFile.one")
        if p is None:
            raise unittest.SkipTest("OnePageWithFile.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "OnePageWithFile.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportTagSizes(unittest.TestCase):
    """Test PDF export of TagSizes.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("TagSizes.one")
        if p is None:
            raise unittest.SkipTest("TagSizes.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "TagSizes.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportSimpleImageFromSeparateFile(unittest.TestCase):
    """Test PDF export of SimpleImageFromSeparateFile.one"""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("SimpleImageFromSeparateFile.one")
        if p is None:
            raise unittest.SkipTest("SimpleImageFromSeparateFile.one not found")
        cls.doc = Document.open(p)
        cls.output_path = _output_dir() / "SimpleImageFromSeparateFile.pdf"
    
    def test_export_creates_file(self) -> None:
        """Test that export creates a PDF file."""
        self.doc.export_pdf(self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 100)


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportOptions(unittest.TestCase):
    """Test PDF export with custom options."""
    
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")
        cls.doc = Document.open(p)
    
    def test_custom_page_size(self) -> None:
        """Test export with custom page size."""
        from onenote import PdfExportOptions
        
        options = PdfExportOptions(
            page_width=595.0,  # A4 width
            page_height=842.0,  # A4 height
        )
        output_path = _output_dir() / "FormattedRichText_A4.pdf"
        self.doc.export_pdf(output_path, options=options)
        self.assertTrue(output_path.exists())
    
    def test_custom_margins(self) -> None:
        """Test export with custom margins."""
        from onenote import PdfExportOptions
        
        options = PdfExportOptions(
            margin_left=50,
            margin_right=50,
            margin_top=50,
            margin_bottom=50,
        )
        output_path = _output_dir() / "FormattedRichText_small_margins.pdf"
        self.doc.export_pdf(output_path, options=options)
        self.assertTrue(output_path.exists())
    
    def test_no_tags(self) -> None:
        """Test export without tags."""
        from onenote import PdfExportOptions
        
        options = PdfExportOptions(include_tags=False)
        output_path = _output_dir() / "FormattedRichText_no_tags.pdf"
        self.doc.export_pdf(output_path, options=options)
        self.assertTrue(output_path.exists())
    
    def test_no_images(self) -> None:
        """Test export without images."""
        from onenote import PdfExportOptions
        
        options = PdfExportOptions(include_images=False)
        output_path = _output_dir() / "FormattedRichText_no_images.pdf"
        self.doc.export_pdf(output_path, options=options)
        self.assertTrue(output_path.exists())
    
    def test_custom_font_size(self) -> None:
        """Test export with custom font size."""
        from onenote import PdfExportOptions
        
        options = PdfExportOptions(
            default_font_size=14,
            title_font_size=24,
        )
        output_path = _output_dir() / "FormattedRichText_large_font.pdf"
        self.doc.export_pdf(output_path, options=options)
        self.assertTrue(output_path.exists())


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class TestPdfExportAllTestFiles(unittest.TestCase):
    """Test PDF export of all available test files."""
    
    def test_export_all_files(self) -> None:
        """Export all test files to PDF."""
        test_files = [
            "3ImagesWithDifferentAlignment.one",
            "AttachedFileWithTag.one",
            "FormattedRichText.one",
            "ImageWithTag.one",
            "NumberedListWithTags.one",
            "OnePageWithFile.one",
            "SimpleHistory.one",
            "SimpleImageFromSeparateFile.one",
            "SimpleTable.one",
            "TableWithTag.one",
            "TagSizes.one",
        ]
        
        exported = []
        skipped = []
        failed = []
        
        for filename in test_files:
            path = _fixture_path(filename)
            if path is None:
                skipped.append(filename)
                continue
            
            try:
                doc = Document.open(path)
                output_name = filename.replace(".one", ".pdf")
                output_path = _output_dir() / output_name
                doc.export_pdf(output_path)
                
                if output_path.exists() and output_path.stat().st_size > 100:
                    exported.append(filename)
                else:
                    failed.append(filename)
            except Exception as e:
                failed.append(f"{filename}: {e}")
        
        print(f"\nExported: {len(exported)}")
        print(f"Skipped (file not found): {len(skipped)}")
        print(f"Failed: {len(failed)}")
        
        if failed:
            print(f"Failures: {failed}")
        
        # At least some files should export successfully
        self.assertGreater(len(exported), 0, "At least one file should export successfully")


if __name__ == "__main__":
    unittest.main()
