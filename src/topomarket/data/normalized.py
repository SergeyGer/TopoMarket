"""Build, validate and write the normalised TopoMarket analysis tables.

The functions in this module are intentionally dependency-free.  They accept
the :class:`~topomarket.data.adapters.base.NormalizedDataset` objects produced
by the seed-file adapters (or plain mappings) and return datasets that follow
the contracts in :mod:`topomarket.data.schemas`.

The A2 contract enforces:

* ``sp500_daily`` uses OpenIntro through 2018-12-07 inclusive and observed FRED
  closes strictly after that cutover, with log returns on the observed market
  calendar;
* industry returns are decimal simple returns (the French source is expressed
  in percent and is divided by 100 exactly once);
* ``tda_daily`` is an exact-date inner join of the index, industry and VIX
  series -- there is no forward fill or interpolation, so missing values stay
  missing and missing dates are not invented;
* output order is deterministic: rows are sorted by ``date`` and columns use
  the canonical order from the schema contract.
"""

from __future__ import annotations

import csv
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .adapters.base import NormalizedDataset, Row, coerce_number, normalize_key, parse_date
from .manifest import atomic_write_json, ensure_data_directory
from .schemas import *  # noqa: F401,F403 - re-export the schema contracts
from .schemas import (
    COLUMNS,
    INDUSTRIES_DAILY,
    INDUSTRIES_DAILY_COLUMNS,
    INDUSTRIES_DAILY_TYPES,
    INDUSTRIES_DAILY_UNITS,
    INDUSTRY_CODES,
    INDUSTRY_NAMES,
    NORMALIZED_FILE_NAMES,
    NORMALIZED_TABLE_NAMES,
    SCHEMA_CONTRACTS,
    SP500_DAILY,
    SP500_DAILY_COLUMNS,
    SP500_DAILY_TYPES,
    SP500_DAILY_UNITS,
    TDA_DAILY,
    TDA_DAILY_COLUMNS,
    TDA_DAILY_TYPES,
    TDA_DAILY_UNITS,
    TableSchema,
    canonical_table_name,
    contracts_as_dict,
)
from .schemas import __all__ as _SCHEMAS_ALL

#: Deterministic demo window.  The synthetic generator uses the same start
#: date and day count so the demo tables line up with the existing fixtures.
DEMO_START_DATE = date(2024, 1, 1)
DEMO_DAY_COUNT = 30

#: OpenIntro is authoritative through this date; FRED supplies later closes.
SP500_CUTOVER_DATE = date(2018, 12, 7)

#: Directory below a data directory that mirrors the normalised CSV files.
NORMALIZED_DIRNAME = "normalized"
NORMALIZED_SCHEMA_FILENAME = "schemas.json"
NORMALIZED_TABLES_FILENAME = "normalized_tables.json"

_VIX_SOURCE_IDS = {"cboe_vix", "cboe", "vix", "vix_history"}
_OPENINTRO_SOURCE_IDS = {"openintro_sp500", "openintro", "sp500_openintro"}
_FRED_SOURCE_IDS = {"fred_sp500", "fred", "sp500_fred"}

SP500_PRICE_SOURCES = ("openintro", "fred")


def _is_dataset(value: Any) -> bool:
    return isinstance(value, NormalizedDataset)


def _source_id_of(value: Any) -> str:
    if _is_dataset(value):
        return normalize_key(getattr(value, "source_id", "") or "")
    if isinstance(value, Mapping):
        return normalize_key(str(value.get("source_id") or value.get("source") or ""))
    return ""


def _as_rows(source: Any) -> list[Mapping[str, Any]]:
    """Return rows from a dataset, a mapping of datasets or an iterable."""

    if source is None:
        return []
    if _is_dataset(source):
        return list(source)
    if isinstance(source, Mapping):
        # A single row mapping is accepted for convenience; otherwise treat a
        # mapping as a collection of datasets/row iterables keyed by source id.
        if "date" in source or "observation_date" in source or "obs_date" in source:
            return [source]
        rows: list[Mapping[str, Any]] = []
        for value in source.values():
            rows.extend(_as_rows(value))
        return rows
    if isinstance(source, (str, bytes, bytearray)):
        raise TypeError("expected a dataset or an iterable of rows, not a string")
    try:
        items = list(source)
    except TypeError as exc:  # pragma: no cover - defensive
        raise TypeError(f"expected an iterable of rows, got {type(source).__name__}") from exc
    rows = []
    for item in items:
        if isinstance(item, Mapping):
            rows.append(item)
        elif _is_dataset(item) or (
            isinstance(item, Iterable) and not isinstance(item, (str, bytes, bytearray))
        ):
            rows.extend(_as_rows(item))
    return rows


def _coerce_value(value: Any, column_type: str) -> Any:
    if value is None:
        return None
    if column_type == "date":
        return parse_date(value)
    if column_type == "integer":
        number = coerce_number(value)
        return None if number is None else int(number)
    if column_type == "float":
        number = coerce_number(value)
        return None if number is None else float(number)
    text = str(value).strip()
    return text or None


def _normalise_rows(
    rows: Iterable[Mapping[str, Any]],
    columns: Sequence[str],
    types: Mapping[str, str],
) -> list[Row]:
    """Coerce, order and de-duplicate rows for a canonical table."""

    records: dict[str, Row] = {}
    for raw in rows:
        record = Row({column: raw.get(column) for column in columns})
        record["date"] = _coerce_value(record.get("date"), "date")
        if record["date"] is None:
            continue
        for column in columns:
            if column == "date":
                continue
            record[column] = _coerce_value(record.get(column), types.get(column, "float"))
        existing = records.get(str(record["date"]))
        if existing is None:
            records[str(record["date"])] = record
            continue
        # Combine duplicate observations without inventing values.  The first
        # observation wins for fields it actually provides; later observations
        # only fill fields that were missing.
        for column in columns:
            if existing.get(column) is None and record.get(column) is not None:
                existing[column] = record[column]
    return [records[key] for key in sorted(records)]


def _dataset(
    name: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    source_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> NormalizedDataset:
    contract = SCHEMA_CONTRACTS[name]
    ordered = _normalise_rows(rows, contract.columns, contract.types)
    return NormalizedDataset(
        ordered,
        source_id=source_id or name,
        source_name=name,
        columns=list(contract.columns),
        units=dict(contract.units),
        types=dict(contract.types),
        metadata=dict(metadata or {}),
    )


def empty_table(name: str, *, source_id: str | None = None) -> NormalizedDataset:
    """Return an empty dataset carrying the full schema for ``name``."""

    return _dataset(name, [], source_id=source_id)


def _positive_number(value: Any) -> float | None:
    number = coerce_number(value)
    if number is None:
        return None
    value_float = float(number)
    if not math.isfinite(value_float) or value_float <= 0:
        return None
    return value_float


def _sp500_kind(rows: Sequence[Mapping[str, Any]], hint: str = "") -> str:
    """Classify one group of rows as openintro, fred or canonical."""

    key = normalize_key(hint)
    source_hint = key
    for row in rows:
        if isinstance(row, Mapping):
            row_source = normalize_key(str(row.get("source_id") or row.get("source") or ""))
            if row_source:
                source_hint = row_source
                break
    if source_hint in _OPENINTRO_SOURCE_IDS:
        return "openintro"
    if source_hint in _FRED_SOURCE_IDS:
        return "fred"
    keys = {normalize_key(str(name)) for row in rows for name in row}
    if keys & {"sp500_close", "price_source", "sp500_log_return"}:
        return "canonical"
    if "close" in keys and (keys & {"open", "high", "low", "volume", "adj_close"}):
        return "openintro"
    if "value" in keys or "sp500" in keys:
        return "fred"
    if "close" in keys:
        return "openintro"
    return "canonical"


def _iter_sp500_groups(
    source: Any, hint: str = ""
) -> Iterable[tuple[str, list[Mapping[str, Any]]]]:
    """Yield ``(kind, rows)`` groups from a dataset, mapping or iterable."""

    if source is None:
        return
    if _is_dataset(source):
        rows = list(source)
        yield _sp500_kind(rows, hint or _source_id_of(source)), rows
        return
    if isinstance(source, Mapping):
        keys = {normalize_key(str(key)) for key in source}
        if keys & {"sp500_close", "price_source", "sp500_log_return"}:
            yield "canonical", [source]
            return
        if keys & (_OPENINTRO_SOURCE_IDS | _FRED_SOURCE_IDS):
            for key, value in source.items():
                yield from _iter_sp500_groups(value, str(key))
            return
        if "date" in keys or "observation_date" in keys or "obs_date" in keys:
            yield _sp500_kind([source], hint), [source]
            return
        for key, value in source.items():
            yield from _iter_sp500_groups(value, str(key))
        return
    if isinstance(source, (str, bytes, bytearray)):
        raise TypeError("expected a dataset or an iterable of rows, not a string")
    try:
        items = list(source)
    except TypeError as exc:  # pragma: no cover - defensive
        raise TypeError(f"expected an iterable of rows, got {type(source).__name__}") from exc
    if not items:
        return
    if all(isinstance(item, Mapping) for item in items):
        yield _sp500_kind(items, hint), items
        return
    for item in items:
        yield from _iter_sp500_groups(item, hint)


def _close_map_from_rows(rows: Iterable[Mapping[str, Any]], *columns: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in rows:
        date_value = parse_date(row.get("date"))
        if date_value is None:
            continue
        close = None
        for column in columns:
            if row.get(column) is not None:
                close = row.get(column)
                break
        number = _positive_number(close)
        if number is not None:
            values[date_value] = number
    return values


def _compute_log_returns(records: Sequence[Row]) -> None:
    """Fill ``sp500_log_return`` using the previous observed row."""

    previous: float | None = None
    for record in records:
        close = _positive_number(record.get("sp500_close"))
        if previous is None or close is None:
            record["sp500_log_return"] = None
        else:
            record["sp500_log_return"] = math.log(close / previous)
        previous = close


def normalize_sp500_daily(
    source: Any = None,
    fred: Any = None,
    *,
    openintro: Any = None,
    cutover: date | str = SP500_CUTOVER_DATE,
    source_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> NormalizedDataset:
    """Return the canonical ``sp500_daily`` dataset.

    ``source`` may be a single dataset, a list of datasets, or a mapping of
    source ids to datasets.  ``openintro`` and ``fred`` can be supplied
    explicitly.  When OpenIntro history is present it is authoritative through
    ``cutover`` (2018-12-07 by default) and FRED closes are used only strictly
    after that date.
    """

    groups: list[tuple[str, list[Mapping[str, Any]]]] = []
    if openintro is not None:
        groups.extend(_iter_sp500_groups(openintro, "openintro_sp500"))
    if fred is not None:
        groups.extend(_iter_sp500_groups(fred, "fred_sp500"))
    if source is not None:
        groups.extend(_iter_sp500_groups(source))

    cutover_date = parse_date(cutover) or SP500_CUTOVER_DATE.isoformat()
    canonical_rows: list[Mapping[str, Any]] = []
    openintro_rows: list[Mapping[str, Any]] = []
    fred_rows: list[Mapping[str, Any]] = []
    for kind, rows in groups:
        if kind == "openintro":
            openintro_rows.extend(rows)
        elif kind == "fred":
            fred_rows.extend(rows)
        else:
            canonical_rows.extend(rows)

    # If the caller supplied an already-canonical table with explicit log
    # returns, keep it exactly as given (after type/order normalisation).
    if canonical_rows:
        has_log_return = any("sp500_log_return" in row for row in canonical_rows)
        table = _dataset(
            SP500_DAILY,
            canonical_rows,
            source_id=source_id or SP500_DAILY,
            metadata={"synthetic": False, **(metadata or {})},
        )
        if not has_log_return:
            _compute_log_returns(list(table))
        return table

    openintro_closes = _close_map_from_rows(openintro_rows, "close", "sp500_close", "value")
    fred_closes = _close_map_from_rows(fred_rows, "value", "sp500", "close", "sp500_close")

    records: list[Row] = []
    if openintro_closes:
        for date_value in sorted(openintro_closes):
            if date_value > cutover_date and fred_closes:
                continue
            records.append(
                Row(
                    {
                        "date": date_value,
                        "sp500_close": openintro_closes[date_value],
                        "price_source": "openintro",
                    }
                )
            )
    if fred_closes:
        for date_value in sorted(fred_closes):
            if openintro_closes and date_value <= cutover_date:
                continue
            records.append(
                Row(
                    {
                        "date": date_value,
                        "sp500_close": fred_closes[date_value],
                        "price_source": "fred",
                    }
                )
            )
    records.sort(key=lambda row: str(row["date"]))
    table = _dataset(
        SP500_DAILY,
        records,
        source_id=source_id or SP500_DAILY,
        metadata={"synthetic": False, **(metadata or {})},
    )
    _compute_log_returns(list(table))
    return table


def _industry_from_column(column: str) -> str | None:
    """Map an ``ind_<code>_return`` column back to a standard industry name."""

    lowered = normalize_key(column)
    for name, code in INDUSTRY_CODES.items():
        if lowered in {f"ind_{code}_return", f"{code}_return", f"ind_{code}"}:
            return name
        if lowered == normalize_key(name):
            return name
    return None


def _industry_from_value(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for name, code in INDUSTRY_CODES.items():
        if text == name or normalize_key(text) == code:
            return name
    return None


def _looks_long_industry(rows: Sequence[Mapping[str, Any]]) -> bool:
    if not rows:
        return False
    keys = {normalize_key(key) for key in rows[0]}
    return "industry" in keys or "weighting" in keys


def _is_percent_source(source: Any) -> bool:
    if _is_dataset(source):
        if normalize_key(getattr(source, "source_id", "")) == "french_12_industries":
            return True
        units = getattr(source, "units", {}) or {}
        return any(str(value).lower().startswith("percent") for value in units.values())
    if isinstance(source, Mapping):
        return any(_is_percent_source(value) for value in source.values())
    if isinstance(source, (list, tuple)):
        return any(_is_percent_source(value) for value in source)
    return False


def normalize_industries_daily(
    source: Any = None,
    *,
    weighting: str = "value",
    percent: bool | None = None,
    source_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> NormalizedDataset:
    """Return a canonical ``industries_daily`` dataset of decimal returns.

    The French adapter exposes percentage returns; they are divided by 100
    exactly once here.  A source that is already expressed as decimal simple
    returns (for example the synthetic demo tables) is left unchanged.
    """

    rows = _as_rows(source)
    equal = str(weighting).strip().lower().startswith(("equal", "ew"))
    source_column = "equal_weighted_return" if equal else "value_weighted_return"
    long_format = _looks_long_industry(rows)
    if percent is None:
        percent = long_format or _is_percent_source(source)
    divisor = 100.0 if percent else 1.0

    by_date: dict[str, dict[str, Any]] = {}
    if long_format:
        for row in rows:
            date_value = parse_date(row.get("date"))
            if date_value is None:
                continue
            industry = _industry_from_value(row.get("industry"))
            if industry is None:
                continue
            value = row.get(source_column)
            if value is None and "return" in row:
                value = row.get("return")
            number = coerce_number(value)
            by_date.setdefault(date_value, {})[industry] = (
                None if number is None else float(number) / divisor
            )
    else:
        for row in rows:
            date_value = parse_date(row.get("date"))
            if date_value is None:
                continue
            record = by_date.setdefault(date_value, {})
            for key, value in row.items():
                industry = _industry_from_column(str(key))
                if industry is not None:
                    number = coerce_number(value)
                    record[industry] = None if number is None else float(number) / divisor

    ordered_rows: list[Row] = []
    for date_value in sorted(by_date):
        record = by_date[date_value]
        ordered_rows.append(
            Row(
                {
                    "date": date_value,
                    **{
                        column: record.get(name)
                        for name, column in zip(
                            INDUSTRY_NAMES, INDUSTRIES_DAILY_COLUMNS[1:], strict=True
                        )
                    },
                }
            )
        )
    return _dataset(
        INDUSTRIES_DAILY,
        ordered_rows,
        source_id=source_id or INDUSTRIES_DAILY,
        metadata={
            "weighting": "equal" if equal else "value",
            "percent_input": bool(percent),
            "synthetic": False,
            **(metadata or {}),
        },
    )


def normalize_vix_daily(
    source: Any = None,
    *,
    source_id: str | None = None,
) -> NormalizedDataset:
    """Return a small ``date, vix_close`` dataset for the VIX source."""

    rows = _as_rows(source)
    records: dict[str, Row] = {}
    for row in rows:
        date_value = parse_date(row.get("date"))
        if date_value is None:
            continue
        close = None
        for column in ("close", "vix_close", "value", "vix"):
            if row.get(column) is not None:
                close = row.get(column)
                break
        number = coerce_number(close)
        records[date_value] = Row({"date": date_value, "vix_close": number})
    ordered = [records[key] for key in sorted(records)]
    return NormalizedDataset(
        ordered,
        source_id=source_id or "cboe_vix",
        source_name="cboe_vix",
        columns=["date", "vix_close"],
        units={"date": "ISO-8601 date", "vix_close": "VIX index points"},
        types={"date": "date", "vix_close": "float"},
        metadata={"synthetic": False},
    )


def _vix_close_map(source: Any) -> dict[str, float]:
    if source is None:
        return {}
    dataset = source if _is_dataset(source) else normalize_vix_daily(source)
    values: dict[str, float] = {}
    for row in dataset:
        date_value = parse_date(row.get("date"))
        number = coerce_number(row.get("vix_close") or row.get("close") or row.get("value"))
        if date_value is not None and number is not None:
            values[date_value] = float(number)
    return values


def compute_tda_daily(
    sp500: Any = None,
    industries: Any = None,
    vix: Any = None,
    *,
    source_id: str | None = None,
) -> NormalizedDataset:
    """Derive the canonical ``tda_daily`` table.

    The table is an exact-date inner join of the index, industry and (when
    supplied) VIX series.  Missing dates are dropped rather than forward
    filled; missing values within a matching row remain ``None``.
    """

    sp500_data = (
        sp500
        if _is_dataset(sp500) and sp500.source_id == SP500_DAILY
        else normalize_sp500_daily(sp500)
    )
    industries_data = (
        industries
        if _is_dataset(industries) and industries.source_id == INDUSTRIES_DAILY
        else normalize_industries_daily(industries)
    )
    sp500_by_date = {str(row["date"]): row for row in sp500_data if row.get("date") is not None}
    industries_by_date = {
        str(row["date"]): row for row in industries_data if row.get("date") is not None
    }
    vix_map = _vix_close_map(vix)

    join_dates = set(sp500_by_date) & set(industries_by_date)
    if vix_map:
        join_dates &= set(vix_map)

    records: list[Row] = []
    for date_value in sorted(join_dates):
        sp500_row = sp500_by_date[date_value]
        industry_row = industries_by_date[date_value]
        record = Row(
            {
                "date": date_value,
                "sp500_close": sp500_row.get("sp500_close"),
                "sp500_log_return": sp500_row.get("sp500_log_return"),
                "vix_close": vix_map.get(date_value),
            }
        )
        for column in TDA_DAILY_COLUMNS[4:]:
            record[column] = industry_row.get(column)
        records.append(record)
    return _dataset(
        TDA_DAILY,
        records,
        source_id=source_id or TDA_DAILY,
        metadata={"join": "inner", "forward_fill": False, "synthetic": False},
    )


def normalize_tda_daily(
    source: Any = None,
    *,
    sp500: Any = None,
    industries: Any = None,
    vix: Any = None,
    source_id: str | None = None,
) -> NormalizedDataset:
    """Return a canonical ``tda_daily`` dataset.

    When ``source`` is ``None`` the table is derived from ``sp500``,
    ``industries`` and ``vix``.  An explicit source is normalised as-is.
    """

    if source is None:
        return compute_tda_daily(sp500, industries, vix, source_id=source_id)
    if _looks_like_source_mapping(source):
        tables = build_normalized_tables_from_sources(source)
        return tables[TDA_DAILY]
    return _dataset(
        TDA_DAILY,
        _as_rows(source),
        source_id=source_id or TDA_DAILY,
        metadata={"synthetic": False},
    )


def _looks_like_source_mapping(value: Any) -> bool:
    """Whether ``value`` is a mapping of source ids or canonical table names."""

    if hasattr(value, "tables"):
        return True
    if not isinstance(value, Mapping):
        return False
    keys = {normalize_key(str(key)) for key in value}
    if not keys or keys & {"date", "observation_date", "obs_date"}:
        return False
    if keys & {normalize_key(name) for name in NORMALIZED_TABLE_NAMES}:
        return True
    source_keys = {
        *_OPENINTRO_SOURCE_IDS,
        *_FRED_SOURCE_IDS,
        *_VIX_SOURCE_IDS,
        "french_12_industries",
        "french",
        "tda",
        "tda_daily",
    }
    return bool(keys & source_keys)


def _looks_like_vix_source(value: Any) -> bool:
    """Whether ``value`` looks like a VIX dataset rather than ``tda_daily``."""

    if _is_dataset(value):
        if normalize_key(getattr(value, "source_id", "")) in _VIX_SOURCE_IDS:
            return True
        columns = {normalize_key(column) for column in getattr(value, "columns", ())}
    else:
        rows = _as_rows(value)
        if not rows:
            return False
        columns = {normalize_key(str(key)) for key in rows[0]}
    if any(column.startswith("ind_") for column in columns):
        return False
    return bool(columns & {"vix_close", "vix"}) or columns <= {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }


def build_normalized_tables(
    sp500: Any = None,
    industries: Any = None,
    tda: Any = None,
    vix: Any = None,
    *,
    compute_tda: bool = True,
) -> dict[str, NormalizedDataset]:
    """Return the three normalised tables in canonical order.

    ``sp500``/``industries`` may each be a dataset or a mapping of source
    tables.  The result always contains all three keys so downstream writers
    can emit a complete schema even when a source is absent.
    """

    if industries is None and tda is None and vix is None and _looks_like_source_mapping(sp500):
        if isinstance(sp500, Mapping):
            keys = {normalize_key(str(key)) for key in sp500}
            if keys & {normalize_key(name) for name in NORMALIZED_TABLE_NAMES}:
                provided = {
                    canonical_table_name(key): value
                    for key, value in sp500.items()
                    if canonical_table_name_if_known(key) is not None
                }
                for key, value in sp500.items():
                    if normalize_key(str(key)) in _VIX_SOURCE_IDS:
                        vix = value
                sp500 = provided.get(SP500_DAILY)
                industries = provided.get(INDUSTRIES_DAILY)
                tda = provided.get(TDA_DAILY)
            else:
                return build_normalized_tables_from_sources(sp500, compute_tda=compute_tda)
        else:
            return build_normalized_tables_from_sources(sp500, compute_tda=compute_tda)

    if tda is not None and vix is None and _looks_like_vix_source(tda):
        vix, tda = tda, None

    sp500_table = normalize_sp500_daily(sp500)
    industries_table = normalize_industries_daily(industries)
    if tda is not None:
        tda_table = normalize_tda_daily(tda)
    elif compute_tda:
        tda_table = compute_tda_daily(sp500_table, industries_table, vix)
    else:
        tda_table = empty_table(TDA_DAILY)
    return {
        SP500_DAILY: sp500_table,
        INDUSTRIES_DAILY: industries_table,
        TDA_DAILY: tda_table,
    }


def build_normalized_tables_from_sources(
    sources: Any,
    *,
    compute_tda: bool = True,
) -> dict[str, NormalizedDataset]:
    """Build the tables from an import result or a source-id mapping."""

    if hasattr(sources, "tables"):
        sources = sources.tables
    if sources is None:
        sources = {}
    if not isinstance(sources, Mapping):
        raise TypeError("sources must be a mapping or an ImportResult")

    aliases = {
        "openintro_sp500": SP500_DAILY,
        "openintro": SP500_DAILY,
        "sp500_openintro": SP500_DAILY,
        "fred_sp500": SP500_DAILY,
        "fred": SP500_DAILY,
        "sp500_fred": SP500_DAILY,
        "french_12_industries": INDUSTRIES_DAILY,
        "french": INDUSTRIES_DAILY,
        "industries": INDUSTRIES_DAILY,
        "tda": TDA_DAILY,
        "tda_daily": TDA_DAILY,
        "cboe_vix": "vix",
        "cboe": "vix",
        "vix": "vix",
        "vix_history": "vix",
    }
    grouped: dict[str, list[Any]] = {
        SP500_DAILY: [],
        INDUSTRIES_DAILY: [],
        TDA_DAILY: [],
        "vix": [],
    }
    for source_id, dataset in sources.items():
        target = aliases.get(normalize_key(source_id))
        if target is None:
            target = canonical_table_name_if_known(source_id)
        if target is None:
            continue
        grouped[target].append(dataset)

    return build_normalized_tables(
        grouped[SP500_DAILY] or None,
        grouped[INDUSTRIES_DAILY] or None,
        grouped[TDA_DAILY] or None,
        grouped["vix"] or None,
        compute_tda=compute_tda,
    )


def canonical_table_name_if_known(name: Any) -> str | None:
    """Return the canonical table name for ``name`` or ``None``."""

    try:
        return canonical_table_name(str(name))
    except KeyError:
        return None


def tables_from_sources(sources: Any, *, compute_tda: bool = True) -> dict[str, NormalizedDataset]:
    """Alias for :func:`build_normalized_tables_from_sources`."""

    return build_normalized_tables_from_sources(sources, compute_tda=compute_tda)


def normalize_sources(sources: Any, *, compute_tda: bool = True) -> dict[str, NormalizedDataset]:
    """Alias used by import orchestration code."""

    return build_normalized_tables_from_sources(sources, compute_tda=compute_tda)


# Friendly spellings used by scripts and by the demo package.
build_tables = build_normalized_tables
normalized_tables = build_normalized_tables
build_tables_from_sources = build_normalized_tables_from_sources
normalise_tables = build_normalized_tables
normalize_tables = build_normalized_tables
normalise_sources = normalize_sources


def table_to_rows(dataset: NormalizedDataset) -> list[list[Any]]:
    """Return rows as lists in the dataset's canonical column order."""

    return [[row.get(column) for column in dataset.columns] for row in dataset]


def _schema_payload(tables: Mapping[str, NormalizedDataset]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name in NORMALIZED_TABLE_NAMES:
        dataset = tables.get(name) or empty_table(name)
        payload[name] = {
            "table": name,
            "file": f"{name}.csv",
            "columns": list(dataset.columns),
            "types": dict(dataset.schema),
            "units": dict(dataset.units),
            "row_count": dataset.row_count,
            "first_observation": dataset.first_observation,
            "last_observation": dataset.last_observation,
        }
    return payload


class NormalizedWriteResult(dict):
    """Mapping of table name to primary CSV path with extra write metadata."""

    def __init__(self, paths: Mapping[str, str], **metadata: Any) -> None:
        super().__init__(paths)
        self.paths = dict(paths)
        self.table_datasets = metadata.pop("tables", {})
        self.schema_path = metadata.get("schema_path")
        self.manifest_path = metadata.get("manifest_path")
        self.written_paths = list(metadata.get("written_paths", ()))
        self.output_dir = metadata.get("output_dir")
        for key, value in metadata.items():
            if hasattr(type(self), key):
                continue
            setattr(self, key, value)

    @property
    def tables(self) -> dict[str, NormalizedDataset]:
        return dict(self.table_datasets)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tables": dict(self),
            "paths": dict(self.paths),
            "schema_path": self.schema_path,
            "manifest_path": self.manifest_path,
        }


def write_normalized_tables(
    tables: Mapping[str, Any],
    output_dir: Path | str,
    *,
    mirror: bool = True,
    write_schema: bool = True,
    source_id: str | None = None,
) -> NormalizedWriteResult:
    """Write the normalised tables as UTF-8/LF CSV files.

    The primary files live directly below ``output_dir``.  A mirrored copy is
    written below ``output_dir/normalized`` for callers that keep raw and
    derived tables separate.  Row order and column order are fixed by the
    schema contract, which makes two runs with identical input byte-identical.
    """

    root = ensure_data_directory(Path(output_dir))
    normalized_dir = root / NORMALIZED_DIRNAME
    normalized_dir.mkdir(parents=True, exist_ok=True)

    normalized: dict[str, NormalizedDataset] = {}
    for name in NORMALIZED_TABLE_NAMES:
        value = tables.get(name)
        if value is None:
            value = empty_table(name, source_id=source_id)
        elif not _is_dataset(value):
            value = _dataset(name, _as_rows(value), source_id=source_id)
        normalized[name] = value

    paths: dict[str, str] = {}
    written_paths: list[Path] = []
    for name in NORMALIZED_TABLE_NAMES:
        dataset = normalized[name]
        primary = root / f"{name}.csv"
        dataset.to_csv(primary)
        written_paths.append(primary)
        if mirror:
            mirror_path = normalized_dir / f"{name}.csv"
            dataset.to_csv(mirror_path)
            written_paths.append(mirror_path)
        paths[name] = str(primary)

    schema_path: Path | None = None
    if write_schema:
        payload = {
            "schema_version": 1,
            "tables": _schema_payload(normalized),
            "contracts": contracts_as_dict(),
        }
        schema_path = normalized_dir / NORMALIZED_SCHEMA_FILENAME
        atomic_write_json(schema_path, payload)
        written_paths.append(schema_path)
        table_index_path = root / NORMALIZED_TABLES_FILENAME
        atomic_write_json(table_index_path, payload)
        written_paths.append(table_index_path)

    return NormalizedWriteResult(
        paths,
        tables=normalized,
        schema_path=str(schema_path) if schema_path is not None else None,
        written_paths=written_paths,
        output_dir=str(root),
    )


def write_tables(tables: Mapping[str, Any], output_dir: Path | str, **kwargs: Any) -> Any:
    """Alias for :func:`write_normalized_tables`."""

    return write_normalized_tables(tables, output_dir, **kwargs)


def _rng(seed: int, section: str) -> random.Random:
    return random.Random(f"topomarket-normalized:{seed}:{section}")  # nosec B311


def _format_number(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def build_demo_normalized_tables(
    seed: int = 42,
    *,
    start_date: date = DEMO_START_DATE,
    days: int = DEMO_DAY_COUNT,
) -> dict[str, NormalizedDataset]:
    """Return deterministic synthetic tables matching the normalised schema.

    The generator is intentionally simple: a seeded random walk for the index,
    independent seeded industry returns, and a seeded VIX series.  It never
    reads private data and always produces the same bytes for the same seed.
    """

    numeric_seed = int(seed)
    day_count = max(0, int(days))
    sp500_rng = _rng(numeric_seed, "sp500")
    industry_rng = _rng(numeric_seed, "industries")
    vix_rng = _rng(numeric_seed, "vix")

    sp500_rows: list[Row] = []
    industries_rows: list[Row] = []
    vix_rows: list[Row] = []
    price = 100.0
    vix = 15.0
    for offset in range(day_count):
        current_date = (start_date + timedelta(days=offset)).isoformat()
        price = max(1.0, price * math.exp(sp500_rng.uniform(-0.02, 0.02)))
        sp500_rows.append(
            Row(
                {
                    "date": current_date,
                    "sp500_close": _format_number(price),
                    "price_source": "synthetic",
                }
            )
        )
        industries_rows.append(
            Row(
                {
                    "date": current_date,
                    **{
                        column: _format_number(industry_rng.uniform(-0.05, 0.05), 6)
                        for column in INDUSTRIES_DAILY_COLUMNS[1:]
                    },
                }
            )
        )
        vix = max(1.0, vix * math.exp(vix_rng.uniform(-0.1, 0.1)))
        vix_rows.append(Row({"date": current_date, "vix_close": _format_number(vix)}))

    sp500_table = normalize_sp500_daily(
        sp500_rows,
        source_id=SP500_DAILY,
        metadata={"synthetic": True, "seed": numeric_seed, "profile": "demo"},
    )
    industries_table = normalize_industries_daily(
        industries_rows,
        source_id=INDUSTRIES_DAILY,
        metadata={"synthetic": True, "seed": numeric_seed, "profile": "demo"},
    )
    tda_table = compute_tda_daily(sp500_table, industries_table, vix_rows)
    tda_table.metadata.update({"synthetic": True, "seed": numeric_seed, "profile": "demo"})
    for table in (sp500_table, industries_table, tda_table):
        table.metadata["synthetic"] = True
        table.metadata["seed"] = numeric_seed
        table.metadata["profile"] = "demo"
    return {
        SP500_DAILY: sp500_table,
        INDUSTRIES_DAILY: industries_table,
        TDA_DAILY: tda_table,
    }


def demo_dataset(
    seed: int = 42,
    *,
    start_date: date = DEMO_START_DATE,
    days: int = DEMO_DAY_COUNT,
) -> dict[str, tuple[tuple[str, ...], list[tuple[Any, ...]]]]:
    """Return the demo tables as CSV-ready ``(header, rows)`` pairs."""

    tables = build_demo_normalized_tables(seed, start_date=start_date, days=days)
    dataset: dict[str, tuple[tuple[str, ...], list[tuple[Any, ...]]]] = {}
    for name in NORMALIZED_TABLE_NAMES:
        dataset[f"{name}.csv"] = (
            tuple(tables[name].columns),
            [tuple(row.get(column) for column in tables[name].columns) for row in tables[name]],
        )
    return dataset


def generate_normalized_tables(
    output_dir: Path | str,
    *,
    seed: int = 42,
    sources: Any = None,
    start_date: date = DEMO_START_DATE,
    days: int = DEMO_DAY_COUNT,
    mirror: bool = True,
    write_schema: bool = True,
) -> NormalizedWriteResult:
    """Generate and write the normalised tables below ``output_dir``.

    When ``sources`` is supplied the private-style pipeline is used; otherwise
    deterministic synthetic tables are produced with ``seed``.
    """

    if sources is not None:
        tables = build_normalized_tables_from_sources(sources)
    else:
        tables = build_demo_normalized_tables(seed, start_date=start_date, days=days)
    return write_normalized_tables(
        tables,
        output_dir,
        mirror=mirror,
        write_schema=write_schema,
    )


def read_normalized_table(path: Path | str, name: str | None = None) -> NormalizedDataset:
    """Read one LF CSV file back into a normalised dataset (optional helper)."""

    source = Path(path)
    table_name = canonical_table_name(name or source.stem)
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return _dataset(table_name, rows, metadata={"filename": source.name})


generate_tables = generate_normalized_tables
write_normalized = write_normalized_tables


__all__ = [
    "COLUMNS",
    "DEMO_DAY_COUNT",
    "DEMO_START_DATE",
    "INDUSTRIES_DAILY",
    "INDUSTRIES_DAILY_COLUMNS",
    "INDUSTRIES_DAILY_TYPES",
    "INDUSTRIES_DAILY_UNITS",
    "NORMALIZED_DIRNAME",
    "NORMALIZED_FILE_NAMES",
    "NORMALIZED_SCHEMA_FILENAME",
    "NORMALIZED_TABLES_FILENAME",
    "NORMALIZED_TABLE_NAMES",
    "NormalizedWriteResult",
    "SP500_CUTOVER_DATE",
    "SP500_DAILY",
    "SP500_DAILY_COLUMNS",
    "SP500_DAILY_TYPES",
    "SP500_DAILY_UNITS",
    "SP500_PRICE_SOURCES",
    "TDA_DAILY",
    "TDA_DAILY_COLUMNS",
    "TDA_DAILY_TYPES",
    "TDA_DAILY_UNITS",
    "TableSchema",
    "build_demo_normalized_tables",
    "build_normalized_tables",
    "build_normalized_tables_from_sources",
    "build_tables",
    "build_tables_from_sources",
    "canonical_table_name_if_known",
    "compute_tda_daily",
    "demo_dataset",
    "empty_table",
    "generate_normalized_tables",
    "generate_tables",
    "normalise_sources",
    "normalise_tables",
    "normalize_industries_daily",
    "normalize_sources",
    "normalize_sp500_daily",
    "normalize_tables",
    "normalize_tda_daily",
    "normalize_vix_daily",
    "normalized_tables",
    "read_normalized_table",
    "table_to_rows",
    "tables_from_sources",
    "write_normalized",
    "write_normalized_tables",
    "write_tables",
]
__all__ += [name for name in _SCHEMAS_ALL if name not in __all__]
