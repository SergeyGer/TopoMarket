"""Integration tests for the version 1.0 dashboard data layer and screen payloads.

Structure- and Replay-specific contracts are covered in ``test_structure.py`` and
``test_replay.py``; this module covers data loading, the four-screen payload
aggregation, the shared cache and the Validation/Data payloads.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from topomarket.ui.dashboard import SCREENS, DashboardSelection
from topomarket.ui.panels import (
    SCREEN_LABELS,
    DashboardDataError,
    PanelCache,
    build_screen_payloads,
    load_dashboard_data,
)

SHOWCASE = Path(__file__).resolve().parents[1] / "showcase"


@pytest.fixture(scope="module")
def data():
    return load_dashboard_data("demo")


def test_public_demo_profile_defaults_to_the_showcase_fixture(data) -> None:
    assert data.profile == "demo"
    assert data.demo is True
    assert len(data.session_dates) == 5673
    assert data.snapshot_id == "showcase-synthetic"
    assert data.score_points
    assert data.evaluation_reports
    # Showcase is the joined synthetic table, so every calendar is aligned.
    assert data.price_rows and data.industry_rows
    assert data.sources


def test_private_profile_can_point_at_the_same_synthetic_fixture() -> None:
    private = load_dashboard_data("private", data_dir=SHOWCASE)
    assert private.profile == "private"
    assert len(private.session_dates) == 5673
    assert private.snapshot_id == "showcase-synthetic"


def test_build_screen_payloads_covers_the_four_release_screens(data) -> None:
    selection = DashboardSelection(screen="structure", mode="replay", date="2020-02-24")
    payloads = build_screen_payloads(data, selection)
    assert set(payloads) == set(SCREENS) == {"structure", "replay", "validation", "data"}
    for screen, payload in payloads.items():
        assert payload["screen"] == screen
        assert payload["title"] == SCREEN_LABELS[screen]
    assert payloads["structure"]["selected"] == "2020-02-24"
    assert payloads["replay"]["date"] == "2020-02-24"


def test_selected_date_must_be_a_loaded_session(data) -> None:
    selection = DashboardSelection(screen="structure", date="1999-01-01")
    with pytest.raises(DashboardDataError):
        build_screen_payloads(data, selection)


def test_validation_payload_reports_sample_size_rate_and_evidence(data) -> None:
    selection = DashboardSelection(screen="validation", mode="live", date="2020-02-24")
    validation = build_screen_payloads(data, selection)["validation"]
    assert validation["available"] is True
    assert validation["wording"]
    assert validation["primary_method"] in validation["metrics"]
    sample = validation["sample_size"]
    assert sample["episode_count"] is not None
    assert sample["eligible_sessions"] is not None
    assert validation["false_alert_rate"] is not None
    assert "limitations" in validation
    assert validation["table_alternative"]
    json.dumps(validation)


def test_validation_payload_exports_alert_evidence(data) -> None:
    selection = DashboardSelection(screen="validation", mode="live", date="2020-02-24")
    validation = build_screen_payloads(data, selection)["validation"]
    table = validation["export_table"]
    assert table["columns"] == ["kind", "method", "date", "episode_onset", "lead_sessions"]
    assert isinstance(table["rows"], list)


def test_data_payload_reports_independent_calendars(data) -> None:
    selection = DashboardSelection(screen="data", mode="live", date="2020-02-24")
    screen = build_screen_payloads(data, selection)["data"]
    assert set(screen["calendars"]) == {"price", "vix", "industry"}
    assert screen["price_calendar_is_signal_calendar"] is True
    assert screen["refresh_available"] is False  # public demo is read-only
    assert screen["synthetic"] is True
    json.dumps(screen)


def test_panel_cache_hits_and_invalidates(data) -> None:
    cache = PanelCache(data)
    selection = DashboardSelection(screen="structure", mode="replay", date="2020-02-24")
    first = cache.get(selection)
    assert cache.misses == 1 and cache.hits == 0
    second = cache.get(selection)
    assert second is first
    assert cache.hits == 1
    # Network view is part of the cache identity.
    mapper_selection = selection.with_network_view("mapper")
    cache.get(mapper_selection)
    assert cache.misses == 2
    cache.invalidate()
    cache.get(selection)
    assert cache.misses == 3


def test_handcrafted_short_data_directory_is_handled_gracefully(tmp_path: Path) -> None:
    from topomarket.ui.panels import _build_dataset

    rows = []
    for offset in range(30):
        rows.append(
            {
                "date": f"2024-01-{offset + 1:02d}",
                "sp500_close": "100.0",
                "sp500_log_return": "0.001" if offset else "",
                "vix_close": "15.0",
                **{
                    f"ind_{code}_return": "0.001"
                    for code in (
                        "nodur",
                        "durbl",
                        "manuf",
                        "enrgy",
                        "chems",
                        "buseq",
                        "telcm",
                        "utils",
                        "shops",
                        "hlth",
                        "money",
                        "other",
                    )
                },
            }
        )
    normalized = tmp_path / "normalized"
    normalized.mkdir()
    header = list(rows[0])
    with (normalized / "tda_daily.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    short = _build_dataset(profile="private", root=tmp_path, active=tmp_path, demo=False)
    selection = DashboardSelection(screen="structure", date=short.session_dates[-1])
    payloads = build_screen_payloads(short, selection)
    assert payloads["structure"]["network"]["available"] is False
    assert payloads["structure"]["mapper"]["available"] is False
    assert payloads["structure"]["mapper"]["reason"]
    assert payloads["structure"]["explanation"]["available"] is False
    json.dumps(payloads)


def test_fallback_demo_generator_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    import topomarket.ui.panels as panels

    monkeypatch.setattr(panels, "_showcase_dir", lambda: None)
    fallback = load_dashboard_data("demo")
    assert fallback.demo is True
    assert len(fallback.session_dates) == 30
    selection = DashboardSelection(screen="structure", date=fallback.session_dates[-1])
    payloads = build_screen_payloads(fallback, selection)
    assert payloads["structure"]["network"]["available"] is False
    assert payloads["replay"]["blind"] is False
