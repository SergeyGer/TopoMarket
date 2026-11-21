"""Optional adapter for the Office of Financial Research Financial Stress Index."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import BaseAdapter, NormalizedDataset, ParsedSource, Row, standard_rows

SOURCE_ID = "ofr_fsi"
SOURCE_NAME = "OFR Financial Stress Index"
CANONICAL_COLUMNS = ("date", "value")
UNITS: Mapping[str, str] = {
    "date": "ISO-8601 date",
    "value": "index points (signed)",
}
TYPES = {"date": "date", "value": "float"}
FIELD_ALIASES = {
    "value": (
        "value",
        "fsi",
        "ofr_fsi",
        "ofrfsi",
        "ofr_financial_stress_index",
        "financial_stress_index",
        "financial_stress",
        "stress_index",
        "index",
    ),
}
_VALUE_ALIASES = (
    "fsi",
    "ofr_fsi",
    "ofrfsi",
    "financial_stress_index",
    "financial_stress",
    "stress_index",
    "value",
    "index",
)


class OFRFSIAdapter(BaseAdapter):
    """Parse the optional OFR Financial Stress Index CSV export."""

    source_id = SOURCE_ID
    source_name = SOURCE_NAME
    aliases = ("ofr", "ofr_fsi", "fsi", "financial_stress", "financial_stress_index")
    filename_patterns = ("ofr", "fsi", "financial_stress", "stress_index")
    required = False
    optional = True
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
            warnings.append("no dated OFR FSI observations were found")
        return rows, schema, units, warnings


# Keep upper-case metadata available on the class as well as the module.
OFRFSIAdapter.SOURCE_ID = SOURCE_ID
OFRFSIAdapter.SOURCE_NAME = SOURCE_NAME
OFRFSIAdapter.columns = CANONICAL_COLUMNS
OFRFSIAdapter.UNITS = UNITS
OFRFSIAdapter.TYPES = TYPES

OFRAdapter = OFRFSIAdapter
OFFRFSIAdapter = OFRFSIAdapter
OFRFSI = OFRFSIAdapter
OFR = OFRFSIAdapter
FinancialStressIndexAdapter = OFRFSIAdapter
OFRFinancialStressIndexAdapter = OFRFSIAdapter
OFRFSICSVAdapter = OFRFSIAdapter
OFFRFSICSVAdapter = OFRFSIAdapter
FinancialStressIndexCSVAdapter = OFRFSIAdapter

OFRFSISource = OFRFSIAdapter
OFRSource = OFRFSIAdapter
OFRFSIParser = OFRFSIAdapter
FinancialStressIndexSource = OFRFSIAdapter
OFRFSIHistoryAdapter = OFRFSIAdapter
FinancialStressAdapter = OFRFSIAdapter
OFRFinancialStressAdapter = OFRFSIAdapter
OFRFSICSV = OFRFSIAdapter


def parse_ofr_fsi(source: Any, **kwargs: Any) -> NormalizedDataset:
    """Parse an OFR FSI CSV file and return its normalised dataset."""

    return OFRFSIAdapter(source, **kwargs).parse()


parse_ofr = parse_ofr_fsi
parse_fsi = parse_ofr_fsi
load_ofr_fsi = parse_ofr_fsi
read_ofr_fsi = parse_ofr_fsi
adapt_ofr_fsi = parse_ofr_fsi
parse_ofr_fsi_csv = parse_ofr_fsi
read_ofr = parse_ofr_fsi
load_ofr = parse_ofr_fsi
read_ofr_fsi_csv = parse_ofr_fsi
load_ofr_fsi_csv = parse_ofr_fsi
adapt_ofr_fsi_csv = parse_ofr_fsi
parse_ofr_fsi_text = parse_ofr_fsi
ofr_fsi = parse_ofr_fsi
fsi = parse_ofr_fsi


__all__ = [
    "OFRFSISource",
    "OFRSource",
    "OFRFSIParser",
    "FinancialStressIndexSource",
    "load_ofr_fsi",
    "read_ofr_fsi",
    "adapt_ofr_fsi",
    "parse_ofr_fsi_csv",
    "CANONICAL_COLUMNS",
    "FIELD_ALIASES",
    "SOURCE_ID",
    "SOURCE_NAME",
    "TYPES",
    "UNITS",
    "FinancialStressAdapter",
    "FinancialStressIndexAdapter",
    "FinancialStressIndexCSVAdapter",
    "OFR",
    "OFRFinancialStressAdapter",
    "OFRAdapter",
    "OFRFSI",
    "OFRFSIAdapter",
    "OFRFSICSV",
    "OFRFSICSVAdapter",
    "OFRFSIHistoryAdapter",
    "OFRFinancialStressIndexAdapter",
    "OFFRFSIAdapter",
    "OFFRFSICSVAdapter",
    "adapt_ofr_fsi_csv",
    "fsi",
    "load_ofr",
    "load_ofr_fsi_csv",
    "ofr_fsi",
    "parse_fsi",
    "parse_ofr",
    "parse_ofr_fsi",
    "parse_ofr_fsi_text",
    "read_ofr",
    "read_ofr_fsi_csv",
]
