"""Profile loading for the public demo and local private configurations.

Profiles are plain JSON files under ``config/``. The private profile only
describes where user-supplied data would live; it never contains data,
credentials, or secrets itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROFILE_NAMES: tuple[str, ...] = ("demo", "private")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = REPOSITORY_ROOT / "config"

_REQUIRED_FIELDS = (
    "profile",
    "name",
    "description",
    "data_source",
    "data_dir",
    "output_dir",
    "cache_dir",
    "random_seed",
    "private_data",
)


@dataclass(frozen=True)
class Profile:
    """Resolved configuration for one TopoMarket profile."""

    profile: str
    name: str
    description: str
    data_source: str
    data_dir: Path
    output_dir: Path
    cache_dir: Path
    random_seed: int
    private_data: bool
    config_path: Path

    @property
    def is_private(self) -> bool:
        """Whether this profile refers to user-supplied private data."""

        return self.private_data

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of the profile."""

        return {
            "profile": self.profile,
            "name": self.name,
            "description": self.description,
            "data_source": self.data_source,
            "data_dir": str(self.data_dir),
            "output_dir": str(self.output_dir),
            "cache_dir": str(self.cache_dir),
            "random_seed": self.random_seed,
            "private_data": self.private_data,
        }


def config_path_for(profile: str, config_dir: Path | str | None = None) -> Path:
    """Return the configuration path for ``profile``."""

    if profile not in PROFILE_NAMES:
        raise ValueError(
            f"Unknown profile {profile!r}; expected one of: {', '.join(PROFILE_NAMES)}"
        )
    directory = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    return directory / f"{profile}.json"


def load_profile(
    profile: str = "demo",
    config_dir: Path | str | None = None,
) -> Profile:
    """Load and validate a profile from ``config/<profile>.json``.

    Relative data, output, and cache directories are resolved against the
    repository root (the parent of ``config/``) so commands behave the same
    regardless of the current working directory.
    """

    path = config_path_for(profile, config_dir)
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"Profile file {path} must contain a JSON object")

    missing = [field for field in _REQUIRED_FIELDS if field not in raw]
    if missing:
        raise ValueError(
            f"Profile file {path} is missing required fields: {', '.join(missing)}"
        )
    if raw["profile"] != profile:
        raise ValueError(
            f"Profile file {path} declares {raw['profile']!r}, expected {profile!r}"
        )
    if not isinstance(raw["private_data"], bool):
        raise ValueError(f"'private_data' in {path} must be a boolean")
    if not isinstance(raw["random_seed"], int):
        raise ValueError(f"'random_seed' in {path} must be an integer")

    root = path.resolve().parent.parent
    return Profile(
        profile=str(raw["profile"]),
        name=str(raw["name"]),
        description=str(raw["description"]),
        data_source=str(raw["data_source"]),
        data_dir=_resolve(root, raw["data_dir"]),
        output_dir=_resolve(root, raw["output_dir"]),
        cache_dir=_resolve(root, raw["cache_dir"]),
        random_seed=raw["random_seed"],
        private_data=raw["private_data"],
        config_path=path,
    )


def _resolve(root: Path, value: Any) -> Path:
    candidate = Path(str(value))
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


__all__ = [
    "DEFAULT_CONFIG_DIR",
    "PROFILE_NAMES",
    "Profile",
    "REPOSITORY_ROOT",
    "config_path_for",
    "load_profile",
]
