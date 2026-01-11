import sys
import unittest
import re
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ms_one.reader import parse_section_file  # noqa: E402
from ms_one.entities.base import BaseNode  # noqa: E402
from ms_one.entities.structure import EmbeddedFile as MsEmbeddedFile  # noqa: E402
from ms_one.entities.structure import Section as MsSection  # noqa: E402

from onestore.file_data import (  # noqa: E402
    get_file_data_by_reference,
    parse_file_data_store_index,
    parse_file_data_store_object_from_ref,
)
from onestore.object_data import DecodedPropertySet  # noqa: E402
from onestore.parse_context import ParseContext  # noqa: E402


def _fixture_path() -> Path | None:
    p = ROOT / "testfiles" / "OnePageWithFile.one"
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


def _resolve_first_attachment_blob(data: bytes, node: MsEmbeddedFile) -> bytes | None:
    ctx = ParseContext(strict=False, file_size=len(data))
    idx = parse_file_data_store_index(data, ctx=ctx)
    if not idx:
        return None

    # Preferred: resolve via GUID(s) collected by ms_one (best-effort).
    for guid in getattr(node, "file_data_guids", ()):
        ref = f"<ifndf>{{{guid}}}</ifndf>"
        blob = get_file_data_by_reference(data, ref, ctx=ctx, index=idx)
        if blob:
            return blob

    # Next: scan node properties for explicit <ifndf>{GUID}</ifndf> references.
    if node.raw_properties is not None:
        for ref in _extract_ifndf_refs_from_pset(node.raw_properties):
            blob = get_file_data_by_reference(data, ref, ctx=ctx, index=idx)
            if blob:
                return blob

    # Fallback: take the largest FileDataStore object.
    best: bytes | None = None
    for _guid_le, ref in idx.items():
        obj = parse_file_data_store_object_from_ref(
            data,
            stp=int(ref.stp),
            cb=int(ref.cb),
            ctx=ctx,
        )
        cur = bytes(obj.file_data)
        if best is None or len(cur) > len(best):
            best = cur

    return best


class TestOnePageWithFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        p = _fixture_path()
        if p is None:
            raise unittest.SkipTest("OnePageWithFile.one not found")
        cls.path = p
        cls.data = p.read_bytes()

    def test_ms_one_extract_and_verify_single_attachment(self) -> None:
        section = parse_section_file(self.data, strict=True)
        self.assertIsInstance(section, MsSection)

        ms_files = [n for n in _iter_nodes(section) if isinstance(n, MsEmbeddedFile)]
        self.assertEqual(len(ms_files), 1, "Expected exactly one MS-ONE EmbeddedFile node")

        f0 = ms_files[0]
        self.assertIsNotNone(f0.original_filename, "Expected attachment filename to be parsed")
        self.assertTrue(str(f0.original_filename).strip())
        self.assertEqual(f0.original_filename, "TestOneNoteSaveAsTiffByFormat.tiff")

        blob = _resolve_first_attachment_blob(self.data, f0)
        self.assertIsNotNone(blob, "Could not resolve attachment bytes from FileDataStore")
        blob = cast(bytes, blob)
        self.assertGreater(len(blob), 32, "Expected attachment to be non-empty")

    def test_ms_one_extract_and_save_attachment_to_out_dir(self) -> None:
        section = parse_section_file(self.data, strict=True)
        ms_files = [n for n in _iter_nodes(section) if isinstance(n, MsEmbeddedFile)]
        self.assertEqual(len(ms_files), 1)
        f0 = ms_files[0]

        blob = _resolve_first_attachment_blob(self.data, f0)
        self.assertIsNotNone(blob, "Could not resolve attachment bytes from FileDataStore")
        blob = cast(bytes, blob)

        out_dir = ROOT / "tests" / "out" / "OnePageWithFile"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Prefer original filename; otherwise fall back to a stable name.
        name = (f0.original_filename or "").strip()
        safe_name = Path(name).name if name else "attachment_1.bin"
        if not safe_name:
            safe_name = "attachment_1.bin"

        out_path = out_dir / safe_name
        if out_path.suffix == "":
            out_path = out_path.with_suffix(".bin")

        out_path.write_bytes(blob)
        self.assertGreater(out_path.stat().st_size, 32)
