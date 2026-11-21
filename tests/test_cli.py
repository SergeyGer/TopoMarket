"""Tests for the TopoMarket command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket.cli import main


def test_help_lists_supported_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])

    assert excinfo.value.code == 0
    output = capsys.readouterr().out.lower()
    for command in ("synthetic", "status", "validate"):
        assert command in output


def test_demo_command_exits_successfully(capsys) -> None:
    assert main(["demo"]) == 0
    output = capsys.readouterr().out
    assert "demo" in output.lower()
    assert "synthetic" in output.lower()


def test_demo_json_output(capsys) -> None:
    assert main(["demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "demo"
    assert payload["market_count"] >= 1


def test_info_command(capsys) -> None:
    assert main(["info", "--profile", "demo"]) == 0
    assert "TopoMarket Demo" in capsys.readouterr().out


def test_validate_commands(capsys) -> None:
    assert main(["validate", "--profile", "demo"]) == 0
    assert "valid" in capsys.readouterr().out.lower()
    assert main(["validate", "--profile", "private"]) == 0
    assert "not included" in capsys.readouterr().out.lower()


def test_status_reports_clean_empty_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"

    assert main(["status", "--data-dir", str(missing)]) == 0

    output = capsys.readouterr().out.lower()
    assert "data source" in output
    assert "no data available" in output


def test_status_and_validate_synthetic_data_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "synthetic"
    assert main(["synthetic", "--out", str(data_dir)]) == 0
    capsys.readouterr()

    assert main(["status", "--data-dir", str(data_dir)]) == 0
    status = capsys.readouterr().out
    assert "manifest: valid" in status.lower()
    assert "latest data date: 2024-01-30" in status.lower()

    assert main(["validate", "--data-dir", str(data_dir)]) == 0
    assert "is valid" in capsys.readouterr().out.lower()


def test_status_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "synthetic"
    assert main(["synthetic", "--out", str(data_dir), "--seed", "7"]) == 0
    capsys.readouterr()

    assert main(["status", "--data-dir", str(data_dir), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "demo"
    assert payload["data_source"] == "synthetic"
    assert payload["manifest_valid"] is True
    assert payload["latest_data_date"] == "2024-01-30"


def test_validate_rejects_a_tampered_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "synthetic"
    assert main(["synthetic", "--out", str(data_dir)]) == 0
    manifest_path = data_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["data_source"] = "tampered"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    capsys.readouterr()

    assert main(["validate", "--data-dir", str(data_dir)]) == 2

    assert "invalid manifest" in capsys.readouterr().err.lower()
