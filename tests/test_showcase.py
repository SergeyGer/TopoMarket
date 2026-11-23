"""Tests for the committed synthetic public showcase fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from topomarket.analysis.evaluation import report_digest
from topomarket.ui.dashboard import DashboardSelection, toggle_blind, toggle_reveal
from topomarket.ui.panels import build_screen_payloads, load_dashboard_data

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "showcase"


def test_showcase_is_marked_synthetic_and_hashed() -> None:
    manifest = json.loads((SHOWCASE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True
    assert manifest["private_data"] is False
    assert manifest["row_count"] > 1000
    assert manifest["hashes"]
    for name, expected in manifest["hashes"].items():
        actual = hashlib.sha256((SHOWCASE / name).read_bytes()).hexdigest()
        assert actual == expected, name


def test_showcase_dashboard_supports_replay_and_alert_inspection() -> None:
    data = load_dashboard_data("private", data_dir=SHOWCASE)
    assert len(data.session_dates) > 5000
    assert data.score_points
    assert data.evaluation_reports
    assert data.snapshot_id == "showcase-synthetic"

    report = data.evaluation_reports[0]
    assert report_digest(report)
    alert_dates = report["metrics"][report["primary_method"]]["alerts"]
    assert alert_dates
    replay_date = alert_dates[-1]

    selection = DashboardSelection(
        screen="topology", mode="replay", date=replay_date, sessions=data.session_dates
    )
    payloads = build_screen_payloads(data, selection)
    history = payloads["overview"]["score_history"]
    assert history
    assert all({"date", "score"} <= set(item) for item in history)
    assert any(item["date"] == selection.date for item in history)
    assert payloads["topology"]["available"] is True
    assert payloads["topology"]["outcome"] is None
    assert payloads["validation"]["available"] is True

    revealed = toggle_reveal(selection)
    revealed_payloads = build_screen_payloads(data, revealed)
    assert revealed_payloads["topology"]["outcome"] is not None
    assert revealed_payloads["overview"]["score"] == payloads["overview"]["score"]
    assert build_screen_payloads(data, toggle_blind(revealed))["topology"]["outcome"] is None


def test_showcase_contains_no_private_data_files() -> None:
    for path in SHOWCASE.rglob("*"):
        assert "private_data" not in path.name.lower()
    manifest = json.loads((SHOWCASE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["private_data"] is False
