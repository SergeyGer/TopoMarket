"""Tests for the causal daily topology score (Step 4)."""

from __future__ import annotations

import csv
import json
import types
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from topomarket import __version__
from topomarket.data.schemas import TDA_DAILY_COLUMNS
from topomarket.topology import (
    DEFAULT_CONFIG,
    DEFAULT_CONFIG_HASH,
    ScoreError,
    ScoreExportError,
    TopologyConfig,
    compute_topology_scores,
    write_scores_csv,
)
from topomarket.topology.score import _percent_rank


def _weekday_dates(count: int, start: date = date(2018, 1, 1)) -> list[date]:
    dates: list[date] = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _rows(returns: list[float | None], *, start: date = date(2018, 1, 1)) -> list[dict]:
    dates = _weekday_dates(len(returns), start)
    return [
        {"date": day.isoformat(), "sp500_log_return": value}
        for day, value in zip(dates, returns, strict=True)
    ]


def _deterministic_returns(count: int) -> list[float]:
    return [0.01 * np.sin(index / 7.0) + 0.0005 * (index % 3) for index in range(count)]


def _small_config(**overrides: object) -> TopologyConfig:
    base = {
        "window_sessions": 6,
        "embedding_dimension": 3,
        "lag": 2,
        "reference_window": 2,
    }
    base.update(overrides)
    return TopologyConfig(**base)


def test_percent_rank_uses_midrank_with_ties() -> None:
    reference = [1.0, 1.0, 2.0]
    assert _percent_rank(100.0, reference, 2.0, 3) == pytest.approx(250.0 / 3.0)
    assert _percent_rank(100.0, reference, 1.0, 3) == pytest.approx(100.0 / 3.0)
    assert _percent_rank(100.0, reference, 3.0, 3) == pytest.approx(100.0)
    # Only the trailing reference window participates.
    reference = [100.0, 1.0, 1.0]
    assert _percent_rank(100.0, reference, 2.0, 2) == pytest.approx(100.0)


def test_controlled_warmup_deviation_and_score(monkeypatch: pytest.MonkeyPatch) -> None:
    returns = [float(index + 1) for index in range(10)]

    def fake_window(values, config, *args, **kwargs):  # noqa: ANN001 - test double
        lifetime = float(values[-1])
        return types.SimpleNamespace(
            available=True,
            reason=None,
            lifetimes=types.SimpleNamespace(h1=np.array([lifetime])),
        )

    monkeypatch.setattr("topomarket.topology.score.window_topology", fake_window)
    series = compute_topology_scores(_rows(returns), _small_config())

    by_date = {point.date: point for point in series.points}
    points = list(series.points)
    # W=6: first valid L at index 5; ref=2: first D at index 7; first score at index 9.
    assert points[5].state == "warming_up"
    assert points[5].l_value == pytest.approx(6.0)
    assert points[6].deviation is None
    assert points[7].deviation == pytest.approx(1.5)
    assert points[7].score is None
    assert points[8].deviation == pytest.approx(1.5)
    assert points[8].score is None
    assert points[9].score == pytest.approx(50.0)  # refs [1.5,1.5], tie at 1.5 -> midrank 50
    assert series.scored_count == 1
    assert series.first_scored_date == points[9].date
    assert series.config_hash != DEFAULT_CONFIG_HASH
    assert series.exploratory is True
    del by_date


def test_default_config_warmup_boundaries() -> None:
    count = 700
    rows = _rows(_deterministic_returns(count))
    series = compute_topology_scores(rows)

    window = DEFAULT_CONFIG.window_sessions
    reference = DEFAULT_CONFIG.reference_window
    first_l_index = window - 1
    first_deviation_index = first_l_index + reference
    first_score_index = first_deviation_index + reference

    points = list(series.points)
    assert series.exploratory is False
    assert series.config_hash == DEFAULT_CONFIG_HASH
    assert all(point.state == "unavailable" for point in points[:first_l_index])
    assert points[first_l_index].l_value is not None
    assert points[first_l_index].state == "warming_up"
    assert points[first_deviation_index - 1].deviation is None
    assert points[first_deviation_index].deviation is not None
    assert points[first_deviation_index].score is None
    assert points[first_score_index - 1].score is None
    assert points[first_score_index].score is not None
    assert series.first_scored_date == rows[first_score_index]["date"]
    assert series.scored_count == count - first_score_index
    assert series.warmup_count == count - first_l_index - series.scored_count
    assert series.unavailable_count == first_l_index
    assert series.latest_date == rows[-1]["date"]
    assert series.latest_score is not None and 0.0 <= series.latest_score <= 100.0


def test_missing_return_breaks_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    returns: list[float | None] = [float(index + 1) for index in range(12)]
    returns[4] = None

    def fake_window(values, config, *args, **kwargs):  # noqa: ANN001 - test double
        return types.SimpleNamespace(
            available=True,
            reason=None,
            lifetimes=types.SimpleNamespace(h1=np.array([float(values[-1])])),
        )

    monkeypatch.setattr("topomarket.topology.score.window_topology", fake_window)
    series = compute_topology_scores(_rows(returns), _small_config())

    states = [point.state for point in series.points]
    assert states[4] == "unavailable"
    # After the gap the six-return window only becomes valid again at index 10.
    assert all(state == "unavailable" for state in states[5:10])
    assert states[10] != "unavailable"
    assert any("missing" in (point.reason or "") for point in series.points)


def test_duplicate_dates_are_rejected() -> None:
    rows = _rows([0.01, 0.02, 0.03])
    rows[1]["date"] = rows[0]["date"]
    with pytest.raises(ScoreError, match="duplicate"):
        compute_topology_scores(rows)


def test_dates_are_normalised_and_sorted() -> None:
    rows = [
        {"date": "2024-01-03", "sp500_log_return": "0.03"},
        {"date": date(2024, 1, 2), "sp500_log_return": "0.02"},
    ]
    series = compute_topology_scores(rows, _small_config())
    assert [point.date for point in series.points] == ["2024-01-02", "2024-01-03"]


def test_causality_prefix_matches_full_series() -> None:
    rows = _rows(_deterministic_returns(450))
    config = _small_config(reference_window=3)
    prefix = compute_topology_scores(rows[:300], config)
    full = compute_topology_scores(rows, config)

    for left, right in zip(prefix.points, full.points[: len(prefix.points)], strict=True):
        assert left == right
    assert prefix.cache_key != full.cache_key


def test_cache_key_is_content_and_config_bound() -> None:
    rows = _rows(_deterministic_returns(40))
    first = compute_topology_scores(rows, _small_config(reference_window=3))
    second = compute_topology_scores(rows, _small_config(reference_window=3))
    different_config = compute_topology_scores(rows, _small_config(reference_window=4))
    changed_rows = [dict(row) for row in rows]
    changed_rows[-1]["sp500_log_return"] = 0.5
    changed = compute_topology_scores(changed_rows, _small_config(reference_window=3))

    assert first.cache_key == second.cache_key
    assert first.config_hash == second.config_hash
    assert first.cache_key != different_config.cache_key
    assert first.cache_key != changed.cache_key


def test_write_scores_csv_is_deterministic_and_guards_identity(tmp_path: Path) -> None:
    rows = _rows(_deterministic_returns(40))
    series = compute_topology_scores(rows, _small_config(reference_window=3))
    first_path = tmp_path / "scores.csv"
    write_scores_csv(series, first_path)
    first_bytes = first_path.read_bytes()
    sidecar = tmp_path / "scores.csv.meta.json"
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["config_hash"] == series.config_hash
    assert metadata["cache_key"] == series.cache_key
    assert metadata["exploratory"] is True

    # Same identity may be rewritten byte-identically.
    write_scores_csv(series, first_path)
    assert first_path.read_bytes() == first_bytes

    other = compute_topology_scores(rows, _small_config(reference_window=4))
    with pytest.raises(ScoreExportError):
        write_scores_csv(other, first_path)


def test_refuses_to_overwrite_an_unidentified_csv(tmp_path: Path) -> None:
    rows = _rows(_deterministic_returns(40))
    series = compute_topology_scores(rows, _small_config(reference_window=3))
    path = tmp_path / "scores.csv"
    path.write_text("something else\n", encoding="utf-8")
    with pytest.raises(ScoreExportError):
        write_scores_csv(series, path)


def test_frozen_default_serialises_expected_metadata() -> None:
    assert DEFAULT_CONFIG.window_sessions == 60
    assert DEFAULT_CONFIG.reference_window == 252
    assert DEFAULT_CONFIG.algorithm_version
    assert isinstance(DEFAULT_CONFIG_HASH, str) and len(DEFAULT_CONFIG_HASH) == 64
    assert __version__


def test_scores_csv_matches_contract_columns(tmp_path: Path) -> None:
    rows = _rows(_deterministic_returns(40))
    series = compute_topology_scores(rows, _small_config(reference_window=3))
    path = tmp_path / "scores.csv"
    write_scores_csv(series, path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        assert set(reader.fieldnames) == {
            "date",
            "sp500_log_return",
            "L",
            "D",
            "score",
            "state",
            "h1_count",
            "reason",
        }
        rows_read = list(reader)
    assert len(rows_read) == len(series.points)


def test_tda_columns_contract_is_available() -> None:
    # The score loader consumes tda_daily rows; keep the contract visible.
    assert "date" in TDA_DAILY_COLUMNS
    assert "sp500_log_return" in TDA_DAILY_COLUMNS
