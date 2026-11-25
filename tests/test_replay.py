"""Replay integrity tests (RE01, acceptance A03)."""

from __future__ import annotations

import copy
import json
from datetime import date as date_type

import pytest

from topomarket.ui.dashboard import DashboardSelection, toggle_blind, toggle_reveal
from topomarket.ui.panels import OUTCOME_HORIZON, build_screen_payloads, load_dashboard_data
from topomarket.ui.replay import build_outcome, build_replay_payload

CUTOFF = "2020-02-24"


@pytest.fixture(scope="module")
def data():
    return load_dashboard_data("demo")


def _selection(data, date: str = CUTOFF, *, mode: str = "replay", reveal: bool = False):
    return DashboardSelection(screen="replay", mode=mode, date=date, reveal=reveal)


def _all_date_strings(value) -> list[str]:
    """Collect every ISO-date-like string emitted anywhere in a payload."""

    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, str) and len(node) == 10 and node[4] == "-" and node[7] == "-":
            try:
                date_type.fromisoformat(node)
            except ValueError:
                return
            found.append(node)

    walk(value)
    return found


def test_blind_replay_contains_no_session_after_the_cutoff(data) -> None:
    payload = build_replay_payload(data, _selection(data))
    assert payload["blind"] is True
    assert payload["outcome"] is None
    emitted = _all_date_strings(payload)
    assert emitted, "replay payload should emit its history dates"
    assert max(emitted) <= CUTOFF
    assert payload["emitted_dates"]["outcome_start"] is None


def test_blind_replay_does_not_leak_the_horizon_dates(data) -> None:
    payload = build_replay_payload(data, _selection(data))
    serialized = json.dumps(payload, sort_keys=True)
    outcome = build_outcome(data, CUTOFF)
    for horizon_date in outcome["dates"]:
        assert horizon_date not in serialized


def test_mutating_future_rows_does_not_change_the_blind_payload(data) -> None:
    baseline = build_replay_payload(data, _selection(data))
    cutoff_index = data.session_dates.index(CUTOFF)
    mutated_rows = [copy.deepcopy(row) for row in data.rows]
    for row in mutated_rows[cutoff_index + 1 :]:
        row["sp500_close"] = "1.0"
        row["vix_close"] = "999.0"
        row["sp500_log_return"] = "-0.9"
    mutated = type(data)(
        profile=data.profile,
        data_dir=data.data_dir,
        active_data_dir=data.active_data_dir,
        session_dates=data.session_dates,
        rows=tuple(mutated_rows),
        price_rows=tuple(mutated_rows),
        industry_rows=data.industry_rows,
        snapshot_id=data.snapshot_id,
        score_points=data.score_points,
        evaluation_reports=data.evaluation_reports,
        demo=True,
    )
    changed = build_replay_payload(mutated, _selection(mutated))
    assert changed["price_history"] == baseline["price_history"]
    assert changed["score_history"] == baseline["score_history"]
    assert changed["alert_markers"] == baseline["alert_markers"]
    assert changed["outcome"] is None


def test_timeline_and_network_payloads_are_blind_safe(data) -> None:
    selection = _selection(data)
    payloads = build_screen_payloads(data, selection)
    structure = payloads["structure"]
    emitted = _all_date_strings(structure)
    assert max(emitted) <= CUTOFF
    assert structure["timeline"]["dates"][-1] == CUTOFF
    assert structure["network"]["window"]["end"] <= CUTOFF


def test_reveal_adds_exactly_the_selected_20_session_horizon(data) -> None:
    selection = _selection(data)
    revealed = toggle_reveal(selection)
    payload = build_replay_payload(data, revealed)
    assert payload["blind"] is False
    assert payload["revealed"] is True
    outcome = payload["outcome"]
    assert outcome is not None
    assert len(outcome["dates"]) == OUTCOME_HORIZON == 20
    assert outcome["origin"]["date"] == CUTOFF
    assert outcome["dates"][0] > CUTOFF
    assert outcome["pending"] is False
    assert outcome["target"] in (0, 1)


def test_outcome_layer_numbers_are_internally_consistent(data) -> None:
    outcome = build_outcome(data, CUTOFF)
    origin = outcome["origin"]["close"]
    boundary = outcome["boundary"]["close"]
    assert boundary == pytest.approx(origin * 0.9)
    closes = [value for value in outcome["closes"] if value is not None]
    assert outcome["lowest"]["close"] == min(closes)
    assert outcome["max_decline"] == pytest.approx((origin - min(closes)) / origin)
    breaches = [value for value in outcome["closes"] if value is not None and value <= boundary]
    if breaches:
        assert outcome["first_breach"] is not None
        assert outcome["first_breach"]["close"] == pytest.approx(breaches[0])
        first_index = next(
            index
            for index, value in enumerate(outcome["closes"])
            if value is not None and value <= boundary
        )
        assert outcome["first_breach"]["date"] == outcome["dates"][first_index]
    assert 0.0 <= outcome["max_decline"] <= 1.0


def test_pending_outcome_is_reported_when_horizon_is_incomplete(data) -> None:
    latest = data.session_dates[-1]
    payload = build_replay_payload(data, _selection(data, latest, reveal=True))
    outcome = payload["outcome"]
    assert outcome is not None
    assert outcome["pending"] is True
    assert outcome["horizon_sessions"] < OUTCOME_HORIZON
    assert outcome["target"] is None
    assert "pending" in payload["accessible_summary"].lower()


def test_hide_removes_the_outcome_payload(data) -> None:
    selection = _selection(data)
    revealed = toggle_reveal(selection)
    payload = build_replay_payload(data, revealed)
    hidden = toggle_blind(revealed)
    payload_hidden = build_replay_payload(data, hidden)
    assert payload["outcome"] is not None
    assert payload_hidden["outcome"] is None
    assert (
        "20" not in json.dumps(payload_hidden.get("outcome")) or payload_hidden["outcome"] is None
    )


def test_changing_date_resets_reveal_and_hides_the_outcome(data) -> None:
    selection = toggle_reveal(_selection(data))
    assert selection.reveal is True
    moved = selection.with_date("2020-03-13")
    assert moved.reveal is False
    payload = build_replay_payload(data, moved)
    assert payload["blind"] is True
    assert payload["outcome"] is None


def test_changing_screen_preserves_the_date(data) -> None:
    selection = _selection(data)
    moved = selection.with_screen("validation")
    assert moved.date == CUTOFF


def test_replay_alerts_are_sliced_by_cutoff(data) -> None:
    payload = build_replay_payload(data, _selection(data))
    alerts = payload["alert_markers"]
    assert alerts
    assert all(alert["date"] <= CUTOFF for alert in alerts)
    assert payload["alert"]["is_alert"] in (True, False)


def test_outcome_available_flag_is_stable_without_revealing(data) -> None:
    blind = build_replay_payload(data, _selection(data))
    assert blind["reveal_available"] is True
    assert blind["outcome"] is None
    assert "outcome_start" in blind["emitted_dates"]


def test_unknown_date_is_rejected(data) -> None:
    from topomarket.ui.panels import DashboardDataError

    selection = DashboardSelection(screen="replay", mode="replay", date="1999-01-01")
    with pytest.raises(DashboardDataError):
        build_replay_payload(data, selection)
