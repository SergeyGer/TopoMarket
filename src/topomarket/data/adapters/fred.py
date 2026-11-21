"""Adapter for the Federal Reserve Bank of St. Louis (FRED) S&P 500 series."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import BaseAdapter, NormalizedDataset, ParsedSource, Row, standard_rows

SOURCE_ID = "fred_sp500"
SOURCE_NAME = "FRED S&P 500"
CANONICAL_COLUMNS = ("date", "value")
UNITS: Mapping[str, str] = {
    "date": "ISO-8601 date",
    "value": "index points",
}
TYPES = {"date": "date", "value": "float"}
FIELD_ALIASES = {
    "value": (
        "value",
        "sp500",
        "sp_500",
        "s_p_500",
        "close",
        "price",
        "index",
        "index_value",
        "observation_value",
    ),
}
_VALUE_ALIASES = (
    "sp500",
    "sp_500",
    "s_p_500",
    "value",
    "close",
    "price",
    "index",
    "index_value",
    "observation_value",
)


class FREDSP500Adapter(BaseAdapter):
    """Parse a local FRED CSV export for the ``SP500`` series."""

    source_id = SOURCE_ID
    source_name = SOURCE_NAME
    aliases = ("fred", "fred_sp500", "sp500_fred", "stlouis", "st_louis", "fredsp500")
    filename_patterns = ("fred", "sp500", "sp_500")
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
            single_value=True,
            extra_value_aliases=_VALUE_ALIASES,
        )
        if not rows:
            warnings.append("no dated FRED SP500 observations were found")
        if rows and "value" not in schema:
            warnings.append("source has no numeric SP500 value column")
        return rows, schema, units, warnings


# Keep upper-case metadata available on the class as well as the module.
FREDSP500Adapter.SOURCE_ID = SOURCE_ID
FREDSP500Adapter.SOURCE_NAME = SOURCE_NAME
FREDSP500Adapter.columns = CANONICAL_COLUMNS
FREDSP500Adapter.UNITS = UNITS
FREDSP500Adapter.TYPES = TYPES

FredSP500Adapter = FREDSP500Adapter
FREDAdapter = FREDSP500Adapter
FredAdapter = FREDSP500Adapter
FREDSP500 = FREDSP500Adapter
FRED = FREDSP500Adapter
Fred = FREDSP500Adapter
FREDSeriesAdapter = FREDSP500Adapter
FREDSP500CSVAdapter = FREDSP500Adapter
FredSP500CSVAdapter = FREDSP500Adapter
FREDCSVAdapter = FREDSP500Adapter

FREDSP500Source = FREDSP500Adapter
FREDSource = FREDSP500Adapter
FREDSP500Parser = FREDSP500Adapter
FredSP500Source = FREDSP500Adapter
FREDSP500DailyAdapter = FREDSP500Adapter
FREDSP500SeriesAdapter = FREDSP500Adapter
FredSP500SeriesAdapter = FREDSP500Adapter
FREDSP500CSV = FREDSP500Adapter


def parse_fred_sp500(source: Any, **kwargs: Any) -> NormalizedDataset:
    """Parse a FRED SP500 CSV export and return its normalised dataset."""

    return FREDSP500Adapter(source, **kwargs).parse()


parse_fred = parse_fred_sp500
load_fred_sp500 = parse_fred_sp500
read_fred_sp500 = parse_fred_sp500
adapt_fred_sp500 = parse_fred_sp500
parse_fred_sp500_csv = parse_fred_sp500
read_fred = parse_fred_sp500
load_fred = parse_fred_sp500
read_fred_sp500_csv = parse_fred_sp500
load_fred_sp500_csv = parse_fred_sp500
adapt_fred_sp500_csv = parse_fred_sp500
parse_fred_sp500_text = parse_fred_sp500
fred_sp500 = parse_fred_sp500
fred = parse_fred_sp500


__all__ = [
    "FREDSP500Source",
    "FREDSource",
    "FREDSP500Parser",
    "FredSP500Source",
    "load_fred_sp500",
    "read_fred_sp500",
    "adapt_fred_sp500",
    "parse_fred_sp500_csv",
    "CANONICAL_COLUMNS",
    "FIELD_ALIASES",
    "SOURCE_ID",
    "SOURCE_NAME",
    "TYPES",
    "UNITS",
    "FREDCSVAdapter",
    "FRED",
    "FREDAdapter",
    "FREDSP500",
    "FREDSP500Adapter",
    "FREDSP500CSV",
    "FREDSP500CSVAdapter",
    "FREDSP500DailyAdapter",
    "FREDSP500SeriesAdapter",
    "FREDSeriesAdapter",
    "Fred",
    "FredAdapter",
    "FredSP500Adapter",
    "FredSP500CSVAdapter",
    "FredSP500SeriesAdapter",
    "adapt_fred_sp500_csv",
    "fred",
    "fred_sp500",
    "load_fred",
    "load_fred_sp500_csv",
    "parse_fred",
    "parse_fred_sp500",
    "parse_fred_sp500_text",
    "read_fred",
    "read_fred_sp500_csv",
]
