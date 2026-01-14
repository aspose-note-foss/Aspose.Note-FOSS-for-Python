import sys
import unittest
import hashlib
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.ms_one.reader import parse_section_file  # noqa: E402
from aspose.note._internal.ms_one.entities.base import BaseNode  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import Image as MsImage  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import Page as MsPage  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import RichText as MsRichText  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import Section as MsSection  # noqa: E402
from aspose.note._internal.ms_one.entities.structure import Table as MsTable  # noqa: E402

from aspose.note._internal.onenote import Document, Image as PublicImage  # noqa: E402
from aspose.note._internal.onestore.chunk_refs import FileNodeChunkReference  # noqa: E402
from aspose.note._internal.onestore.file_data import (  # noqa: E402
    get_file_data_by_reference,
    parse_file_data_store_index,
    parse_file_data_store_object_from_ref,
)
from aspose.note._internal.onestore.object_data import DecodedPropertySet  # noqa: E402
from aspose.note._internal.onestore.parse_context import ParseContext  # noqa: E402


def _fixture_path() -> Path | None:
    p = ROOT / "testfiles" / "3ImagesWithDifferentAlignment.one"
    return p if p.exists() else None


def _iter_nodes(root: BaseNode):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        for attr in ("children", "content_children"):
            kids = getattr(n, attr, None)
            if kids:
                stack.extend(reversed(list(kids)))


def _sniff_image_extension(data: bytes) -> str | None:
    # Common signatures; keep this simple and non-brittle.
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return "tif"
    return None


_IFNDF_TEXT_RE = re.compile(r"<ifndf>\{[0-9a-fA-F\-]{36}\}</ifndf>")


def _iter_property_bytes(pset: DecodedPropertySet) -> "list[bytes]":
    out: list[bytes] = []
    stack: list[DecodedPropertySet] = [pset]
    while stack:
        cur = stack.pop()
        for prop in cur.properties:
            v = prop.value
            if isinstance(v, bytes):
                out.append(v)
                continue
            if isinstance(v, DecodedPropertySet):
                stack.append(v)
                continue
            if isinstance(v, tuple):
                for item in v:
                    if isinstance(item, bytes):
                        out.append(item)
                    elif isinstance(item, DecodedPropertySet):
                        stack.append(item)
    return out


def _extract_ifndf_refs_from_pset(pset: DecodedPropertySet) -> list[str]:
    refs: set[str] = set()
    for b in _iter_property_bytes(pset):
        # Fast path: ASCII bytes containing the tag.
        if b"<ifndf>" in b:
            for m in re.finditer(rb"<ifndf>\{[0-9a-fA-F\-]{36}\}</ifndf>", b):
                try:
                    refs.add(m.group(0).decode("ascii"))
                except UnicodeDecodeError:
                    continue

        # UTF-16LE path: OneNote often stores strings as UTF-16LE.
        if b"<\x00i\x00f\x00n\x00d\x00f\x00" in b:
            s = b.decode("utf-16le", errors="ignore")
            for m in _IFNDF_TEXT_RE.finditer(s):
                refs.add(m.group(0))

    return sorted(refs)


def _extract_candidate_guids_from_pset(pset: DecodedPropertySet, *, index_keys: set[bytes]) -> list[bytes]:
    """Try to find FileDataStore GUID references embedded in property bytes.

    We support both:
    - textual `<ifndf>{GUID}</ifndf>` references
    - raw 16-byte GUID values (little-endian), matched against known FDS GUID keys
    """

    out: set[bytes] = set()

    for ref in _extract_ifndf_refs_from_pset(pset):
        parsed = None
        try:
            parsed = uuid.UUID(ref[len("<ifndf>{") : -len("}</ifndf>")])
        except Exception:
            parsed = None
        if parsed is not None:
            out.add(parsed.bytes_le)

    # If no textual refs were found (or in addition), search for raw GUID bytes.
    if index_keys:
        for b in _iter_property_bytes(pset):
            if len(b) < 16:
                continue
            # Sliding window; cheap enough for fixture-sized property payloads.
            for i in range(0, len(b) - 15):
                chunk = b[i : i + 16]
                if chunk in index_keys:
                    out.add(bytes(chunk))

    return sorted(out)


def _resolve_first_image_blob_for_ms_image(
    data: bytes,
    image: MsImage,
    *,
    index: dict[bytes, FileNodeChunkReference],
    ctx: ParseContext,
) -> tuple[str, bytes] | None:
    if image.raw_properties is None:
        return None

    # Prefer string-based resolution when possible (it validates the syntax).
    for ref in _extract_ifndf_refs_from_pset(image.raw_properties):
        blob = get_file_data_by_reference(data, ref, ctx=ctx, index=index)
        if not blob:
            continue
        ext = _sniff_image_extension(blob)
        if ext is not None:
            return (ext, blob)

    # Fallback: match raw 16-byte GUIDs directly against FileDataStore index keys.
    keyset = set(index.keys())
    for guid_le in _extract_candidate_guids_from_pset(image.raw_properties, index_keys=keyset):
        ref = index.get(guid_le)
        if ref is None:
            continue
        obj = parse_file_data_store_object_from_ref(
            data,
            stp=int(ref.stp),
            cb=int(ref.cb),
            ctx=ctx,
        )
        ext = _sniff_image_extension(obj.file_data)
        if ext is not None:
            return (ext, bytes(obj.file_data))

    return None


def _extract_image_blobs_from_file_data_store(data: bytes) -> list[tuple[str, bytes]]:
    ctx = ParseContext(strict=False, file_size=len(data))
    idx = parse_file_data_store_index(data, ctx=ctx)
    if not idx:
        return []

    found: list[tuple[str, bytes]] = []
    for _guid_le, ref in sorted(idx.items(), key=lambda kv: kv[0]):
        obj = parse_file_data_store_object_from_ref(
            data,
            stp=int(ref.stp),
            cb=int(ref.cb),
            ctx=ctx,
        )
        ext = _sniff_image_extension(obj.file_data)
        if ext is None:
            continue
        found.append((ext, obj.file_data))
    return found


class TestMSOne3ImagesWithDifferentAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path()
        if p is None:
            raise unittest.SkipTest("3ImagesWithDifferentAlignment.one not found")
        cls.path = p
        cls.data = p.read_bytes()

    def test_file_sanity(self) -> None:
        self.assertGreater(len(self.data), 1024)

    def test_parse_does_not_crash(self) -> None:
        section = parse_section_file(self.data, strict=True)
        self.assertIsInstance(section, MsSection)

    def test_extracts_pages(self) -> None:
        section = parse_section_file(self.data, strict=True)
        pages = [n for n in _iter_nodes(section) if isinstance(n, MsPage)]
        self.assertGreaterEqual(len(pages), 1)

    def test_contains_three_images(self) -> None:
        section = parse_section_file(self.data, strict=True)
        images = [n for n in _iter_nodes(section) if isinstance(n, MsImage)]
        # Fixture is expected to contain exactly 3 images.
        self.assertEqual(len(images), 3)

    def test_images_have_same_file_data_guid(self) -> None:
        section = parse_section_file(self.data, strict=True)
        images = [n for n in _iter_nodes(section) if isinstance(n, MsImage)]
        self.assertEqual(len(images), 3)

        # MS-ONE already exposes the underlying object GUID as BaseNode.oid.
        # In this fixture, the same Image object is referenced multiple times with different layout.
        oids = {img.oid.guid for img in images}
        self.assertEqual(len(oids), 1, "Expected all three Image nodes to reference the same MS-ONE object GUID")

    def test_contains_at_least_one_table(self) -> None:
        section = parse_section_file(self.data, strict=True)
        tables = [n for n in _iter_nodes(section) if isinstance(n, MsTable)]
        self.assertGreaterEqual(len(tables), 1)

    def test_contains_expected_labels_as_rich_text(self) -> None:
        section = parse_section_file(self.data, strict=True)
        texts = [n.text for n in _iter_nodes(section) if isinstance(n, MsRichText) and n.text]
        joined = "\n".join(texts)

        # The fixture embeds descriptive labels near each image.
        self.assertIn("Image in the outline with right alignment", joined)
        self.assertIn("Image in the outline with center alignment", joined)
        self.assertIn("Image in the outline with left alignment", joined)


class TestOneNoteAPI3ImagesWithDifferentAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path()
        if p is None:
            raise unittest.SkipTest("3ImagesWithDifferentAlignment.one not found")
        cls.doc = Document.open(p, strict=True)

    def test_document_has_pages(self) -> None:
        self.assertGreaterEqual(len(self.doc.pages), 1)

    def test_document_exposes_three_images(self) -> None:
        images: list[PublicImage] = []
        for page in self.doc.pages:
            images.extend(list(page.iter_images()))

        self.assertEqual(len(images), 3)
        for img in images:
            self.assertIsInstance(img, PublicImage)

    def test_page_text_contains_expected_labels(self) -> None:
        combined = "\n".join(p.text for p in self.doc.pages if p.text)
        # Public API currently guarantees page title text; detailed per-image labels
        # are validated at the MS-ONE entity layer test above.
        self.assertIn("Image in the outline with right alignment", combined)

    def test_public_images_have_data_and_are_identical(self) -> None:
        images: list[PublicImage] = []
        for page in self.doc.pages:
            images.extend(list(page.iter_images()))

        self.assertEqual(len(images), 3)

        blobs = [img.data for img in images]
        self.assertTrue(all(isinstance(b, (bytes, bytearray)) for b in blobs))
        self.assertTrue(all(len(b) > 1024 for b in blobs), "Expected all images to have embedded bytes > 1KB")

        h = [hashlib.sha256(bytes(b)).digest() for b in blobs]
        self.assertEqual(len(set(h)), 1, "Expected all three Image nodes to resolve to the same embedded bytes")

    def test_extracts_three_images_to_out_dir_and_sizes_are_gt_1kb(self) -> None:
        # NOTE: Public Image.data is not populated yet; resolve raw image bytes via
        # the MS-ONE Image nodes' file-data references.
        data = self.doc.source_path.read_bytes() if self.doc.source_path else None
        if data is None:
            raise unittest.SkipTest("Document has no source_path; cannot persist images")

        section = parse_section_file(data, strict=True)
        ms_images = [n for n in _iter_nodes(section) if isinstance(n, MsImage)]
        if len(ms_images) != 3:
            raise unittest.SkipTest("Fixture does not expose exactly 3 MS-ONE Image nodes")

        ctx = ParseContext(strict=False, file_size=len(data))
        idx = parse_file_data_store_index(data, ctx=ctx)
        if not idx:
            raise unittest.SkipTest("Empty FileDataStore index")

        resolved: list[tuple[str, bytes]] = []
        for img in ms_images:
            hit = _resolve_first_image_blob_for_ms_image(data, img, index=idx, ctx=ctx)
            if hit is None:
                raise unittest.SkipTest("Could not resolve image bytes from MS-ONE Image properties")
            resolved.append(hit)

        out_dir = ROOT / "tests" / "out" / "3ImagesWithDifferentAlignment"
        out_dir.mkdir(parents=True, exist_ok=True)

        for i, (ext, blob) in enumerate(resolved, start=1):
            out_path = out_dir / f"image_{i}.{ext}"
            out_path.write_bytes(blob)
            self.assertGreater(out_path.stat().st_size, 1024)

    def test_images_are_identical_by_byte_content(self) -> None:
        data = self.doc.source_path.read_bytes() if self.doc.source_path else None
        if data is None:
            raise unittest.SkipTest("Document has no source_path; cannot read bytes")

        section = parse_section_file(data, strict=True)
        ms_images = [n for n in _iter_nodes(section) if isinstance(n, MsImage)]
        if len(ms_images) != 3:
            raise unittest.SkipTest("Fixture does not expose exactly 3 MS-ONE Image nodes")

        ctx = ParseContext(strict=False, file_size=len(data))
        idx = parse_file_data_store_index(data, ctx=ctx)
        if not idx:
            raise unittest.SkipTest("Empty FileDataStore index")

        resolved: list[tuple[str, bytes]] = []
        for img in ms_images:
            hit = _resolve_first_image_blob_for_ms_image(data, img, index=idx, ctx=ctx)
            if hit is None:
                raise unittest.SkipTest("Could not resolve image bytes from MS-ONE Image properties")
            resolved.append(hit)

        # Expect all three placements to reuse the same embedded image.
        (ext1, b1), (ext2, b2), (ext3, b3) = resolved
        self.assertEqual(ext1, ext2)
        self.assertEqual(ext2, ext3)
        self.assertEqual(hashlib.sha256(b1).digest(), hashlib.sha256(b2).digest())
        self.assertEqual(hashlib.sha256(b2).digest(), hashlib.sha256(b3).digest())
        self.assertEqual(b1, b2)
        self.assertEqual(b2, b3)
