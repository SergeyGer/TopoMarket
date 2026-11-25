"""Replay-screen payload: one authoritative selected session and blind integrity (RE01).

Blind replay must not leak anything after the cutoff.  This module builds the
Replay payload from a single ``selected`` session: every rendered trace and every
serialized value is sliced by that session first, and the 20-session outcome
layer is only present when the selection explicitly reveals it.

The outcome layer shows the origin close, the 10% boundary, the lowest observed
close, the first qualifying breach and the maximum decline from the origin.  An
incomplete horizon is reported as pending; hiding the outcome removes the same
payload rather than only hiding pixels.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .calendars import map_observation_date

REPLAY = "replay"
LIVE = "live"
OUTCOME_HORIZON = 20
DRAWDOWN_TARGET = 0.10
HISTORY_SESSIONS = 120

PRIMARY_METHOD = "tda"


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _price_rows(data: Any) -> list[dict[str, Any]]:
    rows = getattr(data, "price_rows", None)
    if rows is None:
        rows = getattr(data, "rows", ()) or ()
    return [dict(row) for row in rows if row.get("date")]


def _score_point(data: Any, selected: str) -> dict[str, Any]:
    point = (getattr(data, "score_by_date", {}) or {}).get(selected) or {}
    raw = point.get("score")
    value = _float(raw) if raw not in (None, "") and point.get("state") == "scored" else None
    return {"date": selected, "value": value, "state": str(point.get("state") or "unavailable")}


def _report(data: Any) -> dict[str, Any] | None:
    reports = getattr(data, "evaluation_reports", ()) or ()
    return dict(reports[0]) if reports else None


def _primary_metrics(data: Any) -> dict[str, Any]:
    report = _report(data)
    if report is None:
        return {}
    method = report.get("primary_method") or PRIMARY_METHOD
    metrics = (report.get("metrics") or {}).get(method) or {}
    return dict(metrics) if isinstance(metrics, Mapping) else {}


def _policy_cutoff(data: Any) -> float | None:
    report = _report(data)
    if report is None:
        return None
    method = report.get("primary_method") or PRIMARY_METHOD
    policy = (report.get("policies") or {}).get(method)
    if not isinstance(policy, Mapping):
        return None
    return _float(policy.get("cutoff"))


def _alert_status(data: Any, selected: str) -> dict[str, Any]:
    metrics = _primary_metrics(data)
    alerts = {str(value) for value in metrics.get("alerts") or ()}
    matched_entries = {
        str(entry.get("alert_date")): dict(entry)
        for entry in metrics.get("matched") or ()
        if entry.get("alert_date")
    }
    post_onset = {str(value) for value in metrics.get("post_onset_alerts") or ()}
    false_alerts = {str(value) for value in metrics.get("false_alerts") or ()}
    pending = {str(value) for value in metrics.get("pending_alerts") or ()}
    if selected not in alerts:
        return {"is_alert": False, "status": None, "matched": None}
    if selected in matched_entries:
        return {
            "is_alert": True,
            "status": "matched",
            "matched": matched_entries[selected],
            "label": "Warning matched a breach episode",
        }
    if selected in post_onset:
        return {
            "is_alert": True,
            "status": "late",
            "matched": None,
            "label": "Late alert (after onset)",
        }
    if selected in false_alerts:
        return {"is_alert": True, "status": "false", "matched": None, "label": "Mature false alert"}
    if selected in pending:
        return {"is_alert": True, "status": "pending", "matched": None, "label": "Pending alert"}
    return {"is_alert": True, "status": "alert", "matched": None, "label": "Alert"}


def build_outcome(data: Any, selected: str) -> dict[str, Any] | None:
    """Compute the 20-session outcome layer for a selected session.

    Returns ``None`` when the selected session has no price observation.  The
    horizon uses the S&P 500 price calendar only and nothing after it.
    """

    rows = _price_rows(data)
    dates = [str(row.get("date")) for row in rows]
    if selected not in dates:
        return None
    index = dates.index(selected)
    origin_close = _float(rows[index].get("sp500_close"))
    if origin_close is None:
        return None
    horizon_rows = rows[index + 1 : index + 1 + OUTCOME_HORIZON]
    horizon = [
        {"date": str(row.get("date")), "close": _float(row.get("sp500_close"))}
        for row in horizon_rows
    ]
    boundary = origin_close * (1.0 - DRAWDOWN_TARGET)
    lowest = None
    lowest_date = None
    breach = None
    for entry in horizon:
        close = entry["close"]
        if close is None:
            continue
        if lowest is None or close < lowest:
            lowest = close
            lowest_date = entry["date"]
        if breach is None and close <= boundary:
            breach = {"date": entry["date"], "close": close}
    pending = len(horizon) < OUTCOME_HORIZON
    max_decline = None if lowest is None else (origin_close - lowest) / origin_close
    target = None if pending else (1 if breach is not None else 0)
    return {
        "available": True,
        "origin": {"date": selected, "close": origin_close},
        "boundary": {
            "fraction": DRAWDOWN_TARGET,
            "close": boundary,
            "label": "10% boundary",
        },
        "horizon_sessions": len(horizon),
        "required_sessions": OUTCOME_HORIZON,
        "pending": pending,
        "target": target,
        "lowest": {"date": lowest_date, "close": lowest},
        "first_breach": breach,
        "max_decline": max_decline,
        "max_decline_pct": None if max_decline is None else max_decline * 100.0,
        "dates": [entry["date"] for entry in horizon],
        "closes": [entry["close"] for entry in horizon],
        "outcome_label": _outcome_label(pending, breach),
    }


def _outcome_label(pending: bool, breach: Mapping[str, Any] | None) -> str:
    if pending:
        return "Pending outcome: the 20-session horizon is not complete yet"
    if breach is not None:
        return f"Observed: the index closed at or below the 10% boundary on {breach['date']}"
    return "Observed: the index stayed above the 10% boundary for the full horizon"


def _score_history(data: Any, selected: str, limit: int = 252) -> list[dict[str, Any]]:
    """Scored sessions at or before ``selected`` only (blind-safe)."""

    points = list(getattr(data, "score_points", ()) or ())
    history: list[dict[str, Any]] = []
    for point in points:
        date = str(point.get("date") or "")
        if not date or date > selected:
            continue
        if point.get("state") != "scored":
            continue
        value = _float(point.get("score"))
        if value is None:
            continue
        history.append({"date": date, "score": value})
    return history[-limit:]


def _price_history(data: Any, selected: str, limit: int = HISTORY_SESSIONS) -> dict[str, Any]:
    rows = _price_rows(data)
    entries = [
        {
            "date": str(row.get("date")),
            "close": _float(row.get("sp500_close")),
        }
        for row in rows
        if str(row.get("date")) <= selected
    ][-limit:]
    return {
        "dates": [entry["date"] for entry in entries],
        "closes": [entry["close"] for entry in entries],
        "unit": "index points",
        "label": "S&P 500 close",
    }


def _alert_markers(data: Any, selected: str) -> list[dict[str, Any]]:
    metrics = _primary_metrics(data)
    markers: list[dict[str, Any]] = []
    for alert_date in sorted(str(value) for value in metrics.get("alerts") or ()):
        if alert_date > selected:
            continue
        status = _alert_status(data, alert_date)
        markers.append(
            {
                "date": alert_date,
                "status": status.get("status"),
                "label": status.get("label"),
                "selected": alert_date == selected,
            }
        )
    return markers


def build_replay_payload(data: Any, selection: Any) -> dict[str, Any]:
    """Build the Replay-screen payload for one authoritative session."""

    selected = data.selected_date(selection)
    mode = str(getattr(selection, "mode", LIVE))
    reveal = bool(getattr(selection, "reveal", False))
    blind = mode == REPLAY and not reveal
    score = _score_point(data, selected)
    cutoff = _policy_cutoff(data)
    alert = _alert_status(data, selected)
    report = _report(data) or {}
    evidence = report.get("evidence") or {}
    map_info = map_observation_date(data, selected)
    outcome = None if blind else build_outcome(data, selected)
    score_history = _score_history(data, selected)
    history = _price_history(data, selected)
    revealed_dates = outcome["dates"] if outcome else []
    payload: dict[str, Any] = {
        "screen": "replay",
        "title": "Replay",
        "date": selected,
        "mode": mode,
        "blind": blind,
        "revealed": bool(mode == REPLAY and reveal),
        "reveal_available": build_outcome(data, selected) is not None,
        "outcome": outcome,
        "score": {
            "value": score["value"],
            "state": score["state"],
            "percentile_units": score["value"],
            "comparative": True,
            "cutoff": cutoff,
            "cutoff_status": (
                "unavailable"
                if score["value"] is None
                else (
                    "above"
                    if cutoff is not None and score["value"] >= cutoff
                    else ("below" if cutoff is not None else "no_frozen_policy")
                )
            ),
        },
        "alert": alert,
        "alert_markers": _alert_markers(data, selected),
        "score_history": score_history,
        "price_history": history,
        "outcome_horizon": OUTCOME_HORIZON,
        "drawdown_target": DRAWDOWN_TARGET,
        "evidence": {
            "wording": evidence.get("wording"),
            "historical_evidence": bool(evidence.get("historical_evidence")),
            "limitations": list(evidence.get("limitations") or ()),
        },
        "map_observation": map_info,
        "synthetic": bool(getattr(data, "demo", False)),
        "snapshot_id": getattr(data, "snapshot_id", None),
        "legend": "Replay starts with what was available on the selected date. "
        "Reveal adds only the next 20 S&P 500 sessions: origin close, 10% boundary, "
        "lowest close, first breach and maximum decline.",
        "emitted_dates": {
            "history_start": history["dates"][0] if history["dates"] else None,
            "cutoff": selected,
            "outcome_start": revealed_dates[0] if revealed_dates else None,
            "outcome_end": revealed_dates[-1] if revealed_dates else None,
            "history_sessions": len(history["dates"]),
            "scored_sessions": len(score_history),
        },
        "accessible_summary": _replay_summary(score, alert, outcome, blind, selected),
    }
    return payload


def _replay_summary(
    score: Mapping[str, Any],
    alert: Mapping[str, Any],
    outcome: Mapping[str, Any] | None,
    blind: bool,
    selected: str,
) -> str:
    parts = [f"Replay for session {selected}."]
    parts.append(
        "Score unavailable."
        if score.get("value") is None
        else f"Comparative score percentile {score['value']:.1f}."
    )
    parts.append(f"Alert status: {alert.get('status') or 'no alert on this session'}.")
    if blind:
        parts.append("Blind mode: the outcome horizon is hidden until reveal is requested.")
    elif outcome is None:
        parts.append("No outcome layer is available for this session.")
    else:
        parts.append(str(outcome.get("outcome_label")))
        if outcome.get("pending"):
            parts.append("The outcome is pending because the horizon is incomplete.")
    return " ".join(parts)


__all__ = [
    "DRAWDOWN_TARGET",
    "HISTORY_SESSIONS",
    "LIVE",
    "OUTCOME_HORIZON",
    "REPLAY",
    "build_outcome",
    "build_replay_payload",
]
