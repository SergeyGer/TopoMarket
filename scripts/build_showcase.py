#!/usr/bin/env python3
"""Build the committed synthetic showcase fixture used by the public walkthrough.

The fixture is fully deterministic: a seeded synthetic market path with engineered drawdowns,
12 synthetic industry series, a VIX-like series, the frozen topology score series and a frozen
evaluation report. It contains no private or genuine market data and is safe to publish.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from topomarket.analysis.evaluation import build_evaluation_report, write_evaluation_report  # noqa: E402
from topomarket.data.schemas import INDUSTRIES_DAILY_COLUMNS, TDA_DAILY_COLUMNS  # noqa: E402
from topomarket.topology import compute_topology_scores, load_topology_config, write_scores_csv  # noqa: E402

SEED = 4242
SNAPSHOT_ID = "showcase-synthetic"
BASELINE_REPORT = ROOT / "docs" / "reports" / "evaluation-v1.0-baseline.json"
START = date(2005, 1, 3)
END = date(2026, 9, 30)
CRASHES = (
    (date(2008, 9, 2), 32, 0.0130, 0.0060),  # global financial crisis
    (date(2020, 2, 20), 26, 0.0210, 0.0080),  # pandemic crash
    (date(2022, 1, 3), 34, 0.0080, 0.0040),  # rate-shock drawdown
    (date(2025, 2, 19), 24, 0.0110, 0.0050),  # synthetic late drawdown
)


def _business_days(start: date, end: date) -> list[date]:
    values: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return values


def _dates() -> list[date]:
    return _business_days(START, END)


def _crash_factor(day: date, days_index: int) -> float:
    for start, length, first_drop, last_drop in CRASHES:
        offset = (day - start).days
        if 0 <= offset < length:
            progress = offset / max(1, length - 1)
            drop = first_drop + (last_drop - first_drop) * progress
            return 1.0 - drop
    return 1.0


def _rows() -> list[dict[str, str]]:
    days = _dates()
    rng = random.Random(SEED)
    price = 1200.0
    previous: float | None = None
    recent_changes: list[float] = []
    rows: list[dict[str, str]] = []
    base_returns = [rng.gauss(0.0, 0.0045) for _ in days]
    industry_betas = [0.55, 0.9, 1.05, 0.8, 0.95, 1.1, 0.75, 0.7, 0.85, 0.6, 1.0, 0.65]
    for index, day in enumerate(days):
        market_return = base_returns[index]
        crash_factor = _crash_factor(day, index)
        if crash_factor < 1.0:
            market_return -= 1.0 - crash_factor
        price = max(10.0, price * math.exp(market_return))
        recent_changes.append(market_return)
        if len(recent_changes) > 20:
            recent_changes.pop(0)
        volatility = math.sqrt(
            sum(value * value for value in recent_changes) / max(1, len(recent_changes))
        )
        vix = max(9.0, 12.0 + volatility * 900.0 + abs(min(0.0, market_return)) * 500.0)
        row: dict[str, str] = {
            "date": day.isoformat(),
            "sp500_close": f"{price:.6f}",
            "sp500_log_return": "" if previous is None else f"{math.log(price / previous):.12f}",
            "vix_close": f"{vix:.6f}",
        }
        for position, column in enumerate(INDUSTRIES_DAILY_COLUMNS[1:]):
            beta = industry_betas[position]
            idiosyncratic = 0.0025 * math.sin(index / (5.0 + position) + position)
            industry_return = beta * market_return + idiosyncratic + rng.gauss(0.0, 0.0008)
            row[column] = f"{industry_return:.10f}"
        rows.append(row)
        previous = price
    return rows


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out: Path) -> dict:
    rows = _rows()
    normalized = out / "normalized"
    reports = out / "reports"
    normalized.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    header = list(TDA_DAILY_COLUMNS)
    lines = [",".join(header)]
    lines.extend(",".join(row[column] for column in header) for row in rows)
    tda_path = normalized / "tda_daily.csv"
    tda_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    config = load_topology_config()
    series = compute_topology_scores(rows, config)
    scores_path = out / "scores.csv"
    write_scores_csv(series, scores_path)

    import_manifest = {
        "schema_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "source_ids": ["showcase_synthetic"],
        "row_counts": {"showcase_synthetic": len(rows)},
        "normalized_row_counts": {
            "sp500_daily": len(rows),
            "industries_daily": len(rows),
            "tda_daily": len(rows),
        },
        "normalized_tables": ["sp500_daily", "industries_daily", "tda_daily"],
        "latest_data_date": rows[-1]["date"],
        "synthetic": True,
        "private_data": False,
    }
    # Populated input provenance for the public report (#81): carry the import-manifest
    # identity/digest and the independent-calendar metadata recorded by the CLI path.
    from topomarket.data.manifest import compute_snapshot_id
    from topomarket.data.signals import load_signal_calendars

    calendars = load_signal_calendars(out)
    snapshot_provenance = {
        "source": "import_manifest",
        "manifest_digest": compute_snapshot_id(import_manifest),
        "data_dir": str(out),
        "signal_calendars": {
            "as_of": calendars["as_of"],
            "sources": {
                "price": calendars["price_source"],
                "industry": calendars["industry_source"],
                "vix": calendars["vix_source"],
            },
            "reasons": calendars["reasons"],
            "joint_fallback": calendars["joint_fallback"],
        },
    }

    baseline_report = None
    if BASELINE_REPORT.exists():
        baseline_report = json.loads(BASELINE_REPORT.read_text(encoding="utf-8"))
    report = build_evaluation_report(
        rows,
        score_series=series,
        config_hash=str(config.config_hash),
        snapshot_id=SNAPSHOT_ID,
        seed=42,
        include_ablations=False,
        baseline_report=baseline_report,
        snapshot_provenance=snapshot_provenance,
    )
    report_path = reports / "evaluation-showcase.json"
    write_evaluation_report(report, report_path)

    (out / "import_manifest.json").write_text(
        json.dumps(import_manifest, indent=2) + "\n", encoding="utf-8"
    )
    parser_reports = {
        "by_source": {
            "showcase_synthetic": {
                "row_count": len(rows),
                "first_observation": rows[0]["date"],
                "last_observation": rows[-1]["date"],
                "synthetic": True,
            }
        }
    }
    (out / "parser_reports.json").write_text(
        json.dumps(parser_reports, indent=2) + "\n", encoding="utf-8"
    )
    normalized_schema = {
        "schema_version": 1,
        "tables": {
            "tda_daily": {
                "columns": list(TDA_DAILY_COLUMNS),
                "units": {"sp500_close": "index points", "vix_close": "index points"},
            }
        },
    }
    (normalized / "schemas.json").write_text(
        json.dumps(normalized_schema, indent=2) + "\n", encoding="utf-8"
    )
    files = [
        "normalized/tda_daily.csv",
        "scores.csv",
        "scores.csv.meta.json",
        "reports/evaluation-showcase.json",
        "import_manifest.json",
        "parser_reports.json",
        "normalized/schemas.json",
    ]
    hashes = {name: _hash(out / name) for name in files}
    manifest = {
        "schema_version": 1,
        "description": (
            "Synthetic, deterministic public showcase for the TopoMarket walkthrough. "
            "Contains no genuine market data."
        ),
        "synthetic": True,
        "private_data": False,
        "seed": SEED,
        "snapshot_id": SNAPSHOT_ID,
        "row_count": len(rows),
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "generator": "scripts/build_showcase.py",
        "hashes": hashes,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the synthetic public showcase fixture.")
    parser.add_argument("--out", type=Path, default=ROOT / "showcase")
    parser.add_argument(
        "--verify", action="store_true", help="Verify committed hashes instead of writing."
    )
    args = parser.parse_args(argv)
    if args.verify:
        manifest_path = args.out / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        problems = []
        for name, expected in (manifest.get("hashes") or {}).items():
            actual = _hash(args.out / name)
            if actual != expected:
                problems.append(name)
        if problems:
            print("showcase hash mismatch: " + ", ".join(problems), file=sys.stderr)
            return 1
        print(f"showcase fixture verified ({len(manifest.get('hashes') or {})} files)")
        return 0
    manifest = build(args.out)
    print(
        "showcase built: "
        f"{manifest['row_count']} synthetic sessions "
        f"{manifest['start_date']}..{manifest['end_date']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
