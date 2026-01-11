import sys
import unittest
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ms_one.reader import parse_section_file  # noqa: E402
from ms_one.entities.base import BaseNode  # noqa: E402
from ms_one.entities.structure import Image as MsImage  # noqa: E402
from ms_one.entities.structure import Section as MsSection  # noqa: E402

from onenote import Document, Image as PublicImage  # noqa: E402
from onestore.file_data import (  # noqa: E402
    get_file_data_by_reference,
    parse_file_data_store_index,
    parse_file_data_store_object_from_ref,
)
from onestore.object_data import DecodedPropertySet  # noqa: E402
from onestore.parse_context import ParseContext  # noqa: E402


def _fixture_path() -> Path | None:
    p = ROOT / "testfiles" / "SimpleImageFromSeparateFile.one"
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
            elif isinstance(v, DecodedPropertySet):
                stack.append(v)
            elif isinstance(v, tuple):
                for item in v:
                    if isinstance(item, bytes):
                        out.append(item)
                    elif isinstance(item, DecodedPropertySet):
                        stack.append(item)
    return out


def _extract_ifndf_refs_from_pset(pset: DecodedPropertySet) -> list[str]:
    refs: set[str] = set()

    for b in _iter_property_bytes(pset):
        if b"<ifndf>" in b:
            for m in re.finditer(rb"<ifndf>\{[0-9a-fA-F\-]{36}\}</ifndf>", b):
                try:
                    refs.add(m.group(0).decode("ascii"))
                except UnicodeDecodeError:
                    continue

        # UTF-16LE strings are common in OneNote.
        if b"<\x00i\x00f\x00n\x00d\x00f\x00" in b:
            s = b.decode("utf-16le", errors="ignore")
            for m in _IFNDF_TEXT_RE.finditer(s):
                refs.add(m.group(0))

    return sorted(refs)


def _resolve_first_image_blob(data: bytes, image: MsImage) -> tuple[str, bytes] | None:
    ctx = ParseContext(strict=False, file_size=len(data))
    idx = parse_file_data_store_index(data, ctx=ctx)
    if not idx:
        return None

    # Preferred: resolve via explicit <ifndf>{GUID}</ifndf> reference(s) in Image properties.
    if image.raw_properties is not None:
        for ref in _extract_ifndf_refs_from_pset(image.raw_properties):
            blob = get_file_data_by_reference(data, ref, ctx=ctx, index=idx)
            if not blob:
                continue
            ext = _sniff_image_extension(blob)
            if ext is not None:
                return (ext, blob)

    # Fallback: scan FileDataStore objects and pick the first recognized image blob.
    for _guid_le, ref in sorted(idx.items(), key=lambda kv: kv[0]):
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


class TestSimpleImageFromSeparateFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path()
        if p is None:
            raise unittest.SkipTest("SimpleImageFromSeparateFile.one not found")
        cls.path = p
        cls.data = p.read_bytes()

    def test_extract_and_verify_single_image(self) -> None:
        # MS-ONE layer: parse + find the Image node
        section = parse_section_file(self.data, strict=True)
        self.assertIsInstance(section, MsSection)

        ms_images = [n for n in _iter_nodes(section) if isinstance(n, MsImage)]
        self.assertEqual(len(ms_images), 1, "Expected exactly one MS-ONE Image node")

        # MS-ONE should preserve the original source filename when present.
        self.assertIsNotNone(ms_images[0].original_filename, "Expected original image filename to be parsed")
        self.assertTrue(str(ms_images[0].original_filename).strip())
        self.assertEqual(ms_images[0].original_filename, "Tulips.jpg")

        hit = _resolve_first_image_blob(self.data, ms_images[0])
        self.assertIsNotNone(hit, "Could not resolve image bytes from FileDataStore")
        ext, blob = hit  # type: ignore[misc]

        self.assertIn(ext, {"png", "jpg", "bmp", "gif", "tif"})
        self.assertGreater(len(blob), 1024, "Expected extracted image to be > 1KB")

        # If the filename has an extension, it should be consistent with the detected format.
        name = ms_images[0].original_filename or ""
        suffix = Path(name).suffix.lower().lstrip(".")
        if suffix:
            self.assertEqual(suffix, ext)

        # Public API: document exposes exactly one image
        doc = Document.open(self.path, strict=True)
        images: list[PublicImage] = []
        for page in doc.pages:
            images.extend(list(page.iter_images()))
        self.assertEqual(len(images), 1)
        self.assertIsInstance(images[0], PublicImage)
        self.assertTrue(getattr(images[0], "filename", None))
        self.assertEqual(images[0].filename, ms_images[0].original_filename)

    def test_extract_and_save_single_image_to_out_dir(self) -> None:
        # MS-ONE layer: parse + find the Image node
        section = parse_section_file(self.data, strict=True)
        ms_images = [n for n in _iter_nodes(section) if isinstance(n, MsImage)]
        self.assertEqual(len(ms_images), 1)

        hit = _resolve_first_image_blob(self.data, ms_images[0])
        self.assertIsNotNone(hit, "Could not resolve image bytes from FileDataStore")
        ext, blob = hit  # type: ignore[misc]

        out_dir = ROOT / "tests" / "out" / "SimpleImageFromSeparateFile"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Prefer original filename if present; otherwise fall back to a stable name.
        stem = "image_1"
        if ms_images[0].original_filename:
            safe = Path(ms_images[0].original_filename).name
            if safe:
                stem = safe
        out_path = out_dir / stem
        if out_path.suffix.lower().lstrip(".") != ext:
            out_path = out_path.with_suffix(f".{ext}")
        out_path.write_bytes(blob)
        self.assertGreater(out_path.stat().st_size, 1024)
