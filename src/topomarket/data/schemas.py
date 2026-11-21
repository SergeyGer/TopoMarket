"""Canonical schema contracts for the normalised TopoMarket tables.

The demo and private profiles both materialise the same three analysis tables:

``sp500_daily``
    One row per observed market date with the index close, its price source and
    the log return on the observed calendar.

``industries_daily``
    One row per trading date with one decimal simple-return column for each of
    the twelve standard Kenneth French industry portfolios.

``tda_daily``
    An exact-date inner join of the index, VIX and industry series.  Missing
    dates are not forward filled and missing values stay missing.

The module keeps the contracts in ordinary tuples/dicts so they are cheap to
serialise, easy to compare in tests, and available without importing pandas or
any other third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters.base import SchemaMap

SP500_DAILY = "sp500_daily"
INDUSTRIES_DAILY = "industries_daily"
TDA_DAILY = "tda_daily"

#: Canonical table order used for writing and manifests.
NORMALIZED_TABLE_NAMES: tuple[str, ...] = (SP500_DAILY, INDUSTRIES_DAILY, TDA_DAILY)
NORMALIZED_TABLES = NORMALIZED_TABLE_NAMES
TABLE_NAMES = NORMALIZED_TABLE_NAMES
TABLES = NORMALIZED_TABLE_NAMES

#: The twelve standard French industry portfolios, in their canonical order.
INDUSTRY_NAMES: tuple[str, ...] = (
    "NoDur",
    "Durbl",
    "Manuf",
    "Enrgy",
    "Chems",
    "BusEq",
    "Telcm",
    "Utils",
    "Shops",
    "Hlth",
    "Money",
    "Other",
)


def _industry_code(name: str) -> str:
    """Return the stable lower-case code used in the wide industry table."""

    return "".join(character for character in name.lower() if character.isalnum())


INDUSTRY_CODES: dict[str, str] = {name: _industry_code(name) for name in INDUSTRY_NAMES}
INDUSTRY_CODE_NAMES: tuple[str, ...] = tuple(INDUSTRY_CODES[name] for name in INDUSTRY_NAMES)


def industry_return_column(industry: str) -> str:
    """Return the canonical ``industries_daily`` column for ``industry``."""

    code = INDUSTRY_CODES.get(industry, _industry_code(str(industry)))
    return f"ind_{code}_return"


SP500_DAILY_COLUMNS: tuple[str, ...] = (
    "date",
    "sp500_close",
    "price_source",
    "sp500_log_return",
)
INDUSTRIES_DAILY_COLUMNS: tuple[str, ...] = (
    "date",
    *(industry_return_column(name) for name in INDUSTRY_NAMES),
)
TDA_DAILY_COLUMNS: tuple[str, ...] = (
    "date",
    "sp500_close",
    "sp500_log_return",
    "vix_close",
    *(industry_return_column(name) for name in INDUSTRY_NAMES),
)

SP500_DAILY_TYPES: dict[str, str] = {
    "date": "date",
    "sp500_close": "float",
    "price_source": "string",
    "sp500_log_return": "float",
}
INDUSTRIES_DAILY_TYPES: dict[str, str] = {
    "date": "date",
    **{column: "float" for column in INDUSTRIES_DAILY_COLUMNS if column != "date"},
}
TDA_DAILY_TYPES: dict[str, str] = {
    "date": "date",
    "sp500_close": "float",
    "sp500_log_return": "float",
    "vix_close": "float",
    **{column: "float" for column in TDA_DAILY_COLUMNS[4:]},
}

SP500_DAILY_UNITS: dict[str, str] = {
    "date": "ISO-8601 date",
    "sp500_close": "index points",
    "price_source": "openintro or fred",
    "sp500_log_return": "natural logarithm of simple return",
}
INDUSTRIES_DAILY_UNITS: dict[str, str] = {
    "date": "ISO-8601 date",
    **{column: "decimal simple return" for column in INDUSTRIES_DAILY_COLUMNS if column != "date"},
}
TDA_DAILY_UNITS: dict[str, str] = {
    "date": "ISO-8601 date",
    "sp500_close": "index points",
    "sp500_log_return": "natural logarithm of simple return",
    "vix_close": "VIX index points",
    **{column: "decimal simple return" for column in TDA_DAILY_COLUMNS[4:]},
}

SP500_DAILY_SCHEMA: SchemaMap = SchemaMap(SP500_DAILY_TYPES)
INDUSTRIES_DAILY_SCHEMA: SchemaMap = SchemaMap(INDUSTRIES_DAILY_TYPES)
TDA_DAILY_SCHEMA: SchemaMap = SchemaMap(TDA_DAILY_TYPES)
SP500_SCHEMA = SP500_DAILY_SCHEMA
INDUSTRIES_SCHEMA = INDUSTRIES_DAILY_SCHEMA
INDUSTRY_SCHEMA = INDUSTRIES_DAILY_SCHEMA
TDA_SCHEMA = TDA_DAILY_SCHEMA


@dataclass(frozen=True)
class TableSchema:
    """A frozen description of one normalised table."""

    name: str
    columns: tuple[str, ...]
    types: dict[str, str]
    units: dict[str, str]

    @property
    def schema(self) -> dict[str, str]:
        return dict(self.types)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "columns": list(self.columns),
            "types": dict(self.types),
            "units": dict(self.units),
        }


SP500_DAILY_CONTRACT = TableSchema(
    SP500_DAILY, SP500_DAILY_COLUMNS, SP500_DAILY_TYPES, SP500_DAILY_UNITS
)
INDUSTRIES_DAILY_CONTRACT = TableSchema(
    INDUSTRIES_DAILY, INDUSTRIES_DAILY_COLUMNS, INDUSTRIES_DAILY_TYPES, INDUSTRIES_DAILY_UNITS
)
TDA_DAILY_CONTRACT = TableSchema(TDA_DAILY, TDA_DAILY_COLUMNS, TDA_DAILY_TYPES, TDA_DAILY_UNITS)
SCHEMA_CONTRACTS: dict[str, TableSchema] = {
    SP500_DAILY: SP500_DAILY_CONTRACT,
    INDUSTRIES_DAILY: INDUSTRIES_DAILY_CONTRACT,
    TDA_DAILY: TDA_DAILY_CONTRACT,
}
TABLE_CONTRACTS = SCHEMA_CONTRACTS

COLUMNS: dict[str, tuple[str, ...]] = {
    SP500_DAILY: SP500_DAILY_COLUMNS,
    INDUSTRIES_DAILY: INDUSTRIES_DAILY_COLUMNS,
    TDA_DAILY: TDA_DAILY_COLUMNS,
}
TABLE_COLUMNS = COLUMNS
TYPES: dict[str, dict[str, str]] = {
    SP500_DAILY: SP500_DAILY_TYPES,
    INDUSTRIES_DAILY: INDUSTRIES_DAILY_TYPES,
    TDA_DAILY: TDA_DAILY_TYPES,
}
TABLE_TYPES = TYPES
UNITS: dict[str, dict[str, str]] = {
    SP500_DAILY: SP500_DAILY_UNITS,
    INDUSTRIES_DAILY: INDUSTRIES_DAILY_UNITS,
    TDA_DAILY: TDA_DAILY_UNITS,
}
TABLE_UNITS = UNITS
SCHEMAS: dict[str, dict[str, str]] = {
    SP500_DAILY: SP500_DAILY_SCHEMA,
    INDUSTRIES_DAILY: INDUSTRIES_DAILY_SCHEMA,
    TDA_DAILY: TDA_DAILY_SCHEMA,
}
TABLE_SCHEMAS = SCHEMAS
NORMALIZED_SCHEMAS = SCHEMAS
SCHEMA_MAP = SCHEMAS

NORMALIZED_FILE_NAMES: tuple[str, ...] = tuple(f"{name}.csv" for name in NORMALIZED_TABLE_NAMES)
NORMALIZED_FILES = NORMALIZED_FILE_NAMES
TABLE_FILE_NAMES = NORMALIZED_FILE_NAMES


def canonical_table_name(name: str) -> str:
    """Return the canonical table name for ``name`` or raise ``KeyError``."""

    key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "sp500": SP500_DAILY,
        "s_p_500": SP500_DAILY,
        "sp_500_daily": SP500_DAILY,
        "sp500_daily": SP500_DAILY,
        "industries": INDUSTRIES_DAILY,
        "industry_daily": INDUSTRIES_DAILY,
        "french_12_industries": INDUSTRIES_DAILY,
        "tda": TDA_DAILY,
        "topology_daily": TDA_DAILY,
        "topological_daily": TDA_DAILY,
    }
    canonical = aliases.get(key, key)
    if canonical not in SCHEMA_CONTRACTS:
        raise KeyError(f"unknown normalised table: {name!r}")
    return canonical


def schema_for(name: str) -> dict[str, str]:
    """Return the column-to-type contract for a normalised table."""

    return dict(SCHEMA_CONTRACTS[canonical_table_name(name)].types)


def columns_for(name: str) -> tuple[str, ...]:
    """Return the ordered columns for a normalised table."""

    return SCHEMA_CONTRACTS[canonical_table_name(name)].columns


def types_for(name: str) -> dict[str, str]:
    """Return the column-to-type mapping for a normalised table."""

    return dict(SCHEMA_CONTRACTS[canonical_table_name(name)].types)


def units_for(name: str) -> dict[str, str]:
    """Return the column-to-unit mapping for a normalised table."""

    return dict(SCHEMA_CONTRACTS[canonical_table_name(name)].units)


def contracts_as_dict() -> dict[str, dict[str, Any]]:
    """Return every contract as a JSON-friendly mapping."""

    return {name: contract.as_dict() for name, contract in SCHEMA_CONTRACTS.items()}


__all__ = [
    "COLUMNS",
    "INDUSTRIES_DAILY",
    "INDUSTRIES_DAILY_COLUMNS",
    "INDUSTRIES_DAILY_CONTRACT",
    "INDUSTRIES_DAILY_SCHEMA",
    "INDUSTRIES_DAILY_TYPES",
    "INDUSTRIES_DAILY_UNITS",
    "INDUSTRY_CODES",
    "INDUSTRY_CODE_NAMES",
    "INDUSTRY_NAMES",
    "NORMALIZED_FILES",
    "NORMALIZED_FILE_NAMES",
    "NORMALIZED_SCHEMAS",
    "NORMALIZED_TABLES",
    "NORMALIZED_TABLE_NAMES",
    "SCHEMAS",
    "SCHEMA_CONTRACTS",
    "SP500_SCHEMA",
    "INDUSTRIES_SCHEMA",
    "INDUSTRY_SCHEMA",
    "TDA_SCHEMA",
    "SCHEMA_MAP",
    "SP500_DAILY",
    "SP500_DAILY_COLUMNS",
    "SP500_DAILY_CONTRACT",
    "SP500_DAILY_SCHEMA",
    "SP500_DAILY_TYPES",
    "SP500_DAILY_UNITS",
    "TABLES",
    "TABLE_COLUMNS",
    "TABLE_CONTRACTS",
    "TABLE_FILE_NAMES",
    "TABLE_NAMES",
    "TABLE_SCHEMAS",
    "TABLE_TYPES",
    "TABLE_UNITS",
    "TDA_DAILY",
    "TDA_DAILY_COLUMNS",
    "TDA_DAILY_CONTRACT",
    "TDA_DAILY_SCHEMA",
    "TDA_DAILY_TYPES",
    "TDA_DAILY_UNITS",
    "TYPES",
    "UNITS",
    "TableSchema",
    "canonical_table_name",
    "columns_for",
    "contracts_as_dict",
    "industry_return_column",
    "schema_for",
    "types_for",
    "units_for",
]
