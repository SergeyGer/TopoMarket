"""EV01 evaluation-contract regression tests (acceptance check A05).

Every test pins one sentence of the EV01 requirement:

* the exact 10% / day-20 label boundary and the day-21 exclusion;
* early-alert credit: own positive label, breach ownership, 1..20 session lead,
  one credit per episode, preserved late/duplicate statuses and pending labels;
* average precision over the complete eligible scored daily series with tied
  scores evaluated as one block, compared with a trusted implementation;
* common eligible dates shared by every compared method;
* the silent-policy fallback when no calibration threshold qualifies.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import topomarket.analysis.evaluation as evaluation
from topomarket.analysis.alerts import (
    Alert,
    AlertError,
    AlertPolicy,
    MethodReading,
    average_precision,
    calibrate_method,
    evaluate_alerts,
    freeze_policy,
    generate_alerts,
    readings_from_rows,
    readings_from_scores,
)
from topomarket.analysis.labels import (
    BreachEpisodeSeries,
    build_breach_episodes,
    build_target_labels,
    match_alerts,
)


def _business_days(count: int, start: date = date(2024, 1, 1)) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _rows(closes: list[float], start: date = date(2024, 1, 1)) -> list[dict]:
    days = _business_days(len(closes), start)
    rows: list[dict] = []
    previous: float | None = None
    for day, close in zip(days, closes, strict=True):
        rows.append(
            {
                "date": day.isoformat(),
                "sp500_close": close,
                "sp500_log_return": (
                    "" if previous is None else f"{math.log(close / previous):.12f}"
                ),
                "vix_close": 20.0,
            }
        )
        previous = close
    return rows


def _credit_rows() -> list[dict]:
    """52 sessions with three chained-out breach episodes and crafted alerts.

    Episode onsets are 2024-01-02 (index 1), 2024-02-05 (index 25) and
    2024-03-05 (index 46); the gaps (24 and 21 sessions) keep them separate.
    The origin close at index 10 is low enough that its own 20-session label is
    negative even though episode 25 starts 15 sessions later, and the close at
    index 34 leaves its own label pending while episode 46 starts 12 sessions
    later.
    """

    closes = [100.0] * 52
    closes[1] = 89.5
    closes[10] = 95.0
    closes[25] = 89.5
    closes[34] = 95.0
    closes[46] = 89.5
    return _rows(closes)


def _alert(rows: list[dict], index: int) -> Alert:
    return Alert(rows[index]["date"], index, 99.0, "tda")


# ---------------------------------------------------------------------------
# Label boundaries
# ---------------------------------------------------------------------------


def test_positive_label_requires_close_at_or_below_ninety_percent() -> None:
    dates = _business_days(21)
    closes = [100.0] * 21
    closes[20] = 90.0  # exactly 10% below the origin close on day 20

    labels = build_target_labels(dates, closes)

    assert labels[0].target == 1
    assert labels[0].status == "positive"
    assert labels[0].breach_index == 20
    assert labels[0].sessions_to_breach == 20
    # Every origin that observes the exact boundary is positive too.
    assert all(label.target == 1 for label in labels[:20])
    assert labels.positive_count == 20
    assert labels[20].status == "pending"

    just_above = [100.0] * 21
    just_above[20] = 90.0000001
    labels_above = build_target_labels(dates, just_above)
    assert labels_above[0].target == 0
    assert labels_above[0].breach_index is None
    assert labels_above[0].status == "negative"


def test_day_twenty_is_inside_the_horizon_and_day_twenty_one_is_not() -> None:
    dates = _business_days(22)
    closes = [100.0] * 22
    closes[21] = 90.0  # day 21 from row 0, day 20 from row 1

    labels = build_target_labels(dates, closes)

    assert labels[0].target == 0
    assert labels[0].breach_index is None
    assert labels[1].target == 1
    assert labels[1].breach_index == 21
    assert labels[1].sessions_to_breach == 20


# ---------------------------------------------------------------------------
# Early-alert credit
# ---------------------------------------------------------------------------


def test_credit_requires_positive_label_owned_breach_and_twenty_session_lead() -> None:
    rows = _credit_rows()
    sessions = [row["date"] for row in rows]
    labels = build_target_labels(rows)
    episodes = build_breach_episodes(labels)
    assert [episode.start_index for episode in episodes] == [1, 25, 46]

    # Alert 5 is exactly twenty sessions before the owned episode onset 25,
    # alert 6 repeats that claim, alert 1 is late inside episode 1, alert 25 is
    # late inside episode 25, alert 10 has a negative own label and alert 34 has
    # a pending own label whose episode onset (46) is only twelve sessions away.
    result = match_alerts([1, 5, 6, 10, 25, 34], episodes, sessions, labels=labels)

    assert result.credit_rule == "label_positive_and_breach_owned"
    assert [
        (match.alert_index, match.episode_index, match.lead_sessions) for match in result.matches
    ] == [(5, 25, 20)]
    assert {outcome.alert.index: outcome.status for outcome in result.outcomes} == {
        1: "post_onset",
        5: "matched",
        6: "duplicate",
        10: "false_mature",
        25: "post_onset",
        34: "pending",
    }
    assert [alert.index for alert in result.duplicate_alerts] == [6]
    assert [alert.index for alert in result.post_onset_alerts] == [1, 25]
    assert [alert.index for alert in result.false_mature_alerts] == [10]
    assert [alert.index for alert in result.pending_alerts] == [34]
    # The episode is credited once; the other episodes stay missed.
    assert [episode.start_index for episode in result.missed_episodes] == [1, 46]

    metrics = evaluate_alerts(
        method="tda",
        alerts=[_alert(rows, index) for index in (10, 34, 25, 6, 5, 1)],
        episodes=episodes,
        labels=labels,
        sessions=sessions,
        start=sessions[0],
        end=sessions[-1],
    )
    assert metrics.credit_rule == "label_positive_and_breach_owned"
    assert metrics.matched == (
        {"alert_date": sessions[5], "episode_onset": sessions[25], "lead_sessions": 20},
    )
    assert metrics.episode_count == 3
    assert metrics.matched_count == 1
    assert metrics.episode_recall == pytest.approx(1 / 3)
    assert metrics.false_alerts == (sessions[10],)
    assert metrics.false_alert_count == 1
    assert metrics.false_alerts_per_year == pytest.approx(1 / (52 / 252.0))
    assert metrics.median_lead_sessions == 20.0
    assert metrics.pending_alerts == (sessions[34],)
    assert metrics.post_onset_alerts == (sessions[1], sessions[25])
    assert [example["episode_onset"] for example in metrics.missed_episodes] == [
        sessions[1],
        sessions[46],
    ]


def test_credit_lead_boundary_day_twenty_and_day_twenty_one() -> None:
    # A widened 25-session label horizon isolates the 1..20 onset rule: alert 6
    # is exactly twenty sessions before the breach, alert 5 is twenty-one.
    closes = [100.0] * 47
    closes[26] = 89.5
    rows = _rows(closes)
    sessions = [row["date"] for row in rows]
    labels = build_target_labels(rows, horizon_sessions=25)
    episodes = build_breach_episodes(labels)
    assert [episode.start_index for episode in episodes] == [26]
    assert labels[5].target == 1 and labels[6].target == 1

    result = match_alerts([5, 6], episodes, sessions, labels=labels, lead_sessions=20)

    statuses = {outcome.alert.index: outcome.status for outcome in result.outcomes}
    assert statuses == {5: "false_mature", 6: "matched"}
    assert [(match.alert_index, match.lead_sessions) for match in result.matches] == [(6, 20)]


def test_alert_cannot_claim_a_neighbouring_episodes_breach() -> None:
    # Two supplied episodes are three sessions apart (split from one label
    # chain): the alert close at index 4 breaches at index 9, which belongs to
    # the second episode, so the credit must follow its own breach - not the
    # earlier onset at index 6.
    closes = [100.0] * 30
    closes[4] = 95.0
    closes[6] = 90.0
    for index in range(9, 30):
        closes[index] = 85.4
    rows = _rows(closes)
    sessions = [row["date"] for row in rows]
    labels = build_target_labels(rows)
    assert labels[4].breach_index == 9
    assert labels[0].breach_index == 6

    first = build_breach_episodes([6], dates=sessions)
    second = build_breach_episodes([9], dates=sessions)
    episodes = BreachEpisodeSeries([first[0], second[0]], session_dates=sessions)

    result = match_alerts([4], episodes, sessions, labels=labels)

    assert [
        (match.alert_index, match.episode_index, match.lead_sessions) for match in result.matches
    ] == [(4, 9, 5)]
    assert [episode.start_index for episode in result.missed_episodes] == [6]


def test_label_negative_alert_is_not_credited_despite_a_near_episode() -> None:
    rows = _credit_rows()
    sessions = [row["date"] for row in rows]
    labels = build_target_labels(rows)
    episodes = build_breach_episodes(labels)
    assert labels[10].target == 0
    assert episodes[1].start_index - 10 == 15  # the episode onset is 15 sessions away

    result = match_alerts([10], episodes, sessions, labels=labels)

    assert result.matches == ()
    assert [outcome.status for outcome in result.outcomes] == ["false_mature"]
    assert [alert.index for alert in result.false_mature_alerts] == [10]
    assert episodes[1].start_index in [episode.start_index for episode in result.missed_episodes]


def test_pending_label_alert_stays_pending_even_with_a_near_episode() -> None:
    rows = _credit_rows()
    sessions = [row["date"] for row in rows]
    labels = build_target_labels(rows)
    episodes = build_breach_episodes(labels)
    assert labels[34].pending is True
    assert episodes[2].start_index - 34 == 12

    result = match_alerts([34], episodes, sessions, labels=labels)

    assert result.matches == ()
    assert [alert.index for alert in result.pending_alerts] == [34]
    assert [episode.start_index for episode in result.missed_episodes] == [1, 25, 46]


# ---------------------------------------------------------------------------
# Average precision
# ---------------------------------------------------------------------------


def test_average_precision_hand_computed_with_tied_scores() -> None:
    # Blocks: 0.9 -> 2 positives (precision 1, recall 2/3); 0.5 -> one positive
    # and one negative (precision 3/4, recall 1); 0.1 -> no positive.
    scored = [(0.9, True), (0.9, True), (0.5, True), (0.5, False), (0.1, False)]
    assert average_precision(scored) == pytest.approx(2 / 3 + 1 / 4)

    # A perfect ranking is 1.0, and an unlabelled/negative series is undefined.
    assert average_precision([(0.7, True), (0.2, False)]) == pytest.approx(1.0)
    assert average_precision([(0.7, False), (0.2, False)]) is None
    assert average_precision([]) is None
    with pytest.raises(AlertError):
        average_precision([(float("nan"), True)])


def test_average_precision_matches_sklearn_reference() -> None:
    sklearn_metrics = pytest.importorskip("sklearn.metrics")
    rng = random.Random(20261125)
    for _ in range(40):
        count = rng.randrange(1, 60)
        scores = [round(rng.random(), 2) for _ in range(count)]
        flags = [rng.random() < 0.35 for _ in range(count)]
        if not any(flags):
            flags[rng.randrange(count)] = True
        expected = sklearn_metrics.average_precision_score([int(flag) for flag in flags], scores)
        assert average_precision(list(zip(scores, flags, strict=True))) == pytest.approx(expected)


def test_average_precision_uses_the_complete_scored_series() -> None:
    rows = _credit_rows()
    sessions = [row["date"] for row in rows]
    labels = build_target_labels(rows)
    episodes = build_breach_episodes(labels)

    # Only the five sessions before the second episode carry a high score;
    # every other session scores zero.  45 labels are mature/observed (the
    # pending ones are excluded) and 39 of them are positive.
    readings = tuple(
        MethodReading(session, 100.0 if 20 <= index <= 24 else 0.0)
        for index, session in enumerate(sessions)
    )
    metrics = evaluate_alerts(
        method="tda",
        alerts=[_alert(rows, 10)],
        episodes=episodes,
        labels=labels,
        sessions=sessions,
        start=sessions[0],
        end=sessions[-1],
        readings=readings,
    )

    assert metrics.average_precision_sessions == 45
    assert metrics.average_precision_positives == 39
    # Block 100 (5 true positives, precision 1) + block 0 (34 of 40 remaining,
    # recall 1): 5/39 + 34/45.  An alert-only average precision would be 0.0.
    assert metrics.average_precision == pytest.approx(5 / 39 + 34 / 45)
    assert metrics.average_precision_reason is None
    assert metrics.event_prevalence == pytest.approx(39 / 45)


def test_average_precision_without_positive_labels_is_null_with_reason() -> None:
    rows = _rows([100.0] * 40)
    sessions = [row["date"] for row in rows]
    labels = build_target_labels(rows)
    episodes = build_breach_episodes(labels)
    readings = tuple(MethodReading(session, 1.0) for session in sessions)

    metrics = evaluate_alerts(
        method="vix",
        alerts=(),
        episodes=episodes,
        labels=labels,
        sessions=sessions,
        start=sessions[0],
        end=sessions[-1],
        readings=readings,
    )

    assert metrics.average_precision is None
    assert metrics.average_precision_positives == 0
    assert metrics.average_precision_sessions == 20
    assert metrics.average_precision_reason
    assert "no positive target labels" in metrics.average_precision_reason


# ---------------------------------------------------------------------------
# Common eligible dates and report provenance
# ---------------------------------------------------------------------------


def _report_rows(days: int = 3200) -> list[dict]:
    start = date(2005, 1, 3)
    days_list = _business_days(days, start)
    closes: list[float] = []
    price = 1000.0
    for index in range(days):
        phase = index % 400
        if 300 <= phase < 315:
            price *= 0.978
        elif 315 <= phase < 340:
            price *= 1.0005
        else:
            price *= 1.0 + 0.0003 * math.sin(index / 11.0)
        closes.append(price)
    rows: list[dict] = []
    previous: float | None = None
    for index, (day, close) in enumerate(zip(days_list, closes, strict=True)):
        vix = 16.0 + 6.0 * math.sin(index / 19.0)
        rows.append(
            {
                "date": day.isoformat(),
                "sp500_close": f"{close:.10f}",
                "sp500_log_return": (
                    "" if previous is None else f"{math.log(close / previous):.12f}"
                ),
                # Deliberate gaps keep the three methods' date coverage apart.
                "vix_close": "" if index % 37 == 5 else f"{vix:.6f}",
            }
        )
        previous = close
    return rows


class _ScoreSeries:
    """Scored TDA points with periodic warm-up gaps."""

    def __init__(self, rows: list[dict]) -> None:
        self.points = [
            SimpleNamespace(
                date=row["date"],
                state="warming_up" if index % 23 == 0 else "scored",
                score=50.0 + 40.0 * math.sin(index / 29.0),
            )
            for index, row in enumerate(rows)
        ]


@pytest.fixture()
def compact_report(monkeypatch: pytest.MonkeyPatch) -> dict:
    """A compact but complete report on a shortened out-of-sample window."""

    monkeypatch.setattr(evaluation, "TEST_START", "2015-01-01")
    rows = _report_rows()
    return evaluation.build_evaluation_report(
        rows,
        score_series=_ScoreSeries(rows),
        config_hash="cfg-ev01",
        snapshot_id="snap-ev01",
        seed=3,
    )


def test_report_scores_every_method_on_common_eligible_dates(compact_report: dict) -> None:
    report = compact_report
    rows = _report_rows()
    labels = build_target_labels(rows)
    series = _ScoreSeries(rows)
    test_start = "2015-01-01"
    test_end = report["periods"]["test"]["end"]

    mature = {label.date for label in labels if label.status != "pending"}
    tda_dates = {reading.date for reading in readings_from_scores(series.points)}
    vix_dates = {reading.date for reading in readings_from_rows(rows, "vix")}
    vol_dates = {reading.date for reading in readings_from_rows(rows, "realized_vol")}
    expected = {
        session
        for session in tda_dates & vix_dates & vol_dates
        if session in mature and test_start <= session <= test_end
    }

    common = report["common_eligible_dates"]
    assert common["session_count"] == len(expected)
    assert common["start"] == min(expected)
    assert common["end"] == max(expected)
    assert sorted(common["methods"]) == ["realized_vol", "tda", "vix"]
    assert common["method_session_counts"]["tda"] > common["session_count"]
    assert set(common["method_session_counts"]) == set(common["methods"])
    assert "intersection" in common["criteria"]
    for method, metrics in report["metrics"].items():
        assert metrics["average_precision_sessions"] == len(expected), method
        assert metrics["credit_rule"] == "label_positive_and_breach_owned"
        assert metrics["silent_policy"] is False
    # Frozen validation cutoffs and the purge boundary are unchanged.
    assert report["purged_validation_sessions"] == 20
    for calibration in report["calibrations"].values():
        assert calibration["validation_start"] == "2005-01-01"
        assert calibration["validation_end"] == "2013-12-31"
        assert calibration["calibrated"] is True
    assert report["credit_rule"] == "label_positive_and_breach_owned"
    assert report["bootstrap"]["tda_false_alerts_per_year"]["valid_replicates"] > 0


# ---------------------------------------------------------------------------
# Silent policy
# ---------------------------------------------------------------------------


def _unqualified_calibration_fixture() -> tuple[list[dict], list[str], tuple[MethodReading, ...]]:
    closes = [100.0] * 200
    for index in range(60, 90):
        closes[index] = 100.0 * 0.975 ** (index - 59)
    for index in range(90, 200):
        closes[index] = closes[89] * 1.0002 ** (index - 89)
    rows = _rows(closes, start=date(2004, 1, 3))
    sessions = [row["date"] for row in rows]
    readings = tuple(
        MethodReading(session, float(index) / len(sessions) * 100.0)
        for index, session in enumerate(sessions)
    )
    return rows, sessions, readings


def test_no_qualifying_threshold_freezes_a_silent_policy() -> None:
    rows, sessions, readings = _unqualified_calibration_fixture()
    labels = build_target_labels(rows)

    calibration = calibrate_method(
        method="vix",
        readings=readings,
        labels=labels,
        sessions=sessions,
        config_hash="cfg",
        validation_start=sessions[40],
        validation_end=sessions[170],
    )

    assert calibration.calibrated is False
    assert calibration.silent is True
    assert calibration.selected is None
    assert calibration.cutoff is None
    assert calibration.percentile is None
    assert calibration.candidates
    assert all(candidate.constrained for candidate in calibration.candidates)
    assert calibration.reason
    assert "false-alert constraint" in calibration.reason
    assert "silent policy" in calibration.reason

    policy = freeze_policy(calibration)
    assert policy.silent is True
    assert policy.cutoff is None
    assert policy.policy_hash()
    assert AlertPolicy.from_dict(policy.as_dict()).policy_hash() == policy.policy_hash()
    assert generate_alerts(readings, sessions, policy) == ()

    evaluation_result = evaluate_alerts(
        method="vix",
        alerts=(),
        episodes=build_breach_episodes(labels),
        labels=labels,
        sessions=sessions,
        start=sessions[40],
        end=sessions[170],
        policy=policy,
        readings=readings,
    )
    assert evaluation_result.silent_policy is True
    assert evaluation_result.alerts == ()
    assert evaluation_result.false_alert_count == 0
    assert evaluation_result.average_precision is not None


def test_silent_policy_carries_no_cutoff_or_percentile() -> None:
    with pytest.raises(AlertError, match="silent policy"):
        AlertPolicy(method="vix", cutoff=1.0, silent=True)
    with pytest.raises(AlertError, match="cutoff is required"):
        AlertPolicy(method="vix", cutoff=None)
    with pytest.raises(AlertError, match="silent policy"):
        AlertPolicy(method="vix", cutoff=None, percentile=95.0, silent=True)


def test_report_records_a_silent_policy_and_still_reports_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_calibrate = evaluation.calibrate_method
    reason = "forced silent policy for test"

    def fake_calibrate(*, method: str, **kwargs: object):
        result = real_calibrate(method=method, **kwargs)
        if method != "tda":
            return result
        return replace(
            result,
            calibrated=False,
            silent=True,
            reason=reason,
            selected=None,
            percentile=None,
            cutoff=None,
            episode_recall=None,
            false_alerts_per_year=None,
            calibration_hash="forced-silent",
        )

    monkeypatch.setattr(evaluation, "calibrate_method", fake_calibrate)
    monkeypatch.setattr(evaluation, "TEST_START", "2015-01-01")
    rows = _report_rows()
    report = evaluation.build_evaluation_report(
        rows,
        score_series=_ScoreSeries(rows),
        config_hash="cfg-ev01",
        snapshot_id="snap-ev01",
        seed=3,
    )

    assert report["silent_policies"] == {"tda": reason}
    policy = report["policies"]["tda"]
    assert policy["silent"] is True
    assert policy["cutoff"] is None
    assert report["calibrations"]["tda"]["silent"] is True
    assert report["calibrations"]["tda"]["reason"] == reason
    metrics = report["metrics"]["tda"]
    assert metrics["silent_policy"] is True
    assert metrics["alerts"] == []
    assert metrics["false_alert_count"] == 0
    assert metrics["episode_recall"] == 0.0
    assert metrics["credit_rule"] == "label_positive_and_breach_owned"
    assert metrics["average_precision"] is not None
    assert metrics["average_precision_sessions"] == report["common_eligible_dates"]["session_count"]
    assert report["primary_method"] == "tda"


def test_r2_bootstrap_draws_keep_positions_and_multiplicity() -> None:
    """R2: blocks are drawn with replacement, trimmed to N and keep multiplicity."""

    import random as random_module
    from types import SimpleNamespace

    from topomarket.analysis.evaluation import (
        BOOTSTRAP_ALGORITHM,
        _block_bootstrap,
        _draw_block_positions,
    )

    starts = list(range(0, 30, 20))
    positions = _draw_block_positions(
        random_module.Random(42), starts=starts, block_count=4, block=20, position_count=60
    )
    assert len(positions) == 60
    assert all(0 <= position < 60 for position in positions)

    class ConstantRng:
        def randrange(self, low, high):
            return 0

    repeated = _draw_block_positions(
        ConstantRng(), starts=starts, block_count=4, block=20, position_count=60
    )
    assert len(repeated) == 60
    assert repeated.count(0) == 3  # same 20-position block fills the trimmed 60 positions
    assert repeated.count(0) > 1  # multiplicity retained instead of collapsing to a set

    def fake(**kwargs):
        return SimpleNamespace(
            matched=kwargs.get("matched", []),
            missed_episodes=kwargs.get("missed", []),
            false_alerts=kwargs.get("false", []),
        )

    dates = [f"2020-01-{day:02d}" for day in range(1, 25)]
    primary = fake(
        matched=[{"episode_onset": dates[10]}],
        missed=[{"episode_onset": dates[15]}],
        false=[dates[0], dates[1]],
    )
    comparator = fake(
        matched=[{"episode_onset": dates[10]}],
        missed=[{"episode_onset": dates[15]}],
        false=[dates[0], dates[1]],
    )
    result = _block_bootstrap(
        primary=primary,
        comparator=comparator,
        dates=dates,
        test_start=dates[0],
        test_end=dates[-1],
        seed=42,
        block_sessions=6,
        replicates=50,
    )
    assert result["tda_false_alerts_per_year"].valid_replicates == 50
    assert result["episode_recall_gain"].lower == 0.0
    assert result["episode_recall_gain"].upper == 0.0
    assert result["episode_recall_gain"].lower == result["episode_recall_gain"].upper
    assert BOOTSTRAP_ALGORITHM == "moving_block_with_replacement_v2"

    no_events = fake()
    absent = _block_bootstrap(
        primary=no_events,
        comparator=None,
        dates=dates,
        test_start=dates[0],
        test_end=dates[-1],
        seed=42,
        block_sessions=6,
        replicates=20,
    )
    assert absent["tda_episode_recall"].valid_replicates == 0
    assert absent["tda_false_alerts_per_year"].valid_replicates == 20
