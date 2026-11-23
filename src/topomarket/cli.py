"""Command-line interface for TopoMarket."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from topomarket import __version__
from topomarket.analysis import (
    IndustryAnalysisError,
    industry_explorer_payload,
)
from topomarket.data import (
    SOURCE_ID_ALIASES,
    SOURCE_IDS,
    import_sources,
)
from topomarket.data.refresh import (
    DEFAULT_REFRESH_SOURCES,
    RefreshBusyError,
    RefreshError,
    active_snapshot_id,
    load_refresh_status,
    refresh_sources,
    resolve_active_data_dir,
)
from topomarket.data.refresh import resolve_active_data_dir as _resolve_snapshot_dir
from topomarket.demo import DEMO_FILE_NAMES, demo_tables, generate_demo
from topomarket.profiles import PROFILE_NAMES, load_profile
from topomarket.report import (
    build_data_report,
    format_data_report,
    has_import_artifacts,
    validate_data_directory,
)
from topomarket.topology import (
    ScoreError,
    compute_topology_scores,
    load_daily_rows,
    load_topology_config,
    write_scores_csv,
)


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

    import_command = subparsers.add_parser(
        "import",
        help="Import local seed files from a directory or zip archive.",
        description=(
            "Import local seed CSV files from a directory or zip archive and "
            "write normalised tables, the raw hash registry and parser reports. "
            "No network access is performed."
        ),
    )
    source = import_command.add_mutually_exclusive_group()
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
    import_command.add_argument(
        "--input",
        "--input-path",
        dest="input_path",
        type=Path,
        help="Single input file or archive (alternative to --input-dir/--input-zip).",
    )
    import_command.add_argument(
        "--output-dir",
        "--out",
        "--output",
        "--data-dir",
        dest="output_dir",
        type=Path,
        help=(
            "Directory that receives the imported tables, registry and reports "
            "(default: the profile's output directory)."
        ),
    )
    import_command.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="demo",
        help="Profile whose output directory is used when --output-dir is omitted.",
    )
    import_command.add_argument(
        "--registry",
        type=Path,
        help="Override the raw hash registry path.",
    )
    import_command.add_argument(
        "--reports",
        type=Path,
        help="Override the parser reports path.",
    )
    import_command.add_argument(
        "--require",
        action="append",
        default=[],
        choices=(*SOURCE_IDS, *sorted(SOURCE_ID_ALIASES)),
        help="Require a source id or provider alias to be present (repeatable).",
    )
    import_command.add_argument(
        "--strict",
        action="store_true",
        help="Treat unrecognised or unparseable files as errors.",
    )
    import_command.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable import summary.",
    )

    refresh = subparsers.add_parser(
        "refresh",
        help="Refresh fixed provider sources and publish an atomic snapshot.",
        description=(
            "Fetch the fixed HTTPS provider sources with conditional GET, validate and "
            "merge them, and publish a new immutable snapshot atomically. A failed "
            "refresh keeps the last good snapshot active."
        ),
    )
    refresh.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Local data directory to refresh (created if missing).",
    )
    refresh.add_argument(
        "--sources",
        default=",".join(DEFAULT_REFRESH_SOURCES),
        help="Comma-separated source ids (default: all four providers).",
    )
    refresh.add_argument("--json", action="store_true", help="Emit a JSON report.")

    release_check = subparsers.add_parser(
        "release-check",
        help="Run the offline public-release checks.",
        description=(
            "Verify version consistency, repository hygiene, packaged resources, the dependency "
            "lock, synthetic fixture determinism and the offline public smoke commands."
        ),
    )
    release_check.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    release_check.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip fixture regeneration and CLI/app smoke commands.",
    )
    release_check.add_argument("--root", type=Path, default=None, help="Repository root.")

    sources = subparsers.add_parser(
        "sources",
        help="Show per-source freshness and last refresh outcomes.",
        description=(
            "Show the active snapshot and the last attempt/success for every provider "
            "source recorded by topomarket refresh."
        ),
    )
    sources.add_argument("--data-dir", type=Path, required=True)
    sources.add_argument("--json", action="store_true", help="Emit JSON.")

    topology = subparsers.add_parser(
        "topology",
        help="Compute the causal daily topological anomaly score.",
        description=(
            "Compute the causally valid daily delay-embedding/Vietoris-Rips score "
            "series from the active snapshot's tda_daily table. Custom configs are "
            "flagged exploratory; the frozen default comes from config/topology.json."
        ),
    )
    topology.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Data directory or snapshot directory containing normalized/tda_daily.csv.",
    )
    topology.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Exploratory topology configuration JSON file (default: frozen config).",
    )
    topology.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the deterministic score CSV (plus metadata sidecar) to this path.",
    )
    topology.add_argument("--json", action="store_true", help="Emit the full series as JSON.")

    industry = subparsers.add_parser(
        "industries",
        aliases=["industry"],
        help="Build the industry cloud and Mapper graph for one as-of window.",
        description=(
            "Build the robust 60-session industry cloud/PCA/persistence result and "
            "the correlation-distance Mapper graph from the active snapshot's "
            "tda_daily table. With no --date the latest complete window is used."
        ),
    )
    industry.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Data directory or snapshot directory containing normalized/tda_daily.csv.",
    )
    industry.add_argument(
        "--date",
        "--as-of",
        "--asof",
        dest="as_of",
        default=None,
        help="Explicit window end date (ISO-8601); default: latest complete window.",
    )
    industry.add_argument(
        "--out",
        "--output",
        dest="out",
        type=Path,
        default=None,
        help="Write the deterministic combined JSON payload to this path.",
    )
    industry.add_argument(
        "--json",
        action="store_true",
        help="Emit the combined cloud and Mapper payload as JSON.",
    )

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Run the chronological evaluation and warning-evidence report.",
        description=(
            "Calibrate TDA/VIX/realized-volatility alert policies on 2005-2013, freeze the "
            "cutoffs, evaluate the 2014+ out-of-sample period with paired moving-block "
            "bootstrap and evidence wording, and optionally append a private ledger."
        ),
    )
    evaluate.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Data or snapshot directory containing normalized/tda_daily.csv.",
    )
    evaluate.add_argument("--json", action="store_true", help="Emit the full report as JSON.")
    evaluate.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="Write the deterministic report JSON to this path.",
    )
    evaluate.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="Append-only private ledger path (outside the repository checkout).",
    )
    evaluate.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Bootstrap/control seed (default: 42).",
    )
    evaluate.add_argument(
        "--ablations",
        action="store_true",
        help="Include the return-shuffled and unscaled-topology control rows (slower).",
    )

    report = subparsers.add_parser(
        "report",
        help="Show per-source rows, date ranges, warnings and the active snapshot id.",
        description=(
            "Show per-source row counts, observation ranges, warnings and the "
            "active snapshot id for a local data directory or profile."
        ),
    )
    report.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="demo",
        help="Profile whose data directory is inspected (default: demo).",
    )
    report.add_argument(
        "--data-dir",
        type=Path,
        help="Local data directory to report on instead of the profile default.",
    )
    report.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON.",
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
            return _show_status(args.profile, data_dir=args.data_dir, emit_json=args.json)
        if args.command == "report":
            return _show_report(args.profile, data_dir=args.data_dir, emit_json=args.json)
        if args.command == "import":
            return _import_seed_data(
                input_dir=args.input_dir,
                input_zip=args.input_zip,
                input_path=args.input_path,
                output_dir=args.output_dir,
                profile_name=args.profile,
                registry_path=args.registry,
                reports_path=args.reports,
                require=args.require,
                strict=args.strict,
                emit_json=args.json,
            )
        if args.command == "validate":
            return _validate(args.profile, data_dir=args.data_dir)
        if args.command == "refresh":
            return _run_refresh(
                data_dir=args.data_dir,
                sources=args.sources,
                emit_json=args.json,
            )
        if args.command == "sources":
            return _show_sources(data_dir=args.data_dir, emit_json=args.json)
        if args.command == "release-check":
            return _run_release_check(
                root=args.root,
                emit_json=args.json,
                skip_smoke=args.skip_smoke,
            )
        if args.command == "topology":
            return _run_topology(
                data_dir=args.data_dir,
                config_path=args.config,
                out=args.out,
                emit_json=args.json,
            )
        if args.command == "evaluate":
            return _run_evaluation(
                data_dir=args.data_dir,
                emit_json=args.json,
                report_out=args.report_out,
                ledger=args.ledger,
                seed=args.seed,
                ablations=args.ablations,
            )
        if args.command in ("industries", "industry"):
            return _run_industry(
                data_dir=args.data_dir,
                as_of=args.as_of,
                out=args.out,
                emit_json=args.json,
            )
        if args.command == "synthetic":
            return _generate_synthetic(args.out, seed=args.seed)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_demo(emit_json: bool = False) -> int:
    profile = load_profile("demo")
    tables = demo_tables()
    row_counts = {
        str(name): int(getattr(dataset, "row_count", len(dataset)))
        for name, dataset in tables.items()
    }
    summary = {
        "profile": profile.profile,
        "data_source": profile.data_source,
        "synthetic": True,
        "table_count": len(row_counts),
        "tables": sorted(row_counts),
        "row_counts": row_counts,
        "total_rows": sum(row_counts.values()),
    }
    if emit_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"TopoMarket demo ({profile.data_source} data)")
        print(f"Tables: {', '.join(sorted(row_counts))}")
        print(f"Total rows: {summary['total_rows']}")
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
    target = resolve_active_data_dir(profile.data_dir)
    report = build_data_report(
        target,
        profile=profile.profile,
        data_source=profile.data_source,
    )
    report["active_data_dir"] = str(target)
    report["active_snapshot_id"] = active_snapshot_id(profile.data_dir)
    if emit_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print(format_data_report(report))
    return 0


def _show_report(
    profile_name: str,
    *,
    data_dir: Path | None = None,
    emit_json: bool = False,
) -> int:
    """Print per-source rows, ranges, warnings and the active snapshot id."""

    if data_dir is not None:
        profile = load_profile(profile_name, data_dir=data_dir)
        target = profile.data_dir
    else:
        profile = load_profile(profile_name)
        # ``import`` defaults to the profile output directory, so report on it
        # when it actually contains imported data and otherwise keep the
        # profile's configured data directory.
        target = (
            profile.output_dir if has_import_artifacts(profile.output_dir) else profile.data_dir
        )

    target = resolve_active_data_dir(target)
    report = build_data_report(
        target,
        profile=profile.profile,
        data_source=profile.data_source,
    )
    report["active_data_dir"] = str(target)
    report["active_snapshot_id"] = active_snapshot_id(Path(data_dir) if data_dir else target)
    if emit_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print(format_data_report(report))
    return 0


def _import_seed_data(
    *,
    input_dir: Path | None,
    input_zip: Path | None,
    input_path: Path | None,
    output_dir: Path | None,
    profile_name: str,
    registry_path: Path | None,
    reports_path: Path | None,
    require: Sequence[str],
    strict: bool,
    emit_json: bool,
) -> int:
    """Import local seed files and write the normalised data artefacts."""

    supplied = [value is not None for value in (input_dir, input_zip, input_path)]
    if not any(supplied):
        print(
            "error: one of --input-dir, --input-zip or --input is required",
            file=sys.stderr,
        )
        return 2
    if sum(supplied) > 1:
        print(
            "error: pass only one of --input-dir, --input-zip or --input",
            file=sys.stderr,
        )
        return 2

    if output_dir is None:
        output_dir = load_profile(profile_name).output_dir

    result = import_sources(
        input_dir,
        output_dir,
        input_zip=input_zip,
        input_path=input_path,
        registry_path=registry_path,
        reports_path=reports_path,
        strict=strict,
        require=require,
        write=True,
    )

    if not result.tables:
        print("error: no seed files were recognised", file=sys.stderr)
        return 2

    report = build_data_report(result.output_dir) if result.output_dir else {}
    snapshot_id = report.get("snapshot_id") if report else None

    if emit_json:
        payload = {
            "source_ids": list(result.source_ids),
            "row_counts": dict(result.row_counts),
            "reports": {
                source_id: dict(report_item) for source_id, report_item in result.reports.items()
            },
            "registry_entries": len(result.registry.entries),
            "warnings": list(result.warnings),
            "errors": dict(result.errors),
            "missing_sources": list(result.missing_sources),
            "output_dir": str(result.output_dir) if result.output_dir is not None else None,
            "files": result.written,
            "snapshot_id": snapshot_id,
            "active_snapshot_id": snapshot_id,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"Imported {len(result.tables)} source(s) from {len(result.sources)} file(s).")
    for source_id, dataset in result.tables.items():
        parser_report = result.reports.get(source_id) or {}
        first = parser_report.get("first_observation")
        last = parser_report.get("last_observation")
        print(f"  {source_id}: {dataset.row_count} rows (range: {first} .. {last})")
    print(f"Raw hash registry entries: {len(result.registry.entries)}")
    if result.output_dir is not None:
        print(f"Output directory: {result.output_dir}")
        print(f"Registry: {result.written.get('registry')}")
        print(f"Parser reports: {result.written.get('reports')}")
        print(f"Import manifest: {result.written.get('manifest')}")
    if snapshot_id:
        print(f"Active snapshot id: {snapshot_id}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for source_id, message in result.errors.items():
        print(f"error: {source_id}: {message}", file=sys.stderr)
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
    requested = Path(data_dir).expanduser()
    snapshot_id = active_snapshot_id(requested)
    target = resolve_active_data_dir(requested)
    if snapshot_id is not None:
        snapshot_manifest = target / "refresh_manifest.json"
        if not snapshot_manifest.is_file():
            print(
                f"error: active snapshot {snapshot_id} is missing refresh_manifest.json",
                file=sys.stderr,
            )
            return 2
        payload = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
        if payload.get("snapshot_id") != target.name:
            print(
                "error: active snapshot manifest id does not match the snapshot directory",
                file=sys.stderr,
            )
            return 2
    validation = validate_data_directory(target)
    if not validation["valid"]:
        for problem in validation["problems"]:
            print(f"error: {problem}", file=sys.stderr)
        return 2

    report = validation["report"] or {}
    print(f"Data directory '{target}' is valid.")
    if snapshot_id is not None:
        print(f"Active snapshot: {snapshot_id}")
    if report.get("snapshot_id"):
        print(f"Snapshot id: {report['snapshot_id']}")
    print(f"Snapshots: {report.get('snapshot_count', 0)}")
    if report.get("latest_data_date") is not None:
        print(f"Latest data date: {report['latest_data_date']}")

    sources = report.get("sources") or {}
    if sources:
        print(f"Imported sources: {len(sources)}")
        print(f"Rows: {report.get('total_rows', 0)}")
        for source_id, source in sources.items():
            first = source.get("first_observation")
            last = source.get("last_observation")
            print(f"  {source_id}: {source.get('row_count', 0)} rows (range: {first} .. {last})")
    warnings = report.get("warnings") or []
    if warnings:
        print(f"Warnings: {len(warnings)}")
    elif report.get("imported"):
        print("Warnings: none")
    return 0


def _run_refresh(*, data_dir: Path, sources: str, emit_json: bool) -> int:
    """Refresh fixed provider sources and publish an atomic snapshot."""

    requested = [item.strip() for item in sources.split(",") if item.strip()]
    try:
        report = refresh_sources(Path(data_dir).expanduser(), source_ids=requested)
    except (RefreshError, RefreshBusyError) as exc:
        print(f"error: refresh failed: {exc}", file=sys.stderr)
        return 2
    if emit_json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        return 0
    print(f"Active snapshot: {report.active_snapshot_id or 'none'}")
    if report.published:
        print(f"Published snapshot: {report.new_snapshot_id}")
    else:
        print("Snapshot unchanged (no new data accepted)")
    print(f"Latest data date: {report.latest_data_date or 'none'}")
    print(f"Revisions: {len(report.revisions)}")
    for status in report.sources:
        detail = f"HTTP {status.http_status}" if status.http_status else (status.error or "")
        print(f"  {status.source_id}: {status.outcome} {detail}".rstrip())
    for warning in report.warnings:
        print(f"Warning: {warning}")
    return 0


def _show_sources(*, data_dir: Path, emit_json: bool) -> int:
    """Show per-source freshness recorded by the last refresh."""

    requested = Path(data_dir).expanduser()
    status = load_refresh_status(requested)
    payload = {
        "active_snapshot_id": active_snapshot_id(requested),
        "updated_at_utc": status.get("updated_at_utc"),
        "published": status.get("published"),
        "error": status.get("error"),
        "warnings": status.get("warnings") or [],
        "sources": status.get("sources") or {},
    }
    if emit_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(f"Active snapshot: {payload['active_snapshot_id'] or 'none'}")
    print(f"Last refresh: {payload['updated_at_utc'] or 'never'}")
    if payload["error"]:
        print(f"Last error: {payload['error']}")
    for source_id, source in sorted(payload["sources"].items()):
        outcome = source.get("outcome", "unknown")
        attempted = source.get("last_attempt_at") or "never"
        succeeded = source.get("last_success_at") or "never"
        http_status = source.get("http_status")
        http = f" HTTP {http_status}" if http_status else ""
        error = f" ({source.get('error')})" if source.get("error") else ""
        print(
            f"  {source_id}: {outcome}{http}; last attempt {attempted}; "
            f"last success {succeeded}{error}"
        )
    return 0


def _run_industry(
    *,
    data_dir: Path,
    as_of: str | None,
    out: Path | None,
    emit_json: bool,
) -> int:
    """Build the industry cloud and Mapper graph from the active snapshot."""

    requested = Path(data_dir).expanduser()
    target = _resolve_snapshot_dir(requested)
    try:
        rows = load_daily_rows(target)
    except ScoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        payload = industry_explorer_payload(rows, as_of=as_of)
    except (IndustryAnalysisError, ScoreError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    snapshot_id = active_snapshot_id(requested)
    payload["command"] = "industries"
    payload["data_dir"] = str(target)
    payload["active_data_dir"] = str(target)
    payload["active_snapshot_id"] = snapshot_id
    payload["snapshot_id"] = snapshot_id

    serialised = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if out is not None:
        destination = Path(out).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialised)

    if emit_json:
        sys.stdout.write(serialised)
        return 0

    print(f"Data directory: {target}")
    print(f"Active snapshot: {snapshot_id or 'none'}")
    print(f"As of: {payload['as_of']}")
    print(f"Window: {payload['start_date']} .. {payload['end_date']}")
    print(f"Window sessions: {payload['window_sessions']}")
    print(f"Industries: {len(payload['industry_columns'])}")
    print(f"PCA components: {len(payload['cloud']['pca_labels'])}")
    print(f"Nodes: {payload['node_count']}")
    print(f"Edges: {payload['edge_count']}")
    print(f"Intervals: {payload['interval_count']}")
    if out is not None:
        print(f"Wrote: {Path(out).expanduser()}")
    return 0


def _run_topology(
    *,
    data_dir: Path,
    config_path: Path | None,
    out: Path | None,
    emit_json: bool,
) -> int:
    """Compute the default or exploratory daily topology score series."""

    requested = Path(data_dir).expanduser()
    target = _resolve_snapshot_dir(requested)
    if config_path is not None:
        config = load_topology_config(config_path=Path(config_path).expanduser(), allow_custom=True)
    else:
        config = load_topology_config()
    try:
        rows = load_daily_rows(target)
    except ScoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    series = compute_topology_scores(rows, config)
    if out is not None:
        write_scores_csv(series, Path(out).expanduser())
    if emit_json:
        print(json.dumps(series.as_dict(), indent=2, sort_keys=True))
        return 0
    print(f"Data directory: {target}")
    print(f"Config hash: {series.config_hash}")
    print(f"Exploratory: {series.exploratory}")
    print(f"Cache key: {series.cache_key}")
    print(f"Rows: {len(series.points)}")
    print(f"Scored: {series.scored_count}")
    print(f"Warming up: {series.warmup_count}")
    print(f"Unavailable: {series.unavailable_count}")
    if series.first_scored_date:
        print(f"First scored date: {series.first_scored_date}")
    if series.latest_date:
        latest = f"{series.latest_date} score={series.latest_score}"
        print(f"Latest: {latest}")
    if out is not None:
        print(f"Wrote: {Path(out).expanduser()}")
    return 0


def _run_evaluation(
    *,
    data_dir: Path,
    emit_json: bool,
    report_out: Path | None,
    ledger: Path | None,
    seed: int,
    ablations: bool,
) -> int:
    """Run the Step 6 chronological evaluation pipeline."""

    from topomarket.analysis.evaluation import (
        build_evaluation_report,
        write_evaluation_report,
    )
    from topomarket.analysis.ledger import ledger_digest
    from topomarket.data.refresh import active_snapshot_id
    from topomarket.topology import compute_topology_scores, load_topology_config

    requested = Path(data_dir).expanduser()
    target = _resolve_snapshot_dir(requested)
    rows = load_daily_rows(target)
    config = load_topology_config()
    series = compute_topology_scores(rows, config)
    report = build_evaluation_report(
        rows,
        score_series=series,
        config_hash=str(config.config_hash),
        snapshot_id=active_snapshot_id(requested) or "",
        seed=seed,
        include_ablations=ablations,
        ledger_path=Path(ledger).expanduser() if ledger is not None else None,
        ledger_snapshot_id=active_snapshot_id(requested) or "",
    )
    if report_out is not None:
        write_evaluation_report(report, Path(report_out).expanduser())
    if emit_json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0

    primary = report["primary_method"]
    print(f"Data directory: {target}")
    print(f"Snapshot: {report.get('snapshot_id') or 'unknown'}")
    print(f"Rows: {report['row_count']} ({report['data_start']} .. {report['data_end']})")
    print(f"Episodes: {report['episode_count']} (resolved {report['resolved_episode_count']})")
    print(f"Primary method: {primary} | comparator: {report['comparator_method']}")
    print(f"Wording: {report['evidence']['wording']}")
    for method, method_metrics in report["metrics"].items():
        print(
            f"  {method}: recall={method_metrics['episode_recall']} "
            f"false/year={method_metrics['false_alerts_per_year']} "
            f"AP={method_metrics['average_precision']} "
            f"lead={method_metrics['median_lead_sessions']}"
        )
    gain = report["bootstrap"]["episode_recall_gain"]
    print(
        "Recall gain 95% interval: "
        f"[{gain['lower']}, {gain['upper']}] valid={gain['valid_replicates']}"
    )
    if report.get("ledger"):
        print(
            f"Ledger: {report['ledger']['path']} (+{report['ledger']['appended_records']} records)"
        )
        if report.get("snapshot_id"):
            print(f"Ledger digest: {ledger_digest(Path(report['ledger']['path']))[:16]}")
    if report_out is not None:
        print(f"Report: {Path(report_out).expanduser()}")
    return 0


def _run_release_check(*, root: Path | None, emit_json: bool, skip_smoke: bool) -> int:
    """Run the Step 8 release checks."""

    from topomarket.release import ReleaseCheckError, run_release_check

    try:
        report = run_release_check(root, skip_smoke=skip_smoke)
    except ReleaseCheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if emit_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Release checks for TopoMarket {report['package_version']}")
        for check in report["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  [{status}] {check['name']}")
            for problem in check.get("details", {}).get("problems") or ():
                print(f"    - {problem}")
        print("Release checks passed." if report["passed"] else "Release checks failed.")
    return 0 if report["passed"] else 2


def _generate_synthetic(out: Path, *, seed: int = 42) -> int:
    manifest = generate_demo(out, seed=seed)
    files = sorted(manifest.get("file_hashes", {}))
    rows = int(manifest.get("total_rows") or manifest.get("row_count") or 0)
    print(f"Generated synthetic data in {out} (seed={seed})")
    print(f"Tables: {', '.join(DEMO_FILE_NAMES)}")
    print(f"Files: {', '.join(files)}")
    print(f"Rows: {rows}")
    return 0


def run(config_path: Path | None = None) -> int:
    """Compatibility hook for embedders that used ``run()`` as an entry point."""

    del config_path
    return main()


__all__ = ["build_parser", "main", "run"]
