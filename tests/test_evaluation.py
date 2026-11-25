"""Tests for the Step 6 evaluation report, bootstrap and evidence wording."""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from topomarket.analysis.alerts import AlertEvaluation
from topomarket.analysis.evaluation import (
    BOOTSTRAP_REPLICATES,
    TEST_START,
    BootstrapInterval,
    EvaluationError,
    build_evaluation_report,
    evidence_wording,
    report_digest,
    write_evaluation_report,
)
from topomarket.analysis.ledger import ForecastLedger


def business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def build_evaluation_rows() -> list[dict]:
    """Deterministic 1990-2016 rows with several sharp drawdowns."""
    days = business_days(date(1990, 1, 2), date(2016, 12, 30))
    prices: list[float] = []
    price = 100.0
    for index in range(len(days)):
        phase = index % 900
        if 600 <= phase < 615:
            price *= 0.976
        elif 615 <= phase < 640:
            price *= 1.0003
        else:
            price *= 1.0 + 0.0002 * math.sin(index / 17.0)
        prices.append(price)
    rows: list[dict] = []
    previous: float | None = None
    for day, close in zip(days, prices, strict=True):
        vix = 15.0 + 5.0 * math.sin(len(rows) / 23.0)
        rows.append(
            {
                "date": day.isoformat(),
                "sp500_close": f"{close:.10f}",
                "sp500_log_return": (
                    "" if previous is None else f"{math.log(close / previous):.12f}"
                ),
                "vix_close": f"{vix:.6f}",
            }
        )
        previous = close
    return rows


class FakeScoreSeries:
    def __init__(self, rows: list[dict]) -> None:
        self.points = [
            SimpleNamespace(
                date=row["date"],
                state="scored",
                score=50.0 + 40.0 * math.sin(index / 31.0),
            )
            for index, row in enumerate(rows)
        ]


def test_report_has_expected_sections_and_provenance(tmp_path: Path) -> None:
    rows = build_evaluation_rows()
    series = FakeScoreSeries(rows)
    report = build_evaluation_report(
        rows,
        score_series=series,
        config_hash="cfg-1",
        snapshot_id="snap-1",
        seed=7,
    )
    assert report["snapshot_id"] == "snap-1"
    assert report["seed"] == 7
    assert report["row_count"] == len(rows)
    assert "tda" in report["methods"]
    assert "vix" in report["methods"]
    assert "realized_vol" in report["methods"]
    assert report["periods"]["test"]["start"] == TEST_START
    assert report["calibrations"]
    assert report["policies"]
    for method in report["methods"]:
        metrics = report["metrics"][method]
        assert metrics["snapshot_id"] == "snap-1"
        assert {"episode_recall", "false_alerts_per_year", "average_precision"} <= set(metrics)
        assert {
            "average_precision_sessions",
            "average_precision_positives",
            "average_precision_reason",
            "credit_rule",
            "silent_policy",
        } <= set(metrics)
        assert metrics["credit_rule"] == "label_positive_and_breach_owned"
        assert metrics["average_precision_sessions"] > 0
    assert report["bootstrap"]["episode_recall_gain"]["total_replicates"] == BOOTSTRAP_REPLICATES
    assert report["evidence"]["wording"] in {
        "Experimental market anomaly",
        "Historical early-warning evidence",
    }
    assert set(report["examples"]) == set(report["methods"])
    assert isinstance(report["censored_episodes"], list)
    assert isinstance(report["purged_validation_sessions"], int)
    # EV01: the report records the common eligible window and the credit rule.
    assert report["credit_rule"] == "label_positive_and_breach_owned"
    common = report["common_eligible_dates"]
    assert common["session_count"] > 0
    assert common["start"] >= TEST_START
    assert common["end"] <= report["periods"]["test"]["end"]
    assert sorted(common["methods"]) == sorted(report["methods"])
    assert set(common["method_session_counts"]) == set(common["methods"])
    assert all(
        count >= common["session_count"] for count in common["method_session_counts"].values()
    )
    assert isinstance(report["silent_policies"], dict)


def test_report_digest_is_deterministic(tmp_path: Path) -> None:
    rows = build_evaluation_rows()
    series = FakeScoreSeries(rows)
    first = build_evaluation_report(rows, score_series=series, snapshot_id="s", seed=11)
    second = build_evaluation_report(
        rows, score_series=FakeScoreSeries(rows), snapshot_id="s", seed=11
    )
    assert report_digest(first) == report_digest(second)
    third = build_evaluation_report(rows, score_series=series, snapshot_id="s", seed=12)
    assert report_digest(third) != report_digest(first)


def test_report_writes_deterministic_json(tmp_path: Path) -> None:
    rows = build_evaluation_rows()
    report = build_evaluation_report(rows, score_series=FakeScoreSeries(rows), seed=3)
    path = tmp_path / "report.json"
    write_evaluation_report(report, path)
    first = path.read_bytes()
    write_evaluation_report(report, path)
    assert path.read_bytes() == first
    assert first.endswith(b"\n")


def test_ledger_append_is_append_only(tmp_path: Path) -> None:
    rows = build_evaluation_rows()
    ledger_path = tmp_path / "ledger.jsonl"
    report = build_evaluation_report(
        rows,
        score_series=FakeScoreSeries(rows),
        snapshot_id="snap-ledger",
        seed=5,
        ledger_path=ledger_path,
    )
    primary_alerts = report["metrics"][report["primary_method"]]["alerts"]
    records = ForecastLedger(ledger_path).read()
    assert len(records) == len(primary_alerts)
    assert all(record["snapshot_id"] == "snap-ledger" for record in records)
    assert all(record["policy_hash"] for record in records)
    before = ledger_path.read_bytes()
    report_again = build_evaluation_report(
        rows,
        score_series=FakeScoreSeries(rows),
        snapshot_id="snap-ledger",
        seed=5,
        ledger_path=ledger_path,
    )
    after = ledger_path.read_bytes()
    assert after.startswith(before)
    appended = len(ForecastLedger(ledger_path).read()) - len(records)
    assert appended == len(report_again["metrics"][report_again["primary_method"]]["alerts"])


def test_ablations_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = build_evaluation_rows()
    series = FakeScoreSeries(rows)

    def fake_topology_readings(rows, *, normalization=None):  # noqa: ANN001
        from topomarket.analysis.alerts import MethodReading

        return (
            tuple(MethodReading(row["date"], 50.0) for row in rows),
            series,
        )

    monkeypatch.setattr("topomarket.analysis.evaluation._topology_readings", fake_topology_readings)
    report = build_evaluation_report(
        rows,
        score_series=series,
        seed=2,
        include_ablations=True,
    )
    assert "ablations" in report
    assert "tda_unscaled" in report["ablations"]
    assert "tda_shuffled" in report["ablations"]


def _evaluation(
    *,
    episode_count: int,
    matched_count: int,
    false_rate: float | None,
    matches: tuple[dict, ...] = (),
) -> AlertEvaluation:
    recall = matched_count / episode_count if episode_count else None
    return AlertEvaluation(
        method="tda",
        start="2014-01-01",
        end="2020-01-01",
        eligible_sessions=1000,
        eligible_years=1000 / 252.0,
        alerts=(),
        alert_values=(),
        pending_alerts=(),
        matched=matches,
        false_alerts=(),
        missed_episodes=(),
        post_onset_alerts=(),
        episode_count=episode_count,
        matched_count=matched_count,
        episode_recall=recall,
        false_alert_count=0,
        false_alerts_per_year=false_rate,
        median_lead_sessions=None,
        min_lead_sessions=None,
        max_lead_sessions=None,
        average_precision=None,
        event_prevalence=None,
        losing_examples=(),
    )


def test_evidence_wording_rules() -> None:
    comparator = _evaluation(episode_count=8, matched_count=2, false_rate=1.0)
    positive_gain = BootstrapInterval(0.1, 0.4, 0.22, 1000, 1000)
    primary = _evaluation(
        episode_count=8,
        matched_count=6,
        false_rate=1.0,
        matches=tuple({"episode_onset": f"2015-01-0{i}", "lead_sessions": 3} for i in range(1, 7)),
    )
    historical = evidence_wording(primary, comparator, {"episode_recall_gain": positive_gain})
    assert historical.historical_evidence is True
    assert historical.wording == "Historical early-warning evidence"
    assert historical.limitations == ()

    zero_gain = BootstrapInterval(0.0, 0.2, 0.1, 1000, 1000)
    experimental = evidence_wording(primary, comparator, {"episode_recall_gain": zero_gain})
    assert experimental.historical_evidence is False
    assert experimental.wording == "Experimental market anomaly"
    assert experimental.limitations

    few_episodes = _evaluation(episode_count=2, matched_count=2, false_rate=0.0)
    few = evidence_wording(few_episodes, comparator, {"episode_recall_gain": positive_gain})
    assert few.historical_evidence is False
    assert any("episodes" in limitation for limitation in few.limitations)


def test_missing_tda_and_comparator_is_an_error() -> None:
    rows = build_evaluation_rows()
    with pytest.raises(EvaluationError):
        build_evaluation_report(
            rows,
            score_series=SimpleNamespace(points=[]),
            seed=1,
        )
