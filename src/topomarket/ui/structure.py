"""Structure-screen payloads: network, Mapper, shared timeline and score explanation.

The Structure screen is the public landing experience.  This module builds the
complete JSON-serialisable payload for one dashboard selection:

* the **correlation network** (UI02) from the trailing 60 valid industry
  returns up to the map date, with the fixed default cutoff and 66-pair
  accounting;
* the **Mapper view** (UI02) of the same window, with groups placed by their
  volatility lens band, node area/edge width scaling and a member inspector;
* the **shared timeline** (UI03): separate aligned S&P 500, VIX and score
  panels with a shared cursor, frozen threshold and alert markers.  VIX gaps
  stay ``None``; the industry snapshot date actually shown is exposed for the
  stale-map label;
* the **score explanation** (UI03): 56-point Takens window (dimension 3, lag 2),
  2-D display-coordinate scatter of the price embedding, H1 birth-death intervals
  with the longest finite lifetime highlighted, and the industry PCA scatter;
* the deterministic **demonstration presets** (UI01).

Everything is built from the same authoritative selected session (RE01): rows
after the selection are never read in blind replay, and the payload contains the
dates that were actually used so tests can assert it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from topomarket.analysis.asof import alert_markers as asof_alert_markers
from topomarket.analysis.industries import industry_explorer_payload
from topomarket.analysis.labels import build_breach_episodes, build_target_labels
from topomarket.analysis.network import (
    DEFAULT_CORRELATION_CUTOFF,
    DEFAULT_CORRELATION_WINDOW,
    INDUSTRY_CODES,
    INDUSTRY_LABELS,
    PAIR_COUNT,
    build_correlation_network,
    pair_lookup,
)
from topomarket.topology import load_topology_config, window_topology

from .calendars import map_observation_date
from .presets import build_presets

DEFAULT_TIMELINE_SESSIONS = 504
EXPLANATION_DIMENSION = 3
EXPLANATION_LAG = 2
EXPLANATION_WINDOW = 60
EXPLANATION_POINTS = EXPLANATION_WINDOW - (EXPLANATION_DIMENSION - 1) * EXPLANATION_LAG

PRIMARY_METHOD = "tda"


# --------------------------------------------------------------------------- #
# Small shared helpers
# --------------------------------------------------------------------------- #
def _report(data: Any) -> dict[str, Any] | None:
    reports = getattr(data, "evaluation_reports", ()) or ()
    if not reports:
        return None
    return dict(reports[0])


def _policy(data: Any) -> dict[str, Any] | None:
    report = _report(data)
    if report is None:
        return None
    policies = report.get("policies") or {}
    method = report.get("primary_method") or PRIMARY_METHOD
    policy = policies.get(method)
    return dict(policy) if isinstance(policy, Mapping) else None


def _policy_cutoff(data: Any) -> float | None:
    policy = _policy(data)
    if policy is None:
        return None
    try:
        return float(policy["cutoff"])
    except (KeyError, TypeError, ValueError):
        return None


def _score_point(data: Any, selected: str) -> dict[str, Any]:
    point = (getattr(data, "score_by_date", {}) or {}).get(selected) or {}
    raw = point.get("score")
    value: float | None
    try:
        value = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        value = None
    state = str(point.get("state") or "unavailable")
    if value is not None and not math.isfinite(value):
        value = None
    return {"date": selected, "value": value, "state": state}


def _price_rows(data: Any) -> list[dict[str, Any]]:
    rows = getattr(data, "price_rows", None)
    if rows is None:
        rows = getattr(data, "rows", ()) or ()
    return [dict(row) for row in rows]


def _industry_rows(data: Any) -> list[dict[str, Any]]:
    rows = getattr(data, "industry_rows", None)
    if rows is None:
        rows = getattr(data, "rows", ()) or ()
    return [dict(row) for row in rows]


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _trailing_dates(rows: Sequence[Mapping[str, Any]], selected: str, limit: int) -> list[str]:
    dates = [
        str(row.get("date")) for row in rows if row.get("date") and str(row.get("date")) <= selected
    ]
    return dates[-limit:]


# --------------------------------------------------------------------------- #
# Shared timeline (UI03)
# --------------------------------------------------------------------------- #
def build_timeline(data: Any, selected: str, *, blinded: bool = False) -> dict[str, Any]:
    """Build the three aligned panels for the selected session.

    ``blinded`` keeps the alert markers neutral (F02): the timeline must not
    reveal retrospective classifications before the visitor enters the review
    flow.
    """

    price_rows = _price_rows(data)
    price_by_date = {str(row.get("date")): row for row in price_rows if row.get("date")}
    dates = _trailing_dates(price_rows, selected, DEFAULT_TIMELINE_SESSIONS)
    if selected not in dates and dates:
        dates = dates[1:] + [selected] if selected > dates[-1] else dates
    closes = [_float(price_by_date.get(date, {}).get("sp500_close")) for date in dates]
    joined_by_date = {
        str(row.get("date")): row for row in (getattr(data, "rows", ()) or ()) if row.get("date")
    }
    vix_values: list[float | None] = [
        _float(joined_by_date.get(date, {}).get("vix_close")) for date in dates
    ]
    score_by_date = getattr(data, "score_by_date", {}) or {}
    score_values: list[float | None] = []
    for date in dates:
        point = score_by_date.get(date) or {}
        raw = point.get("score")
        try:
            value = float(raw) if raw not in (None, "") and point.get("state") == "scored" else None
        except (TypeError, ValueError):
            value = None
        score_values.append(value if value is not None and math.isfinite(value) else None)
    cutoff = _policy_cutoff(data)
    alerts = _timeline_alerts(data, selected, blinded=blinded)
    return {
        "available": bool(dates),
        "selected": selected,
        "dates": dates,
        "window_sessions": len(dates),
        "panels": {
            "sp500": {
                "panel_id": "sp500",
                "label": "S&P 500",
                "unit": "index points",
                "values": closes,
                "palette": "sp500",
            },
            "vix": {
                "panel_id": "vix",
                "label": "VIX",
                "unit": "index points",
                "values": vix_values,
                "missing_sessions": sum(1 for value in vix_values if value is None),
                "palette": "vix",
            },
            "score": {
                "panel_id": "score",
                "label": "TDA score",
                "unit": "percentile (comparative)",
                "values": score_values,
                "threshold": cutoff,
                "threshold_label": None if cutoff is None else f"Frozen threshold {cutoff:.2f}",
                "alert_markers": alerts,
                "palette": "score",
            },
        },
        "alert_markers": alerts,
        "threshold": cutoff,
        "legend": "Teal: S&P 500. Blue: VIX. Teal score line: comparative percentile. "
        "Amber dashed line: frozen alert threshold. Amber triangles: alerts.",
        "accessibility": "Alerts are also listed in the alert table and marked with symbols.",
    }


def _timeline_alerts(data: Any, selected: str, *, blinded: bool) -> list[dict[str, Any]]:
    """Causally available alert markers (neutral in blind mode)."""

    return asof_alert_markers(data, selected, blinded=blinded)


# --------------------------------------------------------------------------- #
# Two-window comparison (Studio C1)
# --------------------------------------------------------------------------- #
def _pair_key(edge: Mapping[str, Any]) -> tuple[str, str]:
    return (str(edge.get("source")), str(edge.get("target")))


def _network_metrics(network: Mapping[str, Any]) -> dict[str, Any]:
    pairs = [pair for pair in network.get("pairs") or () if pair.get("correlation") is not None]
    values = [float(pair["correlation"]) for pair in pairs]
    total = int(network.get("pairs_total") or PAIR_COUNT)
    qualifying = int(network.get("pairs_qualifying") or 0)
    return {
        "pairs_qualifying": qualifying,
        "pairs_total": total,
        "pairs_percentage": 100.0 * qualifying / total if total else 0.0,
        "mean_off_diagonal_correlation": sum(values) / len(values) if values else None,
        "defined_pairs": len(values),
        "missing_pairs": len(network.get("undefined_pairs") or ())
        + max(0, total - len(values) - len(network.get("undefined_pairs") or ())),
    }


def _same_episode(data: Any, left_date: str, right_date: str) -> bool:
    """Both windows lie inside the same synthetic drawdown episode's context."""

    rows = _price_rows(data)
    dates = [str(row.get("date")) for row in rows]
    try:
        labels = build_target_labels(rows)
        episodes = build_breach_episodes(labels)
    except Exception:  # noqa: BLE001 - comparison stays usable without labels
        return False
    positions = {date: index for index, date in enumerate(dates)}
    left = positions.get(left_date)
    right = positions.get(right_date)
    if left is None or right is None:
        return False
    for episode in episodes:
        window_start = max(0, episode.start_index - 30)
        window_end = min(len(dates) - 1, episode.end_index + 10)
        if window_start <= left <= window_end and window_start <= right <= window_end:
            return True
    return False


def build_window_comparison(
    data: Any,
    left_date: str,
    right_date: str,
    *,
    cutoff: float = DEFAULT_CORRELATION_CUTOFF,
    window: int = DEFAULT_CORRELATION_WINDOW,
) -> dict[str, Any]:
    """Compare two explicitly dated correlation windows (fixed layout/scale).

    The statement never claims chronological crisis emergence unless the right
    window is later, the qualified-pair increase is material and both windows
    belong to the same drawdown-episode context; otherwise it is presented as a
    regime contrast between two independent dated windows.
    """

    rows = _industry_rows(data)
    left = build_correlation_network(rows, left_date, window=window, cutoff=cutoff)
    right = build_correlation_network(rows, right_date, window=window, cutoff=cutoff)
    if not left.get("available") or not right.get("available"):
        return {
            "available": False,
            "reason": left.get("reason") or right.get("reason") or "comparison unavailable",
        }
    left_metrics = _network_metrics(left)
    right_metrics = _network_metrics(right)
    left_pairs = {_pair_key(edge) for edge in left.get("edges") or ()}
    right_pairs = {_pair_key(edge) for edge in right.get("edges") or ()}
    left_correlation = {
        _pair_key(edge): edge.get("correlation") for edge in left.get("edges") or ()
    }
    right_correlation = {
        _pair_key(edge): edge.get("correlation") for edge in right.get("edges") or ()
    }
    added = [
        {
            "source": source,
            "target": target,
            "correlation": right_correlation.get((source, target)),
        }
        for source, target in sorted(right_pairs - left_pairs)
    ]
    removed = [
        {
            "source": source,
            "target": target,
            "correlation": left_correlation.get((source, target)),
        }
        for source, target in sorted(left_pairs - right_pairs)
    ]
    delta = right_metrics["pairs_qualifying"] - left_metrics["pairs_qualifying"]
    material_increase = delta >= max(5, int(round(PAIR_COUNT * 0.10)))
    chronological = right_date > left_date
    same_episode = _same_episode(data, left_date, right_date)
    sequence_claim = bool(chronological and material_increase and same_episode)
    if sequence_claim:
        statement = (
            f"Chronological windows from the same episode: {left_date} → {right_date}, "
            f"+{delta} qualified pairs"
        )
    elif chronological:
        statement = (
            f"Chronological windows {left_date} → {right_date}; the change is shown as a "
            "regime contrast, not as proven crisis emergence"
        )
    else:
        statement = (
            f"Regime contrast: {left_date} vs {right_date}; the later-dated window is "
            f"{left_date}, so no chronological crisis-emergence claim is made"
        )
    return {
        "available": True,
        "cutoff": float(cutoff),
        "window_sessions": int(window),
        "left_date": left_date,
        "right_date": right_date,
        "chronological": chronological,
        "same_episode": same_episode,
        "material_increase": material_increase,
        "sequence_claim": sequence_claim,
        "statement": statement,
        "delta_pairs": delta,
        "delta_percentage_points": right_metrics["pairs_percentage"]
        - left_metrics["pairs_percentage"],
        "added_edges": added,
        "removed_edges": removed,
        "added_count": len(added),
        "removed_count": len(removed),
        "windows": {
            "A": {
                "date": left_date,
                "network": left,
                **left_metrics,
                # Edges removed going A -> B are drawn in A with a distinct style.
                "removed_edges": removed,
                "added_edges": [],
            },
            "B": {
                "date": right_date,
                "network": right,
                **right_metrics,
                # Edges added going A -> B are drawn in B with a distinct style.
                "added_edges": added,
                "removed_edges": [],
            },
        },
        "edge_density_note": (
            "Edge density is the share of the 66 industry pairs with Pearson r above the fixed "
            "0.80 cutoff; it is not the topological anomaly score."
        ),
        "table_alternative": _comparison_table(
            left_date, right_date, left_metrics, right_metrics, delta
        ),
    }


def _comparison_table(
    left_date: str,
    right_date: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    delta: int,
) -> str:
    labels = (
        ("date", left_date, right_date),
        ("qualified pairs", left["pairs_qualifying"], right["pairs_qualifying"]),
        (
            "percentage of 66",
            f"{left['pairs_percentage']:.1f}%",
            f"{right['pairs_percentage']:.1f}%",
        ),
        (
            "mean off-diagonal correlation",
            f"{left['mean_off_diagonal_correlation']:.3f}"
            if left["mean_off_diagonal_correlation"] is not None
            else "n/a",
            f"{right['mean_off_diagonal_correlation']:.3f}"
            if right["mean_off_diagonal_correlation"] is not None
            else "n/a",
        ),
        ("missing/undefined pairs", left["missing_pairs"], right["missing_pairs"]),
        ("change in qualified pairs", delta, ""),
    )
    lines = ["metric, window A, window B"]
    lines.extend(f"{name}, {first}, {second}" for name, first, second in labels)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Mapper view (UI02)
# --------------------------------------------------------------------------- #
def _mapper_payload(data: Any, map_date: str) -> dict[str, Any]:
    cache = getattr(data, "_topology_cache", None)
    key = f"structure-mapper:{map_date}"
    if isinstance(cache, dict) and key in cache:
        return cache[key]
    rows = _industry_rows(data)
    # ``industry_explorer_payload`` parses every supplied row before selecting the
    # trailing window; handing it only the sessions near the map date keeps a
    # warm date change well below the UI performance budget while producing the
    # identical window.
    windowed = [row for row in rows if str(row.get("date") or "") <= map_date][-180:]
    payload = industry_explorer_payload(windowed, as_of=map_date)
    payload["row_count"] = len(windowed)
    if isinstance(cache, dict):
        cache[key] = payload
    return payload


def _label_to_code(data: Any, map_payload: Mapping[str, Any]) -> dict[str, str]:
    labels = [str(value) for value in map_payload.get("industry_labels") or ()]
    return {label: code for label, code in zip(labels, INDUSTRY_CODES, strict=False)}


def _members_as_codes(labels: Sequence[Any], label_to_code: Mapping[str, str]) -> list[str]:
    codes: list[str] = []
    for label in labels:
        code = label_to_code.get(str(label))
        if code is not None and code not in codes:
            codes.append(code)
    return codes


def build_mapper_view(
    data: Any,
    map_date: str,
    *,
    selected_node: str | None = None,
    selected_edge: str | None = None,
    selected_member: str | None = None,
) -> dict[str, Any]:
    """Build the Mapper payload with volatility-band placement and inspectors."""

    try:
        root = _mapper_payload(data, map_date)
    except Exception as error:  # noqa: BLE001 - short windows are an explicit state
        return _empty_mapper_view(map_date, str(error))
    payload = root.get("mapper") if isinstance(root.get("mapper"), Mapping) else root
    label_to_code = _label_to_code(data, payload)
    intervals = list(payload.get("intervals") or ())
    raw_nodes = list(payload.get("nodes") or ())
    raw_edges = list(payload.get("edges") or ())
    correlation_matrix = payload.get("correlation_matrix") or root.get("correlation_matrix") or ()
    codes_in_order = list(INDUSTRY_CODES)
    nodes: list[dict[str, Any]] = []
    bands: dict[int, list[dict[str, Any]]] = {}
    for raw in raw_nodes:
        band = int(raw.get("interval_index") or 0)
        codes = _members_as_codes(raw.get("industries") or raw.get("members") or (), label_to_code)
        node = {
            "node_id": str(raw.get("node_id") or raw.get("id")),
            "interval_index": band,
            "band_lower": _interval_value(intervals, band, "lower"),
            "band_upper": _interval_value(intervals, band, "upper"),
            "members": [{"code": code, "label": INDUSTRY_LABELS[code]} for code in codes],
            "member_codes": codes,
            "member_count": int(raw.get("member_count") or raw.get("size") or len(codes)),
            "volatility": _float(raw.get("mean_volatility") or raw.get("volatility")),
            "member_volatilities": [
                {"code": code, "volatility": _float(volatility)}
                for code, volatility in zip(
                    codes, raw.get("member_volatilities") or (), strict=False
                )
            ],
            "within_group_correlations": _within_group_correlations(
                correlation_matrix, codes, codes_in_order
            ),
        }
        bands.setdefault(band, []).append(node)
    for band in sorted(bands):
        ordered = sorted(bands[band], key=lambda node: node["node_id"])
        for position, node in enumerate(ordered):
            node["band_index"] = list(sorted(bands)).index(band)
            node["x"] = float(node["band_index"])
            node["y"] = float(position) - (len(ordered) - 1) / 2.0
            node["display_size"] = 18.0 + 8.0 * node["member_count"]
        nodes.extend(ordered)
    edges: list[dict[str, Any]] = []
    for raw in raw_edges:
        shared_codes = _members_as_codes(
            raw.get("shared_members") or raw.get("members") or (), label_to_code
        )
        edges.append(
            {
                "edge_id": str(raw.get("edge_id") or raw.get("id")),
                "source": str(raw.get("source_id") or raw.get("source")),
                "target": str(raw.get("target_id") or raw.get("target")),
                "overlap": int(
                    raw.get("shared_member_count") or raw.get("overlap") or len(shared_codes)
                ),
                "shared_members": [
                    {"code": code, "label": INDUSTRY_LABELS[code]} for code in shared_codes
                ],
                "width": 1.0 + float(raw.get("shared_member_count") or raw.get("overlap") or 1),
            }
        )
    band_summary = [
        {
            "band_index": index,
            "lower": _interval_value(intervals, band, "lower"),
            "upper": _interval_value(intervals, band, "upper"),
            "node_ids": [node["node_id"] for node in bands[band]],
            "member_count": sum(node["member_count"] for node in bands[band]),
        }
        for index, band in enumerate(sorted(bands))
    ]
    selected = selected_node
    if selected is None and selected_member:
        for node in nodes:
            if selected_member in node["member_codes"]:
                selected = node["node_id"]
                break
    if selected is None and nodes:
        selected = nodes[0]["node_id"]
    inspector = _mapper_inspector(nodes, labels=label_to_code, selected=selected)
    selected_edge_payload = next((edge for edge in edges if edge["edge_id"] == selected_edge), None)
    return {
        "view": "mapper",
        "available": bool(nodes),
        "as_of": map_date,
        "window": {
            "start": root.get("start_date") or payload.get("start_date"),
            "end": root.get("end_date") or payload.get("end_date"),
            "sessions": root.get("window_sessions") or payload.get("window_sessions"),
        },
        "threshold": payload.get("threshold"),
        "bands": band_summary,
        "nodes": nodes,
        "edges": edges,
        "selected_node_id": selected,
        "selected_edge": selected_edge_payload,
        "member_inspector": inspector,
        "position_rule": "columns are volatility lens bands (low to high); within a band nodes are "
        "sorted by node id (deterministic tie-breaking)",
        "legend": "Circle area = member count. Edge width = number of shared portfolios. "
        "Columns = volatility lens bands.",
        "table_alternative": _mapper_table(nodes, edges),
        "reason": None if nodes else "no Mapper groups for this window",
    }


def _empty_mapper_view(map_date: str, reason: str) -> dict[str, Any]:
    """Return the explicit unavailable Mapper view (for example a short window)."""

    return {
        "view": "mapper",
        "available": False,
        "as_of": map_date,
        "window": {"start": None, "end": map_date, "sessions": 0},
        "threshold": None,
        "bands": [],
        "nodes": [],
        "edges": [],
        "selected_node_id": None,
        "selected_edge": None,
        "member_inspector": {"node_id": None, "members": [], "volatility": None},
        "position_rule": "columns are volatility lens bands (low to high); within a band nodes are "
        "sorted by node id (deterministic tie-breaking)",
        "legend": "Circle area = member count. Edge width = number of shared portfolios.",
        "table_alternative": "Mapper unavailable",
        "reason": reason,
    }


def _interval_value(intervals: Sequence[Mapping[str, Any]], band: int, key: str) -> float | None:
    if band < 0 or band >= len(intervals):
        return None
    return _float(intervals[band].get(key))


def _within_group_correlations(
    matrix: Any, member_codes: Sequence[str], codes_in_order: Sequence[str]
) -> list[dict[str, Any]]:
    try:
        array = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError):
        return []
    if array.ndim != 2 or array.shape[0] != len(codes_in_order):
        return []
    positions = {code: index for index, code in enumerate(codes_in_order)}
    result: list[dict[str, Any]] = []
    for code in member_codes:
        position = positions.get(code)
        if position is None:
            continue
        others = [
            positions[other] for other in member_codes if other != code and other in positions
        ]
        values = [
            float(array[position, other])
            for other in others
            if math.isfinite(array[position, other])
        ]
        result.append(
            {
                "code": code,
                "mean_correlation": float(sum(values) / len(values)) if values else None,
                "pair_count": len(values),
            }
        )
    return result


def _mapper_inspector(
    nodes: Sequence[Mapping[str, Any]], *, labels: Mapping[str, str], selected: str | None
) -> dict[str, Any]:
    node = next((item for item in nodes if item["node_id"] == selected), None)
    if node is None:
        return {"node_id": None, "members": [], "volatility": None}
    members = []
    for entry in node["within_group_correlations"]:
        members.append(
            {
                "code": entry["code"],
                "label": INDUSTRY_LABELS[entry["code"]],
                "volatility": next(
                    (
                        value["volatility"]
                        for value in node["member_volatilities"]
                        if value["code"] == entry["code"]
                    ),
                    None,
                ),
                "within_group_correlation": entry["mean_correlation"],
                "pair_count": entry["pair_count"],
            }
        )
    return {
        "node_id": node["node_id"],
        "band_index": node["band_index"],
        "band": [node["band_lower"], node["band_upper"]],
        "member_count": node["member_count"],
        "volatility": node["volatility"],
        "members": members,
    }


def _mapper_table(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> str:
    lines = ["Node, Band, Members, Volatility"]
    for node in nodes:
        lines.append(
            f"{node['node_id']}, {node['band_index']}, "
            f"{'; '.join(entry['label'] for entry in node['members'])}, {node['volatility']}"
        )
    lines.append("Edge, Source, Target, Shared portfolios")
    for edge in edges:
        lines.append(
            f"{edge['edge_id']}, {edge['source']}, {edge['target']}, "
            f"{'; '.join(entry['label'] for entry in edge['shared_members'])}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Score explanation (UI03)
# --------------------------------------------------------------------------- #
def _return_series(
    rows: Sequence[Mapping[str, Any]], selected: str
) -> tuple[list[str], list[float]]:
    dates: list[str] = []
    values: list[float] = []
    for row in rows:
        date = str(row.get("date"))
        if date > selected:
            break
        value = _float(row.get("sp500_log_return"))
        if value is None:
            continue
        dates.append(date)
        values.append(value)
    return dates, values


def _display_coordinates(points: np.ndarray) -> np.ndarray:
    centred = points - points.mean(axis=0, keepdims=True)
    try:
        u, s, _vh = np.linalg.svd(centred, full_matrices=False)
    except np.linalg.LinAlgError:  # pragma: no cover - defensive
        return centred[:, :2]
    scaled = u[:, :2] * s[:2]
    return np.asarray(scaled, dtype=float)


def build_explanation(data: Any, selected: str, *, map_date: str | None = None) -> dict[str, Any]:
    """Build the Takens/H1/PCA explanation for the selected session."""

    cache = getattr(data, "_topology_cache", None)
    cache_key = f"explanation:{selected}"
    if isinstance(cache, dict) and cache_key in cache:
        return cache[cache_key]
    explanation = _build_explanation_uncached(data, selected, map_date=map_date)
    if isinstance(cache, dict):
        cache[cache_key] = explanation
    return explanation


def _build_explanation_uncached(
    data: Any, selected: str, *, map_date: str | None = None
) -> dict[str, Any]:
    rows = _price_rows(data)
    dates, returns = _return_series(rows, selected)
    config = load_topology_config()
    result = (
        window_topology(returns, config, date=selected)
        if len(returns) >= EXPLANATION_WINDOW
        else None
    )
    base: dict[str, Any] = {
        "available": False,
        "reason": None,
        "selected": selected,
        "window": {
            "sessions": config.window_sessions,
            "dimension": config.embedding_dimension,
            "lag": config.lag,
            "points": EXPLANATION_POINTS,
        },
        "display_note": "Display coordinates: 2-component projection of the full "
        f"{config.embedding_dimension}-D delay embedding.",
        "takens": None,
        "h1": None,
        "industry_pca": None,
        "score": _score_point(data, selected),
        "threshold": _policy_cutoff(data),
    }
    if result is None or not result.available or result.points is None:
        base["reason"] = (
            result.reason
            if result is not None
            else "fewer than 60 valid returns before the session"
        )
        return base
    points = np.asarray(result.points, dtype=float)
    display = _display_coordinates(points)
    window_dates = dates[-config.window_sessions :]
    embedded_dates = window_dates[: points.shape[0]]
    h1 = np.asarray(result.h1, dtype=float) if len(result.h1) else np.empty((0, 2))
    intervals: list[dict[str, Any]] = []
    longest_index: int | None = None
    longest_lifetime = -math.inf
    for index, (birth, death) in enumerate(h1):
        lifetime = float(death - birth)
        intervals.append(
            {
                "index": index,
                "birth": float(birth),
                "death": float(death) if math.isfinite(death) else None,
                "lifetime": lifetime if math.isfinite(lifetime) else None,
                "is_longest": False,
            }
        )
        if math.isfinite(lifetime) and lifetime > longest_lifetime:
            longest_lifetime = lifetime
            longest_index = index
    if longest_index is not None:
        intervals[longest_index]["is_longest"] = True
    base.update(
        {
            "available": True,
            "takens": {
                "points": [
                    {
                        "index": index,
                        "x": float(display[index, 0]),
                        "y": float(display[index, 1]),
                        "date": embedded_dates[index] if index < len(embedded_dates) else None,
                    }
                    for index in range(display.shape[0])
                ],
                "highlight_index": max(0, display.shape[0] - 1),
                "window_start": window_dates[0] if window_dates else None,
                "window_end": selected,
                "coordinates": "display",
            },
            "h1": {
                "intervals": intervals,
                "longest_index": longest_index,
                "longest_lifetime": None if longest_index is None else longest_lifetime,
                "diagonal": True,
                "note": "H1 birth-death diagram with the diagonal reference; the amber point "
                "is the longest finite lifetime used by the anomaly score.",
            },
            "score_detail": {
                "L": _float(result.L),
                "h1_count": int(h1.shape[0]),
            },
        }
    )
    industry_pca = _industry_pca(data, map_date or selected)
    if industry_pca is not None:
        base["industry_pca"] = industry_pca
    return base


def _industry_pca(data: Any, map_date: str) -> dict[str, Any] | None:
    payload = _mapper_payload(data, map_date)
    cloud = payload.get("cloud") or {}
    projection = cloud.get("pca") or ()
    dates = list(cloud.get("dates") or ())
    if not projection:
        return None
    points = []
    for index, pair in enumerate(projection):
        if not isinstance(pair, Sequence) or len(pair) < 2:
            continue
        points.append(
            {
                "index": index,
                "date": dates[index] if index < len(dates) else None,
                "x": _float(pair[0]),
                "y": _float(pair[1]),
            }
        )
    ratios = list(cloud.get("explained_variance_ratio") or ())
    return {
        "points": points,
        "count": len(points),
        "explained_variance_ratio": [_float(value) for value in ratios[:2]],
        "label": "Industry PCA display coordinates (each point is one session)",
        "window_end": dates[-1] if dates else None,
    }


# --------------------------------------------------------------------------- #
# Structure payload (UI01/UI02/UI03)
# --------------------------------------------------------------------------- #
def build_structure_payload(
    data: Any,
    selection: Any,
    *,
    cutoff: float = DEFAULT_CORRELATION_CUTOFF,
    window: int = DEFAULT_CORRELATION_WINDOW,
) -> dict[str, Any]:
    """Build the complete Structure-screen payload for one selection."""

    selected = data.selected_date(selection)
    map_info = map_observation_date(data, selected)
    map_date = map_info.get("date") or selected
    industry_rows = _industry_rows(data)
    network = build_correlation_network(industry_rows, map_date, window=window, cutoff=cutoff)
    if not network["available"] and map_date != selected:
        network = build_correlation_network(industry_rows, selected, window=window, cutoff=cutoff)
    view = getattr(selection, "view", None) or "correlation"
    if str(getattr(selection, "network_view", "correlation")) == "mapper":
        mapper = build_mapper_view(
            data,
            map_date,
            selected_node=getattr(selection, "node", None),
            selected_edge=getattr(selection, "edge", None),
            selected_member=getattr(selection, "member", None),
        )
    else:
        # The correlation view does not render Mapper groups; defer the expensive
        # Mapper window until the visitor switches views.
        mapper = _empty_mapper_view(map_date, "Switch to the Mapper view to build the groups.")
        mapper["deferred"] = True
    blind = str(getattr(selection, "mode", "live")).lower() in {
        "replay",
        "historical",
    } and not bool(getattr(selection, "reveal", False))
    timeline = build_timeline(data, selected, blinded=blind)
    selected_is_alert = any(
        marker.get("date") == selected for marker in timeline.get("alert_markers") or ()
    )
    explanation = (
        build_explanation(data, selected, map_date=map_date)
        if selected_is_alert or getattr(selection, "explain", False)
        else {
            "available": False,
            "deferred": True,
            "selected": selected,
            "reason": "Select an alert on the timeline to open its Takens/H1 explanation.",
        }
    )
    presets = build_presets(data)
    mode = str(getattr(selection, "mode", "live"))
    revealed = bool(getattr(selection, "reveal", False))
    inline_outcome = None
    if mode == "replay" and revealed:
        from .replay import build_outcome

        inline_outcome = build_outcome(data, selected)
    if mode == "replay" and not revealed:
        presets = _blind_safe_presets(presets, selected)
    score = _score_point(data, selected)
    cutoff_value = _policy_cutoff(data)
    cutoff_status = {
        "state": "unavailable"
        if score["value"] is None
        else (
            "above"
            if cutoff_value is not None and score["value"] >= cutoff_value
            else ("below" if cutoff_value is not None else "no_frozen_policy")
        ),
        "cutoff": cutoff_value,
    }
    member_inspector = _correlation_member_inspector(network, getattr(selection, "member", None))
    score_text = "unavailable" if score["value"] is None else f"{score['value']:.1f} percentile"
    payload: dict[str, Any] = {
        "screen": "structure",
        "title": "Structure",
        "mode": str(getattr(selection, "mode", "live")),
        "date": selected,
        "view": view,
        "synthetic": bool(getattr(data, "demo", False)),
        "data_source": "synthetic demo" if getattr(data, "demo", False) else "private research",
        "snapshot_id": getattr(data, "snapshot_id", None),
        "fixture_id": presets["fixture_id"],
        "map_observation": map_info,
        "network": network,
        "mapper": mapper,
        "timeline": timeline,
        "explanation": explanation,
        "score": {**score, "cutoff_status": cutoff_status, "comparative": True},
        "presets": presets,
        "member_inspector": member_inspector,
        "legend": "Neutral canvas. Teal market series. Amber threshold and alerts. "
        "Correlation edges are positive Pearson correlations at the fixed cutoff.",
        "accessible_summary": (
            f"Structure for {selected}: {network['summary']}; "
            f"{len(mapper['nodes'])} Mapper group(s); score {score_text}"
        ),
        "replay": {
            "blind": mode == "replay" and not revealed,
            "revealed": revealed,
            "outcome": inline_outcome,
        },
    }
    return payload


def _blind_safe_presets(presets: Mapping[str, Any], selected: str) -> dict[str, Any]:
    """Do not reveal demonstration dates after the blind-replay cutoff."""

    records: list[dict[str, Any]] = []
    for record in presets.get("presets") or ():
        entry = dict(record)
        date = entry.get("date")
        if date and str(date) > selected:
            entry.update(
                {
                    "date": None,
                    "verified": False,
                    "expected": [],
                    "reason": "preset date is after the blind replay cutoff",
                }
            )
        records.append(entry)
    return {
        **presets,
        "presets": records,
        "available": [record["preset_id"] for record in records if record["verified"]],
        "blind_filtered": True,
    }


def _correlation_member_inspector(network: Mapping[str, Any], member: str | None) -> dict[str, Any]:
    if not member:
        return {"selected": None, "pairs": [], "degree": None}
    node = next((item for item in network.get("nodes") or () if item.get("code") == member), None)
    if node is None:
        return {"selected": member, "pairs": [], "degree": None, "reason": "unknown industry"}
    lookup = pair_lookup(network)
    pairs = []
    for other in INDUSTRY_CODES:
        if other == member:
            continue
        key = (member, other) if member <= other else (other, member)
        value = lookup.get(key)
        pairs.append(
            {
                "code": other,
                "label": INDUSTRY_LABELS[other],
                "correlation": value,
                "qualifies": bool(value is not None and value >= network.get("cutoff", 0.0)),
            }
        )
    pairs.sort(key=lambda item: (-(item["correlation"] or -1.0), item["code"]))
    return {
        "selected": member,
        "label": INDUSTRY_LABELS[member],
        "degree": int(node.get("degree") or 0),
        "pairs": pairs,
        "note": "Pair values are Pearson correlations over the displayed window.",
    }


__all__ = [
    "DEFAULT_TIMELINE_SESSIONS",
    "EXPLANATION_DIMENSION",
    "EXPLANATION_LAG",
    "EXPLANATION_POINTS",
    "EXPLANATION_WINDOW",
    "build_explanation",
    "build_mapper_view",
    "build_structure_payload",
    "build_timeline",
]
