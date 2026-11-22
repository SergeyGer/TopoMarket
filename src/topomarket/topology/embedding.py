"""Delay embedding for topology windows.

For a one-dimensional window ``x`` with embedding dimension ``m`` and lag
``tau`` the default (forward) embedding is the sliding point cloud

``[x[t], x[t + tau], ..., x[t + (m - 1) * tau]]``

for ``t = 0 .. len(x) - (m - 1) * tau - 1``.  A causal/past embedding places
the current observation first and the older lags after it, which is an
isometric coordinate permutation of the same cloud.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .config import DEFAULT_CONFIG, TopologyConfig
from .errors import EmbeddingError
from .scaling import (  # noqa: F401 - compatibility re-exports
    MAD_TO_SIGMA,
    ScaledWindow,
    median_and_mad,
    robust_scale,
    scale_window,
)


def _coerce_config(value: Any) -> TopologyConfig | None:
    if value is None or isinstance(value, TopologyConfig):
        return value
    if isinstance(value, Mapping):
        return TopologyConfig.from_dict(value)
    raise EmbeddingError("config must be a TopologyConfig or mapping")


def _require_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise EmbeddingError(f"{name} must be an integer, got {value!r}")
    return int(value)


def _resolve_arguments(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    """Extract ``(config, dimension, lag, order)`` from flexible arguments."""

    config = kwargs.pop("config", None)
    dimension = None
    for key in ("embedding_dimension", "dimension", "dim", "d", "m"):
        if key in kwargs:
            if dimension is not None:
                raise EmbeddingError("embedding dimension was provided more than once")
            dimension = kwargs.pop(key)
    lag = None
    for key in ("lag", "tau", "delay", "time_delay"):
        if key in kwargs:
            if lag is not None:
                raise EmbeddingError("lag was provided more than once")
            lag = kwargs.pop(key)
    order = kwargs.pop("order", None)
    causal = kwargs.pop("causal", None)
    if kwargs:
        names = ", ".join(sorted(str(key) for key in kwargs))
        raise EmbeddingError(f"unexpected embedding argument(s): {names}")

    positional: list[Any] = []
    for arg in args:
        if isinstance(arg, TopologyConfig) or isinstance(arg, Mapping):
            if config is not None:
                raise EmbeddingError("config was provided more than once")
            config = arg
        elif isinstance(arg, (int, np.integer)) and not isinstance(arg, bool):
            positional.append(int(arg))
        elif isinstance(arg, (tuple, list)) and len(arg) == 2:
            positional.extend(arg)
        else:
            raise EmbeddingError(f"unsupported positional embedding argument: {arg!r}")

    if len(positional) > 2:
        raise EmbeddingError("delay embedding accepts at most dimension and lag positionally")
    if positional:
        if dimension is not None:
            raise EmbeddingError("embedding dimension was provided more than once")
        dimension = positional[0]
    if len(positional) == 2:
        if lag is not None:
            raise EmbeddingError("lag was provided more than once")
        lag = positional[1]

    if causal is not None:
        if order is not None:
            raise EmbeddingError("pass either causal or order, not both")
        order = "causal" if causal else "forward"

    return config, dimension, lag, order


def _resolve_order(order: Any) -> bool:
    """Return ``True`` for a past/causal orientation."""

    if order is None:
        return False
    if isinstance(order, bool):
        return order
    if not isinstance(order, str):
        raise EmbeddingError("order must be a string or boolean")
    normalised = order.strip().lower().replace("_", "-")
    if normalised in {"forward", "future", "lag", "lagged", "delay", "standard"}:
        return False
    if normalised in {"causal", "past", "reverse", "reversed", "backward", "back"}:
        return True
    raise EmbeddingError(f"unknown embedding order: {order!r}")


def delay_embedding(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> np.ndarray:
    """Return the delay-embedded point cloud for ``values``.

    The function accepts either a frozen :class:`TopologyConfig`, a pair of
    ``(dimension, lag)`` arguments, or explicit ``dimension``/``lag`` keyword
    arguments.  For the frozen default (60 observations, dimension 3, lag 2)
    the result has shape ``(56, 3)``.
    """

    config, dimension, lag, order = _resolve_arguments(args, dict(kwargs))
    config = _coerce_config(config)
    if config is None:
        config = DEFAULT_CONFIG
    if dimension is None:
        dimension = config.embedding_dimension
    if lag is None:
        lag = config.lag

    dimension = _require_int("embedding_dimension", dimension)
    lag = _require_int("lag", lag)
    if dimension < 2:
        raise EmbeddingError(f"embedding_dimension must be >= 2, got {dimension}")
    if lag < 1:
        raise EmbeddingError(f"lag must be >= 1, got {lag}")

    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as error:
        raise EmbeddingError("values must be a one-dimensional numeric sequence") from error
    if array.ndim == 2 and array.shape[1] == 1:
        array = array.reshape(-1)
    if array.ndim != 1:
        raise EmbeddingError(f"values must be one-dimensional, got shape {array.shape}")
    if array.size == 0:
        raise EmbeddingError("cannot embed an empty window")
    if not np.all(np.isfinite(array)):
        raise EmbeddingError("window contains non-finite values")

    span = (dimension - 1) * lag
    count = array.size - span
    if count < 1:
        raise EmbeddingError(
            "window is too short for the requested embedding: need more than "
            f"(embedding_dimension - 1) * lag = {span} values, got {array.size}"
        )

    causal = _resolve_order(order)
    if causal:
        starts = np.arange(span, array.size)
        offsets = np.arange(dimension) * lag
        indices = starts[:, None] - offsets[None, :]
    else:
        starts = np.arange(count)
        offsets = np.arange(dimension) * lag
        indices = starts[:, None] + offsets[None, :]
    return np.asarray(array[indices], dtype=float)


def causal_embedding(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> np.ndarray:
    """Delay embedding whose first coordinate is the current observation."""

    kwargs["causal"] = True
    return delay_embedding(values, *args, **kwargs)


def past_embedding(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> np.ndarray:
    """Alias for the causal/past-oriented delay embedding."""

    kwargs["causal"] = True
    return delay_embedding(values, *args, **kwargs)


def forward_embedding(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> np.ndarray:
    """Alias for the default forward delay embedding."""

    kwargs["causal"] = False
    return delay_embedding(values, *args, **kwargs)


def embedding_dimension_of(config: TopologyConfig | None = None) -> int:
    """Return the configured embedding dimension."""

    return (config or DEFAULT_CONFIG).embedding_dimension


# Common alternative spellings.  Deliberately avoid names that would mask the
# ``embedding`` module when imported as ``topomarket.topology.embedding``.
delay_embed = delay_embedding
embed_values = delay_embedding
embed_window = delay_embedding
embed_series = delay_embedding
lag_embed = delay_embedding
lagged_embedding = delay_embedding
sliding_window_embedding = delay_embedding
time_delay_embedding = delay_embedding
make_delay_embedding = delay_embedding
delay_embedding_matrix = delay_embedding


__all__ = [
    "causal_embedding",
    "delay_embed",
    "delay_embedding",
    "delay_embedding_matrix",
    "embed_series",
    "embed_values",
    "embed_window",
    "embedding_dimension_of",
    "forward_embedding",
    "lag_embed",
    "lagged_embedding",
    "make_delay_embedding",
    "past_embedding",
    "sliding_window_embedding",
    "time_delay_embedding",
]
