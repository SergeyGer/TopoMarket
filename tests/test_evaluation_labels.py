"""Focused tests for row-position target labels, episodes and alert matching."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from topomarket.analysis.labels import (
    AlertMatchError,
    BreachEpisodeSeries,
    EpisodeError,
    LabelError,
    LabelSeries,
    build_breach_episodes,
    build_target_labels,
    match_alerts,
    match_early_alerts,
    validate_dates,
)


def _dates(count: int) -> list[str]:
    start = date(2024, 1, 1)
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def _closes(count: int, *, price: float = 100.0) -> list[float]:
    return [price] * count


def test_inclusive_10_percent_threshold_and_first_breach() -> None:
    labels = build_target_labels(["2024-01-01", "2024-01-02", "2024-01-03"], [100.0, 95.0, 90.0])

    assert labels[0].target == 1
    assert labels[0].breach_index == 2
    assert labels[0].breach_date == "2024-01-03"
    assert labels[0].sessions_to_breach == 2

    dates = _dates(22)
    just_above = build_target_labels(dates, [100.0, 90.0001, *(_closes(20))])
    assert just_above[0].target == 0
    assert just_above[0].status == "negative"
    assert just_above[0].breach_index is None


def test_day_twenty_is_in_horizon_but_day_twenty_one_is_not() -> None:
    dates = _dates(22)
    # The only fall is at row 21: day 21 from row 0 and day 20 from row 1.
    closes = _closes(22)
    closes[21] = 90.0

    labels = build_target_labels(dates, closes)

    assert labels[0].target == 0  # row 21 is outside row 0's 20-session horizon
    assert labels[0].breach_index is None
    assert labels[1].target == 1  # row 21 is exactly day 20 from row 1
    assert labels[1].breach_index == 21
    assert labels[1].sessions_to_breach == 20


def test_pending_horizons_are_distinct_from_negative_labels() -> None:
    dates = _dates(22)
    labels = build_target_labels(dates, _closes(22))

    # Rows 0 and 1 observe the complete 20-session horizon; rows 2 onward do not.
    assert labels[0].status == labels[1].status == "negative"
    assert labels[0].target == labels[1].target == 0
    assert labels[2].status == "pending"
    assert labels[2].target is None
    assert [label.status for label in labels[-2:]] == ["pending", "pending"]
    assert labels.pending_count == 20
    assert labels.negative_count == 2
    assert labels.dates == tuple(dates)  # input order is preserved


def test_iso_dates_are_required_ordered_and_unique() -> None:
    with pytest.raises(LabelError, match="duplicate observation date"):
        build_target_labels(["2024-01-02", "2024-01-02"], [100.0, 99.0])

    with pytest.raises(LabelError, match="strictly increasing"):
        build_target_labels(["2024-01-02", "2024-01-01"], [100.0, 99.0])

    with pytest.raises(LabelError, match="ISO-8601"):
        build_target_labels(["01/02/2024"], [100.0])

    assert validate_dates([date(2024, 1, 1), "2024-01-02"]) == (
        "2024-01-01",
        "2024-01-02",
    )


def test_breach_dates_are_deduplicated() -> None:
    dates = _dates(30)
    episodes = build_breach_episodes(
        ["2024-01-06", "2024-01-06", "2024-01-06"],
        dates=dates,
    )

    assert isinstance(episodes, BreachEpisodeSeries)
    assert len(episodes) == 1
    assert episodes[0].breach_indices == (5,)
    assert episodes[0].breach_dates == ("2024-01-06",)


def test_breach_dates_require_full_sessions_to_measure_gaps() -> None:
    with pytest.raises(EpisodeError, match="session dates are required"):
        build_breach_episodes(["2024-01-02", "2024-01-23"])

    dates = _dates(30)
    same = build_breach_episodes(["2024-01-02", "2024-01-22"], dates=dates)
    split = build_breach_episodes(["2024-01-02", "2024-01-23"], dates=dates)

    # Gaps come from positions in the full session list, not from the order in
    # which the breach events were supplied.
    assert len(same) == 1
    assert same[0].breach_indices == (1, 21)
    assert len(split) == 2
    assert [episode.start_index for episode in split] == [1, 22]


def test_episode_origins_are_emitted_in_input_order() -> None:
    dates = _dates(4)
    labels = build_target_labels(dates, [90.0, 100.0, 90.0, 81.0])

    # Row 1 breaches on day 1, while earlier row 0 and later row 2 breach on
    # day 3.  All three belong to one episode but must stay in input order.
    assert labels[0].breach_index == 3
    assert labels[1].breach_index == 2
    assert labels[2].breach_index == 3

    episodes = build_breach_episodes(labels)

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.breach_indices == (2, 3)
    assert episode.origin_indices == (0, 1, 2)
    assert episode.origin_dates == (dates[0], dates[1], dates[2])
    assert episode.positive_origins == 3


def test_episode_chaining_uses_twenty_sessions_but_not_twenty_one() -> None:
    dates = _dates(80)

    same = build_breach_episodes([5, 25], dates=dates, gap_sessions=20)
    split = build_breach_episodes([5, 26], dates=dates, gap_sessions=20)

    assert len(same) == 1
    assert same[0].breach_indices == (5, 25)
    assert same[0].start_index == 5 and same[0].end_index == 25

    assert len(split) == 2
    assert split[0].breach_indices == (5,)
    assert split[1].breach_indices == (26,)
    assert split.onsets == (5, 26)


def test_episodes_report_positive_origin_counts() -> None:
    dates = _dates(40)
    closes = _closes(40)
    closes[5] = 90.0  # origins at rows 0-4 see this first breach within 20 sessions

    labels = build_target_labels(dates, closes)
    episodes = build_breach_episodes(labels)

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.positive_origins == 5
    assert episode.origin_indices == (0, 1, 2, 3, 4)
    assert episode.positive_origin_count == episode.n_positive_origins == 5
    assert labels.positive_count == 5


def test_matching_is_chronological_and_one_to_one() -> None:
    dates = _dates(60)
    episodes = build_breach_episodes([10, 31], dates=dates)

    result = match_alerts([1, 0], episodes, dates=dates, lead_sessions=40)

    # Alerts are processed by session, not input position, and each episode is
    # consumed at most once.
    assert [match.alert_index for match in result.matches] == [0, 1]
    assert [match.episode_index for match in result.matches] == [10, 31]
    assert [match.lead_sessions for match in result.matches] == [10, 30]
    assert result.match_count == 2
    assert result.missed_episodes == ()


def test_duplicate_and_post_onset_alerts_are_not_double_matched() -> None:
    dates = _dates(40)
    episodes = build_breach_episodes([10], dates=dates)

    duplicate = match_alerts([0, 0], episodes, dates=dates)
    assert len(duplicate.matches) == 1
    assert duplicate.matches[0].lead_sessions == 10
    assert [alert.index for alert in duplicate.duplicate_alerts] == [0]

    # A different session whose only eligible episode was already claimed is a
    # duplicate, not a mature false alarm.
    distinct_duplicate = match_alerts([0, 1], episodes, dates=dates)
    assert [match.alert_index for match in distinct_duplicate.matches] == [0]
    assert [alert.index for alert in distinct_duplicate.duplicate_alerts] == [1]
    assert distinct_duplicate.false_mature_alerts == ()

    post_onset = match_alerts([10], episodes, dates=dates)
    assert post_onset.matches == ()
    assert [alert.index for alert in post_onset.post_onset_alerts] == [10]

    # The alert after the stream ended is classified by its own horizon rather
    # than inheriting post-onset from the earlier episode.
    after_episode = match_alerts([11], episodes, dates=dates)
    assert after_episode.matches == ()
    assert after_episode.post_onset_alerts == ()
    assert [alert.index for alert in after_episode.false_mature_alerts] == [11]


def test_alerts_after_an_earlier_episode_use_their_own_horizon() -> None:
    dates = _dates(60)
    episodes = build_breach_episodes([10], dates=dates)

    mature = match_alerts([20], episodes, dates=dates)
    assert mature.matches == ()
    assert mature.post_onset_alerts == ()
    assert [alert.index for alert in mature.false_mature_alerts] == [20]
    assert mature.pending_alerts == ()

    pending = match_alerts([50], episodes, dates=dates)
    assert pending.matches == ()
    assert pending.post_onset_alerts == ()
    assert pending.false_mature_alerts == ()
    assert [alert.index for alert in pending.pending_alerts] == [50]


def test_false_mature_missed_and_pending_events_are_separate() -> None:
    dates = _dates(60)
    no_episodes = build_breach_episodes([], dates=dates)

    mature = match_alerts([0], no_episodes, dates=dates)
    assert mature.matches == ()
    assert [alert.index for alert in mature.false_mature_alerts] == [0]
    assert mature.pending_alerts == ()

    pending = match_alerts([50], no_episodes, dates=dates)
    assert pending.matches == ()
    assert pending.false_mature_alerts == ()
    assert [alert.index for alert in pending.pending_alerts] == [50]

    episodes = build_breach_episodes([10, 31], dates=dates)
    missed = match_alerts([0], episodes, dates=dates)
    assert [match.episode_index for match in missed.matches] == [10]
    assert [episode.start_index for episode in missed.missed_episodes] == [31]


def test_alerts_may_be_mappings_and_aliases_work() -> None:
    dates = _dates(40)
    episodes = build_breach_episodes([10], dates=dates)
    alerts = [
        {"date": "2024-01-01", "score": 99.0},
        {"date": "2024-01-11", "score": 100.0},
    ]

    result = match_early_alerts(alerts, episodes, dates=dates)

    assert len(result.matches) == 1
    assert result.matches[0].alert_date == "2024-01-01"
    assert result.matches[0].lead_sessions == 10
    assert [alert.index for alert in result.post_onset_alerts] == [10]
    assert result["matches"] == result.matches


def test_alert_dates_must_name_a_session() -> None:
    dates = _dates(30)
    episodes = build_breach_episodes([10], dates=dates)

    with pytest.raises(AlertMatchError, match="not one of"):
        match_alerts(["2024-02-15"], episodes, dates=dates)


def test_empty_inputs_return_empty_ordered_results() -> None:
    labels = build_target_labels([], [])
    episodes = build_breach_episodes(labels)
    result = match_alerts([], episodes, n_sessions=0)

    assert isinstance(labels, LabelSeries)
    assert labels == []
    assert episodes == []
    assert result.matches == ()
    assert result.missed_episodes == ()


def test_breach_episode_options_are_forwarded_to_target_labels() -> None:
    dates = _dates(30)
    closes = _closes(30)
    closes[3] = 85.0  # a 15% fall, inside the default threshold but not 20%

    assert build_breach_episodes(dates, closes, threshold=0.10)
    assert build_breach_episodes(dates, closes, threshold=0.20) == []

    horizon_dates = _dates(40)
    horizon_closes = _closes(40)
    horizon_closes[21] = 85.0

    default_horizon = build_breach_episodes(horizon_dates, horizon_closes)
    short_horizon = build_breach_episodes(horizon_dates, horizon_closes, horizon_sessions=10)

    assert default_horizon[0].breach_indices == (21,)
    assert default_horizon[0].positive_origins == 20
    assert short_horizon[0].breach_indices == (21,)
    assert short_horizon[0].positive_origins == 10


def test_unsorted_alerts_report_outcomes_and_classes_in_input_order() -> None:
    dates = _dates(60)
    episodes = build_breach_episodes([10], dates=dates)

    result = match_alerts([50, 20, 10, 0], episodes, dates=dates)

    # Matching consumes alerts by session, while per-alert reporting follows
    # the caller's input order.
    assert [match.alert_index for match in result.matches] == [0]
    assert [outcome.alert.index for outcome in result.outcomes] == [50, 20, 10, 0]
    assert [outcome.status for outcome in result.outcomes] == [
        "pending",
        "false_mature",
        "post_onset",
        "matched",
    ]
    assert [alert.index for alert in result.pending_alerts] == [50]
    assert [alert.index for alert in result.false_mature_alerts] == [20]
    assert [alert.index for alert in result.post_onset_alerts] == [10]
