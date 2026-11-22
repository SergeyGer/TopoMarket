"""Opt-in A3 acceptance checks for the refresh and recovery pipeline.

These checks use the real private seed bytes (never committed) as the fetched payloads, so the
full refresh pipeline runs offline and deterministically against the supplied provider data.
Set ``TOPOMARKET_SEED_DIR`` to the seed directory that contains ``raw/``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from topomarket.data.adapters import import_sources
from topomarket.data.fetch import SOURCES, FetchResult
from topomarket.data.refresh import (
    RefreshError,
    active_snapshot_id,
    load_normalized_tables,
    refresh_sources,
    resolve_active_data_dir,
)
from topomarket.report import validate_data_directory

SEED_ENV = "TOPOMARKET_SEED_DIR"
EXPECTED_SP500_ROWS = 19_343
EXPECTED_INDUSTRY_ROWS = 26_338
EXPECTED_TDA_ROWS = 9_250

#: Private raw filename for every refresh source (OpenIntro is a fixed historical seed).
RAW_FILE_NAMES = {
    "fred_sp500": "SP500_FRED.csv",
    "cboe_vix": "VIX_History.csv",
    "french_12_industries": "12_Industry_Portfolios_daily_CSV.zip",
    "ofr_fsi": "ofr_fsi.csv",
}


def _seed_root() -> Path:
    value = os.environ.get(SEED_ENV)
    if not value:
        pytest.skip(f"{SEED_ENV} is not set; A3 acceptance checks are opt-in")
    root = Path(value)
    if not (root / "raw").is_dir():
        pytest.skip(f"{SEED_ENV} does not contain a raw/ seed directory")
    return root


def _bodies(seed_root: Path) -> dict[str, bytes]:
    raw = seed_root / "raw"
    bodies: dict[str, bytes] = {}
    for source_id, filename in RAW_FILE_NAMES.items():
        path = raw / filename
        if not path.is_file():
            pytest.skip(f"missing private seed file for {source_id}: {path}")
        bodies[source_id] = path.read_bytes()
    return bodies


def _result(
    source_id: str, *, body: bytes | None = None, not_modified: bool = False
) -> FetchResult:
    return FetchResult(
        source_id=source_id,
        url=SOURCES[source_id],
        status=304 if not_modified else 200,
        not_modified=not_modified,
        conditional_requested=not_modified,
        body=body,
        headers={},
        etag=f'"{source_id}-private"',
        last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
        attempts=1,
        timeout_seconds=15.0,
        error=None,
        fetched_at_utc="2025-01-01T00:00:00Z",
    )


def _baseline(tmp_path: Path, seed_root: Path) -> Path:
    data_dir = tmp_path / "data"
    import_sources(seed_root / "raw", data_dir)
    return data_dir


def _fetcher(bodies: dict[str, bytes]):
    def fetch(source_id: str, *, etag=None, last_modified=None) -> FetchResult:
        return _result(source_id, body=bodies[source_id])

    return fetch


def test_a3_refresh_with_private_bytes_keeps_row_counts(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = _baseline(tmp_path, seed_root)

    report = refresh_sources(data_dir, fetcher=_fetcher(_bodies(seed_root)))

    assert report.published is True
    assert active_snapshot_id(data_dir) == report.new_snapshot_id
    tables = load_normalized_tables(data_dir / "snapshots" / report.new_snapshot_id)
    assert len(tables["sp500_daily"]) == EXPECTED_SP500_ROWS
    assert len(tables["industries_daily"]) == EXPECTED_INDUSTRY_ROWS
    assert len(tables["tda_daily"]) == EXPECTED_TDA_ROWS
    assert report.latest_data_date is not None

    validation = validate_data_directory(resolve_active_data_dir(data_dir))
    assert validation["valid"] is True


def test_a3_conditional_refresh_keeps_the_snapshot(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = _baseline(tmp_path, seed_root)
    bodies = _bodies(seed_root)
    first = refresh_sources(data_dir, fetcher=_fetcher(bodies))
    assert first.published is True

    def not_modified(source_id: str, *, etag=None, last_modified=None) -> FetchResult:
        return _result(source_id, not_modified=True)

    second = refresh_sources(data_dir, fetcher=not_modified)
    assert second.published is False
    assert second.active_snapshot_id == first.active_snapshot_id
    assert all(status.outcome == "unchanged" for status in second.sources)


def test_a3_failed_refresh_keeps_the_last_good_snapshot(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = _baseline(tmp_path, seed_root)
    first = refresh_sources(data_dir, fetcher=_fetcher(_bodies(seed_root)))
    snapshot_id = first.new_snapshot_id
    assert snapshot_id is not None
    pointer_before = (data_dir / "state" / "active_snapshot.json").read_bytes()

    def failing(source_id: str, *, etag=None, last_modified=None) -> FetchResult:
        if source_id == "cboe_vix":
            return FetchResult(
                source_id=source_id,
                url=SOURCES[source_id],
                status=None,
                not_modified=False,
                conditional_requested=False,
                body=None,
                headers={},
                etag=None,
                last_modified=None,
                attempts=3,
                timeout_seconds=15.0,
                error="simulated provider outage",
                fetched_at_utc="2025-01-01T00:00:00Z",
            )
        return _result(source_id, body=_bodies(seed_root)[source_id])

    with pytest.raises(RefreshError):
        refresh_sources(data_dir, fetcher=failing)

    assert active_snapshot_id(data_dir) == snapshot_id
    assert (data_dir / "state" / "active_snapshot.json").read_bytes() == pointer_before
    status = json.loads((data_dir / "state" / "refresh_status.json").read_text(encoding="utf-8"))
    assert status["published"] is False
    assert status["sources"]["cboe_vix"]["outcome"] == "failed"
