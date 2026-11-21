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
from topomarket.ui.overview import inspect_data_directory


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
        help="Validate a profile configuration or a local data directory.",
        description=(
            "Validate a profile configuration file, or the manifest and "
            "snapshots of a local data directory when --data-dir is given."
        ),
    )
    validate.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="demo",
        help="Profile configuration to validate (default: demo).",
    )
    validate.add_argument(
        "--data-dir",
        type=Path,
        help="Local data directory to validate instead of a profile.",
    )

    status = subparsers.add_parser(
        "status",
        help="Show the data status for a profile or local data directory.",
        description=(
            "Show the resolved profile, its data source, manifest validity, "
            "snapshot count, and latest data date."
        ),
    )
    status.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="demo",
        help="Profile whose data directory should be inspected (default: demo).",
    )
    status.add_argument(
        "--data-dir",
        type=Path,
        help="Local data directory to inspect instead of the profile default.",
    )
    status.add_argument(
        "--json",
        action="store_true",
        help="Emit the status as JSON.",
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
        if args.command == "status":
            return _show_status(
                args.profile, data_dir=args.data_dir, emit_json=args.json
            )
        if args.command == "validate":
            return _validate(args.profile, data_dir=args.data_dir)
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


def _show_status(
    profile_name: str,
    *,
    data_dir: Path | None = None,
    emit_json: bool = False,
) -> int:
    """Print the data status for ``profile_name`` or an explicit directory."""

    profile = load_profile(profile_name, data_dir=data_dir)
    status = inspect_data_directory(profile.data_dir)
    payload = {
        "profile": profile.profile,
        "data_source": profile.data_source,
        "data_dir": str(profile.data_dir),
        "data_available": status["data_available"],
        "manifest_present": status["manifest_present"],
        "manifest_valid": status["manifest_valid"],
        "manifest_error": status["manifest_error"],
        "snapshot_count": status["snapshot_count"],
        "latest_data_date": status["latest_data_date"],
    }
    if emit_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"Profile: {profile.profile}")
    print(f"Data source: {profile.data_source}")
    print(f"Data directory: {profile.data_dir}")
    if not status["exists"]:
        print("Data status: missing")
        print("Latest data date: none")
        print("No data available yet.")
        return 0

    if status["manifest_present"]:
        if status["manifest_valid"]:
            print("Manifest: valid")
        else:
            print(f"Manifest: invalid ({status['manifest_error']})")
    else:
        print("Manifest: not found")
    print(f"Snapshots: {status['snapshot_count']}")
    if status["latest_data_date"] is not None:
        print(f"Latest data date: {status['latest_data_date']}")
    else:
        print("Latest data date: none")
    if not status["data_available"]:
        print("No data available yet.")
    return 0


def _validate(profile_name: str, *, data_dir: Path | None = None) -> int:
    if data_dir is not None:
        return _validate_data_dir(data_dir)

    profile = load_profile(profile_name)
    if profile.is_private:
        print(
            "Profile 'private' is valid. Supply private data locally; "
            "it is not included in this repository."
        )
    else:
        print(f"Profile '{profile.profile}' is valid.")
    return 0


def _validate_data_dir(data_dir: Path) -> int:
    target = Path(data_dir).expanduser()
    if not target.exists():
        print(f"error: data directory does not exist: {target}", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"error: data path is not a directory: {target}", file=sys.stderr)
        return 2

    status = inspect_data_directory(target)
    if status["manifest_present"] and not status["manifest_valid"]:
        print(
            f"error: invalid manifest in {target}: {status['manifest_error']}",
            file=sys.stderr,
        )
        return 2

    if status["manifest_valid"]:
        print(f"Data directory '{target}' is valid.")
        manifest = status["manifest"] or {}
        if manifest.get("snapshot_id"):
            print(f"Snapshot id: {manifest['snapshot_id']}")
        print(f"Snapshots: {status['snapshot_count']}")
        if status["latest_data_date"] is not None:
            print(f"Latest data date: {status['latest_data_date']}")
        return 0

    print(f"Data directory '{target}' is valid (no manifest found).")
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
