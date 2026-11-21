"""Tests for the deterministic synthetic data generator."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from topomarket import __version__
from topomarket.cli import main
from topomarket.data import read_manifest
from topomarket.data.synthetic import (
    DEFAULT_MARKET_COUNT,
    DEFAULT_PRICE_DAYS,
    DEFAULT_SEED,
    GENERATOR_NAME,
    SYNTHETIC_FILE_NAMES,
    SyntheticGenerator,
    generate_synthetic,
    normalise_seed,
)


def _read_manifest(directory: Path) -> dict[str, object]:
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def _csv_rows(directory: Path, filename: str) -> list[dict[str, str]]:
    with (directory / filename).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_generator_writes_csvs_and_manifest(tmp_path: Path) -> None:
    out = tmp_path / "synthetic"
    manifest = generate_synthetic(out)

    for filename in SYNTHETIC_FILE_NAMES:
        assert (out / filename).is_file(), filename

    assert manifest["synthetic"] is True
    assert manifest["seed"] == DEFAULT_SEED
    assert manifest["generator"] == "topomarket"
    assert manifest["generator_name"] == GENERATOR_NAME
    assert manifest["generator_version"] == __version__
    assert manifest["created_at"]
    assert manifest["file_count"] == len(SYNTHETIC_FILE_NAMES)
    assert manifest["row_count"] == manifest["total_rows"]
    assert set(manifest["row_counts"]) == set(SYNTHETIC_FILE_NAMES)
    assert manifest["row_counts"]["markets.csv"] == DEFAULT_MARKET_COUNT
    assert manifest["row_counts"]["prices.csv"] == DEFAULT_MARKET_COUNT * DEFAULT_PRICE_DAYS
    assert set(manifest["file_hashes"]) == set(SYNTHETIC_FILE_NAMES)

    for entry in manifest["files"]:
        path = out / entry["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["sha256"] == digest
        assert manifest["file_hashes"][entry["path"]] == digest
        assert entry["rows"] == manifest["row_counts"][entry["path"]]
        assert entry["rows"] == len(_csv_rows(out, entry["path"]))

    assert read_manifest(out)["snapshot_id"] == manifest["snapshot_id"]


def test_same_seed_produces_byte_identical_files(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate_synthetic(first, seed=42)
    generate_synthetic(second, seed=42)

    for filename in SYNTHETIC_FILE_NAMES:
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

    first_manifest = _read_manifest(first)
    second_manifest = _read_manifest(second)
    assert first_manifest["file_hashes"] == second_manifest["file_hashes"]
    assert first_manifest["snapshot_id"] == second_manifest["snapshot_id"]

    # The manifest intentionally records when it was created; everything else
    # must be identical for the same seed.
    first_manifest.pop("created_at")
    second_manifest.pop("created_at")
    assert first_manifest == second_manifest


def test_different_seeds_produce_different_data(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate_synthetic(first, seed=42)
    manifest = generate_synthetic(second, seed=7)

    assert manifest["seed"] == 7
    assert any(
        (first / filename).read_bytes() != (second / filename).read_bytes()
        for filename in SYNTHETIC_FILE_NAMES
    )


def test_generator_class_and_keyword_aliases(tmp_path: Path) -> None:
    generator = SyntheticGenerator(seed=11)
    manifest = generator.write(output_dir=tmp_path / "data")

    assert manifest["seed"] == 11
    assert (tmp_path / "data" / "manifest.json").is_file()


def test_normalise_seed_rejects_bad_values() -> None:
    assert normalise_seed("42") == 42
    with pytest.raises(ValueError):
        normalise_seed("not-a-seed")
    with pytest.raises(ValueError):
        normalise_seed(True)


def test_cli_generates_synthetic_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "cli-output"

    assert main(["synthetic", "--out", str(out)]) == 0
    output = capsys.readouterr().out
    assert "synthetic" in output.lower()
    assert "seed=42" in output

    manifest = _read_manifest(out)
    assert manifest["seed"] == 42
    assert manifest["synthetic"] is True
    for filename in SYNTHETIC_FILE_NAMES:
        assert (out / filename).is_file()

    assert main(["synthetic", "--out", str(out), "--seed", "123"]) == 0
    assert _read_manifest(out)["seed"] == 123
