"""Debug helper: decode ReportLab PDF content streams and list text draw operations.

Usage (PowerShell):
  python tools/debug_pdf_text_ops.py NumberedListWithTags.pdf

This does not modify PDFs; it just helps diagnose layout/overlap issues.
"""

from __future__ import annotations

import base64
import re
import sys
import zlib
from pathlib import Path


def _iter_decoded_streams(pdf_bytes: bytes):
    for m in re.finditer(br"stream\r?\n", pdf_bytes):
        start = m.end()
        end = pdf_bytes.find(b"endstream", start)
        if end == -1:
            continue

        dict_start = pdf_bytes.rfind(b"<<", max(0, m.start() - 20000), m.start())
        dict_end = pdf_bytes.find(b">>", dict_start, m.start()) if dict_start != -1 else -1
        if dict_start == -1 or dict_end == -1:
            continue
        stream_dict = pdf_bytes[dict_start : dict_end + 2]

        raw = pdf_bytes[start:end].strip()
        decoded = raw

        if b"ASCII85Decode" in stream_dict:
            if decoded.startswith(b"<~") and decoded.endswith(b"~>"):
                decoded = decoded[2:-2]
            decoded = base64.a85decode(decoded, adobe=True)

        if b"FlateDecode" in stream_dict:
            decoded = zlib.decompress(decoded)

        yield stream_dict, decoded


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Usage: python tools/debug_pdf_text_ops.py <pdf-path> [search]")
        return 2

    pdf_path = Path(sys.argv[1])
    search = sys.argv[2].encode("latin1") if len(sys.argv) == 3 else None
    pdf_bytes = pdf_path.read_bytes()

    # Common ReportLab text operator pattern.
    # Example: BT 1 0 0 1 160 0 Tm (1.) Tj T* ET
    tm_pattern = re.compile(rb"BT\s+1 0 0 1 ([0-9.]+) ([0-9.]+) Tm \((.*?)\) Tj")
    cm_pattern = re.compile(rb"1 0 0 1 ([0-9.]+) ([0-9.]+) cm")

    matches: list[tuple[float, float, float, float, str]] = []

    cm_positions: list[tuple[float, float]] = []

    for stream_dict, decoded in _iter_decoded_streams(pdf_bytes):
        if search and search in decoded:
            idx = decoded.find(search)
            lo = max(0, idx - 400)
            hi = min(len(decoded), idx + 400)
            print("--- decoded context ---")
            print(decoded[lo:hi].decode("latin1", "ignore"))

        # Very small, non-general parser: keep a stack of translations (tx, ty)
        # affected by q/Q, and update it when we see "1 0 0 1 tx ty cm".
        tx, ty = 0.0, 0.0
        stack: list[tuple[float, float]] = []

        # Scan sequentially for q/Q/cm/BT..Tm..Tj.
        token_re = re.compile(rb"\bq\b|\bQ\b|1 0 0 1 [0-9.]+ [0-9.]+ cm|BT\s+1 0 0 1 [0-9.]+ [0-9.]+ Tm \(.*?\) Tj", re.S)
        for t in token_re.finditer(decoded):
            tok = t.group(0)
            if tok == b"q":
                stack.append((tx, ty))
                continue
            if tok == b"Q":
                if stack:
                    tx, ty = stack.pop()
                continue
            if tok.endswith(b" cm"):
                mm = cm_pattern.search(tok)
                if mm:
                    tx, ty = float(mm.group(1)), float(mm.group(2))
                    cm_positions.append((tx, ty))
                continue
            if tok.startswith(b"BT"):
                mm = tm_pattern.search(tok)
                if mm:
                    x = float(mm.group(1))
                    y = float(mm.group(2))
                    txt = mm.group(3).decode("latin1", "ignore")
                    matches.append((ty + y, tx + x, ty, tx, txt))

    matches.sort(reverse=True)

    # Show repeated placements (often a sign of overlap).
    counts: dict[tuple[float, float], int] = {}
    for pos in cm_positions:
        counts[pos] = counts.get(pos, 0) + 1
    repeated = sorted(((n, pos) for pos, n in counts.items() if n > 1), reverse=True)
    if repeated:
        print("Repeated cm placements (count, (tx,ty)):")
        for n, (tx, ty) in repeated[:30]:
            print(f"  {n:3d}  ({tx:8.2f},{ty:8.2f})")

    print(f"Found {len(matches)} text draws")
    # Print a focused subset first (list-ish content)
    focus = [
        "66",
        "10(10-17)",
        "18(18-23)",
        "24",
        "First",
        "Second",
        "1.",
        "2.",
        "3.",
    ]

    printed = 0
    for abs_y, abs_x, cm_y, cm_x, txt in matches:
        if any(k in txt for k in focus):
            print(f"abs=({abs_x:8.2f},{abs_y:8.2f}) cm=({cm_x:8.2f},{cm_y:8.2f}) tm=(?,?) {txt}")
            printed += 1
            if printed >= 120:
                break

    if printed == 0:
        print("(No focused matches; printing first 50 draws)")
        for abs_y, abs_x, cm_y, cm_x, txt in matches[:50]:
            print(f"abs=({abs_x:8.2f},{abs_y:8.2f}) cm=({cm_x:8.2f},{cm_y:8.2f}) {txt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
