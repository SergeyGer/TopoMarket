"""Opt-in A8 acceptance: private seed import, refresh and failure recovery."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from topomarket.data.adapters import import_sources
from topomarket.data.fetch import SOURCES, FetchResult
from topomarket.data.refresh import (
    RefreshError,
    active_snapshot_id,
    refresh_sources,
    resolve_active_data_dir,
)
from topomarket.report import validate_data_directory

SEED_ENV = "TOPOMARKET_SEED_DIR"
RAW_FILES = {
    "fred_sp500": "SP500_FRED.csv",
    "cboe_vix": "VIX_History.csv",
    "french_12_industries": "12_Industry_Portfolios_daily_CSV.zip",
    "ofr_fsi": "ofr_fsi.csv",
}


def _seed_root() -> Path:
    value = os.environ.get(SEED_ENV)
    if not value:
        pytest.skip(f"{SEED_ENV} is not set; A8 acceptance checks are opt-in")
    root = Path(value)
    if not (root / "raw").is_dir():
        pytest.skip(f"{SEED_ENV} does not contain a raw/ seed directory")
    return root


def _bodies(seed_root: Path) -> dict[str, bytes]:
    return {
        source_id: (seed_root / "raw" / filename).read_bytes()
        for source_id, filename in RAW_FILES.items()
    }


def _ok(source_id: str, body: bytes) -> FetchResult:
    return FetchResult(
        source_id=source_id,
        url=SOURCES[source_id],
        status=200,
        not_modified=False,
        conditional_requested=False,
        body=body,
        headers={},
        etag=f'"{source_id}-private"',
        last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
        attempts=1,
        timeout_seconds=15.0,
        error=None,
        fetched_at_utc="2025-01-01T00:00:00Z",
    )


def test_a8_private_import_refresh_and_failure_recovery(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = tmp_path / "data"
    import_sources(seed_root / "raw", data_dir)
    bodies = _bodies(seed_root)

    def fetcher(source_id: str, *, etag=None, last_modified=None) -> FetchResult:
        return _ok(source_id, bodies[source_id])

    published = refresh_sources(data_dir, fetcher=fetcher)
    snapshot_id = active_snapshot_id(data_dir)
    assert published.published is True
    assert snapshot_id is not None
    validation = validate_data_directory(resolve_active_data_dir(data_dir))
    assert validation["valid"] is True

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
                error="simulated outage",
                fetched_at_utc="2025-01-01T00:00:00Z",
            )
        return _ok(source_id, bodies[source_id])

    with pytest.raises(RefreshError):
        refresh_sources(data_dir, fetcher=failing)
    assert active_snapshot_id(data_dir) == snapshot_id
    status = (data_dir / "state" / "refresh_status.json").read_text(encoding="utf-8")
    assert "simulated outage" in status

    recovered = refresh_sources(data_dir, fetcher=fetcher)
    assert recovered.published is False
    assert active_snapshot_id(data_dir) == snapshot_id
