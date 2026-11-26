"""Independent signal calendars for analysis (audit v1.2 R1).

Price-based signals (S&P log returns, TDA, realised volatility, origin labels and
20-index-session horizons) must use the ordered **index** calendar.  Industry
windows use their own table.  Method readings are joined by date only for the
comparison cohort.  Old synthetic snapshots that only contain ``tda_daily`` keep
working through an explicit joint-table fallback with an as-of reason.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .normalized import NORMALIZED_DIRNAME
from .schemas import INDUSTRIES_DAILY_COLUMNS, TDA_DAILY_COLUMNS

PRICE_TABLE = "sp500_daily"
INDUSTRY_TABLE = "industries_daily"
VIX_TABLE = "vix_daily"


def _read_table(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _tda_rows(target: Path) -> list[dict[str, str]]:
    return _read_table(target / NORMALIZED_DIRNAME / "tda_daily.csv")


def _dates(rows: list[Mapping[str, Any]]) -> list[str]:
    return sorted(str(row.get("date")) for row in rows if row.get("date"))


def _calendar_entry(rows: list[Mapping[str, Any]], source: str) -> dict[str, Any]:
    dates = _dates(rows)
    return {
        "source": source,
        "rows": len(rows),
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
        "available": bool(rows),
    }


def _vix_from_snapshot(target: Path) -> list[dict[str, str]]:
    """Read a VIX source file saved at the snapshot root as a fallback."""

    for name in ("cboe_vix.csv", "vix.csv", "cboe.csv"):
        path = target / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        rows = list(csv.DictReader(text.splitlines()))
        normalized: dict[str, dict[str, str]] = {}
        for row in rows:
            raw_date = row.get("date") or row.get("observation_date") or row.get("obs_date")
            raw_value = (
                row.get("close") or row.get("vix_close") or row.get("value") or row.get("vix")
            )
            if not raw_date or raw_value in (None, ""):
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            normalized[str(raw_date)[:10]] = {
                "date": str(raw_date)[:10],
                "vix_close": f"{value:.6f}",
            }
        return [normalized[date] for date in sorted(normalized)]
    return []


def load_signal_calendars(data_dir: Path | str) -> dict[str, Any]:
    """Load price, industry and VIX calendars plus as-of metadata.

    Resolution per calendar: normalised split table, then the saved VIX source
    file, then the joint ``tda_daily`` fallback (old synthetic snapshots).
    """

    target = Path(data_dir).expanduser()
    joint = _tda_rows(target)
    price_split = _read_table(target / NORMALIZED_DIRNAME / f"{PRICE_TABLE}.csv")
    industry_split = _read_table(target / NORMALIZED_DIRNAME / f"{INDUSTRY_TABLE}.csv")
    vix_split = _read_table(target / NORMALIZED_DIRNAME / f"{VIX_TABLE}.csv")
    vix_saved = [] if vix_split else _vix_from_snapshot(target)

    joint_fallback = not price_split and not industry_split
    if price_split:
        price_rows = price_split
        price_source = "index"
    else:
        price_rows = [
            {column: row.get(column, "") for column in TDA_DAILY_COLUMNS if column != "vix_close"}
            for row in joint
        ]
        price_source = "joint_tda_fallback"
    if industry_split:
        industry_rows = industry_split
        industry_source = "industry"
    else:
        industry_rows = [
            {column: row.get(column, "") for column in TDA_DAILY_COLUMNS if column != "vix_close"}
            for row in joint
        ]
        industry_source = "joint_tda_fallback"
    if vix_split:
        vix_rows = vix_split
        vix_source = "vix"
    elif vix_saved:
        vix_rows = vix_saved
        vix_source = "snapshot_source"
    else:
        vix_rows = [
            {"date": str(row.get("date")), "vix_close": row.get("vix_close", "")}
            for row in joint
            if row.get("vix_close") not in (None, "")
        ]
        vix_source = "joint_tda_fallback"

    as_of = {
        "price": (_calendar_entry(price_rows, price_source)["last"]),
        "industry": (_calendar_entry(industry_rows, industry_source)["last"]),
        "vix": (_calendar_entry(vix_rows, vix_source)["last"]),
    }
    return {
        "price_rows": price_rows,
        "industry_rows": industry_rows,
        "vix_rows": vix_rows,
        "price_source": price_source,
        "industry_source": industry_source,
        "vix_source": vix_source,
        "joint_fallback": joint_fallback,
        "as_of": as_of,
        "calendars": {
            "price": _calendar_entry(price_rows, price_source),
            "industry": _calendar_entry(industry_rows, industry_source),
            "vix": _calendar_entry(vix_rows, vix_source),
        },
        "reasons": {
            "price": (
                "index calendar"
                if price_source == "index"
                else "no split index table; joint tda_daily fallback for an old synthetic snapshot"
            ),
            "industry": (
                "industry calendar"
                if industry_source == "industry"
                else (
                    "no split industry table; joint tda_daily fallback for an "
                    "old synthetic snapshot"
                )
            ),
            "vix": (
                "VIX calendar"
                if vix_source == "vix"
                else (
                    "VIX source file saved with the snapshot"
                    if vix_source == "snapshot_source"
                    else "no separate VIX calendar; joint tda_daily fallback"
                )
            ),
        },
    }


def load_price_signal_rows(data_dir: Path | str) -> list[dict[str, str]]:
    """Rows for S&P returns, TDA scores, labels and 20-session horizons (R1)."""

    calendar = load_signal_calendars(data_dir)
    rows: list[dict[str, str]] = []
    for row in calendar["price_rows"]:
        rows.append(
            {
                "date": str(row.get("date") or ""),
                "sp500_close": str(row.get("sp500_close") or ""),
                "sp500_log_return": str(row.get("sp500_log_return") or ""),
                "price_source": str(row.get("price_source") or ""),
            }
        )
    return [row for row in rows if row["date"]]


def load_industry_signal_rows(data_dir: Path | str) -> list[dict[str, str]]:
    """Rows for industry windows/Mapper from the industry calendar (R1)."""

    calendar = load_signal_calendars(data_dir)
    columns = [column for column in INDUSTRIES_DAILY_COLUMNS]
    return [
        {column: str(row.get(column) or "") for column in columns}
        for row in calendar["industry_rows"]
        if row.get("date")
    ]


def load_evaluation_rows(data_dir: Path | str) -> list[dict[str, str]]:
    """Price-calendar rows joined with VIX readings by date (R1).

    The index calendar determines row order, data end, labels and horizons; VIX
    is joined by date for the comparison cohort only, so a later VIX date cannot
    extend or truncate the price-based series.
    """

    calendar = load_signal_calendars(data_dir)
    vix_by_date = {
        str(row.get("date")): row.get("vix_close")
        for row in calendar["vix_rows"]
        if row.get("date") and row.get("vix_close") not in (None, "")
    }
    rows: list[dict[str, str]] = []
    for row in calendar["price_rows"]:
        date = str(row.get("date") or "")
        if not date:
            continue
        rows.append(
            {
                "date": date,
                "sp500_close": str(row.get("sp500_close") or ""),
                "sp500_log_return": str(row.get("sp500_log_return") or ""),
                "vix_close": str(vix_by_date.get(date, "")),
            }
        )
    return rows


__all__ = [
    "INDUSTRY_TABLE",
    "PRICE_TABLE",
    "VIX_TABLE",
    "load_evaluation_rows",
    "load_industry_signal_rows",
    "load_price_signal_rows",
    "load_signal_calendars",
]
