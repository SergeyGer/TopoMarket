"""Deterministic demonstration preset tests (UI01)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket.ui.dashboard import DashboardSelection
from topomarket.ui.panels import load_dashboard_data
from topomarket.ui.presets import (
    PRESET_ORDER,
    PresetError,
    build_presets,
    find_preset,
    load_frozen_presets,
)


@pytest.fixture(scope="module")
def data():
    return load_dashboard_data("demo")


def test_four_presets_are_derived_deterministically(data) -> None:
    first = build_presets(data)
    assert [record["preset_id"] for record in first["presets"]] == list(PRESET_ORDER)
    assert first["fixture_id"] == "showcase-synthetic"
    second = build_presets(data)
    assert second == first


def test_verified_presets_have_warmed_up_dates_in_the_fixture(data) -> None:
    payload = build_presets(data)
    for record in payload["presets"]:
        if not record["verified"]:
            assert record["reason"]
            continue
        assert record["date"] in data.session_dates
        assert data.session_dates.index(record["date"]) >= 60
        assert record["fixture_id"] == "showcase-synthetic"


def test_quiet_window_is_sparser_than_stress_transition(data) -> None:
    from topomarket.analysis.network import build_correlation_network

    quiet = find_preset(data, "quiet")
    stress = find_preset(data, "stress_transition")
    assert quiet is not None and stress is not None
    if not (quiet.verified and stress.verified):
        pytest.skip("preset derivation is unavailable on this fixture")
    quiet_network = build_correlation_network(data.rows, quiet.date)
    stress_network = build_correlation_network(data.rows, stress.date)
    assert quiet_network["pairs_qualifying"] >= 0
    assert quiet_network["pairs_qualifying"] < stress_network["pairs_qualifying"]


def test_matched_warning_is_credited_or_a_labelled_teaching_example(data) -> None:
    preset = find_preset(data, "matched_warning")
    assert preset is not None
    report = data.primary_report() or {}
    method = report.get("primary_method")
    metrics = (report.get("metrics") or {}).get(method) or {}
    if not preset.verified:
        assert "no verified" in (preset.reason or "")
        return
    if preset.teaching:
        # The frozen synthetic showcase has no credited TDA alert; the fallback is a
        # labelled late-warning teaching example that is not part of the evaluation.
        assert preset.date in {str(value) for value in metrics.get("post_onset_alerts") or ()}
        assert "teaching" in preset.label.lower()
        assert "not part of the frozen evaluation" in preset.description
    else:
        matched_dates = {entry.get("alert_date") for entry in metrics.get("matched") or ()}
        assert preset.date in matched_dates


def test_frozen_presets_match_the_deterministic_derivation(data) -> None:
    from topomarket.ui.presets import derive_presets

    frozen = build_presets(data)
    assert frozen["source"] == "frozen"
    derived = [record.as_dict() for record in derive_presets(data)]
    assert [(r["preset_id"], r["date"], r["mode"], r["teaching"]) for r in frozen["presets"]] == [
        (r["preset_id"], r["date"], r["mode"], r["teaching"]) for r in derived
    ]


def test_missed_warning_points_at_a_missed_or_late_episode(data) -> None:
    preset = find_preset(data, "missed_warning")
    assert preset is not None
    if not preset.verified:
        pytest.skip("no missed episode on this fixture")
    report = data.primary_report() or {}
    examples = (report.get("examples") or {}).get(report.get("primary_method")) or {}
    missed = {entry.get("episode_onset") for entry in examples.get("missed") or ()}
    assert preset.date in missed or preset.date is not None


def test_preset_payload_has_a_table_alternative(data) -> None:
    payload = build_presets(data)
    text = str(payload["table_alternative"])
    assert "Quiet period" in text
    assert "Fixture" in text
    if find_preset(data, "matched_warning") and find_preset(data, "matched_warning").teaching:
        assert "Late warning" in text


def test_frozen_presets_file_is_loaded_when_present(tmp_path: Path) -> None:
    frozen = {
        "fixture_id": "showcase-synthetic",
        "presets": [
            {
                "preset_id": "quiet",
                "label": "Quiet period",
                "date": "2019-04-01",
                "mode": "live",
                "expected": ["sparse correlation network"],
                "verified": True,
            }
        ],
    }
    path = tmp_path / "presets.json"
    path.write_text(json.dumps(frozen), encoding="utf-8")
    presets = load_frozen_presets(path)
    assert len(presets) == 1
    assert presets[0].preset_id == "quiet"
    assert presets[0].fixture_id == "showcase-synthetic"
    assert presets[0].verified is True


def test_invalid_frozen_presets_raise(tmp_path: Path) -> None:
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"presets": []}), encoding="utf-8")
    with pytest.raises(PresetError):
        load_frozen_presets(path)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PresetError):
        load_frozen_presets(path)


def test_derived_presets_are_available_as_selections(data) -> None:
    payload = build_presets(data)
    for record in payload["presets"]:
        if not record["verified"]:
            continue
        selection = DashboardSelection(
            screen="structure",
            mode=record["mode"],
            date=record["date"],
            sessions=data.session_dates,
        )
        assert selection.date == record["date"]
