"""Matplotlib chart builders for the Structure and Replay screens (UI02-UI04).

Every function takes a pure payload built by :mod:`topomarket.ui.structure` or
:mod:`topomarket.ui.replay` and returns a matplotlib ``Figure``.  The module is
deliberately free of Streamlit so it can be tested offline; the shell renders the
figures with ``st.pyplot``.

Visual rules (UI04)
-------------------
* neutral canvas, teal market series, amber benchmark/threshold/alert;
* alerts are drawn with a marker symbol plus text, never colour alone;
* fixed correlation-network positions are reused for every date (no random
  layout), so edges/markers animate meaningfully and nothing jumps;
* VIX gaps stay gaps (``numpy.nan``), they are never connected or filled.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from .theme import (  # noqa: E402
    ALERT,
    AMBER,
    BLUE,
    BORDER,
    CANVAS,
    CANVAS_SOFT,
    GRID,
    INK,
    MUTED,
    POSITIVE,
    TEAL,
)

DPI = 110


def _style(figure: Figure) -> None:
    figure.patch.set_facecolor(CANVAS)


def _axes_style(axes: plt.Axes, *, grid: bool = True) -> None:
    axes.set_facecolor(CANVAS)
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        axes.spines[spine].set_color(BORDER)
    axes.tick_params(colors=MUTED, labelsize=8.5)
    axes.xaxis.label.set_color(MUTED)
    axes.yaxis.label.set_color(MUTED)
    if grid:
        axes.grid(True, color=GRID, linewidth=0.6, alpha=0.7)
        axes.set_axisbelow(True)


def _empty_figure(message: str) -> Figure:
    figure = plt.figure(figsize=(7.2, 3.2), dpi=DPI)
    _style(figure)
    axes = figure.add_axes((0.02, 0.02, 0.96, 0.96))
    axes.axis("off")
    axes.text(
        0.5,
        0.5,
        message,
        ha="center",
        va="center",
        fontsize=11,
        color=MUTED,
        wrap=True,
        transform=axes.transAxes,
    )
    return figure


def _save_png_bytes(figure: Figure) -> bytes:
    """Render a figure to PNG bytes (used by the video pipeline and tests)."""

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=DPI, facecolor=figure.get_facecolor())
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Correlation network
# --------------------------------------------------------------------------- #
def correlation_network_figure(
    network: Mapping[str, Any],
    *,
    selected_code: str | None = None,
    height: float = 3.55,
) -> Figure:
    """Draw the fixed-position 12-node correlation network."""

    if not network.get("available"):
        return _empty_figure(str(network.get("reason") or "Correlation network unavailable"))
    nodes = {node["code"]: node for node in network.get("nodes") or ()}
    edges = list(network.get("edges") or ())
    figure = plt.figure(figsize=(8.8, height), dpi=DPI)
    _style(figure)
    axes = figure.add_axes((0.02, 0.10, 0.96, 0.84))
    axes.set_xlim(-1.78, 1.78)
    axes.set_ylim(-1.62, 1.62)
    axes.set_aspect("equal")
    axes.axis("off")
    cutoff = float(network.get("cutoff") or 0.0)
    span = max(1.0 - cutoff, 0.05)
    incident = {
        frozenset((edge["source"], edge["target"]))
        for edge in edges
        if selected_code and selected_code in (edge["source"], edge["target"])
    }
    for edge in edges:
        source = nodes[edge["source"]]
        target = nodes[edge["target"]]
        key = frozenset((edge["source"], edge["target"]))
        highlighted = key in incident
        strength = max(0.0, min(1.0, (float(edge["correlation"]) - cutoff) / span))
        axes.plot(
            [source["x"], target["x"]],
            [source["y"], target["y"]],
            color=AMBER if highlighted else TEAL,
            linewidth=(2.2 if highlighted else 0.5) + 2.0 * strength,
            alpha=0.95 if highlighted else (0.30 + 0.45 * strength),
            solid_capstyle="round",
            zorder=3 if highlighted else 1,
        )
    degree = {node["code"]: int(node.get("degree") or 0) for node in network.get("nodes") or ()}
    max_degree = max(degree.values()) if degree else 1
    for code, node in nodes.items():
        size = 150.0 + 380.0 * degree[code] / max(max_degree, 1)
        selected = code == selected_code
        axes.scatter(
            [node["x"]],
            [node["y"]],
            s=size * (1.45 if selected else 1.0),
            color=AMBER if selected else TEAL,
            edgecolors=INK,
            linewidths=1.2,
            zorder=5,
        )
        axes.scatter([node["x"]], [node["y"]], s=size * 0.30, color=CANVAS, zorder=6)
        # Place labels radially outward with quadrant-aware alignment so long
        # industry names never overlap a neighbouring node or each other.
        label_x = node["x"] * 1.34
        label_y = node["y"] * 1.30
        horizontal = "left" if label_x > 0.25 else ("right" if label_x < -0.25 else "center")
        vertical = "bottom" if label_y > 0.25 else ("top" if label_y < -0.25 else "center")
        axes.annotate(
            node["short_label"],
            (node["x"], node["y"]),
            xytext=(label_x, label_y),
            ha=horizontal,
            va=vertical,
            fontsize=9.0,
            color=INK,
            zorder=7,
        )
    legend_handles = [
        Line2D([0], [0], color=TEAL, linewidth=2, label=f"positive edge r >= {cutoff:.2f}"),
        Line2D([0], [0], color=AMBER, linewidth=2, label="edges of the selected portfolio"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=TEAL,
            markeredgecolor=INK,
            markersize=8,
            label="industry portfolio (fixed position)",
        ),
    ]
    axes.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.06),
        frameon=False,
        fontsize=7.6,
        ncol=3,
        labelcolor=MUTED,
    )
    axes.set_title(
        f"{network.get('pairs_qualifying')}/{network.get('pairs_total')} pairs at "
        f"{network.get('cutoff_display')} · {network['window']['start']} to "
        f"{network['window']['end']}",
        fontsize=9.0,
        color=MUTED,
        loc="left",
    )
    return figure


# --------------------------------------------------------------------------- #
# Mapper
# --------------------------------------------------------------------------- #
def mapper_figure(
    mapper: Mapping[str, Any],
    *,
    selected_node_id: str | None = None,
    selected_edge_id: str | None = None,
    height: float = 4.8,
) -> Figure:
    """Draw Mapper groups in volatility-band columns with shared-member edges."""

    if not mapper.get("available"):
        return _empty_figure(str(mapper.get("reason") or "Mapper unavailable"))
    nodes = list(mapper.get("nodes") or ())
    edges = list(mapper.get("edges") or ())
    by_id = {node["node_id"]: node for node in nodes}
    bands = sorted({int(node["band_index"]) for node in nodes})
    width = max(7.0, 1.6 * len(bands) + 3.0)
    figure = plt.figure(figsize=(width, height), dpi=DPI)
    _style(figure)
    axes = figure.add_axes((0.03, 0.16, 0.94, 0.74))
    axes.set_facecolor(CANVAS_SOFT)
    for node in nodes:
        node["_radius"] = 0.16 + 0.035 * node["member_count"]
    selected_edge = next((edge for edge in edges if edge["edge_id"] == selected_edge_id), None)
    for edge in edges:
        source = by_id.get(edge["source"])
        target = by_id.get(edge["target"])
        if source is None or target is None:
            continue
        highlighted = selected_edge is not None and edge["edge_id"] == selected_edge["edge_id"]
        axes.plot(
            [source["x"], target["x"]],
            [source["y"], target["y"]],
            color=AMBER if highlighted else TEAL,
            linewidth=(1.0 + float(edge.get("overlap") or 1)) * (2.2 if highlighted else 1.0),
            alpha=0.9 if highlighted else 0.45,
            zorder=2 if highlighted else 1,
        )
    for node in nodes:
        selected = node["node_id"] == selected_node_id
        axes.scatter(
            [node["x"]],
            [node["y"]],
            s=node["_radius"] * 2600,
            color=AMBER if selected else TEAL,
            edgecolors=INK,
            linewidths=1.1,
            zorder=4,
        )
        axes.annotate(
            f"{node['node_id']} · {node['member_count']}",
            (node["x"], node["y"]),
            xytext=(node["x"], node["y"] + node["_radius"] + 0.22),
            ha="center",
            va="bottom",
            fontsize=8,
            color=INK,
            zorder=5,
        )
    axes.set_xticks(bands)
    axes.set_xticklabels([f"band {band}" for band in bands])
    axes.set_yticks([])
    axes.set_xlabel("volatility lens band (low to high)")
    axes.set_xlim(-0.6, (max(bands) if bands else 0) + 0.6)
    axes.set_ylim(-1.4, 1.4)
    _axes_style(axes)
    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=TEAL,
            markersize=10,
            label="group (area = members)",
        ),
        Line2D([0], [0], color=TEAL, linewidth=3, label="edge (width = shared portfolios)"),
        Line2D([0], [0], color=AMBER, linewidth=3, label="selected"),
    ]
    axes.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.30),
        ncol=3,
        frameon=False,
        fontsize=8,
        labelcolor=MUTED,
    )
    axes.set_title(
        f"Mapper groups · window {mapper['window']['start']} to {mapper['window']['end']}",
        fontsize=9.5,
        color=MUTED,
        loc="left",
    )
    return figure


# --------------------------------------------------------------------------- #
# Shared timeline
# --------------------------------------------------------------------------- #
def timeline_figure(timeline: Mapping[str, Any], *, height: float = 6.4) -> Figure:
    """Draw the aligned S&P 500, VIX and score panels with a shared cursor."""

    if not timeline.get("available"):
        return _empty_figure("No price observations for the selected window")
    dates: list[str] = list(timeline.get("dates") or ())
    panels = timeline.get("panels") or {}
    positions = np.arange(len(dates))
    figure = plt.figure(figsize=(10.4, height), dpi=DPI)
    _style(figure)
    axes_list = figure.subplots(
        3,
        1,
        sharex=True,
        gridspec_kw={"height_ratios": [1.3, 1.0, 1.0], "hspace": 0.12},
    )
    sp500 = panels.get("sp500") or {}
    vix = panels.get("vix") or {}
    score = panels.get("score") or {}
    axes_list[0].plot(positions, _nan_series(sp500.get("values")), color=TEAL, linewidth=1.6)
    axes_list[0].set_ylabel(f"S&P 500\n({sp500.get('unit')})", fontsize=8.5)
    axes_list[1].plot(positions, _nan_series(vix.get("values")), color=BLUE, linewidth=1.4)
    axes_list[1].set_ylabel(f"VIX\n({vix.get('unit')})", fontsize=8.5)
    axes_list[2].plot(positions, _nan_series(score.get("values")), color=TEAL, linewidth=1.4)
    threshold = score.get("threshold")
    if threshold is not None:
        axes_list[2].axhline(
            float(threshold),
            color=AMBER,
            linestyle="--",
            linewidth=1.2,
            label=f"frozen threshold {float(threshold):.1f}",
        )
        axes_list[2].legend(frameon=False, fontsize=8, labelcolor=MUTED, loc="upper left")
    for marker in timeline.get("alert_markers") or ():
        date = marker.get("date")
        if date not in dates:
            continue
        position = dates.index(date)
        value = _value_at(score.get("values") or (), position)
        y = value if value is not None else (threshold if threshold is not None else 50.0)
        status = marker.get("status") or "alert"
        color = {"matched": POSITIVE, "late": ALERT, "false": MUTED}.get(status, AMBER)
        axes_list[2].scatter(
            [position],
            [y],
            marker="^" if status in {"matched", "alert"} else ("v" if status == "late" else "x"),
            s=54,
            color=color,
            zorder=5,
            label=str(status),
        )
    selected = timeline.get("selected")
    if selected in dates:
        cursor = dates.index(selected)
        for axes in axes_list:
            axes.axvline(cursor, color=AMBER, linewidth=1.0, alpha=0.8, zorder=4)
    tick_positions = _tick_positions(len(dates))
    axes_list[2].set_xticks(tick_positions)
    axes_list[2].set_xticklabels(
        [dates[position] for position in tick_positions], rotation=35, ha="right", fontsize=7.5
    )
    axes_list[2].set_ylabel(f"score\n({score.get('unit')})", fontsize=8.5)
    for axes in axes_list:
        _axes_style(axes)
    axes_list[0].set_title(
        f"Shared timeline · {dates[0]} to {dates[-1]} · cursor {selected}",
        fontsize=9.5,
        color=MUTED,
        loc="left",
    )
    axes_list[0].text(
        0.0,
        -0.55,
        "Teal: S&P 500 close. Blue: VIX close (gaps stay gaps). Teal score line: comparative "
        "percentile. Amber dashed: frozen threshold. Markers: alerts (★ matched, ▼ late, ✕ false).",
        transform=axes_list[0].transAxes,
        fontsize=7.8,
        color=MUTED,
        va="top",
    )
    return figure


def _nan_series(values: Sequence[Any]) -> np.ndarray:
    return np.asarray([np.nan if value is None else float(value) for value in values], dtype=float)


def _value_at(values: Sequence[Any], position: int) -> float | None:
    if position < 0 or position >= len(values):
        return None
    value = values[position]
    return None if value is None else float(value)


def _tick_positions(count: int, ticks: int = 8) -> list[int]:
    if count <= 1:
        return [0]
    step = max(1, count // (ticks - 1))
    positions = list(range(0, count, step))
    if positions[-1] != count - 1:
        positions.append(count - 1)
    return positions


# --------------------------------------------------------------------------- #
# Score explanation
# --------------------------------------------------------------------------- #
def takens_figure(explanation: Mapping[str, Any]) -> Figure:
    """2-D display-coordinate scatter of the 56-point price embedding."""

    takens = explanation.get("takens")
    if not takens:
        return _empty_figure(str(explanation.get("reason") or "No Takens window"))
    points = list(takens.get("points") or ())
    figure = plt.figure(figsize=(5.0, 4.2), dpi=DPI)
    _style(figure)
    axes = figure.add_axes((0.16, 0.16, 0.80, 0.70))
    xs = [point["x"] for point in points]
    ys = [point["y"] for point in points]
    colors = np.arange(len(points))
    scatter = axes.scatter(xs, ys, c=colors, cmap="viridis", s=28, zorder=3, label="session")
    highlight = takens.get("highlight_index")
    if highlight is not None and 0 <= int(highlight) < len(points):
        point = points[int(highlight)]
        axes.scatter(
            [point["x"]],
            [point["y"]],
            s=110,
            facecolors="none",
            edgecolors=AMBER,
            linewidths=2.0,
            zorder=4,
            label="latest session in the window",
        )
    axes.set_xlabel("display coordinate 1")
    axes.set_ylabel("display coordinate 2")
    axes.set_title(
        f"Takens embedding · dimension {explanation['window']['dimension']}, "
        f"lag {explanation['window']['lag']} · {len(points)} points",
        fontsize=9,
        color=MUTED,
        loc="left",
    )
    _axes_style(axes)
    legend = axes.legend(frameon=False, fontsize=7.5, labelcolor=MUTED, loc="best")
    if legend is not None:
        legend.set_draggable(False)
    figure.colorbar(scatter, ax=axes, fraction=0.045, pad=0.02).ax.tick_params(
        labelsize=7, colors=MUTED
    )
    axes.text(
        0.0,
        -0.30,
        str(explanation.get("display_note")),
        transform=axes.transAxes,
        fontsize=7.2,
        color=MUTED,
        va="top",
    )
    return figure


def h1_figure(explanation: Mapping[str, Any]) -> Figure:
    """H1 birth-death plot with diagonal and longest finite lifetime highlighted."""

    h1 = explanation.get("h1")
    if not h1:
        return _empty_figure(str(explanation.get("reason") or "No H1 intervals"))
    intervals = [entry for entry in h1.get("intervals") or () if entry.get("death") is not None]
    figure = plt.figure(figsize=(4.6, 4.2), dpi=DPI)
    _style(figure)
    axes = figure.add_axes((0.18, 0.16, 0.78, 0.70))
    if not intervals:
        axes.text(
            0.5,
            0.5,
            "No finite H1 intervals in this window",
            ha="center",
            va="center",
            color=MUTED,
            transform=axes.transAxes,
        )
    births = [entry["birth"] for entry in intervals]
    deaths = [entry["death"] for entry in intervals]
    axes.scatter(
        births,
        deaths,
        s=34,
        color=TEAL,
        edgecolors=INK,
        linewidths=0.6,
        zorder=3,
        label="H1 interval",
    )
    low = min(births + deaths) if births else 0.0
    high = max(births + deaths) if births else 1.0
    padding = max(0.05 * (high - low), 0.02)
    diagonal = np.linspace(low - padding, high + padding, 50)
    axes.plot(diagonal, diagonal, color=BORDER, linestyle=":", linewidth=1.0, label="birth = death")
    longest = h1.get("longest_index")
    for entry in intervals:
        if entry.get("index") == longest:
            axes.scatter(
                [entry["birth"]],
                [entry["death"]],
                s=120,
                color=AMBER,
                edgecolors=INK,
                linewidths=0.8,
                zorder=4,
                label="longest finite lifetime",
            )
            axes.annotate(
                f"lifetime {float(entry['lifetime']):.3f}",
                (entry["birth"], entry["death"]),
                xytext=(8, 8),
                textcoords="offset points",
                fontsize=8,
                color=AMBER,
            )
    axes.set_xlabel("birth")
    axes.set_ylabel("death")
    axes.set_title("H1 persistence diagram", fontsize=9, color=MUTED, loc="left")
    _axes_style(axes)
    axes.legend(frameon=False, fontsize=7.5, labelcolor=MUTED, loc="upper left")
    return figure


def pca_figure(explanation: Mapping[str, Any]) -> Figure:
    """Industry-cloud PCA scatter (one point per session)."""

    pca = explanation.get("industry_pca")
    if not pca:
        return _empty_figure("No industry PCA scatter for this window")
    points = list(pca.get("points") or ())
    figure = plt.figure(figsize=(4.6, 4.2), dpi=DPI)
    _style(figure)
    axes = figure.add_axes((0.18, 0.16, 0.78, 0.70))
    xs = [point["x"] for point in points]
    ys = [point["y"] for point in points]
    axes.scatter(xs, ys, c=np.arange(len(points)), cmap="viridis", s=26, zorder=3)
    if points:
        latest = points[-1]
        axes.scatter(
            [latest["x"]],
            [latest["y"]],
            s=110,
            facecolors="none",
            edgecolors=AMBER,
            linewidths=2.0,
            zorder=4,
            label="map date",
        )
    ratios = [value for value in (pca.get("explained_variance_ratio") or ()) if value is not None]
    label_x = f"PC1 ({ratios[0] * 100:.0f}%)" if len(ratios) > 0 else "PC1"
    label_y = f"PC2 ({ratios[1] * 100:.0f}%)" if len(ratios) > 1 else "PC2"
    axes.set_xlabel(label_x)
    axes.set_ylabel(label_y)
    axes.set_title(str(pca.get("label") or "Industry PCA"), fontsize=9, color=MUTED, loc="left")
    _axes_style(axes)
    if points:
        axes.legend(frameon=False, fontsize=7.5, labelcolor=MUTED, loc="best")
    return figure


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #
def replay_figure(replay: Mapping[str, Any], *, height: float = 6.2) -> Figure:
    """Draw the Replay screen: score history above, price/outcome below.

    In blind mode the outcome layer is ``None`` and nothing after the cutoff is
    drawn at all (the payload itself contains no post-cutoff values).
    """

    history = replay.get("price_history") or {}
    score_history = list(replay.get("score_history") or ())
    dates = list(history.get("dates") or ())
    if not dates and not score_history:
        return _empty_figure("No replay history for this session")
    figure = plt.figure(figsize=(10.4, height), dpi=DPI)
    _style(figure)
    axes_score, axes_price = figure.subplots(
        2, 1, gridspec_kw={"height_ratios": [1.0, 1.4], "hspace": 0.34}
    )
    if score_history:
        positions = np.arange(len(score_history))
        axes_score.plot(
            positions,
            [entry["score"] for entry in score_history],
            color=TEAL,
            linewidth=1.5,
        )
        cutoff = replay.get("score", {}).get("cutoff")
        if cutoff is not None:
            axes_score.axhline(
                float(cutoff),
                color=AMBER,
                linestyle="--",
                linewidth=1.1,
                label=f"frozen threshold {float(cutoff):.1f}",
            )
            axes_score.legend(frameon=False, fontsize=8, labelcolor=MUTED, loc="upper left")
        tick_positions = _tick_positions(len(score_history))
        axes_score.set_xticks(tick_positions)
        axes_score.set_xticklabels(
            [score_history[position]["date"] for position in tick_positions],
            rotation=30,
            ha="right",
            fontsize=7.5,
        )
        axes_score.set_ylabel("score percentile", fontsize=8.5)
        axes_score.set_title(
            f"Score history up to the cutoff {replay.get('date')} (comparative percentile)",
            fontsize=9,
            color=MUTED,
            loc="left",
        )
        for marker in replay.get("alert_markers") or ():
            position = next(
                (
                    index
                    for index, entry in enumerate(score_history)
                    if entry["date"] == marker["date"]
                ),
                None,
            )
            if position is None:
                continue
            status = marker.get("status")
            color = {"matched": POSITIVE, "late": ALERT}.get(status, AMBER)
            axes_score.scatter(
                [position],
                [score_history[position]["score"]],
                marker="^",
                s=60,
                color=color,
                zorder=5,
            )
    _axes_style(axes_score)

    positions = np.arange(len(dates))
    closes = [np.nan if value is None else float(value) for value in history.get("closes") or ()]
    axes_price.plot(positions, closes, color=TEAL, linewidth=1.6, label="S&P 500 history")
    outcome = replay.get("outcome")
    if outcome:
        horizon_dates = list(outcome.get("dates") or ())
        horizon_closes = outcome.get("closes") or ()
        start = len(dates)
        extended_positions = [start + offset for offset in range(len(horizon_dates))]
        axes_price.plot(
            extended_positions,
            [np.nan if value is None else float(value) for value in horizon_closes],
            color=AMBER,
            linewidth=1.8,
            label="revealed outcome",
        )
        origin = outcome.get("origin") or {}
        boundary = outcome.get("boundary") or {}
        if origin.get("close") is not None:
            axes_price.axhline(
                float(origin["close"]),
                color=INK,
                linestyle="-",
                linewidth=1.0,
                alpha=0.8,
                label="origin close",
            )
        if boundary.get("close") is not None:
            axes_price.axhline(
                float(boundary["close"]),
                color=AMBER,
                linestyle="--",
                linewidth=1.2,
                label="10% boundary",
            )
        lowest = outcome.get("lowest") or {}
        if lowest.get("date") in horizon_dates:
            offset = len(dates) + horizon_dates.index(lowest["date"])
            axes_price.scatter(
                [offset],
                [float(lowest["close"])],
                marker="s",
                s=70,
                color=ALERT,
                zorder=6,
                label="lowest close",
            )
        breach = outcome.get("first_breach") or {}
        if breach.get("date") in horizon_dates:
            offset = len(dates) + horizon_dates.index(breach["date"])
            axes_price.scatter(
                [offset],
                [float(breach["close"])],
                marker="D",
                s=80,
                color=ALERT,
                edgecolors=INK,
                linewidths=0.6,
                zorder=7,
                label="first breach",
            )
        if outcome.get("pending"):
            axes_price.text(
                0.99,
                0.03,
                "Pending outcome: the 20-session horizon is incomplete",
                transform=axes_price.transAxes,
                ha="right",
                fontsize=8,
                color=AMBER,
            )
    cutoff_position = len(dates) - 1
    if cutoff_position >= 0:
        axes_price.axvline(cutoff_position, color=AMBER, linewidth=1.1, alpha=0.9)
        if outcome:
            axes_price.axvspan(
                cutoff_position,
                len(dates) + len(outcome.get("dates") or ()),
                color=AMBER,
                alpha=0.06,
            )
    all_dates = dates + list((outcome or {}).get("dates") or ())
    tick_positions = _tick_positions(len(all_dates))
    axes_price.set_xticks(tick_positions)
    axes_price.set_xticklabels(
        [all_dates[position] for position in tick_positions],
        rotation=30,
        ha="right",
        fontsize=7.5,
    )
    axes_price.set_ylabel("S&P 500 close", fontsize=8.5)
    mode_text = (
        "Blind replay: only data available at the cutoff is shown"
        if replay.get("blind")
        else "Outcome revealed for this selection"
    )
    _axes_style(axes_price)
    figure.subplots_adjust(bottom=0.19)
    figure.text(
        0.01,
        0.035,
        mode_text,
        fontsize=8.5,
        color=AMBER if replay.get("blind") else MUTED,
        ha="left",
        va="bottom",
    )
    handles, labels = axes_price.get_legend_handles_labels()
    if handles:
        axes_price.legend(
            handles=handles,
            labels=labels,
            frameon=False,
            fontsize=7.5,
            labelcolor=MUTED,
            loc="upper left",
            ncol=2,
        )
    return figure


__all__ = [
    "DPI",
    "correlation_network_figure",
    "h1_figure",
    "mapper_figure",
    "pca_figure",
    "replay_figure",
    "takens_figure",
    "timeline_figure",
]
