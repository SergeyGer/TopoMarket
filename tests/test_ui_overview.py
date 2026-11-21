"""Unit tests for the Streamlit-independent overview helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from topomarket.data import write_manifest, write_snapshot
from topomarket.ui import overview


def _write_csv(path: Path, header: str, rows: str) -> None:
    path.write_text(header + "\n" + rows + "\n", encoding="utf-8")


def test_badge_and_data_source_label() -> None:
    assert overview.badge_for_profile(" Demo ") == "demo"
    assert overview.badge_for_profile("PRIVATE") == "private"
    assert (
        overview.data_source_label(SimpleNamespace(data_source="synthetic"))
        == "Data source: synthetic"
    )
    assert overview.data_source_label(object()) == "Data source: unknown"


def test_latest_data_date_prefers_an_explicit_manifest_field(tmp_path: Path) -> None:
    _write_csv(tmp_path / "markets.csv", "date,value", "2023-01-01,1")

    assert (
        overview.latest_data_date(tmp_path, {"latest_date": "2025-03-04"})
        == "2025-03-04"
    )
    assert (
        overview.latest_data_date(tmp_path, {"metadata": {"as_of": "2024-12-31"}})
        == "2024-12-31"
    )


def test_latest_data_date_uses_the_newest_csv_value(tmp_path: Path) -> None:
    _write_csv(tmp_path / "markets.csv", "date,value", "2024-01-02,1\n2024-02-03,2")
    _write_csv(tmp_path / "participants.csv", "as_of,value", "2023-12-31,0")

    assert overview.latest_data_date(tmp_path) == "2024-02-03"


def test_latest_data_date_falls_back_to_manifest_created_at(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        {"created_at": "2022-07-08T09:10:11Z"},
    )

    assert overview.latest_data_date(tmp_path, manifest) == "2022-07-08"


def test_latest_data_date_falls_back_to_snapshot_created_at(tmp_path: Path) -> None:
    write_snapshot(tmp_path, {"created_at": "2021-06-07T00:00:00Z"})

    assert overview.latest_data_date(tmp_path) == "2021-06-07"


def test_latest_data_date_is_none_without_dated_data(tmp_path: Path) -> None:
    _write_csv(tmp_path / "notes.csv", "id,value", "1,not a date")

    assert overview.latest_data_date(tmp_path) is None
    assert overview.latest_data_date(tmp_path / "missing") is None


def test_latest_data_date_ignores_unreadable_csv_files(tmp_path: Path) -> None:
    (tmp_path / "broken.csv").write_bytes(b"\xff\xfe\x00\x00")

    assert overview.latest_data_date(tmp_path) is None


def test_inspect_data_directory_reports_missing_path(tmp_path: Path) -> None:
    status = overview.inspect_data_directory(tmp_path / "missing")

    assert status["exists"] is False
    assert status["data_available"] is False
    assert status["manifest"] is None
    assert status["latest_data_date"] is None


def test_inspect_data_directory_lists_files_and_valid_manifest(tmp_path: Path) -> None:
    (tmp_path / "markets.csv").write_text("id\n1\n", encoding="utf-8")
    write_manifest(tmp_path, {"profile": "demo", "data_source": "synthetic"})

    status = overview.inspect_data_directory(tmp_path)

    assert status["exists"] is True
    assert status["manifest_present"] is True
    assert status["manifest_valid"] is True
    assert status["manifest_error"] is None
    assert status["manifest"]["snapshot_id"]
    assert status["files"] == ["manifest.json", "markets.csv"]
    assert status["data_files"] == ["markets.csv"]
    assert status["snapshot_count"] == 0
    assert status["latest_snapshot"] is None
    assert status["data_available"] is True


def test_inspect_data_directory_reports_invalid_manifest(tmp_path: Path) -> None:
    write_manifest(tmp_path, {"profile": "demo"})
    location = tmp_path / "manifest.json"
    payload = json.loads(location.read_text(encoding="utf-8"))
    payload["profile"] = "tampered"
    location.write_text(json.dumps(payload), encoding="utf-8")

    status = overview.inspect_data_directory(tmp_path)

    assert status["manifest_present"] is True
    assert status["manifest_valid"] is False
    assert "snapshot_id" in str(status["manifest_error"])
    assert status["data_available"] is True


def test_build_overview_rejects_unknown_profiles(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        overview.build_overview("mystery", data_dir=tmp_path)


def test_build_overview_for_private_profile_without_data(tmp_path: Path) -> None:
    result = overview.build_overview("private", data_dir=tmp_path / "empty")

    assert result["profile"] == "private"
    assert result["is_private"] is True
    assert result["profile_badge"] == "private"
    assert result["data_source"] == "private"
    assert result["data_available"] is False
    assert result["empty_state"] == overview.EMPTY_STATE
    assert result["latest_data_date"] is None
    assert result["latest_data_date_label"] == "Latest data date: none"


def test_build_overview_distinguishes_undated_data(tmp_path: Path) -> None:
    _write_csv(tmp_path / "notes.csv", "id,value", "1,2")

    result = overview.build_overview("demo", data_dir=tmp_path)

    assert result["data_available"] is True
    assert result["empty_state"] == overview.NO_DATED_DATA_STATE
    assert result["latest_data_date_label"] == "Latest data date: none"
    assert result["navigation"] == list(overview.NAVIGATION_ITEMS)
    assert result["data_status"]["data_files"] == ["notes.csv"]


def test_plain_text_overview_renders_the_core_fields() -> None:
    text = overview.plain_text_overview(
        {
            "title": "TopoMarket",
            "heading": "Overview",
            "profile_badge": "demo",
            "data_source_label": "Data source: synthetic",
            "data_dir": "/tmp/data",
            "latest_data_date_label": "Latest data date: 2024-01-30",
            "navigation": ["Overview", "Markets"],
        }
    )

    assert text.splitlines() == [
        "TopoMarket",
        "Overview",
        "Profile badge: demo",
        "Data source: synthetic",
        "Data directory: /tmp/data",
        "Latest data date: 2024-01-30",
        "Navigation: Overview, Markets",
    ]


def test_plain_text_overview_includes_empty_state() -> None:
    text = overview.plain_text_overview({"empty_state": overview.EMPTY_STATE})

    assert "No data available yet" in text
    assert "Profile badge: unknown" in text
