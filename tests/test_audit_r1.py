"""R1: price signals use the index calendar, independent of industry coverage."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from topomarket.analysis.evaluation import build_evaluation_report
from topomarket.data.signals import (
    load_evaluation_rows,
    load_signal_calendars,
)
from topomarket.topology import compute_topology_scores, load_topology_config

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "showcase"


def _tda_rows() -> list[dict[str, str]]:
    with (SHOWCASE / "normalized" / "tda_daily.csv").open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _split_fixture(tmp_path: Path) -> dict[str, Path]:
    rows = _tda_rows()
    last = rows[-1]
    base_close = float(last["sp500_close"])
    later = []
    for offset in range(1, 4):
        close = base_close * (1.0 + 0.001 * offset)
        later.append(
            {
                "date": f"2026-10-{offset:02d}",
                "sp500_close": f"{close:.6f}",
                "sp500_log_return": f"{math.log(close / base_close):.12f}",
                "vix_close": f"{15.0 + offset:.6f}",
            }
        )
    price_rows = [
        {
            "date": row["date"],
            "sp500_close": row["sp500_close"],
            "price_source": "fred",
            "sp500_log_return": row["sp500_log_return"],
        }
        for row in rows
    ] + [
        {
            "date": row["date"],
            "sp500_close": row["sp500_close"],
            "price_source": "fred",
            "sp500_log_return": row["sp500_log_return"],
        }
        for row in later
    ]
    industry_columns = ["date"] + [key for key in rows[0] if key.startswith("ind_")]
    industry_rows = [
        {column: row.get(column, "") for column in industry_columns} for row in rows[:-50]
    ]
    vix_rows = [{"date": row["date"], "vix_close": row["vix_close"]} for row in rows] + [
        {"date": row["date"], "vix_close": row["vix_close"]} for row in later
    ]
    normalized = tmp_path / "normalized"
    _write(
        normalized / "sp500_daily.csv",
        ["date", "sp500_close", "price_source", "sp500_log_return"],
        price_rows,
    )
    _write(normalized / "industries_daily.csv", industry_columns, industry_rows)
    _write(normalized / "vix_daily.csv", ["date", "vix_close"], vix_rows)
    return {
        "root": tmp_path,
        "price": normalized / "sp500_daily.csv",
        "industry": normalized / "industries_daily.csv",
    }


def test_showcase_keeps_explicit_joint_fallback() -> None:
    calendar = load_signal_calendars(SHOWCASE)
    assert calendar["joint_fallback"] is True
    assert calendar["as_of"]["price"] == calendar["as_of"]["industry"]
    assert "fallback" in calendar["reasons"]["price"]


def test_price_calendar_extends_past_industry_calendar(tmp_path: Path) -> None:
    fixture = _split_fixture(tmp_path)
    calendar = load_signal_calendars(fixture["root"])
    assert calendar["joint_fallback"] is False
    assert calendar["calendars"]["price"]["source"] == "index"
    assert calendar["calendars"]["industry"]["source"] == "industry"
    assert calendar["as_of"]["price"] == "2026-10-03"
    assert calendar["as_of"]["industry"] < calendar["as_of"]["price"]
    rows = load_evaluation_rows(fixture["root"])
    assert rows[-1]["date"] == "2026-10-03"
    assert rows[-1]["vix_close"] != ""


def test_industry_mutation_does_not_change_price_scores_or_labels(tmp_path: Path) -> None:
    fixture = _split_fixture(tmp_path)
    config = load_topology_config()
    before_calendar = load_signal_calendars(fixture["root"])
    before_series = compute_topology_scores(before_calendar["price_rows"], config)
    before_rows = load_evaluation_rows(fixture["root"])
    before_report = build_evaluation_report(
        before_rows,
        score_series=before_series,
        config_hash=str(config.config_hash),
        snapshot_id="split-fixture",
        seed=42,
    )

    # Append rows and alter values in the industry table only.
    industry_rows = _tda_rows()[:-50]
    columns = ["date"] + [key for key in industry_rows[0] if key.startswith("ind_")]
    mutated = []
    for index, row in enumerate(industry_rows):
        mutated.append(
            {
                column: (
                    f"{0.5 if column.startswith('ind_') and index % 2 else -0.4:.10f}"
                    if column.startswith("ind_")
                    else row.get(column, "")
                )
                for column in columns
            }
        )
    _write(fixture["industry"], columns, mutated)

    after_calendar = load_signal_calendars(fixture["root"])
    after_series = compute_topology_scores(after_calendar["price_rows"], config)
    after_rows = load_evaluation_rows(fixture["root"])
    after_report = build_evaluation_report(
        after_rows,
        score_series=after_series,
        config_hash=str(config.config_hash),
        snapshot_id="split-fixture",
        seed=42,
    )
    assert json.dumps(before_series.as_dict(), sort_keys=True) == json.dumps(
        after_series.as_dict(), sort_keys=True
    )
    assert json.dumps(before_report, sort_keys=True) == json.dumps(after_report, sort_keys=True)
    assert before_report["data_end"] == "2026-10-03"
