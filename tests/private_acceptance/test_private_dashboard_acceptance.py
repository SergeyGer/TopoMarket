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
EXPECTED_ROWS = 9_250
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
    assert len(dashboard_data.session_dates) == EXPECTED_ROWS
    assert dashboard_data.snapshot_id
    selection = DashboardSelection(screen="data", sessions=dashboard_data.session_dates)
    payload = build_screen_payloads(dashboard_data, selection)["data"]
    assert payload["active_snapshot_id"] == dashboard_data.snapshot_id
    assert payload["sources"]
    for source in payload["sources"]:
        assert source.get("source_id")
        assert source.get("first_observation")
        assert source.get("last_observation")
    assert isinstance(payload["snapshots"], list)


def test_a7_march_2020_replay_blind_reveal_blind(dashboard_data) -> None:
    blind = DashboardSelection(
        screen="topology",
        mode="replay",
        date=REPLAY_DATE,
        sessions=dashboard_data.session_dates,
    )
    blind_payloads = build_screen_payloads(dashboard_data, blind)
    blind_overview = blind_payloads["overview"]
    assert blind_payloads["topology"]["outcome"] is None
    assert blind_overview["replay"]["blind"] is True

    revealed = toggle_reveal(blind)
    revealed_payloads = build_screen_payloads(dashboard_data, revealed)
    outcome = revealed_payloads["topology"]["outcome"]
    assert outcome is not None
    assert outcome["horizon_sessions"] == 20
    assert revealed_payloads["overview"]["score"] == blind_overview["score"]

    hidden = toggle_blind(revealed)
    assert build_screen_payloads(dashboard_data, hidden)["topology"]["outcome"] is None


def test_a7_keyboard_equivalents(dashboard_data) -> None:
    state = {
        "tm_screen": "overview",
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
