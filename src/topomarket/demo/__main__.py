"""Command-line entry point for the deterministic demo data generator."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .generator import DEFAULT_SEED, generate_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m topomarket.demo",
        description="Generate the deterministic synthetic demo tables.",
    )
    parser.add_argument(
        "--out",
        "--output",
        "--out-dir",
        dest="out",
        required=True,
        type=Path,
        help="Directory that receives the generated CSV files and manifest.json.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Deterministic seed.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON summary.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = generate_demo(args.out, seed=args.seed)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        files = [entry["path"] for entry in manifest["files"]]
        print(f"Generated demo data in {args.out} (seed={args.seed})")
        print(f"Tables: {', '.join(manifest['tables'])}")
        print(f"Files: {', '.join(files)}")
        print(f"Rows: {manifest['row_count']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
