"""Full Vietoris-Rips persistence for topology windows.

The filtration is intentionally complete: persistence is computed with
``thresh=inf`` so no intervals are discarded at an arbitrary distance.  The
only filtering happens when finite lifetimes are derived, where infinite bars
and bars at or below the configured threshold are excluded.

Every public persistence entry point applies the same rule.  A finite
``thresh`` (which would truncate the filtration) and ``n_perm`` (which would
subsample the point cloud) are rejected rather than silently forwarded to
ripser.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .config import DEFAULT_CONFIG, TopologyConfig
from .errors import PersistenceError

#: Accepted names for the maximum homology dimension.
_MAXDIM_KEYS = ("maxdim", "max_dimension", "max_homology_dimension", "maxdimension")
_COEFF_KEYS = ("coeff", "coefficient", "coeff_field", "homology_coeff_field", "field")


class RipsResult(dict):
    """A dict-like ripser result that also exposes its diagrams as attributes."""

    def __getattr__(self, name: str) -> Any:
        aliases = {
            "diagrams": "dgms",
            "dgms": "dgms",
            "persistence": "dgms",
            "cocycles": "cocycles",
        }
        key = aliases.get(name)
        if key is not None and key in self:
            return self[key]
        raise AttributeError(name)

    @property
    def h0(self) -> Any:
        return self["dgms"][0]

    @property
    def h1(self) -> Any:
        return self["dgms"][1]


class Diagrams(tuple):
    """Tuple of read-only persistence diagrams indexed by homology dimension."""

    def __new__(cls, diagrams: Sequence[Any]) -> Diagrams:
        arrays = []
        for diagram in diagrams:
            array = np.array(diagram, dtype=float, copy=True)
            array.setflags(write=False)
            arrays.append(array)
        return tuple.__new__(cls, tuple(arrays))

    @property
    def diagrams(self) -> Diagrams:
        return self

    @property
    def dgms(self) -> Diagrams:
        return self

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            normalised = key.strip().lower()
            if normalised in {"dgms", "diagrams", "persistence"}:
                return self
            if normalised.startswith("h") and normalised[1:].isdigit():
                return tuple.__getitem__(self, int(normalised[1:]))
            raise KeyError(key)
        return tuple.__getitem__(self, key)

    @property
    def h0(self) -> np.ndarray:
        if len(self) < 1:
            return np.empty((0, 2), dtype=float)
        return tuple.__getitem__(self, 0)

    @property
    def h1(self) -> np.ndarray:
        if len(self) < 2:
            return np.empty((0, 2), dtype=float)
        return tuple.__getitem__(self, 1)

    def as_dict(self) -> dict[str, Any]:
        return {"dgms": list(self)}

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Diagrams):
            other_values: Sequence[Any] = other
        elif isinstance(other, (tuple, list)):
            other_values = other
        else:
            return NotImplemented
        if len(self) != len(other_values):
            return False
        return all(
            np.array_equal(left, right) for left, right in zip(self, other_values, strict=True)
        )

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return NotImplemented
        return not result

    __hash__ = None  # type: ignore[assignment]


class Lifetimes(tuple):
    """Finite read-only lifetimes, per homology dimension.

    Iterating/indexing behaves like a tuple of per-dimension arrays (``[0]`` is
    H0 and ``[1]`` is H1).  Coercing to a NumPy array yields the finite H1
    lifetimes, which is the value used by the anomaly score.
    """

    def __new__(cls, per_dimension: Sequence[Any]) -> Lifetimes:
        arrays = []
        for values in per_dimension:
            array = np.array(values, dtype=float, copy=True).reshape(-1)
            array.setflags(write=False)
            arrays.append(array)
        obj = tuple.__new__(cls, tuple(arrays))
        if len(arrays) > 1:
            obj._default = arrays[1]
        elif arrays:
            obj._default = arrays[-1]
        else:
            obj._default = np.empty(0, dtype=float)
        return obj

    @property
    def h0(self) -> np.ndarray:
        if len(self) < 1:
            return np.empty(0, dtype=float)
        return tuple.__getitem__(self, 0)

    @property
    def h1(self) -> np.ndarray:
        if len(self) < 2:
            return np.empty(0, dtype=float)
        return tuple.__getitem__(self, 1)

    @property
    def flat(self) -> np.ndarray:
        return np.asarray(self._default, dtype=float)

    @property
    def values(self) -> np.ndarray:
        return self.flat

    @property
    def shape(self) -> tuple[int, ...]:
        return self.flat.shape

    @property
    def size(self) -> int:
        return int(self.flat.size)

    @property
    def dtype(self) -> np.dtype[Any]:
        return self.flat.dtype

    def __array__(self, dtype: Any = None) -> np.ndarray:
        return np.asarray(self.flat, dtype=dtype)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            normalised = key.strip().lower()
            if normalised in {"flat", "h1", "values", "lifetimes"}:
                return self.h1 if len(self) > 1 else self.flat
            if normalised.startswith("h") and normalised[1:].isdigit():
                return tuple.__getitem__(self, int(normalised[1:]))
            raise KeyError(key)
        return tuple.__getitem__(self, key)

    def tolist(self) -> list[Any]:
        return [array.tolist() for array in self]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Lifetimes):
            other_values: Sequence[Any] = other
        elif isinstance(other, (tuple, list)):
            other_values = other
        else:
            return NotImplemented
        if len(self) != len(other_values):
            return False
        return all(
            np.array_equal(left, right) for left, right in zip(self, other_values, strict=True)
        )

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return NotImplemented
        return not result

    __hash__ = None  # type: ignore[assignment]


def _coerce_config(value: Any) -> TopologyConfig | None:
    if value is None or isinstance(value, TopologyConfig):
        return value
    if isinstance(value, Mapping):
        return TopologyConfig.from_dict(value)
    raise PersistenceError("config must be a TopologyConfig or mapping")


def _pop_alias(kwargs: dict[str, Any], keys: Sequence[str]) -> Any:
    found: list[tuple[str, Any]] = []
    for key in keys:
        if key in kwargs:
            found.append((key, kwargs.pop(key)))
    if len(found) > 1:
        names = ", ".join(key for key, _ in found)
        raise PersistenceError(f"parameter was provided more than once via {names}")
    return found[0][1] if found else None


def _require_dimension(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise PersistenceError(f"{name} must be an integer, got {value!r}")
    result = int(value)
    if result < 0:
        raise PersistenceError(f"{name} must be >= 0, got {value!r}")
    return result


def _complete_ripser_kwargs(
    kwargs: dict[str, Any],
    config: TopologyConfig | None = None,
) -> dict[str, Any]:
    """Validate a ripser call and return full-filtration keyword arguments."""

    maxdim = _pop_alias(kwargs, _MAXDIM_KEYS)
    coeff = _pop_alias(kwargs, _COEFF_KEYS)
    if maxdim is None:
        maxdim = config.max_homology_dimension if config is not None else 1
    if coeff is None:
        coeff = config.homology_coeff_field if config is not None else 2
    maxdim = _require_dimension("maxdim", maxdim)
    coeff = _require_dimension("coeff", coeff)
    if coeff < 2:
        raise PersistenceError(f"coeff must be >= 2, got {coeff!r}")

    metric = kwargs.pop("metric", "euclidean")
    distance_matrix = kwargs.pop("distance_matrix", None)
    do_cocycles = kwargs.pop("do_cocycles", None)

    if "n_perm" in kwargs:
        raise PersistenceError(
            "n_perm subsampling is not supported; persistence must use the full point cloud"
        )
    thresh = kwargs.pop("thresh", np.inf)
    if kwargs:
        names = ", ".join(sorted(str(key) for key in kwargs))
        raise PersistenceError(f"unexpected persistence argument(s): {names}")

    if thresh is None:
        thresh = np.inf
    try:
        threshold = float(thresh)
    except (TypeError, ValueError) as error:
        raise PersistenceError(
            "thresh must be infinity; truncated filtrations are not supported"
        ) from error
    if not np.isposinf(threshold):
        raise PersistenceError("thresh must be infinity; truncated filtrations are not supported")

    call_kwargs: dict[str, Any] = {
        "maxdim": maxdim,
        "thresh": np.inf,
        "coeff": coeff,
        "metric": metric,
    }
    if distance_matrix is not None:
        call_kwargs["distance_matrix"] = bool(distance_matrix)
    if do_cocycles is not None:
        call_kwargs["do_cocycles"] = bool(do_cocycles)
    return call_kwargs


def ripser(X: Any, **kwargs: Any) -> RipsResult:
    """Call ripser with a complete filtration over every input point.

    The wrapper validates the complete-filtration rule before touching the
    installed ripser implementation.  It is deliberately thin so
    monkeypatching either this module's ``ripser`` name or the library's
    ``ripser.ripser`` entry point works in offline tests.
    """

    call_kwargs = _complete_ripser_kwargs(dict(kwargs))
    try:
        import ripser as _ripser_library

        result = _ripser_library.ripser(X, **call_kwargs)
    except PersistenceError:
        raise
    except Exception as error:  # pragma: no cover - depends on the optional library
        raise PersistenceError(f"Vietoris-Rips persistence failed: {error}") from error
    if isinstance(result, Mapping):
        return RipsResult(result)
    return result  # type: ignore[return-value]


def _as_points(points: Any) -> np.ndarray:
    try:
        array = np.asarray(points, dtype=float)
    except (TypeError, ValueError) as error:
        raise PersistenceError("points must be a two-dimensional numeric array") from error
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    if array.ndim != 2:
        raise PersistenceError(f"points must be two-dimensional, got shape {array.shape}")
    if array.shape[0] == 0:
        raise PersistenceError("cannot compute persistence for an empty point cloud")
    if not np.all(np.isfinite(array)):
        raise PersistenceError("point cloud contains non-finite coordinates")
    return array


def persistence_diagrams(
    points: Any,
    config: TopologyConfig | Mapping[str, Any] | None = None,
    *args: Any,
    **kwargs: Any,
) -> Diagrams:
    """Return full Vietoris-Rips diagrams for ``points``.

    ``maxdim`` and ``coeff`` default to the frozen configuration.  The metric is
    Euclidean and the filtration is always complete: ripser is called with an
    infinite threshold over every point in the cloud.  Truncating the filtration
    with a finite ``thresh`` or subsampling with ``n_perm`` is rejected because
    either would make the reported diagrams incomplete.
    """

    if args:
        if len(args) > 1:
            raise PersistenceError("persistence accepts at most one positional config")
        if config is not None:
            raise PersistenceError("config was provided more than once")
        config = args[0]
    if "config" in kwargs:
        if config is not None:
            raise PersistenceError("config was provided more than once")
        config = kwargs.pop("config")
    config = _coerce_config(config)
    if config is None:
        config = DEFAULT_CONFIG

    call_kwargs = _complete_ripser_kwargs(kwargs, config)
    array = _as_points(points)
    result = ripser(array, **call_kwargs)
    diagrams = result.get("dgms") if isinstance(result, Mapping) else getattr(result, "dgms", None)
    if diagrams is None:
        raise PersistenceError("ripser result does not contain persistence diagrams")
    return Diagrams(diagrams)


def _single_finite_lifetimes(diagram: Any, threshold: float) -> np.ndarray:
    array = np.asarray(diagram, dtype=float)
    if array.size == 0:
        return np.empty(0, dtype=float)
    if array.ndim == 1:
        # A flat array is already a collection of lifetimes as returned by
        # ``h1_lifetimes``; keep it usable with ``total_persistence``.
        values = array[np.isfinite(array)]
        return np.asarray(values[values > threshold], dtype=float)
    if array.ndim != 2 or array.shape[1] != 2:
        raise PersistenceError(f"a persistence diagram must have shape (n, 2), got {array.shape}")
    birth = array[:, 0]
    death = array[:, 1]
    finite = np.isfinite(birth) & np.isfinite(death)
    values = (death - birth)[finite]
    # "at or below the threshold" is excluded, so the comparison is strict.
    values = values[values > threshold]
    return np.asarray(values, dtype=float)


def _is_diagram_collection(value: Any) -> bool:
    if isinstance(value, Diagrams):
        return True
    if isinstance(value, np.ndarray):
        return value.ndim == 3
    if isinstance(value, (list, tuple)) and value:
        return all(isinstance(item, np.ndarray) and item.ndim == 2 for item in value)
    return False


def finite_lifetimes(
    diagram: Any,
    min_interval: float | None = None,
    *args: Any,
    **kwargs: Any,
) -> np.ndarray | Lifetimes:
    """Return finite lifetimes longer than ``min_interval``.

    Infinite deaths (including the essential H0 class) are always excluded.  A
    single ``(n, 2)`` diagram returns a flat array; a sequence of diagrams
    returns a :class:`Lifetimes` tuple indexed by dimension.  The comparison is
    strict: a lifetime exactly equal to the threshold is excluded.
    """

    if args:
        if len(args) > 1:
            raise PersistenceError("finite_lifetimes accepts at most one positional threshold")
        if min_interval is not None:
            raise PersistenceError("min_interval was provided more than once")
        min_interval = args[0]
    for alias in ("threshold", "min_lifetime", "epsilon"):
        if alias in kwargs:
            if min_interval is not None:
                raise PersistenceError("min_interval was provided more than once")
            min_interval = kwargs.pop(alias)
    if min_interval is None:
        config = _coerce_config(kwargs.pop("config", None)) or DEFAULT_CONFIG
        min_interval = config.min_interval
    if kwargs:
        names = ", ".join(sorted(str(key) for key in kwargs))
        raise PersistenceError(f"unexpected lifetime argument(s): {names}")
    if isinstance(min_interval, bool) or not isinstance(min_interval, (int, float, np.number)):
        raise PersistenceError("min_interval must be a finite number")
    threshold = float(min_interval)
    if not np.isfinite(threshold):
        raise PersistenceError("min_interval must be finite")

    if isinstance(diagram, Lifetimes):
        return Lifetimes(tuple(_single_finite_lifetimes(item, threshold) for item in diagram))
    if _is_diagram_collection(diagram):
        return Lifetimes(tuple(_single_finite_lifetimes(item, threshold) for item in diagram))
    return _single_finite_lifetimes(diagram, threshold)


def total_persistence(
    diagram: Any,
    min_interval: float | None = None,
    *args: Any,
    **kwargs: Any,
) -> float:
    """Return the sum of the finite lifetimes selected by :func:`finite_lifetimes`."""

    if isinstance(diagram, Lifetimes):
        diagram = diagram.h1 if len(diagram) > 1 else diagram.flat
    values = finite_lifetimes(diagram, min_interval, *args, **kwargs)
    if isinstance(values, Lifetimes):
        values = values.h1 if len(values) > 1 else values.flat
    return float(np.sum(np.asarray(values, dtype=float)))


def max_persistence(
    diagram: Any,
    min_interval: float | None = None,
    *args: Any,
    **kwargs: Any,
) -> float:
    """Return the largest selected finite lifetime (zero when there is none)."""

    if isinstance(diagram, Lifetimes):
        diagram = diagram.h1 if len(diagram) > 1 else diagram.flat
    values = finite_lifetimes(diagram, min_interval, *args, **kwargs)
    if isinstance(values, Lifetimes):
        values = values.h1 if len(values) > 1 else values.flat
    array = np.asarray(values, dtype=float)
    return float(np.max(array)) if array.size else 0.0


def h1_lifetimes(
    diagrams: Any,
    min_interval: float | None = None,
    *args: Any,
    **kwargs: Any,
) -> np.ndarray:
    """Return finite H1 lifetimes from a diagram collection."""

    if isinstance(diagrams, Lifetimes):
        return np.asarray(diagrams.h1 if len(diagrams) > 1 else diagrams.flat, dtype=float)
    if _is_diagram_collection(diagrams):
        collection = diagrams if isinstance(diagrams, Diagrams) else Diagrams(diagrams)
        if len(collection) < 2:
            return np.empty(0, dtype=float)
        return np.asarray(finite_lifetimes(collection[1], min_interval, *args, **kwargs))
    return np.asarray(finite_lifetimes(diagrams, min_interval, *args, **kwargs))


def persistence_score(
    diagrams: Any,
    min_interval: float | None = None,
    *args: Any,
    **kwargs: Any,
) -> float:
    """Return the total finite H1 persistence (``L``)."""

    values = h1_lifetimes(diagrams, min_interval, *args, **kwargs)
    return float(np.sum(np.asarray(values, dtype=float)))


def vietoris_rips(points: Any, *args: Any, **kwargs: Any) -> RipsResult:
    """Alias for the raw (wrapped) ripser call with the same full-filtration rules."""

    # Validate here as well as inside :func:`ripser`.  That keeps the rule in
    # force even when a test or caller replaces the module-level ``ripser``
    # callable with a thin recording wrapper.
    call_kwargs = _complete_ripser_kwargs(dict(kwargs))
    return ripser(points, **call_kwargs)


# Common alternative spellings.  ``persistence`` is deliberately not exported:
# that name belongs to the ``topomarket.topology.persistence`` module.
compute_persistence = persistence_diagrams
compute_diagrams = persistence_diagrams
persistence_diagram = persistence_diagrams
rips_persistence = persistence_diagrams
vietoris_rips_persistence = persistence_diagrams
ripser_diagrams = persistence_diagrams
diagrams = persistence_diagrams
lifetimes = finite_lifetimes
persistence_lifetimes = finite_lifetimes
finite_persistence_lifetimes = finite_lifetimes
persistence_lifetime = finite_lifetimes
L = total_persistence
persistence_sum = total_persistence
lifetime_sum = total_persistence
h1_persistence = persistence_score
topology_score = persistence_score


__all__ = [
    "Diagrams",
    "L",
    "Lifetimes",
    "RipsResult",
    "compute_diagrams",
    "compute_persistence",
    "diagrams",
    "finite_lifetimes",
    "finite_persistence_lifetimes",
    "h1_lifetimes",
    "h1_persistence",
    "lifetime_sum",
    "lifetimes",
    "max_persistence",
    "persistence_diagram",
    "persistence_diagrams",
    "persistence_lifetime",
    "persistence_lifetimes",
    "persistence_score",
    "persistence_sum",
    "rips_persistence",
    "ripser",
    "ripser_diagrams",
    "topology_score",
    "total_persistence",
    "vietoris_rips",
    "vietoris_rips_persistence",
]
