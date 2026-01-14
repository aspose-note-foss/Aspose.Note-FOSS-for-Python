from __future__ import annotations

import argparse
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aspose.note._internal.onestore.parse_context import ParseContext
from aspose.note._internal.onestore.summary import build_simpletable_summary


def main() -> int:
    p = argparse.ArgumentParser(description="Dump deterministic SimpleTable.one summary as JSON")
    p.add_argument("path", nargs="?", default=str(ROOT / "SimpleTable.one"))
    p.add_argument("--tolerant", action="store_true", help="Use tolerant mode (strict=False)")
    args = p.parse_args()

    path = Path(args.path)
    data = path.read_bytes()

    ctx = ParseContext(strict=not args.tolerant, file_size=len(data), path=str(path))
    summary = build_simpletable_summary(data, ctx=ctx)
    print(summary.to_json(indent=2), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
