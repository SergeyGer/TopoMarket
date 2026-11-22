"""Opt-in Step 5 acceptance checks over the real private seed.

The seed is read only from ``TOPOMARKET_SEED_DIR`` and imported into a pytest
temporary directory.  Nothing is copied into, or written below, the repository
checkout, and the module skips automatically when the variable is absent.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from topomarket import cli
from topomarket.analysis import INDUSTRY_COLUMNS, WINDOW_SESSIONS
from topomarket.data.adapters import import_sources
from topomarket.topology import load_daily_rows

SEED_ENV = "TOPOMARKET_SEED_DIR"
GOLDEN_DATE = "2020-03-16"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _seed_root() -> Path:
    value = os.environ.get(SEED_ENV)
    if not value:
        pytest.skip(f"{SEED_ENV} is not set; Step 5 acceptance checks are opt-in")
    root = Path(value)
    if not (root / "raw").is_dir():
        pytest.skip(f"{SEED_ENV} does not contain a raw/ seed directory")
    return root


def _data_dir(tmp_path: Path, seed_root: Path) -> Path:
    """Import the private seed into a temporary data directory."""

    data_dir = tmp_path / "data"
    import_sources(seed_root / "raw", data_dir)
    return data_dir


def _industry_payload(
    capsys: pytest.CaptureFixture[str], data_dir: Path, *extra: str
) -> dict[str, object]:
    code = cli.main(["industries", "--data-dir", str(data_dir), "--json", *extra])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    payload = json.loads(captured.out)
    assert isinstance(payload, dict)
    return payload


def _complete(row: dict[str, str]) -> bool:
    for column in INDUSTRY_COLUMNS:
        value = row.get(column)
        if value is None or not str(value).strip():
            return False
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(number):
            return False
    return True


def _latest_complete_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for end in range(len(rows) - 1, WINDOW_SESSIONS - 2, -1):
        window = rows[end - WINDOW_SESSIONS + 1 : end + 1]
        if all(_complete(row) for row in window):
            return window
    pytest.fail("private tda_daily has no complete 60-session industry window")


def test_a5_latest_complete_industry_window_on_private_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_root = _seed_root()
    data_dir = _data_dir(tmp_path, seed_root)
    rows = load_daily_rows(data_dir)
    assert len(rows) > WINDOW_SESSIONS
    expected_window = _latest_complete_rows(rows)

    payload = _industry_payload(capsys, data_dir)

    assert payload["as_of"] == expected_window[-1]["date"]
    assert payload["window_sessions"] == WINDOW_SESSIONS == 60
    assert len(payload["dates"]) == WINDOW_SESSIONS
    assert payload["dates"] == [row["date"] for row in expected_window]
    assert payload["start_date"] == expected_window[0]["date"]
    assert len(payload["industry_columns"]) == 12
    assert len(payload["cloud"]["pca"]) == 60
    assert all(len(row) == 2 for row in payload["cloud"]["pca"])
    assert len(payload["mapper"]["nodes"]) == payload["node_count"]
    assert len(payload["mapper"]["edges"]) == payload["edge_count"]
    assert payload["mapper"]["as_of"] == payload["as_of"]


def test_a5_golden_date_window_on_private_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_root = _seed_root()
    data_dir = _data_dir(tmp_path, seed_root)
    rows = load_daily_rows(data_dir)
    dates = [row["date"] for row in rows]
    assert GOLDEN_DATE in dates

    payload = _industry_payload(capsys, data_dir, "--date", GOLDEN_DATE)

    expected_start = dates[dates.index(GOLDEN_DATE) - 59]
    assert payload["as_of"] == GOLDEN_DATE
    assert payload["dates"][0] == expected_start
    assert payload["dates"][-1] == GOLDEN_DATE
    assert len(payload["dates"]) == 60
    assert payload["cloud"]["dates"][-1] == GOLDEN_DATE
    assert payload["mapper"]["as_of"] == GOLDEN_DATE
    assert not Path(str(payload["data_dir"])).resolve().is_relative_to(REPO_ROOT)


def test_a5_private_import_stays_outside_the_repository(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = _data_dir(tmp_path, seed_root)

    assert data_dir.resolve().is_relative_to(tmp_path.resolve())
    written = [path for path in data_dir.rglob("*") if path.is_file()]
    assert written
    assert all(path.resolve().is_relative_to(tmp_path.resolve()) for path in written)
    assert all(not path.resolve().is_relative_to(REPO_ROOT) for path in written)
