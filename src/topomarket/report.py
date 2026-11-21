"""Offline data status reports for local TopoMarket data directories.

The report is built only from files already present below the supplied data
directory.  It never performs network access, never reads credentials and
never touches private inputs outside that directory.

Two layouts are understood:

* imported seed data written by :func:`topomarket.data.adapters.import_sources`
  (``import_manifest.json``, ``parser_reports.json``, ``raw_hashes.json`` and
  the normalised CSV tables); and
* generated synthetic or snapshot data described by a ``manifest.json``.

The returned mapping intentionally exposes a small, stable vocabulary
(``row_counts``, ``ranges``, ``warnings``, ``snapshot_id``) together with the
raw report documents for callers that need more detail.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from topomarket.data import compute_snapshot_id
from topomarket.data.adapters import (
    IMPORT_MANIFEST_FILENAME,
    PARSER_REPORTS_FILENAME,
    RAW_HASHES_FILENAME,
)
from topomarket.ui.overview import inspect_data_directory

REPORT_SCHEMA_VERSION = 1
IMPORT_MANIFEST = IMPORT_MANIFEST_FILENAME
PARSER_REPORTS = PARSER_REPORTS_FILENAME
RAW_HASHES = RAW_HASHES_FILENAME

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_COLUMNS = ("date", "as_of", "as_of_date", "timestamp", "datetime", "time")
_MAX_CSV_ROWS = 200_000


def _as_int(value: Any) -> int | None:
    """Return ``value`` as a non-negative integer when possible."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalise_date(value: Any) -> str | None:
    """Return the first ISO ``YYYY-MM-DD`` date found in ``value``."""

    if value is None or isinstance(value, bool):
        return None
    match = _DATE_RE.search(str(value))
    return match.group(0) if match else None


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    """Read a JSON document, returning ``(payload, error)``."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"could not read {path.name}: {exc}"
    try:
        return json.loads(text), None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"invalid JSON in {path.name}: {exc}"


def _looks_like_report(value: Any) -> bool:
    """Whether ``value`` resembles a single parser report mapping."""

    return isinstance(value, Mapping) and bool(
        {"source_id", "row_count", "rows", "filename"} & set(value)
    )


def _report_mapping(payload: Any) -> dict[str, dict[str, Any]]:
    """Return ``{source_id: report}`` from a parser report document."""

    if not isinstance(payload, Mapping):
        return {}

    candidates: Any = payload.get("reports")
    if candidates is None:
        candidates = payload.get("report_list")
    if candidates is None:
        candidates = payload.get("by_source")
    if candidates is None:
        candidates = payload.get("reports_by_source")

    reports: dict[str, dict[str, Any]] = {}
    if isinstance(candidates, list):
        for entry in candidates:
            if not isinstance(entry, Mapping):
                continue
            source_id = str(entry.get("source_id") or entry.get("parser") or "")
            if source_id:
                reports[source_id] = dict(entry)
    elif isinstance(candidates, Mapping):
        for source_id, entry in candidates.items():
            if isinstance(entry, Mapping):
                reports[str(source_id)] = dict(entry)

    # Some hand-written documents place each report at the top level.
    if not reports:
        for key, entry in payload.items():
            if _looks_like_report(entry):
                reports[str(key)] = dict(entry)  # type: ignore[arg-type]
    return reports


def _source_reports(
    import_manifest: Any,
    parser_reports: Any,
) -> dict[str, dict[str, Any]]:
    """Merge per-source reports from both import documents."""

    merged = _report_mapping(parser_reports)
    merged.update(_report_mapping(import_manifest))
    return merged


def _csv_summary(path: Path) -> dict[str, Any]:
    """Return row count and date range for a CSV file."""

    summary: dict[str, Any] = {
        "row_count": 0,
        "first_observation": None,
        "last_observation": None,
    }
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                return summary

            indexes = [
                index
                for index, column in enumerate(header)
                if column.strip().lower() in _DATE_COLUMNS
            ]
            count = 0
            first: str | None = None
            last: str | None = None
            for row_number, row in enumerate(reader):
                if row_number >= _MAX_CSV_ROWS:
                    break
                count += 1
                for index in indexes:
                    if index >= len(row):
                        continue
                    candidate = _normalise_date(row[index])
                    if candidate is None:
                        continue
                    if first is None or candidate < first:
                        first = candidate
                    if last is None or candidate > last:
                        last = candidate
            summary["row_count"] = count
            summary["first_observation"] = first
            summary["last_observation"] = last
    except (OSError, UnicodeDecodeError, csv.Error):
        return summary
    return summary


def _table_paths(directory: Path, source_id: str) -> list[Path]:
    """Return plausible source CSV paths for ``source_id``."""

    candidates = [
        directory / f"{source_id}.csv",
        directory / "normalized" / f"{source_id}.csv",
    ]
    return [path for path in candidates if path.is_file()]


def _registry_entries(registry: Any) -> list[dict[str, Any]]:
    """Return normalised raw hash registry entries."""

    if isinstance(registry, Mapping):
        entries = registry.get("entries", registry.get("files", []))
    elif isinstance(registry, list):
        entries = registry
    else:
        entries = []
    return [dict(entry) for entry in entries if isinstance(entry, Mapping)]


def _dedupe(items: Iterable[str]) -> list[str]:
    """Return non-empty strings in first-seen order without duplicates."""

    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _active_snapshot_id(
    status: Mapping[str, Any],
    import_manifest: Any,
    parser_reports: Any,
) -> tuple[str | None, str | None]:
    """Return ``(snapshot_id, source)`` for the data directory."""

    latest = status.get("latest_snapshot")
    if isinstance(latest, Mapping):
        candidate = latest.get("snapshot_id")
        if candidate:
            return str(candidate), "snapshot"

    manifest = status.get("manifest")
    if isinstance(manifest, Mapping):
        candidate = manifest.get("snapshot_id")
        if candidate:
            return str(candidate), "manifest"

    if isinstance(import_manifest, Mapping):
        candidate = import_manifest.get("snapshot_id")
        if not candidate:
            candidate = compute_snapshot_id(import_manifest)
        return str(candidate), "import_manifest"

    if isinstance(parser_reports, Mapping):
        return compute_snapshot_id(parser_reports), "parser_reports"

    return None, None


def _range_entry(first: str | None, last: str | None) -> dict[str, str | None]:
    """Return a range mapping with the common key spellings."""

    return {"first": first, "last": last, "start": first, "end": last}


def _source_entry(
    source_id: str,
    *,
    source_name: str,
    row_count: int,
    first: str | None,
    last: str | None,
    warnings: list[str],
    columns: list[str],
    files: list[str],
) -> dict[str, Any]:
    """Build one per-source report entry."""

    return {
        "source_id": source_id,
        "source_name": source_name,
        "row_count": row_count,
        "rows": row_count,
        "first_observation": first,
        "last_observation": last,
        "first_date": first,
        "last_date": last,
        "first": first,
        "last": last,
        "date_range": [first, last],
        "range": {"start": first, "end": last},
        "warnings": warnings,
        "columns": columns,
        "files": files,
    }


def build_data_report(
    data_dir: Path | str,
    *,
    profile: str | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    """Build a complete status report for ``data_dir``.

    ``profile`` and ``data_source`` are optional labels supplied by the CLI;
    they never change which files are inspected.
    """

    directory = Path(data_dir).expanduser()
    status = inspect_data_directory(directory)

    import_manifest, import_error = _read_json(directory / IMPORT_MANIFEST_FILENAME)
    parser_reports, reports_error = _read_json(directory / PARSER_REPORTS_FILENAME)
    registry, registry_error = _read_json(directory / RAW_HASHES_FILENAME)

    artifact_errors = {
        name: error
        for name, error in (
            (IMPORT_MANIFEST_FILENAME, import_error),
            (PARSER_REPORTS_FILENAME, reports_error),
            (RAW_HASHES_FILENAME, registry_error),
        )
        if error
    }

    source_reports = _source_reports(import_manifest, parser_reports)

    row_counts: dict[str, int] = {}
    if isinstance(parser_reports, Mapping):
        raw_counts = parser_reports.get("row_counts")
        if isinstance(raw_counts, Mapping):
            for source_id, count in raw_counts.items():
                parsed = _as_int(count)
                if parsed is not None:
                    row_counts[str(source_id)] = parsed
    if isinstance(import_manifest, Mapping):
        raw_counts = import_manifest.get("row_counts")
        if isinstance(raw_counts, Mapping):
            for source_id, count in raw_counts.items():
                parsed = _as_int(count)
                if parsed is not None:
                    row_counts[str(source_id)] = parsed

    source_ids: list[str] = []
    if isinstance(import_manifest, Mapping):
        declared = import_manifest.get("source_ids")
        if isinstance(declared, list):
            source_ids.extend(str(source_id) for source_id in declared)
    source_ids.extend(row_counts)
    source_ids.extend(source_reports)
    source_ids = _dedupe(source_ids)

    normalized_counts: dict[str, int] = {}
    if isinstance(import_manifest, Mapping):
        raw_normalized = import_manifest.get("normalized_row_counts")
        if isinstance(raw_normalized, Mapping):
            for name, count in raw_normalized.items():
                parsed = _as_int(count)
                if parsed is not None:
                    normalized_counts[str(name)] = parsed

    entries = _registry_entries(registry)
    files_by_source: dict[str, list[str]] = {}
    for entry in entries:
        source_id = str(entry.get("source_id") or "unknown")
        filename = str(entry.get("filename") or entry.get("path") or "")
        if filename:
            files_by_source.setdefault(source_id, []).append(filename)

    sources: dict[str, dict[str, Any]] = {}
    ranges: dict[str, dict[str, str | None]] = {}
    warning_items: list[str] = []
    error_items: dict[str, str] = {}

    if isinstance(import_manifest, Mapping):
        raw_warnings = import_manifest.get("warnings")
        if isinstance(raw_warnings, list):
            warning_items.extend(str(warning) for warning in raw_warnings)
        raw_errors = import_manifest.get("errors")
        if isinstance(raw_errors, Mapping):
            for key, message in raw_errors.items():
                error_items[str(key)] = str(message)

    for source_id in source_ids:
        report = source_reports.get(source_id, {})
        # The aggregate row count wins over a per-file report because a source
        # may be split across several seed files.
        count = row_counts.get(source_id)
        if count is None:
            count = _as_int(report.get("row_count"))
        if count is None:
            count = _as_int(report.get("rows"))

        first = _normalise_date(
            report.get("first_observation")
            if report.get("first_observation") is not None
            else report.get("observation_start", report.get("first_date"))
        )
        last = _normalise_date(
            report.get("last_observation")
            if report.get("last_observation") is not None
            else report.get("observation_end", report.get("last_date"))
        )

        if count is None or first is None or last is None:
            for path in _table_paths(directory, source_id):
                summary = _csv_summary(path)
                if count is None:
                    count = summary["row_count"]
                if first is None:
                    first = summary["first_observation"]
                if last is None:
                    last = summary["last_observation"]
                break

        report_warnings: list[str] = []
        raw_report_warnings = report.get("warnings")
        if isinstance(raw_report_warnings, list):
            report_warnings.extend(str(warning) for warning in raw_report_warnings)
        elif raw_report_warnings:
            report_warnings.append(str(raw_report_warnings))
        warning_items.extend(report_warnings)

        columns = report.get("columns")
        if not isinstance(columns, list):
            columns = []

        resolved_count = count or 0
        row_counts[source_id] = resolved_count
        ranges[source_id] = _range_entry(first, last)
        sources[source_id] = _source_entry(
            source_id,
            source_name=str(report.get("source_name") or source_id),
            row_count=resolved_count,
            first=first,
            last=last,
            warnings=report_warnings,
            columns=[str(column) for column in columns],
            files=_dedupe(files_by_source.get(source_id, [])),
        )

    # Synthetic data stores row counts by filename rather than by source id.
    manifest = status.get("manifest")
    if not source_ids and isinstance(manifest, Mapping):
        manifest_counts = manifest.get("row_counts")
        if isinstance(manifest_counts, Mapping):
            for name, count in manifest_counts.items():
                parsed = _as_int(count)
                if parsed is None:
                    continue
                table_name = str(name)
                source_id = Path(table_name).stem or table_name
                if source_id in sources:
                    continue
                summary = _csv_summary(directory / table_name)
                first = summary["first_observation"]
                last = summary["last_observation"]
                row_counts[source_id] = parsed
                ranges[source_id] = _range_entry(first, last)
                sources[source_id] = _source_entry(
                    source_id,
                    source_name=table_name,
                    row_count=parsed,
                    first=first,
                    last=last,
                    warnings=[],
                    columns=[],
                    files=[table_name],
                )
            source_ids = list(sources)

    # Fall back to the CSV files themselves for hand-assembled directories
    # that have no import or synthetic manifest.
    if not source_ids:
        for path in sorted(directory.glob("*.csv")):
            if not path.is_file():
                continue
            source_id = path.stem
            summary = _csv_summary(path)
            count = summary["row_count"]
            first = summary["first_observation"]
            last = summary["last_observation"]
            row_counts[source_id] = count
            ranges[source_id] = _range_entry(first, last)
            sources[source_id] = _source_entry(
                source_id,
                source_name=path.name,
                row_count=count,
                first=first,
                last=last,
                warnings=[],
                columns=[],
                files=[path.name],
            )
        source_ids = list(sources)

    snapshot_id, snapshot_source = _active_snapshot_id(status, import_manifest, parser_reports)

    raw_manifest_warnings = status.get("manifest_error")
    if raw_manifest_warnings:
        warning_items.append(f"manifest: {raw_manifest_warnings}")

    imported = bool(
        import_manifest is not None
        or parser_reports is not None
        or registry is not None
        or (directory / "normalized").is_dir()
    )

    total_rows = sum(row_counts.values())
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "data_dir": str(directory),
        "path": str(directory),
        "profile": profile,
        "data_source": data_source,
        "exists": status["exists"],
        "is_dir": status["is_dir"],
        "imported": imported,
        "manifest_present": status["manifest_present"],
        "manifest_valid": status["manifest_valid"],
        "manifest_error": status["manifest_error"],
        "snapshot_count": status["snapshot_count"],
        "latest_snapshot": status["latest_snapshot"],
        "snapshot_id": snapshot_id,
        "active_snapshot_id": snapshot_id,
        "active_snapshot": snapshot_id,
        "snapshot_source": snapshot_source,
        "latest_data_date": status["latest_data_date"],
        "data_available": status["data_available"],
        "source_count": len(sources),
        "row_counts": row_counts,
        "rows": dict(row_counts),
        "source_rows": dict(row_counts),
        "total_rows": total_rows,
        "normalized_row_counts": normalized_counts,
        "ranges": ranges,
        "date_ranges": ranges,
        "sources": sources,
        "per_source": sources,
        "reports": source_reports,
        "warnings": _dedupe(warning_items),
        "errors": error_items,
        "artifact_errors": artifact_errors,
        "registry_entries": len(entries),
        "files": {
            "import_manifest": str(directory / IMPORT_MANIFEST_FILENAME)
            if (directory / IMPORT_MANIFEST_FILENAME).is_file()
            else None,
            "parser_reports": str(directory / PARSER_REPORTS_FILENAME)
            if (directory / PARSER_REPORTS_FILENAME).is_file()
            else None,
            "raw_hashes": str(directory / RAW_HASHES_FILENAME)
            if (directory / RAW_HASHES_FILENAME).is_file()
            else None,
        },
    }


def has_import_artifacts(data_dir: Path | str) -> bool:
    """Whether ``data_dir`` looks like an imported seed-data directory."""

    directory = Path(data_dir).expanduser()
    if not directory.is_dir():
        return False
    if (directory / IMPORT_MANIFEST_FILENAME).is_file():
        return True
    if (directory / PARSER_REPORTS_FILENAME).is_file():
        return True
    if (directory / RAW_HASHES_FILENAME).is_file():
        return True
    return (directory / "normalized").is_dir()


def _source_line(source_id: str, source: Mapping[str, Any]) -> str:
    """Format one per-source row count and date range."""

    count = source.get("row_count", 0)
    first = source.get("first_observation")
    last = source.get("last_observation")
    if first and last:
        span = f"{first} .. {last}"
    elif first:
        span = f"from {first}"
    elif last:
        span = f"until {last}"
    else:
        span = "no dated observations"
    return f"  {source_id}: {count} rows (range: {span})"


def format_data_report(report: Mapping[str, Any]) -> str:
    """Render a report mapping as plain text."""

    lines = [f"Data directory: {report.get('data_dir', '')}"]
    profile = report.get("profile")
    if profile:
        lines.append(f"Profile: {profile}")
    data_source = report.get("data_source")
    if data_source:
        lines.append(f"Data source: {data_source}")

    if not report.get("exists"):
        lines.append("Data status: missing")
        lines.append("Active snapshot id: none")
        lines.append("Latest data date: none")
        lines.append("No data available yet.")
        return "\n".join(lines)

    if report.get("manifest_present"):
        if report.get("manifest_valid"):
            lines.append("Manifest: valid")
        else:
            lines.append(f"Manifest: invalid ({report.get('manifest_error')})")
    else:
        lines.append("Manifest: not found")

    lines.append(f"Snapshots: {report.get('snapshot_count', 0)}")
    lines.append(f"Active snapshot id: {report.get('snapshot_id') or 'none'}")
    latest = report.get("latest_data_date")
    lines.append(f"Latest data date: {latest if latest is not None else 'none'}")

    sources = report.get("sources")
    if isinstance(sources, Mapping) and sources:
        lines.append(f"Imported sources: {len(sources)}")
        lines.append(f"Total rows: {report.get('total_rows', 0)}")
        lines.append("Per-source row counts and ranges:")
        for source_id, source in sources.items():
            if isinstance(source, Mapping):
                lines.append(_source_line(str(source_id), source))
    elif report.get("imported"):
        lines.append("Imported sources: 0")

    normalized_counts = report.get("normalized_row_counts")
    if isinstance(normalized_counts, Mapping) and normalized_counts:
        lines.append("Normalized tables:")
        for name, count in normalized_counts.items():
            lines.append(f"  {name}: {count} rows")

    warnings = report.get("warnings") or []
    if warnings:
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"  {warning}")
    else:
        lines.append("Warnings: none")

    errors = report.get("errors")
    if isinstance(errors, Mapping) and errors:
        lines.append("Errors:")
        for key, message in errors.items():
            lines.append(f"  {key}: {message}")

    if not report.get("data_available"):
        lines.append("No data available yet.")
    return "\n".join(lines)


def validate_data_directory(
    data_dir: Path | str,
    *,
    report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a data directory and its imported tables.

    Returns ``{"valid": bool, "problems": list[str], "report": mapping}``.
    """

    directory = Path(data_dir).expanduser()
    if not directory.exists():
        return {
            "valid": False,
            "problems": [f"data directory does not exist: {directory}"],
            "report": None,
        }
    if not directory.is_dir():
        return {
            "valid": False,
            "problems": [f"data path is not a directory: {directory}"],
            "report": None,
        }

    payload = dict(report) if report is not None else build_data_report(directory)
    problems: list[str] = []

    if payload.get("manifest_present") and not payload.get("manifest_valid"):
        problems.append(f"invalid manifest in {directory}: {payload.get('manifest_error')}")

    for name, message in (payload.get("artifact_errors") or {}).items():
        problems.append(f"invalid {name} in {directory}: {message}")

    import_manifest, import_error = _read_json(directory / IMPORT_MANIFEST_FILENAME)
    if import_error:
        problems.append(f"invalid {IMPORT_MANIFEST_FILENAME} in {directory}: {import_error}")
    elif isinstance(import_manifest, Mapping):
        recorded_snapshot = import_manifest.get("snapshot_id")
        if recorded_snapshot:
            expected = compute_snapshot_id(import_manifest)
            if recorded_snapshot != expected:
                problems.append(
                    "import manifest snapshot_id does not match its content "
                    f"(expected {expected}, found {recorded_snapshot})"
                )

        normalized_tables = import_manifest.get("normalized_tables")
        if isinstance(normalized_tables, list):
            for name in normalized_tables:
                table_name = str(name)
                primary = directory / f"{table_name}.csv"
                if not primary.is_file():
                    problems.append(f"missing imported table: {primary}")

        output_hashes = import_manifest.get("output_hashes")
        if isinstance(output_hashes, Mapping):
            from topomarket.data import sha256_file

            for relative, expected in output_hashes.items():
                path = directory / str(relative)
                if not path.is_file():
                    problems.append(f"missing imported file: {path}")
                    continue
                try:
                    actual = sha256_file(path)
                except OSError as exc:
                    problems.append(f"could not read imported file {path}: {exc}")
                    continue
                if actual != str(expected):
                    problems.append(f"imported file checksum mismatch: {path}")

    parser_reports, reports_error = _read_json(directory / PARSER_REPORTS_FILENAME)
    if reports_error:
        problems.append(f"invalid {PARSER_REPORTS_FILENAME} in {directory}: {reports_error}")
    elif isinstance(parser_reports, Mapping):
        report_mapping = _report_mapping(parser_reports)
        if parser_reports.get("reports") and not report_mapping:
            problems.append(f"no usable reports in {directory / PARSER_REPORTS_FILENAME}")
        for source_id, entry in report_mapping.items():
            if _as_int(entry.get("row_count")) is None and _as_int(entry.get("rows")) is None:
                problems.append(f"report for {source_id} is missing a row count")

    registry, registry_error = _read_json(directory / RAW_HASHES_FILENAME)
    if registry_error:
        problems.append(f"invalid {RAW_HASHES_FILENAME} in {directory}: {registry_error}")
    elif isinstance(registry, Mapping):
        entries = registry.get("entries", [])
        if not isinstance(entries, list):
            problems.append(f"invalid entries in {directory / RAW_HASHES_FILENAME}")
        else:
            for entry in entries:
                if not isinstance(entry, Mapping):
                    problems.append(f"invalid registry entry in {directory / RAW_HASHES_FILENAME}")
                    break
                if not entry.get("filename") or not entry.get("sha256"):
                    problems.append(
                        f"incomplete registry entry in {directory / RAW_HASHES_FILENAME}"
                    )
                    break

    return {"valid": not problems, "problems": problems, "report": payload}


# Friendly aliases for embedders and older scripts.
build_report = build_data_report
build_status = build_data_report
build_data_status = build_data_report
data_report = build_data_report
data_status = build_data_report
collect_report = build_data_report
report_for = build_data_report
status_report = build_data_report
format_report = format_data_report
format_status = format_data_report
render_report = format_data_report
render_status = format_data_report
validate_directory = validate_data_directory


__all__ = [
    "IMPORT_MANIFEST",
    "PARSER_REPORTS",
    "RAW_HASHES",
    "REPORT_SCHEMA_VERSION",
    "build_data_report",
    "build_data_status",
    "build_report",
    "build_status",
    "collect_report",
    "data_report",
    "data_status",
    "format_data_report",
    "format_report",
    "format_status",
    "has_import_artifacts",
    "render_report",
    "render_status",
    "report_for",
    "status_report",
    "validate_data_directory",
    "validate_directory",
]
