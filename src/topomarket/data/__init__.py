"""Data access and local data-directory helpers for TopoMarket.

Only synthetic, repository-safe sample data belongs in this package. Private
research inputs are expected to live outside the repository (by default under
``private_data/``) and are never packaged or committed.

The package also provides manifest and snapshot management for local data
directories. Writes are atomic, snapshot ids are content-addressed, and all
relative path handling rejects traversal attempts. See :mod:`topomarket.data.manifest`
and :mod:`topomarket.data.directory` for details.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import (
    adapter,
    adapters,
    cboe,
    cli,
    directory,
    fred,
    french,
    hash_registry,
    importers,
    manifest,
    normalization,
    normalize,
    ofr,
    openintro,
    parser_report,
    parser_reports,
    pipeline,
    raw_hash_registry,
    raw_hashes,
    raw_registry,
    registry,
    reports,
    source_adapters,
    sources,
    synthetic,
)
from .adapters import *  # noqa: F401,F403 - seed-file adapter API
from .adapters import __all__ as _ADAPTERS_ALL
from .directory import (
    DataDir,
    DataDirectory,
    LocalDataDirectory,
    data_directory,
    open_data_dir,
    open_data_directory,
)
from .manifest import (
    MANIFEST_FILE,
    MANIFEST_FILENAME,
    MANIFEST_GENERATOR,
    MANIFEST_NAME,
    MANIFEST_SCHEMA_VERSION,
    PROVENANCE_FIELDS,
    REQUIRED_MANIFEST_FIELDS,
    REQUIRED_PROVENANCE_FIELDS,
    SNAPSHOT_DIR,
    SNAPSHOT_DIRNAME,
    SNAPSHOT_ID_EXCLUDED_FIELDS,
    SNAPSHOTS_DIR,
    SNAPSHOTS_DIRNAME,
    Manifest,
    ManifestError,
    ManifestIntegrityError,
    ManifestNotFoundError,
    PathTraversalError,
    Snapshot,
    atomic_write,
    atomic_write_json,
    atomic_write_manifest,
    canonical_json,
    compute_snapshot_id,
    create_data_dir,
    create_data_directory,
    create_snapshot,
    ensure_data_dir,
    ensure_data_directory,
    ensure_within,
    init_data_dir,
    init_data_directory,
    join_relative,
    latest_snapshot,
    list_snapshot_ids,
    list_snapshots,
    make_data_directory,
    manifest_path,
    normalise_manifest,
    normalize_manifest,
    read_manifest,
    resolve_path,
    resolve_relative,
    resolve_relative_path,
    safe_join,
    safe_path,
    safe_relative_path,
    save_snapshot,
    snapshot_id,
    snapshot_ids,
    validate_manifest,
    validate_relative,
    validate_relative_path,
    write_json_atomic,
    write_manifest,
    write_snapshot,
)
from .synthetic import (
    DEFAULT_SEED,
    GENERATOR_NAME,
    SYNTHETIC_FILE_NAMES,
    DataGenerator,
    SyntheticDataGenerator,
    SyntheticGenerator,
    build_dataset,
    generate,
    generate_synthetic,
    generate_synthetic_data,
    generate_synthetic_dataset,
    normalise_seed,
    write_synthetic,
    write_synthetic_data,
)

DEMO_DATA_FILE = Path(__file__).with_name("demo_markets.json")


def load_demo_markets(path: Path | None = None) -> list[dict[str, Any]]:
    """Return the bundled synthetic demo markets.

    ``path`` may point to alternative JSON data with the same shape, which is
    useful for tests and for local experiments.
    """

    source = Path(path) if path is not None else DEMO_DATA_FILE
    with source.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    markets = payload.get("markets", [])
    if not isinstance(markets, list):
        raise ValueError(f"Expected a list of markets in {source}")
    return markets


__all__ = [
    "DEFAULT_SEED",
    "DEMO_DATA_FILE",
    "GENERATOR_NAME",
    "MANIFEST_FILENAME",
    "MANIFEST_FILE",
    "MANIFEST_GENERATOR",
    "MANIFEST_NAME",
    "MANIFEST_SCHEMA_VERSION",
    "PROVENANCE_FIELDS",
    "REQUIRED_MANIFEST_FIELDS",
    "REQUIRED_PROVENANCE_FIELDS",
    "SNAPSHOTS_DIR",
    "SNAPSHOTS_DIRNAME",
    "SNAPSHOT_DIR",
    "SNAPSHOT_DIRNAME",
    "SNAPSHOT_ID_EXCLUDED_FIELDS",
    "SYNTHETIC_FILE_NAMES",
    "DataDir",
    "DataDirectory",
    "DataGenerator",
    "LocalDataDirectory",
    "Manifest",
    "ManifestError",
    "ManifestIntegrityError",
    "ManifestNotFoundError",
    "PathTraversalError",
    "Snapshot",
    "SyntheticDataGenerator",
    "SyntheticGenerator",
    "atomic_write",
    "atomic_write_json",
    "atomic_write_manifest",
    "build_dataset",
    "canonical_json",
    "compute_snapshot_id",
    "create_data_dir",
    "create_data_directory",
    "create_snapshot",
    "data_directory",
    "directory",
    "ensure_data_dir",
    "ensure_data_directory",
    "ensure_within",
    "generate",
    "generate_synthetic",
    "generate_synthetic_data",
    "generate_synthetic_dataset",
    "init_data_dir",
    "init_data_directory",
    "join_relative",
    "latest_snapshot",
    "list_snapshot_ids",
    "list_snapshots",
    "load_demo_markets",
    "make_data_directory",
    "manifest",
    "manifest_path",
    "normalise_manifest",
    "normalise_seed",
    "normalize_manifest",
    "open_data_dir",
    "open_data_directory",
    "read_manifest",
    "resolve_path",
    "resolve_relative",
    "resolve_relative_path",
    "safe_join",
    "safe_path",
    "safe_relative_path",
    "save_snapshot",
    "snapshot_id",
    "snapshot_ids",
    "synthetic",
    "validate_manifest",
    "validate_relative",
    "validate_relative_path",
    "write_json_atomic",
    "write_manifest",
    "write_snapshot",
    "write_synthetic",
    "write_synthetic_data",
]

# Seed-file adapters, the raw hash registry and parser reports are re-exported
# here so callers can use either ``topomarket.data.<name>`` or the explicit
# ``topomarket.data.adapters`` package.
__all__ += [name for name in _ADAPTERS_ALL if name not in __all__]
__all__ += [
    "adapter",
    "adapters",
    "cboe",
    "cli",
    "fred",
    "french",
    "hash_registry",
    "importers",
    "normalization",
    "normalize",
    "ofr",
    "openintro",
    "parser_report",
    "parser_reports",
    "pipeline",
    "raw_hashes",
    "raw_hash_registry",
    "raw_registry",
    "registry",
    "reports",
    "source_adapters",
    "sources",
]
