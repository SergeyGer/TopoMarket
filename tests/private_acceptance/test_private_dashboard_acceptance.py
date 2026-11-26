"""Opt-in A7 acceptance checks for the interactive dashboard layer.

Uses the real private seed archive imported into a temporary directory:
data-screen provenance, March 2020 replay blind/reveal/blind, keyboard
selection and the cached date-change performance bound.
"""

from __future__ import annotations

import os
from pathlib import Path

import app
import pytest

from topomarket.data.adapters import import_sources
from topomarket.ui.dashboard import DashboardSelection, toggle_blind, toggle_reveal
from topomarket.ui.panels import build_screen_payloads, load_dashboard_data
from topomarket.ui.performance import CACHED_P95_LIMIT_MS, measure_cached_date_changes

SEED_ENV = "TOPOMARKET_SEED_DIR"
#: The dashboard now exposes the ordered index calendar (one row per price
#: observation); the joint analysis table and the industry coverage are shorter
#: and are asserted separately through the Data-screen calendar payload.
EXPECTED_INDEX_ROWS = 19_343
REPLAY_DATE = "2020-03-16"


def _seed_root() -> Path:
    value = os.environ.get(SEED_ENV)
    if not value:
        pytest.skip(f"{SEED_ENV} is not set; A7 acceptance checks are opt-in")
    root = Path(value)
    if not (root / "raw").is_dir():
        pytest.skip(f"{SEED_ENV} does not contain a raw/ seed directory")
    return root


@pytest.fixture(scope="module")
def dashboard_data(tmp_path_factory: pytest.TempPathFactory):
    seed_root = _seed_root()
    data_dir = tmp_path_factory.mktemp("dashboard") / "data"
    import_sources(seed_root / "raw", data_dir)
    return load_dashboard_data("private", data_dir=data_dir)


def test_a7_data_screen_shows_snapshot_and_sources(dashboard_data) -> None:
    # The audit's A7 fix: the dashboard exposes the index calendar, while the
    # joint table and industry coverage are shorter and reported separately.
    assert len(dashboard_data.session_dates) == EXPECTED_INDEX_ROWS
    assert dashboard_data.snapshot_id
    selection = DashboardSelection(screen="data", sessions=dashboard_data.session_dates)
    payload = build_screen_payloads(dashboard_data, selection)["data"]
    assert payload["snapshot_id"] == dashboard_data.snapshot_id
    assert payload["price_calendar_is_signal_calendar"] is True
    calendars = payload["calendars"]
    assert calendars["price"]["observations"] == EXPECTED_INDEX_ROWS
    assert calendars["price"]["last"] >= calendars["industry"]["last"]
    assert calendars["price"]["last"] == dashboard_data.session_dates[-1]
    assert calendars["industry"]["observations"] > 0
    assert payload["map_lags_price"] is True
    assert payload["sources"]
    for source in payload["sources"]:
        assert source.get("source_id")
        assert source.get("first_observation")
        assert source.get("last_observation")
    assert isinstance(payload["refresh"], dict)
    assert isinstance(getattr(dashboard_data, "snapshots", ()), (list, tuple))


def test_a7_march_2020_replay_blind_reveal_blind(dashboard_data) -> None:
    # Current Structure/Replay contract (the retired v1.0 "overview/topology"
    # screens are gone): blind payloads hide the outcome, reveal adds exactly the
    # 20-session layer and hiding removes it again.
    blind = DashboardSelection(
        screen="replay",
        mode="replay",
        date=REPLAY_DATE,
        sessions=dashboard_data.session_dates,
    )
    blind_payloads = build_screen_payloads(dashboard_data, blind, screens=("replay", "structure"))
    blind_replay = blind_payloads["replay"]
    assert blind_replay["blind"] is True
    assert blind_replay["outcome"] is None
    assert all(marker["status"] == "recorded" for marker in blind_replay["alert_markers"])

    # Future-data mutation: the blind payload must not change after rewriting
    # every price observation after the selected session.
    import copy

    original_rows = (copy.deepcopy(dashboard_data.rows), copy.deepcopy(dashboard_data.price_rows))
    try:
        for collection in (dashboard_data.rows, dashboard_data.price_rows):
            for row in collection:
                if str(row.get("date")) > REPLAY_DATE:
                    row["sp500_close"] = "1.0"
                    row["vix_close"] = "999.0"
        mutated_payloads = build_screen_payloads(
            dashboard_data, blind, screens=("replay", "structure")
        )
    finally:
        dashboard_data.rows, dashboard_data.price_rows = original_rows
    import json

    assert json.dumps(blind_replay, sort_keys=True) == json.dumps(
        mutated_payloads["replay"], sort_keys=True
    )

    revealed = toggle_reveal(blind)
    revealed_payloads = build_screen_payloads(dashboard_data, revealed, screens=("replay",))
    outcome = revealed_payloads["replay"]["outcome"]
    assert outcome is not None
    assert outcome["horizon_sessions"] == 20
    revealed_alert = revealed_payloads["replay"]["alert"]
    if revealed_alert.get("is_alert"):
        assert revealed_alert["retrospective"] is True
    else:  # no alert on this session: reveal must not invent one
        assert revealed_alert["is_alert"] is False
        assert revealed_alert["retrospective"] is False

    hidden = toggle_blind(revealed)
    hidden_payload = build_screen_payloads(dashboard_data, hidden, screens=("replay",))["replay"]
    assert hidden_payload["outcome"] is None
    assert hidden_payload["blind"] is True


def test_a7_keyboard_equivalents(dashboard_data) -> None:
    state = {
        "tm_screen": "structure",
        "tm_mode": "latest",
        "tm_date": dashboard_data.session_dates[1000],
        "tm_reveal": False,
        "tm_member": None,
        "tm_run": None,
    }
    updated = app.apply_action_to_state(state, "next_session", dashboard_data)
    assert updated.date == dashboard_data.session_dates[1001]
    member = app.apply_action_to_state(state, "next_member", dashboard_data)
    assert member.member is not None


def test_a7_cached_date_change_bound(dashboard_data) -> None:
    dates = [
        value
        for value in ("2020-03-13", "2020-03-16", "2020-03-17", "2020-03-18", "2020-03-19")
        if value in dashboard_data.date_index
    ]
    result = measure_cached_date_changes(dashboard_data, dates=dates, iterations=100)
    assert result["iterations"] == 100
    assert result["p95_ms"] <= CACHED_P95_LIMIT_MS
    assert result["environment"]["topomarket_version"]
    assert result["build"]["package_version"]
