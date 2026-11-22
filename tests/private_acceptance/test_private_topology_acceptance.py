"""Opt-in A4 acceptance checks for the causal topology score.

Uses the real private seed archive (never committed) to import a temporary data
directory and compute the frozen default score series: warm-up boundary, finite
score range, reproducibility and causality.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from topomarket.data.adapters import import_sources
from topomarket.topology import (
    DEFAULT_CONFIG,
    compute_topology_scores,
    load_daily_rows,
    write_scores_csv,
)

SEED_ENV = "TOPOMARKET_SEED_DIR"
EXPECTED_TDA_ROWS = 9_250


def _seed_root() -> Path:
    value = os.environ.get(SEED_ENV)
    if not value:
        pytest.skip(f"{SEED_ENV} is not set; A4 acceptance checks are opt-in")
    root = Path(value)
    if not (root / "raw").is_dir():
        pytest.skip(f"{SEED_ENV} does not contain a raw/ seed directory")
    return root


def _data_dir(tmp_path: Path, seed_root: Path) -> Path:
    data_dir = tmp_path / "data"
    import_sources(seed_root / "raw", data_dir)
    return data_dir


def test_a4_default_score_series_on_private_snapshot(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = _data_dir(tmp_path, seed_root)
    rows = load_daily_rows(data_dir)
    assert len(rows) == EXPECTED_TDA_ROWS

    series = compute_topology_scores(rows)

    window = DEFAULT_CONFIG.window_sessions
    reference = DEFAULT_CONFIG.reference_window
    first_l_index = window - 1
    first_deviation_index = first_l_index + reference
    first_score_index = first_deviation_index + reference

    assert series.exploratory is False
    assert series.config_hash
    assert series.unavailable_count == first_l_index
    assert series.first_scored_date == rows[first_score_index]["date"]
    assert series.scored_count == EXPECTED_TDA_ROWS - first_score_index
    assert series.warmup_count == EXPECTED_TDA_ROWS - first_l_index - series.scored_count
    scored = [point for point in series.points if point.state == "scored"]
    assert scored
    assert all(point.score is not None and 0.0 <= point.score <= 100.0 for point in scored)
    assert all(point.l_value is not None and point.deviation is not None for point in scored)
    assert series.latest_score is not None


def test_a4_reproducibility_and_causality_on_private_snapshot(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = _data_dir(tmp_path, seed_root)
    rows = load_daily_rows(data_dir)

    first = compute_topology_scores(rows)
    second = compute_topology_scores(rows)
    assert first.cache_key == second.cache_key
    assert first.as_dict() == second.as_dict()

    path_a = tmp_path / "a" / "scores.csv"
    path_b = tmp_path / "b" / "scores.csv"
    write_scores_csv(first, path_a)
    write_scores_csv(second, path_b)
    digest_a = hashlib.sha256(path_a.read_bytes()).hexdigest()
    digest_b = hashlib.sha256(path_b.read_bytes()).hexdigest()
    assert digest_a == digest_b

    prefix = compute_topology_scores(rows[:1000])
    assert list(prefix.points) == list(first.points[:1000])
