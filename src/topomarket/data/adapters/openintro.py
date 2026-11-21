"""Adapter for the OpenIntro / Yahoo Finance S&P 500 daily history."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import BaseAdapter, NormalizedDataset, ParsedSource, Row, standard_rows

SOURCE_ID = "openintro_sp500"
SOURCE_NAME = "OpenIntro S&P 500"
CANONICAL_COLUMNS = ("date", "open", "high", "low", "close", "adj_close", "volume")
UNITS: Mapping[str, str] = {
    "date": "ISO-8601 date",
    "open": "index points",
    "high": "index points",
    "low": "index points",
    "close": "index points",
    "adj_close": "index points (adjusted for corporate actions)",
    "volume": "shares",
}
TYPES = {
    "date": "date",
    "open": "float",
    "high": "float",
    "low": "float",
    "close": "float",
    "adj_close": "float",
    "volume": "integer",
}
FIELD_ALIASES = {
    "open": ("open", "open_price", "opening", "opening_price", "o"),
    "high": ("high", "high_price", "highs", "h"),
    "low": ("low", "low_price", "lows", "l"),
    "close": (
        "close",
        "close_price",
        "closing",
        "closing_price",
        "last",
        "price",
        "value",
        "adj_close",
        "adjusted_close",
    ),
    "adj_close": (
        "adj_close",
        "adjclose",
        "adj close",
        "adjusted_close",
        "adjusted close",
        "adjusted_close_price",
    ),
    "volume": ("volume", "vol", "volumes", "shares", "traded_volume"),
}


class OpenIntroSP500Adapter(BaseAdapter):
    """Parse the OpenIntro/Yahoo S&P 500 CSV into daily observations."""

    source_id = SOURCE_ID
    source_name = SOURCE_NAME
    aliases = ("openintro", "open_intro", "openintro_sp500", "sp500_openintro", "s_p_500")
    filename_patterns = ("openintro", "open_intro", "sp500", "s_p_500")
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
            extra_value_aliases=("sp500", "sp_500", "price", "close", "value"),
        )
        if not rows:
            warnings.append("no dated S&P 500 observations were found")
        elif "close" not in schema:
            warnings.append("source has no close column")
        return rows, schema, units, warnings


# Keep upper-case metadata available on the class as well as the module.
OpenIntroSP500Adapter.SOURCE_ID = SOURCE_ID
OpenIntroSP500Adapter.SOURCE_NAME = SOURCE_NAME
OpenIntroSP500Adapter.columns = CANONICAL_COLUMNS
OpenIntroSP500Adapter.UNITS = UNITS
OpenIntroSP500Adapter.TYPES = TYPES

OpenIntroAdapter = OpenIntroSP500Adapter
OpenIntro = OpenIntroSP500Adapter
OpenIntroSP500 = OpenIntroSP500Adapter
SP500Adapter = OpenIntroSP500Adapter
OpenIntroSP500CSVAdapter = OpenIntroSP500Adapter
OpenIntroCSVAdapter = OpenIntroSP500Adapter
SP500CSVAdapter = OpenIntroSP500Adapter

OpenIntroSP500Source = OpenIntroSP500Adapter
OpenIntroSource = OpenIntroSP500Adapter
OpenIntroSP500Parser = OpenIntroSP500Adapter
SP500Source = OpenIntroSP500Adapter
OpenIntroSP500DailyAdapter = OpenIntroSP500Adapter
OpenIntroSP500FileAdapter = OpenIntroSP500Adapter
SP500OpenIntroAdapter = OpenIntroSP500Adapter
OpenIntroSP500CSV = OpenIntroSP500Adapter


def parse_openintro_sp500(source: Any, **kwargs: Any) -> NormalizedDataset:
    """Parse an OpenIntro S&P 500 file and return its normalised dataset."""

    return OpenIntroSP500Adapter(source, **kwargs).parse()


parse_openintro = parse_openintro_sp500
parse_sp500 = parse_openintro_sp500
load_openintro_sp500 = parse_openintro_sp500
read_openintro_sp500 = parse_openintro_sp500
adapt_openintro_sp500 = parse_openintro_sp500
parse_openintro_sp500_csv = parse_openintro_sp500
read_openintro = parse_openintro_sp500
load_openintro = parse_openintro_sp500
read_openintro_sp500_csv = parse_openintro_sp500
load_openintro_sp500_csv = parse_openintro_sp500
adapt_openintro_sp500_csv = parse_openintro_sp500
parse_openintro_sp500_text = parse_openintro_sp500
openintro_sp500 = parse_openintro_sp500
sp500 = parse_openintro_sp500


__all__ = [
    "OpenIntroSP500Source",
    "OpenIntroSource",
    "OpenIntroSP500Parser",
    "SP500Source",
    "load_openintro_sp500",
    "read_openintro_sp500",
    "adapt_openintro_sp500",
    "parse_openintro_sp500_csv",
    "CANONICAL_COLUMNS",
    "FIELD_ALIASES",
    "SOURCE_ID",
    "SOURCE_NAME",
    "TYPES",
    "UNITS",
    "OpenIntroCSVAdapter",
    "OpenIntro",
    "OpenIntroAdapter",
    "OpenIntroSP500",
    "OpenIntroSP500Adapter",
    "OpenIntroSP500CSV",
    "OpenIntroSP500CSVAdapter",
    "OpenIntroSP500DailyAdapter",
    "OpenIntroSP500FileAdapter",
    "SP500Adapter",
    "SP500OpenIntroAdapter",
    "SP500CSVAdapter",
    "adapt_openintro_sp500_csv",
    "load_openintro",
    "load_openintro_sp500_csv",
    "openintro_sp500",
    "parse_openintro",
    "parse_openintro_sp500",
    "parse_openintro_sp500_text",
    "parse_sp500",
    "read_openintro",
    "read_openintro_sp500_csv",
    "sp500",
]
