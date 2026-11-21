"""Adapter for the Kenneth R. French Data Library 12 Industry Portfolios."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from typing import Any

from .base import (
    BaseAdapter,
    DateParseError,
    NormalizedDataset,
    ParsedSource,
    Row,
    coerce_number,
    detect_delimiter,
    normalize_key,
    parse_date,
    read_csv_table,
)

SOURCE_ID = "french_12_industries"
SOURCE_NAME = "Kenneth French 12 Industry Portfolios"
CANONICAL_COLUMNS = ("date", "industry", "value_weighted_return", "equal_weighted_return")
LONG_COLUMNS = ("date", "industry", "weighting", "return")
UNITS: Mapping[str, str] = {
    "date": "ISO-8601 date",
    "industry": "industry code",
    "value_weighted_return": "percent",
    "equal_weighted_return": "percent",
}
TYPES = {
    "date": "date",
    "industry": "string",
    "value_weighted_return": "float",
    "equal_weighted_return": "float",
}

# The standard 12-industry names.  Keeping them lets content sniffing work even
# when the supplied archive uses a generic file name such as ``returns.csv``.
INDUSTRY_NAMES = (
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
#: Stable lower-case codes used by the downstream wide industry table.
INDUSTRY_CODES = {name: normalize_key(name) for name in INDUSTRY_NAMES}
_FF_MISSING_THRESHOLD = -99.0


def _line_row(line: str, delimiter: str) -> list[str]:
    try:
        return [cell.strip() for cell in next(csv.reader(io.StringIO(line), delimiter=delimiter))]
    except (csv.Error, StopIteration):  # pragma: no cover - defensive
        return []


def _section_weighting(line: str) -> str | None:
    lowered = line.lower()
    if "equal" in lowered and ("weight" in lowered or "return" in lowered):
        return "equal"
    if "value" in lowered and ("weight" in lowered or "return" in lowered):
        return "value"
    return None


def _looks_like_header(row: list[str]) -> bool:
    if len(row) < 2:
        return False
    cells = [cell for cell in row if cell]
    if len(cells) < 2:
        return False
    lowered = " ".join(cells).lower()
    prose_markers = ("created by", "database", "copyright", "return", "average")
    if any(word in lowered for word in prose_markers):
        # A descriptive line can contain many comma-separated words; real
        # headers are short industry labels and do not contain these phrases.
        if "average" not in lowered or len(cells) < 3:
            return False
    # Data rows have numeric date and numeric values.  A header has at most one
    # numeric-looking cell (the optional Date label is not numeric).
    numeric_cells = sum(1 for cell in cells if coerce_number(cell) is not None)
    if numeric_cells > 1:
        return False
    # Industry labels are compact; reject prose.
    if any(len(cell) > 40 for cell in cells):
        return False
    return True


def _find_header(lines: list[str], start: int, delimiter: str) -> int | None:
    for index in range(start, min(len(lines), start + 80)):
        line = lines[index].strip()
        if not line:
            continue
        row = _line_row(line, delimiter)
        if _looks_like_header(row):
            return index
    return None


def _parse_section(
    lines: list[str], header_index: int, delimiter: str
) -> tuple[dict[str, dict[str, float | None]], list[str], int]:
    header = _line_row(lines[header_index], delimiter)
    industries: list[str] = []
    columns: list[int] = []
    for index, cell in enumerate(header):
        if index == 0 and (not cell or normalize_key(cell) in {"date", "dates", "day", "period"}):
            continue
        if not cell:
            continue
        industries.append(cell.strip())
        columns.append(index)
    if not industries and len(header) > 1:
        industries = [
            cell.strip() or f"industry_{index}" for index, cell in enumerate(header[1:], 1)
        ]
        columns = list(range(1, len(header)))

    values: dict[str, dict[str, float | None]] = {}
    index = header_index + 1
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            if values:
                index += 1
                break
            index += 1
            continue
        if _section_weighting(stripped) is not None and values:
            break
        row = _line_row(stripped, delimiter)
        if len(row) <= 0:
            index += 1
            continue
        try:
            parsed = parse_date(row[0])
        except DateParseError:
            if values:
                break
            index += 1
            continue
        if parsed is None:
            index += 1
            continue
        per_industry: dict[str, float | None] = {}
        for industry, column in zip(industries, columns, strict=False):
            raw = row[column] if column < len(row) else None
            number = coerce_number(raw)
            if number is not None and float(number) <= _FF_MISSING_THRESHOLD:
                number = None
            per_industry[industry] = number
        values[parsed] = per_industry
        index += 1
    return values, industries, index


class French12IndustryAdapter(BaseAdapter):
    """Parse the daily (or monthly) 12-industry portfolio return file.

    The normalised table is wide: one row per date and industry with separate
    value-weighted and equal-weighted return columns.  :meth:`parse_long` is
    available for callers that prefer the long/tidy representation.
    """

    source_id = SOURCE_ID
    source_name = SOURCE_NAME
    aliases = (
        "french",
        "kenneth_french",
        "ken_french",
        "fama_french",
        "industry",
        "industries",
        "12_industry",
        "12_industries",
        "12industry",
    )
    filename_patterns = (
        "french",
        "kenneth",
        "fama",
        "industry",
        "industries",
        "12_industry",
        "12industry",
    )
    required = True
    canonical_columns = CANONICAL_COLUMNS
    units = UNITS
    types = TYPES

    def matches(self, filename: str, text: str | None = None) -> bool:
        if super().matches(filename, text):
            return True
        if not text:
            return False
        lowered = text.lower()
        if "industry portfolios" in lowered or "12 industry" in lowered:
            return True
        found = sum(1 for name in INDUSTRY_NAMES if name.lower() in lowered)
        return found >= 4

    def _parse_long_rows(
        self, source: ParsedSource
    ) -> tuple[list[Row], dict[str, str], dict[str, str], list[str]] | None:
        """Parse an already-tidy long table, if the header looks like one."""

        table, warnings = read_csv_table(source)
        keys = set(table.keys)
        if "industry" not in keys:
            return None
        value_columns = {
            "value_weighted_return",
            "equal_weighted_return",
            "weighted_return",
            "return",
            "value",
        }
        if not keys & value_columns:
            return None
        date_index = table.date_index()
        industry_index = next(
            (index for index, key in enumerate(table.keys) if key == "industry"), None
        )
        if industry_index is None:
            return None
        weighting_index = next(
            (index for index, key in enumerate(table.keys) if key in {"weighting", "weight"}),
            None,
        )
        return_index = next(
            (
                index
                for index, key in enumerate(table.keys)
                if key in {"return", "value", "weighted_return"}
            ),
            None,
        )
        vw_index = next(
            (
                index
                for index, key in enumerate(table.keys)
                if key in {"value_weighted_return", "vw_return", "vw"}
            ),
            None,
        )
        ew_index = next(
            (
                index
                for index, key in enumerate(table.keys)
                if key in {"equal_weighted_return", "ew_return", "ew"}
            ),
            None,
        )
        rows: list[Row] = []
        for raw_row in table.rows:
            if len(raw_row) <= max(date_index, industry_index):
                continue
            try:
                date_value = parse_date(raw_row[date_index])
            except DateParseError:
                continue
            if date_value is None:
                continue
            industry = str(raw_row[industry_index]).strip()
            if not industry:
                continue
            if weighting_index is not None and return_index is not None:
                weighting = str(raw_row[weighting_index]).strip().lower()
                value = coerce_number(raw_row[return_index])
                if value is not None and float(value) <= _FF_MISSING_THRESHOLD:
                    value = None
                rows.append(
                    Row(
                        {
                            "date": date_value,
                            "industry": industry,
                            "weighting": "equal" if "equal" in weighting else "value",
                            "return": value,
                        }
                    )
                )
            else:
                rows.append(
                    Row(
                        {
                            "date": date_value,
                            "industry": industry,
                            "value_weighted_return": (
                                coerce_number(raw_row[vw_index])
                                if vw_index is not None and vw_index < len(raw_row)
                                else None
                            ),
                            "equal_weighted_return": (
                                coerce_number(raw_row[ew_index])
                                if ew_index is not None and ew_index < len(raw_row)
                                else None
                            ),
                        }
                    )
                )
        if not rows:
            return None
        if weighting_index is not None and return_index is not None:
            types = {
                "date": "date",
                "industry": "string",
                "weighting": "string",
                "return": "float",
            }
            units = {
                "date": "ISO-8601 date",
                "industry": "industry code",
                "weighting": "value or equal",
                "return": "percent",
            }
        else:
            types = dict(TYPES)
            units = dict(UNITS)
        rows.sort(key=lambda item: (str(item.get("date")), str(item.get("industry"))))
        return rows, types, units, warnings

    def _parse_rows(
        self, source: ParsedSource
    ) -> tuple[list[Row], dict[str, str], dict[str, str], list[str]]:
        long_rows = self._parse_long_rows(source)
        if long_rows is not None:
            return long_rows
        lines = source.text.splitlines()
        delimiter = detect_delimiter(source.text)
        warnings: list[str] = []
        sections: list[tuple[str, dict[str, dict[str, float | None]], list[str]]] = []

        index = 0
        while index < len(lines):
            weighting = _section_weighting(lines[index])
            if weighting is None:
                index += 1
                continue
            header_index = _find_header(lines, index + 1, delimiter)
            if header_index is None:
                warnings.append(f"no header found after section marker: {lines[index].strip()}")
                index += 1
                continue
            values, industries, next_index = _parse_section(lines, header_index, delimiter)
            if values:
                sections.append((weighting, values, industries))
            else:
                warnings.append(f"no observations found in section: {lines[index].strip()}")
            index = max(next_index, header_index + 1)

        if not sections:
            header_index = _find_header(lines, 0, delimiter)
            if header_index is None:
                return [], {}, dict(UNITS), warnings + ["no industry return table found"]
            values, industries, _next = _parse_section(lines, header_index, delimiter)
            if values:
                sections.append(("value", values, industries))
            else:
                return [], {}, dict(UNITS), warnings + ["no industry return observations found"]

        value_section = next((section for section in sections if section[0] == "value"), None)
        equal_section = next((section for section in sections if section[0] == "equal"), None)
        if equal_section is None:
            warnings.append("equal-weighted section not found")

        industries: list[str] = []
        for _weighting, _values, names in sections:
            for name in names:
                if name not in industries:
                    industries.append(name)

        dates = sorted(
            {date_value for _weighting, values, _names in sections for date_value in values}
        )
        rows: list[Row] = []
        for date_value in dates:
            for industry in industries:
                rows.append(
                    Row(
                        {
                            "date": date_value,
                            "industry": industry,
                            "value_weighted_return": (
                                value_section[1].get(date_value, {}).get(industry)
                                if value_section is not None
                                else None
                            ),
                            "equal_weighted_return": (
                                equal_section[1].get(date_value, {}).get(industry)
                                if equal_section is not None
                                else None
                            ),
                        }
                    )
                )

        schema = dict(TYPES)
        units = dict(UNITS)
        return rows, schema, units, warnings

    def _as_dataset(self, source: Any = None, **kwargs: Any) -> NormalizedDataset:
        if isinstance(source, NormalizedDataset):
            return source
        return self.parse(source, **kwargs)

    def parse_long(self, source: Any = None, **kwargs: Any) -> NormalizedDataset:
        """Return the tidy (date, industry, weighting, return) representation."""

        wide = self._as_dataset(source, **kwargs)
        long_rows: list[Row] = []
        for row in wide:
            for weighting, column in (
                ("value", "value_weighted_return"),
                ("equal", "equal_weighted_return"),
            ):
                value = row.get(column)
                if value is None:
                    continue
                long_rows.append(
                    Row(
                        {
                            "date": row["date"],
                            "industry": row["industry"],
                            "weighting": weighting,
                            "return": value,
                        }
                    )
                )
        return NormalizedDataset(
            long_rows,
            source_id=self.source_id,
            source_name=self.source_name,
            columns=list(LONG_COLUMNS),
            units={
                "date": "ISO-8601 date",
                "industry": "industry code",
                "weighting": "value or equal",
                "return": "percent",
            },
            types={
                "date": "date",
                "industry": "string",
                "weighting": "string",
                "return": "float",
            },
            metadata={"filename": wide.metadata.get("filename")},
        )

    parse_tidy = parse_long

    def _industries(self, data: NormalizedDataset) -> list[str]:
        industries: list[str] = []
        for row in data:
            industry = row.get("industry")
            if industry is not None and industry not in industries:
                industries.append(str(industry))
        return industries

    def parse_industry_columns(self, source: Any = None, **kwargs: Any) -> NormalizedDataset:
        """Return a date-by-industry matrix with value/equal return columns."""

        data = self._as_dataset(source, **kwargs)
        industries = self._industries(data)
        columns = ["date"]
        for industry in industries:
            columns.append(f"{industry}_value_weighted_return")
            columns.append(f"{industry}_equal_weighted_return")
        by_date: dict[str, Row] = {}
        for row in data:
            date_value = str(row["date"])
            record = by_date.setdefault(date_value, Row({"date": date_value}))
            industry = str(row["industry"])
            record[f"{industry}_value_weighted_return"] = row.get("value_weighted_return")
            record[f"{industry}_equal_weighted_return"] = row.get("equal_weighted_return")
        return NormalizedDataset(
            [by_date[key] for key in sorted(by_date)],
            source_id=self.source_id,
            source_name=self.source_name,
            columns=columns,
            units={
                "date": "ISO-8601 date",
                **{
                    f"{industry}_value_weighted_return": "percent"
                    for industry in industries
                },
                **{
                    f"{industry}_equal_weighted_return": "percent"
                    for industry in industries
                },
            },
            types={"date": "date"},
            metadata=dict(data.metadata),
        )

    def parse_industry_returns(
        self,
        source: Any = None,
        *,
        weighting: str = "value",
        **kwargs: Any,
    ) -> NormalizedDataset:
        """Return one row per date with twelve ``ind_<code>_return`` columns.

        This is the shape used by the downstream ``industries_daily`` table.
        ``weighting`` selects the value-weighted (default) or equal-weighted
        return section.
        """

        data = self._as_dataset(source, **kwargs)
        industries = self._industries(data)
        equal = str(weighting).strip().lower().startswith(("equal", "ew"))
        source_column = "equal_weighted_return" if equal else "value_weighted_return"
        codes = {
            industry: INDUSTRY_CODES.get(industry, normalize_key(industry))
            for industry in industries
        }
        columns = ["date", *(f"ind_{codes[industry]}_return" for industry in industries)]
        by_date: dict[str, Row] = {}
        for row in data:
            date_value = str(row["date"])
            record = by_date.setdefault(date_value, Row({"date": date_value}))
            industry = str(row["industry"])
            record[f"ind_{codes[industry]}_return"] = row.get(source_column)
        return NormalizedDataset(
            [by_date[key] for key in sorted(by_date)],
            source_id=self.source_id,
            source_name=self.source_name,
            columns=columns,
            units={
                "date": "ISO-8601 date",
                **{column: "percent" for column in columns if column != "date"},
            },
            types={"date": "date", **{column: "float" for column in columns if column != "date"}},
            metadata={**dict(data.metadata), "weighting": "equal" if equal else "value"},
        )

    parse_matrix = parse_industry_columns
    parse_wide = parse_industry_returns
    parse_returns = parse_industry_returns


# Keep upper-case metadata available on the class as well as the module.
French12IndustryAdapter.SOURCE_ID = SOURCE_ID
French12IndustryAdapter.SOURCE_NAME = SOURCE_NAME
French12IndustryAdapter.columns = CANONICAL_COLUMNS
French12IndustryAdapter.UNITS = UNITS
French12IndustryAdapter.TYPES = TYPES

French12IndustriesAdapter = French12IndustryAdapter
FrenchIndustriesAdapter = French12IndustryAdapter
KennethFrench12IndustriesAdapter = French12IndustryAdapter
KennethFrenchAdapter = French12IndustryAdapter
FamaFrench12IndustryAdapter = French12IndustryAdapter
French12IndustryCSVAdapter = French12IndustryAdapter
French12IndustriesCSVAdapter = French12IndustryAdapter
KennethFrench12IndustryAdapter = French12IndustryAdapter
FrenchAdapter = French12IndustryAdapter
French12 = French12IndustryAdapter
FrenchIndustries = French12IndustryAdapter
French12IndustryDailyAdapter = French12IndustryAdapter
French12IndustryPortfoliosAdapter = French12IndustryAdapter
KennethFrench12IndustryPortfoliosAdapter = French12IndustryAdapter

French12IndustrySource = French12IndustryAdapter
French12IndustriesSource = French12IndustryAdapter
FrenchSource = French12IndustryAdapter
French12IndustryParser = French12IndustryAdapter


def parse_french_12_industries(source: Any, **kwargs: Any) -> NormalizedDataset:
    """Parse a French 12-industry return file and return a wide dataset."""

    return French12IndustryAdapter(source, **kwargs).parse()


parse_french = parse_french_12_industries
parse_french_12 = parse_french_12_industries
load_french_12_industries = parse_french_12_industries
read_french_12_industries = parse_french_12_industries
adapt_french_12_industries = parse_french_12_industries
parse_french_12_industries_csv = parse_french_12_industries
parse_industries = parse_french_12_industries
read_french = parse_french_12_industries
load_french = parse_french_12_industries
read_french_12_industries_csv = parse_french_12_industries
load_french_12_industries_csv = parse_french_12_industries
adapt_french_12_industries_csv = parse_french_12_industries
parse_french_12_industries_text = parse_french_12_industries
french_12_industries = parse_french_12_industries
french_12 = parse_french_12_industries


__all__ = [
    "French12IndustrySource",
    "French12IndustriesSource",
    "FrenchSource",
    "French12IndustryParser",
    "load_french_12_industries",
    "read_french_12_industries",
    "adapt_french_12_industries",
    "parse_french_12_industries_csv",
    "CANONICAL_COLUMNS",
    "INDUSTRY_CODES",
    "INDUSTRY_NAMES",
    "LONG_COLUMNS",
    "SOURCE_ID",
    "SOURCE_NAME",
    "TYPES",
    "UNITS",
    "FamaFrench12IndustryAdapter",
    "French12",
    "French12IndustriesAdapter",
    "French12IndustriesCSVAdapter",
    "French12IndustryAdapter",
    "French12IndustryCSVAdapter",
    "French12IndustryDailyAdapter",
    "French12IndustryPortfoliosAdapter",
    "FrenchAdapter",
    "FrenchIndustries",
    "FrenchIndustriesAdapter",
    "KennethFrench12IndustriesAdapter",
    "KennethFrench12IndustryAdapter",
    "KennethFrench12IndustryPortfoliosAdapter",
    "KennethFrenchAdapter",
    "adapt_french_12_industries_csv",
    "french_12",
    "french_12_industries",
    "load_french",
    "load_french_12_industries_csv",
    "parse_french",
    "parse_french_12",
    "parse_french_12_industries",
    "parse_french_12_industries_text",
    "parse_industries",
    "read_french",
    "read_french_12_industries_csv",
]
