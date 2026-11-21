"""Command-line entry point for the local seed-file adapters."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .pipeline import (
    IMPORT_MANIFEST_FILENAME,
    PARSER_REPORTS_FILENAME,
    SOURCE_ID_ALIASES,
    SOURCE_IDS,
    import_sources,
)
from .registry import RAW_HASHES_FILENAME


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ``python -m topomarket.data.adapters``."""

    parser = argparse.ArgumentParser(
        prog="topomarket-data-adapters",
        description=(
            "Import local TopoMarket seed files from a directory or zip archive. "
            "No network access is performed."
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--input-dir",
        type=Path,
        help="Directory containing the supplied seed CSV files (searched recursively).",
    )
    source.add_argument(
        "--input-zip",
        type=Path,
        help="Zip archive containing the supplied seed CSV files.",
    )
    parser.add_argument(
        "--input",
        "--input-path",
        dest="input_path",
        type=Path,
        help="Single input file or archive (alternative to --input-dir/--input-zip).",
    )
    parser.add_argument(
        "--output-dir",
        "--out",
        "--output",
        dest="output_dir",
        type=Path,
        help="Directory that receives normalised tables, the hash registry and parser reports.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        help=f"Override the raw hash registry path (default: <output>/{RAW_HASHES_FILENAME}).",
    )
    parser.add_argument(
        "--reports",
        type=Path,
        help=f"Override the parser reports path (default: <output>/{PARSER_REPORTS_FILENAME}).",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        choices=(*SOURCE_IDS, *sorted(SOURCE_ID_ALIASES)),
        help="Require a source id or provider alias to be present (repeatable).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat unrecognised or unparseable files as errors.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable summary instead of text.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the adapter importer and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input_dir is None and args.input_zip is None and args.input_path is None:
        parser.error("one of --input-dir, --input-zip or --input is required")

    try:
        result = import_sources(
            args.input_dir,
            args.output_dir,
            input_zip=args.input_zip,
            input_path=args.input_path,
            registry_path=args.registry,
            reports_path=args.reports,
            strict=args.strict,
            require=args.require,
            write=args.output_dir is not None,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not result.tables:
        print("error: no seed files were recognised", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "source_ids": list(result.source_ids),
            "row_counts": {
                source_id: dataset.row_count for source_id, dataset in result.tables.items()
            },
            "reports": {
                source_id: {
                    "filename": report.get("filename"),
                    "row_count": report.get("row_count"),
                    "first_observation": report.get("first_observation"),
                    "last_observation": report.get("last_observation"),
                    "warnings": report.get("warnings", []),
                }
                for source_id, report in result.reports.items()
            },
            "registry_entries": len(result.registry.entries),
            "warnings": list(result.warnings),
            "errors": dict(result.errors),
            "missing_sources": list(result.missing_sources),
            "output_dir": str(result.output_dir) if result.output_dir is not None else None,
            "files": result.written,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"Imported {len(result.tables)} source(s) from {len(result.sources)} file(s).")
    for source_id, dataset in result.tables.items():
        report = result.reports.get(source_id)
        first = report.get("first_observation") if report else None
        last = report.get("last_observation") if report else None
        print(f"  {source_id}: {dataset.row_count} rows ({first} .. {last})")
    print(f"Raw hash registry entries: {len(result.registry.entries)}")
    if result.output_dir is not None:
        print(f"Output directory: {result.output_dir}")
        print(f"Registry: {result.written.get('registry')}")
        print(f"Parser reports: {result.written.get('reports')}")
        print(f"Import manifest: {result.written.get('manifest', IMPORT_MANIFEST_FILENAME)}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for source_id, message in result.errors.items():
        print(f"error: {source_id}: {message}", file=sys.stderr)
    return 0


run = main


__all__ = ["build_parser", "main", "run"]
