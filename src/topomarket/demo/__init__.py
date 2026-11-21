"""Public synthetic demo profile data for TopoMarket.

The demo uses only project-generated values and the normalised schema shared
with the private import pipeline.  It never reads ``private_data`` or any
network resource.
"""

from __future__ import annotations

from topomarket.data.schemas import *  # noqa: F401,F403 - shared contracts
from topomarket.data.schemas import __all__ as _SCHEMAS_ALL

from .generator import (
    DEFAULT_DAY_COUNT,
    DEFAULT_DAYS,
    DEFAULT_SEED,
    DEFAULT_START_DATE,
    DEMO_FILE_NAMES,
    DEMO_GENERATOR_NAME,
    DEMO_START,
    DEMO_TABLE_NAMES,
    GENERATOR_NAME,
    DataGenerator,
    DemoDataGenerator,
    DemoGenerator,
    SyntheticDemoDataGenerator,
    SyntheticDemoGenerator,
    SyntheticGenerator,
    build_dataset,
    build_demo_dataset,
    demo,
    demo_tables,
    generate,
    generate_demo,
    generate_demo_data,
    generate_demo_dataset,
    generate_synthetic_demo,
    normalise_seed,
    write,
    write_demo,
    write_demo_data,
)

__all__ = [
    "DEFAULT_DAY_COUNT",
    "DEFAULT_SEED",
    "DEFAULT_DAYS",
    "DEFAULT_START_DATE",
    "DEMO_FILE_NAMES",
    "DEMO_GENERATOR_NAME",
    "DEMO_START",
    "DEMO_TABLE_NAMES",
    "DemoDataGenerator",
    "SyntheticGenerator",
    "SyntheticDemoDataGenerator",
    "DataGenerator",
    "DemoGenerator",
    "GENERATOR_NAME",
    "SyntheticDemoGenerator",
    "build_demo_dataset",
    "write",
    "generate",
    "build_dataset",
    "demo",
    "demo_tables",
    "generate_demo",
    "generate_demo_data",
    "generate_demo_dataset",
    "generate_synthetic_demo",
    "normalise_seed",
    "write_demo",
    "write_demo_data",
]

__all__ += [name for name in _SCHEMAS_ALL if name not in __all__]
