"""Normalisation helpers shared by the seed-file adapters."""

from __future__ import annotations

from .adapters.base import (
    NormalizedDataset,
    Row,
    coerce_number,
    is_missing,
    normalize_key,
    parse_date,
)

normalize_date = parse_date
normalize_number = coerce_number
normalise_date = parse_date
normalise_number = coerce_number
normalize_value = coerce_number
normalise_value = coerce_number


def normalize_table(rows, **kwargs):
    """Build a :class:`NormalizedDataset` from an iterable of mappings."""

    return NormalizedDataset(rows, **kwargs)


normalise_table = normalize_table


__all__ = [
    "NormalizedDataset",
    "Row",
    "coerce_number",
    "is_missing",
    "normalise_date",
    "normalise_number",
    "normalise_table",
    "normalise_value",
    "normalize_date",
    "normalize_key",
    "normalize_number",
    "normalize_table",
    "normalize_value",
    "parse_date",
]

# The A2 normalised analysis tables are exposed here as well so callers that
# already import ``topomarket.data.normalize`` can discover the table builders
# without changing their import path.
from .normalized import *  # noqa: E402,F401,F403
from .normalized import __all__ as _NORMALIZED_ALL  # noqa: E402

__all__ += [name for name in _NORMALIZED_ALL if name not in __all__]
