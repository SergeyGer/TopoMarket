"""Focused tests for the frozen topology configuration and registry."""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import pytest

import topomarket
from topomarket.topology import (
    DEFAULT_CONFIG,
    DEFAULT_CONFIG_HASH,
    PACKAGED_REGISTRY_PATH,
    SOURCE_REGISTRY_PATH,
    FrozenConfigurationError,
    LoadedTopologyConfig,
    TopologyConfig,
    TopologyConfigError,
    UnknownFieldError,
    config_hash,
    load_topology_config,
)


def _registry_payload() -> dict[str, object]:
    return json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_registry(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_default_values() -> None:
    config = TopologyConfig()

    assert config.window_sessions == 60
    assert config.embedding_dimension == 3
    assert config.lag == 2
    assert config.max_homology_dimension == 1
    assert config.homology_coeff_field == 2
    assert config.min_interval == 1e-8
    assert config.normalization == "robust"
    assert config.reference_window == 252
    assert config.score_scale == 100.0
    assert config.metric == "euclidean"
    assert config.algorithm_version == "tda-v1"
    assert config == DEFAULT_CONFIG


def test_configuration_is_frozen_and_hashable() -> None:
    config = TopologyConfig()

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.window_sessions = 120  # type: ignore[misc]

    assert hash(config) == hash(TopologyConfig())


def test_round_trip_is_stable() -> None:
    config = TopologyConfig(window_sessions=90, reference_window=100, score_scale=50.0)
    payload = config.to_dict()

    assert TopologyConfig.from_dict(payload) == config
    assert TopologyConfig.from_dict(payload).to_dict() == payload
    assert json.dumps(payload, sort_keys=True) == json.dumps(
        TopologyConfig.from_dict(payload).to_dict(), sort_keys=True
    )


def test_nested_config_values_are_supported() -> None:
    config = TopologyConfig.from_dict({"config": {"window_sessions": 90, "lag": 3}})

    assert config.window_sessions == 90
    assert config.lag == 3
    assert config.embedding_dimension == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"window_sessions": 0},
        {"window_sessions": -10},
        {"window_sessions": 4},
        {"window_sessions": True},
        {"window_sessions": 60.0},
        {"embedding_dimension": 1},
        {"embedding_dimension": 2.5},
        {"lag": 0},
        {"lag": -1},
        {"reference_window": 0},
        {"max_homology_dimension": 0},
        {"homology_coeff_field": 1},
        {"min_interval": -0.1},
        {"min_interval": float("nan")},
        {"min_interval": float("inf")},
        {"score_scale": 0},
        {"score_scale": float("inf")},
        {"normalization": "unknown"},
        {"metric": "unknown"},
        {"algorithm_version": ""},
        {"algorithm_version": "   "},
    ],
)
def test_invalid_parameters_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(TopologyConfigError):
        TopologyConfig.from_dict(payload)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(UnknownFieldError):
        TopologyConfig.from_dict({"window_sessions": 60, "mystery": 1})

    with pytest.raises(TypeError):
        TopologyConfig(mystery=1)  # type: ignore[call-arg]


@pytest.mark.parametrize("coeff_field", [2, 3, 5, 7, 11])
def test_prime_homology_coefficient_fields_are_accepted(coeff_field: int) -> None:
    assert TopologyConfig(homology_coeff_field=coeff_field).homology_coeff_field == coeff_field


@pytest.mark.parametrize("coeff_field", [4, 6, 9, 15, 21, 25, 27, 49])
def test_composite_homology_coefficient_fields_are_rejected(coeff_field: int) -> None:
    with pytest.raises(TopologyConfigError, match="prime"):
        TopologyConfig(homology_coeff_field=coeff_field)


@pytest.mark.parametrize("field", ["hash", "sha256", "digest", "name", "config_hash"])
def test_registry_metadata_is_rejected_by_from_dict(field: str) -> None:
    payload = DEFAULT_CONFIG.to_dict() | {field: "unexpected"}

    with pytest.raises(UnknownFieldError, match=field):
        TopologyConfig.from_dict(payload)


def test_unknown_nested_fields_are_rejected() -> None:
    with pytest.raises(UnknownFieldError, match="mystery"):
        TopologyConfig.from_dict({"config": {"window_sessions": 60, "mystery": 1}})

    with pytest.raises(UnknownFieldError, match="hash"):
        TopologyConfig.from_dict({"config": DEFAULT_CONFIG.to_dict(), "hash": DEFAULT_CONFIG_HASH})

    with pytest.raises(UnknownFieldError, match="hash"):
        TopologyConfig.from_dict(
            {"config": DEFAULT_CONFIG.to_dict() | {"hash": DEFAULT_CONFIG_HASH}}
        )


def test_equal_configurations_hash_equally() -> None:
    first = TopologyConfig(min_interval=0, score_scale=100)
    second = TopologyConfig(min_interval=0.0, score_scale=100.0)

    assert first == second
    assert first.config_hash() == second.config_hash()
    assert config_hash(first) == config_hash(first.to_dict())


def test_signed_zero_hashes_like_positive_zero() -> None:
    negative = TopologyConfig(min_interval=-0.0)
    positive = TopologyConfig(min_interval=0.0)

    assert negative == positive
    assert math.copysign(1.0, negative.min_interval) == 1.0
    assert negative.config_hash() == positive.config_hash()


def test_changing_every_field_changes_the_hash() -> None:
    base = TopologyConfig()
    variants = [
        {"window_sessions": 80},
        {"embedding_dimension": 4},
        {"lag": 3},
        {"max_homology_dimension": 2},
        {"homology_coeff_field": 3},
        {"min_interval": 1e-6},
        {"normalization": "none"},
        {"reference_window": 100},
        {"score_scale": 50.0},
        {"metric": "manhattan"},
        {"algorithm_version": "tda-v2"},
    ]

    baseline_hash = base.config_hash()
    seen = {baseline_hash}
    for change in variants:
        changed = dataclasses.replace(base, **change)
        assert changed.config_hash() != baseline_hash
        assert changed.config_hash() not in seen
        seen.add(changed.config_hash())


def test_hash_includes_package_version(monkeypatch: pytest.MonkeyPatch) -> None:
    config = TopologyConfig()
    original = config.config_hash()

    monkeypatch.setattr(topomarket, "__version__", "99.99.99")

    assert config.config_hash() != original


def test_source_registry_entry_is_verifiable() -> None:
    payload = _registry_payload()
    entry = payload["default"]
    assert isinstance(entry, dict)

    flat = {key: value for key, value in entry.items() if key != "config_hash"}
    nested = entry["config"]
    assert isinstance(nested, dict)

    assert (
        entry["config_hash"]
        == TopologyConfig.from_dict(
            {key: value for key, value in flat.items() if key in TopologyConfig.field_names()}
        ).config_hash()
    )
    assert entry["config_hash"] == TopologyConfig.from_dict(nested).config_hash()
    assert TopologyConfig.from_dict(nested) == DEFAULT_CONFIG
    assert entry["config_hash"] == DEFAULT_CONFIG_HASH


def test_default_loading_is_frozen() -> None:
    loaded = load_topology_config()

    assert isinstance(loaded, LoadedTopologyConfig)
    assert isinstance(loaded, TopologyConfig)
    assert loaded == DEFAULT_CONFIG
    assert loaded.to_dict() == DEFAULT_CONFIG.to_dict()
    assert loaded.exploratory is False
    assert loaded.frozen is True
    assert loaded.entry_name == "default"
    assert loaded.config_hash == DEFAULT_CONFIG_HASH
    assert loaded.config_hash() == DEFAULT_CONFIG_HASH
    assert loaded.config == DEFAULT_CONFIG


def test_packaged_and_source_defaults_agree() -> None:
    source = load_topology_config(SOURCE_REGISTRY_PATH)
    packaged = load_topology_config(PACKAGED_REGISTRY_PATH)

    assert source.to_dict() == packaged.to_dict()
    assert source.config_hash == packaged.config_hash == DEFAULT_CONFIG_HASH


def test_mutated_frozen_entry_is_rejected_even_for_custom_loading(tmp_path: Path) -> None:
    payload = _registry_payload()
    entry = payload["default"]
    assert isinstance(entry, dict)
    config = entry["config"]
    assert isinstance(config, dict)
    config["window_sessions"] = 120

    path = _write_registry(tmp_path / "topology.json", payload)

    with pytest.raises(FrozenConfigurationError, match="hash"):
        load_topology_config(path)
    with pytest.raises(FrozenConfigurationError, match="hash"):
        load_topology_config(path, allow_custom=True)


def test_mutated_flat_entry_is_rejected(tmp_path: Path) -> None:
    payload = _registry_payload()
    entry = payload["default"]
    assert isinstance(entry, dict)
    entry["window_sessions"] = 120

    path = _write_registry(tmp_path / "topology.json", payload)

    with pytest.raises(FrozenConfigurationError, match="hash"):
        load_topology_config(path)
    with pytest.raises(FrozenConfigurationError, match="hash"):
        load_topology_config(path, allow_custom=True)


def test_custom_config_requires_explicit_opt_in_and_is_flagged(tmp_path: Path) -> None:
    custom = DEFAULT_CONFIG.to_dict() | {"window_sessions": 120}
    path = _write_registry(tmp_path / "topology.json", {"default": custom})

    with pytest.raises(FrozenConfigurationError):
        load_topology_config(path)

    loaded = load_topology_config(path, allow_custom=True)
    assert loaded.exploratory is True
    assert loaded.is_exploratory is True
    assert loaded.frozen is False
    assert loaded.window_sessions == 120
    assert loaded.config_hash != DEFAULT_CONFIG_HASH


def test_custom_config_with_valid_own_hash_needs_opt_in(tmp_path: Path) -> None:
    custom = TopologyConfig(window_sessions=120)
    entry = custom.registry_entry(name="research")
    path = _write_registry(tmp_path / "topology.json", {"default": entry})

    with pytest.raises(FrozenConfigurationError):
        load_topology_config(path)

    loaded = load_topology_config(path, allow_custom=True)
    assert loaded.exploratory is True
    assert loaded.window_sessions == 120


def test_registry_metadata_is_handled_by_the_loader(tmp_path: Path) -> None:
    entry = DEFAULT_CONFIG.to_dict() | {
        "name": "default",
        "config": DEFAULT_CONFIG.to_dict(),
        "config_hash": DEFAULT_CONFIG_HASH,
    }
    path = _write_registry(tmp_path / "topology.json", {"default": entry})

    loaded = load_topology_config(path)
    assert loaded == DEFAULT_CONFIG
    assert loaded.frozen is True


def test_named_registry_entry_is_honored(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "entries": {
            "default": DEFAULT_CONFIG.registry_entry(),
            "research": TopologyConfig(window_sessions=120).registry_entry(name="research"),
        },
    }
    path = _write_registry(tmp_path / "topology.json", payload)

    frozen = load_topology_config(path)
    assert frozen == DEFAULT_CONFIG
    assert frozen.entry_name == "default"
    assert frozen.frozen is True

    loaded = load_topology_config(path, allow_custom=True, name="research")
    assert loaded.window_sessions == 120
    assert loaded.entry_name == "research"
    assert loaded.exploratory is True


def test_unknown_registry_entry_name_is_rejected(tmp_path: Path) -> None:
    payload = {
        "entries": {
            "default": DEFAULT_CONFIG.registry_entry(),
            "research": TopologyConfig(window_sessions=120).registry_entry(name="research"),
        }
    }
    path = _write_registry(tmp_path / "topology.json", payload)

    with pytest.raises(FrozenConfigurationError, match="no 'missing' entry"):
        load_topology_config(path, allow_custom=True, name="missing")


def test_default_only_registry_cannot_silently_return_the_default(tmp_path: Path) -> None:
    path = _write_registry(tmp_path / "topology.json", {"default": DEFAULT_CONFIG.registry_entry()})

    with pytest.raises(FrozenConfigurationError, match="no 'research' entry"):
        load_topology_config(path, allow_custom=True, name="research")


def test_unknown_fields_remain_rejected_in_custom_config(tmp_path: Path) -> None:
    custom = DEFAULT_CONFIG.to_dict() | {"window_sessions": 120, "unknown": 1}
    path = _write_registry(tmp_path / "topology.json", {"default": custom})

    with pytest.raises(UnknownFieldError):
        load_topology_config(path, allow_custom=True)


def test_unknown_nested_fields_are_rejected_in_registry(tmp_path: Path) -> None:
    payload = _registry_payload()
    entry = payload["default"]
    assert isinstance(entry, dict)
    nested = entry["config"]
    assert isinstance(nested, dict)
    nested["mystery"] = 1

    path = _write_registry(tmp_path / "topology.json", payload)

    with pytest.raises(UnknownFieldError, match="mystery"):
        load_topology_config(path, allow_custom=True)


def test_missing_registry_is_a_readable_error(tmp_path: Path) -> None:
    with pytest.raises(FrozenConfigurationError, match="Unable to read"):
        load_topology_config(tmp_path / "missing.json")
