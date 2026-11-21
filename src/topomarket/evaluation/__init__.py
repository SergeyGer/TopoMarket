"""Evaluation helpers for TopoMarket.

The scaffold intentionally keeps evaluation independent from data loading so
that the same metrics can be applied to the synthetic demo profile and to
user-supplied private data.
"""

from __future__ import annotations

from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean of ``values``.

    Raises ``ValueError`` for an empty sequence.
    """

    if not values:
        raise ValueError("mean() requires at least one value")
    return sum(values) / len(values)


__all__ = ["mean"]
