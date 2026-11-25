"""v1.1 evidence integrity: corrected calibration recalls, versioned reports, holdout isolation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from topomarket.analysis.evaluation import (
    CALIBRATION_VERSION,
    REPORT_VERSION,
    build_evaluation_report,
)

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "showcase"
REPORT = SHOWCASE / "reports" / "evaluation-showcase.json"
BASELINE = ROOT / "docs" / "reports" / "evaluation-v1.0-baseline.json"


class _Point:
    def __init__(self, day: str, state: str, score: float | None) -> None:
        self.date = day
        self.state = state
        self.score = score


class _ScoreSeries:
    def __init__(self, points: list[_Point]) -> None:
        self.points = tuple(points)


def _score_series() -> _ScoreSeries:
    points: list[_Point] = []
    with (SHOWCASE / "scores.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            score = row.get("score")
            points.append(
                _Point(
                    row["date"],
                    row.get("state") or "scored",
                    float(score) if score not in (None, "") else None,
                )
            )
    return _ScoreSeries(points)


def _showcase_rows() -> list[dict[str, str]]:
    with (SHOWCASE / "normalized" / "tda_daily.csv").open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def test_committed_report_is_versioned_and_keeps_the_v1_baseline() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert report["report_version"] == REPORT_VERSION == "1.1"
    assert report["calibration_version"] == CALIBRATION_VERSION == "F01-corrected-v1"
    assert report["schema_version"] == 2
    assert baseline["package_version"] == "1.0.0"
    provenance = report["provenance"]
    assert provenance["calibration_version"] == CALIBRATION_VERSION
    assert provenance["snapshot_id"] == "showcase-synthetic"
    assert set(provenance["policy_hashes"]) == {"tda", "vix", "realized_vol"}
    assert all(value for value in provenance["calibration_hashes"].values())
    comparison = report["calibration_comparison"]
    assert comparison["same_eligible_dates"] is True
    assert comparison["baseline"]["package_version"] == "1.0.0"
    methods = comparison["methods"]
    # The v1.0 code reported zero calibration recall for every candidate; the
    # corrected calibration credits matched validation episodes for VIX and
    # realized volatility. Holdout metrics and frozen policies do not change.
    assert methods["vix"]["calibration"]["before"]["episode_recall"] == 0.0
    assert methods["vix"]["calibration"]["after"]["episode_recall"] > 0.0
    assert methods["realized_vol"]["calibration"]["before"]["episode_recall"] == 0.0
    assert methods["realized_vol"]["calibration"]["after"]["episode_recall"] > 0.0
    for method in methods:
        assert methods[method]["policy_changed"] is False


def test_holdout_suffix_mutation_does_not_change_fitted_policies() -> None:
    rows = _showcase_rows()
    series = _score_series()
    baseline = build_evaluation_report(
        rows,
        score_series=series,
        config_hash="cfg",
        snapshot_id="showcase-synthetic",
        seed=42,
    )
    mutated = [dict(row) for row in rows]
    for row in mutated:
        if row["date"] >= "2014-01-01":
            row["sp500_close"] = f"{float(row['sp500_close']) * 1.07:.6f}"
    changed = build_evaluation_report(
        mutated,
        score_series=series,
        config_hash="cfg",
        snapshot_id="showcase-synthetic",
        seed=42,
    )
    assert changed["policies"] == baseline["policies"]
    assert changed["calibrations"] == baseline["calibrations"]
    assert changed["common_eligible_dates"] == baseline["common_eligible_dates"]
    assert changed["provenance"]["policy_hashes"] == baseline["provenance"]["policy_hashes"]
    # Labelled holdout outcomes may change with the mutated closes; the fitted
    # policy above must not.
    assert changed["metrics"] != baseline["metrics"]
