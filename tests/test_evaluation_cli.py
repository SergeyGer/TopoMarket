"""CLI tests for the Step 6 evaluation command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.test_evaluation import FakeScoreSeries, build_evaluation_rows

from topomarket import cli


def _write_data_dir(tmp_path: Path) -> Path:
    rows = build_evaluation_rows()
    root = tmp_path / "data"
    normalized = root / "normalized"
    normalized.mkdir(parents=True)
    header = list(rows[0])
    lines = [",".join(header)]
    lines.extend(",".join(str(row[column]) for column in header) for row in rows)
    (normalized / "tda_daily.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    state = root / "state"
    state.mkdir()
    (state / "active_snapshot.json").write_text(
        json.dumps({"schema_version": 1, "snapshot_id": "snap-cli"}), encoding="utf-8"
    )
    snapshot = root / "snapshots" / "snap-cli" / "normalized"
    snapshot.mkdir(parents=True)
    (snapshot / "tda_daily.csv").write_text(
        (normalized / "tda_daily.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


def test_evaluate_cli_json_report_and_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _write_data_dir(tmp_path)

    def fake_scores(rows_arg, config=None):  # noqa: ANN001
        return FakeScoreSeries(list(rows_arg))

    monkeypatch.setattr("topomarket.topology.compute_topology_scores", fake_scores)
    ledger = tmp_path / "ledger.jsonl"
    assert (
        cli.main(
            [
                "evaluate",
                "--data-dir",
                str(data_dir),
                "--json",
                "--seed",
                "5",
                "--ledger",
                str(ledger),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["snapshot_id"] == "snap-cli"
    assert payload["primary_method"] == "tda"
    assert payload["methods"]
    assert payload["evidence"]["wording"]
    assert ledger.is_file()


def test_evaluate_cli_report_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _write_data_dir(tmp_path)

    def fake_scores(rows_arg, config=None):  # noqa: ANN001
        return FakeScoreSeries(list(rows_arg))

    monkeypatch.setattr("topomarket.topology.compute_topology_scores", fake_scores)
    report_path = tmp_path / "report.json"
    assert (
        cli.main(
            [
                "evaluate",
                "--data-dir",
                str(data_dir),
                "--report-out",
                str(report_path),
                "--seed",
                "3",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Wording:" in output
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["row_count"] > 0


def test_evaluate_cli_missing_data_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"
    assert cli.main(["evaluate", "--data-dir", str(missing)]) == 2
    assert "error:" in capsys.readouterr().err.lower()
