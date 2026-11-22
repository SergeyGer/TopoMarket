"""Tests for the append-only Step 6 forecast ledger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket.analysis.ledger import ForecastLedger, LedgerError, ledger_digest


def _record(index: int = 0) -> dict:
    return {
        "recorded_at_utc": "2024-01-01T00:00:00Z",
        "as_of": f"2024-01-{index + 2:02d}",
        "method": "tda",
        "value": 90.0 + index,
        "cutoff": 85.0,
        "alert": True,
        "snapshot_id": "snap-1",
        "config_hash": "cfg-1",
        "policy_hash": "policy-1",
    }


def test_append_only_preserves_previous_bytes(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = ForecastLedger(path)
    assert ledger.read() == []
    ledger.append(_record(0))
    first_bytes = path.read_bytes()
    ledger.append(_record(1))
    assert path.read_bytes().startswith(first_bytes)
    records = ledger.read()
    assert [record["as_of"] for record in records] == ["2024-01-02", "2024-01-03"]


def test_append_many_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = ForecastLedger(path)
    count = ledger.append_many([_record(0), _record(1)])
    assert count == 2
    assert len(ledger.records) == 2
    digest = ledger_digest(path)
    assert len(digest) == 64
    ledger.append(_record(2))
    assert ledger_digest(path) != digest


def test_invalid_record_does_not_modify_file(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = ForecastLedger(path)
    ledger.append(_record(0))
    before = path.read_bytes()
    with pytest.raises(LedgerError):
        ledger.append({**_record(1), "alert": "not-a-bool"})
    with pytest.raises(LedgerError):
        ledger.append({k: v for k, v in _record(1).items() if k != "snapshot_id"})
    with pytest.raises(LedgerError):
        ledger.append({**_record(1), "unknown": "x"})
    assert path.read_bytes() == before


def test_corrupt_existing_line_raises_without_writes(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    ledger = ForecastLedger(path)
    before = path.read_bytes()
    with pytest.raises(LedgerError):
        ledger.read()
    assert path.read_bytes() == before


def test_ledger_records_are_deterministic_json_lines(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ForecastLedger(path).append_many([_record(0), _record(1)])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    payloads = [json.loads(line) for line in lines]
    assert all("recorded_at_utc" in payload for payload in payloads)
