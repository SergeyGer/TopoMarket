"""Orchestration for importing local seed files from a directory or zip archive."""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ..manifest import atomic_write_json, ensure_data_directory
from .base import (
    AdapterError,
    AdapterResult,
    AliasDict,
    BaseAdapter,
    NormalizedDataset,
    ParsedSource,
    ParserReport,
    UnsupportedSourceError,
    build_parser_report,
    decode_bytes,
    normalize_key,
    read_csv_table,
    sha256_file,
)
from .cboe import CboeVixAdapter
from .fred import FREDSP500Adapter
from .french import INDUSTRY_NAMES, French12IndustryAdapter
from .ofr import OFRFSIAdapter
from .openintro import OpenIntroSP500Adapter
from .registry import (
    RAW_HASH_REGISTRY_ALIAS_FILENAME,
    RAW_HASHES_FILENAME,
    RawHashRegistry,
)

PARSER_REPORTS_FILENAME = "parser_reports.json"
NORMALIZED_DIRNAME = "normalized"
REPORTS_DIRNAME = "reports"
IMPORT_MANIFEST_FILENAME = "import_manifest.json"

#: Adapter classes in a stable, deterministic order.
ADAPTER_CLASSES: tuple[type[BaseAdapter], ...] = (
    OpenIntroSP500Adapter,
    FREDSP500Adapter,
    CboeVixAdapter,
    French12IndustryAdapter,
    OFRFSIAdapter,
)
ADAPTERS: dict[str, type[BaseAdapter]] = {adapter.source_id: adapter for adapter in ADAPTER_CLASSES}
SOURCE_ADAPTERS = ADAPTERS
SOURCE_IDS: tuple[str, ...] = tuple(ADAPTERS)
SOURCE_NAMES: dict[str, str] = {
    adapter.source_id: adapter.source_name for adapter in ADAPTER_CLASSES
}
REQUIRED_SOURCE_IDS: tuple[str, ...] = tuple(
    adapter.source_id for adapter in ADAPTER_CLASSES if adapter.required
)
OPTIONAL_SOURCE_IDS: tuple[str, ...] = tuple(
    adapter.source_id for adapter in ADAPTER_CLASSES if adapter.optional
)

#: Convenience aliases accepted when looking up imported tables/reports.
SOURCE_ID_ALIASES: dict[str, str] = {
    "openintro": "openintro_sp500",
    "open_intro": "openintro_sp500",
    "openintro_sp_500": "openintro_sp500",
    "sp500_openintro": "openintro_sp500",
    "fred": "fred_sp500",
    "fredsp500": "fred_sp500",
    "sp500_fred": "fred_sp500",
    "stlouis": "fred_sp500",
    "st_louis": "fred_sp500",
    "cboe": "cboe_vix",
    "vix": "cboe_vix",
    "vix_history": "cboe_vix",
    "cboevix": "cboe_vix",
    "french": "french_12_industries",
    "french_12": "french_12_industries",
    "french_industries": "french_12_industries",
    "french_12_industry": "french_12_industries",
    "kenneth_french": "french_12_industries",
    "fama_french": "french_12_industries",
    "12_industries": "french_12_industries",
    "12_industry": "french_12_industries",
    "ofr": "ofr_fsi",
    "ofrfsi": "ofr_fsi",
    "fsi": "ofr_fsi",
    "financial_stress": "ofr_fsi",
    "financial_stress_index": "ofr_fsi",
}
SOURCE_ALIASES = SOURCE_ID_ALIASES


def canonical_source_id(source_id: str) -> str:
    """Return the canonical source id for an id or provider alias."""

    key = normalize_key(source_id)
    return SOURCE_ID_ALIASES.get(key, key)


class SourceAliasDict(AliasDict):
    """A mapping that also resolves short source aliases."""

    aliases = SOURCE_ID_ALIASES


_DATA_SUFFIXES = {".csv", ".txt", ".tsv", ".tab", ".dat", ".asc"}
_ARCHIVE_SUFFIXES = {".zip"}


_DOCUMENTATION_PREFIXES = ("readme", "license", "licence", "notice", "changelog")


def _ignored_name(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    if any(part.startswith(".") for part in parts):
        return True
    if "__MACOSX" in parts:
        return True
    name = PurePosixPath(relative).name.lower()
    if name.startswith("~$"):
        return True
    return name.startswith(_DOCUMENTATION_PREFIXES)


def _is_data_file(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in _DATA_SUFFIXES


def _is_archive_file(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in _ARCHIVE_SUFFIXES


def _source_from_bytes(
    filename: str,
    data: bytes,
    *,
    relative_path: str,
    metadata: Mapping[str, Any] | None = None,
) -> ParsedSource:
    text, encoding = decode_bytes(data)
    return ParsedSource(
        filename=PurePosixPath(filename).name,
        data=data,
        text=text,
        encoding=encoding,
        relative_path=relative_path,
        metadata=dict(metadata or {}),
    )


def load_input_sources(
    input_dir: Path | str | None = None,
    *,
    input_zip: Path | str | None = None,
    input_path: Path | str | None = None,
    include_unknown: bool = True,
) -> list[ParsedSource]:
    """Load source files from a directory, a single file, or a zip archive."""

    if input_path is not None:
        if input_dir is not None or input_zip is not None:
            raise TypeError("pass only one of input_dir, input_zip or input_path")
        input_dir = input_path
    elif input_dir is not None and input_zip is not None:
        raise TypeError("pass only one of input_dir, input_zip or input_path")
    if input_dir is None and input_zip is None:
        raise TypeError("an input directory or input zip archive is required")

    if input_zip is not None:
        archive_path = Path(input_zip).expanduser()
        return _load_zip_sources(archive_path, include_unknown=include_unknown)

    directory = Path(input_dir).expanduser()  # type: ignore[arg-type]
    if directory.is_file():
        if directory.suffix.lower() == ".zip":
            return _load_zip_sources(directory, include_unknown=include_unknown)
        if not _is_data_file(directory.name):
            return []
        data = directory.read_bytes()
        return [
            _source_from_bytes(
                directory.name,
                data,
                relative_path=directory.name,
                metadata={"relative_path": directory.name},
            )
        ]
    if not directory.exists():
        raise FileNotFoundError(f"input directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"input path is not a directory: {directory}")

    sources: list[ParsedSource] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(directory).as_posix()
        except ValueError:  # pragma: no cover - defensive
            relative = path.name
        if _ignored_name(relative):
            continue
        if path.suffix.lower() == ".zip":
            sources.extend(_load_zip_sources(path, include_unknown=include_unknown))
            continue
        if not _is_data_file(path.name):
            continue
        sources.append(
            _source_from_bytes(
                path.name,
                path.read_bytes(),
                relative_path=relative,
                metadata={"relative_path": relative},
            )
        )
    return sources


def _load_zip_bytes(
    data: bytes,
    archive_name: str,
    *,
    prefix: str = "",
    metadata: Mapping[str, Any] | None = None,
    nested: bool = False,
) -> list[ParsedSource]:
    """Recursively load data files from an in-memory zip archive.

    Seed archives may contain nested provider archives (the Kenneth French
    library, for example, distributes a zip inside the supplied seed zip).  The
    recursion keeps member paths in ``relative_path`` and records the archive
    names in metadata.  For a nested provider archive only the best data file
    is imported, so documentation or alternate-frequency CSVs cannot shadow
    the requested daily series.
    """

    sources: list[ParsedSource] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = sorted(archive.infolist(), key=lambda item: item.filename)
            if nested:
                data_members = [
                    item for item in members if _is_data_file(item.filename)
                ]
                csv_members = [
                    item
                    for item in data_members
                    if PurePosixPath(item.filename).suffix.lower() == ".csv"
                ]
                if csv_members:
                    daily_members = [
                        item for item in csv_members if "daily" in item.filename.lower()
                    ]
                    data_members = daily_members or csv_members
                archive_members = [
                    item for item in members if _is_archive_file(item.filename)
                ]
                members = [*data_members, *archive_members]
            for member in members:
                if member.is_dir():
                    continue
                relative = member.filename.replace("\\", "/").lstrip("./")
                if _ignored_name(relative):
                    continue
                full_path = f"{prefix}{relative}" if prefix else relative
                payload = archive.read(member)
                member_metadata = {
                    **dict(metadata or {}),
                    "archive": archive_name,
                    "member": full_path,
                    "relative_path": full_path,
                }
                if _is_archive_file(relative):
                    nested_metadata = {
                        **member_metadata,
                        "archive_filename": PurePosixPath(relative).name,
                        "archive_sha256": hashlib.sha256(payload).hexdigest(),
                        "archive_size_bytes": len(payload),
                    }
                    sources.extend(
                        _load_zip_bytes(
                            payload,
                            PurePosixPath(relative).name,
                            prefix=f"{full_path}/",
                            metadata=nested_metadata,
                            nested=True,
                        )
                    )
                elif _is_data_file(relative):
                    sources.append(
                        _source_from_bytes(
                            relative,
                            payload,
                            relative_path=full_path,
                            metadata=member_metadata,
                        )
                    )
    except zipfile.BadZipFile as exc:
        raise AdapterError(f"invalid zip archive: {archive_name}") from exc
    return sources


def _load_zip_sources(
    archive_path: Path,
    *,
    include_unknown: bool = True,
) -> list[ParsedSource]:
    if not archive_path.exists():
        raise FileNotFoundError(f"input zip archive does not exist: {archive_path}")
    if not archive_path.is_file():
        raise IsADirectoryError(f"input zip path is not a file: {archive_path}")
    return _load_zip_bytes(archive_path.read_bytes(), archive_path.name)


def _header_keys(text: str) -> list[str]:
    sample = "\n".join(line for line in text.splitlines() if line.strip())[:200_000]
    if not sample:
        return []
    sample_source = ParsedSource(filename="<sniff>", data=b"", text=sample)
    try:
        table, _warnings = read_csv_table(sample_source)
    except AdapterError:
        return []
    return list(table.keys)


def _content_scores(text: str) -> dict[str, int]:
    scores = {source_id: 0 for source_id in SOURCE_IDS}
    lowered = text.lower()
    if "vix" in lowered or "volatility index" in lowered:
        scores["cboe_vix"] += 40
    if "financial stress" in lowered or "ofr fsi" in lowered:
        scores["ofr_fsi"] += 30
    if "average value weighted" in lowered or "average equal weighted" in lowered:
        scores["french_12_industries"] += 60
    if "industry portfolios" in lowered or "12 industry" in lowered:
        scores["french_12_industries"] += 30
    industry_hits = sum(1 for name in INDUSTRY_NAMES if name.lower() in lowered)
    if industry_hits >= 4:
        scores["french_12_industries"] += 30

    keys = _header_keys(text)
    key_set = set(keys)
    if any(key in key_set for key in ("fsi", "ofr_fsi", "ofrfsi", "financial_stress_index")):
        scores["ofr_fsi"] += 40
    if any("vix" in key for key in key_set):
        scores["cboe_vix"] += 40
    if any(key in key_set for key in ("open", "high", "low")) and "close" in key_set:
        scores["openintro_sp500"] += 18
    if any(key in key_set for key in ("adj_close", "adjclose", "adjusted_close")):
        scores["openintro_sp500"] += 20
    if any(key in key_set for key in ("sp500", "sp_500", "s_p_500")):
        scores["fred_sp500"] += 18
    if "close" in key_set:
        scores["openintro_sp500"] += 5
        scores["fred_sp500"] += 3
    # A single numeric series with a date column is the classic FRED export.
    non_date = [key for key in keys if key not in {"date", "dates", "observation_date", "period"}]
    if len(keys) >= 2 and len(non_date) == 1:
        scores["fred_sp500"] += 8
    return scores


def _filename_scores(filename: str) -> dict[str, int]:
    original = PurePosixPath(filename).name
    name = normalize_key(original)
    scores = {source_id: 0 for source_id in SOURCE_IDS}
    if "openintro" in name or "open_intro" in name:
        scores["openintro_sp500"] += 40
    if "fred" in name or "st_louis" in name or "stlouis" in name:
        scores["fred_sp500"] += 40
    if "vix" in name or "cboe" in name:
        scores["cboe_vix"] += 40
    if any(token in name for token in ("french", "kenneth", "fama", "industry", "industries")):
        scores["french_12_industries"] += 40
    if "ofr" in name or "fsi" in name or "financial_stress" in name:
        scores["ofr_fsi"] += 40
    if "sp500" in name or "sp_500" in name or "s_p_500" in name:
        scores["openintro_sp500"] += 3
        scores["fred_sp500"] += 3
    if original == "SP500.csv":
        scores["fred_sp500"] += 4
    return scores


def detect_adapter(
    filename: str | None = None,
    text: str | None = None,
    *,
    source: ParsedSource | None = None,
) -> BaseAdapter | None:
    """Return the adapter that best matches a filename and/or file content."""

    if source is None and text is None and filename is not None:
        # Convenience: a caller may pass an actual local file path instead of
        # a file name.  Read it so content sniffing can disambiguate generic
        # names such as ``SP500.csv``.
        try:
            candidate = Path(filename).expanduser()
            if candidate.is_file():
                from .base import load_source

                source = load_source(candidate)
        except (OSError, TypeError, ValueError):  # pragma: no cover - defensive
            source = None
    if source is not None:
        filename = filename or source.filename
        text = text if text is not None else source.text
    filename = filename or ""
    scores = {source_id: 0 for source_id in SOURCE_IDS}
    for source_id, score in _filename_scores(filename).items():
        scores[source_id] += score
    if text:
        for source_id, score in _content_scores(text).items():
            scores[source_id] += score
    best_source = max(
        SOURCE_IDS,
        key=lambda source_id: (scores[source_id], -SOURCE_IDS.index(source_id)),
    )
    if scores[best_source] <= 0:
        return None
    # Content sniffing should win over a merely generic "sp500" file name.
    if (
        scores[best_source] == scores.get("openintro_sp500")
        and scores.get("fred_sp500") == scores[best_source]
    ):
        keys = set(_header_keys(text or ""))
        if any(key in keys for key in ("open", "high", "low", "adj_close", "adjclose")):
            best_source = "openintro_sp500"
        else:
            best_source = "fred_sp500"
    return ADAPTERS[best_source]()


def get_adapter(source: str | type[BaseAdapter] | BaseAdapter) -> BaseAdapter:
    """Return an adapter instance for a source id, alias, class or instance."""

    if isinstance(source, BaseAdapter):
        return source
    if isinstance(source, type) and issubclass(source, BaseAdapter):
        return source()
    key = normalize_key(source)
    for source_id, adapter_class in ADAPTERS.items():
        tokens = {
            source_id,
            adapter_class.source_name,
            adapter_class.__name__,
            *adapter_class.aliases,
        }
        if key == normalize_key(source_id) or key in {normalize_key(token) for token in tokens}:
            return adapter_class()
    raise UnsupportedSourceError(f"unknown source adapter: {source!r}")


adapter_for = get_adapter


@dataclass
class ImportResult:
    """The tables, reports and registry produced by an import run."""

    tables: dict[str, NormalizedDataset] = field(default_factory=dict)
    normalized_tables: dict[str, NormalizedDataset] = field(default_factory=dict)
    reports: dict[str, ParserReport] = field(default_factory=dict)
    registry: RawHashRegistry = field(default_factory=RawHashRegistry)
    sources: list[ParsedSource] = field(default_factory=list)
    results: list[AdapterResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    output_dir: Path | None = None
    written: dict[str, Any] = field(default_factory=dict)
    missing_sources: list[str] = field(default_factory=list)

    @property
    def report_list(self) -> list[ParserReport]:
        return [result.report for result in self.results]

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(self.tables)

    @property
    def datasets(self) -> dict[str, NormalizedDataset]:
        return self.tables

    @property
    def normalized(self) -> dict[str, NormalizedDataset]:
        return self.tables

    @property
    def derived_tables(self) -> dict[str, NormalizedDataset]:
        return self.normalized_tables

    @property
    def analysis_tables(self) -> dict[str, NormalizedDataset]:
        return self.normalized_tables

    @property
    def normalized_row_counts(self) -> dict[str, int]:
        return {
            table_name: dataset.row_count
            for table_name, dataset in self.normalized_tables.items()
        }

    @property
    def raw_hashes(self) -> RawHashRegistry:
        return self.registry

    @property
    def parser_reports(self) -> dict[str, ParserReport]:
        return self.reports

    @property
    def entries(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self.registry.entries]

    @property
    def registry_entries(self) -> int:
        return len(self.registry.entries)

    @property
    def row_counts(self) -> dict[str, int]:
        return {source_id: dataset.row_count for source_id, dataset in self.tables.items()}

    @property
    def report_count(self) -> int:
        return len(self.reports)

    @property
    def file_hashes(self) -> dict[str, str]:
        return self.registry.hashes

    def get(self, source_id: str, default: Any = None) -> NormalizedDataset | Any:
        if source_id in self.tables:
            return self.tables[source_id]
        return self.normalized_tables.get(source_id, default)

    def __getitem__(self, key: str) -> Any:
        aliases = {
            "tables": self.tables,
            "datasets": self.tables,
            "normalized": self.tables,
            "normalized_tables": self.normalized_tables,
            "derived_tables": self.normalized_tables,
            "analysis_tables": self.normalized_tables,
            "reports": self.reports,
            "parser_reports": self.reports,
            "registry": self.registry,
            "raw_hashes": self.registry,
            "sources": self.sources,
            "results": self.results,
            "warnings": self.warnings,
            "errors": self.errors,
            "output_dir": self.output_dir,
            "written": self.written,
            "row_counts": self.row_counts,
            "normalized_row_counts": self.normalized_row_counts,
            "registry_entries": self.registry_entries,
            "report_count": self.report_count,
            "file_hashes": self.file_hashes,
        }
        if key in aliases:
            return aliases[key]
        if key in self.tables:
            return self.tables[key]
        if key in self.normalized_tables:
            return self.normalized_tables[key]
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and (
            key in self.tables or key in self.reports or key in self.normalized_tables
        )

    def __iter__(self):
        return iter(self.tables)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_ids": list(self.source_ids),
            "normalized_tables": list(self.normalized_tables),
            "normalized_row_counts": self.normalized_row_counts,
            "reports": {source_id: dict(report) for source_id, report in self.reports.items()},
            "registry": self.registry.to_dict(),
            "warnings": list(self.warnings),
            "errors": dict(self.errors),
            "missing_sources": list(self.missing_sources),
            "output_dir": str(self.output_dir) if self.output_dir is not None else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.as_dict()

    def write(
        self,
        output_dir: Path | str,
        *,
        registry_path: Path | str | None = None,
        reports_path: Path | str | None = None,
        write_import_manifest: bool = True,
    ) -> ImportResult:
        """Write normalised CSVs, the raw hash registry and parser reports."""

        root = ensure_data_directory(Path(output_dir))
        tables_directory = root / NORMALIZED_DIRNAME
        reports_directory = root / REPORTS_DIRNAME
        tables_directory.mkdir(parents=True, exist_ok=True)
        reports_directory.mkdir(parents=True, exist_ok=True)

        table_paths: dict[str, str] = {}
        written_paths: list[Path] = []
        for source_id, dataset in self.tables.items():
            primary = root / f"{source_id}.csv"
            mirror = tables_directory / f"{source_id}.csv"
            dataset.to_csv(primary)
            dataset.to_csv(mirror)
            table_paths[source_id] = str(primary)
            written_paths.extend((primary, mirror))

        # The derived analysis tables share their schema with the synthetic
        # demo generator.  They are written alongside the source tables so
        # private and demo consumers can use the same downstream contract.
        from ..normalized import build_normalized_tables_from_sources, write_normalized_tables

        if not self.normalized_tables:
            self.normalized_tables = build_normalized_tables_from_sources(self.tables)
        normalized_written = write_normalized_tables(self.normalized_tables, root)
        normalized_table_paths = dict(normalized_written)
        written_paths.extend(normalized_written.written_paths)

        registry_destination = (
            Path(registry_path) if registry_path is not None else root / RAW_HASHES_FILENAME
        )
        self.registry.write(registry_destination)
        written_paths.append(registry_destination)
        # Older import scripts looked for the more explicit name.  Writing the
        # same deterministic document under both names keeps both conventions
        # working without duplicating registry state.
        if registry_path is None:
            registry_alias_destination = root / RAW_HASH_REGISTRY_ALIAS_FILENAME
            self.registry.write(registry_alias_destination)
            written_paths.append(registry_alias_destination)

        ordered_source_ids = sorted(self.reports)
        reports_payload = {
            "schema_version": 1,
            "report_count": len(self.reports),
            "source_ids": ordered_source_ids,
            "row_counts": {
                source_id: dataset.row_count for source_id, dataset in self.tables.items()
            },
            "reports": [dict(self.reports[source_id]) for source_id in ordered_source_ids],
            "report_list": [dict(self.reports[source_id]) for source_id in ordered_source_ids],
            "by_source": {
                source_id: dict(self.reports[source_id]) for source_id in ordered_source_ids
            },
            "reports_by_source": {
                source_id: dict(self.reports[source_id]) for source_id in ordered_source_ids
            },
            **{
                source_id: dict(self.reports[source_id]) for source_id in ordered_source_ids
            },
        }
        report_destination = (
            Path(reports_path) if reports_path is not None else root / PARSER_REPORTS_FILENAME
        )
        atomic_write_json(report_destination, reports_payload)
        written_paths.append(report_destination)
        for source_id in ordered_source_ids:
            destination = reports_directory / f"{source_id}.json"
            atomic_write_json(destination, dict(self.reports[source_id]))
            written_paths.append(destination)

        written: dict[str, Any] = {
            "output_dir": str(root),
            "tables": table_paths,
            "normalized_tables": normalized_table_paths,
            "derived_tables": normalized_table_paths,
            "normalized_row_counts": {
                name: dataset.row_count
                for name, dataset in self.normalized_tables.items()
            },
            "schemas": {
                name: {
                    "columns": list(dataset.columns),
                    "types": dict(dataset.schema),
                    "units": dict(dataset.units),
                }
                for name, dataset in self.normalized_tables.items()
            },
            "normalized_dir": str(tables_directory),
            "registry": str(registry_destination),
            "reports": str(report_destination),
            "report_dir": str(reports_directory),
        }
        if registry_path is None:
            written["registry_alias"] = str(root / RAW_HASH_REGISTRY_ALIAS_FILENAME)
        if write_import_manifest:
            output_hashes = {
                path.relative_to(root).as_posix(): sha256_file(path)
                for path in sorted(set(written_paths))
                if path.is_file() and path.is_relative_to(root)
            }
            manifest_payload = {
                "schema_version": 1,
                "source_ids": list(self.source_ids),
                "normalized_tables": list(self.normalized_tables),
                "normalized_row_counts": {
                    name: dataset.row_count
                    for name, dataset in self.normalized_tables.items()
                },
                "file_count": len(self.registry.entries),
                "row_counts": {
                    source_id: dataset.row_count for source_id, dataset in self.tables.items()
                },
                "schemas": written["schemas"],
                "missing_sources": list(self.missing_sources),
                "warnings": list(self.warnings),
                "errors": dict(self.errors),
                "files": self.registry.to_dict()["entries"],
                "reports": [dict(self.reports[source_id]) for source_id in ordered_source_ids],
                "output_hashes": output_hashes,
            }
            manifest_destination = root / IMPORT_MANIFEST_FILENAME
            atomic_write_json(manifest_destination, manifest_payload)
            written["manifest"] = str(manifest_destination)

        self.output_dir = root
        self.written = written
        return self


def import_sources(
    input_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    *,
    input_zip: Path | str | None = None,
    input_path: Path | str | None = None,
    registry_path: Path | str | None = None,
    reports_path: Path | str | None = None,
    strict: bool = False,
    require: Iterable[str] | None = None,
    write: bool = True,
    include_unknown: bool = True,
    **kwargs: Any,
) -> ImportResult:
    """Adapt seed files from ``input_dir`` or ``input_zip``.

    ``output_dir`` is optional.  When supplied (and ``write`` is true), the
    normalised tables, ``raw_hashes.json``, ``parser_reports.json`` and an
    ``import_manifest.json`` summary are written below it.  The returned
    :class:`ImportResult` always exposes the same data in memory.
    """

    if kwargs:
        aliases = {
            "directory": "input_dir",
            "input_directory": "input_dir",
            "zip_path": "input_zip",
            "archive": "input_zip",
            "input_archive": "input_zip",
            "out": "output_dir",
            "out_dir": "output_dir",
            "output": "output_dir",
        }
        for key, value in kwargs.items():
            target = aliases.get(key)
            if target == "input_dir" and input_dir is None:
                input_dir = value
            elif target == "input_zip" and input_zip is None:
                input_zip = value
            elif target == "output_dir" and output_dir is None:
                output_dir = value
            else:
                raise TypeError(f"unexpected keyword argument: {key!r}")

    sources = load_input_sources(
        input_dir,
        input_zip=input_zip,
        input_path=input_path,
        include_unknown=include_unknown,
    )
    result = ImportResult(sources=sources)
    grouped_rows: dict[str, list[Any]] = {}
    grouped_report: dict[str, ParserReport] = {}

    for parsed_source in sources:
        adapter = detect_adapter(source=parsed_source)
        if adapter is None:
            metadata = parsed_source.as_metadata()
            metadata["recognised"] = False
            result.registry.register(
                parsed_source,
                source_id="unknown",
                metadata=metadata,
                filename=parsed_source.filename,
            )
            result.warnings.append(f"unrecognised input file: {parsed_source.relative_path}")
            if strict:
                raise UnsupportedSourceError(
                    f"no adapter recognises input file: {parsed_source.relative_path}"
                )
            continue

        metadata = parsed_source.as_metadata()
        metadata.update(
            {
                "relative_path": parsed_source.relative_path,
                "adapter": type(adapter).__name__,
            }
        )
        result.registry.register(
            parsed_source,
            source_id=adapter.source_id,
            metadata=metadata,
            filename=parsed_source.filename,
        )

        try:
            adapted = adapter.adapt(parsed_source)
        except (AdapterError, OSError, ValueError) as exc:
            result.errors[parsed_source.relative_path] = str(exc)
            warning = f"could not parse {parsed_source.relative_path}: {exc}"
            result.warnings.append(warning)
            if strict:
                raise
            report = build_parser_report(
                parsed_source,
                [],
                source_id=adapter.source_id,
                source_name=adapter.source_name,
                schema={},
                units={},
                columns=[],
                warnings=[warning],
                metadata={"adapter": type(adapter).__name__, "error": str(exc)},
            )
            grouped_report[adapter.source_id] = report
            result.reports[adapter.source_id] = report
            continue

        result.results.append(adapted)
        grouped_rows.setdefault(adapter.source_id, []).extend(adapted.rows)
        grouped_report[adapter.source_id] = adapted.report
        result.reports[adapter.source_id] = adapted.report

    for source_id, rows in grouped_rows.items():
        template = next(
            (adapted.dataset for adapted in result.results if adapted.source_id == source_id),
            None,
        )
        if template is None:  # pragma: no cover - defensive
            continue
        ordered_rows = sorted(
            rows,
            key=lambda row: (
                str(row.get("date") or ""),
                str(row.get("industry") or ""),
                str(row.get("weighting") or ""),
            ),
        )
        result.tables[source_id] = NormalizedDataset(
            ordered_rows,
            source_id=source_id,
            source_name=template.source_name,
            columns=template.columns,
            units=template.units,
            types=template.schema,
            metadata={
                "files": [
                    adapted.filename for adapted in result.results if adapted.source_id == source_id
                ]
            },
        )

    # Keep the canonical source ids when iterating/serialising, while still
    # accepting provider shorthand such as ``result.tables["vix"]``.  Ordering
    # by ``SOURCE_IDS`` makes the result independent of archive/member order.
    def _canonical_order(mapping: Mapping[str, Any]) -> dict[str, Any]:
        ordered = {
            source_id: mapping[source_id]
            for source_id in SOURCE_IDS
            if source_id in mapping
        }
        for source_id in sorted(set(mapping) - set(SOURCE_IDS)):
            ordered[source_id] = mapping[source_id]
        return ordered

    result.tables = SourceAliasDict(_canonical_order(result.tables))
    result.reports = SourceAliasDict(_canonical_order(result.reports))

    from ..normalized import build_normalized_tables_from_sources

    result.normalized_tables = SourceAliasDict(
        build_normalized_tables_from_sources(result.tables)
    )

    required = [canonical_source_id(item) for item in require] if require is not None else []
    for source_id in required:
        if source_id not in result.tables:
            result.missing_sources.append(source_id)
    if strict and result.missing_sources:
        raise UnsupportedSourceError(
            "missing required sources: " + ", ".join(result.missing_sources)
        )
    if not result.tables and strict:
        raise UnsupportedSourceError("no seed files were recognised")

    if write and output_dir is not None:
        result.write(output_dir, registry_path=registry_path, reports_path=reports_path)
    return result


def parse_sources(
    input_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    *,
    input_zip: Path | str | None = None,
    input_path: Path | str | None = None,
    strict: bool = False,
    **kwargs: Any,
) -> ImportResult:
    """Parse seed inputs, optionally writing them below ``output_dir``."""

    return import_sources(
        input_dir,
        output_dir,
        input_zip=input_zip,
        input_path=input_path,
        strict=strict,
        write=output_dir is not None,
        **kwargs,
    )


def import_directory(
    input_dir: Path | str,
    output_dir: Path | str | None = None,
    **kwargs: Any,
) -> ImportResult:
    """Import every recognised seed file in a directory."""

    return import_sources(input_dir, output_dir, **kwargs)


def import_zip(
    input_zip: Path | str,
    output_dir: Path | str | None = None,
    **kwargs: Any,
) -> ImportResult:
    """Import every recognised seed file in a zip archive."""

    return import_sources(None, output_dir, input_zip=input_zip, **kwargs)


def adapt_directory(
    input_dir: Path | str,
    output_dir: Path | str | None = None,
    **kwargs: Any,
) -> ImportResult:
    """Alias for :func:`import_directory`."""

    return import_directory(input_dir, output_dir, **kwargs)


def adapt_zip(
    input_zip: Path | str,
    output_dir: Path | str | None = None,
    **kwargs: Any,
) -> ImportResult:
    """Alias for :func:`import_zip`."""

    return import_zip(input_zip, output_dir, **kwargs)


import_seed_files = import_sources
import_seed_archive = import_sources
import_seed_inputs = import_sources
run_adapters = import_sources
adapt_sources = import_sources
parse_seed_inputs = parse_sources
load_sources = parse_sources


def build_parser_reports(
    input_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    *,
    input_zip: Path | str | None = None,
    input_path: Path | str | None = None,
    strict: bool = False,
) -> dict[str, ParserReport]:
    """Return parser reports for the seed files in a directory or archive."""

    result = import_sources(
        input_dir,
        output_dir,
        input_zip=input_zip,
        input_path=input_path,
        strict=strict,
        write=output_dir is not None,
    )
    return result.reports


generate_parser_reports = build_parser_reports
reports_for_sources = build_parser_reports


def parse_all(
    input_dir: Path | str | None = None,
    *,
    input_zip: Path | str | None = None,
    input_path: Path | str | None = None,
    strict: bool = False,
):
    """Return ``(tables, registry, reports)`` for a seed input set."""

    result = parse_sources(
        input_dir,
        input_zip=input_zip,
        input_path=input_path,
        strict=strict,
    )
    return result.tables, result.registry, result.reports


def import_all(
    input_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    **kwargs: Any,
) -> ImportResult:
    """Alias for :func:`import_sources`."""

    return import_sources(input_dir, output_dir, **kwargs)


adapt_all = import_all


def adapt_source(
    source: ParsedSource | str | bytes | Path | Any,
    *,
    adapter: str | type[BaseAdapter] | BaseAdapter | None = None,
    filename: str | None = None,
) -> AdapterResult:
    """Adapt one source, detecting its adapter when not supplied."""

    parsed = source if isinstance(source, ParsedSource) else None
    parsed_source = parsed or None
    if parsed_source is None:
        from .base import load_source

        parsed_source = load_source(source, filename=filename)
    chosen = get_adapter(adapter) if adapter is not None else detect_adapter(source=parsed_source)
    if chosen is None:
        raise UnsupportedSourceError(f"no adapter recognises source: {parsed_source.filename}")
    return chosen.adapt(parsed_source)


adapt_file = adapt_source


def parse_source(
    source: ParsedSource | str | bytes | Path | Any,
    *,
    adapter: str | type[BaseAdapter] | BaseAdapter | None = None,
    filename: str | None = None,
) -> NormalizedDataset:
    """Parse one source and return its normalised dataset."""

    return adapt_source(source, adapter=adapter, filename=filename).rows


def parse_file(
    source: ParsedSource | str | bytes | Path | Any,
    *,
    adapter: str | type[BaseAdapter] | BaseAdapter | None = None,
    filename: str | None = None,
) -> NormalizedDataset:
    """Alias for :func:`parse_source`."""

    return parse_source(source, adapter=adapter, filename=filename)


read_source = parse_source
read_file = parse_file


__all__ = [
    "adapt_all",
    "import_all",
    "parse_all",
    "build_parser_reports",
    "canonical_source_id",
    "generate_parser_reports",
    "reports_for_sources",
    "adapt_directory",
    "adapt_zip",
    "import_directory",
    "import_zip",
    "read_file",
    "read_source",
    "ADAPTERS",
    "ADAPTER_CLASSES",
    "IMPORT_MANIFEST_FILENAME",
    "NORMALIZED_DIRNAME",
    "OPTIONAL_SOURCE_IDS",
    "PARSER_REPORTS_FILENAME",
    "RAW_HASH_REGISTRY_ALIAS_FILENAME",
    "REPORTS_DIRNAME",
    "REQUIRED_SOURCE_IDS",
    "SOURCE_ADAPTERS",
    "SOURCE_ALIASES",
    "SOURCE_ID_ALIASES",
    "SOURCE_IDS",
    "SOURCE_NAMES",
    "SourceAliasDict",
    "ImportResult",
    "adapt_file",
    "adapt_source",
    "adapt_sources",
    "adapter_for",
    "detect_adapter",
    "get_adapter",
    "import_seed_archive",
    "import_seed_files",
    "import_seed_inputs",
    "import_sources",
    "load_input_sources",
    "load_sources",
    "parse_file",
    "parse_seed_inputs",
    "parse_source",
    "parse_sources",
    "run_adapters",
]
