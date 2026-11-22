"""Refresh orchestration, atomic snapshot publication and recovery (Step 3).

The refresh pipeline connects :mod:`topomarket.data.fetch` to the existing
adapters/normalized tables and publishes immutable snapshots below a local data
directory:

* fetched bytes are staged and validated before anything is published;
* writers are serialized with one lock file;
* a candidate snapshot directory is built completely in staging and atomically
  renamed into ``snapshots/<snapshot_id>``;
* the active snapshot pointer is replaced atomically only after validation;
* previous snapshots stay readable, so a failed refresh keeps the last good
  snapshot active;
* conditional request validators are committed only after a successful publish.

Nothing in this module performs network work at import time, and nothing is ever
written outside the supplied data directory.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import shutil
import uuid
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from topomarket.data.adapters import import_sources
from topomarket.data.fetch import SOURCES, FetchResult, fetch_source
from topomarket.data.manifest import compute_snapshot_id
from topomarket.data.normalized import SP500_CUTOVER_DATE, write_normalized_tables
from topomarket.data.schemas import (
    INDUSTRIES_DAILY,
    INDUSTRIES_DAILY_COLUMNS,
    NORMALIZED_TABLE_NAMES,
    SP500_DAILY,
    TDA_DAILY,
)

#: Maximum accepted size of a single fetched source payload (50 MiB).
MAX_SOURCE_BYTES = 50 * 1024 * 1024

STATE_DIRNAME = "state"
SNAPSHOTS_DIRNAME = "snapshots"
STAGING_DIRNAME = "staging"
ACTIVE_POINTER_FILENAME = "active_snapshot.json"
VALIDATORS_FILENAME = "validators.json"
REFRESH_STATUS_FILENAME = "refresh_status.json"
LOCK_FILENAME = "refresh.lock"
SNAPSHOT_MANIFEST_FILENAME = "refresh_manifest.json"

#: Provider filenames used for adapter detection when staging fetched bytes.
SOURCE_FILENAMES: Mapping[str, str] = {
    "fred_sp500": "SP500_FRED.csv",
    "cboe_vix": "VIX_History.csv",
    "french_12_industries": "12_Industry_Portfolios_daily_CSV.zip",
    "ofr_fsi": "ofr_fsi.csv",
}

#: Sources that must refresh successfully before a new snapshot is published.
REQUIRED_REFRESH_SOURCES: tuple[str, ...] = (
    "fred_sp500",
    "cboe_vix",
    "french_12_industries",
)

OPTIONAL_REFRESH_SOURCES: tuple[str, ...] = ("ofr_fsi",)

DEFAULT_REFRESH_SOURCES: tuple[str, ...] = (*REQUIRED_REFRESH_SOURCES, *OPTIONAL_REFRESH_SOURCES)

INDUSTRY_RETURN_COLUMNS: tuple[str, ...] = tuple(INDUSTRIES_DAILY_COLUMNS[1:])


class RefreshError(RuntimeError):
    """Raised when a refresh cannot be validated or published."""


class RefreshBusyError(RefreshError):
    """Raised when another refresh holds the local writer lock."""


@dataclass(frozen=True, slots=True)
class SourceRefreshStatus:
    source_id: str
    url: str
    outcome: str
    http_status: int | None
    not_modified: bool
    received_at_utc: str | None
    last_attempt_at: str
    last_success_at: str | None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "outcome": self.outcome,
            "http_status": self.http_status,
            "not_modified": self.not_modified,
            "received_at_utc": self.received_at_utc,
            "last_attempt_at": self.last_attempt_at,
            "last_success_at": self.last_success_at,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    date: str
    source_id: str
    field: str
    old_value: str | None
    new_value: str | None
    snapshot_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "source_id": self.source_id,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True, slots=True)
class RefreshReport:
    active_snapshot_id: str | None
    new_snapshot_id: str | None
    published: bool
    sources: tuple[SourceRefreshStatus, ...] = ()
    revisions: tuple[RevisionRecord, ...] = ()
    added_rows: int = 0
    removed_rows: int = 0
    warnings: tuple[str, ...] = ()
    latest_data_date: str | None = None

    @property
    def ok(self) -> bool:
        return self.published or all(
            status.outcome in {"unchanged", "busy"} for status in self.sources
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_snapshot_id": self.active_snapshot_id,
            "new_snapshot_id": self.new_snapshot_id,
            "published": self.published,
            "sources": [status.as_dict() for status in self.sources],
            "revisions": [revision.as_dict() for revision in self.revisions],
            "added_rows": self.added_rows,
            "removed_rows": self.removed_rows,
            "warnings": list(self.warnings),
            "latest_data_date": self.latest_data_date,
        }


class _RefreshLock:
    """Single-process writer lock based on an O_EXCL lock file."""

    def __init__(self, data_dir: Path, *, stale_seconds: float = 600.0) -> None:
        self._path = data_dir / STATE_DIRNAME / LOCK_FILENAME
        self._stale_seconds = stale_seconds
        self._own_token: str | None = None

    def __enter__(self) -> _RefreshLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        payload = json.dumps(
            {"pid": os.getpid(), "token": token, "started_at": _now_iso()}, sort_keys=True
        )
        for attempt in (1, 2):
            try:
                descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if attempt == 2:
                    raise RefreshBusyError(
                        f"another refresh holds the writer lock: {self._path}"
                    ) from None
                self._break_stale_lock()
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
            self._own_token = token
            return self
        raise RefreshBusyError(f"could not acquire refresh lock: {self._path}")

    def __exit__(self, *_exc_info: object) -> None:
        if self._own_token is None:
            return
        try:
            current = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = None
        if isinstance(current, dict) and current.get("token") == self._own_token:
            try:
                self._path.unlink()
            except FileNotFoundError:  # pragma: no cover - defensive
                pass
        self._own_token = None

    def _break_stale_lock(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            started = datetime.fromisoformat(str(payload.get("started_at")))
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - started).total_seconds()
        except (OSError, ValueError, TypeError):
            age = self._stale_seconds + 1
        if age <= self._stale_seconds:
            raise RefreshBusyError(f"another refresh holds the writer lock: {self._path}")
        try:
            self._path.unlink()
        except FileNotFoundError:  # pragma: no cover - defensive
            pass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_layout(data_dir: Path) -> None:
    for directory in (STATE_DIRNAME, SNAPSHOTS_DIRNAME, STAGING_DIRNAME):
        (data_dir / directory).mkdir(parents=True, exist_ok=True)


def active_snapshot_id(data_dir: Path | str) -> str | None:
    """Return the active snapshot id stored in the data directory, if any."""
    root = Path(data_dir)
    payload = _read_json(root / STATE_DIRNAME / ACTIVE_POINTER_FILENAME)
    if not payload:
        return None
    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        return None
    if not (root / SNAPSHOTS_DIRNAME / snapshot_id).is_dir():
        return None
    return snapshot_id


def resolve_active_data_dir(data_dir: Path | str) -> Path:
    """Resolve the directory that exposes the currently active snapshot data."""
    root = Path(data_dir)
    snapshot_id = active_snapshot_id(root)
    if snapshot_id is None:
        return root
    return root / SNAPSHOTS_DIRNAME / snapshot_id


def load_refresh_status(data_dir: Path | str) -> dict[str, Any]:
    """Return the last refresh status document (empty when never refreshed)."""
    return _read_json(Path(data_dir) / STATE_DIRNAME / REFRESH_STATUS_FILENAME) or {}


def _validators_for_active(data_dir: Path) -> dict[str, dict[str, str]]:
    snapshot_id = active_snapshot_id(data_dir)
    payload = _read_json(data_dir / STATE_DIRNAME / VALIDATORS_FILENAME)
    if not payload or snapshot_id is None or payload.get("snapshot_id") != snapshot_id:
        return {}
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for source_id, validators in sources.items():
        if isinstance(validators, dict):
            entry: dict[str, str] = {}
            if isinstance(validators.get("etag"), str):
                entry["etag"] = validators["etag"]
            if isinstance(validators.get("last_modified"), str):
                entry["last_modified"] = validators["last_modified"]
            result[str(source_id)] = entry
    return result


def _previous_source_status(data_dir: Path) -> dict[str, dict[str, Any]]:
    payload = load_refresh_status(data_dir)
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        return {}
    return {
        str(source_id): dict(value)
        for source_id, value in sources.items()
        if isinstance(value, dict)
    }


def _write_refresh_status(
    data_dir: Path,
    *,
    statuses: Sequence[SourceRefreshStatus],
    published: bool,
    snapshot_id: str | None,
    error: str | None,
    warnings: Sequence[str],
) -> None:
    payload = {
        "schema_version": 1,
        "active_snapshot_id": snapshot_id,
        "published": published,
        "updated_at_utc": _now_iso(),
        "error": error,
        "warnings": list(warnings),
        "sources": {status.source_id: status.as_dict() for status in statuses},
    }
    _atomic_write_json(data_dir / STATE_DIRNAME / REFRESH_STATUS_FILENAME, payload)


# --------------------------------------------------------------------------- #
# Staging / validation helpers
# --------------------------------------------------------------------------- #


def _validate_archive(data: bytes) -> None:
    """Reject unsafe or oversized ZIP archives before handing them to adapters."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = 0
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or name.startswith("../") or "/../" in name:
                    raise RefreshError(f"unsafe archive member path: {info.filename!r}")
                total += info.file_size
                if info.file_size > MAX_SOURCE_BYTES or total > MAX_SOURCE_BYTES:
                    raise RefreshError("archive expands beyond the 50 MiB limit")
            if archive.testzip() is not None:
                raise RefreshError("archive is corrupt")
    except zipfile.BadZipFile as exc:
        raise RefreshError(f"invalid ZIP payload: {exc}") from exc


def _stage_fetched_bytes(
    staging_dir: Path, source_id: str, data: bytes, *, received_at: str, http_status: int | None
) -> Path:
    if len(data) > MAX_SOURCE_BYTES:
        raise RefreshError(f"{source_id}: payload of {len(data)} bytes exceeds the 50 MiB limit")
    if len(data) == 0:
        raise RefreshError(f"{source_id}: provider returned an empty payload")
    filename = SOURCE_FILENAMES[source_id]
    if filename.endswith(".zip"):
        _validate_archive(data)
    destination = staging_dir / filename
    destination.write_bytes(data)
    sidecar = staging_dir / f"{source_id}.meta.json"
    _atomic_write_json(
        sidecar,
        {
            "source_id": source_id,
            "filename": filename,
            "sha256": _sha256_bytes(data),
            "size_bytes": len(data),
            "received_at_utc": received_at,
            "http_status": http_status,
        },
    )
    return destination


def _build_candidate(
    staging_dir: Path, build_dir: Path, fetched: Mapping[str, bytes]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate staged bytes by importing them into a throwaway build directory."""
    raw_dir = staging_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source_id, data in fetched.items():
        (raw_dir / SOURCE_FILENAMES[source_id]).write_bytes(data)
    try:
        result = import_sources(raw_dir, build_dir)
    except Exception as exc:  # noqa: BLE001 - adapters raise several error types
        raise RefreshError(f"staged provider data failed validation: {exc}") from exc
    if result.errors:
        messages = "; ".join(f"{path}: {message}" for path, message in result.errors.items())
        raise RefreshError(f"staged provider data failed validation: {messages}")
    for source_id in fetched:
        dataset = result.tables.get(source_id)
        if dataset is None or not len(dataset):
            raise RefreshError(
                f"staged provider data for {source_id} produced no accepted observations"
            )
    return result.normalized_tables, {
        "reports": {source_id: dict(report) for source_id, report in result.reports.items()},
        "warnings": list(result.warnings),
    }


# --------------------------------------------------------------------------- #
# Normalized-table merge
# --------------------------------------------------------------------------- #


def load_normalized_tables(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Load normalized CSV tables from a snapshot/data directory."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for name in NORMALIZED_TABLE_NAMES:
        path = data_dir / "normalized" / f"{name}.csv"
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            tables[name] = list(csv.DictReader(handle))
    return tables


def _source_rows(result_tables: Mapping[str, Any], source_id: str) -> list[dict[str, Any]]:
    dataset = result_tables.get(source_id)
    if dataset is None:
        return []
    return [dict(row) for row in dataset]


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _format_float(value: float, digits: int = 10) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


def _merge_sp500(
    previous: Sequence[Mapping[str, Any]], candidate: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {
        str(row["date"]): dict(row) for row in previous if row.get("date")
    }
    cutover = SP500_CUTOVER_DATE.isoformat()
    for row in candidate:
        date = str(row.get("date") or "")
        if not date:
            continue
        # OpenIntro is authoritative through the fixed cutover date; FRED rows are
        # accepted only strictly after it (the baseline already applies the rule).
        if date <= cutover:
            continue
        merged[date] = dict(row)
    ordered = [merged[date] for date in sorted(merged)]
    previous_close: float | None = None
    for row in ordered:
        close = _float(row.get("sp500_close"))
        if close is None or close <= 0:
            row["sp500_log_return"] = ""
            previous_close = None
            continue
        if previous_close is not None:
            row["sp500_log_return"] = _format_float(math.log(close / previous_close))
        else:
            row["sp500_log_return"] = ""
        previous_close = close
    return ordered


def _rebuild_tda(
    sp500_rows: Sequence[Mapping[str, Any]],
    industries_rows: Sequence[Mapping[str, Any]],
    vix_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    vix_by_date = {
        str(row.get("date")): _float(row.get("close") or row.get("vix_close"))
        for row in vix_rows
        if row.get("date")
    }
    industries_by_date = {str(row.get("date")): row for row in industries_rows if row.get("date")}
    result: list[dict[str, Any]] = []
    for row in sp500_rows:
        date = str(row.get("date"))
        close = _float(row.get("sp500_close"))
        log_return = row.get("sp500_log_return")
        vix_close = vix_by_date.get(date)
        industry = industries_by_date.get(date)
        if close is None or vix_close is None or industry is None:
            continue
        values = [industry.get(column) for column in INDUSTRY_RETURN_COLUMNS]
        if any(value in (None, "") for value in values):
            continue
        merged_row: dict[str, Any] = {
            "date": date,
            "sp500_close": row.get("sp500_close"),
            "sp500_log_return": log_return if log_return not in (None, "") else "",
            "vix_close": _format_float(vix_close),
        }
        for column, value in zip(INDUSTRY_RETURN_COLUMNS, values, strict=True):
            merged_row[column] = value
        result.append(merged_row)
    return result


def merge_normalized_tables(
    previous: Mapping[str, Sequence[Mapping[str, Any]]],
    candidate_tables: Mapping[str, Any],
    *,
    fetched_sources: set[str],
) -> tuple[dict[str, list[dict[str, Any]]], tuple[str, ...]]:
    """Merge candidate tables over the previous snapshot deterministically."""
    warnings: list[str] = []
    previous_sp500 = list(previous.get(SP500_DAILY, []))
    candidate_sp500 = _source_rows(candidate_tables, SP500_DAILY)
    sp500_rows = _merge_sp500(previous_sp500, candidate_sp500)

    candidate_industries = _source_rows(candidate_tables, INDUSTRIES_DAILY)
    if candidate_industries:
        industries_rows = [dict(row) for row in candidate_industries]
    else:
        industries_rows = list(previous.get(INDUSTRIES_DAILY, []))
        warnings.append("industries unchanged: French source not refreshed")

    candidate_vix = _source_rows(candidate_tables, TDA_DAILY)
    if not candidate_vix:
        source_vix = _source_rows(candidate_tables, "cboe_vix")
        candidate_vix = [
            {"date": row.get("date"), "vix_close": row.get("close")} for row in source_vix
        ]
    vix_by_date: dict[str, Any] = {
        str(row.get("date")): row.get("vix_close")
        for row in previous.get(TDA_DAILY, [])
        if row.get("vix_close") not in (None, "")
    }
    for row in candidate_vix:
        date = str(row.get("date") or "")
        value = row.get("vix_close")
        if date and value not in (None, ""):
            vix_by_date[date] = value
    vix_rows = [{"date": date, "close": value} for date, value in sorted(vix_by_date.items())]
    if not candidate_vix and vix_rows:
        warnings.append("VIX unchanged: Cboe source not refreshed")
    tda_rows = _rebuild_tda(sp500_rows, industries_rows, vix_rows)
    if not tda_rows:
        warnings.append("tda_daily could not be rebuilt from the refreshed inputs")

    merged = {
        SP500_DAILY: sp500_rows,
        INDUSTRIES_DAILY: industries_rows,
        TDA_DAILY: tda_rows,
    }
    del fetched_sources
    return merged, tuple(warnings)


def _values_equal(old: Any, new: Any) -> bool:
    old_number = _float(old)
    new_number = _float(new)
    if old_number is not None and new_number is not None:
        return abs(old_number - new_number) <= 1e-9
    return old == new


def _collect_revisions(
    previous: Mapping[str, Sequence[Mapping[str, Any]]],
    merged: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[RevisionRecord, ...]:
    revisions: list[RevisionRecord] = []
    for table, key_fields in (
        (SP500_DAILY, ("date",)),
        (INDUSTRIES_DAILY, ("date",)),
    ):
        previous_rows = {
            tuple(str(row[key]) for key in key_fields): row for row in previous.get(table, [])
        }
        for row in merged.get(table, []):
            key = tuple(str(row.get(field)) for field in key_fields)
            old = previous_rows.get(key)
            if old is None:
                continue
            for column in row:
                if column in key_fields:
                    continue
                if not _values_equal(old.get(column), row.get(column)):
                    if table == SP500_DAILY:
                        source_id = "fred_sp500"
                    elif table == INDUSTRIES_DAILY:
                        source_id = "french_12_industries"
                    else:
                        source_id = "refresh"
                    revisions.append(
                        RevisionRecord(
                            date=key[0],
                            source_id=source_id,
                            field=column,
                            old_value=old.get(column),
                            new_value=row.get(column),
                        )
                    )
    revisions.sort(key=lambda item: (item.date, item.source_id, item.field))
    return tuple(revisions)


def _canonical_rows_digest(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    digest = hashlib.sha256()
    digest.update(b"topomarket-refresh-v1\n")
    for name in NORMALIZED_TABLE_NAMES:
        digest.update(f"[{name}]\n".encode())
        for row in tables.get(name, []):
            digest.update(
                json.dumps(
                    {column: row.get(column) for column in row},
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                ).encode()
            )
            digest.update(b"\n")
    return digest.hexdigest()


def _normalized_digest(normalized_dir: Path) -> str:
    """Hash the published normalized CSV bytes (the active snapshot identity)."""
    digest = hashlib.sha256()
    digest.update(b"topomarket-refresh-normalized-v1\n")
    for name in NORMALIZED_TABLE_NAMES:
        path = normalized_dir / "normalized" / f"{name}.csv"
        digest.update(f"[{name}]\n".encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _copy_snapshot_artifacts(source_dir: Path, destination: Path) -> None:
    """Copy import artifacts from ``source_dir`` to ``destination`` (no state dirs)."""
    destination.mkdir(parents=True, exist_ok=True)
    skipped = {"state", "staging", "snapshots", "normalized"}
    for entry in source_dir.iterdir():
        if entry.name in skipped:
            continue
        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)


def _write_import_manifest(
    snapshot_dir: Path,
    *,
    row_counts: Mapping[str, int],
    normalized_row_counts: Mapping[str, int],
    source_ids: Sequence[str],
    latest_data_date: str | None,
    warnings: Sequence[str],
) -> None:
    excluded_names = {"import_manifest.json", "refresh_manifest.json"}
    files: list[dict[str, Any]] = []
    for path in sorted(snapshot_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name in excluded_names:
            continue
        relative = path.relative_to(snapshot_dir).as_posix()
        if relative.startswith(
            (f"{STATE_DIRNAME}/", f"{STAGING_DIRNAME}/", f"{SNAPSHOTS_DIRNAME}/")
        ):
            continue
        files.append(
            {
                "path": relative,
                "sha256": _sha256_bytes(path.read_bytes()),
                "size_bytes": path.stat().st_size,
            }
        )
    payload = {
        "schema_version": 1,
        "source_ids": list(source_ids),
        "row_counts": dict(row_counts),
        "normalized_row_counts": dict(normalized_row_counts),
        "normalized_tables": list(NORMALIZED_TABLE_NAMES),
        "file_count": len(files),
        "files": files,
        "output_hashes": {entry["path"]: entry["sha256"] for entry in files},
        "errors": {},
        "missing_sources": [],
        "warnings": list(warnings),
        "latest_data_date": latest_data_date,
    }
    payload["snapshot_id"] = compute_snapshot_id(payload)
    _atomic_write_json(snapshot_dir / "import_manifest.json", payload)


# --------------------------------------------------------------------------- #
# Public refresh entry point
# --------------------------------------------------------------------------- #


def refresh_sources(
    data_dir: Path | str,
    *,
    source_ids: Sequence[str] | None = None,
    fetcher: Callable[..., FetchResult] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> RefreshReport:
    """Refresh the requested sources, publish atomically and return a report."""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    _ensure_layout(root)
    now = (clock or (lambda: datetime.now(UTC)))()
    now_iso = now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    selected = tuple(source_ids) if source_ids is not None else DEFAULT_REFRESH_SOURCES
    unknown = [source_id for source_id in selected if source_id not in SOURCES]
    if unknown:
        raise RefreshError(f"unknown refresh source(s): {', '.join(unknown)}")

    with _RefreshLock(root):
        previous_status = _previous_source_status(root)
        active_id = active_snapshot_id(root)
        previous_dir = resolve_active_data_dir(root)
        previous_tables = load_normalized_tables(previous_dir)
        validators = _validators_for_active(root) if active_id else {}
        attempt_id = uuid.uuid4().hex
        staging_dir = root / STAGING_DIRNAME / attempt_id
        build_dir = staging_dir / "build"
        staging_dir.mkdir(parents=True, exist_ok=True)
        statuses: list[SourceRefreshStatus] = []
        fetched: dict[str, bytes] = {}
        obtained_validators: dict[str, dict[str, str | None]] = {}
        warnings: list[str] = []
        revisions: tuple[RevisionRecord, ...] = ()
        try:
            for source_id in selected:
                previous = previous_status.get(source_id, {})
                last_success = previous.get("last_success_at")
                last_attempt = now_iso
                try:
                    if fetcher is None:
                        result = fetch_source(
                            source_id,
                            etag=validators.get(source_id, {}).get("etag"),
                            last_modified=validators.get(source_id, {}).get("last_modified"),
                        )
                    else:
                        result = fetcher(
                            source_id,
                            etag=validators.get(source_id, {}).get("etag"),
                            last_modified=validators.get(source_id, {}).get("last_modified"),
                        )
                except (RefreshError, RefreshBusyError):
                    raise
                except Exception as exc:  # noqa: BLE001 - surface any provider failure
                    result = FetchResult(
                        source_id=source_id,
                        url=SOURCES[source_id],
                        status=None,
                        not_modified=False,
                        conditional_requested=bool(validators.get(source_id)),
                        body=None,
                        headers={},
                        etag=None,
                        last_modified=None,
                        attempts=0,
                        timeout_seconds=15.0,
                        error=f"{type(exc).__name__}: {exc}",
                        fetched_at_utc=now_iso,
                    )

                if result.not_modified:
                    if active_id is None:
                        raise RefreshError(
                            f"{source_id}: provider returned 304 but no accepted snapshot exists"
                        )
                    statuses.append(
                        SourceRefreshStatus(
                            source_id=source_id,
                            url=SOURCES[source_id],
                            outcome="unchanged",
                            http_status=304,
                            not_modified=True,
                            received_at_utc=None,
                            last_attempt_at=last_attempt,
                            last_success_at=last_success,
                        )
                    )
                    continue
                if result.error is not None or result.status != 200 or result.body is None:
                    status = SourceRefreshStatus(
                        source_id=source_id,
                        url=SOURCES[source_id],
                        outcome=(
                            "optional_failed" if source_id in OPTIONAL_REFRESH_SOURCES else "failed"
                        ),
                        http_status=result.status,
                        not_modified=False,
                        received_at_utc=None,
                        last_attempt_at=last_attempt,
                        last_success_at=last_success,
                        error=result.error or f"provider returned HTTP {result.status}",
                    )
                    statuses.append(status)
                    if source_id in REQUIRED_REFRESH_SOURCES:
                        raise RefreshError(f"required source {source_id} failed: {status.error}")
                    warnings.append(f"optional source {source_id} failed: {status.error}")
                    continue
                _stage_fetched_bytes(
                    staging_dir,
                    source_id,
                    result.body,
                    received_at=result.fetched_at_utc,
                    http_status=result.status,
                )
                fetched[source_id] = result.body
                obtained_validators[source_id] = {
                    "etag": result.etag,
                    "last_modified": result.last_modified,
                }
                statuses.append(
                    SourceRefreshStatus(
                        source_id=source_id,
                        url=SOURCES[source_id],
                        outcome="updated",
                        http_status=result.status,
                        not_modified=False,
                        received_at_utc=result.fetched_at_utc,
                        last_attempt_at=last_attempt,
                        last_success_at=result.fetched_at_utc,
                    )
                )

            candidate_tables, build_meta = _build_candidate(staging_dir, build_dir, fetched)
            warnings.extend(str(item) for item in build_meta.get("warnings", []))
            merged, merge_warnings = merge_normalized_tables(
                previous_tables, candidate_tables, fetched_sources=set(fetched)
            )
            warnings.extend(merge_warnings)
            candidate_normalized_dir = staging_dir / "normalized-candidate"
            write_normalized_tables(merged, candidate_normalized_dir)
            snapshot_id = _normalized_digest(candidate_normalized_dir)
            revisions = _collect_revisions(previous_tables, merged)
            revisions = tuple(
                RevisionRecord(
                    date=revision.date,
                    source_id=revision.source_id,
                    field=revision.field,
                    old_value=revision.old_value,
                    new_value=revision.new_value,
                    snapshot_id=snapshot_id,
                )
                for revision in revisions
            )

            if active_id is not None and snapshot_id == active_id:
                next_validators: dict[str, dict[str, str | None]] = {
                    source_id: dict(entry) for source_id, entry in validators.items()
                }
                next_validators.update(obtained_validators)
                _atomic_write_json(
                    root / STATE_DIRNAME / VALIDATORS_FILENAME,
                    {
                        "schema_version": 1,
                        "snapshot_id": active_id,
                        "sources": next_validators,
                    },
                )
                _write_refresh_status(
                    root,
                    statuses=statuses,
                    published=False,
                    snapshot_id=active_id,
                    error=None,
                    warnings=warnings,
                )
                latest = str(merged[SP500_DAILY][-1]["date"]) if merged.get(SP500_DAILY) else None
                return RefreshReport(
                    active_snapshot_id=active_id,
                    new_snapshot_id=None,
                    published=False,
                    sources=tuple(statuses),
                    revisions=revisions,
                    added_rows=0,
                    removed_rows=0,
                    warnings=tuple(warnings),
                    latest_data_date=latest,
                )

            # Build the complete snapshot in staging, then rename atomically.
            snapshot_tmp = staging_dir / "snapshot"
            _copy_snapshot_artifacts(previous_dir, snapshot_tmp)
            shutil.copytree(candidate_normalized_dir, snapshot_tmp, dirs_exist_ok=True)
            source_row_counts: dict[str, int] = {}
            snapshot_source_ids: list[str] = []
            for source_id in SOURCES:
                source_file = build_dir / f"{source_id}.csv"
                if source_file.is_file():
                    shutil.copy2(source_file, snapshot_tmp / source_file.name)
                    snapshot_source_ids.append(source_id)
                    source_row_counts[source_id] = sum(
                        1 for _ in csv.DictReader(source_file.open(encoding="utf-8"))
                    )
                elif (snapshot_tmp / f"{source_id}.csv").is_file():
                    snapshot_source_ids.append(source_id)
                    source_row_counts[source_id] = sum(
                        1
                        for _ in csv.DictReader(
                            (snapshot_tmp / f"{source_id}.csv").open(encoding="utf-8")
                        )
                    )
            latest_data_date = (
                str(merged[SP500_DAILY][-1]["date"]) if merged.get(SP500_DAILY) else None
            )
            normalized_row_counts = {
                name: len(rows) for name, rows in merged.items() if name in NORMALIZED_TABLE_NAMES
            }
            _write_import_manifest(
                snapshot_tmp,
                row_counts=source_row_counts,
                normalized_row_counts=normalized_row_counts,
                source_ids=snapshot_source_ids,
                latest_data_date=latest_data_date,
                warnings=warnings,
            )
            _atomic_write_json(
                snapshot_tmp / SNAPSHOT_MANIFEST_FILENAME,
                {
                    "schema_version": 1,
                    "snapshot_id": snapshot_id,
                    "created_at_utc": now_iso,
                    "source_statuses": [status.as_dict() for status in statuses],
                    "revisions": [revision.as_dict() for revision in revisions],
                    "warnings": list(warnings),
                    "latest_data_date": latest_data_date,
                    "normalized_row_counts": normalized_row_counts,
                    "content_hash": _sha256_bytes(snapshot_id.encode()),
                },
            )
            final_snapshot = root / SNAPSHOTS_DIRNAME / snapshot_id
            if not final_snapshot.exists():
                os.replace(snapshot_tmp, final_snapshot)
            _atomic_write_json(
                root / STATE_DIRNAME / ACTIVE_POINTER_FILENAME,
                {
                    "schema_version": 1,
                    "snapshot_id": snapshot_id,
                    "published_at_utc": now_iso,
                },
            )
            # Validators are committed only after the snapshot is active.
            next_validators: dict[str, dict[str, str | None]] = {
                source_id: dict(entry) for source_id, entry in validators.items()
            }
            next_validators.update(obtained_validators)
            _atomic_write_json(
                root / STATE_DIRNAME / VALIDATORS_FILENAME,
                {
                    "schema_version": 1,
                    "snapshot_id": snapshot_id,
                    "sources": next_validators,
                },
            )
            _write_refresh_status(
                root,
                statuses=statuses,
                published=True,
                snapshot_id=snapshot_id,
                error=None,
                warnings=warnings,
            )
            return RefreshReport(
                active_snapshot_id=snapshot_id,
                new_snapshot_id=snapshot_id,
                published=True,
                sources=tuple(statuses),
                revisions=revisions,
                added_rows=sum(normalized_row_counts.values()),
                removed_rows=0,
                warnings=tuple(warnings),
                latest_data_date=latest_data_date,
            )
        except (RefreshError, RefreshBusyError) as exc:
            failed_statuses = [
                SourceRefreshStatus(
                    source_id=status.source_id,
                    url=status.url,
                    outcome="failed" if status.outcome == "updated" else status.outcome,
                    http_status=status.http_status,
                    not_modified=status.not_modified,
                    received_at_utc=status.received_at_utc,
                    last_attempt_at=status.last_attempt_at,
                    last_success_at=status.last_success_at,
                    error=str(exc) if status.outcome == "updated" else status.error,
                )
                for status in statuses
            ]
            _write_refresh_status(
                root,
                statuses=failed_statuses,
                published=False,
                snapshot_id=active_id,
                error=str(exc),
                warnings=warnings,
            )
            raise
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)


__all__ = [
    "ACTIVE_POINTER_FILENAME",
    "DEFAULT_REFRESH_SOURCES",
    "MAX_SOURCE_BYTES",
    "OPTIONAL_REFRESH_SOURCES",
    "REQUIRED_REFRESH_SOURCES",
    "RefreshBusyError",
    "RefreshError",
    "RefreshReport",
    "RevisionRecord",
    "SOURCE_FILENAMES",
    "SourceRefreshStatus",
    "active_snapshot_id",
    "load_normalized_tables",
    "load_refresh_status",
    "merge_normalized_tables",
    "refresh_sources",
    "resolve_active_data_dir",
]
