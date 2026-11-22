"""One-window topology pipeline: robust scaling, delay embedding, persistence.

A window is considered available only when it is long enough, contains finite
observations, has a non-zero robust scale, and persistence completes.  Invalid
windows are not exceptions: they return a frozen result with ``available`` set
to false and a human-readable ``reason`` so a caller can continue through a
time series and mark the unavailable date.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from .config import DEFAULT_CONFIG, TopologyConfig
from .embedding import delay_embedding
from .errors import PersistenceError, ScalingError, WindowError
from .persistence import Diagrams, Lifetimes, finite_lifetimes, persistence_diagrams
from .scaling import (  # noqa: F401 - compatibility re-exports for the window API
    MAD_TO_SIGMA,
    ScaledWindow,
    mad_scale,
    median_absolute_deviation,
    median_and_mad,
    median_mad_scale,
    robust_scale,
    scale_window,
)


@dataclass(frozen=True)
class WindowTopologyResult:
    """Frozen outcome of the topology pipeline for one causal window."""

    available: bool
    reason: str | None = None
    points: np.ndarray | None = None
    diagrams: Diagrams = field(default_factory=lambda: Diagrams(()))
    lifetimes: Lifetimes = field(default_factory=lambda: Lifetimes(()))
    L: float = 0.0

    def __post_init__(self) -> None:
        points = self.points
        if points is not None:
            # Always own a private, read-only copy.  In particular, do not flip
            # the writeable flag on a caller-owned point-cloud array.
            array = np.array(points, dtype=float, copy=True)
            array.setflags(write=False)
            object.__setattr__(self, "points", array)
        # Rebuild the containers so their arrays are private and read-only even
        # when a caller supplied writable arrays.
        object.__setattr__(self, "diagrams", Diagrams(tuple(self.diagrams or ())))
        object.__setattr__(self, "lifetimes", Lifetimes(tuple(self.lifetimes or ())))
        object.__setattr__(self, "L", float(self.L))
        if not self.available and self.reason is None:
            object.__setattr__(self, "reason", "window is unavailable")

    @property
    def is_available(self) -> bool:
        return self.available

    @property
    def ok(self) -> bool:
        return self.available

    @property
    def unavailable(self) -> bool:
        return not self.available

    @property
    def error(self) -> str | None:
        return self.reason

    @property
    def message(self) -> str | None:
        return self.reason

    @property
    def unavailable_reason(self) -> str | None:
        return self.reason

    @property
    def point_cloud(self) -> np.ndarray | None:
        return self.points

    @property
    def embedding(self) -> np.ndarray | None:
        return self.points

    @property
    def embedded(self) -> np.ndarray | None:
        return self.points

    @property
    def cloud(self) -> np.ndarray | None:
        return self.points

    @property
    def h0(self) -> np.ndarray:
        return self.diagrams.h0

    @property
    def h1(self) -> np.ndarray:
        return self.diagrams.h1

    @property
    def homology_0(self) -> np.ndarray:
        return self.h0

    @property
    def homology_1(self) -> np.ndarray:
        return self.h1

    @property
    def h0_lifetimes(self) -> np.ndarray:
        return self.lifetimes.h0

    @property
    def h1_lifetimes(self) -> np.ndarray:
        return self.lifetimes.h1

    @property
    def finite_lifetimes(self) -> Lifetimes:
        return self.lifetimes

    @property
    def max_lifetime(self) -> float:
        values = np.asarray(self.h1_lifetimes, dtype=float)
        return float(np.max(values)) if values.size else 0.0

    @property
    def h1_count(self) -> int:
        return int(np.asarray(self.h1_lifetimes).size)

    @property
    def n_loops(self) -> int:
        return self.h1_count

    @property
    def loop_count(self) -> int:
        return self.h1_count

    @property
    def total_persistence(self) -> float:
        return self.L

    @property
    def lifetime_sum(self) -> float:
        return self.L

    @property
    def h1_persistence(self) -> float:
        return self.L

    @property
    def persistence(self) -> float:
        return self.L

    @property
    def score(self) -> float:
        return self.L

    @property
    def midrank_score(self) -> float:
        return self.L

    @property
    def config(self) -> TopologyConfig:
        return getattr(self, "_config", DEFAULT_CONFIG)

    @property
    def config_hash(self) -> str:
        return self.config.config_hash()

    @property
    def window_sessions(self) -> int:
        return self.config.window_sessions

    @property
    def embedding_dimension(self) -> int:
        return self.config.embedding_dimension

    @property
    def lag(self) -> int:
        return self.config.lag

    @property
    def max_homology_dimension(self) -> int:
        return self.config.max_homology_dimension

    @property
    def maxdim(self) -> int:
        return self.config.max_homology_dimension

    @property
    def homology_coeff_field(self) -> int:
        return self.config.homology_coeff_field

    @property
    def coeff(self) -> int:
        return self.config.homology_coeff_field

    @property
    def coeff_field(self) -> int:
        return self.config.homology_coeff_field

    @property
    def min_interval(self) -> float:
        return self.config.min_interval

    @property
    def metric(self) -> str:
        return self.config.metric

    @property
    def window_index(self) -> Any:
        return getattr(self, "_window_index", None)

    @property
    def index(self) -> Any:
        return self.window_index

    @property
    def date(self) -> Any:
        return getattr(self, "_date", None)

    def __getitem__(self, key: str) -> Any:
        if hasattr(type(self), key) or key in {
            "available",
            "reason",
            "points",
            "diagrams",
            "lifetimes",
            "L",
        }:
            return getattr(self, key)
        metadata = getattr(self, "_metadata", {})
        if key in metadata:
            return metadata[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "points": self.points,
            "diagrams": self.diagrams,
            "lifetimes": self.lifetimes,
            "L": self.L,
        }


#: Friendly aliases for the result type.
WindowResult = WindowTopologyResult
TopologyWindow = WindowTopologyResult
TopologyWindowResult = WindowTopologyResult
WindowTopology = WindowTopologyResult
WindowTopologyOutput = WindowTopologyResult


def _coerce_config(value: Any) -> TopologyConfig:
    if value is None:
        return DEFAULT_CONFIG
    if isinstance(value, TopologyConfig):
        return value
    if isinstance(value, Mapping):
        return TopologyConfig.from_dict(value)
    raise WindowError("config must be a TopologyConfig or mapping")


def _unavailable(
    config: TopologyConfig,
    reason: str,
    *,
    points: np.ndarray | None = None,
    **metadata: Any,
) -> WindowTopologyResult:
    result = WindowTopologyResult(
        available=False,
        reason=reason,
        points=points,
        diagrams=Diagrams(()),
        lifetimes=Lifetimes(()),
        L=0.0,
    )
    object.__setattr__(result, "_config", config)
    object.__setattr__(result, "_metadata", dict(metadata))
    object.__setattr__(result, "_window_index", metadata.get("window_index"))
    object.__setattr__(result, "_date", metadata.get("date"))
    return result


def window_topology(
    values: Any = None,
    config: TopologyConfig | Mapping[str, Any] | None = None,
    *args: Any,
    **kwargs: Any,
) -> WindowTopologyResult:
    """Compute topology for one window using the frozen configuration.

    ``values`` is normally a one-dimensional sequence of observations.  A
    two-dimensional array is treated as an already-embedded point cloud, which
    is useful when comparing a diagram directly with ripser.  For a longer
    series only the configured trailing window is examined, so an older
    non-finite observation cannot invalidate the current window.  Extra
    positional arguments are accepted as metadata (for example a window
    index).
    """

    if isinstance(values, TopologyConfig) and config is not None:
        values, config = config, values
    if values is None:
        for key in ("returns", "series", "window_values", "data", "observations", "window"):
            if key in kwargs:
                values = kwargs.pop(key)
                break
    if values is None:
        raise WindowError("window_topology requires a sequence of values")

    if "config" in kwargs:
        if config is not None:
            raise WindowError("config was provided more than once")
        config = kwargs.pop("config")
    config = _coerce_config(config)

    # Allow a caller to override configuration fields directly on the window
    # call, including the short aliases used by the persistence API.
    config_fields = set(TopologyConfig.field_names())
    aliases = {
        "dimension": "embedding_dimension",
        "maxdim": "max_homology_dimension",
        "coeff": "homology_coeff_field",
        "coeff_field": "homology_coeff_field",
    }
    overrides: dict[str, Any] = {}
    for key in list(kwargs):
        target = key if key in config_fields else aliases.get(key)
        if target is not None:
            overrides[target] = kwargs.pop(key)
    if overrides:
        config = replace(config, **overrides)

    metadata: dict[str, Any] = {}
    for key in ("window_index", "index", "window_id", "date", "as_of", "session"):
        if key in kwargs:
            metadata[key] = kwargs.pop(key)
    if args:
        metadata.setdefault("window_index", args[0])
        if len(args) > 1:
            metadata.setdefault("extra", args[1:])
    # Remaining keyword arguments are retained as metadata.  This keeps the
    # primitive usable with callers that attach a date or session identifier.
    metadata.update(kwargs)

    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return _unavailable(config, "window values must be numeric", **metadata)
    if array.ndim == 2 and array.shape[1] == 1:
        array = array.reshape(-1)

    if array.ndim == 2:
        points = np.asarray(array, dtype=float)
        if points.shape[0] == 0:
            return _unavailable(config, "window contains no points", **metadata)
        # A point cloud is already the current embedded window; only inspect it
        # after any trailing-window selection would have taken place.
        if not np.all(np.isfinite(points)):
            return _unavailable(config, "window contains non-finite values", **metadata)
    elif array.ndim == 1:
        if array.size < config.window_sessions:
            return _unavailable(
                config,
                "window is too short: requires at least "
                f"{config.window_sessions} observations, got {array.size}",
                **metadata,
            )
        # Select the configured trailing window *before* validating finiteness:
        # an old bad observation outside the current window is irrelevant.
        window_values = np.asarray(array[-config.window_sessions :], dtype=float)
        if not np.all(np.isfinite(window_values)):
            return _unavailable(config, "window contains non-finite values", **metadata)
        try:
            scaled = robust_scale(window_values, config)
        except ScalingError as error:
            return _unavailable(config, str(error), **metadata)
        try:
            points = delay_embedding(scaled, config)
        except Exception as error:  # embedding/validation errors make the window unavailable
            return _unavailable(config, str(error), **metadata)
    else:
        return _unavailable(config, "window values must be one- or two-dimensional", **metadata)

    try:
        diagrams = persistence_diagrams(points, config)
        lifetime_values = finite_lifetimes(diagrams, config.min_interval)
        h1_values = lifetime_values.h1 if len(lifetime_values) > 1 else np.empty(0, dtype=float)
        # The anomaly score uses the largest finite H1 lifetime; a valid cloud
        # without finite H1 pairs has L = 0.0.
        score = float(np.max(h1_values)) if h1_values.size else 0.0
    except PersistenceError as error:
        return _unavailable(config, str(error), points=points, **metadata)
    except Exception as error:
        return _unavailable(config, f"persistence failed: {error}", points=points, **metadata)

    result = WindowTopologyResult(
        available=True,
        reason=None,
        points=points,
        diagrams=diagrams,
        lifetimes=lifetime_values,
        L=score,
    )
    object.__setattr__(result, "_config", config)
    object.__setattr__(result, "_metadata", dict(metadata))
    object.__setattr__(result, "_window_index", metadata.get("window_index"))
    object.__setattr__(result, "_date", metadata.get("date"))
    return result


def causal_window(
    values: Any = None,
    config: TopologyConfig | Mapping[str, Any] | None = None,
    *args: Any,
    **kwargs: Any,
) -> WindowTopologyResult:
    """Alias for :func:`window_topology` emphasising its causal trailing window."""

    return window_topology(values, config, *args, **kwargs)


# Common alternative spellings.
compute_window = window_topology
compute_window_topology = window_topology
window_result = window_topology
topology_for_window = window_topology
topology_window = window_topology
window_tda = window_topology
window_persistence = window_topology


__all__ = [
    "TopologyWindow",
    "TopologyWindowResult",
    "WindowResult",
    "WindowTopology",
    "WindowTopologyOutput",
    "WindowTopologyResult",
    "causal_window",
    "compute_window",
    "compute_window_topology",
    "topology_for_window",
    "topology_window",
    "window_persistence",
    "window_result",
    "window_tda",
    "window_topology",
]
