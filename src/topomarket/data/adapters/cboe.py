"""Adapter for the Cboe Global Markets spot VIX history archive."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import BaseAdapter, NormalizedDataset, ParsedSource, Row, standard_rows

SOURCE_ID = "cboe_vix"
SOURCE_NAME = "Cboe VIX"
CANONICAL_COLUMNS = ("date", "open", "high", "low", "close")
UNITS: Mapping[str, str] = {
    "date": "ISO-8601 date",
    "open": "VIX index points",
    "high": "VIX index points",
    "low": "VIX index points",
    "close": "VIX index points",
}
TYPES = {
    "date": "date",
    "open": "float",
    "high": "float",
    "low": "float",
    "close": "float",
}
FIELD_ALIASES = {
    "open": ("open", "open_price", "opening", "o"),
    "high": ("high", "high_price", "h"),
    "low": ("low", "low_price", "l"),
    "close": (
        "close",
        "close_price",
        "closing",
        "closing_price",
        "last",
        "vix",
        "vix_close",
        "value",
        "price",
    ),
}


class CboeVixAdapter(BaseAdapter):
    """Parse the official Cboe VIX CSV into daily observations."""

    source_id = SOURCE_ID
    source_name = SOURCE_NAME
    aliases = ("cboe", "cboe_vix", "vix", "vix_history", "cboevix")
    filename_patterns = ("cboe", "vix")
    required = True
    canonical_columns = CANONICAL_COLUMNS
    units = UNITS
    types = TYPES

    def _parse_rows(
        self, source: ParsedSource
    ) -> tuple[list[Row], dict[str, str], dict[str, str], list[str]]:
        rows, schema, units, warnings = standard_rows(
            source,
            field_aliases=FIELD_ALIASES,
            canonical_columns=CANONICAL_COLUMNS,
            units=UNITS,
            types=TYPES,
        )
        if not rows:
            warnings.append("no dated VIX observations were found")
        elif "close" not in schema:
            warnings.append("source has no VIX close column")
        return rows, schema, units, warnings


# Keep upper-case metadata available on the class as well as the module.
CboeVixAdapter.SOURCE_ID = SOURCE_ID
CboeVixAdapter.SOURCE_NAME = SOURCE_NAME
CboeVixAdapter.columns = CANONICAL_COLUMNS
CboeVixAdapter.UNITS = UNITS
CboeVixAdapter.TYPES = TYPES

CboeVIXAdapter = CboeVixAdapter
VIXAdapter = CboeVixAdapter
CboeAdapter = CboeVixAdapter
CboeVix = CboeVixAdapter
CboeVIX = CboeVixAdapter
VIX = CboeVixAdapter
CboeVIXHistoryAdapter = CboeVixAdapter
CBOEVIXAdapter = CboeVixAdapter
CboeVixCSVAdapter = CboeVixAdapter
CboeVIXCSVAdapter = CboeVixAdapter

CboeVixSource = CboeVixAdapter
CboeVIXSource = CboeVixAdapter
VIXSource = CboeVixAdapter
CboeVixParser = CboeVixAdapter
CboeVixHistoryAdapter = CboeVixAdapter
CboeVixHistoryCSVAdapter = CboeVixAdapter
VIXHistoryAdapter = CboeVixAdapter
CboeVixCSV = CboeVixAdapter


def parse_cboe_vix(source: Any, **kwargs: Any) -> NormalizedDataset:
    """Parse a Cboe VIX CSV file and return its normalised dataset."""

    return CboeVixAdapter(source, **kwargs).parse()


parse_vix = parse_cboe_vix
load_cboe_vix = parse_cboe_vix
read_cboe_vix = parse_cboe_vix
adapt_cboe_vix = parse_cboe_vix
parse_cboe_vix_csv = parse_cboe_vix
parse_cboe = parse_cboe_vix
read_vix = parse_cboe_vix
load_vix = parse_cboe_vix
read_cboe_vix_csv = parse_cboe_vix
load_cboe_vix_csv = parse_cboe_vix
adapt_cboe_vix_csv = parse_cboe_vix
parse_cboe_vix_text = parse_cboe_vix
cboe_vix = parse_cboe_vix
vix = parse_cboe_vix


__all__ = [
    "CboeVixSource",
    "CboeVIXSource",
    "VIXSource",
    "CboeVixParser",
    "load_cboe_vix",
    "read_cboe_vix",
    "adapt_cboe_vix",
    "parse_cboe_vix_csv",
    "CANONICAL_COLUMNS",
    "FIELD_ALIASES",
    "SOURCE_ID",
    "SOURCE_NAME",
    "TYPES",
    "UNITS",
    "CBOEVIXAdapter",
    "CboeAdapter",
    "CboeVIX",
    "CboeVIXAdapter",
    "CboeVIXCSVAdapter",
    "CboeVIXHistoryAdapter",
    "CboeVix",
    "CboeVixAdapter",
    "CboeVixCSV",
    "CboeVixCSVAdapter",
    "CboeVixHistoryAdapter",
    "CboeVixHistoryCSVAdapter",
    "VIX",
    "VIXAdapter",
    "VIXHistoryAdapter",
    "adapt_cboe_vix_csv",
    "cboe_vix",
    "load_cboe_vix_csv",
    "load_vix",
    "parse_cboe",
    "parse_cboe_vix",
    "parse_cboe_vix_text",
    "parse_vix",
    "read_cboe_vix_csv",
    "read_vix",
    "vix",
]
