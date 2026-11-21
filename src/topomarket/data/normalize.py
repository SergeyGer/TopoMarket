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
