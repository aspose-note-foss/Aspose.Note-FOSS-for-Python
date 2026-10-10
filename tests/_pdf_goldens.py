from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests._bootstrap import ensure_src_on_path

ensure_src_on_path()

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

GOLDENS_DIR = ROOT / "tests" / "goldens" / "pdf"
FAILURES_DIR = ROOT / "tests" / "out" / "pdf_golden_failures"

MANIFEST_SCHEMA_VERSION = 2

try:
    from pypdf import PdfReader

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import fitz

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from PIL import Image, ImageChops

    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

PDFTOPPM_PATH = shutil.which("pdftoppm")
HAS_PDFTOPPM = PDFTOPPM_PATH is not None


@dataclass(frozen=True)
class PdfGoldenCase:
    case_id: str
    fixture_name: str


PDF_GOLDEN_CASES: tuple[PdfGoldenCase, ...] = (
    PdfGoldenCase("attached_file_with_tag", "AttachedFileWithTag.one"),
    PdfGoldenCase("formatted_richtext", "FormattedRichText.one"),
    PdfGoldenCase("image_with_tag", "ImageWithTag.one"),
    PdfGoldenCase("page_with_subpage", "Issue1Subpages.one"),
    PdfGoldenCase("simple_table", "SimpleTable.one"),
    PdfGoldenCase("numbered_list_with_tags", "NumberedListWithTags.one"),
    PdfGoldenCase("images_with_alignment", "3ImagesWithDifferentAlignment.one"),
    PdfGoldenCase("one_page_with_file", "OnePageWithFile.one"),
    PdfGoldenCase("simple_history", "SimpleHistory.one"),
    PdfGoldenCase("simple_image_from_separate_file", "SimpleImageFromSeparateFile.one"),
    PdfGoldenCase("table_with_tag", "TableWithTag.one"),
    PdfGoldenCase("tag_sizes", "TagSizes.one"),
)


def fixture_path(name: str) -> Path | None:
    path = ROOT / "testfiles" / name
    return path if path.exists() else None


def golden_pdf_path(case_id: str) -> Path:
    return GOLDENS_DIR / f"{case_id}.pdf"


def golden_manifest_path(case_id: str) -> Path:
    return GOLDENS_DIR / f"{case_id}.manifest.json"


def failure_pdf_path(case_id: str) -> Path:
    return FAILURES_DIR / f"{case_id}.generated.pdf"


def failure_manifest_path(case_id: str) -> Path:
    return FAILURES_DIR / f"{case_id}.generated.manifest.json"


def ensure_output_dirs() -> None:
    GOLDENS_DIR.mkdir(parents=True, exist_ok=True)
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)


def visual_diff_available() -> bool:
    return HAS_PILLOW and (HAS_PYMUPDF or HAS_PDFTOPPM)


def normalize_text(text: str) -> str:
    normalized_lines: list[str] = []
    for line in text.replace("\xa0", " ").splitlines():
        compact = re.sub(r"\s+", " ", line).strip()
        if compact:
            normalized_lines.append(compact)
    return "\n".join(normalized_lines)


def _annotation_links(page) -> list[str]:
    links: set[str] = set()
    annotations = page.get("/Annots") or []
    for annotation in annotations:
        try:
            resolved = annotation.get_object()
        except Exception:
            continue
        action = resolved.get("/A") if hasattr(resolved, "get") else None
        if action is None or not hasattr(action, "get"):
            continue
        uri = action.get("/URI")
        if isinstance(uri, str) and uri.strip():
            links.add(uri.strip())
    return sorted(links)


def _image_count(page) -> int:
    resources = page.get("/Resources") if hasattr(page, "get") else None
    if not resources or not hasattr(resources, "get"):
        return 0
    x_objects = resources.get("/XObject")
    if x_objects is None:
        return 0
    try:
        resolved = x_objects.get_object()
    except Exception:
        resolved = x_objects
    if not hasattr(resolved, "items"):
        return 0
    count = 0
    for _, obj in resolved.items():
        try:
            candidate = obj.get_object()
        except Exception:
            candidate = obj
        if hasattr(candidate, "get") and candidate.get("/Subtype") == "/Image":
            count += 1
    return count


def _normalize_layout_number(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return str(value)
    rounded = round(number, 2)
    if abs(rounded) < 0.005:
        rounded = 0.0
    text = f"{rounded:.2f}"
    return text.rstrip("0").rstrip(".") or "0"


def _normalize_layout_operand(value: Any, name_map: dict[str, str]) -> Any:
    if isinstance(value, (list, tuple)):
        return [_normalize_layout_operand(item, name_map) for item in value]
    if isinstance(value, str):
        return "<str>"
    if hasattr(value, "items"):
        return "<dict>"

    text = str(value)
    if text.startswith("/"):
        token = name_map.get(text)
        if token is None:
            token = f"N{len(name_map) + 1}"
            name_map[text] = token
        return token

    try:
        return _normalize_layout_number(value)
    except Exception:
        return text


def _layout_operations(page, reader) -> list[str]:
    try:
        from pypdf.generic import ContentStream
    except Exception:
        return []

    try:
        content = ContentStream(page.get_contents(), reader)
    except Exception:
        return []

    name_map: dict[str, str] = {}
    operations: list[str] = []
    for operands, operator in content.operations:
        operator_text = operator.decode("latin-1") if isinstance(operator, bytes) else str(operator)
        normalized_operands = [_normalize_layout_operand(operand, name_map) for operand in operands]
        pieces = [operator_text]
        for operand in normalized_operands:
            if isinstance(operand, list):
                pieces.append("[" + ", ".join(str(item) for item in operand) + "]")
            else:
                pieces.append(str(operand))
        operations.append(" ".join(pieces))
    return operations


def _layout_digest(layout_ops: list[str]) -> str:
    payload = "\n".join(layout_ops).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_pdf_manifest(pdf_path: Path, fixture_name: str | None = None) -> dict[str, Any]:
    if not HAS_PYPDF:
        raise RuntimeError("PDF golden tests require pypdf")

    reader = PdfReader(str(pdf_path))
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages):
        extracted_text = page.extract_text() or ""
        layout_ops = _layout_operations(page, reader)
        pages.append(
            {
                "index": index,
                "text": normalize_text(extracted_text),
                "links": _annotation_links(page),
                "image_count": _image_count(page),
                "layout_digest": _layout_digest(layout_ops),
                "layout_ops": layout_ops,
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "page_count": len(pages),
        "pages": pages,
    }
    if fixture_name is not None:
        manifest["fixture"] = fixture_name
    return manifest


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_pretty_json(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def semantic_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    pages = [
        {
            "index": page["index"],
            "text": page["text"],
            "links": page["links"],
            "image_count": page["image_count"],
        }
        for page in manifest.get("pages", [])
    ]

    result: dict[str, Any] = {
        "schema_version": manifest.get("schema_version"),
        "page_count": manifest.get("page_count"),
        "pages": pages,
    }
    if "fixture" in manifest:
        result["fixture"] = manifest["fixture"]
    return result


def _render_pdf_with_pymupdf(pdf_path: Path, output_dir: Path, prefix: str) -> list[Path]:
    if not HAS_PYMUPDF:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf_path)
    written: list[Path] = []
    try:
        matrix = fitz.Matrix(2.0, 2.0)
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            output_path = output_dir / f"{prefix}-{index}.png"
            pixmap.save(output_path)
            written.append(output_path)
    finally:
        document.close()
    return written


def _render_pdf_to_pngs(pdf_path: Path, output_dir: Path, prefix: str) -> list[Path]:
    if HAS_PYMUPDF:
        return _render_pdf_with_pymupdf(pdf_path, output_dir, prefix)
    if not HAS_PDFTOPPM:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = output_dir / prefix
    subprocess.run(
        [PDFTOPPM_PATH, "-png", "-r", "144", str(pdf_path), str(output_prefix)],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(output_dir.glob(f"{prefix}-*.png"))


def create_visual_diff_artifacts(case_id: str, expected_pdf: Path, generated_pdf: Path) -> list[Path]:
    if not visual_diff_available():
        return []

    case_dir = FAILURES_DIR / case_id / "visual" / uuid.uuid4().hex[:8]
    baseline_dir = case_dir / "baseline"
    generated_dir = case_dir / "generated"
    diff_dir = case_dir / "diff"

    baseline_pages = _render_pdf_to_pngs(expected_pdf, baseline_dir, "baseline")
    generated_pages = _render_pdf_to_pngs(generated_pdf, generated_dir, "generated")
    written: list[Path] = [*baseline_pages, *generated_pages]

    for index, (baseline_page, generated_page) in enumerate(zip(baseline_pages, generated_pages), start=1):
        with Image.open(baseline_page) as baseline_image, Image.open(generated_page) as generated_image:
            if baseline_image.size != generated_image.size:
                width = max(baseline_image.width, generated_image.width)
                height = max(baseline_image.height, generated_image.height)
                expanded_baseline = Image.new("RGBA", (width, height), "white")
                expanded_generated = Image.new("RGBA", (width, height), "white")
                expanded_baseline.paste(baseline_image.convert("RGBA"), (0, 0))
                expanded_generated.paste(generated_image.convert("RGBA"), (0, 0))
                baseline_rgba = expanded_baseline
                generated_rgba = expanded_generated
            else:
                baseline_rgba = baseline_image.convert("RGBA")
                generated_rgba = generated_image.convert("RGBA")

            diff_image = ImageChops.difference(baseline_rgba, generated_rgba)
            diff_path = diff_dir / f"diff-{index}.png"
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_image.save(diff_path)
            written.append(diff_path)

    return written