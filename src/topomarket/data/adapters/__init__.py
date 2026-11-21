"""Offline adapters for the private TopoMarket seed files.

Five public sources are supported:

* :class:`OpenIntroSP500Adapter` -- OpenIntro / Yahoo Finance daily S&P 500;
* :class:`FREDSP500Adapter` -- FRED ``SP500`` series;
* :class:`CboeVixAdapter` -- Cboe spot VIX history;
* :class:`French12IndustryAdapter` -- Kenneth French 12 Industry Portfolios;
* :class:`OFRFSIAdapter` -- optional OFR Financial Stress Index.

Each adapter reads a local path, bytes, stream or :class:`ParsedSource`, produces
a normalised table and a :class:`ParserReport`.  :func:`import_sources` handles
whole directories and zip archives, records SHA-256 digests in a
:class:`RawHashRegistry`, and can write CSV/JSON artefacts.  Nothing in this
package performs network access or depends on a hard-coded input path.
"""

from __future__ import annotations

from .base import (
    ADAPTER_SCHEMA_VERSION,
    PARSER_VERSION,
    AdapterError,
    AdapterResult,
    AliasDict,
    BaseAdapter,
    ColumnList,
    CsvTable,
    DateParseError,
    FieldAliases,
    MissingValueCounts,
    NormalizedDataset,
    ParsedSource,
    ParserReport,
    Row,
    SchemaMap,
    SourceReadError,
    UnsupportedSourceError,
    build_parser_report,
    coerce_number,
    create_parser_report,
    decode_bytes,
    detect_delimiter,
    is_missing,
    load_parser_reports,
    load_source,
    looks_like_date,
    make_parser_report,
    normalize_key,
    parse_date,
    parse_report,
    read_csv_table,
    sha256_bytes,
    sha256_file,
    standard_rows,
    write_parser_reports,
)
from .cboe import (
    VIX,
    CboeAdapter,
    CboeVIX,
    CboeVix,
    CboeVIXAdapter,
    CboeVixAdapter,
    CboeVIXHistoryAdapter,
    CboeVixParser,
    CboeVIXSource,
    CboeVixSource,
    VIXAdapter,
    VIXSource,
    adapt_cboe_vix,
    load_cboe_vix,
    parse_cboe,
    parse_cboe_vix,
    parse_cboe_vix_csv,
    parse_vix,
    read_cboe_vix,
)
from .fred import (
    FRED,
    FREDSP500,
    Fred,
    FREDAdapter,
    FredAdapter,
    FREDSeriesAdapter,
    FREDSource,
    FREDSP500Adapter,
    FredSP500Adapter,
    FREDSP500Parser,
    FREDSP500Source,
    FredSP500Source,
    adapt_fred_sp500,
    load_fred_sp500,
    parse_fred,
    parse_fred_sp500,
    parse_fred_sp500_csv,
    read_fred_sp500,
)
from .french import (
    INDUSTRY_NAMES,
    FamaFrench12IndustryAdapter,
    French12,
    French12IndustriesAdapter,
    French12IndustriesSource,
    French12IndustryAdapter,
    French12IndustryParser,
    French12IndustrySource,
    FrenchAdapter,
    FrenchIndustries,
    FrenchIndustriesAdapter,
    FrenchSource,
    KennethFrench12IndustriesAdapter,
    KennethFrenchAdapter,
    adapt_french_12_industries,
    load_french_12_industries,
    parse_french,
    parse_french_12,
    parse_french_12_industries,
    parse_french_12_industries_csv,
    parse_industries,
    read_french_12_industries,
)
from .ofr import (
    OFR,
    OFRFSI,
    FinancialStressIndexAdapter,
    FinancialStressIndexSource,
    OFFRFSIAdapter,
    OFRAdapter,
    OFRFinancialStressIndexAdapter,
    OFRFSIAdapter,
    OFRFSIParser,
    OFRFSISource,
    OFRSource,
    adapt_ofr_fsi,
    load_ofr_fsi,
    parse_fsi,
    parse_ofr,
    parse_ofr_fsi,
    parse_ofr_fsi_csv,
    read_ofr_fsi,
)
from .openintro import (
    OpenIntro,
    OpenIntroAdapter,
    OpenIntroSource,
    OpenIntroSP500,
    OpenIntroSP500Adapter,
    OpenIntroSP500CSVAdapter,
    OpenIntroSP500Parser,
    OpenIntroSP500Source,
    SP500Adapter,
    SP500Source,
    adapt_openintro_sp500,
    load_openintro_sp500,
    parse_openintro,
    parse_openintro_sp500,
    parse_openintro_sp500_csv,
    parse_sp500,
    read_openintro_sp500,
)
from .pipeline import (
    ADAPTER_CLASSES,
    ADAPTERS,
    IMPORT_MANIFEST_FILENAME,
    NORMALIZED_DIRNAME,
    OPTIONAL_SOURCE_IDS,
    PARSER_REPORTS_FILENAME,
    REPORTS_DIRNAME,
    REQUIRED_SOURCE_IDS,
    SOURCE_ADAPTERS,
    SOURCE_ALIASES,
    SOURCE_ID_ALIASES,
    SOURCE_IDS,
    SOURCE_NAMES,
    ImportResult,
    SourceAliasDict,
    adapt_all,
    adapt_directory,
    adapt_file,
    adapt_source,
    adapt_sources,
    adapt_zip,
    adapter_for,
    build_parser_reports,
    canonical_source_id,
    detect_adapter,
    generate_parser_reports,
    get_adapter,
    import_all,
    import_directory,
    import_seed_archive,
    import_seed_files,
    import_seed_inputs,
    import_sources,
    import_zip,
    load_input_sources,
    load_sources,
    parse_all,
    parse_file,
    parse_seed_inputs,
    parse_source,
    parse_sources,
    read_file,
    read_source,
    reports_for_sources,
    run_adapters,
)
from .registry import (
    HASH_ALGORITHM,
    HASH_REGISTRY_FILENAME,
    RAW_HASH_REGISTRY_ALIAS_FILENAME,
    RAW_HASH_REGISTRY_FILENAME,
    RAW_HASH_SCHEMA_VERSION,
    RAW_HASHES_FILENAME,
    FileHashRegistry,
    HashRegistry,
    RawHashEntry,
    RawHashes,
    RawHashRegistry,
    build_raw_hash_registry,
    compute_sha256,
    hash_file,
    load_registry,
    raw_hash_registry,
    register_file,
    registry_for_sources,
    sha256_digest,
    write_registry,
)

# Common vocabulary used by callers and older scripts.
Adapter = BaseAdapter
DataAdapter = BaseAdapter
SeedAdapter = BaseAdapter
FileAdapter = BaseAdapter
SourceAdapter = BaseAdapter
SUPPORTED_SOURCES = SOURCE_IDS
DEFAULT_ADAPTERS = ADAPTER_CLASSES
NORMALIZED_TABLE_FILENAME = "normalized_tables.json"


def adapt(source, *, adapter=None, filename=None):
    """Adapt one file with an explicit or automatically detected adapter."""

    if adapter is None:
        return adapt_source(source, filename=filename)
    return adapt_source(source, adapter=adapter, filename=filename)


def parse(source, *, adapter=None, filename=None):
    """Parse one file and return its normalised dataset."""

    return adapt(source, adapter=adapter, filename=filename).rows


def import_data(*args, **kwargs):
    """Alias for :func:`import_sources`."""

    return import_sources(*args, **kwargs)


import_seed_data = import_data
load_seed_files = import_sources
run_import = import_sources


def main(argv=None) -> int:
    """Run the adapter command-line interface."""

    from .cli import main as _main

    return _main(argv)


__all__ = [
    "adapt_all",
    "import_all",
    "parse_all",
    "create_parser_report",
    "make_parser_report",
    "parse_report",
    "build_parser_reports",
    "canonical_source_id",
    "generate_parser_reports",
    "reports_for_sources",
    "build_raw_hash_registry",
    "raw_hash_registry",
    "registry_for_sources",
    "adapt_directory",
    "adapt_zip",
    "import_directory",
    "import_zip",
    "read_file",
    "read_source",
    "OpenIntroSP500Source",
    "OpenIntroSource",
    "OpenIntroSP500Parser",
    "SP500Source",
    "load_openintro_sp500",
    "read_openintro_sp500",
    "adapt_openintro_sp500",
    "parse_openintro_sp500_csv",
    "FREDSP500Source",
    "FREDSource",
    "FREDSP500Parser",
    "FredSP500Source",
    "load_fred_sp500",
    "read_fred_sp500",
    "adapt_fred_sp500",
    "parse_fred_sp500_csv",
    "CboeVixSource",
    "CboeVIXSource",
    "VIXSource",
    "CboeVixParser",
    "load_cboe_vix",
    "read_cboe_vix",
    "adapt_cboe_vix",
    "parse_cboe_vix_csv",
    "French12IndustrySource",
    "French12IndustriesSource",
    "FrenchSource",
    "French12IndustryParser",
    "load_french_12_industries",
    "read_french_12_industries",
    "adapt_french_12_industries",
    "parse_french_12_industries_csv",
    "OFRFSISource",
    "OFRSource",
    "OFRFSIParser",
    "FinancialStressIndexSource",
    "load_ofr_fsi",
    "read_ofr_fsi",
    "adapt_ofr_fsi",
    "parse_ofr_fsi_csv",
    "ADAPTERS",
    "ADAPTER_CLASSES",
    "ADAPTER_SCHEMA_VERSION",
    "DEFAULT_ADAPTERS",
    "HASH_ALGORITHM",
    "HASH_REGISTRY_FILENAME",
    "IMPORT_MANIFEST_FILENAME",
    "INDUSTRY_NAMES",
    "NORMALIZED_DIRNAME",
    "NORMALIZED_TABLE_FILENAME",
    "OPTIONAL_SOURCE_IDS",
    "PARSER_REPORTS_FILENAME",
    "PARSER_VERSION",
    "RAW_HASHES_FILENAME",
    "RAW_HASH_REGISTRY_ALIAS_FILENAME",
    "RAW_HASH_REGISTRY_FILENAME",
    "RAW_HASH_SCHEMA_VERSION",
    "REPORTS_DIRNAME",
    "REQUIRED_SOURCE_IDS",
    "SOURCE_ADAPTERS",
    "SOURCE_ALIASES",
    "SOURCE_ID_ALIASES",
    "SOURCE_IDS",
    "SOURCE_NAMES",
    "SourceAliasDict",
    "SUPPORTED_SOURCES",
    "Adapter",
    "AdapterError",
    "AdapterResult",
    "AliasDict",
    "BaseAdapter",
    "CboeAdapter",
    "CboeVIX",
    "CboeVIXAdapter",
    "CboeVIXHistoryAdapter",
    "CboeVix",
    "CboeVixAdapter",
    "CsvTable",
    "DataAdapter",
    "ColumnList",
    "DateParseError",
    "FRED",
    "FieldAliases",
    "FREDAdapter",
    "FREDSP500",
    "FREDSP500Adapter",
    "FREDSeriesAdapter",
    "FamaFrench12IndustryAdapter",
    "FileAdapter",
    "FileHashRegistry",
    "FinancialStressIndexAdapter",
    "Fred",
    "FredAdapter",
    "FredSP500Adapter",
    "French12",
    "French12IndustriesAdapter",
    "French12IndustryAdapter",
    "FrenchAdapter",
    "FrenchIndustries",
    "FrenchIndustriesAdapter",
    "HashRegistry",
    "ImportResult",
    "KennethFrench12IndustriesAdapter",
    "KennethFrenchAdapter",
    "MissingValueCounts",
    "NormalizedDataset",
    "OFFRFSIAdapter",
    "OFR",
    "OFRAdapter",
    "OFRFSI",
    "OFRFSIAdapter",
    "OFRFinancialStressIndexAdapter",
    "OpenIntro",
    "OpenIntroAdapter",
    "OpenIntroSP500",
    "OpenIntroSP500Adapter",
    "OpenIntroSP500CSVAdapter",
    "ParserReport",
    "ParsedSource",
    "RawHashEntry",
    "RawHashRegistry",
    "RawHashes",
    "Row",
    "SP500Adapter",
    "SchemaMap",
    "SeedAdapter",
    "SourceAdapter",
    "SourceReadError",
    "UnsupportedSourceError",
    "VIX",
    "VIXAdapter",
    "adapt",
    "adapt_file",
    "adapt_source",
    "adapt_sources",
    "adapter_for",
    "build_parser_report",
    "coerce_number",
    "compute_sha256",
    "decode_bytes",
    "detect_adapter",
    "detect_delimiter",
    "get_adapter",
    "hash_file",
    "import_data",
    "import_seed_archive",
    "import_seed_data",
    "import_seed_files",
    "import_seed_inputs",
    "import_sources",
    "is_missing",
    "load_input_sources",
    "load_parser_reports",
    "load_registry",
    "load_seed_files",
    "load_source",
    "load_sources",
    "looks_like_date",
    "main",
    "normalize_key",
    "parse",
    "parse_cboe",
    "parse_cboe_vix",
    "parse_date",
    "parse_file",
    "parse_fred",
    "parse_fred_sp500",
    "parse_french",
    "parse_french_12",
    "parse_french_12_industries",
    "parse_fsi",
    "parse_industries",
    "parse_ofr",
    "parse_ofr_fsi",
    "parse_openintro",
    "parse_openintro_sp500",
    "parse_seed_inputs",
    "parse_source",
    "parse_sources",
    "parse_sp500",
    "parse_vix",
    "read_csv_table",
    "register_file",
    "run_adapters",
    "run_import",
    "sha256_bytes",
    "sha256_digest",
    "sha256_file",
    "standard_rows",
    "write_parser_reports",
    "write_registry",
]

# Keep the package namespace in sync with every adapter module so additional
# friendly spellings (for example ``FredSP500CSVAdapter``) are available from
# both ``topomarket.data.adapters`` and ``topomarket.data`` without having to
# maintain a second hand-written list here.
from . import cboe as _cboe_module  # noqa: E402
from . import fred as _fred_module  # noqa: E402
from . import french as _french_module  # noqa: E402
from . import ofr as _ofr_module  # noqa: E402
from . import openintro as _openintro_module  # noqa: E402
from . import registry as _registry_module  # noqa: E402

for _adapter_module in (
    _cboe_module,
    _fred_module,
    _french_module,
    _ofr_module,
    _openintro_module,
    _registry_module,
):
    for _exported_name in getattr(_adapter_module, "__all__", ()):
        globals()[_exported_name] = getattr(_adapter_module, _exported_name)
        if _exported_name not in __all__:
            __all__.append(_exported_name)

del _adapter_module, _exported_name
