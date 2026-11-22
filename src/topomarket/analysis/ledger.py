"""Append-only private forecast ledger for Step 6.

The ledger is a JSONL file supplied by the caller. It is opened only in append
mode, existing bytes are never rewritten or removed, and every record is
validated before it is written. The default location is intentionally absent:
private ledgers must live outside the repository checkout.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class LedgerError(ValueError):
    """Raised for invalid ledger records or unreadable ledger files."""


REQUIRED_FIELDS: tuple[str, ...] = (
    "recorded_at_utc",
    "as_of",
    "method",
    "value",
    "cutoff",
    "alert",
    "snapshot_id",
    "config_hash",
    "policy_hash",
)

_STRING_FIELDS = ("recorded_at_utc", "as_of", "method", "snapshot_id", "config_hash", "policy_hash")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(record)
    unknown = set(data) - set(REQUIRED_FIELDS)
    if unknown:
        raise LedgerError(f"unknown ledger field(s): {', '.join(sorted(unknown))}")
    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        raise LedgerError(f"missing ledger field(s): {', '.join(missing)}")
    for field in _STRING_FIELDS:
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            raise LedgerError(f"ledger field {field!r} must be a non-empty string")
    if data["method"] not in {"tda", "vix", "realized_vol", "tda_unscaled", "tda_shuffled"}:
        raise LedgerError(f"unknown ledger method: {data['method']!r}")
    if not isinstance(data["alert"], bool):
        raise LedgerError("ledger alert must be a boolean")
    for field in ("value", "cutoff"):
        try:
            number = float(data[field])
        except (TypeError, ValueError) as exc:
            raise LedgerError(f"ledger field {field!r} must be numeric") from exc
        if not number == number or number in (float("inf"), float("-inf")):
            raise LedgerError(f"ledger field {field!r} must be finite")
        data[field] = number
    try:
        datetime.fromisoformat(data["as_of"])
    except ValueError as exc:
        raise LedgerError("ledger field 'as_of' must be an ISO date") from exc
    return data


class ForecastLedger:
    """Append-only JSONL ledger; existing records are never modified."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()

    def read(self) -> list[dict[str, Any]]:
        """Read all records in order; malformed lines raise without writes."""
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise LedgerError(f"could not read ledger {self.path}: {exc}") from exc
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"invalid JSON in ledger line {number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise LedgerError(f"ledger line {number} is not an object")
            records.append(payload)
        return records

    @property
    def records(self) -> list[dict[str, Any]]:
        return self.read()

    def append(self, record: Mapping[str, Any], *, clock: Any | None = None) -> int:
        """Validate and append one record; return the new record count."""
        data = dict(record)
        if "recorded_at_utc" not in data:
            data["recorded_at_utc"] = _now_iso() if clock is None else str(clock())
        validated = _validate_record(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(validated, sort_keys=True, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return len(self.read())

    def append_many(self, records: Iterable[Mapping[str, Any]], *, clock: Any | None = None) -> int:
        """Append multiple records atomically with respect to this process."""
        materialised = [dict(record) for record in records]
        if not materialised:
            return len(self.read())
        lines: list[str] = []
        for record in materialised:
            data = dict(record)
            if "recorded_at_utc" not in data:
                data["recorded_at_utc"] = _now_iso() if clock is None else str(clock())
            validated = _validate_record(data)
            lines.append(json.dumps(validated, sort_keys=True, separators=(",", ":")) + "\n")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("".join(lines))
            handle.flush()
            os.fsync(handle.fileno())
        return len(self.read())


def ledger_records_for_alerts(
    evaluation: Any,
    *,
    policy: Any,
    snapshot_id: str,
    config_hash: str,
    clock: Any | None = None,
) -> list[dict[str, Any]]:
    """Build ledger records for the alerts of one evaluation (alert=True only)."""
    alert_dates = list(getattr(evaluation, "alerts", ()) or ())
    alert_values = list(getattr(evaluation, "alert_values", ()) or ())
    if len(alert_values) != len(alert_dates):
        alert_values = [float("nan")] * len(alert_dates)
    records: list[dict[str, Any]] = []
    recorded = _now_iso() if clock is None else str(clock())
    for date, value in zip(alert_dates, alert_values, strict=True):
        records.append(
            {
                "recorded_at_utc": recorded,
                "as_of": str(date),
                "method": str(getattr(evaluation, "method", "unknown")),
                "value": float(value) if value == value else 0.0,
                "cutoff": float(policy.cutoff),
                "alert": True,
                "snapshot_id": snapshot_id,
                "config_hash": config_hash,
                "policy_hash": policy.policy_hash(),
            }
        )
    return records


def ledger_digest(path: Path | str) -> str:
    """Return a sha256 digest of the ledger bytes (for evidence/reporting)."""
    import hashlib

    ledger = ForecastLedger(path)
    if not ledger.path.exists():
        return ""
    return hashlib.sha256(ledger.path.read_bytes()).hexdigest()


__all__ = [
    "ForecastLedger",
    "LedgerError",
    "REQUIRED_FIELDS",
    "ledger_digest",
    "ledger_records_for_alerts",
]
