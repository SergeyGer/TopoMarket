"""Market Structure Studio (WP-C): comparison, fixed layout, interaction mapping."""

from __future__ import annotations

import math
from pathlib import Path

from topomarket.ui import interactive
from topomarket.ui.panels import load_dashboard_data
from topomarket.ui.structure import build_timeline, build_window_comparison

ROOT = Path(__file__).resolve().parents[1]


def _data():
    return load_dashboard_data("demo")


def _pearson(left: list[float], right: list[float]) -> float:
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    covariance = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right, strict=True))
    variance_left = sum((a - mean_left) ** 2 for a in left)
    variance_right = sum((b - mean_right) ** 2 for b in right)
    return covariance / math.sqrt(variance_left * variance_right)


def test_comparison_values_match_independent_pearson() -> None:
    data = _data()
    comparison = build_window_comparison(data, "2020-08-18", "2020-02-24")
    network = comparison["windows"]["B"]["network"]
    window_dates = network["window"]["dates"]
    rows = {str(row["date"]): row for row in data.industry_rows}
    left = [float(rows[date]["ind_nodur_return"]) for date in window_dates]
    right = [float(rows[date]["ind_enrgy_return"]) for date in window_dates]
    expected = round(_pearson(left, right), 6)
    pairs = {(pair["source"], pair["target"]): pair["correlation"] for pair in network["pairs"]}
    assert pairs[("nodur", "enrgy")] == expected
    for letter in ("A", "B"):
        window = comparison["windows"][letter]
        assert window["pairs_total"] == 66
        assert 0 <= window["pairs_qualifying"] <= 66


def test_comparison_is_honest_about_reverse_chronology() -> None:
    data = _data()
    comparison = build_window_comparison(data, "2020-08-18", "2020-02-24")
    assert comparison["available"] is True
    assert comparison["chronological"] is False
    assert comparison["sequence_claim"] is False
    assert "no chronological crisis-emergence claim" in comparison["statement"]
    assert comparison["delta_pairs"] == (
        comparison["windows"]["B"]["pairs_qualifying"]
        - comparison["windows"]["A"]["pairs_qualifying"]
    )
    left_pairs = {
        (edge["source"], edge["target"]) for edge in comparison["windows"]["A"]["network"]["edges"]
    }
    right_pairs = {
        (edge["source"], edge["target"]) for edge in comparison["windows"]["B"]["network"]["edges"]
    }
    added = {(edge["source"], edge["target"]) for edge in comparison["added_edges"]}
    removed = {(edge["source"], edge["target"]) for edge in comparison["removed_edges"]}
    assert added == right_pairs - left_pairs
    assert removed == left_pairs - right_pairs
    assert not (added & left_pairs)
    assert "table_alternative" in comparison


def test_fixed_node_positions_are_identical_in_every_state() -> None:
    data = _data()
    comparison = build_window_comparison(data, "2020-08-18", "2020-02-24")
    positions_a = {
        node["code"]: (node["x"], node["y"])
        for node in comparison["windows"]["A"]["network"]["nodes"]
    }
    positions_b = {
        node["code"]: (node["x"], node["y"])
        for node in comparison["windows"]["B"]["network"]["nodes"]
    }
    assert positions_a == positions_b
    timeline_a = build_timeline(data, "2020-08-18", blinded=True)
    timeline_b = build_timeline(data, "2020-02-24", blinded=True)
    assert timeline_a["dates"] != timeline_b["dates"]


def test_interactive_selection_mapping() -> None:
    assert (
        interactive.network_selection(
            {"selection": {"points": [{"customdata": ["money", "Finance", 8]}]}}
        )
        == "money"
    )
    dates = ["2020-02-20", "2020-02-21", "2020-02-24"]
    assert (
        interactive.timeline_selection(
            {"selection": {"points": [{"point_index": 2, "curve_number": 0}]}}, dates
        )
        == "2020-02-24"
    )
    assert (
        interactive.timeline_selection(
            {"selection": {"points": [{"customdata": ["2020-02-21", "Alert recorded"]}]}},
            dates,
        )
        == "2020-02-21"
    )
    assert interactive.network_selection(None) is None
    assert interactive.timeline_selection({}, dates) is None


def test_plotly_figures_are_interactive_and_blind_safe() -> None:
    data = _data()
    comparison = build_window_comparison(data, "2020-08-18", "2020-02-24")
    network = comparison["windows"]["A"]["network"]
    network_figure = interactive.network_figure(network, selected_code="money")
    node_trace = network_figure.data[-1]
    codes = {node_trace.customdata[index][0] for index in range(len(node_trace.customdata))}
    assert codes == set(
        comparison["windows"]["A"]["network"]["nodes"][index]["code"] for index in range(12)
    )
    positions = {
        node_trace.customdata[index][0]: (node_trace.x[index], node_trace.y[index])
        for index in range(len(node_trace.customdata))
    }
    for node in network["nodes"]:
        assert positions[node["code"]] == (node["x"], node["y"])
    comparison_figure = interactive.comparison_figure(comparison)
    assert len(comparison_figure.data) > 10
    timeline = build_timeline(data, "2025-03-10", blinded=True)
    timeline_figure = interactive.timeline_figure(timeline, selected_date="2025-03-10")
    assert len(timeline_figure.data) >= 4
    marker_texts = [
        str(trace.customdata)
        for trace in timeline_figure.data
        if getattr(trace, "customdata", None)
    ]
    joined = " ".join(marker_texts).lower()
    for forbidden in ("matched", "post_onset", "late alert", "episode_onset"):
        assert forbidden not in joined


def test_guided_steps_sequence_and_application() -> None:
    import app

    from topomarket.ui.dashboard import DashboardSelection

    data = _data()
    presets = data._presets_cache or app.build_presets(data)
    steps = app._guided_steps(presets, data)
    assert [step["name"] for step in steps] == [
        "Synthetic market shift",
        "Quiet window",
        "Stress transition",
        "Explain the alert",
        "Replay it blind",
    ]
    assert steps[0]["compare"] is True
    # Chronological window A is the earlier date; the comparison is +37 (not -37).
    assert steps[0]["date"] == "2008-08-29"
    assert steps[0]["compare_date"] == "2008-10-10"
    dates = [step["date"] for step in steps]
    assert all(dates)
    assert dates[0] < dates[1], "stress transition must follow the quiet window"
    selection = DashboardSelection(screen="structure", mode="replay", date=dates[0])
    applied = app._apply_guided_step(selection, steps[4])
    assert applied.screen == "replay"
    assert applied.reveal is False
    assert applied.network_view == "correlation"


def test_comparison_edge_change_encoding_uses_real_style() -> None:
    """U3: added/removed edges get distinct colour + dash in rendered traces."""

    from topomarket.ui.interactive import comparison_figure
    from topomarket.ui.presets import build_structure_change_pair
    from topomarket.ui.theme import ALERT, POSITIVE

    data = _data()
    pair = build_structure_change_pair(data)
    assert pair["summary"]["left_pairs"] == 29
    assert pair["summary"]["right_pairs"] == 66
    assert pair["summary"]["added"] == 37
    assert pair["summary"]["removed"] == 0

    comparison = build_window_comparison(data, pair["left_date"], pair["right_date"])
    assert comparison["added_count"] == 37
    assert comparison["removed_count"] == 0
    assert len(comparison["windows"]["B"]["added_edges"]) == 37
    assert comparison["windows"]["A"]["removed_edges"] == []
    figure = comparison_figure(comparison)
    namespace = [trace for trace in figure.data if getattr(trace, "name", "") or ""]
    added = [trace for trace in namespace if trace.name.startswith("Added in B")]
    assert len(added) == 37
    assert all(trace.line.color == POSITIVE for trace in added)
    assert all(trace.line.dash == "solid" for trace in added)
    assert len([trace for trace in namespace if trace.name.startswith("Kept")]) > 0
    legend_names = {trace.name for trace in figure.data if trace.showlegend}
    assert "Added in B (solid, positive)" in legend_names

    reverse = build_window_comparison(data, pair["right_date"], pair["left_date"])
    assert reverse["removed_count"] == 37
    assert len(reverse["windows"]["A"]["removed_edges"]) == 37
    reverse_figure = comparison_figure(reverse)
    removed = [
        trace
        for trace in reverse_figure.data
        if (getattr(trace, "name", "") or "").startswith("Removed in B")
    ]
    assert len(removed) == 37
    assert all(trace.line.color == ALERT for trace in removed)
    assert all(trace.line.dash == "dash" for trace in removed)
