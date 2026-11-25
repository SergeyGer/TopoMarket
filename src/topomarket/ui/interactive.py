"""Interactive Plotly figures for the Market Structure Studio (WP-C, F03).

The landing correlation network and the shared timeline are rendered with
Plotly so visitors can select a node, hover an edge for its exact correlation
and click a timeline point to move the authoritative selected session.  The
module is Streamlit-free: it returns figures and maps Streamlit selection
events back to the same selection vocabulary used by the keyboard controls.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import plotly.graph_objects as go

from .theme import ALERT, AMBER, BORDER, CANVAS, GRID, INK, MUTED, POSITIVE, TEAL

NETWORK_KEY = "network"
TIMELINE_KEY = "timeline"

_NODE_SIZE = 34


def _rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red},{green},{blue},{alpha})"


def _base_layout(figure: go.Figure, *, height: int) -> go.Figure:
    figure.update_layout(
        paper_bgcolor=CANVAS,
        plot_bgcolor=CANVAS,
        font={"color": INK, "size": 12},
        margin={"l": 30, "r": 20, "t": 40, "b": 30},
        height=height,
        showlegend=False,
        clickmode="event+select",
        hoverlabel={"bgcolor": CANVAS, "font": {"color": INK}},
    )
    return figure


def _edge_trace(
    network: Mapping[str, Any],
    *,
    selected_code: str | None,
) -> go.Scatter:
    positions = {node["code"]: (node["x"], node["y"]) for node in network.get("nodes") or ()}
    labels = {node["code"]: node["label"] for node in network.get("nodes") or ()}
    xs: list[float | None] = []
    ys: list[float | None] = []
    texts: list[str] = []
    colors: list[str] = []
    for edge in network.get("edges") or ():
        source, target = edge["source"], edge["target"]
        if source not in positions or target not in positions:
            continue
        xs.extend([positions[source][0], positions[target][0], None])
        ys.extend([positions[source][1], positions[target][1], None])
        correlation = float(edge.get("correlation") or 0.0)
        texts.append(
            f"{labels.get(source, source)} – {labels.get(target, target)}<br>"
            f"r = {correlation:.3f} · threshold {float(network.get('cutoff') or 0.0):.2f}"
        )
        incident = selected_code in {source, target}
        colors.append(_rgba(TEAL, 0.95) if incident else _rgba(TEAL, 0.35))
    return go.Scatter(
        x=xs,
        y=ys,
        mode="lines",
        line={"width": 2.2, "color": _rgba(TEAL, 0.55)},
        hoverinfo="text",
        text=texts,
        name="correlation edges",
    )


def network_figure(
    network: Mapping[str, Any],
    *,
    selected_code: str | None = None,
    subtitle: str | None = None,
    height: int = 340,
) -> go.Figure:
    """Interactive fixed-position correlation network with node click selection."""

    figure = go.Figure()
    if not network.get("available"):
        figure.add_annotation(
            text=str(network.get("reason") or "Correlation network unavailable"),
            showarrow=False,
            font={"color": MUTED, "size": 14},
        )
        return _base_layout(figure, height=460)
    figure.add_trace(_edge_trace(network, selected_code=selected_code))
    nodes = list(network.get("nodes") or ())
    incident = {
        code
        for edge in network.get("edges") or ()
        for code in (edge["source"], edge["target"])
        if selected_code in {edge["source"], edge["target"]}
    }
    labels = [node["short_label"] for node in nodes]
    figure.add_trace(
        go.Scatter(
            x=[node["x"] for node in nodes],
            y=[node["y"] for node in nodes],
            mode="markers+text",
            text=labels,
            textposition="top center",
            textfont={"size": 12, "color": INK},
            marker={
                "size": [
                    _NODE_SIZE + 6 if node["code"] == selected_code else _NODE_SIZE
                    for node in nodes
                ],
                "color": [ALERT if node["code"] == selected_code else TEAL for node in nodes],
                "line": {
                    "color": [INK if node["code"] in incident else CANVAS for node in nodes],
                    "width": 2,
                },
                "opacity": [
                    1.0 if node["code"] in incident or not selected_code else 0.55 for node in nodes
                ],
            },
            customdata=[[node["code"], node["label"], node["degree"]] for node in nodes],
            hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]} qualifying pairs"
            "<extra>Click to inspect</extra>",
            name="industry portfolios",
        )
    )
    title = f"Correlation network · {network.get('summary')}"
    if subtitle:
        title = f"{title}<br><sup>{subtitle}</sup>"
    figure.update_layout(
        title={"text": title, "font": {"size": 16, "color": INK}, "x": 0.01},
        xaxis={"visible": False, "range": [-1.25, 1.25], "fixedrange": True},
        yaxis={"visible": False, "range": [-1.25, 1.25], "fixedrange": True},
        dragmode="select",
    )
    return _base_layout(figure, height=height)


def comparison_figure(
    comparison: Mapping[str, Any],
    *,
    selected_code: str | None = None,
) -> go.Figure:
    """Two-window network comparison with added/removed edge colours."""

    windows = comparison.get("windows") or {}
    letters = list(windows)
    figure = go.Figure()
    for column, letter in enumerate(letters):
        window = windows[letter]
        network = window.get("network") or {}
        nodes = list(network.get("nodes") or ())
        x_offset = column * 2.8
        added = {frozenset(edge) for edge in window.get("added_edges") or ()}
        removed = {frozenset(edge) for edge in window.get("removed_edges") or ()}
        positions = {node["code"]: (node["x"] + x_offset, node["y"]) for node in nodes}
        labels = {node["code"]: node["label"] for node in nodes}
        for edge in network.get("edges") or ():
            pair = frozenset((edge["source"], edge["target"]))
            colour = POSITIVE if pair in added else (_rgba(TEAL, 0.55))
            if pair in removed and letter == letters[0]:
                colour = ALERT
            figure.add_trace(
                go.Scatter(
                    x=[
                        positions[edge["source"]][0],
                        positions[edge["target"]][0],
                        None,
                    ],
                    y=[
                        positions[edge["source"]][1],
                        positions[edge["target"]][1],
                        None,
                    ],
                    mode="lines",
                    line={"width": 2.2 if pair in added else 1.6, "color": colour},
                    hoverinfo="text",
                    text=[
                        f"{labels[edge['source']]} – {labels[edge['target']]}<br>"
                        f"r = {float(edge['correlation']):.3f}",
                        "",
                        "",
                    ],
                    showlegend=False,
                )
            )
        figure.add_trace(
            go.Scatter(
                x=[position[0] for position in positions.values()],
                y=[position[1] for position in positions.values()],
                mode="markers+text",
                text=[node["short_label"] for node in nodes],
                textposition="top center",
                textfont={"size": 10.5, "color": INK},
                marker={
                    "size": [
                        _NODE_SIZE + 4 if node["code"] == selected_code else _NODE_SIZE - 4
                        for node in nodes
                    ],
                    "color": [ALERT if node["code"] == selected_code else TEAL for node in nodes],
                    "line": {"color": CANVAS, "width": 1.5},
                },
                customdata=[[node["code"], node["label"]] for node in nodes],
                hovertemplate="<b>%{customdata[1]}</b><extra></extra>",
                showlegend=False,
            )
        )
        figure.add_annotation(
            x=x_offset,
            y=1.34,
            text=(
                f"<b>{letter}</b> · {window.get('date')}<br>"
                f"{window.get('pairs_qualifying')}/{window.get('pairs_total')} pairs · "
                f"{window.get('pairs_percentage'):.1f}%"
            ),
            showarrow=False,
            font={"size": 12, "color": INK},
        )
    figure.update_layout(
        title={
            "text": f"Two-window comparison · {comparison.get('statement')}",
            "font": {"size": 14, "color": INK},
            "x": 0.01,
        },
        xaxis={"visible": False, "range": [-1.25, 1.25 + 2.8]},
        yaxis={"visible": False, "range": [-1.25, 1.5], "fixedrange": True},
        dragmode="select",
    )
    return _base_layout(figure, height=440)


def timeline_figure(
    timeline: Mapping[str, Any],
    *,
    selected_date: str | None = None,
) -> go.Figure:
    """Three aligned panels (S&P 500, VIX, score) with a clickable date cursor."""

    from plotly.subplots import make_subplots

    panes = timeline.get("panels") or {}
    sp500 = panes.get("sp500") or {}
    vix = panes.get("vix") or {}
    score = panes.get("score") or {}
    dates = list(timeline.get("dates") or ())
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        row_heights=[0.4, 0.28, 0.32],
        subplot_titles=("S&P 500", "VIX", "TDA score (comparative percentile)"),
    )
    panels = (
        (sp500, 1, TEAL, "S&P 500"),
        (vix, 2, "#2563eb", "VIX"),
        (score, 3, TEAL, "TDA score"),
    )
    for panel, row, colour, name in panels:
        values = list(panel.get("values") or ())
        if not values:
            continue
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                mode="lines+markers",
                line={"color": colour, "width": 1.6},
                marker={"size": 3.5, "color": colour, "opacity": 0.7},
                name=name,
                customdata=[[date] for date in dates],
                hovertemplate="%{x}<br>" + name + ": %{y:.2f}<extra></extra>",
            ),
            row=row,
            col=1,
        )
    threshold = score.get("threshold")
    if threshold is not None:
        figure.add_hline(
            y=float(threshold),
            line={"color": AMBER, "dash": "dash", "width": 1.1},
            row=3,
            col=1,
        )
    for marker in timeline.get("alert_markers") or ():
        date = str(marker.get("date"))
        if date not in dates:
            continue
        index = dates.index(date)
        values = list(score.get("values") or ())
        value = values[index] if index < len(values) and values[index] is not None else threshold
        figure.add_trace(
            go.Scatter(
                x=[date],
                y=[float(value) if value is not None else 50.0],
                mode="markers",
                marker={
                    "symbol": "triangle-up",
                    "size": 11,
                    "color": AMBER,
                },
                name="alert recorded",
                customdata=[[date, str(marker.get("label") or "Alert recorded")]],
                hovertemplate="%{customdata[0]}<br>%{customdata[1]}<extra></extra>",
            ),
            row=3,
            col=1,
        )
    if selected_date is not None:
        figure.add_vline(
            x=selected_date,
            line={"color": AMBER, "width": 1.0, "dash": "dot"},
        )
    figure.update_layout(
        paper_bgcolor=CANVAS,
        plot_bgcolor=CANVAS,
        font={"color": INK, "size": 11},
        height=400,
        margin={"l": 40, "r": 20, "t": 50, "b": 30},
        showlegend=False,
        hovermode="x unified",
        dragmode="select",
        clickmode="event+select",
    )
    for row in (1, 2, 3):
        figure.update_xaxes(
            gridcolor=GRID,
            linecolor=BORDER,
            row=row,
            col=1,
            showspikes=True,
            spikemode="across",
            spikethickness=1,
            spikecolor=MUTED,
        )
        figure.update_yaxes(gridcolor=GRID, linecolor=BORDER, row=row, col=1)
    return figure


def landing_figure(
    network: Mapping[str, Any],
    timeline: Mapping[str, Any],
    *,
    selected_code: str | None = None,
    selected_date: str | None = None,
    height: int = 360,
) -> go.Figure:
    """Single interactive figure: fixed network plus a clickable compact timeline.

    Keeping both visuals in one Plotly chart halves the per-rerun chart overhead
    while preserving direct node and timeline selection (WP-C/CL02).
    """

    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=2,
        cols=1,
        row_heights=[0.84, 0.16],
        vertical_spacing=0.03,
        specs=[[{"type": "xy"}], [{"type": "xy"}]],
    )
    # --- network (row 1) ---------------------------------------------------
    if network.get("available"):
        positions = {node["code"]: (node["x"], node["y"]) for node in network.get("nodes") or ()}
        labels = {node["code"]: node["label"] for node in network.get("nodes") or ()}
        xs: list[float | None] = []
        ys: list[float | None] = []
        texts: list[str] = []
        for edge in network.get("edges") or ():
            source, target = edge["source"], edge["target"]
            if source not in positions or target not in positions:
                continue
            xs.extend([positions[source][0], positions[target][0], None])
            ys.extend([positions[source][1], positions[target][1], None])
            texts.append(
                f"{labels.get(source, source)} – {labels.get(target, target)}<br>"
                f"r = {float(edge.get('correlation') or 0.0):.3f}"
            )
        figure.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"width": 1.8, "color": _rgba(TEAL, 0.5)},
                hoverinfo="text",
                text=texts,
                showlegend=False,
            ),
            row=1,
            col=1,
        )
        nodes = list(network.get("nodes") or ())
        figure.add_trace(
            go.Scatter(
                x=[node["x"] for node in nodes],
                y=[node["y"] for node in nodes],
                mode="markers+text",
                text=[node["short_label"] for node in nodes],
                textposition="top center",
                textfont={"size": 11, "color": INK},
                marker={
                    "size": [
                        _NODE_SIZE + 4 if node["code"] == selected_code else _NODE_SIZE - 2
                        for node in nodes
                    ],
                    "color": [ALERT if node["code"] == selected_code else TEAL for node in nodes],
                    "line": {"color": CANVAS, "width": 1.5},
                },
                customdata=[[node["code"], node["label"], node["degree"]] for node in nodes],
                hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]} qualifying pairs"
                "<extra>Box-select to inspect</extra>",
                showlegend=False,
            ),
            row=1,
            col=1,
        )
        figure.add_annotation(
            text="",
            xref="x domain",
            yref="y domain",
            x=0.0,
            y=1.08,
            showarrow=False,
            font={"size": 11, "color": MUTED},
        )
    # --- compact S&P 500 timeline (row 2) ----------------------------------
    panes = timeline.get("panels") or {}
    sp500 = panes.get("sp500") or {}
    window = 84
    dates = list(timeline.get("dates") or ())[-window:]
    closes = list(sp500.get("values") or ())[-window:]
    if dates and closes:
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=closes,
                mode="lines+markers",
                line={"color": TEAL, "width": 1.3},
                marker={"size": 2.5, "color": TEAL, "opacity": 0.6},
                customdata=[[date] for date in dates],
                hoverinfo="skip",
                showlegend=False,
            ),
            row=2,
            col=1,
        )
    for marker in timeline.get("alert_markers") or ():
        date = str(marker.get("date"))
        if date not in dates:
            continue
        index = dates.index(date)
        figure.add_trace(
            go.Scatter(
                x=[date],
                y=[closes[index] if index < len(closes) and closes[index] is not None else 0],
                mode="markers",
                marker={"symbol": "triangle-up", "size": 7, "color": AMBER},
                hoverinfo="skip",
                showlegend=False,
            ),
            row=2,
            col=1,
        )
    if selected_date is not None:
        figure.add_vline(
            x=selected_date,
            line={"color": AMBER, "width": 1.0, "dash": "dot"},
            row=2,
            col=1,
        )
    figure.update_layout(
        paper_bgcolor=CANVAS,
        plot_bgcolor=CANVAS,
        height=height,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        showlegend=False,
        dragmode="select",
        clickmode="event+select",
        hovermode="closest",
        hoverlabel={"bgcolor": CANVAS, "font": {"color": INK}},
    )
    figure.update_xaxes(visible=False, fixedrange=True, row=1, col=1)
    figure.update_yaxes(visible=False, fixedrange=True, row=1, col=1)
    figure.update_xaxes(
        gridcolor=GRID,
        linecolor=BORDER,
        showgrid=False,
        tickfont={"size": 8},
        row=2,
        col=1,
    )
    figure.update_yaxes(
        gridcolor=GRID,
        linecolor=BORDER,
        tickfont={"size": 8},
        nticks=3,
        row=2,
        col=1,
    )
    return figure


def landing_selection(event: Any, dates: Sequence[str], codes: Sequence[str]) -> dict[str, str]:
    """Map one click/box selection to a member code or a session date."""

    payload = selection_from_event(event)
    custom = payload.get("customdata")
    if isinstance(custom, list) and custom:
        first = custom[0]
        if isinstance(first, str):
            if first in codes:
                return {"member": first}
            if first in dates:
                return {"date": first}
    return {}


def mini_timeline_figure(
    timeline: Mapping[str, Any],
    *,
    selected_date: str | None = None,
) -> go.Figure:
    """Compact clickable S&P 500 strip for the above-the-fold landing scene."""

    panes = timeline.get("panels") or {}
    sp500 = panes.get("sp500") or {}
    dates = list(timeline.get("dates") or ())
    closes = list(sp500.get("values") or ())
    figure = go.Figure()
    if dates and closes:
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=closes,
                mode="lines+markers",
                line={"color": TEAL, "width": 1.4},
                marker={"size": 3, "color": TEAL, "opacity": 0.65},
                customdata=[[date] for date in dates],
                hovertemplate="%{x}<br>S&P 500 %{y:.2f}<extra></extra>",
                name="S&P 500",
            )
        )
    for marker in timeline.get("alert_markers") or ():
        date = str(marker.get("date"))
        if date not in dates:
            continue
        index = dates.index(date)
        figure.add_trace(
            go.Scatter(
                x=[date],
                y=[closes[index] if index < len(closes) and closes[index] is not None else 0],
                mode="markers",
                marker={"symbol": "triangle-up", "size": 7, "color": AMBER},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    if selected_date is not None:
        figure.add_vline(
            x=selected_date,
            line={"color": AMBER, "width": 1.0, "dash": "dot"},
        )
    figure.update_layout(
        paper_bgcolor=CANVAS,
        plot_bgcolor=CANVAS,
        height=80,
        margin={"l": 8, "r": 8, "t": 4, "b": 18},
        showlegend=False,
        hovermode="x unified",
        dragmode="select",
        clickmode="event+select",
        font={"color": INK, "size": 9},
    )
    figure.update_xaxes(
        gridcolor=GRID,
        linecolor=BORDER,
        showgrid=False,
        tickfont={"size": 8},
        showspikes=True,
        spikemode="across",
        spikethickness=1,
        spikecolor=MUTED,
    )
    figure.update_yaxes(
        gridcolor=GRID,
        linecolor=BORDER,
        showgrid=True,
        tickfont={"size": 8},
        nticks=3,
    )
    return figure


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    """Coerce a dict-like Streamlit value into a Mapping (PlotlyState is duck-typed)."""

    if isinstance(value, Mapping):
        return value
    for converter in ("to_dict", "dict"):
        method = getattr(value, converter, None)
        if callable(method):
            try:
                converted = method()
            except Exception:  # noqa: BLE001 - fall back to attribute access
                converted = None
            if isinstance(converted, Mapping):
                return converted
    if value is not None:
        data = getattr(value, "__dict__", None)
        if isinstance(data, dict):
            return data
    return None


def selection_from_event(event: Any) -> dict[str, Any]:
    """Map a Streamlit Plotly selection event (PlotlyState or dict) to a selection update."""

    selection: Any = None
    try:  # ``PlotlyState`` supports dictionary-style access
        selection = event["selection"]
    except Exception:  # noqa: BLE001 - fall back to attributes / mappings
        selection = getattr(event, "selection", None)
    if selection is None:
        container = _as_mapping(event)
        if container is not None:
            selection = container.get("selection")
    selection_mapping = _as_mapping(selection)
    if selection_mapping is None and selection is not None:
        try:
            selection_mapping = {"points": list(selection["points"])}
        except Exception:  # noqa: BLE001 - unreadable selection shape
            selection_mapping = None
    if selection_mapping is None:
        return {}
    points = selection_mapping.get("points") or ()
    try:
        points = list(points)
    except TypeError:
        points = ()
    for point in points:
        point_mapping = _as_mapping(point)
        if point_mapping is None:
            continue
        custom = point_mapping.get("customdata")
        if isinstance(custom, (list, tuple)) and custom:
            return {
                "customdata": list(custom),
                "curve_number": point_mapping.get("curve_number"),
            }
        point_index = point_mapping.get("point_index")
        if isinstance(point_index, int):
            return {
                "point_index": point_index,
                "curve_number": point_mapping.get("curve_number"),
            }
    return {}


def network_selection(event: Any) -> str | None:
    """Node code selected by a click on the interactive network."""

    payload = selection_from_event(event)
    custom = payload.get("customdata")
    if isinstance(custom, list) and custom:
        code = custom[0]
        if isinstance(code, str) and len(code) > 1:
            return code
    return None


def timeline_selection(event: Any, dates: Sequence[str]) -> str | None:
    """Session date selected by a click on the interactive timeline."""

    payload = selection_from_event(event)
    custom = payload.get("customdata")
    if isinstance(custom, list) and custom and isinstance(custom[0], str) and custom[0] in dates:
        return custom[0]
    position = payload.get("point_index")
    curve = payload.get("curve_number")
    if isinstance(position, int) and 0 <= position < len(dates):
        # The three panel line traces share the same date order; marker curves
        # are covered by their customdata above.
        if curve is not None and int(curve) > 2:
            return None
        return dates[position]
    return None


__all__ = [
    "NETWORK_KEY",
    "TIMELINE_KEY",
    "comparison_figure",
    "landing_figure",
    "landing_selection",
    "mini_timeline_figure",
    "network_figure",
    "network_selection",
    "selection_from_event",
    "timeline_figure",
    "timeline_selection",
]
