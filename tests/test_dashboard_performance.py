"""A7 performance tests for the cached dashboard layer."""

from __future__ import annotations

from topomarket.ui.performance import (
    CACHED_P95_LIMIT_MS,
    DEMO_STARTUP_LIMIT_MS,
    measure_cached_date_changes,
    measure_dashboard_startup,
    run_a7_benchmarks,
)


def test_cached_date_change_p95_within_limit() -> None:
    result = measure_cached_date_changes(iterations=100)
    assert result["iterations"] == 100
    assert result["p95_ms"] <= CACHED_P95_LIMIT_MS
    assert result["within_limit"] is True
    assert result["environment"]["topomarket_version"]
    assert result["environment"]["python_version"]
    assert result["build"]["package_version"]
    assert result["cache_hits"] >= 100


def test_demo_startup_within_limit() -> None:
    result = measure_dashboard_startup()
    assert result["startup_ms"] <= DEMO_STARTUP_LIMIT_MS
    assert result["within_limit"] is True
    assert result["sessions"] > 0
    assert result["environment"]["reference_environment"]


def test_combined_benchmarks_payload() -> None:
    result = run_a7_benchmarks()
    assert set(result) == {"cached_date_changes", "demo_startup"}
    assert result["cached_date_changes"]["within_limit"]
    assert result["demo_startup"]["within_limit"]
