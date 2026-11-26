"""Executable checks for the mathematics reference in ``docs/MATHEMATICS.md``."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from topomarket.analysis.alerts import average_precision
from topomarket.analysis.evaluation import _draw_block_positions
from topomarket.analysis.labels import build_target_labels
from topomarket.analysis.mapper import mapper_intervals
from topomarket.topology import delay_embedding, window_topology
from topomarket.topology.score import _percent_rank

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_REPORT = ROOT / "showcase" / "reports" / "evaluation-showcase.json"


def test_60_returns_give_56_delay_points_in_causal_orientation() -> None:
    values = np.arange(60, dtype=float)
    embedded = delay_embedding(values)

    assert embedded.shape == (56, 3)
    np.testing.assert_array_equal(embedded[0], [0.0, 2.0, 4.0])
    np.testing.assert_array_equal(embedded[-1], [55.0, 57.0, 59.0])

    causal = np.array(
        [
            [values[position], values[position - 2], values[position - 4]]
            for position in range(4, 60)
        ]
    )
    # The forward cloud maps to the causal cloud by reversing coordinate order.
    np.testing.assert_array_equal(causal, embedded[:, ::-1])


def test_tied_midrank_189_below_and_6_tied_is_76_19() -> None:
    reference = [0.0] * 189 + [1.0] * 6 + [2.0] * 57
    assert len(reference) == 252

    score = _percent_rank(100.0, reference, 1.0, 252)

    assert score == pytest.approx(100 * (189 + 0.5 * 6) / 252)
    assert score == pytest.approx(76.19047619047619)
    assert round(score, 2) == 76.19


def test_valid_cloud_without_h1_is_zero_but_invalid_windows_are_unavailable() -> None:
    line_cloud = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    valid = window_topology(line_cloud)
    assert valid.available is True
    assert valid.h1_count == 0
    assert valid.L == 0.0

    zero_mad = window_topology(np.zeros(60))
    assert zero_mad.available is False
    assert "zero" in (zero_mad.reason or "")

    too_short = window_topology(np.zeros(59))
    assert too_short.available is False
    assert "too short" in (too_short.reason or "")


def test_mapper_cover_has_three_closed_overlapping_intervals() -> None:
    intervals = mapper_intervals(np.array([0.0, 1.0]))
    width = 1.0 / 2.2
    stride = 0.6 * width

    assert len(intervals) == 3
    np.testing.assert_allclose(
        [interval.bounds for interval in intervals],
        [(0.0, width), (stride, stride + width), (2.0 * stride, 1.0)],
    )
    assert intervals[0].contains(0.0)
    assert intervals[0].contains(width) and intervals[1].contains(width)
    assert intervals[0].contains(stride) and intervals[1].contains(stride)
    assert intervals[1].contains(2.0 * stride) and intervals[2].contains(2.0 * stride)
    assert intervals[1].contains(stride + width) and intervals[2].contains(stride + width)
    assert intervals[2].contains(1.0)

    equal = mapper_intervals(np.array([2.0, 2.0]))
    assert len(equal) == 1
    assert equal[0].bounds == (2.0, 2.0)


def test_exactly_080_qualifies_and_rounding_boundary_is_documented() -> None:
    assert (0.80 >= 0.80) is True
    assert (0.7999994 >= 0.80) is False
    assert (0.800001 >= 0.80) is True

    assert round(0.7999994, 6) == 0.799999
    assert round(0.7999996, 6) == 0.800000
    assert round(0.8000000, 6) == 0.800000


def test_day_20_is_inside_the_horizon_and_day_21_is_outside() -> None:
    dates = [f"2024-01-{day:02d}" for day in range(1, 23)]
    closes = [100.0] * 22
    closes[21] = 90.0

    labels = build_target_labels(dates, closes)

    assert labels[0].target == 0
    assert labels[0].breach_index is None
    assert labels[1].target == 1
    assert labels[1].breach_index == 21
    assert labels[1].sessions_to_breach == 20


def test_forced_duplicate_bootstrap_blocks_keep_multiplicity() -> None:
    class ConstantRng:
        def randrange(self, low: int, high: int) -> int:
            del low, high
            return 0

    positions = _draw_block_positions(
        ConstantRng(), starts=[0, 20], block_count=4, block=20, position_count=60
    )
    weights = Counter(positions)

    assert len(positions) == 60
    assert weights[0] == 3
    assert weights[19] == 3
    assert weights[20] == 0
    assert sum(weights.values()) == 60


def test_tied_average_precision_uses_one_block() -> None:
    scored = [(0.9, True), (0.5, True), (0.5, False), (0.1, False)]
    assert average_precision(scored) == pytest.approx(5.0 / 6.0)
    assert average_precision([(0.7, False), (0.2, False)]) is None


def test_public_showcase_matches_the_reference_figures() -> None:
    report = json.loads(SHOWCASE_REPORT.read_text(encoding="utf-8"))

    assert report["schema_version"] == 2
    assert report["report_version"] == "1.1"
    assert report["calibration_version"] == "F01-corrected-v1"
    assert report["purged_validation_sessions"] == 20
    assert report["provenance"]["bootstrap_algorithm"] == "moving_block_with_replacement_v2"
    assert report["common_eligible_dates"]["session_count"] == 3306

    tda = report["metrics"]["tda"]
    assert tda["episode_count"] == 3
    assert tda["matched_count"] == 0
    assert tda["episode_recall"] == 0.0
    assert tda["average_precision"] == pytest.approx(0.015397765713962076)

    vix = report["metrics"]["vix"]
    assert vix["matched_count"] == 1
    assert vix["episode_recall"] == pytest.approx(1.0 / 3.0)

    volatility = report["metrics"]["realized_vol"]
    assert volatility["matched_count"] == 0
    assert report["evidence"]["wording"] == "Experimental market anomaly"
