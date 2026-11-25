"""Structure-screen payload tests (UI01-UI04)."""

from __future__ import annotations

import math

import pytest

from topomarket.analysis.network import PAIR_COUNT
from topomarket.ui.dashboard import DashboardSelection
from topomarket.ui.panels import load_dashboard_data
from topomarket.ui.structure import (
    EXPLANATION_POINTS,
    build_explanation,
    build_mapper_view,
    build_structure_payload,
    build_timeline,
)

ALERT_DATE = "2020-03-13"


@pytest.fixture(scope="module")
def data():
    return load_dashboard_data("demo")


@pytest.fixture(scope="module")
def selection():
    return DashboardSelection(screen="structure", mode="replay", date=ALERT_DATE)


@pytest.fixture(scope="module")
def payload(data, selection):
    return build_structure_payload(data, selection)


def test_default_public_profile_uses_the_showcase_fixture(data) -> None:
    assert data.profile == "demo"
    assert data.demo is True
    assert len(data.session_dates) > 5000
    assert data.snapshot_id == "showcase-synthetic"
    assert data.score_points
    assert data.evaluation_reports


def test_default_selection_opens_structure_on_a_warmed_scene(data) -> None:
    import app

    default = app.default_selection(data)
    assert default.screen == "structure"
    assert default.date in data.session_dates
    index = data.session_dates.index(default.date)
    assert index >= 60, "topology window must be warmed up on the landing screen"


def test_network_payload_matches_the_selected_map_date(payload) -> None:
    network = payload["network"]
    assert network["available"] is True
    assert network["pairs_total"] == PAIR_COUNT
    assert len(network["nodes"]) == 12
    assert len(network["edges"]) == network["pairs_qualifying"]
    assert network["window"]["end"] == payload["map_observation"]["date"]
    assert all(edge["correlation"] >= network["cutoff"] for edge in network["edges"])
    assert network["summary"].startswith(f"{network['pairs_qualifying']} of 66")


def test_network_positions_are_fixed_across_dates(data) -> None:
    first = build_structure_payload(data, DashboardSelection(screen="structure", date="2019-04-01"))
    second = build_structure_payload(
        data, DashboardSelection(screen="structure", date="2020-03-13")
    )
    positions_first = {node["code"]: (node["x"], node["y"]) for node in first["network"]["nodes"]}
    positions_second = {node["code"]: (node["x"], node["y"]) for node in second["network"]["nodes"]}
    assert positions_first == positions_second


def test_mapper_view_places_nodes_by_volatility_band(data) -> None:
    mapper = build_mapper_view(data, ALERT_DATE)
    assert mapper["available"] is True
    assert mapper["nodes"]
    bands = [node["band_index"] for node in mapper["nodes"]]
    assert bands == sorted(bands), "nodes must be ordered by volatility band"
    for node in mapper["nodes"]:
        assert node["x"] == float(node["band_index"])
        assert node["member_count"] == len(node["member_codes"]) or node["member_count"] > 0
        assert node["display_size"] > 0
    for edge in mapper["edges"]:
        assert edge["overlap"] == len(edge["shared_members"])
        assert edge["width"] >= 1.0


def test_mapper_member_inspector_reports_volatility_and_correlations(data) -> None:
    mapper = build_mapper_view(data, ALERT_DATE)
    inspector = mapper["member_inspector"]
    assert inspector["node_id"]
    assert inspector["members"]
    for member in inspector["members"]:
        assert member["label"]
        assert member["volatility"] is not None
        assert -1.0 <= member["within_group_correlation"] <= 1.0


def test_selecting_an_edge_exposes_its_shared_portfolios(data) -> None:
    baseline = build_mapper_view(data, ALERT_DATE)
    edge_id = baseline["edges"][0]["edge_id"]
    selected = build_mapper_view(data, ALERT_DATE, selected_edge=edge_id)
    assert selected["selected_edge"]["edge_id"] == edge_id
    assert selected["selected_edge"]["shared_members"]


def test_timeline_is_aligned_and_never_contains_future_sessions(data) -> None:
    timeline = build_timeline(data, ALERT_DATE)
    assert timeline["available"] is True
    assert timeline["dates"][-1] == ALERT_DATE
    assert max(timeline["dates"]) <= ALERT_DATE
    panels = timeline["panels"]
    for panel in ("sp500", "vix", "score"):
        assert len(panels[panel]["values"]) == len(timeline["dates"])
    assert panels["score"]["threshold"] is not None
    assert all(marker["date"] <= ALERT_DATE for marker in timeline["alert_markers"])
    assert any(marker["date"] == ALERT_DATE for marker in timeline["alert_markers"])


def test_timeline_vix_gaps_stay_going_concern_gaps(tmp_path) -> None:
    from topomarket.ui.calendars import build_calendar_status
    from topomarket.ui.panels import DashboardData

    rows = []
    for key in range(1, 31):
        date = f"2024-01-{key:02d}"
        rows.append(
            {
                "date": date,
                "sp500_close": "100.0",
                "vix_close": "" if key in {5, 9} else "15.0",
                "sp500_log_return": "0.001",
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
    fixture = DashboardData(
        profile="private",
        data_dir=tmp_path,
        active_data_dir=tmp_path,
        session_dates=tuple(row["date"] for row in rows),
        rows=tuple(rows),
        snapshot_id="fixture",
    )
    timeline = build_timeline(fixture, rows[-1]["date"])
    vix_values = timeline["panels"]["vix"]["values"]
    assert vix_values[4] is None and vix_values[8] is None
    assert timeline["panels"]["vix"]["missing_sessions"] == 2
    status = build_calendar_status(fixture)
    assert status["calendars"]["vix"]["gaps"] == 2


def test_explanation_has_56_takens_points_and_h1_diagram(data) -> None:
    explanation = build_explanation(data, ALERT_DATE)
    assert explanation["available"] is True
    assert explanation["window"] == {"sessions": 60, "dimension": 3, "lag": 2, "points": 56}
    assert len(explanation["takens"]["points"]) == EXPLANATION_POINTS == 56
    assert explanation["takens"]["coordinates"] == "display"
    assert "display" in explanation["display_note"].lower()
    intervals = explanation["h1"]["intervals"]
    assert intervals
    assert explanation["h1"]["longest_index"] is not None
    assert any(entry["is_longest"] for entry in intervals)
    assert explanation["h1"]["diagonal"] is True
    assert explanation["industry_pca"]["count"] == 60
    assert len(explanation["industry_pca"]["points"]) == 60


def test_longest_h1_lifetime_is_the_maximum_finite_lifetime(data) -> None:
    explanation = build_explanation(data, ALERT_DATE)
    h1 = explanation["h1"]
    finite = [entry["lifetime"] for entry in h1["intervals"] if entry["lifetime"] is not None]
    assert h1["longest_lifetime"] == pytest.approx(max(finite))
    longest = next(entry for entry in h1["intervals"] if entry["is_longest"])
    assert longest["lifetime"] == pytest.approx(h1["longest_lifetime"])


def test_explanation_is_deferred_for_non_alert_sessions(data) -> None:
    payload = build_structure_payload(
        data, DashboardSelection(screen="structure", date="2019-04-01")
    )
    assert payload["explanation"]["available"] is False
    assert payload["explanation"]["deferred"] is True
    assert "alert" in payload["explanation"]["reason"].lower()


def test_score_is_reported_as_a_comparative_percentile(payload) -> None:
    score = payload["score"]
    assert score["comparative"] is True
    assert score["value"] is not None
    assert 0.0 <= float(score["value"]) <= 100.0
    assert score["cutoff_status"]["cutoff"] is not None


def test_correlation_member_inspector_lists_pair_values(data) -> None:
    payload = build_structure_payload(
        data, DashboardSelection(screen="structure", date=ALERT_DATE, member="money")
    )
    inspector = payload["member_inspector"]
    assert inspector["selected"] == "money"
    assert len(inspector["pairs"]) == 11
    for pair in inspector["pairs"]:
        assert pair["label"]
        assert pair["correlation"] is None or math.isfinite(pair["correlation"])


def test_presets_are_verified_against_the_fixture(payload, data) -> None:
    presets = payload["presets"]
    assert presets["fixture_id"] == "showcase-synthetic"
    assert len(presets["presets"]) == 4
    for record in presets["presets"]:
        assert record["preset_id"] in {
            "quiet",
            "stress_transition",
            "matched_warning",
            "missed_warning",
        }
        if record["verified"]:
            assert record["date"] in data.session_dates
            index = data.session_dates.index(record["date"])
            assert index >= 60


def test_payload_is_json_serialisable(payload) -> None:
    import json

    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["screen"] == "structure"
