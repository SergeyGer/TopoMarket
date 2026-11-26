"""Independent observation calendars and source-status payloads (DA01).

The upgraded application keeps three calendars apart instead of assuming one
joined table:

* the **S&P 500 price calendar** (signal windows, labels and the replay horizon);
* the **VIX observation calendar** (its own missing sessions stay gaps);
* the **industry-return calendar** (the map/Mapper window, which can lag the
  price calendar because the industry archive is published with a delay).

This module turns those calendars and the refresh/source metadata into a
JSON-serialisable payload for the Data screen and for the "map is stale" marker
on the Structure screen.  It never fills a missing VIX close with a future
value; missing sessions are reported as gaps.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from topomarket.data.manifest import path_text

from .accessibility import alternative_text, table_alternative

PRICE = "price"
VIX = "vix"
INDUSTRY = "industry"
CALENDAR_IDS = (PRICE, VIX, INDUSTRY)

CALENDAR_LABELS = {
    PRICE: "S&P 500 price calendar",
    VIX: "VIX observation calendar",
    INDUSTRY: "Industry-return calendar",
}

#: Coarse status vocabulary used by the Data screen and the stale-map marker.
STATUS_OK = "ok"
STATUS_GAP = "gaps"
STATUS_LAGGING = "lagging"
STATUS_EMPTY = "empty"


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _calendar(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_column: str | None,
    value_columns: Sequence[str] = (),
) -> dict[str, Any]:
    """Summarise one observation calendar from ordered rows."""

    observed: list[str] = []
    gaps = 0
    for row in rows:
        date = _date(row.get("date"))
        if date is None:
            continue
        if value_column is not None:
            present = _float_or_none(row.get(value_column)) is not None
        else:
            present = all(_float_or_none(row.get(column)) is not None for column in value_columns)
        if present:
            observed.append(date)
        else:
            gaps += 1
    return {
        "observations": len(observed),
        "first": observed[0] if observed else None,
        "last": observed[-1] if observed else None,
        "gaps": gaps,
        "status": STATUS_OK
        if observed and gaps == 0
        else (STATUS_GAP if observed else STATUS_EMPTY),
    }


def _combined_calendar(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [str(row.get("date")) for row in rows if row.get("date")]
    return {
        "observations": len(observed),
        "first": observed[0] if observed else None,
        "last": observed[-1] if observed else None,
        "status": STATUS_OK if observed else STATUS_EMPTY,
    }


def _refresh_summary(data: Any) -> dict[str, Any]:
    status = data.refresh_status or {}
    sources_status = status.get("sources") or {}
    return {
        "updated_at_utc": status.get("updated_at_utc"),
        "published": status.get("published"),
        "error": status.get("error"),
        "warnings": list(status.get("warnings") or ()),
        "source_attempts": {
            str(source_id): {
                "last_attempt_at": value.get("last_attempt_at"),
                "last_success_at": value.get("last_success_at"),
                "outcome": value.get("outcome"),
                "error": value.get("error"),
            }
            for source_id, value in sources_status.items()
            if isinstance(value, Mapping)
        },
    }


def _score_coverage(data: Any) -> dict[str, Any]:
    points = list(getattr(data, "score_points", ()) or ())
    scored = [str(point.get("date")) for point in points if point.get("state") == "scored"]
    return {
        "rows": len(points),
        "scored": len(scored),
        "first_scored": scored[0] if scored else None,
        "last_scored": scored[-1] if scored else None,
    }


def recompute_required(data: Any, snapshot_id: str | None = None) -> bool:
    """Return whether cached scores must be invalidated for the supplied snapshot.

    The dashboard recomputes/invalidate dependent score payloads whenever the
    active snapshot or the frozen topology configuration changes.  The check is
    conservative: a new snapshot id or a score file that does not match the
    snapshot manifest forces a rebuild of the cached panels.
    """

    current = getattr(data, "snapshot_id", None)
    expected = snapshot_id if snapshot_id is not None else current
    if current != expected:
        return True
    points = list(getattr(data, "score_points", ()) or ())
    return not points


def refresh_available(data: Any) -> bool:
    """Return whether the private-only validated refresh action can be offered.

    Public/demo profiles are always read-only.  A private profile is writable
    only when its configured data directory exists and is writable by the
    current process; the action still goes through the validated refresh
    pipeline, which keeps the last good snapshot active on failure.
    """

    if getattr(data, "demo", False):
        return False
    if getattr(data, "profile", "") != "private":
        return False
    root = Path(getattr(data, "data_dir", ""))
    try:
        return root.is_dir() and os.access(root, os.W_OK)
    except OSError:  # pragma: no cover - defensive for unusual filesystems
        return False


def build_calendar_status(data: Any) -> dict[str, Any]:
    """Build the independent-calendar and source-status payload."""

    price_rows: Sequence[Mapping[str, Any]] = getattr(data, "price_rows", ()) or data.rows
    industry_rows: Sequence[Mapping[str, Any]] = getattr(data, "industry_rows", ()) or data.rows
    joined_rows: Sequence[Mapping[str, Any]] = data.rows
    industry_columns = tuple(
        column
        for column in (industry_rows[0] if industry_rows else ())
        if column.startswith("ind_")
    )
    calendars = {
        PRICE: _calendar(price_rows, value_column="sp500_close"),
        VIX: _calendar(joined_rows, value_column="vix_close"),
        INDUSTRY: _calendar(industry_rows, value_column=None, value_columns=industry_columns),
    }
    price_last = calendars[PRICE]["last"]
    industry_last = calendars[INDUSTRY]["last"]
    map_lags_price = bool(price_last and industry_last and industry_last < price_last)
    vix_gaps = calendars[VIX]["gaps"]
    if map_lags_price:
        calendars[INDUSTRY]["status"] = STATUS_LAGGING
    combined = _combined_calendar(joined_rows)
    sources = []
    for source in getattr(data, "sources", ()) or ():
        entry = dict(source)
        attempt = (_refresh_summary(data)["source_attempts"]).get(str(entry.get("source_id")), {})
        entry.update(attempt)
        sources.append(entry)
    revisions = [dict(value) for value in (getattr(data, "revisions", ()) or ())]
    score_coverage = _score_coverage(data)
    payload: dict[str, Any] = {
        "screen": "data",
        "title": "Data",
        "profile": getattr(data, "profile", None),
        "snapshot_id": getattr(data, "snapshot_id", None),
        "data_dir": path_text(getattr(data, "data_dir", "")),
        "synthetic": bool(getattr(data, "demo", False)),
        "calendars": calendars,
        "combined": combined,
        "map_lags_price": map_lags_price,
        "vix_gaps": vix_gaps,
        "price_calendar_is_signal_calendar": True,
        "scores": score_coverage,
        "sources": sources,
        "failures": [
            source
            for source in sources
            if source.get("outcome") in {"failed", "optional_failed", "error"}
        ],
        "revisions": revisions[:100],
        "revision_count": len(revisions),
        "refresh": _refresh_summary(data),
        "refresh_available": refresh_available(data),
        "refresh_action": "Run validated refresh (private only)"
        if refresh_available(data)
        else "Read-only public demo: provider refresh is disabled",
        "recompute_required": recompute_required(data),
        "notes": _notes(calendars, map_lags_price, vix_gaps),
        "table_alternative": table_alternative(
            "Independent observation calendars",
            columns=[
                "calendar",
                "observations",
                "first",
                "last",
                "gaps",
                "status",
            ],
            rows=[
                (
                    CALENDAR_LABELS[calendar_id],
                    calendars[calendar_id]["observations"],
                    calendars[calendar_id]["first"],
                    calendars[calendar_id]["last"],
                    calendars[calendar_id]["gaps"],
                    calendars[calendar_id]["status"],
                )
                for calendar_id in CALENDAR_IDS
            ],
        ),
        "accessible_summary": alternative_text(
            "Data source status",
            description=(
                f"{calendars[PRICE]['observations']} price observations, "
                f"{calendars[VIX]['observations']} VIX observations, "
                f"{calendars[INDUSTRY]['observations']} industry observations; "
                f"map lags price: {map_lags_price}; VIX gaps: {vix_gaps}"
            ),
        ),
    }
    return payload


def _notes(
    calendars: Mapping[str, Mapping[str, Any]], map_lags_price: bool, vix_gaps: int
) -> list[str]:
    notes: list[str] = [
        "The S&P 500 price calendar drives signal windows, labels and the replay horizon.",
        "VIX missing sessions stay gaps and are never forward-filled.",
    ]
    if map_lags_price:
        notes.append(
            "The industry-return calendar lags the price calendar; the map is marked with the "
            "date actually shown."
        )
    if vix_gaps:
        notes.append(f"{vix_gaps} session(s) have no VIX observation.")
    if not calendars[PRICE]["observations"]:
        notes.append("No price observations are available for this profile.")
    return notes


def map_observation_date(data: Any, selected: str) -> dict[str, Any]:
    """Return the industry snapshot date and staleness marker for a selection.

    The map always shows the last complete industry window at or before the
    selected session.  If the industry calendar ends before the price calendar,
    the actual date shown is returned so the UI can label it.
    """

    industry_rows: Sequence[Mapping[str, Any]] = getattr(data, "industry_rows", ()) or data.rows
    dates = [str(row.get("date")) for row in industry_rows if row.get("date")]
    if not dates:
        return {"available": False, "reason": "no industry observations", "date": None}
    candidates = [date for date in dates if date <= selected]
    if not candidates:
        return {
            "available": False,
            "reason": f"no industry observation at or before {selected}",
            "date": None,
        }
    map_date = candidates[-1]
    return {
        "available": True,
        "date": map_date,
        "selected": selected,
        "lag_sessions": _session_lag(
            getattr(data, "price_rows", ()) or data.rows, selected, map_date
        ),
        "stale": map_date < selected,
        "reason": None,
    }


def _session_lag(rows: Sequence[Mapping[str, Any]], selected: str, map_date: str) -> int:
    dates = [
        str(row.get("date")) for row in rows if row.get("date") and str(row.get("date")) <= selected
    ]
    try:
        return dates.index(selected) - dates.index(map_date)
    except ValueError:
        return 0


__all__ = [
    "CALENDAR_IDS",
    "CALENDAR_LABELS",
    "INDUSTRY",
    "PRICE",
    "STATUS_EMPTY",
    "STATUS_GAP",
    "STATUS_LAGGING",
    "STATUS_OK",
    "VIX",
    "build_calendar_status",
    "map_observation_date",
    "recompute_required",
    "refresh_available",
]
