"""Tests for the data package API and the generator compatibility module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket.data import (
    SYNTHETIC_FILE_NAMES,
    build_dataset,
    generator,
    load_demo_markets,
    synthetic,
)


def test_load_demo_markets_uses_the_bundled_synthetic_file() -> None:
    markets = load_demo_markets()

    assert markets
    assert all(isinstance(market, dict) for market in markets)
    assert all("id" in market for market in markets)


def test_load_demo_markets_accepts_an_alternative_path(tmp_path: Path) -> None:
    custom = tmp_path / "markets.json"
    payload = {"markets": [{"id": "custom", "name": "Custom market"}]}
    custom.write_text(json.dumps(payload), encoding="utf-8")

    assert load_demo_markets(custom) == payload["markets"]


def test_load_demo_markets_rejects_a_non_list_markets_field(tmp_path: Path) -> None:
    custom = tmp_path / "markets.json"
    custom.write_text(json.dumps({"markets": {"id": "wrong"}}), encoding="utf-8")

    with pytest.raises(ValueError, match="Expected a list of markets"):
        load_demo_markets(custom)


def test_generator_module_reexports_the_synthetic_api() -> None:
    assert generator.SyntheticGenerator is synthetic.SyntheticGenerator
    assert generator.generate_synthetic is synthetic.generate_synthetic
    assert generator.build_dataset is synthetic.build_dataset
    assert generator.__all__ == synthetic.__all__


def test_build_dataset_is_deterministic_and_well_formed() -> None:
    first = build_dataset(17)
    second = build_dataset(17)

    assert first == second
    assert set(first) == set(SYNTHETIC_FILE_NAMES)
    for header, rows in first.values():
        assert isinstance(header, tuple)
        assert header
        assert isinstance(rows, list)
        assert all(len(row) == len(header) for row in rows)

    assert build_dataset(18) != first
