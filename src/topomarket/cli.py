"""Command-line interface for TopoMarket."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from topomarket import __version__
from topomarket.data import generate_synthetic, load_demo_markets
from topomarket.profiles import PROFILE_NAMES, load_profile


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser used by all entry points."""

    parser = argparse.ArgumentParser(
        prog="topomarket",
        description="Topology-aware market research toolkit.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser(
        "demo",
        help="Run the bundled synthetic demo profile.",
        description="Run the bundled synthetic demo profile (no private data needed).",
    )
    demo.add_argument(
        "--json",
        action="store_true",
        help="Emit the demo summary as JSON.",
    )

    info = subparsers.add_parser(
        "info",
        help="Show the resolved configuration for a profile.",
    )
    info.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="demo",
        help="Profile to inspect (default: demo).",
    )

    validate = subparsers.add_parser(
        "validate",
        help="Validate a profile configuration file.",
    )
    validate.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="demo",
        help="Profile to validate (default: demo).",
    )

    synthetic = subparsers.add_parser(
        "synthetic",
        help="Generate deterministic synthetic CSV data and a manifest.",
        description=(
            "Generate deterministic synthetic CSV data plus manifest.json. "
            "The same seed always produces byte-identical files."
        ),
    )
    synthetic.add_argument(
        "--out",
        "--output",
        "--out-dir",
        dest="out",
        required=True,
        type=Path,
        help="Directory that receives the generated CSV files and manifest.json.",
    )
    synthetic.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed (default: 42).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the TopoMarket CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "demo":
            return _run_demo(emit_json=args.json)
        if args.command == "info":
            return _show_info(args.profile)
        if args.command == "validate":
            return _validate(args.profile)
        if args.command == "synthetic":
            return _generate_synthetic(args.out, seed=args.seed)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_demo(emit_json: bool = False) -> int:
    profile = load_profile("demo")
    markets = load_demo_markets()
    summary = {
        "profile": profile.profile,
        "data_source": profile.data_source,
        "market_count": len(markets),
        "markets": [market.get("id", "unknown") for market in markets],
    }
    if emit_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"TopoMarket demo ({profile.data_source} data)")
        print(f"Markets: {', '.join(summary['markets'])}")
        print(f"Total markets: {summary['market_count']}")
    return 0


def _show_info(profile_name: str) -> int:
    profile = load_profile(profile_name)
    print(json.dumps(profile.as_dict(), indent=2, sort_keys=True))
    return 0


def _validate(profile_name: str) -> int:
    profile = load_profile(profile_name)
    if profile.is_private:
        print(
            "Profile 'private' is valid. Supply private data locally; "
            "it is not included in this repository."
        )
    else:
        print(f"Profile '{profile.profile}' is valid.")
    return 0


def _generate_synthetic(out: Path, *, seed: int = 42) -> int:
    manifest = generate_synthetic(out, seed=seed)
    files = [entry["path"] for entry in manifest["files"]]
    print(f"Generated synthetic data in {out} (seed={seed})")
    print(f"Files: {', '.join(files)}")
    print(f"Rows: {manifest['row_count']}")
    return 0


def run(config_path: Path | None = None) -> int:
    """Compatibility hook for embedders that used ``run()`` as an entry point."""

    del config_path
    return main()


__all__ = ["build_parser", "main", "run"]
