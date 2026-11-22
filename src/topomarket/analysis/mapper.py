"""Correlation-distance Mapper graph for the industry explorer.

The graph is built from exactly the same validated 60-session industry window
used by :mod:`topomarket.analysis.industries`.  For that window we compute:

* the Pearson correlation matrix between the twelve industry return columns;
* the clipped correlation distance ``clip(1 - correlation, 0, 2)``;
* annualised sample volatility (``std(ddof=1) * sqrt(252)``) for each industry;
* three inclusive, equally wide lens intervals (a single interval when every
  industry has the same volatility);
* one Mapper node per connected component of the distance graph inside each
  interval, using the inclusive distance threshold ``1.0``.

Identical member sets that occur in more than one interval are merged once,
keeping the lowest interval index as the deterministic representative.  Two
distinct nodes are connected whenever their member sets intersect, which keeps
the shared-boundary relationships visible after that merge.

The public surface is deliberately small::

    compute_mapper_graph(rows, as_of=None) -> MapperGraph
    mapper_payload(graph) -> dict

All results are frozen and expose a JSON-serialisable payload.  The module has
no I/O, network, cache or UI dependencies.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from topomarket.analysis.industries import (
    INDUSTRY_COLUMNS,
    INDUSTRY_LABELS,
    WINDOW_SESSIONS,
    IndustryAnalysisError,
    IndustryWindow,
    select_industry_window,
)
from topomarket.topology.config import DEFAULT_CONFIG, TopologyConfig

#: Inclusive Mapper clustering threshold in correlation-distance units.
DEFAULT_THRESHOLD = 1.0
THRESHOLD = DEFAULT_THRESHOLD
MAPPER_THRESHOLD = DEFAULT_THRESHOLD
DISTANCE_THRESHOLD = DEFAULT_THRESHOLD

#: Number of inclusive lens intervals.
DEFAULT_INTERVALS = 3
DEFAULT_N_INTERVALS = DEFAULT_INTERVALS
INTERVAL_COUNT = DEFAULT_INTERVALS
N_INTERVALS = DEFAULT_INTERVALS
COVER_INTERVALS = DEFAULT_INTERVALS

#: Trading-day annualisation used for sample volatility.
TRADING_DAYS = 252
ANNUALIZATION = float(TRADING_DAYS)
PERIODS_PER_YEAR = TRADING_DAYS
ANNUALISATION = ANNUALIZATION

#: The exact string used when a singleton node has no pairwise correlation.
NOT_APPLICABLE = "Not applicable"


class MapperError(IndustryAnalysisError):
    """Raised when a Mapper graph cannot be built from the industry window."""


# Friendly aliases used by callers/tests.
MapperGraphError = MapperError
IndustryMapperError = MapperError
MapperAnalysisError = MapperError


class _PayloadDict(dict[str, Any]):
    """A payload mapping that can also be called like ``payload()``."""

    def __call__(self) -> dict[str, Any]:
        return dict(self)


def _as_float_array(values: Any, *, name: str) -> np.ndarray:
    if isinstance(values, IndustryWindow):
        values = values.values
    elif hasattr(values, "window") and isinstance(values.window, IndustryWindow):
        values = values.window.values
    try:
        array = np.array(values, dtype=float, copy=True)
    except (TypeError, ValueError) as error:
        raise MapperError(f"{name} must be numeric") from error
    if not np.all(np.isfinite(array)):
        raise MapperError(f"{name} contains non-finite values")
    return array


def _coerce_annualization(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise MapperError(f"annualization must be a finite number > 0, got {value!r}")
    annualization = float(value)
    if not math.isfinite(annualization) or annualization <= 0.0:
        raise MapperError(f"annualization must be a finite number > 0, got {value!r}")
    return annualization


def _coerce_threshold(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise MapperError(f"threshold must be a finite number >= 0, got {value!r}")
    threshold = float(value)
    if not math.isfinite(threshold) or threshold < 0.0:
        raise MapperError(f"threshold must be a finite number >= 0, got {value!r}")
    return threshold


def _coerce_interval_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise MapperError(f"n_intervals must be an integer >= 1, got {value!r}")
    count = int(value)
    if count < 1:
        raise MapperError(f"n_intervals must be an integer >= 1, got {value!r}")
    return count


def _column_names(count: int, columns: Sequence[str] | None) -> tuple[str, ...]:
    if columns is None:
        if count == len(INDUSTRY_COLUMNS):
            return INDUSTRY_COLUMNS
        return tuple(f"column_{index}" for index in range(count))
    names = tuple(str(column) for column in columns)
    if len(names) != count:
        raise MapperError(
            f"columns must have one name per series: got {len(names)} for {count} columns"
        )
    return names


def pearson_correlations(
    values: Any,
    *,
    columns: Sequence[str] | None = None,
) -> np.ndarray:
    """Return the Pearson correlation matrix of a rows-by-series window.

    A series whose observations are all identical has no defined Pearson
    correlation.  The check compares the values directly instead of testing a
    computed standard deviation, because repeating a value such as ``0.1`` can
    leave a tiny non-zero sample standard deviation.  A constant series raises
    :class:`MapperError` rather than poisoning the graph with ``nan``.
    """

    matrix = _as_float_array(values, name="values")
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    if matrix.ndim != 2:
        raise MapperError(f"values must be two-dimensional, got shape {matrix.shape}")
    if matrix.shape[0] < 2:
        raise MapperError("at least two observations are required for Pearson correlation")
    if matrix.shape[1] < 1:
        raise MapperError("at least one series is required for Pearson correlation")

    names = _column_names(matrix.shape[1], columns)
    constant = [
        name for name, column in zip(names, matrix.T, strict=True) if np.all(column == column[0])
    ]
    if constant:
        joined = ", ".join(constant)
        raise MapperError(f"Pearson correlation is undefined for constant-vector series: {joined}")

    if matrix.shape[1] == 1:
        correlation = np.ones((1, 1), dtype=float)
    else:
        correlation = np.array(np.corrcoef(matrix, rowvar=False), dtype=float, copy=True)
        if correlation.shape != (matrix.shape[1], matrix.shape[1]):
            raise MapperError(
                f"Pearson correlation produced an unexpected matrix shape: {correlation.shape}"
            )
        # Round-off can push a correlation a few ulps outside [-1, 1]; the
        # clipped value is what the Mapper distance is defined on.
        correlation = np.clip(correlation, -1.0, 1.0)
        correlation = (correlation + correlation.T) / 2.0
        np.fill_diagonal(correlation, 1.0)
    return correlation


def pearson_correlation(left: Any, right: Any) -> float:
    """Return the Pearson correlation between two equal-length series."""

    left_values = _as_float_array(left, name="left").reshape(-1)
    right_values = _as_float_array(right, name="right").reshape(-1)
    if left_values.size != right_values.size:
        raise MapperError("left and right must have the same number of observations")
    matrix = np.column_stack((left_values, right_values))
    return float(pearson_correlations(matrix)[0, 1])


def correlation_distance(correlation: Any, *, clip: bool = True) -> Any:
    """Convert Pearson correlation(s) to clipped correlation distance.

    The distance is ``1 - correlation`` clipped to ``[0, 2]``.  Scalar input
    returns a float; array input returns a new NumPy array.
    """

    values = np.asarray(correlation, dtype=float)
    if not np.all(np.isfinite(values)):
        raise MapperError("correlations must be finite")
    if clip:
        values = np.clip(values, -1.0, 1.0)
    distances = np.clip(1.0 - values, 0.0, 2.0)
    if distances.ndim == 0:
        return float(distances)
    return distances


def correlation_distances(correlations: Any, *, clip: bool = True) -> Any:
    """Alias for :func:`correlation_distance` accepting a matrix."""

    return correlation_distance(correlations, clip=clip)


def clipped_correlation_distances(correlations: Any) -> Any:
    """Return correlation distances clipped to the closed interval ``[0, 2]``."""

    return correlation_distance(correlations, clip=True)


def annualized_volatility(
    values: Any,
    annualization: float = ANNUALIZATION,
    *,
    periods_per_year: float | None = None,
    ddof: int = 1,
) -> Any:
    """Return annualised sample volatility of one or more return series.

    A two-dimensional input is treated as rows of observations and columns of
    industries, so the result has one volatility per industry.  A
    one-dimensional input returns a single float.  The sample standard
    deviation uses ``ddof=1`` and is multiplied by ``sqrt(annualization)``.
    """

    periods = _coerce_annualization(annualization if periods_per_year is None else periods_per_year)
    if isinstance(ddof, bool) or not isinstance(ddof, (int, np.integer)) or int(ddof) < 1:
        raise MapperError(f"ddof must be an integer >= 1, got {ddof!r}")
    matrix = _as_float_array(values, name="values")
    if matrix.ndim not in (1, 2):
        raise MapperError(f"values must be one- or two-dimensional, got shape {matrix.shape}")
    if matrix.shape[0] < int(ddof) + 1:
        raise MapperError(
            "annualized sample volatility requires at least "
            f"{int(ddof) + 1} observations, got {matrix.shape[0]}"
        )
    deviation = np.std(matrix, axis=0, ddof=int(ddof)) * math.sqrt(periods)
    if np.asarray(deviation).ndim == 0:
        return float(deviation)
    return np.array(deviation, dtype=float, copy=True)


def annualized_sample_volatility(
    values: Any,
    annualization: float = ANNUALIZATION,
    **kwargs: Any,
) -> Any:
    """Alias for :func:`annualized_volatility`."""

    return annualized_volatility(values, annualization, **kwargs)


# Common alternative spellings.
annualised_volatility = annualized_volatility
annualized_volatilities = annualized_volatility
annualised_volatilities = annualized_volatility
annualized_sample_volatilities = annualized_volatility
sample_volatility = annualized_volatility
compute_volatility = annualized_volatility
annualized_std = annualized_volatility
volatility = annualized_volatility
correlation_matrix = pearson_correlations
pearson_correlation_matrix = pearson_correlations
compute_correlations = pearson_correlations
pairwise_correlations = pearson_correlations
pearson = pearson_correlations
corr = pearson_correlations
distance_matrix = correlation_distances
correlation_distance_matrix = correlation_distances
compute_distances = correlation_distances
pairwise_correlation_distances = correlation_distances
clipped_correlation_distance = correlation_distance


@dataclass(frozen=True, eq=False)
class MapperInterval:
    """One inclusive lens interval used by the Mapper cover."""

    lower: float
    upper: float
    index: int = 0

    def __post_init__(self) -> None:
        lower = float(self.lower)
        upper = float(self.upper)
        if not math.isfinite(lower) or not math.isfinite(upper):
            raise MapperError("interval bounds must be finite")
        if lower > upper:
            raise MapperError(f"interval lower bound {lower} exceeds upper bound {upper}")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(self, "index", int(self.index))

    @property
    def start(self) -> float:
        return self.lower

    @property
    def stop(self) -> float:
        return self.upper

    @property
    def lo(self) -> float:
        return self.lower

    @property
    def hi(self) -> float:
        return self.upper

    @property
    def bounds(self) -> tuple[float, float]:
        return (self.lower, self.upper)

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, value: Any) -> bool:
        """Return whether ``value`` lies inside the inclusive interval.

        The comparison is deliberately exact: adding an absolute tolerance
        would make tiny but distinct volatility values members of every
        interval and silently merge unrelated Mapper nodes.
        """

        value = float(value)
        return self.lower <= value <= self.upper

    def __iter__(self):
        yield self.lower
        yield self.upper

    def __len__(self) -> int:
        return 2

    def __getitem__(self, item: Any) -> Any:
        return self.bounds[item]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MapperInterval):
            return self.bounds == other.bounds
        if isinstance(other, (tuple, list)) and len(other) == 2:
            try:
                return self.bounds == (float(other[0]), float(other[1]))
            except (TypeError, ValueError):
                return NotImplemented
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.bounds)

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "lower": self.lower,
            "upper": self.upper,
            "start": self.lower,
            "stop": self.upper,
        }


def mapper_intervals(
    lens: Any,
    n_intervals: int = DEFAULT_INTERVALS,
    overlap: float = 0.0,
) -> tuple[MapperInterval, ...]:
    """Split the lens range into inclusive, equally wide intervals.

    Adjacent intervals share their boundary endpoint.  A lens with a single
    distinct value receives one interval instead of three zero-width copies.
    """

    values = _as_float_array(lens, name="lens").reshape(-1)
    if values.size == 0:
        raise MapperError("lens must contain at least one value")
    count = _coerce_interval_count(n_intervals)
    if isinstance(overlap, bool) or not isinstance(overlap, (int, float, np.integer, np.floating)):
        raise MapperError(f"overlap must be a number in [0, 1), got {overlap!r}")
    overlap_value = float(overlap)
    if not math.isfinite(overlap_value) or overlap_value < 0.0 or overlap_value >= 1.0:
        raise MapperError(f"overlap must be a number in [0, 1), got {overlap!r}")

    lower = float(np.min(values))
    upper = float(np.max(values))
    if lower == upper:
        return (MapperInterval(lower, upper, 0),)

    width = (upper - lower) / count
    if overlap_value == 0.0:
        edges = np.linspace(lower, upper, count + 1)
        return tuple(
            MapperInterval(float(edges[index]), float(edges[index + 1]), index)
            for index in range(count)
        )

    # A positive overlap extends each interval beyond the next start; the final
    # interval is clamped to the lens maximum so the cover stays bounded.
    step = width * (1.0 - overlap_value)
    intervals: list[MapperInterval] = []
    for index in range(count):
        start = lower + index * step
        stop = min(start + width, upper)
        intervals.append(MapperInterval(float(start), float(stop), index))
    intervals[-1] = MapperInterval(float(intervals[-1].lower), upper, count - 1)
    return tuple(intervals)


# Common alternative spellings.
inclusive_intervals = mapper_intervals
overlapping_intervals = mapper_intervals
cover_intervals = mapper_intervals
build_intervals = mapper_intervals
compute_intervals = mapper_intervals
interval_cover = mapper_intervals
lens_intervals = mapper_intervals
intervals_for_lens = mapper_intervals


def connected_components(
    distances: Any,
    threshold: float = DEFAULT_THRESHOLD,
    *,
    labels: Sequence[Any] | None = None,
) -> tuple[tuple[Any, ...], ...]:
    """Return inclusive threshold connected components of a distance matrix.

    Two indices are adjacent when their distance is less than or equal to the
    threshold.  Isolated indices are returned as singleton components.  If
    ``labels`` is supplied the components contain those labels instead of
    integer positions.
    """

    matrix = _as_float_array(distances, name="distances")
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise MapperError(f"distances must be a square matrix, got shape {matrix.shape}")
    limit = _coerce_threshold(threshold)
    size = matrix.shape[0]
    if labels is None:
        names: tuple[Any, ...] = tuple(range(size))
    else:
        names = tuple(labels)
        if len(names) != size:
            raise MapperError(f"labels must have one entry per series: got {len(names)} for {size}")

    adjacency: list[list[int]] = [[] for _ in range(size)]
    for left in range(size):
        for right in range(left + 1, size):
            if matrix[left, right] <= limit:
                adjacency[left].append(right)
                adjacency[right].append(left)

    seen = [False] * size
    components: list[tuple[Any, ...]] = []
    for start in range(size):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in adjacency[current]:
                if not seen[neighbour]:
                    seen[neighbour] = True
                    stack.append(neighbour)
        component.sort()
        components.append(tuple(names[index] for index in component))
    components.sort(key=lambda component: component[0] if component else ())
    return tuple(components)


components = connected_components
threshold_components = connected_components
cluster_components = connected_components
distance_components = connected_components


def _node_correlations(
    indices: Sequence[int],
    correlations: np.ndarray,
) -> tuple[float, ...] | str:
    if len(indices) < 2:
        return NOT_APPLICABLE
    values = [
        float(correlations[left, right])
        for position, left in enumerate(indices)
        for right in indices[position + 1 :]
    ]
    return tuple(sorted(values))


@dataclass(frozen=True)
class MapperNode:
    """One Mapper node: a component of industries inside one lens interval."""

    id: str
    interval_index: int
    members: tuple[str, ...]
    member_indices: tuple[int, ...]
    member_columns: tuple[str, ...]
    member_volatilities: tuple[float, ...]
    member_correlations: tuple[float, ...] | str
    position: tuple[float, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", str(self.id))
        object.__setattr__(self, "interval_index", int(self.interval_index))
        object.__setattr__(self, "members", tuple(str(value) for value in self.members))
        object.__setattr__(
            self, "member_indices", tuple(int(value) for value in self.member_indices)
        )
        object.__setattr__(
            self, "member_columns", tuple(str(value) for value in self.member_columns)
        )
        object.__setattr__(
            self,
            "member_volatilities",
            tuple(float(value) for value in self.member_volatilities),
        )
        if isinstance(self.member_correlations, str):
            object.__setattr__(self, "member_correlations", self.member_correlations)
        else:
            object.__setattr__(
                self,
                "member_correlations",
                tuple(float(value) for value in self.member_correlations),
            )
        position = (float(self.position[0]), float(self.position[1]))
        object.__setattr__(self, "position", position)

    @property
    def node_id(self) -> str:
        return self.id

    @property
    def key(self) -> str:
        return self.id

    @property
    def interval(self) -> int:
        return self.interval_index

    @property
    def cover_index(self) -> int:
        return self.interval_index

    @property
    def level(self) -> int:
        return self.interval_index

    @property
    def index(self) -> int:
        try:
            return int(self.id.rsplit("-", 1)[-1])
        except (TypeError, ValueError):
            return -1

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def member_count(self) -> int:
        return self.size

    @property
    def industries(self) -> tuple[str, ...]:
        return self.members

    @property
    def labels(self) -> tuple[str, ...]:
        return self.members

    @property
    def member_labels(self) -> tuple[str, ...]:
        return self.members

    @property
    def columns(self) -> tuple[str, ...]:
        return self.member_columns

    @property
    def indices(self) -> tuple[int, ...]:
        return self.member_indices

    @property
    def x(self) -> float:
        return self.position[0]

    @property
    def y(self) -> float:
        return self.position[1]

    @property
    def angle(self) -> float:
        return math.atan2(self.position[1], self.position[0]) % (2.0 * math.pi)

    @property
    def radius(self) -> float:
        return math.hypot(self.position[0], self.position[1])

    @property
    def circular_position(self) -> tuple[float, float]:
        return self.position

    @property
    def correlations(self) -> tuple[float, ...] | str:
        return self.member_correlations

    @property
    def pairwise_correlations(self) -> tuple[float, ...] | str:
        return self.member_correlations

    @property
    def member_correlation_values(self) -> tuple[float, ...] | str:
        return self.member_correlations

    @property
    def sorted_member_correlations(self) -> tuple[float, ...] | str:
        return self.member_correlations

    @property
    def correlation(self) -> float | str:
        return self.mean_correlation

    @property
    def mean_correlation(self) -> float | str:
        if isinstance(self.member_correlations, str):
            return self.member_correlations
        values = self.member_correlations
        if not values:
            return NOT_APPLICABLE
        return float(np.mean(values))

    @property
    def max_correlation(self) -> float | str:
        if isinstance(self.member_correlations, str) or not self.member_correlations:
            return NOT_APPLICABLE
        return float(max(self.member_correlations))

    @property
    def min_correlation(self) -> float | str:
        if isinstance(self.member_correlations, str) or not self.member_correlations:
            return NOT_APPLICABLE
        return float(min(self.member_correlations))

    @property
    def volatility(self) -> float:
        values = self.member_volatilities
        return float(np.mean(values)) if values else 0.0

    @property
    def mean_volatility(self) -> float:
        return self.volatility

    @property
    def tooltip(self) -> str:
        interval = self.interval_index
        members = ", ".join(self.members) if self.members else "(none)"
        correlations = self.member_correlations
        if isinstance(correlations, str):
            correlation_text = correlations
        else:
            correlation_text = ", ".join(f"{value:.4f}" for value in correlations)
        return (
            f"Mapper node {self.id} in lens interval {interval}: "
            f"{self.size} member(s) [{members}]; "
            f"mean annualized volatility {self.volatility:.4f}; "
            f"member correlations: {correlation_text}"
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_payload().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]

    def to_payload(self) -> dict[str, Any]:
        correlations: list[float] | str
        if isinstance(self.member_correlations, str):
            correlations = self.member_correlations
        else:
            correlations = [float(value) for value in self.member_correlations]
        return {
            "id": self.id,
            "node_id": self.id,
            "interval_index": self.interval_index,
            "interval": self.interval_index,
            "members": list(self.members),
            "industries": list(self.members),
            "member_columns": list(self.member_columns),
            "member_indices": list(self.member_indices),
            "size": self.size,
            "member_count": self.size,
            "position": [float(self.position[0]), float(self.position[1])],
            "circular_position": [float(self.position[0]), float(self.position[1])],
            "x": float(self.position[0]),
            "y": float(self.position[1]),
            "angle": self.angle,
            "radius": self.radius,
            "member_volatilities": [float(value) for value in self.member_volatilities],
            "volatility": self.volatility,
            "mean_volatility": self.volatility,
            "member_correlations": correlations,
            "correlations": correlations,
            "mean_correlation": self.mean_correlation,
            "max_correlation": self.max_correlation,
            "min_correlation": self.min_correlation,
            "tooltip": self.tooltip,
        }

    def as_dict(self) -> dict[str, Any]:
        return self.to_payload()

    def to_dict(self) -> dict[str, Any]:
        return self.to_payload()

    @property
    def payload(self) -> _PayloadDict:
        return _PayloadDict(self.to_payload())


@dataclass(frozen=True)
class MapperEdge:
    """An undirected Mapper edge between two distinct nodes."""

    source: str
    target: str
    members: tuple[str, ...]
    source_index: int = 0
    target_index: int = 0
    weight: float = 1.0
    member_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "target", str(self.target))
        object.__setattr__(self, "members", tuple(str(value) for value in self.members))
        object.__setattr__(self, "source_index", int(self.source_index))
        object.__setattr__(self, "target_index", int(self.target_index))
        object.__setattr__(self, "weight", float(self.weight))
        object.__setattr__(
            self, "member_indices", tuple(int(value) for value in self.member_indices)
        )

    @property
    def source_id(self) -> str:
        return self.source

    @property
    def target_id(self) -> str:
        return self.target

    @property
    def shared_members(self) -> tuple[str, ...]:
        return self.members

    @property
    def shared_member_indices(self) -> tuple[int, ...]:
        return self.member_indices

    @property
    def intersection(self) -> tuple[str, ...]:
        return self.members

    @property
    def shared_member_count(self) -> int:
        return len(self.members)

    @property
    def overlap(self) -> int:
        return len(self.members)

    @property
    def id(self) -> str:
        return f"{self.source}--{self.target}"

    @property
    def edge_id(self) -> str:
        return self.id

    @property
    def tooltip(self) -> str:
        members = ", ".join(self.members) if self.members else "(none)"
        return (
            f"Mapper edge {self.source} -- {self.target} shares "
            f"{len(self.members)} member(s) [{members}]"
        )

    def __iter__(self):
        yield self.source
        yield self.target

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_payload().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "edge_id": self.id,
            "source": self.source,
            "target": self.target,
            "source_id": self.source,
            "target_id": self.target,
            "source_index": self.source_index,
            "target_index": self.target_index,
            "members": list(self.members),
            "shared_members": list(self.members),
            "intersection": list(self.members),
            "member_indices": list(self.member_indices),
            "shared_member_indices": list(self.member_indices),
            "shared_member_count": self.shared_member_count,
            "overlap": self.overlap,
            "weight": self.weight,
            "tooltip": self.tooltip,
        }

    def as_dict(self) -> dict[str, Any]:
        return self.to_payload()

    def to_dict(self) -> dict[str, Any]:
        return self.to_payload()

    @property
    def payload(self) -> _PayloadDict:
        return _PayloadDict(self.to_payload())


def _assemble_nodes(
    window: IndustryWindow,
    correlations: np.ndarray,
    distances: np.ndarray,
    volatilities: np.ndarray,
    intervals: Sequence[MapperInterval],
    threshold: float,
) -> tuple[tuple[MapperNode, ...], tuple[MapperEdge, ...]]:
    """Build deduplicated nodes and all shared-member edges."""

    representatives: dict[tuple[int, ...], int] = {}
    for interval in intervals:
        member_indices = tuple(
            index for index, value in enumerate(volatilities) if interval.contains(float(value))
        )
        if not member_indices:
            continue
        submatrix = distances[np.ix_(member_indices, member_indices)]
        for component in connected_components(submatrix, threshold):
            indices = tuple(sorted(member_indices[int(position)] for position in component))
            previous = representatives.get(indices)
            if previous is None or interval.index < previous:
                representatives[indices] = interval.index

    # Nodes are ordered by their canonical member tuple so IDs and circular
    # positions do not depend on interval iteration or dictionary insertion.
    ordered = sorted(representatives.items(), key=lambda item: item[0])
    total = len(ordered)
    nodes: list[MapperNode] = []
    for position, (indices, interval_index) in enumerate(ordered):
        angle = (2.0 * math.pi * position / total) if total else 0.0
        nodes.append(
            MapperNode(
                id=f"node-{position:02d}",
                interval_index=interval_index,
                members=tuple(window.labels[index] for index in indices),
                member_indices=indices,
                member_columns=tuple(window.columns[index] for index in indices),
                member_volatilities=tuple(float(volatilities[index]) for index in indices),
                member_correlations=_node_correlations(indices, correlations),
                position=(round(math.cos(angle), 6), round(math.sin(angle), 6)),
            )
        )

    edges: list[MapperEdge] = []
    for left in range(total):
        left_node = nodes[left]
        left_members = set(left_node.member_indices)
        for right in range(left + 1, total):
            right_node = nodes[right]
            shared = tuple(sorted(left_members.intersection(right_node.member_indices)))
            if not shared:
                continue
            edges.append(
                MapperEdge(
                    source=left_node.id,
                    target=right_node.id,
                    members=tuple(window.labels[index] for index in shared),
                    source_index=left,
                    target_index=right,
                    weight=float(len(shared)),
                    member_indices=shared,
                )
            )
    return tuple(nodes), tuple(edges)


@dataclass(frozen=True, eq=False)
class MapperGraph:
    """A deterministic correlation-distance Mapper graph and its metadata."""

    window: IndustryWindow
    correlations: np.ndarray
    distances: np.ndarray
    volatilities: np.ndarray
    intervals: tuple[MapperInterval, ...]
    nodes: tuple[MapperNode, ...]
    edges: tuple[MapperEdge, ...]
    threshold: float = DEFAULT_THRESHOLD
    annualization: float = ANNUALIZATION
    config: TopologyConfig = DEFAULT_CONFIG
    labels: tuple[str, ...] = field(default_factory=lambda: INDUSTRY_LABELS)

    def __post_init__(self) -> None:
        if not isinstance(self.window, IndustryWindow):
            raise MapperError("window must be an IndustryWindow")
        correlations = np.array(self.correlations, dtype=float, copy=True)
        distances = np.array(self.distances, dtype=float, copy=True)
        volatilities = np.array(self.volatilities, dtype=float, copy=True)
        if correlations.ndim != 2 or correlations.shape[0] != correlations.shape[1]:
            raise MapperError(
                f"correlations must be a square matrix, got shape {correlations.shape}"
            )
        if distances.shape != correlations.shape:
            raise MapperError(
                "distances shape must match correlations: "
                f"{distances.shape} != {correlations.shape}"
            )
        if volatilities.ndim != 1 or volatilities.size != correlations.shape[0]:
            raise MapperError("volatilities must have one entry per correlated series")
        for name, array in (
            ("correlations", correlations),
            ("distances", distances),
            ("volatilities", volatilities),
        ):
            if not np.all(np.isfinite(array)):
                raise MapperError(f"{name} contains non-finite values")
            array.setflags(write=False)
        object.__setattr__(self, "correlations", correlations)
        object.__setattr__(self, "distances", distances)
        object.__setattr__(self, "volatilities", volatilities)
        object.__setattr__(
            self,
            "intervals",
            tuple(
                interval
                if isinstance(interval, MapperInterval)
                else MapperInterval(float(interval[0]), float(interval[1]), index)
                for index, interval in enumerate(self.intervals)
            ),
        )
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "threshold", _coerce_threshold(self.threshold))
        object.__setattr__(self, "annualization", _coerce_annualization(self.annualization))
        object.__setattr__(self, "labels", tuple(str(value) for value in self.labels))
        object.__setattr__(self, "config", self.config)

    # -- window metadata -------------------------------------------------
    @property
    def columns(self) -> tuple[str, ...]:
        return self.window.columns

    @property
    def industry_columns(self) -> tuple[str, ...]:
        return self.window.columns

    @property
    def canonical_columns(self) -> tuple[str, ...]:
        return self.window.columns

    @property
    def industry_labels(self) -> tuple[str, ...]:
        return self.labels

    @property
    def dates(self) -> tuple[str, ...]:
        return self.window.dates

    @property
    def as_of(self) -> str:
        return self.window.as_of

    @property
    def as_of_date(self) -> str:
        return self.window.as_of

    @property
    def start_date(self) -> str:
        return self.window.start_date

    @property
    def end_date(self) -> str:
        return self.window.end_date

    @property
    def window_sessions(self) -> int:
        return self.window.window_sessions

    @property
    def n_sessions(self) -> int:
        return self.window.window_sessions

    @property
    def config_hash(self) -> str:
        return self.config.config_hash()

    # -- matrix aliases --------------------------------------------------
    @property
    def correlation_matrix(self) -> np.ndarray:
        return self.correlations

    @property
    def corr(self) -> np.ndarray:
        return self.correlations

    @property
    def pearson_correlations(self) -> np.ndarray:
        return self.correlations

    @property
    def distance_matrix(self) -> np.ndarray:
        return self.distances

    @property
    def correlation_distances(self) -> np.ndarray:
        return self.distances

    @property
    def correlation_distance_matrix(self) -> np.ndarray:
        return self.distances

    @property
    def distances_clipped(self) -> np.ndarray:
        return self.distances

    @property
    def cluster_threshold(self) -> float:
        return self.threshold

    @property
    def distance_threshold(self) -> float:
        return self.threshold

    @property
    def lens(self) -> np.ndarray:
        return self.volatilities

    @property
    def lens_values(self) -> np.ndarray:
        return self.volatilities

    @property
    def annualized_volatilities(self) -> np.ndarray:
        return self.volatilities

    @property
    def annualised_volatilities(self) -> np.ndarray:
        return self.volatilities

    @property
    def volatility(self) -> np.ndarray:
        return self.volatilities

    @property
    def cover(self) -> tuple[MapperInterval, ...]:
        return self.intervals

    @property
    def lens_intervals(self) -> tuple[MapperInterval, ...]:
        return self.intervals

    @property
    def interval_cover(self) -> tuple[MapperInterval, ...]:
        return self.intervals

    @property
    def interval_bounds(self) -> tuple[tuple[float, float], ...]:
        return tuple(interval.bounds for interval in self.intervals)

    # -- graph statistics ------------------------------------------------
    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def n_nodes(self) -> int:
        return self.node_count

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def n_edges(self) -> int:
        return self.edge_count

    @property
    def density(self) -> float:
        count = self.node_count
        if count < 2:
            return 0.0
        return (2.0 * self.edge_count) / (count * (count - 1))

    @property
    def largest_component_size(self) -> int:
        count = self.node_count
        if count == 0:
            return 0
        positions = {node.id: index for index, node in enumerate(self.nodes)}
        adjacency: list[list[int]] = [[] for _ in range(count)]
        for edge in self.edges:
            source = positions.get(edge.source, edge.source_index)
            target = positions.get(edge.target, edge.target_index)
            if source == target or not (0 <= source < count and 0 <= target < count):
                continue
            adjacency[source].append(target)
            adjacency[target].append(source)
        seen = [False] * count
        largest = 0
        for start in range(count):
            if seen[start]:
                continue
            stack = [start]
            seen[start] = True
            size = 0
            while stack:
                current = stack.pop()
                size += 1
                for neighbour in adjacency[current]:
                    if not seen[neighbour]:
                        seen[neighbour] = True
                        stack.append(neighbour)
            largest = max(largest, size)
        return largest

    @property
    def largest_component_fraction(self) -> float:
        if not self.nodes:
            return 0.0
        return self.largest_component_size / float(self.node_count)

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes)

    @property
    def positions(self) -> dict[str, tuple[float, float]]:
        return {node.id: node.position for node in self.nodes}

    @property
    def circular_positions(self) -> dict[str, tuple[float, float]]:
        return self.positions

    @property
    def adjacency(self) -> dict[str, tuple[str, ...]]:
        neighbours: dict[str, list[str]] = {node.id: [] for node in self.nodes}
        for edge in self.edges:
            neighbours[edge.source].append(edge.target)
            neighbours[edge.target].append(edge.source)
        return {node_id: tuple(sorted(values)) for node_id, values in neighbours.items()}

    @property
    def member_count(self) -> int:
        """Number of distinct industries represented by the nodes."""

        return len({index for node in self.nodes for index in node.member_indices})

    @property
    def member_correlation_pairs(
        self,
    ) -> tuple[tuple[str, str, float], ...]:
        pairs: list[tuple[str, str, float]] = []
        for left in range(len(self.labels)):
            for right in range(left + 1, len(self.labels)):
                pairs.append(
                    (
                        self.labels[left],
                        self.labels[right],
                        float(self.correlations[left, right]),
                    )
                )
        return tuple(pairs)

    @property
    def correlation_pairs(self) -> tuple[tuple[str, str, float], ...]:
        return self.member_correlation_pairs

    @property
    def member_correlations(self) -> tuple[tuple[str, str, float], ...]:
        return self.member_correlation_pairs

    @property
    def member_correlation_values(self) -> tuple[float, ...]:
        return tuple(sorted(pair[2] for pair in self.member_correlation_pairs))

    @property
    def sorted_member_correlations(self) -> tuple[float, ...]:
        return self.member_correlation_values

    def _member_correlation_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "industry_a": left,
                "industry_b": right,
                "left": left,
                "right": right,
                "correlation": correlation,
            }
            for left, right, correlation in self.member_correlation_pairs
        ]

    # -- serialisation ---------------------------------------------------
    def to_payload(self) -> _PayloadDict:
        return _PayloadDict(
            {
                "as_of": self.as_of,
                "window_sessions": self.window_sessions,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "dates": list(self.dates),
                "columns": list(self.columns),
                "labels": list(self.labels),
                "industry_labels": list(self.industry_labels),
                "threshold": float(self.threshold),
                "annualization": float(self.annualization),
                "correlations": [[float(value) for value in row] for row in self.correlations],
                "correlation_matrix": [
                    [float(value) for value in row] for row in self.correlations
                ],
                "distances": [[float(value) for value in row] for row in self.distances],
                "distance_matrix": [[float(value) for value in row] for row in self.distances],
                "correlation_distances": [
                    [float(value) for value in row] for row in self.distances
                ],
                "clipped_correlation_distances": [
                    [float(value) for value in row] for row in self.distances
                ],
                "volatilities": [float(value) for value in self.volatilities],
                "annualized_volatility": [float(value) for value in self.volatilities],
                "annualized_volatilities": [float(value) for value in self.volatilities],
                "sample_volatility": [float(value) for value in self.volatilities],
                "lens": [float(value) for value in self.volatilities],
                "lens_values": [float(value) for value in self.volatilities],
                "intervals": [
                    {
                        **interval.to_payload(),
                        "members": [
                            self.labels[index]
                            for index, value in enumerate(self.volatilities)
                            if interval.contains(float(value))
                        ],
                    }
                    for interval in self.intervals
                ],
                "interval_bounds": [
                    [interval.lower, interval.upper] for interval in self.intervals
                ],
                "cover": [[interval.lower, interval.upper] for interval in self.intervals],
                "cover_intervals": [
                    [interval.lower, interval.upper] for interval in self.intervals
                ],
                "nodes": [node.to_payload() for node in self.nodes],
                "node_ids": [node.id for node in self.nodes],
                "edges": [edge.to_payload() for edge in self.edges],
                "node_count": self.node_count,
                "edge_count": self.edge_count,
                "density": self.density,
                "largest_component_size": self.largest_component_size,
                "largest_component_fraction": self.largest_component_fraction,
                "member_correlations": self._member_correlation_payload(),
                "correlation_pairs": self._member_correlation_payload(),
                "member_correlation_values": list(self.member_correlation_values),
                "config": self.config.to_dict(),
                "config_hash": self.config.config_hash(),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return dict(self.to_payload())

    def to_dict(self) -> dict[str, Any]:
        return self.as_dict()

    @property
    def payload(self) -> _PayloadDict:
        return self.to_payload()

    def as_payload(self) -> dict[str, Any]:
        return self.as_dict()

    @property
    def payload_dict(self) -> _PayloadDict:
        return self.to_payload()

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, allow_nan=False)

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(type(self), key):
            return getattr(self, key)
        return self.to_payload().get(key, default)

    def __getitem__(self, key: str) -> Any:
        if hasattr(type(self), key):
            return getattr(self, key)
        payload = self.to_payload()
        if key in payload:
            return payload[key]
        raise KeyError(key)

    def __len__(self) -> int:
        return self.node_count

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MapperGraph):
            return NotImplemented
        return (
            self.window == other.window
            and np.array_equal(self.correlations, other.correlations)
            and np.array_equal(self.distances, other.distances)
            and np.array_equal(self.volatilities, other.volatilities)
            and self.intervals == other.intervals
            and self.nodes == other.nodes
            and self.edges == other.edges
            and self.threshold == other.threshold
            and self.annualization == other.annualization
            and self.config == other.config
            and self.labels == other.labels
        )

    __hash__ = None  # type: ignore[assignment]


# Friendly aliases for the result type.
MapperGraphResult = MapperGraph
IndustryMapper = MapperGraph
IndustryMapperGraph = MapperGraph
MapperResult = MapperGraph
MapperOutput = MapperGraph
IndustryMapperResult = MapperGraph
MapperGraphNode = MapperNode
MapperGraphEdge = MapperEdge
Node = MapperNode
Edge = MapperEdge


def _validate_canonical_window(window: IndustryWindow) -> IndustryWindow:
    """Enforce the shared 60-session canonical contract on a selected window."""

    if not isinstance(window, IndustryWindow):
        raise MapperError("selected industry window must be an IndustryWindow")
    if tuple(window.columns) != INDUSTRY_COLUMNS:
        raise MapperError(
            "selected industry window must use the canonical industry columns: "
            f"{', '.join(INDUSTRY_COLUMNS)}"
        )
    expected_shape = (WINDOW_SESSIONS, len(INDUSTRY_COLUMNS))
    if window.values.shape != expected_shape:
        raise MapperError(
            f"Mapper requires a {WINDOW_SESSIONS} x {len(INDUSTRY_COLUMNS)} industry window, "
            f"got {window.values.shape}"
        )
    if window.window_sessions != WINDOW_SESSIONS or len(window.dates) != WINDOW_SESSIONS:
        raise MapperError(
            f"Mapper requires exactly {WINDOW_SESSIONS} sessions, got "
            f"window_sessions={window.window_sessions} and {len(window.dates)} dates"
        )
    if tuple(window.labels) != INDUSTRY_LABELS:
        raise MapperError(
            "selected industry window labels must match the canonical industry labels: "
            f"{', '.join(INDUSTRY_LABELS)}"
        )
    return window


def compute_mapper_graph(rows: Any, as_of: Any = None) -> MapperGraph:
    """Build the 60-session correlation-distance Mapper graph for ``rows``.

    ``rows`` is the sequence of ``industries_daily`` observations accepted by
    :func:`topomarket.analysis.industries.select_industry_window`.  Window
    selection and canonical industry validation are shared with the industry
    cloud task; no caller-supplied window length, alternative configuration or
    preselected cloud can change the required 60-session contract.
    """

    try:
        window = select_industry_window(rows, as_of=as_of)
    except IndustryAnalysisError as error:
        if isinstance(error, MapperError):
            raise
        raise MapperError(str(error)) from error
    _validate_canonical_window(window)

    correlations = pearson_correlations(window.values, columns=window.labels)
    distances = np.asarray(correlation_distances(correlations), dtype=float)
    volatilities = np.asarray(annualized_volatility(window.values), dtype=float)
    intervals = mapper_intervals(volatilities)
    nodes, edges = _assemble_nodes(
        window,
        correlations,
        distances,
        volatilities,
        intervals,
        DEFAULT_THRESHOLD,
    )
    return MapperGraph(
        window=window,
        correlations=correlations,
        distances=distances,
        volatilities=volatilities,
        intervals=intervals,
        nodes=nodes,
        edges=edges,
        threshold=DEFAULT_THRESHOLD,
        annualization=ANNUALIZATION,
        config=DEFAULT_CONFIG,
        labels=window.labels,
    )


def mapper_payload(graph: MapperGraph) -> dict[str, Any]:
    """Return the JSON-serialisable payload for a computed Mapper graph."""

    if not isinstance(graph, MapperGraph):
        raise MapperError("mapper_payload expects a MapperGraph")
    return graph.to_payload()


# Common alternative spellings retained for callers that use the longer name.
build_mapper = compute_mapper_graph
build_mapper_graph = compute_mapper_graph
build_industry_mapper = compute_mapper_graph
build_industry_mapper_graph = compute_mapper_graph
compute_mapper = compute_mapper_graph
compute_industry_mapper = compute_mapper_graph
mapper_graph = compute_mapper_graph
industry_mapper = compute_mapper_graph
industry_mapper_graph = compute_mapper_graph
make_mapper = compute_mapper_graph
construct_mapper = compute_mapper_graph
construct_mapper_graph = compute_mapper_graph
mapper = compute_mapper_graph
build_correlation_mapper = compute_mapper_graph
correlation_mapper = compute_mapper_graph
build_correlation_distance_mapper = compute_mapper_graph
build_correlation_distance_graph = compute_mapper_graph
build_graph = compute_mapper_graph
compute_graph = compute_mapper_graph
construct_graph = compute_mapper_graph

__all__ = [
    "ANNUALISATION",
    "ANNUALIZATION",
    "COVER_INTERVALS",
    "DEFAULT_INTERVALS",
    "DEFAULT_N_INTERVALS",
    "DEFAULT_THRESHOLD",
    "DISTANCE_THRESHOLD",
    "INTERVAL_COUNT",
    "INDUSTRY_COLUMNS",
    "INDUSTRY_LABELS",
    "MAPPER_THRESHOLD",
    "MapperAnalysisError",
    "MapperEdge",
    "MapperError",
    "MapperGraph",
    "MapperGraphEdge",
    "MapperGraphError",
    "MapperGraphNode",
    "MapperGraphResult",
    "MapperInterval",
    "MapperNode",
    "MapperOutput",
    "MapperResult",
    "N_INTERVALS",
    "NOT_APPLICABLE",
    "Node",
    "PERIODS_PER_YEAR",
    "THRESHOLD",
    "TRADING_DAYS",
    "WINDOW_SESSIONS",
    "Edge",
    "IndustryMapper",
    "IndustryMapperError",
    "IndustryMapperGraph",
    "IndustryMapperResult",
    "annualised_volatility",
    "annualised_volatilities",
    "annualized_sample_volatility",
    "annualized_sample_volatilities",
    "annualized_volatility",
    "annualized_volatilities",
    "annualized_std",
    "build_correlation_distance_graph",
    "build_correlation_distance_mapper",
    "build_correlation_mapper",
    "build_graph",
    "build_industry_mapper",
    "build_industry_mapper_graph",
    "build_intervals",
    "build_mapper",
    "build_mapper_graph",
    "clipped_correlation_distance",
    "clipped_correlation_distances",
    "cluster_components",
    "components",
    "compute_correlations",
    "compute_distances",
    "compute_graph",
    "compute_intervals",
    "compute_industry_mapper",
    "compute_mapper",
    "compute_mapper_graph",
    "compute_volatility",
    "connected_components",
    "construct_graph",
    "construct_mapper",
    "construct_mapper_graph",
    "corr",
    "correlation_distance",
    "correlation_distance_matrix",
    "correlation_distances",
    "correlation_matrix",
    "correlation_mapper",
    "cover_intervals",
    "distance_components",
    "distance_matrix",
    "inclusive_intervals",
    "interval_cover",
    "industry_mapper",
    "industry_mapper_graph",
    "intervals_for_lens",
    "lens_intervals",
    "make_mapper",
    "mapper",
    "mapper_graph",
    "mapper_intervals",
    "mapper_payload",
    "overlapping_intervals",
    "pairwise_correlation_distances",
    "pairwise_correlations",
    "pearson",
    "pearson_correlation",
    "pearson_correlation_matrix",
    "pearson_correlations",
    "sample_volatility",
    "threshold_components",
    "volatility",
]
