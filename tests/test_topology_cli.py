"""CLI tests for the Step 4 topology command."""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from topomarket import cli
from topomarket.topology import DEFAULT_CONFIG, DEFAULT_CONFIG_HASH


def _tda_rows(count: int = 700) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current = date(2018, 1, 1)
    index = 0
    while len(rows) < count:
        if current.weekday() < 5:
            value = 0.01 * (((index * 37) % 23) - 11) / 11.0
            rows.append(
                {
                    "date": current.isoformat(),
                    "sp500_close": f"{200 + index / 10:.4f}",
                    "sp500_log_return": "" if not rows else f"{value:.10f}",
                    "vix_close": f"{15 + (index % 7):.4f}",
                }
            )
            index += 1
        current += timedelta(days=1)
    return rows


def _data_dir(tmp_path: Path, count: int = 700) -> Path:
    root = tmp_path / "data"
    normalized = root / "normalized"
    normalized.mkdir(parents=True)
    rows = _tda_rows(count)
    with (normalized / "tda_daily.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return root


def test_topology_command_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = _data_dir(tmp_path)

    assert cli.main(["topology", "--data-dir", str(data_dir)]) == 0

    output = capsys.readouterr().out
    assert "Scored:" in output
    assert DEFAULT_CONFIG_HASH in output
    assert "Exploratory: False" in output
    assert "First scored date:" in output
    assert "Latest:" in output


def test_topology_command_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = _data_dir(tmp_path)

    assert cli.main(["topology", "--data-dir", str(data_dir), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["config_hash"] == DEFAULT_CONFIG_HASH
    assert payload["exploratory"] is False
    assert payload["row_count"] == 700
    assert payload["scored_count"] > 0
    assert len(payload["points"]) == 700
    assert all(
        0.0 <= point["score"] <= 100.0 for point in payload["points"] if point["score"] is not None
    )


def test_topology_command_writes_csv(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = _data_dir(tmp_path)
    output_path = tmp_path / "scores.csv"

    assert cli.main(["topology", "--data-dir", str(data_dir), "--out", str(output_path)]) == 0
    capsys.readouterr()

    assert output_path.is_file()
    assert (tmp_path / "scores.csv.meta.json").is_file()
    with output_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        assert "score" in reader.fieldnames
        assert len(list(reader)) == 700


def test_topology_command_custom_config_is_exploratory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _data_dir(tmp_path)
    config_path = tmp_path / "custom-topology.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "default": {"name": "default", "config": DEFAULT_CONFIG.to_dict()},
            }
        ),
        encoding="utf-8",
    )

    assert cli.main(["topology", "--data-dir", str(data_dir), "--config", str(config_path)]) == 0
    output = capsys.readouterr().out
    assert "Exploratory: True" in output


def test_topology_command_missing_data_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"
    assert cli.main(["topology", "--data-dir", str(missing)]) == 2
    assert "error:" in capsys.readouterr().err.lower()


def test_topology_command_resolves_active_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _data_dir(tmp_path)
    # Simulate a published snapshot pointer: topology must read the snapshot copy.
    snapshot_id = "a" * 64
    snapshot_dir = data_dir / "snapshots" / snapshot_id / "normalized"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "tda_daily.csv").write_text(
        (data_dir / "normalized" / "tda_daily.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )
    state = data_dir / "state"
    state.mkdir()
    (state / "active_snapshot.json").write_text(
        json.dumps({"schema_version": 1, "snapshot_id": snapshot_id}), encoding="utf-8"
    )

    assert cli.main(["topology", "--data-dir", str(data_dir)]) == 0
    output = capsys.readouterr().out
    assert snapshot_id in output
