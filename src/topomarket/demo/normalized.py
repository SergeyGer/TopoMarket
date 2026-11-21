"""Demo wrappers around the shared normalised-table schemas."""

from __future__ import annotations

from topomarket.data.normalized import (  # noqa: F401
    build_demo_normalized_tables,
    demo_dataset,
    write_normalized_tables,
)
from topomarket.data.schemas import (  # noqa: F401
    COLUMNS,
    INDUSTRIES_DAILY,
    INDUSTRIES_DAILY_COLUMNS,
    NORMALIZED_FILE_NAMES,
    NORMALIZED_TABLE_NAMES,
    SCHEMAS,
    SP500_DAILY,
    SP500_DAILY_COLUMNS,
    TDA_DAILY,
    TDA_DAILY_COLUMNS,
)

from .generator import (  # noqa: F401
    DEMO_FILE_NAMES,
    DEMO_TABLE_NAMES,
    DemoGenerator,
    build_demo_dataset,
    demo_tables,
    generate_demo,
)

__all__ = [
    "COLUMNS",
    "DEMO_FILE_NAMES",
    "DEMO_TABLE_NAMES",
    "DemoGenerator",
    "INDUSTRIES_DAILY",
    "INDUSTRIES_DAILY_COLUMNS",
    "NORMALIZED_FILE_NAMES",
    "NORMALIZED_TABLE_NAMES",
    "SCHEMAS",
    "SP500_DAILY",
    "SP500_DAILY_COLUMNS",
    "TDA_DAILY",
    "TDA_DAILY_COLUMNS",
    "build_demo_dataset",
    "build_demo_normalized_tables",
    "demo_dataset",
    "demo_tables",
    "generate_demo",
    "write_normalized_tables",
]
