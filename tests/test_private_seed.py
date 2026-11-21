"""Optional private-seed integration check.

Public CI has no private inputs, so this test is always skipped there.  An
operator can point one of the environment variables below at a local seed
directory, zip archive or single CSV file to run the same schema checks against
their own copy.  The test never copies, prints or stores the seed contents.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from topomarket.data.adapters import import_sources
from topomarket.data.schemas import NORMALIZED_TABLE_NAMES, SCHEMAS

#: Environment variables accepted by the optional private-seed smoke test.
PRIVATE_SEED_ENV_VARS = (
    "TOPOMARKET_PRIVATE_SEED_DIR",
    "TOPOMARKET_PRIVATE_SEED_ARCHIVE",
    "TOPOMARKET_PRIVATE_SEED_ZIP",
    "TOPOMARKET_PRIVATE_SEED_PATH",
    "TOPOMARKET_PRIVATE_SEED",
    "TOPOMARKET_SEED_DIR",
    "TOPOMARKET_SEED_ARCHIVE",
    "TOPOMARKET_SEED_ZIP",
    "TOPOMARKET_SEED_PATH",
)


def _private_seed_path() -> Path:
    for name in PRIVATE_SEED_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser()
    pytest.skip("private seed environment is not configured")


def test_private_seed_import_matches_public_schema() -> None:
    source = _private_seed_path()
    if not source.exists():
        pytest.skip(f"private seed path does not exist: {source.name}")

    if source.is_dir():
        result = import_sources(source, write=False)
    elif source.suffix.lower() == ".zip":
        result = import_sources(input_zip=source, write=False)
    else:
        result = import_sources(input_path=source, write=False)

    if not result.tables:
        pytest.skip("private seed path contains no recognised source files")

    assert set(result.normalized_tables) == set(NORMALIZED_TABLE_NAMES)
    for table_name in NORMALIZED_TABLE_NAMES:
        dataset = result.normalized_tables[table_name]
        assert list(dataset.columns) == list(SCHEMAS[table_name])
        assert dataset.schema == SCHEMAS[table_name]
