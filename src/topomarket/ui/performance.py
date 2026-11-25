"""Selection-cache performance benchmarks for the public dashboard (CL02).

Cached screen payloads are keyed by the dashboard selection plus the data
signature; a cached date change must not recompute topology, the Mapper graph or
the evaluation report.  The helpers record the measured values, the environment
and the build identity so the 500 ms cached date-change target and the cold
startup measurement can be evidenced (browser measurements are recorded
separately from these backend timings).
"""

from __future__ import annotations

import importlib.metadata
import platform
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from topomarket import __version__

from .dashboard import DashboardSelection
from .panels import DashboardData, PanelCache, load_dashboard_data

CACHED_P95_LIMIT_MS = 500.0
DEMO_STARTUP_LIMIT_MS = 15_000.0
REFERENCE_ENVIRONMENT = "2-vCPU / 4-GB Linux reference machine"


def environment_metadata() -> dict[str, Any]:
    """Return the environment/build metadata recorded with measurements."""

    def package_version(name: str) -> str | None:
        try:
            return importlib.metadata.version(name)
        except (importlib.metadata.PackageNotFoundError, ValueError):
            return None

    return {
        "python_version": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": __import__("os").cpu_count(),
        "topomarket_version": __version__,
        "numpy_version": package_version("numpy"),
        "ripser_version": package_version("ripser"),
        "reference_environment": REFERENCE_ENVIRONMENT,
    }


def build_metadata() -> dict[str, Any]:
    return {
        "package_version": __version__,
        "build": "source-checkout",
        "cache": "in-memory selection cache",
        "measured_at_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, int(round(fraction * (len(sorted_values) - 1)))))
    return float(sorted_values[index])


def _selection_for(data: DashboardData, *, date: str | None = None) -> DashboardSelection:
    return DashboardSelection(
        screen="structure",
        mode="live",
        date=date or (data.session_dates[-1] if data.session_dates else None),
        network_view="correlation",
    )


def benchmark_dates(data: DashboardData, *, sample: int = 60) -> list[str]:
    """Return warmed-up benchmark dates sampled across the series.

    A structure payload needs a full 60-session industry window, so the first
    sessions are excluded; the sample is deterministic and spread over the whole
    history so the measurement is not dominated by a single regime.
    """

    dates = list(data.session_dates)
    if not dates:
        return []
    first_usable = min(200, len(dates) - 1)
    candidates = dates[first_usable:]
    if len(candidates) <= sample:
        return candidates
    step = max(1, len(candidates) // sample)
    return candidates[::step][:sample]


def _prewarm(data: DashboardData, cache: PanelCache, dates: Sequence[str]) -> float:
    started = time.perf_counter()
    for date in dates:
        if date in data.date_index:
            cache.get(_selection_for(data, date=date))
    return (time.perf_counter() - started) * 1000.0


def measure_cached_date_changes(
    data: DashboardData | None = None,
    dates: Sequence[str] | None = None,
    iterations: int = 100,
) -> dict[str, Any]:
    """Measure cached date-change latency and the demo startup time.

    Payloads for every distinct selected date are built once (pre-warm), then
    ``iterations`` cached date changes are timed.  The p95 must be <= 500 ms.
    """
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if data is None:
        data = load_dashboard_data("demo")
    if not data.session_dates:
        raise ValueError("dashboard data has no sessions")
    selected_dates = [str(value) for value in dates] if dates else benchmark_dates(data)
    selected_dates = [value for value in selected_dates if value in data.date_index]
    if not selected_dates:
        raise ValueError("no valid benchmark dates")
    cache = PanelCache(data)
    prewarm_ms = _prewarm(data, cache, sorted(set(selected_dates)))
    timings: list[float] = []
    for index in range(iterations):
        date = selected_dates[index % len(selected_dates)]
        started = time.perf_counter()
        cache.get(_selection_for(data, date=date))
        timings.append((time.perf_counter() - started) * 1000.0)
    ordered = sorted(timings)
    return {
        "iterations": iterations,
        "unique_dates": len(set(selected_dates)),
        "p50_ms": round(statistics.median(ordered), 4),
        "p95_ms": round(_percentile(ordered, 0.95), 4),
        "max_ms": round(max(ordered), 4),
        "prewarm_ms": round(prewarm_ms, 4),
        "cache_hits": cache.hits,
        "cache_misses": cache.misses,
        "environment": environment_metadata(),
        "build": build_metadata(),
        "limit_ms": CACHED_P95_LIMIT_MS,
        "within_limit": _percentile(ordered, 0.95) <= CACHED_P95_LIMIT_MS,
    }


def measure_dashboard_startup(data: DashboardData | None = None) -> dict[str, Any]:
    """Measure a cold load plus the first cached payload build (demo by default)."""
    started = time.perf_counter()
    loaded = data if data is not None else load_dashboard_data("demo")
    load_ms = (time.perf_counter() - started) * 1000.0
    cache = PanelCache(loaded)
    started = time.perf_counter()
    if loaded.session_dates:
        cache.get(_selection_for(loaded))
    payload_ms = (time.perf_counter() - started) * 1000.0
    startup_ms = load_ms + payload_ms
    return {
        "startup_ms": round(startup_ms, 4),
        "load_ms": round(load_ms, 4),
        "first_payload_ms": round(payload_ms, 4),
        "sessions": len(loaded.session_dates),
        "profile": loaded.profile,
        "environment": environment_metadata(),
        "build": build_metadata(),
        "limit_ms": DEMO_STARTUP_LIMIT_MS,
        "within_limit": startup_ms <= DEMO_STARTUP_LIMIT_MS,
    }


def run_a7_benchmarks(data: DashboardData | None = None) -> dict[str, Any]:
    """Return both A7 measurements in one payload for the report/tests."""
    return {
        "cached_date_changes": measure_cached_date_changes(data),
        "demo_startup": measure_dashboard_startup(data),
    }


__all__ = [
    "CACHED_P95_LIMIT_MS",
    "DEMO_STARTUP_LIMIT_MS",
    "REFERENCE_ENVIRONMENT",
    "build_metadata",
    "environment_metadata",
    "measure_cached_date_changes",
    "measure_dashboard_startup",
    "run_a7_benchmarks",
]
