"""Reusable industry windows and cloud analysis for the industry explorer.

The analysis starts from already-loaded ``industries_daily`` rows: this module
never reads files, downloads data or infers an exchange calendar.  A caller
selects a causal as-of window (60 sessions by default), which is validated
against the canonical twelve French industry columns.  The window is then
robustly scaled column by column with the shared topology median/MAD primitive,
projected to two dimensions with a deterministic NumPy SVD, and passed to the
existing full-filtration Vietoris-Rips persistence primitives.

The public surface is deliberately small:

``select_industry_window``
    Shared row validation and 60-session as-of selection (also used by the
    Mapper task).

``build_industry_cloud``
    Window selection, robust scaling, PCA and H0/H1 persistence in one result.

``IndustryWindow`` / ``IndustryCloud``
    Frozen, JSON-serialisable results with readable aliases for downstream UI
    and Mapper consumers.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np

from topomarket.data.schemas import (
    INDUSTRIES_DAILY_COLUMNS,
    INDUSTRY_NAMES,
)
from topomarket.topology.config import DEFAULT_CONFIG, TopologyConfig
from topomarket.topology.errors import ScalingError, ZeroScaleError
from topomarket.topology.persistence import (
    Diagrams,
    Lifetimes,
    finite_lifetimes,
    persistence_diagrams,
)
from topomarket.topology.scaling import MAD_TO_SIGMA, ScaledWindow, robust_scale

#: Number of sessions in the canonical industry window.
WINDOW_SESSIONS = DEFAULT_CONFIG.window_sessions
DEFAULT_WINDOW_SESSIONS = WINDOW_SESSIONS
DEFAULT_WINDOW = WINDOW_SESSIONS
WINDOW_SIZE = WINDOW_SESSIONS
WINDOW_LENGTH = WINDOW_SESSIONS
INDUSTRY_WINDOW_SESSIONS = WINDOW_SESSIONS

#: Prefix that identifies an industry return column in ``industries_daily``.
INDUSTRY_PREFIX = "ind_"

#: The twelve canonical industry return columns, in the table's stable order.
INDUSTRY_COLUMNS: tuple[str, ...] = tuple(
    column for column in INDUSTRIES_DAILY_COLUMNS if column != "date"
)
CANONICAL_COLUMNS = INDUSTRY_COLUMNS
CANONICAL_INDUSTRY_COLUMNS = INDUSTRY_COLUMNS
WINDOW_COLUMNS: tuple[str, ...] = ("date", *INDUSTRY_COLUMNS)

#: Human-readable industry names (the labels shown by consumers).
INDUSTRY_LABELS: tuple[str, ...] = tuple(INDUSTRY_NAMES)

#: Labels that identify the canonical return columns themselves.
INDUSTRY_COLUMN_LABELS = INDUSTRY_COLUMNS
COLUMN_LABELS = INDUSTRY_COLUMNS

#: Labels for the first two principal components.
PCA_LABELS: tuple[str, ...] = ("PC1", "PC2")
COMPONENT_LABELS = PCA_LABELS


class IndustryAnalysisError(ValueError):
    """Raised when an industry window or cloud cannot be analysed.

    Every invalid input is reported as this single error type with a message
    that names the offending date, column or row, so callers (including the
    Mapper task) can show a actionable reason instead of a raw NumPy error.
    """


# Friendly aliases used by callers/tests.
IndustryError = IndustryAnalysisError
IndustryWindowError = IndustryAnalysisError
IndustryCloudError = IndustryAnalysisError
InvalidIndustryWindowError = IndustryAnalysisError


class _PayloadDict(dict[str, Any]):
    """A payload mapping that can also be called like ``payload()``."""

    def __call__(self) -> dict[str, Any]:
        return dict(self)


def _coerce_config(config: TopologyConfig | Mapping[str, Any] | None) -> TopologyConfig:
    if config is None:
        return DEFAULT_CONFIG
    if isinstance(config, TopologyConfig):
        return config
    if isinstance(config, Mapping):
        try:
            return TopologyConfig.from_dict(config)
        except ValueError as error:
            raise IndustryAnalysisError(f"invalid topology configuration: {error}") from error
    raise IndustryAnalysisError(
        f"config must be a TopologyConfig or mapping, got {type(config).__name__}"
    )


def _coerce_window_sessions(value: Any, default: int) -> int:
    if value is None:
        return int(default)
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise IndustryAnalysisError(f"window_sessions must be an integer >= 1, got {value!r}")
    sessions = int(value)
    if sessions < 1:
        raise IndustryAnalysisError(f"window_sessions must be an integer >= 1, got {value!r}")
    return sessions


def _pop_alias(kwargs: dict[str, Any], names: Sequence[str], current: Any) -> Any:
    found = [(name, kwargs.pop(name)) for name in names if name in kwargs]
    if not found:
        return current
    if len(found) > 1:
        joined = ", ".join(name for name, _ in found)
        raise IndustryAnalysisError(f"parameter was provided more than once via {joined}")
    if current is not None:
        raise IndustryAnalysisError(f"{found[0][0]} was provided more than once")
    return found[0][1]


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    if hasattr(row, "_asdict"):
        try:
            return row._asdict().get(key, default)
        except (AttributeError, TypeError):
            pass
    return getattr(row, key, default)


def _row_keys(row: Any) -> tuple[str, ...]:
    if isinstance(row, Mapping):
        return tuple(str(key) for key in row)
    if hasattr(row, "_fields"):
        return tuple(str(key) for key in row._fields)
    try:
        return tuple(str(key) for key in vars(row))
    except TypeError:
        return tuple(name for name in dir(row) if not name.startswith("_"))


def _materialise_rows(rows: Any) -> list[Any]:
    if rows is None:
        raise IndustryAnalysisError("industry rows are required")
    if isinstance(rows, (str, bytes)):
        raise IndustryAnalysisError("industry rows must be a sequence of observations, not text")
    if isinstance(rows, Mapping):
        # A column-oriented mapping is a convenient read-only input form.
        if rows and "date" in rows and not isinstance(rows["date"], (str, bytes, date, datetime)):
            columns = list(rows)
            lengths = {len(rows[column]) for column in columns}
            if len(lengths) > 1:
                raise IndustryAnalysisError("column-oriented industry rows have unequal lengths")
            return [
                {column: rows[column][index] for column in columns}
                for index in range(next(iter(lengths), 0))
            ]
        return [rows]
    try:
        return list(rows)
    except TypeError as error:
        raise IndustryAnalysisError("industry rows must be an iterable of observations") from error


def _parse_date(value: Any, *, row_number: int | None = None) -> date:
    context = f" in row {row_number}" if row_number is not None else ""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise IndustryAnalysisError(f"observation is missing a date{context}")
    if isinstance(value, bool):
        raise IndustryAnalysisError(f"invalid observation date{context}: {value!r}")
    text = str(value).strip()
    if not text:
        raise IndustryAnalysisError(f"observation is missing a date{context}")
    if "T" in text or " " in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise IndustryAnalysisError(f"invalid observation date{context}: {value!r}")


def _validate_columns(
    observed: set[str],
    expected: tuple[str, ...],
) -> None:
    prefix = INDUSTRY_PREFIX.lower()
    unknown = sorted(
        key for key in observed if key.lower().startswith(prefix) and key not in expected
    )
    if unknown:
        raise IndustryAnalysisError(
            "unknown industry column(s): "
            f"{', '.join(unknown)}; expected canonical columns: {', '.join(expected)}"
        )
    missing = [column for column in expected if column not in observed]
    if missing:
        raise IndustryAnalysisError(
            f"missing industry column(s): {', '.join(missing)}; "
            f"expected canonical columns: {', '.join(expected)}"
        )


def _normalise_rows(
    rows: Any,
    expected: tuple[str, ...],
) -> list[tuple[date, Any]]:
    materialised = _materialise_rows(rows)
    if not materialised:
        raise IndustryAnalysisError(
            f"industry window is too short: requires at least {WINDOW_SESSIONS} rows, got 0"
        )

    observed: set[str] = set()
    parsed: list[tuple[date, Any]] = []
    seen: dict[date, int] = {}
    for index, row in enumerate(materialised):
        keys = _row_keys(row)
        observed.update(keys)
        raw_date = _row_get(row, "date")
        observation_date = _parse_date(raw_date, row_number=index)
        if observation_date in seen:
            raise IndustryAnalysisError(
                "duplicate observation date: "
                f"{observation_date.isoformat()} (rows {seen[observation_date]} and {index})"
            )
        seen[observation_date] = index
        parsed.append((observation_date, row))

    _validate_columns(observed, expected)
    parsed.sort(key=lambda item: item[0])
    return parsed


def _window_value(row: Any, column: str, observation_date: date) -> float:
    raw = _row_get(row, column)
    if raw is None:
        raise IndustryAnalysisError(
            f"missing value for industry column {column!r} on {observation_date.isoformat()}"
        )
    if isinstance(raw, str) and not raw.strip():
        raise IndustryAnalysisError(
            f"missing value for industry column {column!r} on {observation_date.isoformat()}"
        )
    if isinstance(raw, bool):
        raise IndustryAnalysisError(
            f"non-numeric value for industry column {column!r} on {observation_date.isoformat()}: "
            f"{raw!r}"
        )
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise IndustryAnalysisError(
            f"non-numeric value for industry column {column!r} on "
            f"{observation_date.isoformat()}: {raw!r}"
        ) from error
    if not math.isfinite(value):
        raise IndustryAnalysisError(
            f"non-finite value for industry column {column!r} on "
            f"{observation_date.isoformat()}: {raw!r}"
        )
    return value


@dataclass(frozen=True)
class IndustryWindow:
    """A validated, ascending industry window ending at one as-of date."""

    columns: tuple[str, ...]
    dates: tuple[str, ...]
    values: np.ndarray
    as_of: str
    window_sessions: int = WINDOW_SESSIONS
    labels: tuple[str, ...] = field(default_factory=lambda: INDUSTRY_LABELS)

    def __post_init__(self) -> None:
        columns = tuple(str(column) for column in self.columns)
        dates = tuple(str(value) for value in self.dates)
        values = np.array(self.values, dtype=float, copy=True)
        if values.ndim != 2:
            raise IndustryAnalysisError(
                f"industry window values must be two-dimensional, got shape {values.shape}"
            )
        if values.shape != (len(dates), len(columns)):
            raise IndustryAnalysisError(
                "industry window values shape does not match dates and columns: "
                f"{values.shape} != ({len(dates)}, {len(columns)})"
            )
        values.setflags(write=False)
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "dates", dates)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "as_of", str(self.as_of))
        object.__setattr__(self, "window_sessions", int(self.window_sessions))
        object.__setattr__(self, "labels", tuple(str(label) for label in self.labels))

    # -- shape and metadata aliases -------------------------------------
    @property
    def industry_columns(self) -> tuple[str, ...]:
        return self.columns

    @property
    def canonical_columns(self) -> tuple[str, ...]:
        return self.columns

    @property
    def column_labels(self) -> tuple[str, ...]:
        return self.labels

    @property
    def date_labels(self) -> tuple[str, ...]:
        return self.dates

    @property
    def matrix(self) -> np.ndarray:
        return self.values

    @property
    def data(self) -> np.ndarray:
        return self.values

    @property
    def returns(self) -> np.ndarray:
        return self.values

    @property
    def observations(self) -> np.ndarray:
        return self.values

    @property
    def rows(self) -> np.ndarray:
        return self.values

    @property
    def n_rows(self) -> int:
        return int(self.values.shape[0])

    @property
    def n_sessions(self) -> int:
        return self.n_rows

    @property
    def n_industries(self) -> int:
        return int(self.values.shape[1])

    @property
    def row_count(self) -> int:
        return self.n_rows

    @property
    def session_count(self) -> int:
        return self.n_rows

    @property
    def industry_count(self) -> int:
        return self.n_industries

    @property
    def column_count(self) -> int:
        return self.n_industries

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.values.shape[0]), int(self.values.shape[1]))

    @property
    def start_date(self) -> str:
        return self.dates[0]

    @property
    def end_date(self) -> str:
        return self.dates[-1]

    @property
    def first_date(self) -> str:
        return self.start_date

    @property
    def last_date(self) -> str:
        return self.end_date

    @property
    def as_of_date(self) -> str:
        return self.as_of

    def __len__(self) -> int:
        return self.n_rows

    def to_payload(self) -> _PayloadDict:
        return _PayloadDict(
            {
                "as_of": self.as_of,
                "window_sessions": self.window_sessions,
                "columns": list(self.columns),
                "labels": list(self.labels),
                "dates": list(self.dates),
                "values": [[float(value) for value in row] for row in self.values],
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return dict(self.to_payload())

    def to_dict(self) -> dict[str, Any]:
        return self.as_dict()

    @property
    def payload(self) -> _PayloadDict:
        return self.to_payload()

    def __getitem__(self, key: str) -> Any:
        if hasattr(type(self), key):
            return getattr(self, key)
        payload = self.to_payload()
        if key in payload:
            return payload[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IndustryWindow):
            return NotImplemented
        return (
            self.columns == other.columns
            and self.dates == other.dates
            and self.as_of == other.as_of
            and self.window_sessions == other.window_sessions
            and np.array_equal(self.values, other.values)
        )

    __hash__ = None  # type: ignore[assignment]


def _resolve_expected_columns(value: Any) -> tuple[str, ...]:
    """Return the canonical columns, rejecting any attempt to replace them.

    A caller may pass the canonical column names explicitly (in any order) for
    readability, but the override can never add an unknown ``ind_`` column or
    omit a canonical one.  Validation always uses the canonical set so a
    caller cannot widen or narrow what the Mapper contract accepts.
    """

    if value is None:
        return INDUSTRY_COLUMNS
    if isinstance(value, str):
        raise IndustryAnalysisError("columns must be a sequence of column names, not text")
    try:
        columns = tuple(str(column) for column in value)
    except TypeError as error:
        raise IndustryAnalysisError("columns must be a sequence of column names") from error
    if not columns:
        raise IndustryAnalysisError("columns must contain at least one industry column")

    canonical = INDUSTRY_COLUMNS
    if len(columns) != len(canonical) or set(columns) != set(canonical):
        unknown = sorted(column for column in columns if column not in canonical)
        missing = [column for column in canonical if column not in columns]
        details: list[str] = []
        if unknown:
            details.append(f"unknown industry column(s): {', '.join(unknown)}")
        if missing:
            details.append(f"missing industry column(s): {', '.join(missing)}")
        if not details:
            details.append("duplicate or non-canonical column names")
        raise IndustryAnalysisError(
            "columns override must contain exactly the canonical industry columns; "
            + "; ".join(details)
        )
    return canonical


def select_industry_window(
    rows: Any = None,
    as_of: Any = None,
    window_sessions: int | None = None,
    **kwargs: Any,
) -> IndustryWindow:
    """Select and validate the trailing industry window through ``as_of``.

    Rows are validated for duplicate dates, canonical industry columns, unknown
    ``ind_``-prefixed columns and missing/non-finite window values.  Unrelated
    row fields (for example ``vix_close``) are ignored.  Dates are sorted and
    returned as ascending ISO-8601 strings.  When ``as_of`` is omitted the most
    recent observation is used; an explicit as-of date must be present in the
    rows.
    """

    if rows is None and "rows" in kwargs:
        rows = kwargs.pop("rows")
    as_of = _pop_alias(
        kwargs,
        ("as_of_date", "asof", "end_date", "date", "session", "as_of_session"),
        as_of,
    )
    window_sessions = _pop_alias(
        kwargs,
        ("sessions", "window", "window_size", "window_length", "n_sessions", "size"),
        window_sessions,
    )
    expected = _resolve_expected_columns(
        _pop_alias(kwargs, ("columns", "industry_columns", "expected_columns"), None)
    )
    config = _pop_alias(kwargs, ("config", "topology_config", "topology"), None)
    if kwargs:
        names = ", ".join(sorted(str(key) for key in kwargs))
        raise IndustryAnalysisError(f"unexpected industry window argument(s): {names}")

    config_value = _coerce_config(config)
    sessions = _coerce_window_sessions(window_sessions, config_value.window_sessions)
    parsed = _normalise_rows(rows, expected)

    available_dates = [observation_date for observation_date, _row in parsed]
    if as_of is None:
        selected_as_of = available_dates[-1]
    else:
        selected_as_of = _parse_date(as_of)
        if selected_as_of not in available_dates:
            raise IndustryAnalysisError(
                f"as-of date {selected_as_of.isoformat()} is not present in the industry rows"
            )

    eligible = [
        (observation_date, row)
        for observation_date, row in parsed
        if observation_date <= selected_as_of
    ]
    if len(eligible) < sessions:
        raise IndustryAnalysisError(
            "industry window is too short: requires at least "
            f"{sessions} rows through {selected_as_of.isoformat()}, got {len(eligible)}"
        )
    selected = eligible[-sessions:]

    values = np.empty((len(selected), len(expected)), dtype=float)
    for row_index, (observation_date, row) in enumerate(selected):
        for column_index, column in enumerate(expected):
            values[row_index, column_index] = _window_value(row, column, observation_date)

    return IndustryWindow(
        columns=expected,
        dates=tuple(observation_date.isoformat() for observation_date, _row in selected),
        values=values,
        as_of=selected_as_of.isoformat(),
        window_sessions=sessions,
        labels=INDUSTRY_LABELS if expected == INDUSTRY_COLUMNS else expected,
    )


def _principal_components(
    matrix: np.ndarray,
    n_components: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return deterministic PCA scores, variances, ratios, loadings and S."""

    samples = matrix.shape[0]
    centered = matrix - np.mean(matrix, axis=0, keepdims=True)
    # ``full_matrices=False`` keeps the decomposition deterministic even for a
    # rank-deficient window; only the leading right singular vectors are used.
    left, singular_values, loadings = np.linalg.svd(centered, full_matrices=False)

    # A singular vector is only defined up to sign.  Anchor each component by
    # making its largest-magnitude loading positive; ties fall back to the
    # first such loading, which is stable across runs and BLAS implementations.
    for component in range(loadings.shape[0]):
        row = loadings[component]
        if row.size == 0:
            continue
        pivot = int(np.argmax(np.abs(row)))
        if row[pivot] < 0.0:
            left[:, component] *= -1.0
            loadings[component, :] *= -1.0

    scores = left[:, :n_components] * singular_values[:n_components]
    variance = (singular_values[:n_components] ** 2) / float(max(samples - 1, 1))
    total = float(np.sum(singular_values**2))
    if total > 0.0:
        ratio = (singular_values[:n_components] ** 2) / total
    else:  # pragma: no cover - robust scaling rejects a zero cloud first
        ratio = np.zeros(n_components, dtype=float)
    return scores, variance, ratio, loadings[:n_components], singular_values


class PCAProjection(np.ndarray):
    """A two-dimensional PCA score matrix carrying its own explained variance.

    It is a real ``numpy.ndarray`` (so shape checks, slicing and JSON export
    behave normally) with descriptive attributes for consumers that prefer an
    object over a bare matrix.
    """

    explained_variance: np.ndarray
    explained_variance_ratio: np.ndarray
    labels: tuple[str, ...]
    components: np.ndarray

    def __new__(
        cls,
        values: Any,
        *,
        explained_variance: Any = None,
        explained_variance_ratio: Any = None,
        labels: Sequence[str] = PCA_LABELS,
        components: Any = None,
    ) -> PCAProjection:
        obj = np.array(values, dtype=float, copy=True).view(cls)
        obj.explained_variance = np.asarray(explained_variance, dtype=float)
        obj.explained_variance_ratio = np.asarray(explained_variance_ratio, dtype=float)
        obj.labels = tuple(str(label) for label in labels)
        obj.components = np.asarray(components, dtype=float)
        obj.setflags(write=False)
        return obj

    def __array_finalize__(self, obj: Any) -> None:
        if obj is None:
            return
        self.explained_variance = getattr(obj, "explained_variance", np.empty(0))
        self.explained_variance_ratio = getattr(obj, "explained_variance_ratio", np.empty(0))
        self.labels = getattr(obj, "labels", PCA_LABELS)
        self.components = getattr(obj, "components", np.empty((0, 0)))

    @property
    def scores(self) -> np.ndarray:
        return np.asarray(self)

    @property
    def projection(self) -> np.ndarray:
        return np.asarray(self)

    @property
    def n_components(self) -> int:
        return int(self.shape[1])


@dataclass(frozen=True)
class IndustryCloud:
    """Robustly scaled 60x12 cloud, its two-dimensional PCA and persistence."""

    window: IndustryWindow
    scaled_cloud: np.ndarray
    pca: np.ndarray
    explained_variance: np.ndarray
    explained_variance_ratio: np.ndarray
    components: np.ndarray
    singular_values: np.ndarray
    diagrams: Diagrams = field(default_factory=lambda: Diagrams(()))
    lifetimes: Lifetimes = field(default_factory=lambda: Lifetimes(()))
    min_interval: float = DEFAULT_CONFIG.min_interval
    labels: tuple[str, ...] = PCA_LABELS
    config: TopologyConfig = DEFAULT_CONFIG

    def __post_init__(self) -> None:
        def frozen_array(values: Any, name: str) -> np.ndarray:
            array = np.array(values, dtype=float, copy=True)
            array.setflags(write=False)
            if not np.all(np.isfinite(array)):
                raise IndustryAnalysisError(f"{name} contains non-finite values")
            return array

        scaled = frozen_array(self.scaled_cloud, "scaled cloud")
        pca = frozen_array(self.pca, "PCA projection")
        variance = frozen_array(self.explained_variance, "explained variance")
        ratio = frozen_array(self.explained_variance_ratio, "explained variance ratio")
        components = frozen_array(self.components, "PCA components")
        singular = np.array(self.singular_values, dtype=float, copy=True)
        singular.setflags(write=False)
        if scaled.ndim != 2:
            raise IndustryAnalysisError(
                f"scaled industry cloud must be two-dimensional, got shape {scaled.shape}"
            )
        if pca.ndim != 2 or pca.shape[0] != scaled.shape[0]:
            raise IndustryAnalysisError(
                f"PCA projection must have one row per session, got {pca.shape}"
            )
        if variance.ndim != 1 or ratio.ndim != 1:
            raise IndustryAnalysisError("explained variance must be one-dimensional")
        pca_projection = PCAProjection(
            pca,
            explained_variance=variance,
            explained_variance_ratio=ratio,
            labels=self.labels,
            components=components,
        )
        object.__setattr__(self, "scaled_cloud", scaled)
        object.__setattr__(self, "pca", pca_projection)
        object.__setattr__(self, "explained_variance", variance)
        object.__setattr__(self, "explained_variance_ratio", ratio)
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "singular_values", singular)
        object.__setattr__(self, "diagrams", Diagrams(tuple(self.diagrams or ())))
        object.__setattr__(self, "lifetimes", Lifetimes(tuple(self.lifetimes or ())))
        object.__setattr__(self, "min_interval", float(self.min_interval))
        object.__setattr__(self, "labels", tuple(str(label) for label in self.labels))
        object.__setattr__(self, "config", _coerce_config(self.config))

    # -- cloud aliases ---------------------------------------------------
    @property
    def scaled_window(self) -> ScaledWindow:
        window = ScaledWindow(self.scaled_cloud, self.medians, self.mads, self.scales)
        window.setflags(write=False)
        return window

    @property
    def cloud(self) -> ScaledWindow:
        return self.scaled_window

    @property
    def scaled(self) -> ScaledWindow:
        return self.scaled_window

    @property
    def points(self) -> np.ndarray:
        return self.scaled_cloud

    @property
    def point_cloud(self) -> np.ndarray:
        return self.scaled_cloud

    @property
    def matrix(self) -> np.ndarray:
        return self.scaled_cloud

    @property
    def data(self) -> np.ndarray:
        return self.scaled_cloud

    @property
    def values(self) -> np.ndarray:
        return self.scaled_cloud

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.scaled_cloud.shape[0]), int(self.scaled_cloud.shape[1]))

    @property
    def n_rows(self) -> int:
        return int(self.scaled_cloud.shape[0])

    @property
    def n_sessions(self) -> int:
        return self.n_rows

    @property
    def n_industries(self) -> int:
        return int(self.scaled_cloud.shape[1])

    @property
    def row_count(self) -> int:
        return self.n_rows

    @property
    def session_count(self) -> int:
        return self.n_rows

    @property
    def industry_count(self) -> int:
        return self.n_industries

    @property
    def column_count(self) -> int:
        return self.n_industries

    @property
    def pca_shape(self) -> tuple[int, int]:
        return (int(self.pca.shape[0]), int(self.pca.shape[1]))

    # -- metadata delegated to the window --------------------------------
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
    def column_labels(self) -> tuple[str, ...]:
        return self.window.labels

    @property
    def industry_labels(self) -> tuple[str, ...]:
        return self.window.labels

    @property
    def dates(self) -> tuple[str, ...]:
        return self.window.dates

    @property
    def date_labels(self) -> tuple[str, ...]:
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
    def first_date(self) -> str:
        return self.window.first_date

    @property
    def last_date(self) -> str:
        return self.window.last_date

    @property
    def window_dates(self) -> tuple[str, ...]:
        return self.window.dates

    @property
    def window_sessions(self) -> int:
        return self.window.window_sessions

    @property
    def raw_values(self) -> np.ndarray:
        return self.window.values

    # -- PCA aliases -----------------------------------------------------
    @property
    def projection(self) -> np.ndarray:
        return self.pca

    @property
    def pca_scores(self) -> np.ndarray:
        return self.pca

    @property
    def scores(self) -> np.ndarray:
        return self.pca

    @property
    def pca_components(self) -> np.ndarray:
        return self.components

    @property
    def loadings(self) -> np.ndarray:
        return self.components

    @property
    def pca_labels(self) -> tuple[str, ...]:
        return self.labels

    @property
    def component_labels(self) -> tuple[str, ...]:
        return self.labels

    @property
    def explained_variance_labels(self) -> tuple[str, ...]:
        return self.labels

    @property
    def variance(self) -> np.ndarray:
        return self.explained_variance

    @property
    def variance_ratio(self) -> np.ndarray:
        return self.explained_variance_ratio

    @property
    def pca_explained_variance(self) -> np.ndarray:
        return self.explained_variance

    @property
    def pca_explained_variance_ratio(self) -> np.ndarray:
        return self.explained_variance_ratio

    @property
    def cumulative_explained_variance(self) -> np.ndarray:
        return np.cumsum(self.explained_variance_ratio)

    # -- robust scaling metadata ----------------------------------------
    @property
    def medians(self) -> np.ndarray:
        return np.median(self.window.values, axis=0)

    @property
    def median(self) -> np.ndarray:
        return self.medians

    @property
    def mads(self) -> np.ndarray:
        medians = self.medians
        return np.median(np.abs(self.window.values - medians), axis=0)

    @property
    def mad(self) -> np.ndarray:
        return self.mads

    @property
    def scales(self) -> np.ndarray:
        return MAD_TO_SIGMA * self.mads

    @property
    def scale(self) -> np.ndarray:
        return self.scales

    # -- persistence aliases --------------------------------------------
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
    def H0(self) -> np.ndarray:
        return self.h0

    @property
    def H1(self) -> np.ndarray:
        return self.h1

    @property
    def h0_diagram(self) -> np.ndarray:
        return self.h0

    @property
    def h1_diagram(self) -> np.ndarray:
        return self.h1

    @property
    def persistence_diagrams(self) -> Diagrams:
        return self.diagrams

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
    def h1_count(self) -> int:
        return int(np.asarray(self.h1_lifetimes, dtype=float).size)

    @property
    def max_lifetime(self) -> float:
        values = np.asarray(self.h1_lifetimes, dtype=float)
        return float(np.max(values)) if values.size else 0.0

    @property
    def L(self) -> float:
        return self.max_lifetime

    @property
    def persistence(self) -> float:
        return self.max_lifetime

    @property
    def total_persistence(self) -> float:
        values = np.asarray(self.h1_lifetimes, dtype=float)
        return float(np.sum(values)) if values.size else 0.0

    def __len__(self) -> int:
        return self.n_rows

    def _diagram_payload(self, diagram: np.ndarray) -> list[list[float | None]]:
        rows: list[list[float | None]] = []
        for birth, death in np.asarray(diagram, dtype=float):
            rows.append(
                [
                    float(birth) if math.isfinite(float(birth)) else None,
                    float(death) if math.isfinite(float(death)) else None,
                ]
            )
        return rows

    def to_payload(self) -> _PayloadDict:
        return _PayloadDict(
            {
                "as_of": self.as_of,
                "window_sessions": self.window_sessions,
                "columns": list(self.columns),
                "labels": list(self.labels),
                "industry_labels": list(self.industry_labels),
                "dates": list(self.dates),
                "cloud": [[float(value) for value in row] for row in self.scaled_cloud],
                "scaled_cloud": [[float(value) for value in row] for row in self.scaled_cloud],
                "pca": [[float(value) for value in row] for row in self.pca],
                "pca_labels": list(self.pca_labels),
                "explained_variance": [float(value) for value in self.explained_variance],
                "explained_variance_ratio": [
                    float(value) for value in self.explained_variance_ratio
                ],
                "singular_values": [float(value) for value in self.singular_values],
                "pca_components": [[float(value) for value in row] for row in self.components],
                "h0": self._diagram_payload(self.h0),
                "h1": self._diagram_payload(self.h1),
                "h0_lifetimes": [float(value) for value in self.h0_lifetimes],
                "h1_lifetimes": [float(value) for value in self.h1_lifetimes],
                "min_interval": float(self.min_interval),
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

    def __getitem__(self, key: str) -> Any:
        if hasattr(type(self), key):
            return getattr(self, key)
        payload = self.to_payload()
        if key in payload:
            return payload[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IndustryCloud):
            return NotImplemented
        return (
            self.window == other.window
            and np.array_equal(self.scaled_cloud, other.scaled_cloud)
            and np.array_equal(self.pca, other.pca)
            and np.array_equal(self.explained_variance, other.explained_variance)
            and np.array_equal(self.explained_variance_ratio, other.explained_variance_ratio)
            and np.array_equal(self.components, other.components)
            and self.lifetimes == other.lifetimes
            and self.min_interval == other.min_interval
            and self.config == other.config
        )

    __hash__ = None  # type: ignore[assignment]


def build_industry_cloud(
    rows: Any = None,
    as_of: Any = None,
    window_sessions: int | None = None,
    **kwargs: Any,
) -> IndustryCloud:
    """Build the robust industry cloud, PCA and H0/H1 persistence for one as-of window."""

    if rows is None and "rows" in kwargs:
        rows = kwargs.pop("rows")
    n_components = _pop_alias(
        kwargs,
        ("components", "n_components", "pca_components", "dimensions"),
        None,
    )
    config = _pop_alias(kwargs, ("topology_config", "topology", "config"), None)
    config_value = _coerce_config(config)

    window = select_industry_window(
        rows,
        as_of=as_of,
        window_sessions=window_sessions,
        config=config_value,
        **kwargs,
    )
    sessions = window.window_sessions
    if n_components is None:
        n_components = 2
    if isinstance(n_components, bool) or not isinstance(n_components, (int, np.integer)):
        raise IndustryAnalysisError(f"n_components must be an integer >= 1, got {n_components!r}")
    components_count = int(n_components)
    limit = min(window.values.shape)
    if components_count < 1 or components_count > limit:
        raise IndustryAnalysisError(
            f"n_components must be between 1 and {limit}, got {components_count}"
        )

    try:
        scaled = robust_scale(window.values, axis=0)
    except ZeroScaleError as error:
        scaled_values = np.asarray(window.values, dtype=float)
        medians = np.median(scaled_values, axis=0)
        mads = np.median(np.abs(scaled_values - medians), axis=0)
        zero_columns = [
            column for column, mad in zip(window.columns, mads, strict=True) if mad <= 0.0
        ]
        names = ", ".join(zero_columns) if zero_columns else "(unknown)"
        raise IndustryAnalysisError(
            "industry window cannot be robustly scaled: zero median/MAD scale for "
            f"column(s): {names}"
        ) from error
    except ScalingError as error:
        raise IndustryAnalysisError(
            f"industry window cannot be robustly scaled: {error}"
        ) from error

    scaled_values = np.array(scaled, dtype=float, copy=True)
    pca, variance, ratio, loadings, singular_values = _principal_components(
        scaled_values, components_count
    )

    try:
        diagrams = persistence_diagrams(scaled_values, config_value)
        lifetimes = finite_lifetimes(diagrams, config_value.min_interval)
    except Exception as error:
        raise IndustryAnalysisError(f"industry cloud persistence failed: {error}") from error

    labels = PCA_LABELS[:components_count]
    if components_count > len(labels):
        labels = tuple(f"PC{index + 1}" for index in range(components_count))

    resolved_config = config_value
    if sessions != config_value.window_sessions:
        try:
            resolved_config = TopologyConfig.from_dict(
                {**config_value.to_dict(), "window_sessions": sessions}
            )
        except ValueError:
            # A very small custom window can violate the topology config's
            # embedding constraints; the selected window is still valid for
            # the industry cloud itself.
            resolved_config = config_value

    return IndustryCloud(
        window=window,
        scaled_cloud=scaled_values,
        pca=pca,
        explained_variance=variance,
        explained_variance_ratio=ratio,
        components=loadings,
        singular_values=singular_values,
        diagrams=diagrams,
        lifetimes=lifetimes,
        min_interval=config_value.min_interval,
        labels=labels,
        config=resolved_config,
    )


def latest_complete_industry_date(
    rows: Any = None,
    window_sessions: int | None = None,
    **kwargs: Any,
) -> str | None:
    """Return the latest as-of date with a complete trailing industry window.

    ``tda_daily`` is an exact-date inner join, so its newest rows can still
    contain blank industry cells when an upstream source is missing.  Scanning
    backwards for the first complete ``window_sessions`` window keeps the
    default explorer useful without changing the strict explicit-date contract
    of :func:`select_industry_window`.
    """

    if rows is None and "rows" in kwargs:
        rows = kwargs.pop("rows")
    window_sessions = _pop_alias(
        kwargs,
        ("sessions", "window", "window_size", "window_length", "n_sessions", "size"),
        window_sessions,
    )
    expected = _resolve_expected_columns(
        _pop_alias(kwargs, ("columns", "industry_columns", "expected_columns"), None)
    )
    config = _pop_alias(kwargs, ("config", "topology_config", "topology"), None)
    if kwargs:
        names = ", ".join(sorted(str(key) for key in kwargs))
        raise IndustryAnalysisError(f"unexpected industry window argument(s): {names}")

    sessions = _coerce_window_sessions(window_sessions, _coerce_config(config).window_sessions)
    parsed = _normalise_rows(rows, expected)
    if len(parsed) < sessions:
        return None

    for end in range(len(parsed) - 1, sessions - 2, -1):
        window = parsed[end - sessions + 1 : end + 1]
        complete = True
        for observation_date, row in window:
            for column in expected:
                try:
                    _window_value(row, column, observation_date)
                except IndustryAnalysisError:
                    complete = False
                    break
            if not complete:
                break
        if complete:
            return window[-1][0].isoformat()
    return None


def industry_explorer_payload(rows: Any = None, as_of: Any = None) -> dict[str, Any]:
    """Return the combined cloud and Mapper payload for one as-of window.

    The two analysis products are always computed from the exact same validated
    window.  When ``as_of`` is omitted the helper selects the latest complete
    trailing window, matching the ``topomarket industries`` command.
    """

    if as_of is None:
        as_of = latest_complete_industry_date(rows)
        if as_of is None:
            raise IndustryAnalysisError(
                "no complete industry window is available; requires at least "
                f"{WINDOW_SESSIONS} rows with finite values for every industry column"
            )
    cloud = build_industry_cloud(rows, as_of=as_of)
    # Imported lazily so the base industries module does not import the Mapper
    # module (which itself depends on this shared window contract) at load time.
    from .mapper import compute_mapper_graph, mapper_payload

    graph = compute_mapper_graph(rows, as_of=cloud.as_of)
    return {
        "as_of": cloud.as_of,
        "as_of_date": cloud.as_of,
        "start_date": cloud.start_date,
        "end_date": cloud.end_date,
        "window_sessions": cloud.window_sessions,
        "row_count": len(cloud.dates),
        "columns": list(cloud.columns),
        "labels": list(cloud.industry_labels),
        "industry_columns": list(cloud.columns),
        "industry_labels": list(cloud.industry_labels),
        "dates": list(cloud.dates),
        "cloud": cloud.to_payload(),
        "mapper": mapper_payload(graph),
        "node_count": graph.node_count,
        "edge_count": graph.edge_count,
        "interval_count": len(graph.intervals),
    }


# Friendly aliases for result types.
IndustryWindowResult = IndustryWindow
IndustryCloudResult = IndustryCloud

# Common alternative spellings.  ``industry_window`` returns the validated raw
# window; ``industry_cloud`` and its aliases return the scaled/PCA/persistence
# result.
industry_window = select_industry_window
select_window = select_industry_window
select_industry_rows = select_industry_window
window_for_as_of = select_industry_window
build_window = select_industry_window
industry_window_for = select_industry_window
prepare_industry_window = select_industry_window
validate_industry_window = select_industry_window
select_industry_window_for = select_industry_window
window_as_of = select_industry_window

industry_cloud = build_industry_cloud
build_cloud = build_industry_cloud
compute_industry_cloud = build_industry_cloud
compute_cloud = build_industry_cloud
analyse_industry_cloud = build_industry_cloud
analyze_industry_cloud = build_industry_cloud
industry_analysis = build_industry_cloud
analyse_industries = build_industry_cloud
analyze_industries = build_industry_cloud
compute_industry_analysis = build_industry_cloud
analyse_industry_window = build_industry_cloud
analyze_industry_window = build_industry_cloud
industry_cloud_analysis = build_industry_cloud
compute_industry_pca_cloud = build_industry_cloud
industry_cloud_from_rows = build_industry_cloud

# Combined explorer payload helpers.  The primary name follows the Step 5
# contract; the shorter aliases keep existing callers working.
industry_payload = industry_explorer_payload
build_industry_payload = industry_explorer_payload
combined_industry_payload = industry_explorer_payload
latest_complete_as_of = latest_complete_industry_date
latest_complete_industry_window = latest_complete_industry_date


__all__ = [
    "CANONICAL_COLUMNS",
    "CANONICAL_INDUSTRY_COLUMNS",
    "DEFAULT_WINDOW",
    "DEFAULT_WINDOW_SESSIONS",
    "COMPONENT_LABELS",
    "COLUMN_LABELS",
    "INDUSTRY_COLUMN_LABELS",
    "INDUSTRY_COLUMNS",
    "INDUSTRY_LABELS",
    "INDUSTRY_NAMES",
    "INDUSTRY_PREFIX",
    "IndustryAnalysisError",
    "INDUSTRY_WINDOW_SESSIONS",
    "IndustryCloud",
    "IndustryCloudError",
    "IndustryCloudResult",
    "IndustryError",
    "IndustryWindow",
    "IndustryWindowError",
    "IndustryWindowResult",
    "InvalidIndustryWindowError",
    "PCAProjection",
    "PCA_LABELS",
    "WINDOW_COLUMNS",
    "WINDOW_LENGTH",
    "WINDOW_SESSIONS",
    "WINDOW_SIZE",
    "analyse_industry_cloud",
    "analyse_industry_window",
    "analyse_industries",
    "analyze_industry_cloud",
    "analyze_industry_window",
    "analyze_industries",
    "build_cloud",
    "build_industry_cloud",
    "build_industry_payload",
    "build_window",
    "compute_cloud",
    "compute_industry_analysis",
    "compute_industry_cloud",
    "compute_industry_pca_cloud",
    "combined_industry_payload",
    "industry_analysis",
    "industry_explorer_payload",
    "industry_cloud",
    "industry_cloud_analysis",
    "industry_cloud_from_rows",
    "industry_payload",
    "industry_window",
    "industry_window_for",
    "latest_complete_as_of",
    "latest_complete_industry_date",
    "latest_complete_industry_window",
    "prepare_industry_window",
    "select_industry_rows",
    "select_industry_window",
    "select_industry_window_for",
    "select_window",
    "validate_industry_window",
    "window_as_of",
    "window_for_as_of",
]
