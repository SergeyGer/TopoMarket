"""Deterministic correlation network over the 12 US industry portfolios (UI02).

The Structure screen shows two complementary views of the same 60-session
window: a Pearson correlation network (this module) and the Mapper groups
(:mod:`topomarket.analysis.mapper`).  This module is intentionally free of UI
and plotting imports so the numeric payload can be tested offline and reused by
the Streamlit shell, the social-preview builder and the demo-video fixtures.

Conventions
-----------

* The window is the trailing 60 **valid** daily return rows up to and including
  the selected session.  A row is valid when every one of the 12 industry
  returns parses as a finite number; the window never includes sessions after
  the selected date, so it is safe for blind replay.
* Pearson correlations are computed on the raw simple daily returns in the
  window.  A pair whose series has zero variance is reported as ``undefined``
  instead of being silently drawn as zero.
* Positive edges are drawn at ``r >= cutoff`` (default ``0.80``).  The payload
  always reports the cutoff, the number of qualifying pairs and the fixed pair
  count (66) so the UI can state "n/66".
* Node positions are fixed upstream so the graph does not jump between
  reruns or date changes (UI04).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: The 12 Kenneth French industry portfolio codes used by the dataset.
INDUSTRY_CODES: tuple[str, ...] = (
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

#: Human-readable labels used in the graph, inspectors and tables.
INDUSTRY_LABELS: Mapping[str, str] = {
    "nodur": "Consumer nondurables",
    "durbl": "Consumer durables",
    "manuf": "Manufacturing",
    "enrgy": "Energy",
    "chems": "Chemicals",
    "buseq": "Business equipment",
    "telcm": "Telecom",
    "utils": "Utilities",
    "shops": "Wholesale & retail",
    "hlth": "Healthcare",
    "money": "Finance",
    "other": "Other industries",
}

#: Short labels that stay readable at 390 px width and in narrow graph nodes.
INDUSTRY_SHORT_LABELS: Mapping[str, str] = {
    "nodur": "Nondurables",
    "durbl": "Durables",
    "manuf": "Manufacturing",
    "enrgy": "Energy",
    "chems": "Chemicals",
    "buseq": "Bus. equipment",
    "telcm": "Telecom",
    "utils": "Utilities",
    "shops": "Retail",
    "hlth": "Healthcare",
    "money": "Finance",
    "other": "Other",
}

#: Trailing window length in sessions, shared with the Mapper view.
DEFAULT_CORRELATION_WINDOW = 60

#: Fixed default positive-edge cutoff (displayed in the UI).
DEFAULT_CORRELATION_CUTOFF = 0.80

#: Number of unordered pairs among 12 nodes.
PAIR_COUNT = len(INDUSTRY_CODES) * (len(INDUSTRY_CODES) - 1) // 2

#: Return-column prefix/suffix: ``ind_<code>_return``.
RETURN_COLUMN_TEMPLATE = "ind_{code}_return"


class NetworkError(ValueError):
    """Raised when a correlation-network payload cannot be constructed."""


@dataclass(frozen=True, slots=True)
class IndustryNode:
    """One industry node with fixed display coordinates."""

    code: str
    label: str
    short_label: str
    x: float
    y: float

    @property
    def id(self) -> str:
        return f"ind_{self.code}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "label": self.label,
            "short_label": self.short_label,
            "x": self.x,
            "y": self.y,
        }


def fixed_node_positions(
    *, radius: float = 1.0, center: tuple[float, float] = (0.0, 0.0)
) -> dict[str, tuple[float, float]]:
    """Return the fixed circular layout used by every view and the video.

    The first industry sits at the top and the order follows
    :data:`INDUSTRY_CODES`, so labels and positions are identical for every
    date and every rerun.
    """

    positions: dict[str, tuple[float, float]] = {}
    count = len(INDUSTRY_CODES)
    for index, code in enumerate(INDUSTRY_CODES):
        angle = math.pi / 2.0 - (2.0 * math.pi * index) / count
        positions[code] = (
            float(center[0] + radius * math.cos(angle)),
            float(center[1] + radius * math.sin(angle)),
        )
    return positions


def industry_nodes() -> tuple[IndustryNode, ...]:
    """Return the fixed node list (stable order and coordinates)."""

    positions = fixed_node_positions()
    return tuple(
        IndustryNode(
            code=code,
            label=INDUSTRY_LABELS[code],
            short_label=INDUSTRY_SHORT_LABELS[code],
            x=positions[code][0],
            y=positions[code][1],
        )
        for code in INDUSTRY_CODES
    )


def return_column(code: str) -> str:
    """Return the normalized return column name for an industry code."""

    return RETURN_COLUMN_TEMPLATE.format(code=code)


def _row_returns(row: Mapping[str, Any]) -> tuple[float, ...] | None:
    """Return the 12 finite industry returns for a row, or ``None``."""

    values: list[float] = []
    for code in INDUSTRY_CODES:
        raw = row.get(return_column(code))
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        values.append(value)
    return tuple(values)


def select_correlation_window(
    rows: Sequence[Mapping[str, Any]],
    as_of: str,
    *,
    window: int = DEFAULT_CORRELATION_WINDOW,
) -> dict[str, Any]:
    """Select the trailing valid-return window ending at ``as_of``.

    Returns a payload with ``dates``, ``returns`` per industry, ``missing``
    observations and an explicit ``available`` flag.  Dates after ``as_of`` are
    never inspected, which makes the function replay-safe by construction.
    """

    if window < 2:
        raise NetworkError("correlation window must contain at least two sessions")
    dates = [str(row.get("date")) for row in rows]
    if as_of not in dates:
        raise NetworkError(f"session {as_of!r} is not present in the rows")
    end = dates.index(as_of)
    selected_dates: list[str] = []
    selected_returns: list[tuple[float, ...]] = []
    index = end
    while index >= 0 and len(selected_dates) < window:
        values = _row_returns(rows[index])
        if values is not None:
            selected_dates.append(dates[index])
            selected_returns.append(values)
        index -= 1
    selected_dates.reverse()
    selected_returns.reverse()
    missing = [
        dates[position]
        for position in range(max(0, end - window * 2), end + 1)
        if _row_returns(rows[position]) is None
    ]
    available = len(selected_dates) >= window
    payload: dict[str, Any] = {
        "available": available,
        "as_of": as_of,
        "window_sessions": window,
        "sessions": len(selected_dates),
        "start": selected_dates[0] if selected_dates else None,
        "end": selected_dates[-1] if selected_dates else None,
        "dates": selected_dates,
        "missing_sessions": missing,
        "reason": None
        if available
        else (
            f"needs {window} valid windows, selected window has {len(selected_dates)} "
            "complete observations"
        ),
        "series": {
            code: [values[position] for values in selected_returns]
            for position, code in enumerate(INDUSTRY_CODES)
        },
    }
    if not available:
        payload["series"] = {}
    return payload


def pearson_correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Return the Pearson correlation, or ``None`` when it is undefined."""

    if len(left) != len(right):
        raise NetworkError("correlation series must have equal length")
    count = len(left)
    if count < 2:
        return None
    mean_left = sum(left) / count
    mean_right = sum(right) / count
    covariance = sum(
        (left[index] - mean_left) * (right[index] - mean_right) for index in range(count)
    )
    var_left = sum((value - mean_left) ** 2 for value in left)
    var_right = sum((value - mean_right) ** 2 for value in right)
    if var_left <= 0.0 or var_right <= 0.0:
        return None
    value = covariance / math.sqrt(var_left * var_right)
    if not math.isfinite(value):
        return None
    # Numerical guard: keep the value in [-1, 1].
    return max(-1.0, min(1.0, value))


def build_correlation_network(
    rows: Sequence[Mapping[str, Any]],
    as_of: str,
    *,
    window: int = DEFAULT_CORRELATION_WINDOW,
    cutoff: float = DEFAULT_CORRELATION_CUTOFF,
) -> dict[str, Any]:
    """Build the deterministic 12-node correlation-network payload.

    The payload is JSON-serialisable and contains everything the Structure
    screen needs: nodes with fixed positions, positive edges at ``cutoff``,
    the pair count (``n/66``), the underlying pair values for the inspector and
    explicit reasons for unavailable or undefined cases.
    """

    selected = select_correlation_window(rows, as_of, window=window)
    base: dict[str, Any] = {
        "view": "correlation",
        "available": selected["available"],
        "as_of": as_of,
        "cutoff": float(cutoff),
        "cutoff_display": f"r >= {cutoff:.2f}",
        "pairs_total": PAIR_COUNT,
        "pairs_qualifying": 0,
        "window": {
            "sessions": selected["sessions"],
            "required": window,
            "start": selected["start"],
            "end": selected["end"],
            "dates": selected["dates"],
        },
        "nodes": [],
        "edges": [],
        "pairs": [],
        "undefined_pairs": [],
        "missing_sessions": selected["missing_sessions"],
        "reason": selected["reason"],
        "legend": {
            "node": "US industry portfolio",
            "edge": f"Pearson correlation r >= {cutoff:.2f} on the trailing {window} sessions",
        },
        "summary": "Correlation network unavailable",
    }
    if not selected["available"]:
        base["summary"] = str(selected["reason"])
        return base
    if not (-1.0 <= cutoff <= 1.0):
        raise NetworkError("correlation cutoff must be within [-1, 1]")

    nodes = [node.as_dict() for node in industry_nodes()]
    series: Mapping[str, Sequence[float]] = selected["series"]
    pairs: list[dict[str, Any]] = []
    undefined: list[dict[str, str]] = []
    for left_position, left_code in enumerate(INDUSTRY_CODES):
        for right_code in INDUSTRY_CODES[left_position + 1 :]:
            value = pearson_correlation(series[left_code], series[right_code])
            if value is None:
                undefined.append({"source": left_code, "target": right_code})
                continue
            pairs.append(
                {
                    "source": left_code,
                    "target": right_code,
                    "correlation": round(value, 6),
                }
            )
    edges = [dict(pair) for pair in pairs if pair["correlation"] >= cutoff]
    degree: dict[str, int] = {code: 0 for code in INDUSTRY_CODES}
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    for node in nodes:
        node["degree"] = degree[node["code"]]
        node["incident_edges"] = [
            dict(edge) for edge in edges if node["code"] in (edge["source"], edge["target"])
        ]
    base.update(
        {
            "nodes": nodes,
            "edges": edges,
            "pairs": pairs,
            "undefined_pairs": undefined,
            "pairs_qualifying": len(edges),
            "summary": (
                f"{len(edges)} of {PAIR_COUNT} industry pairs move together at "
                f"r >= {cutoff:.2f} on {selected['start']}..{selected['end']}"
            ),
        }
    )
    if undefined:
        base["summary"] += f" ({len(undefined)} pair(s) undefined)"
    return base


def pair_lookup(network: Mapping[str, Any]) -> dict[tuple[str, str], float]:
    """Return a canonical ``(source, target) -> r`` lookup for inspector use."""

    lookup: dict[tuple[str, str], float] = {}
    for pair in network.get("pairs") or ():
        source = str(pair.get("source"))
        target = str(pair.get("target"))
        key = (source, target) if source <= target else (target, source)
        lookup[key] = float(pair["correlation"])
    return lookup


def node_by_code(network: Mapping[str, Any], code: str) -> dict[str, Any] | None:
    """Return the node payload for an industry code, or ``None``."""

    for node in network.get("nodes") or ():
        if node.get("code") == code:
            return dict(node)
    return None


__all__ = [
    "DEFAULT_CORRELATION_CUTOFF",
    "DEFAULT_CORRELATION_WINDOW",
    "INDUSTRY_CODES",
    "INDUSTRY_LABELS",
    "INDUSTRY_SHORT_LABELS",
    "IndustryNode",
    "NetworkError",
    "PAIR_COUNT",
    "build_correlation_network",
    "fixed_node_positions",
    "industry_nodes",
    "node_by_code",
    "pair_lookup",
    "pearson_correlation",
    "return_column",
    "select_correlation_window",
]
