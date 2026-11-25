"""Tests for the Step 6 alert policy and calibration layer."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from topomarket.analysis.alerts import (
    AlertError,
    AlertPolicy,
    MethodReading,
    calibrate_method,
    evaluate_alerts,
    freeze_policy,
    generate_alerts,
    percentile,
    readings_from_rows,
    readings_from_scores,
    validate_readings,
)
from topomarket.analysis.labels import build_breach_episodes, build_target_labels


def _business_days(count: int, start: date = date(2000, 1, 3)) -> list[date]:
    result: list[date] = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _crash_rows(
    count: int = 120,
    *,
    crash_start: int = 40,
    crash_days: int = 20,
    daily_drop: float = 0.975,
    start: date = date(2000, 1, 3),
) -> list[dict]:
    days = _business_days(count, start)
    closes: list[float] = []
    price = 100.0
    for index in range(count):
        if crash_start <= index < crash_start + crash_days:
            price *= daily_drop
        elif index >= crash_start + crash_days:
            price *= 1.0002
        closes.append(price)
    rows: list[dict] = []
    previous = None
    for day, close in zip(days, closes, strict=True):
        rows.append(
            {
                "date": day.isoformat(),
                "sp500_close": close,
                "sp500_log_return": ""
                if previous is None
                else f"{__import__('math').log(close / previous):.12f}",
                "vix_close": 20.0,
            }
        )
        previous = close
    return rows


def _session_dates(rows: list[dict]) -> list[str]:
    return [row["date"] for row in rows]


def test_percentile_linear_interpolation() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)
    assert percentile([1.0, 2.0], 50) == pytest.approx(1.5)
    assert percentile([5.0], 99) == 5.0
    with pytest.raises(AlertError):
        percentile([], 50)


def test_method_reading_dates_and_finiteness() -> None:
    reading = MethodReading("2024-01-02", "1.5")
    assert reading.value == 1.5
    assert reading.date == "2024-01-02"
    with pytest.raises(AlertError):
        MethodReading("2024-01-02", float("nan"))
    with pytest.raises(AlertError):
        validate_readings([MethodReading("2024-01-03", 1.0), MethodReading("2024-01-02", 2.0)])


def test_cooldown_is_twenty_sessions() -> None:
    sessions = [day.isoformat() for day in _business_days(100, date(2020, 1, 1))]
    readings = tuple(MethodReading(session, 10.0) for session in sessions)
    policy = AlertPolicy(method="vix", cutoff=5.0)
    alerts = generate_alerts(readings, sessions, policy)
    assert [alert.date for alert in alerts[:4]] == [
        sessions[0],
        sessions[20],
        sessions[40],
        sessions[60],
    ]
    assert len(alerts) == 5


def test_frozen_policy_round_trip_and_identity() -> None:
    policy = AlertPolicy(method="tda", cutoff=90.0, percentile=95.0, config_hash="abc")
    payload = policy.as_dict()
    assert payload["policy_hash"] == policy.policy_hash()
    restored = AlertPolicy.from_dict(payload)
    assert restored.policy_hash() == policy.policy_hash()
    changed = AlertPolicy(method="tda", cutoff=91.0, percentile=95.0, config_hash="abc")
    assert changed.policy_hash() != policy.policy_hash()
    with pytest.raises(AlertError):
        AlertPolicy.from_dict({**payload, "unknown": 1})


def test_readings_from_rows_vix_and_realized_volatility() -> None:
    rows = _crash_rows(60)
    vix = readings_from_rows(rows, "vix")
    volatility = readings_from_rows(rows, "realized_vol")
    assert len(vix) == 60
    assert len(volatility) == 60 - 20
    assert all(reading.value == pytest.approx(20.0) for reading in vix)
    assert all(reading.value >= 0.0 for reading in volatility)
    with pytest.raises(AlertError):
        readings_from_rows(rows, "tda")


def test_readings_from_scores_only_accepts_scored_points() -> None:
    class Point:
        def __init__(self, day: str, state: str, score: float | None) -> None:
            self.date = day
            self.state = state
            self.score = score

    points = [
        Point("2024-01-02", "scored", 50.0),
        Point("2024-01-03", "warming_up", 50.0),
        Point("2024-01-04", "unavailable", None),
        Point("2024-01-05", "scored", 60.0),
    ]
    readings = readings_from_scores(points)
    assert [(reading.date, reading.value) for reading in readings] == [
        ("2024-01-02", 50.0),
        ("2024-01-05", 60.0),
    ]
    with pytest.raises(AlertError):
        readings_from_scores([Point("2024-01-02", "scored", 101.0)])
    skipped = readings_from_scores([Point("2024-01-02", "ready", 50.0)])
    assert skipped == ()
    with pytest.raises(AlertError):
        readings_from_scores(
            [Point("2024-01-03", "scored", 50.0), Point("2024-01-02", "scored", 40.0)]
        )


def test_evaluate_alerts_matches_early_and_classifies_other_alerts() -> None:
    rows = _crash_rows(140, crash_start=50, crash_days=25)
    sessions = _session_dates(rows)
    labels = build_target_labels(rows)
    episodes = build_breach_episodes(labels)
    assert episodes

    class Alert:
        def __init__(self, index: int) -> None:
            self.index = index
            self.date = sessions[index]
            self.value = 99.0
            self.method = "tda"

    # index 35 is 15 sessions before the first breach (early), 60 is inside the
    # episode (post-onset), 0 has no future episode in its 20-session window,
    # and the last index is pending.
    alerts = [Alert(35), Alert(60), Alert(0), Alert(len(sessions) - 1)]
    evaluation = evaluate_alerts(
        method="tda",
        alerts=alerts,
        episodes=episodes,
        labels=labels,
        sessions=sessions,
        start=sessions[0],
        end=sessions[-1],
    )
    assert evaluation.matched, evaluation
    assert evaluation.post_onset_alerts
    assert evaluation.false_alerts
    assert evaluation.pending_alerts
    assert evaluation.episode_count >= 1
    assert evaluation.matched_count >= 1


def test_calibration_selects_a_candidate_and_marks_it() -> None:
    # Long validation window with one crash and a contiguous high-reading
    # block: the 85th-percentile cutoff alerts through the whole block and
    # breaks the false-alert constraint, while the higher percentiles keep
    # eight false alerts over ~4.5 years (<= 2/year) and qualify.
    rows = _crash_rows(1200, crash_start=600, crash_days=6, daily_drop=0.97, start=date(2004, 1, 1))
    sessions = _session_dates(rows)
    labels = build_target_labels(rows)
    high_block = range(590, 761)
    readings = tuple(
        MethodReading(session, 100.0 if index in high_block else 0.0)
        for index, session in enumerate(sessions)
    )
    calibration = calibrate_method(
        method="vix",
        readings=readings,
        labels=labels,
        sessions=sessions,
        config_hash="cfg",
        validation_start=sessions[20],
        validation_end=sessions[1180],
    )
    assert calibration.calibrated is True
    assert calibration.silent is False
    assert calibration.reason is None
    assert len(calibration.candidates) == 6
    selected = [candidate for candidate in calibration.candidates if candidate.selected]
    assert len(selected) == 1
    assert calibration.selected is not None
    assert calibration.selected.selected is True
    assert calibration.selected.percentile in (85.0, 90.0, 92.5, 95.0, 97.5, 99.0)
    # The constrained 85th-percentile candidate is never selected.
    assert [
        candidate.percentile for candidate in calibration.candidates if candidate.constrained
    ] == [85.0]
    assert calibration.selected.percentile != 85.0
    policy = freeze_policy(calibration)
    assert policy.method == "vix"
    assert policy.silent is False
    assert policy.cutoff is not None
    assert policy.policy_hash()


def test_calibration_hash_includes_sessions_and_years() -> None:
    rows_a = _crash_rows(200, crash_start=60, crash_days=30, start=date(2004, 1, 1))
    rows_b = _crash_rows(201, crash_start=60, crash_days=30, start=date(2004, 1, 1))
    sessions_a = _session_dates(rows_a)
    sessions_b = _session_dates(rows_b)

    def calibrate(rows, sessions):
        labels = build_target_labels(rows)
        readings = tuple(
            MethodReading(session, float(index) / len(sessions) * 100.0)
            for index, session in enumerate(sessions)
        )
        return calibrate_method(
            method="vix",
            readings=readings,
            labels=labels,
            sessions=sessions,
            config_hash="cfg",
            validation_start=sessions[40],
            validation_end=sessions[170],
        )

    first = calibrate(rows_a, sessions_a)
    second = calibrate(rows_b, sessions_b)
    assert first.calibration_hash
    assert first.session_digest != second.session_digest
    assert first.calibration_hash != second.calibration_hash


def _two_crash_rows(
    count: int = 4200,
    *,
    crash_starts: tuple[int, int] = (2000, 3200),
    crash_days: int = 25,
    daily_drop: float = 0.97,
) -> list[dict]:
    days = _business_days(count, date(2004, 1, 2))
    headings = []
    price = 100.0
    for index in range(count):
        if any(start <= index < start + crash_days for start in crash_starts):
            price *= daily_drop
        else:
            price *= 1.0012
        headings.append(price)
    rows: list[dict] = []
    previous = None
    for day, close in zip(days, headings, strict=True):
        rows.append(
            {
                "date": day.isoformat(),
                "sp500_close": close,
                "sp500_log_return": ""
                if previous is None
                else f"{__import__('math').log(close / previous):.12f}",
                "vix_close": 20.0,
            }
        )
        previous = close
    return rows


def test_calibration_recall_prefers_higher_recall_over_fewer_false_alerts() -> None:
    """F01 regression: recall must count unique matched episode onsets.

    Two eligible episodes are warned with 60-value windows; a 100-value candidate
    has one fewer false alert but recalls no episode. The corrected calibration
    must select the higher-recall candidate (97.5th percentile, 2/2 matched)
    instead of the lower-false-alert 99th percentile.
    """

    rows = _two_crash_rows()
    sessions = _session_dates(rows)
    labels = build_target_labels(rows)
    episodes = build_breach_episodes(labels)
    assert [episode.start_index for episode in episodes[:2]] == [2003, 3203]
    values = [0.0] * len(sessions)
    for episode in episodes[:2]:
        onset = episode.start_index
        for index in range(onset - 19, onset + 50):
            values[index] = 60.0
        for index in range(onset + 5, onset + 30):
            values[index] = 100.0
    for index in (300, 900, 1500):
        values[index] = 60.0
    far = [
        index
        for index in range(100, 4000, 140)
        if all(abs(index - episode.start_index) > 80 for episode in episodes)
    ]
    for index in far[:28]:
        values[index] = 100.0
    readings = tuple(
        MethodReading(session, value) for session, value in zip(sessions, values, strict=True)
    )
    calibration = calibrate_method(
        method="vix",
        readings=readings,
        labels=labels,
        sessions=sessions,
        config_hash="cfg",
        validation_start=sessions[30],
        validation_end=sessions[4150],
    )
    assert calibration.calibrated is True
    assert calibration.silent is False
    selected = calibration.selected
    assert selected is not None
    assert selected.percentile == 97.5
    assert selected.episode_count == 2
    assert selected.matched_count == 2
    assert selected.episode_recall == 1.0
    assert selected.false_alerts_per_year is not None
    assert selected.false_alerts_per_year <= 2.0
    candidates = {candidate.percentile: candidate for candidate in calibration.candidates}
    # The 99th percentile has fewer false alerts but no recall; the corrected
    # ordering still prefers the matched candidate.
    assert candidates[99.0].matched_count == 0
    assert candidates[99.0].false_count < selected.false_count
    assert candidates[99.0].constrained is False
