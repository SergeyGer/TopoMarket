"""Chart-builder tests for the Structure and Replay screens (UI02-UI04)."""

from __future__ import annotations

import io

import pytest

from topomarket.ui import charts
from topomarket.ui.dashboard import DashboardSelection
from topomarket.ui.panels import build_screen_payloads, load_dashboard_data


@pytest.fixture(scope="module")
def data():
    return load_dashboard_data("demo")


@pytest.fixture(scope="module")
def structure_payload(data):
    selection = DashboardSelection(screen="structure", mode="replay", date="2020-03-13")
    return build_screen_payloads(data, selection)["structure"]


@pytest.fixture(scope="module")
def mapper_payload(data):
    selection = DashboardSelection(
        screen="structure", mode="replay", date="2020-03-13", network_view="mapper"
    )
    return build_screen_payloads(data, selection)["structure"]


@pytest.fixture(scope="module")
def replay_payload(data):
    selection = DashboardSelection(screen="replay", mode="replay", date="2020-02-24")
    return build_screen_payloads(data, selection)["replay"]


def _png_bytes(figure) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=60, facecolor=figure.get_facecolor())
    payload = buffer.getvalue()
    import matplotlib.pyplot as plt

    plt.close(figure)
    return payload


def test_correlation_network_figure_draws_nodes_edges_and_legend(structure_payload) -> None:
    figure = charts.correlation_network_figure(structure_payload["network"], selected_code="money")
    assert len(figure.axes) >= 1
    axes = figure.axes[0]
    assert len(axes.lines) >= len(structure_payload["network"]["edges"])
    assert len(axes.collections) >= 12  # 2 scatter collections per node
    assert axes.get_legend() is not None
    png = _png_bytes(figure)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 10_000


def test_mapper_figure_has_one_band_tick_per_interval(mapper_payload) -> None:
    mapper = mapper_payload["mapper"]
    figure = charts.mapper_figure(mapper, selected_node_id=mapper["selected_node_id"])
    axes = figure.axes[0]
    assert len(axes.get_xticks()) == len(mapper["bands"])
    assert axes.get_xlabel().startswith("volatility lens band")
    assert len(_png_bytes(figure)) > 10_000


def test_timeline_figure_has_three_aligned_panels(structure_payload) -> None:
    timeline = structure_payload["timeline"]
    figure = charts.timeline_figure(timeline)
    assert len(figure.axes) >= 3
    axes_list = figure.axes[:3]
    assert axes_list[0].get_ylabel().startswith("S&P 500")
    assert axes_list[1].get_ylabel().startswith("VIX")
    assert axes_list[2].get_ylabel().startswith("score")
    # Shared x axis: the three panels use the same x limits.
    limits = {tuple(axes.get_xlim()) for axes in axes_list}
    assert len(limits) == 1
    assert len(_png_bytes(figure)) > 10_000


def test_timeline_figure_renders_vix_gaps_without_connecting_them(structure_payload, data) -> None:
    timeline = dict(structure_payload["timeline"])
    panels = {key: dict(value) for key, value in timeline["panels"].items()}
    panels["vix"] = dict(panels["vix"])
    panels["vix"]["values"] = [
        None if index % 17 == 3 else 15.0 for index in range(len(timeline["dates"]))
    ]
    timeline["panels"] = panels
    figure = charts.timeline_figure(timeline)
    vix_line = figure.axes[1].lines[0]
    assert any(value != value for value in vix_line.get_ydata())  # NaN gap
    _png_bytes(figure)


def test_explanation_figures_render(structure_payload) -> None:
    explanation = structure_payload["explanation"]
    assert explanation["available"] is True
    for builder in (charts.takens_figure, charts.h1_figure, charts.pca_figure):
        figure = builder(explanation)
        assert figure is not None
        assert len(_png_bytes(figure)) > 5_000


def test_blind_replay_figure_does_not_draw_the_outcome(replay_payload) -> None:
    assert replay_payload["blind"] is True
    figure = charts.replay_figure(replay_payload)
    assert len(figure.axes) >= 2
    price_axes = figure.axes[1]
    # Only the historical price line and the cutoff cursor are drawn in blind mode;
    # no outcome line, origin line or boundary line exists.
    labels = {line.get_label() for line in price_axes.lines}
    assert "S&P 500 history" in labels
    assert "revealed outcome" not in labels
    assert "10% boundary" not in labels
    assert len(_png_bytes(figure)) > 10_000


def test_revealed_replay_figure_draws_outcome_layer(data) -> None:
    selection = DashboardSelection(screen="replay", mode="replay", date="2020-02-24", reveal=True)
    payload = build_screen_payloads(data, selection)["replay"]
    figure = charts.replay_figure(payload)
    price_axes = figure.axes[1]
    assert len(price_axes.lines) >= 3  # history + revealed outcome + origin/boundary
    assert any(line.get_linestyle() == "--" for line in price_axes.lines)
    labels = [text.get_text() for text in price_axes.texts]
    assert not any("Pending" in label for label in labels)
    _png_bytes(figure)


def test_empty_payloads_are_explicit_instead_of_blank() -> None:
    figure = charts.correlation_network_figure({"available": False, "reason": "unavailable"})
    texts = [text.get_text() for text in figure.axes[0].texts]
    assert any("unavailable" in text.lower() for text in texts)
    _png_bytes(figure)


def test_mapper_figure_uses_deterministic_band_columns(mapper_payload) -> None:
    mapper = mapper_payload["mapper"]
    for node in mapper["nodes"]:
        assert node["x"] == float(node["band_index"])
    figure = charts.mapper_figure(mapper)
    _png_bytes(figure)
