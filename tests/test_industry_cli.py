"""Offline integration tests for the Step 5 ``topomarket industries`` command."""

from __future__ import annotations

import csv
import importlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

import topomarket.analysis as analysis
from topomarket import cli
from topomarket.analysis.mapper import mapper_intervals
from topomarket.data.schemas import INDUSTRY_NAMES, TDA_DAILY_COLUMNS

industries_module = importlib.import_module("topomarket.analysis.industries")
mapper_module = importlib.import_module("topomarket.analysis.mapper")


def _rows(count: int = 80) -> list[dict[str, object]]:
    """Return deterministic, individually varying industry observations."""

    start = date(2023, 1, 2)
    rows: list[dict[str, object]] = []
    for index in range(count):
        row: dict[str, object] = {
            "date": (start + timedelta(days=index)).isoformat(),
            "sp500_close": f"{3000.0 + index:.4f}",
            "sp500_log_return": f"{0.001 * math.sin(index / 4.0):.10f}",
            "vix_close": f"{15.0 + (index % 9):.4f}",
        }
        for column_index, column in enumerate(analysis.INDUSTRY_COLUMNS):
            row[column] = (
                0.01 * math.sin(index / 5.0 + column_index)
                + 0.003 * math.cos(index / 7.0 + 2.0 * column_index)
                + 0.0001 * column_index
            )
        rows.append(row)
    return rows


def _write_tda(root: Path, rows: list[dict[str, object]]) -> Path:
    normalized = root / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    path = normalized / "tda_daily.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TDA_DAILY_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in TDA_DAILY_COLUMNS})
    return root


def _data_dir(tmp_path: Path, rows: list[dict[str, object]] | None = None) -> Path:
    return _write_tda(tmp_path / "data", _rows() if rows is None else rows)


def _json_payload(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> tuple[int, dict[str, object]]:
    code = cli.main(argv)
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out else {}
    return code, payload


def test_public_exports_include_both_step_five_analyses() -> None:
    expected = {
        "INDUSTRY_COLUMNS",
        "INDUSTRY_LABELS",
        "WINDOW_SESSIONS",
        "IndustryCloud",
        "IndustryWindow",
        "build_industry_cloud",
        "select_industry_window",
        "MapperGraph",
        "MapperError",
        "compute_mapper_graph",
        "mapper_payload",
        "mapper_intervals",
        "pearson_correlations",
        "annualized_volatility",
        "industry_explorer_payload",
    }
    assert expected <= set(analysis.__all__)
    # Step 5 exports must remain available; later steps add their own public API.
    assert set(industries_module.__all__) | set(mapper_module.__all__) <= set(analysis.__all__)

    for name in expected:
        assert hasattr(analysis, name), name
    assert callable(analysis.industry_explorer_payload)
    assert analysis.industry_payload is analysis.industry_explorer_payload

    # The whole-volatility lens edge case collapses to a single inclusive
    # interval rather than three zero-width copies.
    equal_lens = mapper_intervals([2.0, 2.0])
    assert len(equal_lens) == 1
    assert equal_lens[0].bounds == (2.0, 2.0)


def test_combined_payload_keys_and_shapes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _data_dir(tmp_path)
    code, payload = _json_payload(capsys, ["industries", "--data-dir", str(data_dir), "--json"])

    assert code == 0
    assert payload["command"] == "industries"
    assert payload["window_sessions"] == analysis.WINDOW_SESSIONS == 60
    assert payload["as_of"] == payload["as_of_date"] == payload["dates"][-1]
    assert len(payload["dates"]) == 60
    assert len(payload["industry_columns"]) == 12
    assert len(payload["industry_labels"]) == 12
    assert payload["industry_columns"] == list(analysis.INDUSTRY_COLUMNS)
    assert payload["industry_labels"] == list(INDUSTRY_NAMES)
    assert payload["start_date"] == payload["dates"][0]
    assert payload["end_date"] == payload["dates"][-1]
    assert payload["row_count"] == 60
    assert payload["active_snapshot_id"] is None
    assert payload["snapshot_id"] is None
    assert payload["data_dir"] == str(data_dir)

    cloud = payload["cloud"]
    assert len(cloud["dates"]) == 60
    assert len(cloud["cloud"]) == 60
    assert all(len(row) == 12 for row in cloud["cloud"])
    assert len(cloud["pca"]) == 60
    assert all(len(row) == 2 for row in cloud["pca"])
    assert cloud["pca_labels"] == ["PC1", "PC2"]
    assert len(cloud["explained_variance"]) == 2
    assert cloud["as_of"] == payload["as_of"]

    mapper = payload["mapper"]
    assert len(mapper["dates"]) == 60
    assert len(mapper["correlations"]) == 12
    assert all(len(row) == 12 for row in mapper["correlations"])
    assert len(mapper["volatilities"]) == 12
    assert len(mapper["intervals"]) == payload["interval_count"]
    assert len(mapper["nodes"]) == payload["node_count"] == mapper["node_count"]
    assert len(mapper["edges"]) == payload["edge_count"] == mapper["edge_count"]
    assert mapper["as_of"] == payload["as_of"]
    assert mapper["config_hash"]


def test_public_combined_payload_helper_matches_the_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _rows()
    direct = analysis.industry_explorer_payload(rows)

    assert direct["as_of"] == rows[-1]["date"]
    assert direct["cloud"]["as_of"] == direct["as_of"]
    assert direct["mapper"]["as_of"] == direct["as_of"]
    assert direct["dates"] == direct["cloud"]["dates"] == direct["mapper"]["dates"]
    assert direct["row_count"] == 60
    assert direct["node_count"] == len(direct["mapper"]["nodes"])
    assert "data_dir" not in direct

    data_dir = _data_dir(tmp_path, rows)
    code, cli_payload = _json_payload(capsys, ["industries", "--data-dir", str(data_dir), "--json"])
    assert code == 0
    for key in ("as_of", "dates", "cloud", "mapper", "node_count", "edge_count"):
        assert cli_payload[key] == direct[key]


def test_latest_complete_window_skips_incomplete_trailing_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _rows()
    latest_complete = rows[-1]["date"]
    incomplete = dict(rows[-1])
    incomplete["date"] = (date.fromisoformat(str(rows[-1]["date"])) + timedelta(days=1)).isoformat()
    for column in analysis.INDUSTRY_COLUMNS:
        incomplete[column] = ""
    rows.append(incomplete)
    data_dir = _data_dir(tmp_path, rows)

    code, payload = _json_payload(capsys, ["industries", "--data-dir", str(data_dir), "--json"])

    assert code == 0
    assert payload["as_of"] == latest_complete
    assert payload["dates"][-1] == latest_complete
    assert incomplete["date"] not in payload["dates"]

    # Explicit selection stays strict: asking for the incomplete date fails.
    code, payload = _json_payload(
        capsys,
        ["industries", "--data-dir", str(data_dir), "--date", str(incomplete["date"]), "--json"],
    )
    assert code == 2
    assert payload == {}


def test_explicit_date_and_as_of_alias_select_the_trailing_window(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _rows()
    selected_index = 70
    selected = str(rows[selected_index]["date"])
    data_dir = _data_dir(tmp_path, rows)

    code, payload = _json_payload(
        capsys, ["industries", "--data-dir", str(data_dir), "--date", selected, "--json"]
    )

    assert code == 0
    assert payload["as_of"] == selected
    expected_dates = [str(row["date"]) for row in rows[selected_index - 59 : selected_index + 1]]
    assert payload["dates"] == expected_dates
    assert payload["cloud"]["dates"][-1] == selected
    assert payload["mapper"]["as_of"] == selected

    code, alias_payload = _json_payload(
        capsys, ["industries", "--data-dir", str(data_dir), "--as-of", selected, "--json"]
    )
    assert code == 0
    assert alias_payload == payload


def test_industries_command_resolves_the_active_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _data_dir(tmp_path)
    snapshot_id = "b" * 64
    snapshot_rows = _rows(90)
    snapshot_dir = data_dir / "snapshots" / snapshot_id
    _write_tda(snapshot_dir, snapshot_rows)
    state = data_dir / "state"
    state.mkdir()
    (state / "active_snapshot.json").write_text(
        json.dumps({"schema_version": 1, "snapshot_id": snapshot_id}),
        encoding="utf-8",
        newline="\n",
    )

    code, payload = _json_payload(capsys, ["industries", "--data-dir", str(data_dir), "--json"])

    assert code == 0
    assert payload["active_snapshot_id"] == payload["snapshot_id"] == snapshot_id
    assert payload["data_dir"] == str(snapshot_dir)
    assert payload["active_data_dir"] == str(snapshot_dir)
    assert payload["as_of"] == str(snapshot_rows[-1]["date"])
    assert payload["dates"] == [str(row["date"]) for row in snapshot_rows[-60:]]


def test_summary_output_has_the_expected_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _data_dir(tmp_path)

    assert cli.main(["industries", "--data-dir", str(data_dir)]) == 0

    output = capsys.readouterr().out
    for marker in (
        "Data directory:",
        "Active snapshot:",
        "As of:",
        "Window:",
        "Window sessions: 60",
        "Industries: 12",
        "PCA components: 2",
        "Nodes:",
        "Edges:",
        "Intervals:",
    ):
        assert marker in output, marker


def test_json_stdout_is_deterministic_and_sorted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _data_dir(tmp_path)

    assert cli.main(["industries", "--data-dir", str(data_dir), "--json"]) == 0
    first = capsys.readouterr().out
    assert cli.main(["industries", "--data-dir", str(data_dir), "--json"]) == 0
    second = capsys.readouterr().out

    assert first == second
    assert first.endswith("\n")
    payload = json.loads(first)
    assert first == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert list(payload) == sorted(payload)


def test_json_file_output_is_utf8_sorted_key_lf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = _data_dir(tmp_path)
    output_path = tmp_path / "artifacts" / "industry.json"

    assert (
        cli.main(["industries", "--data-dir", str(data_dir), "--json", "--out", str(output_path)])
        == 0
    )
    stdout = capsys.readouterr().out

    raw = output_path.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    payload = json.loads(text)
    assert text == stdout
    assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert "Wrote:" not in stdout

    # Writing without --json produces the same deterministic file and leaves
    # the human-readable summary on stdout.
    second_path = tmp_path / "artifacts" / "industry-second.json"
    assert cli.main(["industries", "--data-dir", str(data_dir), "--out", str(second_path)]) == 0
    human = capsys.readouterr().out
    assert "As of:" in human
    assert second_path.read_bytes() == raw


def test_industries_command_alias(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = _data_dir(tmp_path)

    code, payload = _json_payload(capsys, ["industry", "--data-dir", str(data_dir), "--json"])

    assert code == 0
    assert payload["command"] == "industries"
    assert payload["as_of"] == _rows()[-1]["date"]


@pytest.mark.parametrize(
    ("name", "setup"),
    [
        ("missing", lambda tmp_path: None),
        ("empty", lambda tmp_path: _write_tda(tmp_path / "data", [])),
        ("short", lambda tmp_path: _data_dir(tmp_path, _rows(59))),
    ],
)
def test_missing_or_invalid_data_exits_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    setup: object,
) -> None:
    setup(tmp_path)  # type: ignore[operator]
    data_dir = tmp_path / (name if name == "missing" else "data")

    assert cli.main(["industries", "--data-dir", str(data_dir)]) == 2
    assert "error:" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("selected", ["not-a-date", "1990-01-01", "2023-01-03"])
def test_invalid_date_selection_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], selected: str
) -> None:
    data_dir = _data_dir(tmp_path)

    assert cli.main(["industries", "--data-dir", str(data_dir), "--date", selected]) == 2
    assert "error:" in capsys.readouterr().err.lower()


def test_missing_industry_column_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _rows()
    for row in rows:
        row.pop(analysis.INDUSTRY_COLUMNS[0])
    data_dir = _data_dir(tmp_path, rows)

    assert cli.main(["industries", "--data-dir", str(data_dir)]) == 2
    assert "industry column" in capsys.readouterr().err.lower()
