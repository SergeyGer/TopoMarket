"""Causally available alert state for blind Replay and the Structure timeline (F02).

Blind mode must never expose retrospective information: the frozen evaluation
report stores which alerts matched an episode, when the episode started, and
whether an alert was late/false.  Those fields are functions of the full sample
and cannot be shown before the outcome is knowingly revealed.

This module derives the alert state **as of** the selected session from the
score readings, the frozen policy cutoff/cooldown and price history up to that
session only.  Blind payloads therefore expose just `Alert recorded` /
`No alert recorded`; the retrospective classification is computed from the
revealed scope (selected session + 20 closes) and flagged as retrospective.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .labels import build_breach_episodes, build_target_labels

COOLDOWN_SESSIONS = 20
HORIZON_SESSIONS = 20
DRAWDOWN_TARGET = 0.10
PRIMARY_METHOD = "tda"
ALERT_SYMBOL = "^"

#: Alert statuses that only exist in the retrospective review flow.
REVIEW_STATUSES = ("matched", "late", "false", "pending")


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def primary_report(data: Any) -> dict[str, Any] | None:
    reports = getattr(data, "evaluation_reports", ()) or ()
    if not reports:
        return None
    first = reports[0]
    return dict(first) if isinstance(first, Mapping) else None


def frozen_policy(data: Any) -> dict[str, Any]:
    """Return the frozen policy for the primary method (configuration, not outcome)."""

    report = primary_report(data)
    if report is None:
        return {}
    method = report.get("primary_method") or PRIMARY_METHOD
    policies = report.get("policies") or {}
    policy = policies.get(method)
    return dict(policy) if isinstance(policy, Mapping) else {}


def session_dates(data: Any) -> list[str]:
    price_rows = getattr(data, "price_rows", None)
    if price_rows is None:
        price_rows = getattr(data, "rows", ()) or ()
    return [str(row.get("date")) for row in price_rows if row.get("date")]


def _scored_points(data: Any) -> list[tuple[str, float]]:
    points: list[tuple[str, float]] = []
    for point in getattr(data, "score_points", ()) or ():
        date = str(point.get("date") or "")
        if not date or point.get("state") != "scored":
            continue
        value = _float(point.get("score"))
        if value is None:
            continue
        points.append((date, value))
    points.sort(key=lambda item: item[0])
    return points


def causal_alert_dates(data: Any, selected: str | None = None) -> list[str]:
    """Alert dates derived from readings at or before ``selected`` only."""

    policy = frozen_policy(data)
    if policy.get("silent"):
        return []
    cutoff = _float(policy.get("cutoff"))
    if cutoff is None:
        return []
    cooldown = int(policy.get("cooldown_sessions") or COOLDOWN_SESSIONS)
    positions = {date: index for index, date in enumerate(session_dates(data))}
    alerts: list[str] = []
    last_position: int | None = None
    for date, value in _scored_points(data):
        if selected is not None and date > selected:
            break
        position = positions.get(date)
        if position is None or value < cutoff:
            continue
        if last_position is not None and position - last_position < cooldown:
            continue
        alerts.append(date)
        last_position = position
    return alerts


def _price_rows(data: Any) -> list[dict[str, Any]]:
    rows = getattr(data, "price_rows", None)
    if rows is None:
        rows = getattr(data, "rows", ()) or ()
    return [dict(row) for row in rows if row.get("date")]


def _classification_scope(data: Any, alert_date: str) -> tuple[list[dict[str, Any]], str | None]:
    """Rows and last session that are observable when the alert's horizon ends."""

    rows = _price_rows(data)
    dates = [str(row.get("date")) for row in rows]
    if alert_date not in dates:
        return rows, None
    index = dates.index(alert_date)
    horizon_end = dates[min(len(dates) - 1, index + HORIZON_SESSIONS)]
    return [row for row in rows if str(row.get("date")) <= horizon_end], horizon_end


def classify_alert(data: Any, alert_date: str) -> dict[str, Any]:
    """Retrospective classification from the alert's own revealed/observed horizon."""

    rows, horizon_end = _classification_scope(data, alert_date)
    dates = [str(row.get("date")) for row in rows]
    if alert_date not in dates:
        return {
            "is_alert": True,
            "status": "pending",
            "label": "Alert recorded; its horizon is not observed in the revealed scope",
            "retrospective": True,
        }
    labels = build_target_labels(rows)
    episodes = build_breach_episodes(labels)
    index = dates.index(alert_date)
    label = labels[index]
    if getattr(label, "pending", False):
        return {
            "is_alert": True,
            "status": "pending",
            "label": "Alert recorded; its 20-session horizon is not complete in the revealed scope",
            "retrospective": True,
        }
    covering = next(
        (episode for episode in episodes if episode.start_index <= index <= episode.end_index),
        None,
    )
    if covering is not None:
        return {
            "is_alert": True,
            "status": "late",
            "label": "Late alert (the breach episode had already started)",
            "episode_onset": covering.start_date,
            "retrospective": True,
        }
    if getattr(label, "positive", False) and getattr(label, "first_breach_index", None) is not None:
        breach_index = int(label.first_breach_index)
        owner = next(
            (
                episode
                for episode in episodes
                if episode.start_index <= breach_index <= episode.end_index
            ),
            None,
        )
        if owner is not None:
            onset = owner.start_index
            lead = onset - index
            if onset <= index:  # pragma: no cover - covered by ``covering`` above
                return {
                    "is_alert": True,
                    "status": "late",
                    "label": "Late alert (the breach episode had already started)",
                    "retrospective": True,
                }
            if lead <= HORIZON_SESSIONS:
                return {
                    "is_alert": True,
                    "status": "matched",
                    "label": "Warning matched a breach episode",
                    "matched": {
                        "alert_date": alert_date,
                        "episode_onset": owner.start_date,
                        "lead_sessions": lead,
                    },
                    "retrospective": True,
                }
    return {
        "is_alert": True,
        "status": "false",
        "label": "No 10% decline within its own 20-session horizon",
        "retrospective": True,
    }


def alert_state(data: Any, selected: str, *, blinded: bool) -> dict[str, Any]:
    """Alert object for one session: neutral in blind mode, retrospective otherwise."""

    alerts = causal_alert_dates(data, selected=selected)
    is_alert = selected in alerts
    if blinded or not is_alert:
        return {
            "is_alert": is_alert,
            "status": "recorded" if is_alert else None,
            "label": "Alert recorded" if is_alert else "No alert recorded",
            "retrospective": False,
        }
    return classify_alert(data, selected)


def alert_markers(data: Any, selected: str, *, blinded: bool) -> list[dict[str, Any]]:
    """Markers for alerts causally available at ``selected``.

    Blind markers are neutral (`Alert recorded`, same symbol for every alert);
    review markers carry the classification derived from the revealed scope.
    """

    markers: list[dict[str, Any]] = []
    for alert_date in causal_alert_dates(data, selected=selected):
        if alert_date > selected:
            continue
        if blinded:
            style = {
                "status": "recorded",
                "label": "Alert recorded",
                "symbol": ALERT_SYMBOL,
                "retrospective": False,
            }
        else:
            state = classify_alert(data, alert_date)
            style = {
                "status": state.get("status"),
                "label": state.get("label"),
                "symbol": _review_symbol(str(state.get("status"))),
                "retrospective": True,
            }
        markers.append({"date": alert_date, "selected": alert_date == selected, **style})
    return markers


def _review_symbol(status: str) -> str:
    return {"matched": "*", "late": "v", "false": "x", "pending": "o"}.get(status, ALERT_SYMBOL)


__all__ = [
    "COOLDOWN_SESSIONS",
    "HORIZON_SESSIONS",
    "alert_markers",
    "alert_state",
    "causal_alert_dates",
    "classify_alert",
    "frozen_policy",
    "primary_report",
    "session_dates",
]
