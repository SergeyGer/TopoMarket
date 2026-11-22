"""Robust (median/MAD) scaling for causal topology windows.

A window is scaled only with the observations it contains.  No statistics from
outside the window are used, so the transform is causal and cannot leak future
information into a historical topology reading.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from .errors import NonFiniteScaleError, ScalingError, ZeroScaleError

#: Constant that makes the MAD comparable to a standard deviation for normal data.
MAD_TO_SIGMA = 1.4826


class ScaledWindow(np.ndarray):
    """A scaled window carrying the robust location and scale used for it.

    For a one-dimensional input the statistics are floats.  When an ``axis`` is
    supplied they are arrays with one entry per reduced slice, which makes the
    result useful for row-wise (``axis=1``) scaling as well.
    """

    median: Any
    mad: Any
    scale: Any

    def __new__(cls, values: np.ndarray, median: Any, mad: Any, scale: Any) -> ScaledWindow:
        obj = np.array(values, dtype=float, copy=True).view(cls)
        obj.median = median
        obj.mad = mad
        obj.scale = scale
        return obj

    def __array_finalize__(self, obj: Any) -> None:
        if obj is None:
            return
        self.median = getattr(obj, "median", float("nan"))
        self.mad = getattr(obj, "mad", float("nan"))
        self.scale = getattr(obj, "scale", float("nan"))

    @property
    def location(self) -> Any:
        """Alias for the window median."""

        return self.median

    @property
    def center(self) -> Any:
        """Alias for the window median."""

        return self.median

    @property
    def robust_scale(self) -> Any:
        """Alias for the denominator used by the scaling."""

        return self.scale


def _as_float_array(
    values: Sequence[float] | np.ndarray,
    *,
    name: str = "values",
    axis: int | None = None,
) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as error:
        raise ScalingError(f"{name} must be a numeric sequence") from error
    if axis is None:
        if array.ndim != 1:
            raise ScalingError(f"{name} must be one-dimensional, got shape {array.shape}")
    elif array.ndim < 1:
        raise ScalingError(f"{name} must have at least one dimension, got shape {array.shape}")
    if array.size == 0:
        raise ScalingError("cannot scale an empty window")
    if not np.all(np.isfinite(array)):
        raise NonFiniteScaleError("window contains non-finite values")
    return array


def _normalise_axis(axis: Any) -> int | None:
    if axis is None:
        return None
    if isinstance(axis, bool) or not isinstance(axis, (int, np.integer)):
        raise ScalingError(f"axis must be an integer or None, got {axis!r}")
    return int(axis)


def _median_mad_keepdims(array: np.ndarray, axis: int | None) -> tuple[Any, Any]:
    if axis is None:
        location = float(np.median(array))
        mad = float(np.median(np.abs(array - location)))
        return location, mad
    try:
        location = np.median(array, axis=axis, keepdims=True)
        mad = np.median(np.abs(array - location), axis=axis, keepdims=True)
    except (TypeError, ValueError) as error:
        raise ScalingError(f"invalid scaling axis {axis!r}") from error
    return location, mad


def _public_stat(value: Any, axis: int | None) -> Any:
    array = np.asarray(value)
    if array.ndim == 0:
        return float(array)
    if axis is not None:
        return np.squeeze(array, axis=axis)
    return array


def median_absolute_deviation(
    values: Sequence[float] | np.ndarray,
    *,
    center: float | None = None,
    axis: int | None = None,
) -> Any:
    """Return the (unscaled) median absolute deviation of ``values``."""

    normalised_axis = _normalise_axis(axis)
    array = _as_float_array(values, axis=normalised_axis)
    if center is None:
        _, mad = _median_mad_keepdims(array, normalised_axis)
        return _public_stat(mad, normalised_axis)
    return float(np.median(np.abs(array - float(center))))


def median_and_mad(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    axis: int | None = None,
    **kwargs: Any,
) -> tuple[Any, Any]:
    """Return ``(median, MAD)`` for ``values`` without scaling them."""

    kwargs.pop("config", None)
    if (
        args
        and axis is None
        and isinstance(args[0], (int, np.integer))
        and not isinstance(args[0], bool)
    ):
        axis = int(args[0])
    normalised_axis = _normalise_axis(axis)
    array = _as_float_array(values, axis=normalised_axis)
    location, mad = _median_mad_keepdims(array, normalised_axis)
    return _public_stat(location, normalised_axis), _public_stat(mad, normalised_axis)


def robust_scale(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> ScaledWindow:
    """Scale ``values`` using ``(x - median) / (1.4826 * MAD)``.

    A window whose MAD is zero cannot be scaled and raises
    :class:`ZeroScaleError`; a non-finite median, MAD or resulting scale raises
    :class:`NonFiniteScaleError`.  Both are subclasses of :class:`ScalingError`
    (and :class:`ValueError`).

    An ``axis`` keyword applies the same robust transform independently along
    that axis.  The reduced dimensions are kept while broadcasting, so a
    two-dimensional ``axis=1`` call standardises each row rather than failing
    on a shape mismatch.
    """

    # ``config`` is accepted explicitly so a mistyped configuration does not
    # silently change the transform; it is intentionally unused.
    kwargs.pop("config", None)
    axis = kwargs.pop("axis", None)
    if (
        args
        and axis is None
        and isinstance(args[0], (int, np.integer))
        and not isinstance(args[0], bool)
    ):
        axis = int(args[0])
    normalised_axis = _normalise_axis(axis)
    array = _as_float_array(values, axis=normalised_axis)

    location, mad = _median_mad_keepdims(array, normalised_axis)
    scale = MAD_TO_SIGMA * np.asarray(mad, dtype=float)
    if not np.all(np.isfinite(np.asarray(location, dtype=float))) or not np.all(np.isfinite(scale)):
        raise NonFiniteScaleError("window median or MAD is not finite")
    if np.any(scale <= 0.0):
        raise ZeroScaleError("window scale is zero; use a window with non-zero MAD")

    scaled = (array - location) / scale
    return ScaledWindow(
        scaled,
        _public_stat(location, normalised_axis),
        _public_stat(mad, normalised_axis),
        _public_stat(scale, normalised_axis),
    )


def scale_window(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> ScaledWindow:
    """Alias for :func:`robust_scale` used by the window API."""

    return robust_scale(values, *args, **kwargs)


def robust_zscore(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> ScaledWindow:
    """Alias for :func:`robust_scale`."""

    return robust_scale(values, *args, **kwargs)


def median_mad_scale(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> ScaledWindow:
    """Alias for :func:`robust_scale` named after the statistic it uses."""

    return robust_scale(values, *args, **kwargs)


def mad_scale(
    values: Sequence[float] | np.ndarray,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Return the robust scale denominator ``1.4826 * MAD`` for ``values``."""

    axis = kwargs.pop("axis", None)
    if (
        args
        and axis is None
        and isinstance(args[0], (int, np.integer))
        and not isinstance(args[0], bool)
    ):
        axis = int(args[0])
    normalised_axis = _normalise_axis(axis)
    array = _as_float_array(values, axis=normalised_axis)
    _, mad = _median_mad_keepdims(array, normalised_axis)
    scale = MAD_TO_SIGMA * np.asarray(mad, dtype=float)
    if not np.all(np.isfinite(scale)):
        raise NonFiniteScaleError("window median or MAD is not finite")
    if np.any(scale <= 0.0):
        raise ZeroScaleError("window scale is zero; use a window with non-zero MAD")
    return _public_stat(scale, normalised_axis)


# Common alternative spellings.
median_mad = median_and_mad
robust_scaling = robust_scale
scale_values = robust_scale
normalise_window = robust_scale
normalize_window = robust_scale
scale_robust = robust_scale
robust_normalize = robust_scale
robust_normalise = robust_scale
median_mad_normalize = robust_scale
median_mad_normalise = robust_scale
robust = robust_scale


__all__ = [
    "MAD_TO_SIGMA",
    "ScaledWindow",
    "mad_scale",
    "median_absolute_deviation",
    "median_and_mad",
    "median_mad",
    "median_mad_normalise",
    "median_mad_normalize",
    "median_mad_scale",
    "normalise_window",
    "normalize_window",
    "robust",
    "robust_normalise",
    "robust_normalize",
    "robust_scale",
    "robust_scaling",
    "robust_zscore",
    "scale_robust",
    "scale_values",
    "scale_window",
]
