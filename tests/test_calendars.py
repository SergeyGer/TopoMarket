"""Independent observation calendars and source-status tests (DA01)."""

from __future__ import annotations

from pathlib import Path

from topomarket.ui.calendars import (
    INDUSTRY,
    PRICE,
    STATUS_LAGGING,
    VIX,
    build_calendar_status,
    map_observation_date,
    recompute_required,
    refresh_available,
)
from topomarket.ui.panels import DashboardData


def _rows(start: int = 1, count: int = 20, *, vix_missing: set[int] | None = None):
    rows = []
    for offset in range(count):
        day = start + offset
        rows.append(
            {
                "date": f"2024-{1 + (day - 1) // 28:02d}-{1 + (day - 1) % 28:02d}",
                "sp500_close": "100.0",
                "vix_close": "" if vix_missing and offset in vix_missing else "15.0",
                "sp500_log_return": "0.001",
                **{
                    f"ind_{code}_return": "0.001"
                    for code in (
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
                },
            }
        )
    return rows


def _data(tmp_path: Path, *, price_ranges, industry_ranges, profile="demo", demo=True):
    return DashboardData(
        profile=profile,
        data_dir=tmp_path,
        active_data_dir=tmp_path,
        session_dates=tuple(str(row.get("date")) for row in price_ranges),
        rows=tuple(industry_ranges),
        price_rows=tuple(price_ranges),
        industry_rows=tuple(industry_ranges),
        snapshot_id="showcase-synthetic" if demo else "snapshot-1",
        score_points=({"date": str(price_ranges[-1]["date"]), "state": "scored", "score": "50.0"},),
        demo=demo,
    )


def test_price_and_industry_calendars_are_reported_independently(tmp_path: Path) -> None:
    price = _rows(1, 20)
    industry = price[:15]
    data = _data(tmp_path, price_ranges=price, industry_ranges=industry)
    status = build_calendar_status(data)
    assert status["calendars"][PRICE]["observations"] == 20
    assert status["calendars"][INDUSTRY]["observations"] == 15
    assert status["calendars"][INDUSTRY]["status"] == STATUS_LAGGING
    assert status["map_lags_price"] is True
    assert status["price_calendar_is_signal_calendar"] is True
    assert status["calendars"][PRICE]["last"] == data.session_dates[-1]


def test_map_observation_date_labels_the_actual_industry_snapshot(tmp_path: Path) -> None:
    price = _rows(1, 20)
    industry = price[:15]
    data = _data(tmp_path, price_ranges=price, industry_ranges=industry)
    selected = data.session_dates[-1]
    map_info = map_observation_date(data, selected)
    assert map_info["available"] is True
    assert map_info["stale"] is True
    assert map_info["date"] == industry[-1]["date"]
    assert map_info["selected"] == selected
    assert map_info["lag_sessions"] > 0


def test_missing_vix_observations_are_gaps_not_forward_filled(tmp_path: Path) -> None:
    rows = _rows(1, 20, vix_missing={3, 7})
    data = _data(tmp_path, price_ranges=rows, industry_ranges=rows)
    status = build_calendar_status(data)
    assert status["calendars"][VIX]["gaps"] == 2
    assert status["vix_gaps"] == 2
    assert any("VIX" in note for note in status["notes"])


def test_demo_profile_is_read_only_and_private_profile_can_offer_refresh(
    tmp_path: Path,
) -> None:
    rows = _rows(1, 20)
    demo = _data(tmp_path, price_ranges=rows, industry_ranges=rows, profile="demo", demo=True)
    assert refresh_available(demo) is False
    private = _data(
        tmp_path, price_ranges=rows, industry_ranges=rows, profile="private", demo=False
    )
    assert refresh_available(private) is True
    status = build_calendar_status(private)
    assert "private only" in status["refresh_action"]
    assert status["refresh_available"] is True


def test_recompute_required_detects_snapshot_and_score_changes(tmp_path: Path) -> None:
    rows = _rows(1, 20)
    data = _data(tmp_path, price_ranges=rows, industry_ranges=rows, profile="private", demo=False)
    assert recompute_required(data) is False
    assert recompute_required(data, snapshot_id="other-snapshot") is True
    data.score_points = ()
    assert recompute_required(data) is True


def test_calendar_payload_has_accessible_table_and_summary(tmp_path: Path) -> None:
    rows = _rows(1, 20)
    data = _data(tmp_path, price_ranges=rows, industry_ranges=rows)
    status = build_calendar_status(data)
    assert "Independent observation calendars" in str(status["table_alternative"])
    assert "price observations" in str(status["accessible_summary"])
    assert "3 row(s)" in str(status["table_alternative"])
