"""Overview data and rendering helpers for the Streamlit shell.

The module deliberately has no dependency on Streamlit so it can be imported
(and unit tested) in environments where the optional UI dependency is not
installed. :mod:`app` supplies the Streamlit module when it renders.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from topomarket.data import latest_snapshot, list_snapshots, read_manifest
from topomarket.data.manifest import ManifestError
from topomarket.profiles import PROFILE_NAMES, load_profile

TITLE = "TopoMarket"
OVERVIEW_HEADING = "Overview"
NAVIGATION_ITEMS: tuple[str, ...] = (
    "Overview",
    "Markets",
    "Topology",
    "Evaluation",
    "Data status",
)
EMPTY_STATE = (
    "No data available yet. Generate a synthetic dataset with "
    "`topomarket synthetic --out <dir>` or point the app at a local data "
    "directory with `--data-dir`."
)
NO_DATED_DATA_STATE = (
    "No dated data is available yet. Add a CSV with a `date` column or "
    "generate synthetic data to see the latest observation date."
)

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_KEYS = (
    "latest_data_date",
    "latest_date",
    "data_date",
    "as_of_date",
    "as_of",
    "observation_date",
    "last_updated",
    "updated_at",
)
_DATE_COLUMN_NAMES = ("date", "as_of", "as_of_date", "timestamp", "datetime", "time")
_MAX_CSV_ROWS = 200_000


def badge_for_profile(profile: str) -> str:
    """Return the short badge text used for a profile."""

    return profile.strip().lower()


def data_source_label(profile: Any) -> str:
    """Return the human-readable label shown next to the profile badge."""

    return f"Data source: {getattr(profile, 'data_source', 'unknown')}"


def _normalise_date(value: Any) -> str | None:
    """Return an ISO ``YYYY-MM-DD`` date found in ``value``, if any."""

    if value is None or isinstance(value, bool):
        return None
    match = _DATE_RE.search(str(value))
    return match.group(0) if match else None


def _explicit_date(manifest: Mapping[str, Any] | None) -> str | None:
    """Return a date explicitly recorded in a manifest, if present."""

    if not isinstance(manifest, Mapping):
        return None

    for key in _DATE_KEYS:
        normalised = _normalise_date(manifest.get(key))
        if normalised is not None:
            return normalised

    metadata = manifest.get("metadata")
    if isinstance(metadata, Mapping):
        for key in _DATE_KEYS:
            normalised = _normalise_date(metadata.get(key))
            if normalised is not None:
                return normalised
    return None


def _csv_date(path: Path) -> str | None:
    """Return the newest ``date`` value found in a CSV file, if any."""

    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                return None
            indexes = {
                index
                for index, column in enumerate(header)
                if column.strip().lower() in _DATE_COLUMN_NAMES
            }
            if not indexes:
                return None

            newest: str | None = None
            for row_number, row in enumerate(reader):
                if row_number >= _MAX_CSV_ROWS:
                    break
                for index in indexes:
                    if index >= len(row):
                        continue
                    candidate = _normalise_date(row[index])
                    if candidate is not None and (newest is None or candidate > newest):
                        newest = candidate
            return newest
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def _csv_date_for_directory(data_dir: Path) -> str | None:
    """Return the newest dated observation across the directory's CSV files."""

    try:
        paths = sorted(path for path in data_dir.glob("*.csv") if path.is_file())
    except OSError:
        return None

    newest: str | None = None
    for path in paths:
        candidate = _csv_date(path)
        if candidate is not None and (newest is None or candidate > newest):
            newest = candidate
    return newest


def latest_data_date(
    data_dir: Path | str,
    manifest: Mapping[str, Any] | None = None,
) -> str | None:
    """Return the newest data date available in ``data_dir``.

    Explicit manifest date fields win, then the newest date found in CSV data,
    then the newest snapshot's date, and finally the manifest's ``created_at``.
    ``None`` means the directory has no dated data.
    """

    directory = Path(data_dir)
    explicit = _explicit_date(manifest)
    if explicit is not None:
        return explicit

    csv_date = _csv_date_for_directory(directory)
    if csv_date is not None:
        return csv_date

    try:
        snapshot = latest_snapshot(directory)
    except (OSError, ValueError):
        snapshot = None
    if snapshot is not None:
        snapshot_date = _explicit_date(snapshot)
        if snapshot_date is not None:
            return snapshot_date
        snapshot_created = _normalise_date(snapshot.get("created_at"))
        if snapshot_created is not None:
            return snapshot_created

    if isinstance(manifest, Mapping):
        return _normalise_date(manifest.get("created_at"))
    return None


def inspect_data_directory(data_dir: Path | str) -> dict[str, Any]:
    """Describe the local data directory used by the overview screen."""

    directory = Path(data_dir).expanduser()
    status: dict[str, Any] = {
        "path": str(directory),
        "exists": directory.is_dir(),
        "is_dir": directory.is_dir(),
        "files": [],
        "data_files": [],
        "manifest_present": False,
        "manifest_valid": False,
        "manifest": None,
        "manifest_error": None,
        "snapshot_count": 0,
        "snapshots": [],
        "latest_snapshot": None,
        "latest_data_date": None,
        "data_available": False,
    }
    if not status["exists"]:
        return status

    try:
        entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    except OSError as exc:
        status["manifest_error"] = str(exc)
        return status

    status["files"] = [entry.name for entry in entries if entry.is_file()]
    status["data_files"] = [
        name for name in status["files"] if name != "manifest.json"
    ]

    manifest_path = directory / "manifest.json"
    if manifest_path.is_file():
        status["manifest_present"] = True
        try:
            manifest = read_manifest(directory)
        except ManifestError as exc:
            status["manifest_error"] = str(exc)
        else:
            status["manifest_valid"] = True
            status["manifest"] = manifest

    try:
        snapshots = list_snapshots(directory)
    except (OSError, ValueError):
        snapshots = []
    status["snapshots"] = [dict(snapshot) for snapshot in snapshots]
    status["snapshot_count"] = len(snapshots)
    status["latest_snapshot"] = dict(snapshots[-1]) if snapshots else None

    status["latest_data_date"] = latest_data_date(directory, status["manifest"])
    status["data_available"] = bool(
        status["manifest_present"] or status["snapshot_count"] or status["data_files"]
    )
    return status


def build_overview(
    profile: str = "demo",
    *,
    data_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Build the data needed to render the overview screen.

    ``profile`` must be one of :data:`topomarket.profiles.PROFILE_NAMES`.
    ``data_dir`` optionally overrides the data directory resolved by the
    profile loader (forwarded from ``--data-dir``).
    """

    if profile not in PROFILE_NAMES:
        raise ValueError(
            f"Unknown profile {profile!r}; expected one of: {', '.join(PROFILE_NAMES)}"
        )

    resolved = load_profile(profile, data_dir=data_dir)
    status = inspect_data_directory(resolved.data_dir)
    latest = status["latest_data_date"]

    if latest is not None:
        empty_state = None
        latest_label = f"Latest data date: {latest}"
    elif status["data_available"]:
        empty_state = NO_DATED_DATA_STATE
        latest_label = "Latest data date: none"
    else:
        empty_state = EMPTY_STATE
        latest_label = "Latest data date: none"

    return {
        "title": TITLE,
        "heading": OVERVIEW_HEADING,
        "profile": resolved.profile,
        "profile_name": resolved.name,
        "profile_description": resolved.description,
        "profile_badge": badge_for_profile(resolved.profile),
        "badge": badge_for_profile(resolved.profile),
        "is_private": resolved.is_private,
        "data_source": resolved.data_source,
        "data_source_label": data_source_label(resolved),
        "data_dir": str(resolved.data_dir),
        "latest_data_date": latest,
        "latest_date": latest,
        "latest_data_date_label": latest_label,
        "empty_state": empty_state,
        "data_available": status["data_available"],
        "navigation": list(NAVIGATION_ITEMS),
        "nav_items": list(NAVIGATION_ITEMS),
        "data_status": status,
        "manifest": status["manifest"],
    }


def plain_text_overview(overview: Mapping[str, Any]) -> str:
    """Render the overview as plain text for non-Streamlit environments."""

    lines = [
        str(overview.get("title", TITLE)),
        str(overview.get("heading", OVERVIEW_HEADING)),
        f"Profile badge: {overview.get('profile_badge', 'unknown')}",
        str(overview.get("data_source_label", "Data source: unknown")),
        f"Data directory: {overview.get('data_dir', '')}",
        str(overview.get("latest_data_date_label", "Latest data date: none")),
    ]
    empty_state = overview.get("empty_state")
    if empty_state:
        lines.append(str(empty_state))
    lines.append("Navigation: " + ", ".join(overview.get("navigation", [])))
    return "\n".join(lines)


__all__ = [
    "EMPTY_STATE",
    "NAVIGATION_ITEMS",
    "NO_DATED_DATA_STATE",
    "OVERVIEW_HEADING",
    "TITLE",
    "badge_for_profile",
    "build_overview",
    "data_source_label",
    "inspect_data_directory",
    "latest_data_date",
    "plain_text_overview",
]
