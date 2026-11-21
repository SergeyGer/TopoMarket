"""Behavioural tests for demo/private profile resolution.

These tests are deliberately independent of the ambient HOME/TMPDIR layout:
paths used for assertions are either explicit ``tmp_path`` locations or the
resolver's own reported defaults. Sandboxed test runs sometimes place HOME
inside the checkout, so tests must not assume otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket import profiles
from topomarket.profiles import (
    DEFAULT_CONFIG_DIR,
    DEFAULT_DEMO_DATA_DIR,
    DEFAULT_PRIVATE_DATA_DIR,
    ENV_CONFIG_DIR,
    ENV_DATA_DIR,
    ENV_DEMO_DATA_DIR,
    ENV_PRIVATE_DATA_DIR,
    PROFILE_NAMES,
    config_path_for,
    load_profile,
    resolve_profile,
)

_ENV_NAMES = (
    "TOPOMARKET_DATA_DIR",
    "TOPOMARKET_PRIVATE_DATA_DIR",
    "TOPOMARKET_DEMO_DATA_DIR",
    "TOPOMARKET_CONFIG_DIR",
    "TOPOMARKET_PRIVATE_DATA",
    "TOPOMARKET_PRIVATE_DIR",
    "TOPOMARKET_PRIVATE_DATA_PATH",
    "TOPOMARKET_DEMO_DATA",
    "TOPOMARKET_DEMO_DIR",
    "TOPOMARKET_DEMO_DATA_PATH",
    "TOPOMARKET_CONFIG",
    "TOPOMARKET_CONFIG_HOME",
    "TOPOMARKET_DATA",
    "TOPOMARKET_DATA_PATH",
    "TOPO_MARKET_PRIVATE_DATA_DIR",
    "TOPO_MARKET_DEMO_DATA_DIR",
    "TOPO_MARKET_CONFIG_DIR",
    "TOPO_MARKET_DATA_DIR",
)


@pytest.fixture(autouse=True)
def clear_profile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ambient developer configuration from affecting these tests."""

    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _write_profile(
    directory: Path,
    profile: str,
    *,
    overrides: dict[str, object] | None = None,
) -> Path:
    """Write a valid profile file based on the bundled configuration."""

    source = DEFAULT_CONFIG_DIR / f"{profile}.json"
    config = json.loads(source.read_text(encoding="utf-8"))
    if overrides:
        config.update(overrides)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{profile}.json"
    destination.write_text(json.dumps(config), encoding="utf-8")
    return destination


def test_demo_profile_uses_bundled_synthetic_data() -> None:
    profile = load_profile("demo")

    assert profile.profile == "demo"
    assert profile.private_data is False
    assert profile.is_private is False
    assert profile.data_source == "synthetic"
    assert profile.data_dir == DEFAULT_DEMO_DATA_DIR
    assert profile.data_dir.is_dir()
    assert (profile.data_dir / "demo_markets.json").is_file()
    assert profile.config_path == DEFAULT_CONFIG_DIR / "demo.json"
    assert profile.output_dir.is_absolute()
    assert profile.cache_dir.is_absolute()


def test_private_profile_default_data_dir_is_absolute_and_stable() -> None:
    profile = load_profile("private")

    assert profile.profile == "private"
    assert profile.private_data is True
    assert profile.is_private is True
    assert profile.data_dir == DEFAULT_PRIVATE_DATA_DIR
    assert profile.data_dir == profiles._default_private_data_dir()
    assert profile.data_dir.is_absolute()


def test_private_default_is_pushed_outside_a_fake_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The fallback chain must not return a directory inside the checkout."""

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    monkeypatch.setattr(profiles, "REPOSITORY_ROOT", fake_repo)
    monkeypatch.setenv("HOME", str(fake_repo / "home"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("TMPDIR", str(fake_repo / "tmp"))
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    resolved = profiles._default_private_data_dir()

    assert not resolved.is_relative_to(fake_repo)
    assert resolved == (tmp_path / "topomarket-private").resolve()


def test_private_profile_specific_environment_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "private-data"
    monkeypatch.setenv(ENV_PRIVATE_DATA_DIR, str(target))

    profile = load_profile("private")

    assert profile.data_dir == target


def test_private_profile_generic_environment_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "generic-data"
    monkeypatch.setenv(ENV_DATA_DIR, str(target))

    profile = load_profile("private")

    assert profile.data_dir == target


def test_demo_profile_environment_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "demo-data"
    monkeypatch.setenv(ENV_DEMO_DATA_DIR, str(target))

    profile = load_profile("demo")

    assert profile.data_dir == target


def test_explicit_data_dir_beats_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path / "environment"))
    explicit = tmp_path / "explicit"

    profile = load_profile("private", data_dir=explicit)

    assert profile.data_dir == explicit


def test_explicit_data_dir_accepts_relative_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    profile = load_profile("private", data_dir="operator-data")

    assert profile.data_dir == (tmp_path / "operator-data").resolve()


def test_environment_override_can_point_inside_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inside = tmp_path / "explicit-private-data"
    monkeypatch.setenv(ENV_PRIVATE_DATA_DIR, str(inside))

    profile = load_profile("private")

    assert profile.data_dir == inside


def test_unknown_profile_fails_clearly() -> None:
    with pytest.raises(ValueError, match="Unknown profile 'mystery'"):
        load_profile("mystery")

    with pytest.raises(ValueError, match="Unknown profile 'mystery'"):
        config_path_for("mystery")

    with pytest.raises(ValueError, match="Unknown profile 'Demo'"):
        resolve_profile("Demo")


def test_config_dir_can_be_overridden_by_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_CONFIG_DIR, str(tmp_path))

    assert config_path_for("demo") == tmp_path / "demo.json"
    assert config_path_for("demo", config_dir=tmp_path / "other") == (
        tmp_path / "other" / "demo.json"
    )


def test_custom_private_config_can_use_relative_data_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    _write_profile(config_dir, "private", overrides={"data_dir": "operator-data"})

    profile = load_profile("private", config_dir=config_dir)

    assert profile.data_dir == (tmp_path / "operator-data").resolve()


def test_custom_private_config_can_use_absolute_data_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    target = tmp_path / "private-target"
    _write_profile(config_dir, "private", overrides={"data_dir": str(target)})

    profile = load_profile("private", config_dir=config_dir)

    assert profile.data_dir == target


def test_load_profile_as_dict() -> None:
    profile = load_profile("demo")
    payload = profile.as_dict()

    assert payload["profile"] == "demo"
    assert payload["private_data"] is False
    assert payload["data_dir"] == str(profile.data_dir)


@pytest.mark.parametrize("profile", PROFILE_NAMES)
def test_load_profile_round_trips_bundled_configs(profile: str) -> None:
    loaded = load_profile(profile)

    assert loaded.profile == profile
    assert loaded.config_path.name == f"{profile}.json"
    assert loaded.config_path.parent == DEFAULT_CONFIG_DIR


def test_missing_required_fields_are_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    _write_profile(config_dir, "demo")
    config = json.loads((config_dir / "demo.json").read_text(encoding="utf-8"))
    del config["data_dir"]
    (config_dir / "demo.json").write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required fields: data_dir"):
        load_profile("demo", config_dir=config_dir)


def test_mismatched_profile_name_is_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    _write_profile(config_dir, "demo", overrides={"profile": "private"})

    with pytest.raises(ValueError, match="declares 'private'"):
        load_profile("demo", config_dir=config_dir)


def test_invalid_private_data_flag_is_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    _write_profile(config_dir, "demo", overrides={"private_data": "yes"})

    with pytest.raises(ValueError, match="'private_data'.*must be a boolean"):
        load_profile("demo", config_dir=config_dir)


def test_invalid_random_seed_is_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    _write_profile(config_dir, "demo", overrides={"random_seed": "forty-two"})

    with pytest.raises(ValueError, match="'random_seed'.*must be an integer"):
        load_profile("demo", config_dir=config_dir)


def test_non_object_profile_file_is_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "demo.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a JSON object"):
        load_profile("demo", config_dir=config_dir)
