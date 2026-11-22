"""Causal daily topological anomaly score for TopoMarket (Step 4).

For every market close ``t`` the scorer uses the last ``window_sessions`` S&P 500
log returns ending at ``t`` (never future data):

1. robustly scale the window (median / 1.4826 * MAD),
2. delay-embed it,
3. compute Vietoris-Rips H0/H1 persistence,
4. take ``L(t)`` as the largest finite H1 lifetime (0 when there are no finite
   H1 pairs),
5. compute ``D(t) = |L(t) - median(previous 252 valid L values)|`` and rank
   ``D(t)`` against the previous 252 valid ``D`` values with the midrank formula
   ``score = 100 * (below + 0.5 * equal) / 252``.

Warm-up is explicit: points before the full 60-return window are ``unavailable``,
points before 252 L references (or 252 D references) are ``warming_up``.  A
window is valid only when all of its returns are finite; a missing return
invalidates the window until a new run of 60 consecutive valid returns exists
(no interpolation, no exchange-calendar inference).  ``tda_daily`` is already
the ordered complete-session table, so consecutive rows are consecutive
sessions by contract.

Custom configurations are flagged exploratory when their fields differ from the
frozen default; the cache key binds the output to the configuration hash, the
input values and the produced points.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from topomarket import __version__

from .config import (
    DEFAULT_CONFIG_HASH,
    LoadedTopologyConfig,
    TopologyConfig,
    load_topology_config,
)
from .errors import TopologyError
from .window import window_topology

CSV_COLUMNS: tuple[str, ...] = (
    "date",
    "sp500_log_return",
    "L",
    "D",
    "score",
    "state",
    "h1_count",
    "reason",
)
SIDECAR_SUFFIX = ".meta.json"


class ScoreError(TopologyError):
    """Raised for invalid scoring inputs or configurations."""


class ScoreExportError(ScoreError):
    """Raised when an export would overwrite a different result identity."""


@dataclass(frozen=True, slots=True)
class TopologyPoint:
    """One scored (or unavailable/warming-up) market close."""

    date: str
    log_return: float | None
    l_value: float | None
    deviation: float | None
    score: float | None
    state: str
    h1_count: int
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "sp500_log_return": self.log_return,
            "L": self.l_value,
            "D": self.deviation,
            "score": self.score,
            "state": self.state,
            "h1_count": self.h1_count,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class TopologyScoreSeries:
    """Deterministic result of one score computation."""

    points: tuple[TopologyPoint, ...]
    config: TopologyConfig
    config_hash: str
    exploratory: bool
    cache_key: str
    scored_count: int
    warmup_count: int
    unavailable_count: int
    first_scored_date: str | None
    last_scored_date: str | None
    latest_score: float | None
    latest_date: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "config_hash": self.config_hash,
            "cache_key": self.cache_key,
            "exploratory": self.exploratory,
            "algorithm_version": self.config.algorithm_version,
            "row_count": len(self.points),
            "scored_count": self.scored_count,
            "warmup_count": self.warmup_count,
            "unavailable_count": self.unavailable_count,
            "first_scored_date": self.first_scored_date,
            "last_scored_date": self.last_scored_date,
            "latest_date": self.latest_date,
            "latest_score": self.latest_score,
            "points": [point.as_dict() for point in self.points],
        }


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ScoreError("boolean values are not valid returns")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ScoreError(f"non-numeric return value: {value!r}") from exc
    if not math.isfinite(parsed):
        return None
    return parsed


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ScoreError(f"invalid observation date: {value!r}") from exc


def _resolve_config(
    config: TopologyConfig | LoadedTopologyConfig | Mapping[str, Any] | None,
) -> tuple[TopologyConfig, str, bool]:
    if config is None:
        loaded = load_topology_config()
        return loaded, str(loaded.config_hash), bool(loaded.exploratory)
    if isinstance(config, LoadedTopologyConfig):
        return config, str(config.config_hash), bool(config.exploratory)
    if isinstance(config, Mapping):
        config = TopologyConfig.from_dict(config)
    if not isinstance(config, TopologyConfig):
        raise ScoreError(f"unsupported configuration type: {type(config).__name__}")
    config_hash = config.config_hash()
    return config, config_hash, config_hash != DEFAULT_CONFIG_HASH


def _normalise_observations(
    rows: Iterable[Any] | Any,
) -> list[tuple[date, float | None]]:
    if rows is None:
        raise ScoreError("rows are required")
    if isinstance(rows, (str, bytes)):
        raise ScoreError("rows must be a sequence of observations, not text")
    materialised = list(rows)
    observations: list[tuple[date, float | None]] = []
    seen: set[date] = set()
    for row in materialised:
        if isinstance(row, Mapping):
            raw_date = row.get("date")
            raw_return = row.get("sp500_log_return", row.get("log_return"))
        else:
            raw_date = getattr(row, "date", None)
            raw_return = getattr(row, "sp500_log_return", getattr(row, "log_return", None))
        if raw_date is None:
            raise ScoreError("observation is missing a date")
        observation_date = _to_date(raw_date)
        if observation_date in seen:
            raise ScoreError(f"duplicate observation date: {observation_date.isoformat()}")
        seen.add(observation_date)
        observations.append((observation_date, _to_float(raw_return)))
    observations.sort(key=lambda item: item[0])
    return observations


def _percent_rank(
    score_scale: float, reference: Sequence[float], value: float, window: int
) -> float:
    tolerance = 1e-12
    below = 0
    equal = 0
    for candidate in reference[-window:]:
        if candidate < value - tolerance:
            below += 1
        elif abs(candidate - value) <= tolerance:
            equal += 1
    return score_scale * (below + 0.5 * equal) / float(window)


def _points_digest(points: Sequence[TopologyPoint]) -> str:
    payload = [
        {
            "date": point.date,
            "log_return": _format_number(point.log_return),
            "L": _format_number(point.l_value),
            "D": _format_number(point.deviation),
            "score": _format_number(point.score),
            "state": point.state,
            "h1_count": point.h1_count,
        }
        for point in points
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _format_number(value: float | None) -> str | None:
    if value is None:
        return None
    return repr(float(value))


def compute_topology_scores(
    rows: Iterable[Any] | Any,
    config: TopologyConfig | LoadedTopologyConfig | Mapping[str, Any] | None = None,
) -> TopologyScoreSeries:
    """Compute the causal daily topology score series for ``rows``.

    ``rows`` must expose ``date`` and ``sp500_log_return`` (mapping keys or
    attributes).  Dates are normalised from date/datetime/ISO/tidy formats and
    duplicates are rejected.
    """

    resolved_config, config_hash, exploratory = _resolve_config(config)
    observations = _normalise_observations(rows)
    window = resolved_config.window_sessions
    reference_window = resolved_config.reference_window
    score_scale = resolved_config.score_scale
    min_interval = resolved_config.min_interval

    returns = [item[1] for item in observations]
    points: list[TopologyPoint] = []
    valid_l: list[float] = []
    valid_d: list[float] = []
    valid_streak = 0

    for index, (observation_date, _value) in enumerate(observations):
        current_return = returns[index]
        if current_return is None:
            valid_streak = 0
            points.append(
                TopologyPoint(
                    date=observation_date.isoformat(),
                    log_return=None,
                    l_value=None,
                    deviation=None,
                    score=None,
                    state="unavailable",
                    h1_count=0,
                    reason="missing or non-finite return",
                )
            )
            continue
        valid_streak += 1
        if valid_streak < window:
            points.append(
                TopologyPoint(
                    date=observation_date.isoformat(),
                    log_return=current_return,
                    l_value=None,
                    deviation=None,
                    score=None,
                    state="unavailable",
                    h1_count=0,
                    reason="fewer than window_sessions consecutive valid returns",
                )
            )
            continue

        window_returns = [float(value) for value in returns[index - window + 1 : index + 1]]
        result = window_topology(window_returns, resolved_config)
        if not result.available:
            points.append(
                TopologyPoint(
                    date=observation_date.isoformat(),
                    log_return=current_return,
                    l_value=None,
                    deviation=None,
                    score=None,
                    state="unavailable",
                    h1_count=0,
                    reason=result.reason,
                )
            )
            continue

        h1_lifetimes = np.asarray(result.lifetimes.h1, dtype=float)
        h1_lifetimes = h1_lifetimes[h1_lifetimes > min_interval]
        l_value = float(np.max(h1_lifetimes)) if h1_lifetimes.size else 0.0
        h1_count = int(h1_lifetimes.size)

        deviation: float | None = None
        score: float | None = None
        reason: str | None = None
        if len(valid_l) >= reference_window:
            deviation = abs(l_value - float(median(valid_l[-reference_window:])))
            if len(valid_d) >= reference_window:
                score = _percent_rank(score_scale, valid_d, deviation, reference_window)
                state = "scored"
            else:
                state = "warming_up"
                reason = (
                    "fewer than reference_window valid D references "
                    f"({len(valid_d)}/{reference_window})"
                )
            # D enters the reference history only when it was computed from a
            # full L reference set (never from partial histories).
            valid_d.append(deviation)
        else:
            state = "warming_up"
            reason = (
                "fewer than reference_window valid L references "
                f"({len(valid_l)}/{reference_window})"
            )

        points.append(
            TopologyPoint(
                date=observation_date.isoformat(),
                log_return=current_return,
                l_value=l_value,
                deviation=deviation,
                score=score,
                state=state,
                h1_count=h1_count,
                reason=reason,
            )
        )
        valid_l.append(l_value)

    scored_points = [point for point in points if point.state == "scored"]
    warmup_points = [point for point in points if point.state == "warming_up"]
    unavailable_points = [point for point in points if point.state == "unavailable"]
    latest_scored = scored_points[-1] if scored_points else None
    content_digest = _points_digest(points)
    cache_key = hashlib.sha256(
        json.dumps(
            {
                "config_hash": config_hash,
                "algorithm_version": resolved_config.algorithm_version,
                "package_version": __version__,
                "row_count": len(points),
                "first_date": points[0].date if points else None,
                "last_date": points[-1].date if points else None,
                "content_digest": content_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return TopologyScoreSeries(
        points=tuple(points),
        config=resolved_config,
        config_hash=config_hash,
        exploratory=exploratory,
        cache_key=cache_key,
        scored_count=len(scored_points),
        warmup_count=len(warmup_points),
        unavailable_count=len(unavailable_points),
        first_scored_date=scored_points[0].date if scored_points else None,
        last_scored_date=latest_scored.date if latest_scored else None,
        latest_score=latest_scored.score if latest_scored else None,
        latest_date=points[-1].date if points else None,
    )


def _sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + SIDECAR_SUFFIX)


def _check_export_collision(series: TopologyScoreSeries, path: Path, metadata_path: Path) -> None:
    if metadata_path == path:
        raise ScoreExportError("metadata_path must not be the CSV target")
    sidecar = _sidecar_path(path)
    if path.exists() and not sidecar.exists():
        raise ScoreExportError(
            f"refusing to overwrite {path}: no metadata sidecar proves the result identity"
        )
    if sidecar.exists():
        try:
            existing = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ScoreExportError(f"invalid sidecar {sidecar}: {exc}") from exc
        if not isinstance(existing, Mapping):
            raise ScoreExportError(f"invalid sidecar {sidecar}: expected an object")
        if existing.get("config_hash") != series.config_hash:
            raise ScoreExportError(
                "refusing to overwrite an export produced with a different configuration "
                f"({existing.get('config_hash')} != {series.config_hash})"
            )
        if bool(existing.get("exploratory")) != series.exploratory:
            raise ScoreExportError(
                "refusing to overwrite an export with a different exploratory/frozen status"
            )


def _csv_number(value: float | None) -> str:
    if value is None:
        return ""
    return _format_csv_float(value)


def _format_csv_float(value: float) -> str:
    text = repr(float(value))
    return text


def write_scores_csv(
    series: TopologyScoreSeries,
    path: Path | str,
    *,
    metadata_path: Path | str | None = None,
) -> Path:
    """Write the deterministic score CSV plus a metadata sidecar.

    An existing export produced by a different configuration or with a different
    frozen/exploratory status is never silently overwritten.
    """

    target = Path(path).expanduser()
    sidecar = (
        Path(metadata_path).expanduser() if metadata_path is not None else _sidecar_path(target)
    )
    _check_export_collision(series, target, sidecar)
    target.parent.mkdir(parents=True, exist_ok=True)
    sidecar.parent.mkdir(parents=True, exist_ok=True)

    buffer_lines: list[str] = [",".join(CSV_COLUMNS)]
    for point in series.points:
        buffer_lines.append(
            ",".join(
                [
                    point.date,
                    _csv_number(point.log_return),
                    _csv_number(point.l_value),
                    _csv_number(point.deviation),
                    _csv_number(point.score),
                    point.state,
                    str(point.h1_count),
                    (point.reason or "").replace(",", ";"),
                ]
            )
        )
    text = "\n".join(buffer_lines) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=target.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
    os.replace(temporary, target)

    metadata = {
        "config_hash": series.config_hash,
        "exploratory": series.exploratory,
        "cache_key": series.cache_key,
        "algorithm_version": series.config.algorithm_version,
        "row_count": len(series.points),
        "scored_count": series.scored_count,
        "warmup_count": series.warmup_count,
        "unavailable_count": series.unavailable_count,
    }
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=sidecar.parent, delete=False
    ) as handle:
        temporary_meta = Path(handle.name)
        handle.write(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    os.replace(temporary_meta, sidecar)
    return target


def load_daily_rows(data_dir: Path | str) -> list[dict[str, str]]:
    """Load ``tda_daily`` rows from a data/snapshot directory (active or baseline)."""
    root = Path(data_dir)
    path = root / "normalized" / "tda_daily.csv"
    if not path.is_file():
        raise ScoreError(f"tda_daily table not found in {root}")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


__all__ = [
    "CSV_COLUMNS",
    "SIDECAR_SUFFIX",
    "ScoreError",
    "ScoreExportError",
    "TopologyPoint",
    "TopologyScoreSeries",
    "compute_topology_scores",
    "load_daily_rows",
    "write_scores_csv",
]
