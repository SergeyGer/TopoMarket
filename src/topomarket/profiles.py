"""Profile loading for the public demo and local private configurations.

Profiles are plain JSON files under ``config/``. The private profile only
describes where user-supplied data would live; it never contains data,
credentials, or secrets itself.

The private profile deliberately defaults to a location outside the checkout
so that operator-supplied data never lands in the repository by accident. The
location can be overridden with an environment variable or an explicit
``data_dir`` argument (for example, from a CLI ``--data-dir`` option).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROFILE_NAMES: tuple[str, ...] = ("demo", "private")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = REPOSITORY_ROOT / "config"
DEFAULT_DEMO_DATA_DIR = (REPOSITORY_ROOT / "src" / "topomarket" / "data").resolve()

# Environment variables understood by the profile loader. Profile-specific
# variables take precedence over the generic data-directory override.
DATA_DIR_ENV_VAR = "TOPOMARKET_DATA_DIR"
PRIVATE_DATA_DIR_ENV_VAR = "TOPOMARKET_PRIVATE_DATA_DIR"
DEMO_DATA_DIR_ENV_VAR = "TOPOMARKET_DEMO_DATA_DIR"
CONFIG_DIR_ENV_VAR = "TOPOMARKET_CONFIG_DIR"

# Aliases kept for scripts and documentation that used shorter names.
ENV_DATA_DIR = DATA_DIR_ENV_VAR
ENV_PRIVATE_DATA_DIR = PRIVATE_DATA_DIR_ENV_VAR
ENV_DEMO_DATA_DIR = DEMO_DATA_DIR_ENV_VAR
ENV_CONFIG_DIR = CONFIG_DIR_ENV_VAR
DATA_DIR_ENV = DATA_DIR_ENV_VAR
PRIVATE_DATA_ENV_VAR = PRIVATE_DATA_DIR_ENV_VAR
DEMO_DATA_ENV_VAR = DEMO_DATA_DIR_ENV_VAR
CONFIG_ENV_VAR = CONFIG_DIR_ENV_VAR

_PRIVATE_DATA_ENV_VARS = (
    PRIVATE_DATA_DIR_ENV_VAR,
    "TOPOMARKET_PRIVATE_DATA",
    "TOPOMARKET_PRIVATE_DIR",
    "TOPOMARKET_PRIVATE_DATA_PATH",
    "TOPO_MARKET_PRIVATE_DATA_DIR",
    DATA_DIR_ENV_VAR,
    "TOPOMARKET_DATA",
    "TOPOMARKET_DATA_PATH",
    "TOPO_MARKET_DATA_DIR",
)
_DEMO_DATA_ENV_VARS = (
    DEMO_DATA_DIR_ENV_VAR,
    "TOPOMARKET_DEMO_DATA",
    "TOPOMARKET_DEMO_DIR",
    "TOPOMARKET_DEMO_DATA_PATH",
    "TOPO_MARKET_DEMO_DATA_DIR",
    DATA_DIR_ENV_VAR,
    "TOPOMARKET_DATA",
    "TOPOMARKET_DATA_PATH",
    "TOPO_MARKET_DATA_DIR",
)
_CONFIG_DIR_ENV_VARS = (
    CONFIG_DIR_ENV_VAR,
    "TOPOMARKET_CONFIG",
    "TOPOMARKET_CONFIG_HOME",
    "TOPO_MARKET_CONFIG_DIR",
)

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


def _data_root() -> Path:
    """Return the platform-appropriate base directory for user data."""

    if os.name == "nt":
        override = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(override).expanduser() if override else Path.home() / "AppData" / "Local"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    override = os.environ.get("XDG_DATA_HOME")
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_absolute():
            return candidate
    return Path.home() / ".local" / "share"


def _temp_root() -> Path:
    """Return the temporary directory, honouring live environment changes.

    ``tempfile.gettempdir()`` caches its result, which makes it awkward to test
    in a sandbox whose ``TMPDIR`` moves. Read the usual variables first and
    only fall back to :mod:`tempfile`.
    """

    for name in ("TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser()
    return Path(tempfile.gettempdir())


def _is_within_repository(path: Path) -> bool:
    """Whether ``path`` points inside the checkout."""

    try:
        return path.resolve().is_relative_to(REPOSITORY_ROOT)
    except (OSError, ValueError):  # pragma: no cover - defensive only
        return False


def _default_private_data_dir() -> Path:
    """Compute a private-data default that is never inside the checkout."""

    candidate = _data_root() / "topomarket" / "private"
    if not _is_within_repository(candidate):
        return candidate.resolve()

    # Sandboxed and containerised environments sometimes put HOME or TMPDIR
    # inside the repository. Fall back until the location is outside it.
    candidate = _temp_root() / "topomarket" / "private"
    if not _is_within_repository(candidate):
        return candidate.resolve()
    return (REPOSITORY_ROOT.parent / "topomarket-private").resolve()


DEFAULT_PRIVATE_DATA_DIR = _default_private_data_dir()


def _env_value(names: tuple[str, ...]) -> str | None:
    """Return the first non-empty environment value from ``names``."""

    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _resolve(root: Path, value: Any) -> Path:
    """Resolve a configured path, expanding ``~`` and environment variables."""

    candidate = Path(os.path.expandvars(str(value))).expanduser()
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


def _resolve_user_path(value: Any) -> Path:
    """Resolve an explicit or environment-provided path against the CWD."""

    candidate = Path(os.path.expandvars(str(value))).expanduser()
    return candidate if candidate.is_absolute() else candidate.resolve()


def _is_bundled_private_config(path: Path) -> bool:
    """Whether ``path`` is the repository's own private profile template."""

    try:
        return path.resolve() == (DEFAULT_CONFIG_DIR / "private.json").resolve()
    except (OSError, ValueError):  # pragma: no cover - defensive only
        return False


def config_path_for(profile: str, config_dir: Path | str | None = None) -> Path:
    """Return the configuration path for ``profile``.

    ``config_dir`` may be supplied explicitly or through
    ``TOPOMARKET_CONFIG_DIR``.
    """

    if profile not in PROFILE_NAMES:
        raise ValueError(
            f"Unknown profile {profile!r}; expected one of: {', '.join(PROFILE_NAMES)}"
        )

    if config_dir is None:
        environment_dir = _env_value(_CONFIG_DIR_ENV_VARS)
        if environment_dir is not None:
            config_dir = environment_dir
    directory = Path(config_dir).expanduser() if config_dir is not None else DEFAULT_CONFIG_DIR
    return directory / f"{profile}.json"


def _resolve_data_dir(
    profile: str,
    raw: dict[str, Any],
    root: Path,
    override: Any,
    config_path: Path,
) -> Path:
    """Resolve the data directory for ``profile``.

    Precedence is: explicit override, profile-specific environment variable,
    generic environment variable, then the profile default. The bundled
    private template's relative ``private_data`` placeholder is treated as a
    default rather than as a real in-checkout location; custom configuration
    files may use relative paths next to themselves.
    """

    if override is not None and str(override).strip():
        return _resolve_user_path(override)

    if profile == "private":
        environment_dir = _env_value(_PRIVATE_DATA_ENV_VARS)
        if environment_dir is not None:
            return _resolve_user_path(environment_dir)

        configured = raw.get("data_dir")
        if configured is not None and str(configured).strip():
            candidate = _resolve(root, configured)
            if not _is_bundled_private_config(config_path):
                return candidate
            if not _is_within_repository(candidate):
                return candidate
        return _default_private_data_dir()

    environment_dir = _env_value(_DEMO_DATA_ENV_VARS)
    if environment_dir is not None:
        return _resolve_user_path(environment_dir)

    configured = raw.get("data_dir")
    if configured is not None and str(configured).strip():
        return _resolve(root, configured)
    return DEFAULT_DEMO_DATA_DIR


def load_profile(
    profile: str = "demo",
    config_dir: Path | str | None = None,
    data_dir: Path | str | None = None,
) -> Profile:
    """Load and validate a profile from ``config/<profile>.json``.

    Relative data, output, and cache directories are resolved against the
    repository root (the parent of ``config/``) so commands behave the same
    regardless of the current working directory. The private profile's data
    directory defaults to :data:`DEFAULT_PRIVATE_DATA_DIR`, outside the
    checkout, and can be overridden with ``data_dir`` or an environment
    variable.
    """

    path = config_path_for(profile, config_dir)
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"Profile file {path} must contain a JSON object")

    missing = [field for field in _REQUIRED_FIELDS if field not in raw]
    if missing:
        raise ValueError(f"Profile file {path} is missing required fields: {', '.join(missing)}")
    if raw["profile"] != profile:
        raise ValueError(f"Profile file {path} declares {raw['profile']!r}, expected {profile!r}")
    if not isinstance(raw["private_data"], bool):
        raise ValueError(f"'private_data' in {path} must be a boolean")
    if isinstance(raw["random_seed"], bool) or not isinstance(raw["random_seed"], int):
        raise ValueError(f"'random_seed' in {path} must be an integer")

    root = path.resolve().parent.parent
    resolved_data_dir = _resolve_data_dir(profile, raw, root, data_dir, path)
    return Profile(
        profile=str(raw["profile"]),
        name=str(raw["name"]),
        description=str(raw["description"]),
        data_source=str(raw["data_source"]),
        data_dir=resolved_data_dir,
        output_dir=_resolve(root, raw["output_dir"]),
        cache_dir=_resolve(root, raw["cache_dir"]),
        random_seed=raw["random_seed"],
        private_data=raw["private_data"],
        config_path=path,
    )


def resolve_profile(
    profile: str = "demo",
    config_dir: Path | str | None = None,
    data_dir: Path | str | None = None,
) -> Profile:
    """Alias for :func:`load_profile` with the same resolution rules."""

    return load_profile(profile, config_dir=config_dir, data_dir=data_dir)


__all__ = [
    "CONFIG_DIR_ENV_VAR",
    "CONFIG_ENV_VAR",
    "DATA_DIR_ENV",
    "DATA_DIR_ENV_VAR",
    "DEFAULT_CONFIG_DIR",
    "DEFAULT_DEMO_DATA_DIR",
    "DEFAULT_PRIVATE_DATA_DIR",
    "DEMO_DATA_DIR_ENV_VAR",
    "DEMO_DATA_ENV_VAR",
    "ENV_CONFIG_DIR",
    "ENV_DATA_DIR",
    "ENV_DEMO_DATA_DIR",
    "ENV_PRIVATE_DATA_DIR",
    "PRIVATE_DATA_DIR_ENV_VAR",
    "PRIVATE_DATA_ENV_VAR",
    "PROFILE_NAMES",
    "Profile",
    "REPOSITORY_ROOT",
    "config_path_for",
    "load_profile",
    "resolve_profile",
]
