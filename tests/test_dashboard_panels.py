"""Tests for the Step 7 dashboard data layer and screen payloads."""

from __future__ import annotations

import csv
import json
import math
from datetime import date, timedelta
from pathlib import Path

import app

from topomarket.analysis.industries import INDUSTRY_COLUMNS
from topomarket.ui.dashboard import (
    DashboardSelection,
    apply_keyboard_action,
    toggle_blind,
    toggle_reveal,
)
from topomarket.ui.panels import (
    OUTCOME_HORIZON,
    build_screen_payloads,
    load_dashboard_data,
)


def _business_days(start: date, end: date) -> list[date]:
    values: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return values


def _rows() -> list[dict[str, str]]:
    days = _business_days(date(2019, 1, 2), date(2020, 12, 31))
    rows: list[dict[str, str]] = []
    price = 100.0
    flags: list[str] = []
    for index, day in enumerate(days):
        if day.isoformat() == "2020-03-16":
            flags.append("crash")
        if flags and index < len(days):
            if "crash" in flags and day.isoformat() >= "2020-03-16" and index < len(days):
                if day <= date(2020, 4, 15):
                    price *= 0.994
                else:
                    price *= 1.0005
            else:
                price *= 1.0004
        else:
            price *= 1.0004
        row = {
            "date": day.isoformat(),
            "sp500_close": f"{price:.6f}",
            "sp500_log_return": "" if index == 0 else f"{math.log(price / (price / 1.0004)):.12f}",
            "vix_close": f"{15.0 + 10.0 * math.sin(index / 13.0):.6f}",
        }
        for column_index, column in enumerate(INDUSTRY_COLUMNS):
            row[column] = f"{0.002 * math.sin((index + column_index) / 9.0):.8f}"
        rows.append(row)
    return rows


def _write_data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    normalized = root / "normalized"
    normalized.mkdir(parents=True)
    rows = _rows()
    with (normalized / "tda_daily.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (root / "scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["date", "sp500_log_return", "L", "D", "score", "state", "h1_count", "reason"]
        )
        for index, row in enumerate(rows):
            writer.writerow(
                [
                    row["date"],
                    row["sp500_log_return"],
                    "0.1",
                    "0.2",
                    "80.0" if index % 2 else "20.0",
                    "scored",
                    "2",
                    "",
                ]
            )
    report = {
        "schema_version": 1,
        "snapshot_id": "snap-test",
        "seed": 42,
        "methods": ["tda", "vix"],
        "primary_method": "tda",
        "comparator_method": "vix",
        "periods": {"test": {"start": "2014-01-01", "end": "2020-12-31"}},
        "config_hash": "cfg-hash",
        "policies": {
            "tda": {
                "method": "tda",
                "cutoff": 90.0,
                "percentile": 95.0,
                "policy_hash": "policy-tda",
            },
            "vix": {
                "method": "vix",
                "cutoff": 60.0,
                "percentile": 99.0,
                "policy_hash": "policy-vix",
            },
        },
        "evidence": {"wording": "Experimental market anomaly", "historical_evidence": False},
        "metrics": {
            "tda": {
                "episode_recall": 0.5,
                "false_alerts_per_year": 1.0,
                "average_precision": 0.4,
                "median_lead_sessions": 10,
                "alerts": ["2020-03-10", "2020-03-11"],
            }
        },
        "examples": {
            "tda": {
                "matched": [
                    {"alert_date": "2020-03-10", "episode_onset": "2020-03-16", "lead_sessions": 4}
                ],
                "missed": [{"episode_onset": "2019-05-01"}],
                "false_alerts": ["2019-06-01"],
            }
        },
        "bootstrap": {
            "episode_recall_gain": {"lower": 0.0, "upper": 0.3, "valid_replicates": 1000}
        },
        "episode_count": 2,
        "resolved_episode_count": 2,
        "censored_episodes": [],
        "purged_validation_sessions": 20,
    }
    reports = root / "reports"
    reports.mkdir()
    (reports / "evaluation-test.json").write_text(json.dumps(report), encoding="utf-8")
    manifest = {
        "source_ids": ["fred_sp500", "cboe_vix", "french_12_industries"],
        "row_counts": {"fred_sp500": 10, "cboe_vix": 10, "french_12_industries": 10},
        "normalized_row_counts": {
            "sp500_daily": len(rows),
            "industries_daily": len(rows),
            "tda_daily": len(rows),
        },
        "latest_data_date": rows[-1]["date"],
    }
    (root / "import_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "parser_reports.json").write_text(
        json.dumps(
            {
                "by_source": {
                    "fred_sp500": {
                        "row_count": 10,
                        "first_observation": "2016-01-04",
                        "last_observation": "2020-12-31",
                    },
                    "cboe_vix": {
                        "row_count": 10,
                        "first_observation": "1990-01-02",
                        "last_observation": "2020-12-31",
                    },
                    "french_12_industries": {
                        "row_count": 10,
                        "first_observation": "1926-07-01",
                        "last_observation": "2020-12-31",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "normalized" / "schemas.json").write_text(
        json.dumps({"tables": {"tda_daily": {"columns": ["date", "sp500_close"]}}}),
        encoding="utf-8",
    )
    state = root / "state"
    state.mkdir()
    (state / "refresh_status.json").write_text(
        json.dumps(
            {
                "updated_at_utc": "2024-01-01T00:00:00Z",
                "published": True,
                "sources": {
                    "fred_sp500": {
                        "outcome": "updated",
                        "last_attempt_at": "2024-01-01T00:00:00Z",
                        "last_success_at": "2024-01-01T00:00:00Z",
                    },
                    "cboe_vix": {
                        "outcome": "failed",
                        "last_attempt_at": "2024-01-01T00:00:00Z",
                        "error": "timeout",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    snapshots = root / "snapshots" / "snap-test"
    snapshots.mkdir(parents=True)
    (snapshots / "refresh_manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": "snap-test",
                "revisions": [
                    {"date": "2020-03-16", "source_id": "fred_sp500", "field": "sp500_close"}
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_load_dashboard_data_private(tmp_path: Path) -> None:
    root = _write_data_dir(tmp_path)
    data = load_dashboard_data("private", data_dir=root)
    assert data.profile == "private"
    assert len(data.session_dates) > 60
    assert data.score_points
    assert data.evaluation_reports
    assert data.sources
    assert data.revisions


def test_screen_payloads_have_expected_shape(tmp_path: Path) -> None:
    root = _write_data_dir(tmp_path)
    data = load_dashboard_data("private", data_dir=root)
    date = "2020-03-16"
    selection = DashboardSelection(screen="overview", date=date, sessions=data.session_dates)
    payloads = build_screen_payloads(data, selection)
    assert set(payloads) == {"overview", "topology", "validation", "data"}
    assert payloads["overview"]["date"] == date
    assert payloads["overview"]["score"]["value"] in {20.0, 80.0}
    assert payloads["overview"]["score"]["cutoff_status"]["state"] in {"above", "below"}
    assert payloads["topology"]["available"] is True
    assert len(payloads["topology"]["window"]) == 60
    assert payloads["validation"]["available"] is True
    assert payloads["validation"]["export_table"]["rows"]
    assert payloads["data"]["sources"]
    assert payloads["data"]["failures"]


def test_march_2020_replay_blind_reveal_blind(tmp_path: Path) -> None:
    root = _write_data_dir(tmp_path)
    data = load_dashboard_data("private", data_dir=root)
    blind = DashboardSelection(
        screen="topology", mode="replay", date="2020-03-16", sessions=data.session_dates
    )
    blind_payloads = build_screen_payloads(data, blind)
    assert blind_payloads["topology"]["outcome"] is None
    assert (
        blind_payloads["overview"]["score"]["cutoff_status"]
        == build_screen_payloads(
            data,
            DashboardSelection(
                screen="topology", mode="replay", date="2020-03-16", sessions=data.session_dates
            ),
        )["overview"]["score"]["cutoff_status"]
    )

    revealed = toggle_reveal(blind)
    revealed_payloads = build_screen_payloads(data, revealed)
    outcome = revealed_payloads["topology"]["outcome"]
    assert outcome is not None
    assert outcome["horizon_sessions"] == OUTCOME_HORIZON
    assert revealed_payloads["overview"]["score"] == blind_payloads["overview"]["score"]

    hidden_again = toggle_blind(revealed)
    assert build_screen_payloads(data, hidden_again)["topology"]["outcome"] is None


def test_keyboard_actions_change_selection(tmp_path: Path) -> None:
    root = _write_data_dir(tmp_path)
    data = load_dashboard_data("private", data_dir=root)
    selection = DashboardSelection(
        screen="overview", date=data.session_dates[100], sessions=data.session_dates
    )
    state = {
        "tm_screen": selection.screen,
        "tm_mode": selection.mode,
        "tm_date": selection.date,
        "tm_reveal": False,
        "tm_member": None,
        "tm_run": None,
    }
    updated = app.apply_action_to_state(state, "next_session", data)
    assert updated.date == data.session_dates[101]
    member_updated = apply_keyboard_action("next_member", updated)
    assert member_updated.member is not None


def test_validation_empty_state_when_no_reports(tmp_path: Path) -> None:
    root = _write_data_dir(tmp_path)
    for path in (root / "reports").glob("*"):
        path.unlink()
    data = load_dashboard_data("private", data_dir=root)
    selection = DashboardSelection(screen="validation", sessions=data.session_dates)
    payload = build_screen_payloads(data, selection)["validation"]
    assert payload["available"] is False
    assert "evaluation" in payload["empty_state"].lower()
    assert payload["export_table"] == {"columns": [], "rows": []}


def test_demo_data_loads_without_private_inputs() -> None:
    data = load_dashboard_data("demo")
    assert data.demo is True
    assert data.profile == "demo"
    selection = DashboardSelection(screen="overview", sessions=data.session_dates)
    payloads = build_screen_payloads(data, selection)
    assert payloads["overview"]["date"] == data.session_dates[-1]
    assert payloads["topology"]["available"] is False
