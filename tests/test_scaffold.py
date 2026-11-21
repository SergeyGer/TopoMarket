"""Scaffold-level tests for repository structure and profile configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket.profiles import PROFILE_NAMES, load_profile

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "app.py",
    "README.md",
    "pyproject.toml",
    ".gitignore",
    "config/demo.json",
    "config/private.json",
    ".github/workflows/ci.yml",
    "src/topomarket/__init__.py",
    "src/topomarket/__main__.py",
    "src/topomarket/cli.py",
    "src/topomarket/profiles.py",
    "src/topomarket/data/__init__.py",
    "src/topomarket/ui/__init__.py",
    "src/topomarket/topology/__init__.py",
    "src/topomarket/evaluation/__init__.py",
]

REQUIRED_CONFIG_FIELDS = [
    "profile",
    "name",
    "description",
    "data_source",
    "data_dir",
    "output_dir",
    "cache_dir",
    "random_seed",
    "private_data",
]


@pytest.mark.parametrize("relative_path", REQUIRED_FILES)
def test_required_files_exist(relative_path: str) -> None:
    assert (REPO_ROOT / relative_path).is_file(), relative_path


@pytest.mark.parametrize("profile", PROFILE_NAMES)
def test_config_has_required_fields(profile: str) -> None:
    path = REPO_ROOT / "config" / f"{profile}.json"
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    for field in REQUIRED_CONFIG_FIELDS:
        assert field in config, f"{profile}: missing {field}"
    assert config["profile"] == profile
    assert isinstance(config["private_data"], bool)


def test_demo_config_is_public_and_synthetic() -> None:
    config = json.loads((REPO_ROOT / "config" / "demo.json").read_text(encoding="utf-8"))
    assert config["private_data"] is False
    assert config["data_source"] == "synthetic"


def test_private_config_does_not_contain_secrets() -> None:
    text = (REPO_ROOT / "config" / "private.json").read_text(encoding="utf-8").lower()
    for marker in ("token", "password", "secret", "api_key", "apikey"):
        assert marker not in text


@pytest.mark.parametrize("profile", PROFILE_NAMES)
def test_load_profile(profile: str) -> None:
    loaded = load_profile(profile)
    assert loaded.profile == profile
    assert loaded.config_path.name == f"{profile}.json"


def test_gitignore_preserves_private_paths() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "private_data/" in text
    assert ".adp-inputs/" in text
