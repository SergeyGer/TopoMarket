"""Opt-in A6 acceptance checks for the chronological evaluation pipeline.

Uses the real private seed archive (imported to a temporary directory) and
computes the full deterministic report: calibration/frozen policies, test
metrics, paired moving-block bootstrap, evidence wording, provenance links and
the append-only ledger. Skips when ``TOPOMARKET_SEED_DIR`` is unset.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from topomarket.analysis.evaluation import (
    build_evaluation_report,
    report_digest,
)
from topomarket.analysis.labels import build_target_labels
from topomarket.analysis.ledger import ForecastLedger
from topomarket.data.adapters import import_sources
from topomarket.topology import compute_topology_scores, load_daily_rows, load_topology_config

SEED_ENV = "TOPOMARKET_SEED_DIR"
EXPECTED_ALLOWED_WORDINGS = {
    "Experimental market anomaly",
    "Historical early-warning evidence",
}


def _seed_root() -> Path:
    value = os.environ.get(SEED_ENV)
    if not value:
        pytest.skip(f"{SEED_ENV} is not set; A6 acceptance checks are opt-in")
    root = Path(value)
    if not (root / "raw").is_dir():
        pytest.skip(f"{SEED_ENV} does not contain a raw/ seed directory")
    return root


def _data_dir(tmp_path: Path, seed_root: Path) -> Path:
    data_dir = tmp_path / "data"
    import_sources(seed_root / "raw", data_dir)
    return data_dir


def test_a6_report_determinism_provenance_and_wording(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = _data_dir(tmp_path, seed_root)
    rows = load_daily_rows(data_dir)
    config = load_topology_config()
    series = compute_topology_scores(rows, config)
    snapshot_id = "private-acceptance-snapshot"

    first = build_evaluation_report(
        rows,
        score_series=series,
        config_hash=str(config.config_hash),
        snapshot_id=snapshot_id,
        seed=42,
        include_ablations=False,
    )
    second = build_evaluation_report(
        rows,
        score_series=series,
        config_hash=str(config.config_hash),
        snapshot_id=snapshot_id,
        seed=42,
        include_ablations=False,
    )
    assert report_digest(first) == report_digest(second)
    assert first["snapshot_id"] == snapshot_id
    assert first["seed"] == 42
    assert first["primary_method"] == "tda"
    assert first["comparator_method"] in {"vix", "realized_vol"}
    assert first["periods"]["test"]["start"] == "2014-01-01"

    # Frozen calibration/policy with explicit frozen hash identity.
    assert first["calibrations"]
    assert first["policies"]
    for policy in first["policies"].values():
        assert policy["policy_hash"]
        assert isinstance(policy["cutoff"], float)

    # Every metrics table links back to the source snapshot and dates.
    for _method, metrics in first["metrics"].items():
        assert metrics["snapshot_id"] == snapshot_id
        assert metrics["start"] == "2014-01-01"
        assert "episode_recall" in metrics
        assert "false_alerts_per_year" in metrics
        assert "average_precision" in metrics
        if metrics["episode_count"] == 0:
            assert metrics["episode_recall"] is None
    assert first["episode_count"] > 0
    assert first["resolved_episode_count"] > 0

    bootstrap = first["bootstrap"]
    for key in (
        "episode_recall_gain",
        "tda_episode_recall",
        "tda_false_alerts_per_year",
    ):
        interval = bootstrap[key]
        assert interval["valid_replicates"] > 0
        assert interval["total_replicates"] == 1_000
    assert first["evidence"]["wording"] in EXPECTED_ALLOWED_WORDINGS
    assert isinstance(first["evidence"]["criteria"], dict)
    assert set(first["examples"]) == set(first["methods"])
    for examples in first["examples"].values():
        assert {"matched", "missed", "false_alerts"} <= set(examples)


def test_a6_ledger_and_future_suffix_causality(tmp_path: Path) -> None:
    seed_root = _seed_root()
    data_dir = _data_dir(tmp_path, seed_root)
    rows = load_daily_rows(data_dir)
    config = load_topology_config()
    series = compute_topology_scores(rows, config)
    ledger_path = tmp_path / "private-ledger.jsonl"
    report = build_evaluation_report(
        rows,
        score_series=series,
        config_hash=str(config.config_hash),
        snapshot_id="ledger-snapshot",
        seed=11,
        include_ablations=False,
        ledger_path=ledger_path,
    )
    records = ForecastLedger(ledger_path).read()
    primary_alerts = report["metrics"][report["primary_method"]]["alerts"]
    assert len(records) == len(primary_alerts)
    assert all(record["snapshot_id"] == "ledger-snapshot" for record in records)
    assert all(record["alert"] is True for record in records)

    # Future data does not change earlier target labels.
    prefix = rows[:6000]
    full_labels = build_target_labels(rows)
    prefix_labels = build_target_labels(prefix)
    prefix_dates = {row["date"] for row in prefix[:-20]}
    compared = 0
    for full_label, prefix_label in zip(full_labels, prefix_labels, strict=False):
        if prefix_label.date not in prefix_dates:
            continue
        assert full_label.target == prefix_label.target
        assert full_label.breach_date == prefix_label.breach_date
        compared += 1
    assert compared > 5000
    assert ledger_path.stat().st_size > 0
