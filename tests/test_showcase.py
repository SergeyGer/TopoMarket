"""Tests for the committed synthetic public showcase fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

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


def test_showcase_dashboard_supports_structure_replay_and_alert_inspection() -> None:
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
        screen="structure", mode="replay", date=replay_date, sessions=data.session_dates
    )
    payloads = build_screen_payloads(data, selection)
    structure = payloads["structure"]
    assert structure["screen"] == "structure"
    assert structure["synthetic"] is True
    assert structure["timeline"]["dates"][-1] == replay_date
    assert structure["network"]["available"] is True
    assert structure["explanation"]["available"] is True  # selected session is an alert

    replay = payloads["replay"]
    assert replay["blind"] is True
    assert replay["outcome"] is None

    revealed = toggle_reveal(selection)
    revealed_payloads = build_screen_payloads(data, revealed)
    assert revealed_payloads["replay"]["outcome"] is not None
    assert revealed_payloads["structure"]["network"]["window"]["end"] <= replay_date
    assert build_screen_payloads(data, toggle_blind(revealed))["replay"]["outcome"] is None

    validation = payloads["validation"]
    assert validation["available"] is True
    assert validation["wording"]
    assert validation["sample_size"]["episode_count"] is not None

    data_screen = payloads["data"]
    assert data_screen["synthetic"] is True
    assert data_screen["refresh_available"] is False


def test_showcase_contains_no_private_data_files() -> None:
    for path in SHOWCASE.rglob("*"):
        assert "private_data" not in path.name.lower()
    manifest = json.loads((SHOWCASE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["private_data"] is False


def test_showcase_scoring_and_report_are_deterministic() -> None:
    """The committed score file and report must carry the frozen configuration."""
    scores_meta = json.loads((SHOWCASE / "scores.csv.meta.json").read_text(encoding="utf-8"))
    report = json.loads(
        (SHOWCASE / "reports" / "evaluation-showcase.json").read_text(encoding="utf-8")
    )
    assert scores_meta["algorithm_version"] == "tda-v1"
    assert scores_meta["scored_count"] > 0
    assert report["snapshot_id"] == "showcase-synthetic"
    assert report["primary_method"] in report["methods"]
    assert report["evidence"]["wording"] == "Experimental market anomaly"
    assert report["seed"] == 42


def test_public_report_has_populated_provenance() -> None:
    """#81: the published synthetic report records its input identity and calendars."""

    import json
    from pathlib import Path

    report = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "showcase"
            / "reports"
            / "evaluation-showcase.json"
        ).read_text(encoding="utf-8")
    )
    assert report["snapshot_id"] == "showcase-synthetic"
    provenance = report["provenance"]
    assert provenance["code_revision"]
    snapshot = provenance["snapshot_provenance"]
    assert snapshot["source"] == "import_manifest"
    assert len(snapshot["manifest_digest"]) == 64
    calendars = snapshot["signal_calendars"]
    assert calendars["sources"]["price"] == "joint_tda_fallback"
    assert calendars["as_of"]["price"]
    assert provenance["bootstrap_algorithm"] == "moving_block_with_replacement_v2"
    assert report["metrics"]["tda"]["episode_recall"] == 0.0
    assert report["metrics"]["vix"]["episode_recall"] == pytest.approx(1 / 3)
    assert report["metrics"]["tda"]["average_precision"] == pytest.approx(0.0154, abs=1e-4)
    assert report["metrics"]["vix"]["average_precision"] == pytest.approx(0.1187, abs=1e-4)
