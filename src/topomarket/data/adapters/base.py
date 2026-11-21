"""Shared primitives for the local seed-file adapters.

The adapters in this package never touch the network.  They accept a path, the
raw bytes of a file, an open binary file object, or a :class:`ParsedSource` and
return a small, predictable normalised table plus a parser report.  The helpers
here deliberately use only the Python standard library so the private profile
can be used in the same environment as the synthetic demo.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

ADAPTER_SCHEMA_VERSION = 1
PARSER_VERSION = "1.0.0"
DEFAULT_ENCODING = "utf-8-sig"

_MISSING_TOKENS = {
    "",
    ".",
    "..",
    "...",
    "-",
    "--",
    "---",
    "na",
    "n/a",
    "nan",
    "none",
    "null",
    "nil",
    "missing",
    "#n/a",
    "#nv",
    "not available",
    "notavailable",
}

_DATE_KEYS = {
    "date",
    "dates",
    "day",
    "dt",
    "time",
    "timestamp",
    "datetime",
    "date_time",
    "observation_date",
    "observationdate",
    "obs_date",
    "period",
    "period_date",
    "month",
    "year",
}
_DATE_PREFIXES = ("date", "observation_date", "obs_date", "timestamp", "period")
_NUMBER_SUFFIXES = ("_pct", "_percent", "_return", "_value", "_close", "_open", "_high", "_low")


class AdapterError(ValueError):
    """Base class for adapter and input errors."""


class UnsupportedSourceError(AdapterError):
    """Raised when no adapter recognises a source file."""


class SourceReadError(AdapterError, OSError):
    """Raised when a local source file cannot be read or decoded."""


class DateParseError(AdapterError):
    """Raised internally when a date value cannot be interpreted."""


def _utc_now() -> str:
    """Return the current time as an ISO-8601 UTC string."""

    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_key(value: Any) -> str:
    """Return a stable, lower-case key for a CSV column name."""

    text = str(value or "").strip().lower().lstrip("\ufeff")
    text = re.sub(r"[\s\-/\\]+", "_", text)
    text = re.sub(r"[^a-z0-9_]+", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def decode_bytes(data: bytes, *, encoding: str | None = None) -> tuple[str, str]:
    """Decode ``data`` using UTF-8 first and common fallbacks afterwards."""

    if isinstance(data, str):  # pragma: no cover - defensive convenience
        return data, encoding or "utf-8"
    candidates = [encoding] if encoding else []
    candidates.extend(["utf-8", "utf-8-sig", "cp1252", "latin-1"])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return data.decode(candidate), candidate
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("latin-1", errors="replace"), "latin-1"


def sha256_bytes(data: bytes) -> str:
    """Return the lower-case SHA-256 hex digest of ``data``."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file without reading it all into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _expand_year(value: int) -> int:
    if value >= 100:
        return value
    # Match the common financial-data convention: 69-99 are 1900s, 00-68 are
    # 2000s.  This covers the two-digit dates used by some Yahoo exports.
    return 1900 + value if value >= 69 else 2000 + value


def parse_date(value: Any) -> str | None:
    """Parse a date value and return an ISO ``YYYY-MM-DD`` string.

    ``None`` is returned for missing values.  A :class:`DateParseError` is
    raised for values that look like text rather than a date, which lets callers
    skip preamble rows while still noticing malformed observations.
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = int(value)
        text = str(number)
    else:
        text = str(value).strip().strip('"').strip("'")
    if not text or text.lower() in _MISSING_TOKENS:
        return None

    # Date-time strings (ISO, FRED and Yahoo variants).
    text = text.replace("\u00a0", " ").strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text and re.match(r"^\d{4}-\d{1,2}-\d{1,2}\s", text):
        text = text.split(" ", 1)[0]

    # Eight-digit compact dates used by the Fama-French library.
    if re.fullmatch(r"\d{8}", text):
        try:
            return date(int(text[:4]), int(text[4:6]), int(text[6:8])).isoformat()
        except ValueError as exc:
            raise DateParseError(f"invalid compact date: {text!r}") from exc

    # Excel serial dates are occasionally exported instead of a date column.
    if re.fullmatch(r"\d{5}", text):
        try:
            serial = int(text)
            parsed = date(1899, 12, 30).toordinal() + serial
            return date.fromordinal(parsed).isoformat()
        except (ValueError, OverflowError) as exc:  # pragma: no cover - extreme input
            raise DateParseError(f"invalid Excel date: {text!r}") from exc

    # Compact year-month dates used by monthly data-library exports.
    if re.fullmatch(r"\d{6}", text):
        try:
            return date(int(text[:4]), int(text[4:6]), 1).isoformat()
        except ValueError as exc:
            raise DateParseError(f"invalid compact month: {text!r}") from exc

    # ISO-like dates, including a trailing timezone suffix.
    iso_candidate = text[:10]
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", iso_candidate):
        try:
            return date.fromisoformat(iso_candidate).isoformat()
        except ValueError as exc:
            raise DateParseError(f"invalid date: {text!r}") from exc

    # Slash and dash separated dates.  Financial exports from the US normally
    # use month-first order; an unambiguous four-digit year at the start or end
    # is handled first.
    parts = re.split(r"[/\-.]", text)
    if len(parts) == 3 and all(part.strip() for part in parts):
        raw = [part.strip() for part in parts]
        try:
            if len(raw[0]) == 4:
                year, month, day = int(raw[0]), int(raw[1]), int(raw[2])
            elif len(raw[2]) == 4:
                month, day, year = int(raw[0]), int(raw[1]), int(raw[2])
            else:
                month, day, year = int(raw[0]), int(raw[1]), _expand_year(int(raw[2]))
            return date(year, month, day).isoformat()
        except ValueError as exc:
            raise DateParseError(f"invalid date: {text!r}") from exc

    raise DateParseError(f"not a date: {text!r}")


def looks_like_date(value: Any) -> bool:
    """Return whether ``value`` can be parsed as a date."""

    try:
        return parse_date(value) is not None
    except DateParseError:
        return False


def coerce_number(value: Any) -> float | int | None:
    """Convert a CSV numeric value into a number.

    Missing markers become ``None``.  Commas, currency signs, percent signs and
    surrounding whitespace are tolerated, as are accounting-style parentheses
    for negative values.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    text = str(value).strip().replace("\u00a0", " ")
    if not text or text.lower() in _MISSING_TOKENS:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = text.replace(",", "").replace("$", "").replace("£", "").replace("€", "")
    text = text.replace("%", "").strip()
    if text.endswith("*"):
        text = text[:-1].strip()
    if not text or text.lower() in _MISSING_TOKENS:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    if negative:
        number = -number
    if number.is_integer():
        return int(number)
    return number


def is_missing(value: Any) -> bool:
    """Return whether a raw value should be counted as missing."""

    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().lower() in _MISSING_TOKENS


def detect_delimiter(text: str) -> str:
    """Guess the CSV delimiter used by ``text``."""

    sample_lines = [line for line in text.splitlines() if line.strip()][:25]
    sample = "\n".join(sample_lines)
    if not sample:
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        pass
    counts = {delimiter: sample.count(delimiter) for delimiter in (",", ";", "\t", "|")}
    delimiter = max(counts, key=counts.get)
    return delimiter if counts[delimiter] else ","


@dataclass
class ParsedSource:
    """A locally loaded source file together with its digest and metadata."""

    filename: str
    data: bytes
    text: str
    encoding: str = "utf-8"
    sha256: str = ""
    relative_path: str | None = None
    path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sha256:
            self.sha256 = sha256_bytes(self.data)
        if self.relative_path is None:
            self.relative_path = self.filename

    @property
    def size_bytes(self) -> int:
        return len(self.data)

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.filename).suffix.lower()

    def as_metadata(self) -> dict[str, Any]:
        return {
            "size_bytes": self.size_bytes,
            "relative_path": self.relative_path,
            "encoding": self.encoding,
            **dict(self.metadata),
        }


def _read_text_source(text: str, filename: str, encoding: str = "utf-8") -> ParsedSource:
    data = text.encode("utf-8")
    return ParsedSource(filename=filename, data=data, text=text, encoding=encoding)


_ZIP_DATA_SUFFIXES = {".csv", ".txt", ".tsv", ".tab", ".dat", ".asc"}


def _read_zip_member(
    archive: Any,
    archive_name: str,
    *,
    prefix: str = "",
) -> ParsedSource:
    """Read the best data member from an already-open zip archive."""

    members = [
        member
        for member in archive.infolist()
        if not member.is_dir()
        and not PurePosixPath(member.filename).name.startswith(".")
        and "__MACOSX" not in member.filename
    ]
    data_members = [
        member
        for member in members
        if PurePosixPath(member.filename).suffix.lower() in _ZIP_DATA_SUFFIXES
    ]
    archive_members = [
        member for member in members if PurePosixPath(member.filename).suffix.lower() == ".zip"
    ]

    if data_members:
        # Prefer a CSV when a provider archive also ships notes or a readme.
        data_members.sort(
            key=lambda member: (
                PurePosixPath(member.filename).suffix.lower() != ".csv",
                member.filename,
            )
        )
        member = data_members[0]
        data = archive.read(member)
        relative = f"{prefix}{member.filename}" if prefix else member.filename
        text, encoding = decode_bytes(data)
        return ParsedSource(
            filename=PurePosixPath(member.filename).name,
            data=data,
            text=text,
            encoding=encoding,
            relative_path=relative,
            metadata={"archive": archive_name, "member": relative},
        )

    if len(archive_members) == 1:
        import zipfile

        member = archive_members[0]
        relative = f"{prefix}{member.filename}" if prefix else member.filename
        nested = archive.read(member)
        try:
            with zipfile.ZipFile(io.BytesIO(nested)) as inner:
                return _read_zip_member(
                    inner,
                    PurePosixPath(member.filename).name,
                    prefix=f"{relative}/",
                )
        except zipfile.BadZipFile as exc:
            raise SourceReadError(f"invalid nested zip archive: {relative}") from exc

    raise SourceReadError(f"zip archive {archive_name} must contain a recognisable data file")


def _read_zip_source(path: Path) -> ParsedSource:
    """Read the data member of a zip passed directly to an adapter."""

    import zipfile

    try:
        with zipfile.ZipFile(path) as archive:
            return _read_zip_member(archive, path.name)
    except zipfile.BadZipFile as exc:
        raise SourceReadError(f"invalid zip archive: {path}") from exc


def load_source(
    source: ParsedSource | str | bytes | bytearray | Path | Any,
    *,
    filename: str | None = None,
    encoding: str | None = None,
) -> ParsedSource:
    """Load a source from a path, bytes, text or file-like object."""

    if isinstance(source, ParsedSource):
        return source
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
        text, used_encoding = decode_bytes(data, encoding=encoding)
        return ParsedSource(
            filename=filename or "<bytes>",
            data=data,
            text=text,
            encoding=used_encoding,
        )
    if hasattr(source, "read"):
        payload = source.read()
        if isinstance(payload, str):
            return _read_text_source(payload, filename or "<stream>", encoding or "utf-8")
        data = bytes(payload)
        text, used_encoding = decode_bytes(data, encoding=encoding)
        return ParsedSource(
            filename=filename or "<stream>",
            data=data,
            text=text,
            encoding=used_encoding,
        )
    if isinstance(source, str) and "\n" in source and not Path(source).exists():
        return _read_text_source(source, filename or "<text>", encoding or "utf-8")

    path = Path(source).expanduser()
    if path.suffix.lower() == ".zip":
        return _read_zip_source(path)
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise SourceReadError(f"source file not found: {path}") from exc
    except OSError as exc:
        raise SourceReadError(f"could not read source file {path}: {exc}") from exc
    text, used_encoding = decode_bytes(data, encoding=encoding)
    return ParsedSource(
        filename=filename or path.name,
        data=data,
        text=text,
        encoding=used_encoding,
        relative_path=path.name,
        path=path,
    )


class AliasDict(dict):
    """A ``dict`` whose lookups accept alternative column names.

    Serialisation keeps only the canonical keys, while callers can still use
    provider-specific spellings such as ``adj close`` or ``SP500``.  Equality
    also understands aliases so both spellings compare equal in tests.
    """

    aliases: Mapping[str, str] = {}

    @classmethod
    def _canonical_key(cls, key: Any) -> Any:
        if dict.__contains__(cls.aliases, key):
            return cls.aliases[key]  # type: ignore[index]
        try:
            normalised = normalize_key(key)
        except Exception:  # pragma: no cover - defensive
            return key
        return cls.aliases.get(normalised, normalised)  # type: ignore[union-attr]

    def _resolve_key(self, key: Any) -> Any | None:
        """Follow aliases until a stored canonical key is found."""

        current = key
        seen: set[Any] = set()
        while True:
            if dict.__contains__(self, current):
                return current
            if current in seen:
                return None
            seen.add(current)
            canonical = self._canonical_key(current)
            if canonical == current:
                return None
            current = canonical

    def __getitem__(self, key: Any) -> Any:
        resolved = self._resolve_key(key)
        if resolved is not None:
            return dict.__getitem__(self, resolved)
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return self._resolve_key(key) is not None

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key: Any, *default: Any) -> Any:  # type: ignore[override]
        resolved = self._resolve_key(key)
        if resolved is not None:
            return dict.pop(self, resolved)
        if default:
            return default[0]
        raise KeyError(key)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            if dict.__eq__(self, other):
                return True
            translated = {self._canonical_key(key): value for key, value in other.items()}
            return dict.__eq__(self, translated)
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def as_dict(self) -> dict[str, Any]:
        return dict(self)


class Row(AliasDict):
    """A normalised observation with provider-friendly alias lookups."""

    aliases: Mapping[str, str] = {
        "observation_date": "date",
        "obs_date": "date",
        "timestamp": "date",
        "day": "date",
        "price": "close",
        "closing_price": "close",
        "last": "close",
        "adjusted_close": "adj_close",
        "adjclose": "adj_close",
        "adj_close_price": "adj_close",
        "vol": "volume",
        "traded_volume": "volume",
        "sp500": "value",
        "sp_500": "value",
        "close": "value",
        "price_index": "value",
        "index": "value",
        "fsi": "value",
        "ofr_fsi": "value",
        "financial_stress_index": "value",
        "value_weighted": "value_weighted_return",
        "value_weighted_return_pct": "value_weighted_return",
        "vw": "value_weighted_return",
        "vw_return": "value_weighted_return",
        "equal_weighted": "equal_weighted_return",
        "equal_weighted_return_pct": "equal_weighted_return",
        "ew": "equal_weighted_return",
        "ew_return": "equal_weighted_return",
        "vix": "close",
        "vix_close": "close",
        "value": "close",
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
    }


class FieldAliases(AliasDict):
    """A schema/unit mapping whose keys accept provider-friendly aliases."""

    aliases = Row.aliases


class SchemaMap(FieldAliases):
    """A column-to-type mapping that can also compare to a list of columns.

    Reports are consumed by callers that expect either a mapping (column ->
    logical type) or a plain ordered list of column names.  Comparing equal to
    both keeps the report useful without duplicating the schema under yet
    another key.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return FieldAliases.__eq__(self, other)
        if isinstance(other, (list, tuple)):
            wanted = [normalize_key(item) for item in other]
            available = [normalize_key(item) for item in self.keys()]
            return wanted == available
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result


class ColumnList(list):
    """A list of column names that also resolves provider-friendly aliases."""

    def __contains__(self, item: object) -> bool:
        if list.__contains__(self, item):
            return True
        try:
            normalised = normalize_key(item)
        except Exception:  # pragma: no cover - defensive
            return False
        if list.__contains__(self, normalised):
            return True
        canonical = Row.aliases.get(normalised)
        return canonical is not None and list.__contains__(self, canonical)

    @staticmethod
    def _canonical(item: object) -> str:
        key = normalize_key(item)
        return Row.aliases.get(key, key)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple)):
            return [self._canonical(item) for item in self] == [
                self._canonical(item) for item in other
            ]
        return list.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result


class NormalizedDataset(list):
    """A list of normalised rows with schema, units and provenance metadata."""

    def __init__(
        self,
        rows: Iterable[Mapping[str, Any]] = (),
        *,
        source_id: str,
        source_name: str | None = None,
        columns: Sequence[str] | None = None,
        units: Mapping[str, str] | None = None,
        types: Mapping[str, str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        prepared = [row if isinstance(row, Row) else Row(row) for row in rows]
        if columns is None:
            ordered: list[str] = []
            for row in prepared:
                for key in row:
                    if key not in ordered:
                        ordered.append(key)
            columns = ordered
        super().__init__(prepared)
        self.source_id = source_id
        self.source_name = source_name or source_id
        self.columns = ColumnList(columns)
        self.units = FieldAliases(units or {})
        self.types = dict(types or {})
        self.metadata = dict(metadata or {})
        self.report: ParserReport | None = None

    @property
    def rows(self) -> NormalizedDataset:
        return self

    @property
    def table(self) -> NormalizedDataset:
        return self

    @property
    def records(self) -> list[dict[str, Any]]:
        return self.to_records()

    @property
    def dicts(self) -> list[dict[str, Any]]:
        return self.to_records()

    @property
    def schema(self) -> dict[str, str]:
        return SchemaMap({column: self.types.get(column, "float") for column in self.columns})

    @property
    def dates(self) -> list[str]:
        return sorted({str(row["date"]) for row in self if row.get("date") is not None})

    @property
    def first_observation(self) -> str | None:
        values = self.dates
        return values[0] if values else None

    first_date = first_observation

    @property
    def last_observation(self) -> str | None:
        values = self.dates
        return values[-1] if values else None

    last_date = last_observation

    @property
    def row_count(self) -> int:
        return len(self)

    @property
    def missing_values(self) -> MissingValueCounts:
        return MissingValueCounts(
            {column: sum(1 for row in self if row.get(column) is None) for column in self.columns}
        )

    @property
    def missing_total(self) -> int:
        return self.missing_values.total

    def to_records(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self]

    def to_dicts(self) -> list[dict[str, Any]]:
        return self.to_records()

    def as_dicts(self) -> list[dict[str, Any]]:
        return self.to_records()

    def to_json(self, *, indent: int | None = 2) -> str:
        import json

        return json.dumps(
            {
                "source_id": self.source_id,
                "source_name": self.source_name,
                "schema": self.schema,
                "units": self.units,
                "row_count": self.row_count,
                "first_observation": self.first_observation,
                "last_observation": self.last_observation,
                "rows": self.to_records(),
            },
            indent=indent,
            sort_keys=True,
            ensure_ascii=False,
        )

    def to_csv(self, path: Path | str | None = None) -> str | Path:
        """Return CSV text, or write it atomically when ``path`` is given."""

        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer,
            fieldnames=self.columns,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in self:
            writer.writerow({column: row.get(column) for column in self.columns})
        text = buffer.getvalue()
        if path is None:
            return text
        from ..manifest import _atomic_write_text

        destination = Path(path)
        _atomic_write_text(destination, text)
        return destination

    write_csv = to_csv
    to_path = to_csv
    save = to_csv


class MissingValueCounts(dict):
    """Per-column missing counts that also compare equal to their total.

    Reports expose both the detailed mapping (``{"close": 1}``) and a scalar
    total (``missing_total``).  This small ``dict`` subclass lets callers use
    either convention for the generic ``missing_values`` field without having
    to know which one the report happened to use.
    """

    def __init__(self, values: Mapping[str, int] | None = None) -> None:
        super().__init__(values or {})
        self.total = int(sum(self.values()))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict.__eq__(self, other)
        if isinstance(other, bool):
            return NotImplemented
        if isinstance(other, (int, float)):
            return self.total == other
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __int__(self) -> int:
        return self.total

    def __index__(self) -> int:
        return self.total


class ParserReport(AliasDict):
    """A JSON-friendly report describing one parsed source file."""

    aliases: Mapping[str, str] = {
        "rows": "row_count",
        "row_counts": "row_count",
        "num_rows": "row_count",
        "rowcount": "row_count",
        "first_date": "first_observation",
        "last_date": "last_observation",
        "first": "first_observation",
        "last": "last_observation",
        "missing": "missing_values",
        "missing_count": "missing_total",
        "missing_values_count": "missing_total",
        "source": "source_id",
        "file": "filename",
        "name": "source_name",
        "columns": "schema",
        "column_schema": "schema",
        "checksum": "sha256",
        "hash": "sha256",
        "errors": "warnings",
    }

    def to_dict(self) -> dict[str, Any]:
        return dict(self)

    def as_dict(self) -> dict[str, Any]:
        return dict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        import json

        return json.dumps(dict(self), indent=indent, sort_keys=True, ensure_ascii=False)

    def write(self, path: Path | str) -> Path:
        from ..manifest import atomic_write_json

        return atomic_write_json(path, dict(self))

    def __call__(self) -> ParserReport:
        """Allow ``adapter.report`` to be used as an attribute or a method."""

        return self


def _ordered_columns(rows: Sequence[Row], preferred: Sequence[str]) -> list[str]:
    columns = [column for column in preferred if any(column in row for row in rows)]
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    return columns


def build_parser_report(
    source: ParsedSource | None,
    rows: Sequence[Mapping[str, Any]],
    *,
    source_id: str,
    source_name: str | None = None,
    schema: Mapping[str, str] | None = None,
    units: Mapping[str, str] | None = None,
    columns: Sequence[str] | None = None,
    warnings: Iterable[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> ParserReport:
    """Build a parser report from normalised rows and source metadata.

    Reports intentionally contain no wall-clock timestamp by default.  Two
    imports of the same input bytes therefore produce byte-identical report
    documents, which the determinism contract requires.  Callers that want a
    timestamp can pass ``created_at`` explicitly.
    """

    row_objects = [row if isinstance(row, Row) else Row(row) for row in rows]
    if columns is None:
        ordered: list[str] = []
        for row in row_objects:
            for key in row:
                if key not in ordered:
                    ordered.append(key)
        columns = ordered
    columns = ColumnList(columns)
    schema_map = SchemaMap(schema or {})
    for column in columns:
        schema_map.setdefault(column, "date" if column == "date" else "float")
    units_map = FieldAliases({column: (units or {}).get(column, "") for column in columns})

    missing = MissingValueCounts(
        {column: sum(1 for row in row_objects if row.get(column) is None) for column in columns}
    )
    missing_total = missing.total
    dates = sorted({str(row["date"]) for row in row_objects if row.get("date") not in (None, "")})
    first = dates[0] if dates else None
    last = dates[-1] if dates else None

    payload: dict[str, Any] = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "parser": source_name or source_id,
        "parser_version": PARSER_VERSION,
        "source_id": source_id,
        "source_name": source_name or source_id,
        "filename": source.filename if source is not None else None,
        "relative_path": source.relative_path if source is not None else None,
        "sha256": source.sha256 if source is not None else None,
        "size_bytes": source.size_bytes if source is not None else None,
        "encoding": source.encoding if source is not None else None,
        "row_count": len(row_objects),
        "rows": len(row_objects),
        "observation_count": len(dates),
        "unique_dates": len(dates),
        "date_count": len(dates),
        "columns": columns,
        "schema": schema_map,
        "column_schema": schema_map,
        "fields": schema_map,
        "units": units_map,
        "first_observation": first,
        "last_observation": last,
        "first_date": first,
        "last_date": last,
        "observation_start": first,
        "observation_end": last,
        "missing_values": missing,
        "missing_by_column": dict(missing),
        "missing_total": missing_total,
        "missing_count": missing_total,
        "warnings": list(warnings or []),
        "metadata": dict(metadata or {}),
    }
    industries = sorted(
        {str(row["industry"]) for row in row_objects if row.get("industry") not in (None, "")}
    )
    if industries:
        payload["industries"] = industries
        payload["industry_count"] = len(industries)
    if created_at is not None:
        payload["created_at"] = str(created_at)
    return ParserReport(payload)


create_parser_report = build_parser_report
make_parser_report = build_parser_report
parse_report = build_parser_report


def _coerce_report(value: Mapping[str, Any] | ParserReport) -> ParserReport:
    if isinstance(value, ParserReport):
        return value
    payload = dict(value)
    missing = payload.get("missing_values")
    if isinstance(missing, Mapping) and not isinstance(missing, MissingValueCounts):
        payload["missing_values"] = MissingValueCounts(missing)
    return ParserReport(payload)


def write_parser_reports(
    reports: Mapping[str, ParserReport | Mapping[str, Any]]
    | Sequence[ParserReport | Mapping[str, Any]],
    path: Path | str,
) -> Path:
    """Write parser reports as a JSON document and return its path."""

    from ..manifest import atomic_write_json

    if isinstance(reports, Mapping):
        prepared = {
            str(source_id): dict(_coerce_report(report)) for source_id, report in reports.items()
        }
    else:
        prepared = [dict(_coerce_report(report)) for report in reports]
    return atomic_write_json(Path(path), prepared)


def load_parser_reports(path: Path | str) -> dict[str, ParserReport]:
    """Load parser reports from a JSON document written by this package."""

    import json

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        candidates = payload.get("by_source") or payload.get("reports") or payload
        if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
            entries = {}
            for index, report in enumerate(candidates):
                report_map = dict(report)
                source_id = str(report_map.get("source_id") or index)
                entries[source_id] = _coerce_report(report_map)
            return entries
        if isinstance(candidates, Mapping):
            return {
                str(source_id): _coerce_report(report)
                for source_id, report in candidates.items()
                if isinstance(report, Mapping)
            }
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return {
            str(dict(report).get("source_id") or index): _coerce_report(report)
            for index, report in enumerate(payload)
            if isinstance(report, Mapping)
        }
    raise ValueError("parser report document must contain objects")


@dataclass
class AdapterResult:
    """The result of adapting a single source file."""

    source_id: str
    source_name: str
    dataset: NormalizedDataset
    report: ParserReport
    source: ParsedSource
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def rows(self) -> NormalizedDataset:
        return self.dataset

    @property
    def table(self) -> NormalizedDataset:
        return self.dataset

    @property
    def schema(self) -> dict[str, str]:
        return self.dataset.schema

    @property
    def units(self) -> dict[str, str]:
        return self.dataset.units

    @property
    def filename(self) -> str:
        return self.source.filename

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "filename": self.filename,
            "rows": self.dataset.to_records(),
            "report": dict(self.report),
            "metadata": dict(self.metadata),
        }

    def __getitem__(self, key: str) -> Any:
        aliases = {
            "rows": self.dataset,
            "table": self.dataset,
            "dataset": self.dataset,
            "report": self.report,
            "source": self.source,
            "source_id": self.source_id,
            "filename": self.filename,
            "metadata": self.metadata,
        }
        if key in aliases:
            return aliases[key]
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc


@dataclass
class CsvTable:
    """A parsed CSV header and its data rows."""

    header: Sequence[str]
    keys: Sequence[str]
    rows: list[list[str]]
    delimiter: str = ","

    def column_index(self, *aliases: str) -> int | None:
        wanted = {normalize_key(alias) for alias in aliases}
        for index, key in enumerate(self.keys):
            if key in wanted:
                return index
        return None

    def date_index(self) -> int:
        for index, key in enumerate(self.keys):
            if key in _DATE_KEYS or key.startswith(_DATE_PREFIXES):
                return index
        return 0


def _looks_like_header(row: Sequence[str]) -> bool:
    keys = [normalize_key(cell) for cell in row]
    non_empty = [key for key in keys if key]
    if len(non_empty) < 2:
        return False
    return any(key in _DATE_KEYS or key.startswith(_DATE_PREFIXES) for key in keys)


def read_csv_table(source: ParsedSource) -> tuple[CsvTable, list[str]]:
    """Parse ``source`` into a :class:`CsvTable`, skipping preamble lines."""

    text = source.text
    delimiter = detect_delimiter(text)
    warnings: list[str] = []
    try:
        raw_rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    except csv.Error as exc:
        raise AdapterError(f"could not parse CSV {source.filename}: {exc}") from exc

    rows = [
        [str(cell).strip().lstrip("\ufeff") for cell in row]
        for row in raw_rows
        if any(str(cell).strip() for cell in row)
    ]
    if not rows:
        return CsvTable([], [], [], delimiter), ["source file is empty"]

    header_index: int | None = None
    for index, row in enumerate(rows[:200]):
        if _looks_like_header(row):
            header_index = index
            break
    if header_index is None:
        # The header may have an unnamed first (date) column, which is common in
        # data-library exports.  Detect it by checking whether the next row
        # begins with a date and contains at least one numeric value.
        for index in range(min(len(rows) - 1, 200)):
            if len(rows[index]) >= 2 and looks_like_date(rows[index + 1][0]):
                header_index = index
                break
    if header_index is None:
        header_index = 0
        warnings.append("no recognisable header row; using the first non-empty row")

    header = list(rows[header_index])
    keys: list[str] = []
    seen: Counter[str] = Counter()
    for position, name in enumerate(header):
        key = normalize_key(name)
        if not key:
            key = "column_0" if position == 0 else f"column_{position}"
        if key in seen:
            seen[key] += 1
            key = f"{key}_{seen[key]}"
        else:
            seen[key] += 1
        keys.append(key)

    data_rows = rows[header_index + 1 :]
    return CsvTable(header=header, keys=keys, rows=data_rows, delimiter=delimiter), warnings


def _iter_numeric_columns(table: CsvTable, date_index: int) -> Iterator[tuple[int, str]]:
    for index, key in enumerate(table.keys):
        if index == date_index:
            continue
        if key.startswith("column_"):
            continue
        yield index, key


def standard_rows(
    source: ParsedSource,
    *,
    field_aliases: Mapping[str, Sequence[str]],
    canonical_columns: Sequence[str],
    units: Mapping[str, str],
    types: Mapping[str, str] | None = None,
    single_value: bool = False,
    extra_value_aliases: Sequence[str] = (),
) -> tuple[list[Row], dict[str, str], dict[str, str], list[str]]:
    """Parse a conventional one-row-per-date CSV into normalised rows.

    ``field_aliases`` maps canonical output names to accepted header spellings.
    Columns that are present in the file are included in the output; the order
    of ``canonical_columns`` controls the CSV column order.
    """

    table, warnings = read_csv_table(source)
    if not table.rows:
        return [], {}, dict(units), warnings + ["no data rows found"]

    date_index = table.date_index()
    present: dict[str, int] = {}
    for canonical, spellings in field_aliases.items():
        index = table.column_index(*spellings)
        if index is not None and index != date_index:
            present[canonical] = index

    if single_value and "value" not in present:
        for index, key in _iter_numeric_columns(table, date_index):
            if key in {normalize_key(alias) for alias in extra_value_aliases}:
                present["value"] = index
                break
        else:
            for index, _key in _iter_numeric_columns(table, date_index):
                present["value"] = index
                break

    rows: list[Row] = []
    invalid_after_data = 0
    for row in table.rows:
        if len(row) <= date_index:
            continue
        raw_date = row[date_index]
        if is_missing(raw_date):
            continue
        if looks_like_date(raw_date):
            parsed_date = parse_date(raw_date)
        else:
            # Skip preambles and trailing notes, but stop once a plausible data
            # section has ended instead of silently scanning the whole file.
            if rows:
                invalid_after_data += 1
                if invalid_after_data >= 3:
                    break
            continue
        invalid_after_data = 0
        if parsed_date is None:
            continue
        observation: dict[str, Any] = {"date": parsed_date}
        for canonical, index in present.items():
            value = row[index] if index < len(row) else None
            observation[canonical] = coerce_number(value)
        rows.append(Row(observation))

    rows.sort(key=lambda item: str(item.get("date")))
    actual_columns = [column for column in canonical_columns if any(column in row for row in rows)]
    actual_schema = {
        column: (types or {}).get(column, "date" if column == "date" else "float")
        for column in actual_columns
    }
    actual_units = {column: units.get(column, "") for column in actual_columns}
    return rows, actual_schema, actual_units, warnings


class BaseAdapter:
    """Base class for the local seed-file adapters."""

    source_id = "unknown"
    source_name = "Unknown source"
    aliases: tuple[str, ...] = ()
    required = False
    optional = False
    filename_patterns: tuple[str, ...] = ()
    canonical_columns: tuple[str, ...] = ("date",)
    units: Mapping[str, str] = {"date": "ISO-8601 date"}
    types: Mapping[str, str] = {"date": "date"}
    parser_version = PARSER_VERSION

    def __init__(
        self,
        path: Path | str | ParsedSource | None = None,
        *,
        filename: str | None = None,
        source: Path | str | ParsedSource | None = None,
        text: str | None = None,
        data: bytes | bytearray | None = None,
        encoding: str | None = None,
    ) -> None:
        if source is not None:
            if path is not None:
                raise TypeError("pass only one of 'path' or 'source'")
            path = source
        provided = sum(value is not None for value in (path, text, data))
        if provided > 1:
            raise TypeError("pass only one of 'path', 'text' or 'data'")
        if isinstance(path, (ParsedSource, type(None))):
            self.path = path
        else:
            self.path = Path(path).expanduser()
        self.filename = filename
        self.encoding = encoding
        self._inline_source: ParsedSource | None = None
        if text is not None:
            self._inline_source = ParsedSource(
                filename=filename or "<text>",
                data=text.encode("utf-8"),
                text=text,
                encoding=encoding or "utf-8",
            )
        elif data is not None:
            payload = bytes(data)
            decoded, used_encoding = decode_bytes(payload, encoding=encoding)
            self._inline_source = ParsedSource(
                filename=filename or "<bytes>",
                data=payload,
                text=decoded,
                encoding=used_encoding,
            )
        self.last_report: ParserReport | None = None
        self.last_source: ParsedSource | None = None

    # Detection ---------------------------------------------------------
    def matches(self, filename: str, text: str | None = None) -> bool:
        """Return whether this adapter recognises ``filename``/``text``."""

        name = normalize_key(PurePosixPath(filename).name)
        tokens = {self.source_id, *self.aliases, *self.filename_patterns}
        return any(normalize_key(token) and normalize_key(token) in name for token in tokens)

    # Parsing -----------------------------------------------------------
    def _parse_rows(
        self, source: ParsedSource
    ) -> tuple[list[Row], dict[str, str], dict[str, str], list[str]]:
        raise NotImplementedError

    def parse(
        self,
        source: ParsedSource | str | bytes | bytearray | Path | Any | None = None,
        *,
        filename: str | None = None,
        encoding: str | None = None,
    ) -> NormalizedDataset:
        """Parse ``source`` and return the normalised table."""

        target = source
        if target is None:
            target = self._inline_source if self._inline_source is not None else self.path
        if target is None:
            raise TypeError("a source file is required")
        parsed = load_source(
            target,
            filename=filename or self.filename,
            encoding=encoding or self.encoding,
        )
        rows, schema, units, warnings = self._parse_rows(parsed)
        dataset = NormalizedDataset(
            rows,
            source_id=self.source_id,
            source_name=self.source_name,
            columns=[
                column for column in self.canonical_columns if any(column in row for row in rows)
            ],
            units=units,
            types=schema,
            metadata={"filename": parsed.filename, "sha256": parsed.sha256},
        )
        report = build_parser_report(
            parsed,
            rows,
            source_id=self.source_id,
            source_name=self.source_name,
            schema=schema,
            units=units,
            columns=dataset.columns,
            warnings=warnings,
            metadata={"adapter": type(self).__name__, "parser_version": self.parser_version},
        )
        self.last_report = report
        self.last_source = parsed
        dataset.report = report
        return dataset

    read = parse
    load = parse
    normalize = parse
    parse_file = parse

    def parse_text(
        self,
        text: str,
        *,
        filename: str | None = None,
        encoding: str | None = None,
    ) -> NormalizedDataset:
        """Parse in-memory text without touching the filesystem."""

        if not isinstance(text, str):
            raise TypeError("parse_text() expects a string")
        parsed = ParsedSource(
            filename=filename or self.filename or "<text>",
            data=text.encode("utf-8"),
            text=text,
            encoding=encoding or "utf-8",
        )
        return self.parse(parsed)

    parse_string = parse_text
    parse_str = parse_text
    read_text = parse_text
    load_text = parse_text
    from_text = parse_text
    normalize_text = parse_text

    def parse_bytes(
        self,
        data: bytes | bytearray,
        *,
        filename: str | None = None,
        encoding: str | None = None,
    ) -> NormalizedDataset:
        """Parse in-memory bytes without touching the filesystem."""

        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("parse_bytes() expects bytes")
        payload = bytes(data)
        decoded, used_encoding = decode_bytes(payload, encoding=encoding)
        parsed = ParsedSource(
            filename=filename or self.filename or "<bytes>",
            data=payload,
            text=decoded,
            encoding=used_encoding,
        )
        return self.parse(parsed)

    parse_binary = parse_bytes
    read_bytes = parse_bytes
    load_bytes = parse_bytes
    from_bytes = parse_bytes
    normalize_bytes = parse_bytes

    def adapt(
        self,
        source: ParsedSource | str | bytes | Path | Any | None = None,
        *,
        filename: str | None = None,
        encoding: str | None = None,
    ) -> AdapterResult:
        """Parse ``source`` and return the table together with its report."""

        target = source
        if target is None:
            target = self._inline_source if self._inline_source is not None else self.path
        if target is None:
            raise TypeError("a source file is required")
        parsed = load_source(
            target,
            filename=filename or self.filename,
            encoding=encoding or self.encoding,
        )
        rows, schema, units, warnings = self._parse_rows(parsed)
        dataset = NormalizedDataset(
            rows,
            source_id=self.source_id,
            source_name=self.source_name,
            columns=[
                column for column in self.canonical_columns if any(column in row for row in rows)
            ],
            units=units,
            types=schema,
            metadata={"filename": parsed.filename, "sha256": parsed.sha256},
        )
        report = build_parser_report(
            parsed,
            rows,
            source_id=self.source_id,
            source_name=self.source_name,
            schema=schema,
            units=units,
            columns=dataset.columns,
            warnings=warnings,
            metadata={"adapter": type(self).__name__, "parser_version": self.parser_version},
        )
        self.last_report = report
        self.last_source = parsed
        dataset.report = report
        return AdapterResult(
            source_id=self.source_id,
            source_name=self.source_name,
            dataset=dataset,
            report=report,
            source=parsed,
            metadata={"adapter": type(self).__name__},
        )

    def adapt_text(
        self,
        text: str,
        *,
        filename: str | None = None,
        encoding: str | None = None,
    ) -> AdapterResult:
        """Adapt in-memory text and return the table together with its report."""

        if not isinstance(text, str):
            raise TypeError("adapt_text() expects a string")
        parsed = ParsedSource(
            filename=filename or self.filename or "<text>",
            data=text.encode("utf-8"),
            text=text,
            encoding=encoding or "utf-8",
        )
        return self.adapt(parsed)

    def adapt_bytes(
        self,
        data: bytes | bytearray,
        *,
        filename: str | None = None,
        encoding: str | None = None,
    ) -> AdapterResult:
        """Adapt in-memory bytes and return the table together with its report."""

        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("adapt_bytes() expects bytes")
        payload = bytes(data)
        decoded, used_encoding = decode_bytes(payload, encoding=encoding)
        parsed = ParsedSource(
            filename=filename or self.filename or "<bytes>",
            data=payload,
            text=decoded,
            encoding=used_encoding,
        )
        return self.adapt(parsed)

    def build_report(
        self,
        source: ParsedSource | str | bytes | Path | Any | None = None,
    ) -> ParserReport:
        """Parse ``source`` (if needed) and return its parser report."""

        if source is not None:
            return self.adapt(source).report
        if self.last_report is None:
            target = self._inline_source if self._inline_source is not None else self.path
            if target is None:
                raise TypeError("a source file is required")
            return self.adapt(target).report
        return self.last_report

    def report_for(self, source: Any = None) -> ParserReport:
        return self.build_report(source)

    def report_text(
        self,
        text: str,
        *,
        filename: str | None = None,
        encoding: str | None = None,
    ) -> ParserReport:
        return self.adapt_text(text, filename=filename, encoding=encoding).report

    def report_bytes(
        self,
        data: bytes | bytearray,
        *,
        filename: str | None = None,
        encoding: str | None = None,
    ) -> ParserReport:
        return self.adapt_bytes(data, filename=filename, encoding=encoding).report

    @property
    def report(self) -> ParserReport | None:
        return self.last_report

    def __call__(self, source: Any = None) -> NormalizedDataset:
        return self.parse(source)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(source_id={self.source_id!r})"


__all__ = [
    "create_parser_report",
    "make_parser_report",
    "parse_report",
    "ADAPTER_SCHEMA_VERSION",
    "PARSER_VERSION",
    "AdapterError",
    "AdapterResult",
    "AliasDict",
    "BaseAdapter",
    "CsvTable",
    "ColumnList",
    "DateParseError",
    "FieldAliases",
    "NormalizedDataset",
    "ParserReport",
    "ParsedSource",
    "Row",
    "SchemaMap",
    "MissingValueCounts",
    "SourceReadError",
    "UnsupportedSourceError",
    "build_parser_report",
    "load_parser_reports",
    "write_parser_reports",
    "coerce_number",
    "decode_bytes",
    "detect_delimiter",
    "is_missing",
    "load_source",
    "looks_like_date",
    "normalize_key",
    "parse_date",
    "read_csv_table",
    "sha256_bytes",
    "sha256_file",
    "standard_rows",
]
