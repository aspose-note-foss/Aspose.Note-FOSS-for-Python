from __future__ import annotations

import difflib
import io
import unittest

from tests._pdf_goldens import (
    HAS_PYPDF,
    PDF_GOLDEN_CASES,
    create_visual_diff_artifacts,
    ensure_output_dirs,
    failure_manifest_path,
    failure_pdf_path,
    fixture_path,
    golden_manifest_path,
    golden_pdf_path,
    load_manifest,
    manifest_pretty_json,
    semantic_manifest,
    visual_diff_available,
    write_manifest,
)

try:
    import reportlab  # noqa: F401

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


@unittest.skipUnless(HAS_REPORTLAB and HAS_PYPDF, "reportlab and pypdf are required")
class TestAsposeNotePdfGoldens(unittest.TestCase):
    def test_pdf_goldens_match_manifest(self) -> None:
        from aspose.note import Document
        from aspose.note.saving import PdfSaveOptions

        from tests._pdf_goldens import build_pdf_manifest

        ensure_output_dirs()

        for case in PDF_GOLDEN_CASES:
            with self.subTest(case=case.case_id):
                source = fixture_path(case.fixture_name)
                if source is None:
                    raise unittest.SkipTest(f"{case.fixture_name} not found")

                expected_pdf = golden_pdf_path(case.case_id)
                expected_manifest_path = golden_manifest_path(case.case_id)
                self.assertTrue(
                    expected_manifest_path.exists(),
                    f"Missing golden manifest for {case.case_id}. Run tools/regenerate_pdf_goldens.py.",
                )

                buf = io.BytesIO()
                Document(source).Save(buf, PdfSaveOptions())

                generated_pdf = failure_pdf_path(case.case_id)
                generated_pdf.write_bytes(buf.getvalue())
                actual_manifest = build_pdf_manifest(generated_pdf, fixture_name=case.fixture_name)
                generated_manifest = failure_manifest_path(case.case_id)
                write_manifest(generated_manifest, actual_manifest)

                expected_manifest = load_manifest(expected_manifest_path)
                actual_semantic = semantic_manifest(actual_manifest)
                expected_semantic = semantic_manifest(expected_manifest)
                if actual_semantic != expected_semantic:
                    visual_artifacts: list[str] = []
                    if expected_pdf.exists() and visual_diff_available():
                        visual_artifacts = [
                            str(path)
                            for path in create_visual_diff_artifacts(case.case_id, expected_pdf, generated_pdf)
                        ]
                    diff = "".join(
                        difflib.unified_diff(
                            manifest_pretty_json(expected_semantic).splitlines(keepends=True),
                            manifest_pretty_json(actual_semantic).splitlines(keepends=True),
                            fromfile=str(expected_manifest_path),
                            tofile=str(generated_manifest),
                        )
                    )
                    self.fail(
                        f"PDF golden mismatch for {case.case_id}.\n"
                        f"Generated PDF: {generated_pdf}\n"
                        f"Generated manifest: {generated_manifest}\n"
                        f"Comparison mode: semantic manifest (text, links, image_count, page_count)\n"
                        f"Visual artifacts: {visual_artifacts or 'not available'}\n"
                        f"Manifest diff:\n{diff}"
                    )

    def test_numbered_list_fixture_preserves_list_markers(self) -> None:
        from aspose.note import Document
        from aspose.note.saving import PdfSaveOptions

        from tests._pdf_goldens import build_pdf_manifest

        source = fixture_path("NumberedListWithTags.one")
        if source is None:
            raise unittest.SkipTest("NumberedListWithTags.one not found")

        ensure_output_dirs()
        generated_pdf = failure_pdf_path("numbered_list_with_tags.markers")

        buf = io.BytesIO()
        Document(source).Save(buf, PdfSaveOptions())
        generated_pdf.write_bytes(buf.getvalue())

        manifest = build_pdf_manifest(generated_pdf, fixture_name="NumberedListWithTags.one")
        text = manifest["pages"][0]["text"]

        for expected in (
            "1.",
            "2.",
            "a.",
            "b.",
            "c.",
            "i.",
            "ii.",
        ):
            self.assertIn(expected, text)

    def test_attachment_fixture_exports_filename_only(self) -> None:
        from aspose.note import Document
        from aspose.note.saving import PdfSaveOptions

        from tests._pdf_goldens import build_pdf_manifest

        source = fixture_path("AttachedFileWithTag.one")
        if source is None:
            raise unittest.SkipTest("AttachedFileWithTag.one not found")

        ensure_output_dirs()
        generated_pdf = failure_pdf_path("attached_file_with_tag.inline")

        buf = io.BytesIO()
        Document(source).Save(buf, PdfSaveOptions())
        generated_pdf.write_bytes(buf.getvalue())

        manifest = build_pdf_manifest(generated_pdf, fixture_name="AttachedFileWithTag.one")
        text = manifest["pages"][0]["text"]

        self.assertNotIn("[Attachment]", text)
        self.assertIn("TestOneNoteSaveAsTiffByFormat.tiff", text)
        self.assertNotIn("Важно, Дела", text)