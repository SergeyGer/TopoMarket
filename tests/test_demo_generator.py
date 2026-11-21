"""Public tests for the synthetic demo generator.

The demo generator is the credential-free counterpart of the private import
pipeline.  These tests use only generated values and temporary directories.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from topomarket.data.normalized import read_normalized_table
from topomarket.data.schemas import (
    NORMALIZED_FILE_NAMES,
    NORMALIZED_TABLE_NAMES,
    SCHEMA_CONTRACTS,
)
from topomarket.demo import (
    DEFAULT_SEED,
    DEMO_FILE_NAMES,
    DEMO_TABLE_NAMES,
    DemoGenerator,
    build_demo_dataset,
    demo_tables,
    generate_demo,
    normalise_seed,
    write_demo,
)
from topomarket.demo.__main__ import main as demo_main


def _digests(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_demo_generator_writes_every_normalized_file(tmp_path: Path) -> None:
    output = tmp_path / "demo"

    manifest = generate_demo(output, seed=42, created_at="2024-02-01T00:00:00Z")

    assert DEMO_FILE_NAMES == NORMALIZED_FILE_NAMES
    assert DEMO_TABLE_NAMES == NORMALIZED_TABLE_NAMES
    assert manifest["seed"] == 42
    assert manifest["synthetic"] is True
    assert manifest["private_data"] is False
    assert manifest["tables"] == list(NORMALIZED_TABLE_NAMES)
    assert manifest["file_count"] == len(NORMALIZED_FILE_NAMES)

    for filename in NORMALIZED_FILE_NAMES:
        path = output / filename
        assert path.is_file()
        assert manifest["row_counts"][filename] > 0
        assert manifest["file_hashes"][filename] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert b"\r\n" not in path.read_bytes()
        assert path.read_bytes().endswith(b"\n")

    for table_name in NORMALIZED_TABLE_NAMES:
        contract = SCHEMA_CONTRACTS[table_name]
        record = manifest["schemas"][table_name]
        assert record["file"] == f"{table_name}.csv"
        assert record["columns"] == list(contract.columns)
        assert record["types"] == dict(contract.types)
        assert record["units"] == dict(contract.units)
        dataset = read_normalized_table(output / f"{table_name}.csv")
        assert tuple(dataset.columns) == contract.columns
        assert dataset.schema == dict(contract.types)


def test_demo_generator_is_byte_identical_for_the_same_seed(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_manifest = generate_demo(first, seed=DEFAULT_SEED, created_at="2024-02-01T00:00:00Z")
    second_manifest = generate_demo(second, seed=DEFAULT_SEED, created_at="2024-02-01T00:00:00Z")

    assert _digests(first) == _digests(second)
    assert dict(first_manifest) == dict(second_manifest)
    assert first_manifest["snapshot_id"] == second_manifest["snapshot_id"]


def test_demo_generator_changes_with_a_different_seed(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate_demo(first, seed=42, created_at="2024-02-01T00:00:00Z")
    manifest = generate_demo(second, seed=7, created_at="2024-02-01T00:00:00Z")

    assert manifest["seed"] == 7
    assert any(
        (first / filename).read_bytes() != (second / filename).read_bytes()
        for filename in NORMALIZED_FILE_NAMES
    )


def test_demo_generator_class_and_aliases(tmp_path: Path) -> None:
    generator = DemoGenerator(seed=11)

    manifest = generator.write(out_dir=tmp_path / "class")

    assert manifest["seed"] == 11
    assert (tmp_path / "class" / "manifest.json").is_file()
    assert set(generator.build()) == set(NORMALIZED_FILE_NAMES)
    assert set(generator.tables()) == set(NORMALIZED_TABLE_NAMES)

    alias_manifest = write_demo(out=tmp_path / "alias", seed=11)
    assert alias_manifest["row_counts"] == manifest["row_counts"]
    assert set(build_demo_dataset(11)) == set(NORMALIZED_FILE_NAMES)
    assert set(demo_tables(11)) == set(NORMALIZED_TABLE_NAMES)


def test_demo_seed_validation() -> None:
    assert normalise_seed("42") == 42
    with pytest.raises(ValueError):
        normalise_seed(True)
    with pytest.raises(ValueError):
        normalise_seed("not-a-seed")


def test_demo_module_cli_generates_synthetic_tables(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli"

    assert demo_main(["--out", str(output), "--seed", "123", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["seed"] == 123
    assert payload["synthetic"] is True
    assert payload["private_data"] is False
    assert payload["tables"] == list(NORMALIZED_TABLE_NAMES)
    for filename in NORMALIZED_FILE_NAMES:
        assert (output / filename).is_file()
