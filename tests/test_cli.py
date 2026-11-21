"""Tests for the TopoMarket command-line interface."""

from __future__ import annotations

from topomarket.cli import main


def test_demo_command_exits_successfully(capsys) -> None:
    assert main(["demo"]) == 0
    output = capsys.readouterr().out
    assert "demo" in output.lower()
    assert "synthetic" in output.lower()


def test_demo_json_output(capsys) -> None:
    import json

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
