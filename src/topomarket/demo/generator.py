"""Deterministic demo data generator for the normalised TopoMarket tables.

This is the public, credential-free counterpart of the private seed-file import
pipeline.  Both paths emit the same ``sp500_daily``, ``industries_daily`` and
``tda_daily`` schemas; only the values differ (the demo values are synthetic
and clearly marked as such in the manifest).
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from topomarket import __version__
from topomarket.data.manifest import (
    MANIFEST_GENERATOR,
    MANIFEST_SCHEMA_VERSION,
    _atomic_write_text,
    write_manifest,
)
from topomarket.data.normalized import (
    DEMO_DAY_COUNT,
    DEMO_START_DATE,
    build_demo_normalized_tables,
    demo_dataset,
)
from topomarket.data.schemas import (
    NORMALIZED_FILE_NAMES,
    NORMALIZED_TABLE_NAMES,
    SCHEMA_CONTRACTS,
)

GENERATOR_NAME = "topomarket.demo"
DEMO_GENERATOR_NAME = GENERATOR_NAME
DEFAULT_SEED = 42
DEFAULT_DAY_COUNT = DEMO_DAY_COUNT
DEMO_FILE_NAMES: tuple[str, ...] = NORMALIZED_FILE_NAMES
DEMO_TABLE_NAMES: tuple[str, ...] = NORMALIZED_TABLE_NAMES
DEMO_START = DEMO_START_DATE
DEFAULT_START_DATE = DEMO_START_DATE
DEFAULT_DAYS = DEMO_DAY_COUNT


def normalise_seed(seed: Any) -> int:
    """Return ``seed`` as an integer, rejecting booleans and bad values."""

    if isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    try:
        return int(seed)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"seed must be an integer, got {seed!r}") from exc


def _csv_text(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Serialise rows as CSV with stable formatting and Unix line endings."""

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _file_entry(path: str, digest: str, size: int, rows: int) -> dict[str, Any]:
    return {
        "path": path,
        "name": path,
        "filename": path,
        "sha256": digest,
        "checksum": digest,
        "bytes": size,
        "size_bytes": size,
        "rows": rows,
        "row_count": rows,
    }


def _resolve_output(target: Path | str | None, overrides: Mapping[str, Any]) -> Path:
    candidates = [target]
    for key in ("out", "out_dir", "output_dir", "output"):
        candidates.append(overrides.get(key))
    for candidate in candidates:
        if candidate is not None:
            return Path(candidate)
    raise TypeError("an output directory is required")


def build_demo_dataset(
    seed: Any = DEFAULT_SEED,
    *,
    start_date: date = DEMO_START_DATE,
    days: int = DEMO_DAY_COUNT,
) -> dict[str, tuple[tuple[str, ...], list[tuple[Any, ...]]]]:
    """Return the demo CSVs as ``filename -> (header, rows)`` pairs."""

    return demo_dataset(normalise_seed(seed), start_date=start_date, days=days)


def demo_tables(
    seed: Any = DEFAULT_SEED,
    *,
    start_date: date = DEMO_START_DATE,
    days: int = DEMO_DAY_COUNT,
):
    """Return the demo tables as normalised datasets keyed by table name."""

    return build_demo_normalized_tables(normalise_seed(seed), start_date=start_date, days=days)


class DemoGenerator:
    """Generate the deterministic synthetic demo tables."""

    name = GENERATOR_NAME
    version = __version__

    def __init__(self, seed: Any = DEFAULT_SEED) -> None:
        self.seed = normalise_seed(seed)

    def build(self) -> dict[str, tuple[tuple[str, ...], list[tuple[Any, ...]]]]:
        return build_demo_dataset(self.seed)

    def tables(self):
        return demo_tables(self.seed)

    def generate(
        self,
        out_dir: Path | str | None = None,
        *,
        seed: Any | None = None,
        created_at: str | datetime | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if seed is not None:
            self.seed = normalise_seed(seed)
        destination = _resolve_output(out_dir, kwargs)
        destination.mkdir(parents=True, exist_ok=True)

        dataset = self.build()
        file_entries: list[dict[str, Any]] = []
        file_hashes: dict[str, str] = {}
        row_counts: dict[str, int] = {}
        for filename in DEMO_FILE_NAMES:
            header, rows = dataset[filename]
            text = _csv_text(header, rows)
            encoded = text.encode("utf-8")
            _atomic_write_text(destination / filename, text)
            digest = hashlib.sha256(encoded).hexdigest()
            file_entries.append(_file_entry(filename, digest, len(encoded), len(rows)))
            file_hashes[filename] = digest
            row_counts[filename] = len(rows)

        total_rows = sum(row_counts.values())
        table_schemas = {
            table_name: {
                "file": f"{table_name}.csv",
                "columns": list(SCHEMA_CONTRACTS[table_name].columns),
                "types": dict(SCHEMA_CONTRACTS[table_name].types),
                "units": dict(SCHEMA_CONTRACTS[table_name].units),
                "row_count": row_counts.get(f"{table_name}.csv", 0),
            }
            for table_name in DEMO_TABLE_NAMES
        }
        metadata = {
            "generator": GENERATOR_NAME,
            "generator_version": __version__,
            "seed": self.seed,
            "synthetic": True,
            "private_data": False,
            "row_counts": dict(row_counts),
            "tables": list(DEMO_TABLE_NAMES),
            "schemas": table_schemas,
        }
        payload: dict[str, Any] = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "generator": MANIFEST_GENERATOR,
            "generator_name": GENERATOR_NAME,
            "generator_version": __version__,
            "name": GENERATOR_NAME,
            "version": __version__,
            "profile": "demo",
            "data_source": "synthetic",
            "source": "synthetic",
            "data_dir": ".",
            "seed": self.seed,
            "synthetic": True,
            "private_data": False,
            "file_count": len(file_entries),
            "files": file_entries,
            "file_hashes": dict(file_hashes),
            "checksums": dict(file_hashes),
            "hashes": dict(file_hashes),
            "row_counts": dict(row_counts),
            "rows": dict(row_counts),
            "row_count": total_rows,
            "total_rows": total_rows,
            "tables": list(DEMO_TABLE_NAMES),
            "normalized_tables": list(DEMO_TABLE_NAMES),
            "schemas": table_schemas,
            "metadata": metadata,
        }
        return write_manifest(destination, payload, created_at=created_at)

    def write(self, out_dir: Path | str | None = None, **kwargs: Any) -> dict[str, Any]:
        return self.generate(out_dir, **kwargs)

    __call__ = generate


def generate_demo(
    out_dir: Path | str | None = None,
    seed: Any = DEFAULT_SEED,
    *,
    created_at: str | datetime | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Write deterministic demo tables and a manifest below ``out_dir``."""

    return DemoGenerator(seed=seed).generate(out_dir, created_at=created_at, **kwargs)


def write_demo(
    out_dir: Path | str | None = None,
    seed: Any = DEFAULT_SEED,
    **kwargs: Any,
) -> dict[str, Any]:
    """Alias for :func:`generate_demo`."""

    return generate_demo(out_dir, seed=seed, **kwargs)


# Common alternative spellings used by scripts and tests.
SyntheticDemoGenerator = DemoGenerator
SyntheticDemoDataGenerator = DemoGenerator
DemoDataGenerator = DemoGenerator
SyntheticGenerator = DemoGenerator
DataGenerator = DemoGenerator
generate_demo_data = generate_demo
generate_demo_dataset = generate_demo
generate_synthetic_demo = generate_demo
write_demo_data = generate_demo
demo = generate_demo
build_dataset = build_demo_dataset
generate = generate_demo
write = generate_demo


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
    "DemoGenerator",
    "DataGenerator",
    "SyntheticGenerator",
    "SyntheticDemoDataGenerator",
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
