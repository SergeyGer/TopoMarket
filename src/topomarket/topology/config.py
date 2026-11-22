"""Frozen topology analysis configuration and registry loading.

The topology pipeline must be reproducible: every result and cache identity is
derived from a :class:`TopologyConfig` and the package version.  The canonical
default lives in ``config/topology.json`` while a copy is packaged with the
installation (``topomarket/topology/topology.json``) so loading does not depend
on the current working directory or on a source checkout being present.

Registry entries are JSON objects containing the configuration fields and a
``config_hash``.  For readability a registry may instead nest the fields under
a ``config`` key and put the hash beside it; both forms are accepted and, when
both are present, they must agree.  Registry metadata is handled only by the
loader: :meth:`TopologyConfig.from_dict` accepts configuration fields (and a
single nested ``config`` object), never registry metadata.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from typing import Any

#: Environment variable that can point at an alternative registry file.
CONFIG_ENV_VAR = "TOPOMARKET_TOPOLOGY_CONFIG"
CONFIG_PATH_ENV_VAR = CONFIG_ENV_VAR

#: Registry entry name used for the frozen default configuration.
DEFAULT_NAME = "default"
DEFAULT_ENTRY_NAME = DEFAULT_NAME

#: Normalisation and metric names understood by the pipeline.
NORMALIZATIONS: tuple[str, ...] = ("robust", "none", "identity", "standard", "zscore", "minmax")
METRICS: tuple[str, ...] = (
    "euclidean",
    "manhattan",
    "cityblock",
    "cosine",
    "correlation",
    "chebyshev",
    "hamming",
    "minkowski",
)

# Registry-only keys.  They are consumed by ``load_topology_config`` and are
# never accepted by ``TopologyConfig.from_dict``.
_REGISTRY_META_KEYS: frozenset[str] = frozenset(
    {"config", "config_hash", "hash", "sha256", "digest", "name", "schema_version"}
)
_HASH_KEYS: tuple[str, ...] = ("config_hash", "hash", "sha256", "digest")


class TopologyConfigError(ValueError):
    """Base class for invalid or unverifiable topology configurations."""


class UnknownFieldError(TopologyConfigError, TypeError):
    """Raised when a configuration contains an unknown field.

    It subclasses both :class:`ValueError` (the configuration-error family) and
    :class:`TypeError` (the usual error for an unexpected dataclass keyword).
    """


class FrozenConfigurationError(TopologyConfigError):
    """Raised when a frozen registry entry cannot be verified."""


# Friendly aliases used by callers/tests.
ConfigurationError = TopologyConfigError
UnknownField = UnknownFieldError
FrozenConfigError = FrozenConfigurationError
ConfigHashError = FrozenConfigurationError


def _package_version() -> str:
    """Return ``topomarket.__version__`` as observed at call time."""

    package = import_module("topomarket")
    version = getattr(package, "__version__", None)
    if not isinstance(version, str) or not version:
        raise TopologyConfigError("topomarket.__version__ must be a non-empty string")
    return version


def _require_int(name: str, value: Any, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TopologyConfigError(f"{name} must be an integer, got {value!r}")
    if value < minimum:
        raise TopologyConfigError(f"{name} must be >= {minimum}, got {value!r}")
    return value


def _is_prime(value: int) -> bool:
    """Return whether ``value`` is a prime suitable for a coefficient field."""

    if value < 2:
        return False
    if value == 2:
        return True
    if value % 2 == 0:
        return False
    limit = math.isqrt(value)
    for divisor in range(3, limit + 1, 2):
        if value % divisor == 0:
            return False
    return True


def _require_finite_number(name: str, value: Any, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TopologyConfigError(f"{name} must be a finite number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise TopologyConfigError(f"{name} must be finite, got {value!r}")
    if minimum is not None and number < minimum:
        raise TopologyConfigError(f"{name} must be >= {minimum}, got {value!r}")
    # JSON renders -0.0 differently from 0.0 even though the values compare
    # equal.  Collapse signed zero so equal configurations always hash equally.
    if number == 0.0:
        number = 0.0
    return number


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TopologyConfigError(f"{name} must be a non-empty string, got {value!r}")
    return value


@dataclass(frozen=True, init=False)
class TopologyConfig:
    """Immutable configuration for one topology analysis run."""

    window_sessions: int = 60
    embedding_dimension: int = 3
    lag: int = 2
    max_homology_dimension: int = 1
    homology_coeff_field: int = 2
    min_interval: float = 1e-8
    normalization: str = "robust"
    reference_window: int = 252
    score_scale: float = 100.0
    metric: str = "euclidean"
    algorithm_version: str = "tda-v1"

    def __init__(
        self,
        window_sessions: int = 60,
        embedding_dimension: int = 3,
        lag: int = 2,
        max_homology_dimension: int = 1,
        homology_coeff_field: int = 2,
        min_interval: float = 1e-8,
        normalization: str = "robust",
        reference_window: int = 252,
        score_scale: float = 100.0,
        metric: str = "euclidean",
        algorithm_version: str = "tda-v1",
        **unknown: Any,
    ) -> None:
        if unknown:
            names = ", ".join(sorted(str(key) for key in unknown))
            raise UnknownFieldError(f"unknown field(s) for TopologyConfig: {names}")
        object.__setattr__(self, "window_sessions", window_sessions)
        object.__setattr__(self, "embedding_dimension", embedding_dimension)
        object.__setattr__(self, "lag", lag)
        object.__setattr__(self, "max_homology_dimension", max_homology_dimension)
        object.__setattr__(self, "homology_coeff_field", homology_coeff_field)
        object.__setattr__(self, "min_interval", min_interval)
        object.__setattr__(self, "normalization", normalization)
        object.__setattr__(self, "reference_window", reference_window)
        object.__setattr__(self, "score_scale", score_scale)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "algorithm_version", algorithm_version)
        self.__post_init__()

    def __post_init__(self) -> None:
        window_sessions = _require_int("window_sessions", self.window_sessions, 1)
        embedding_dimension = _require_int("embedding_dimension", self.embedding_dimension, 2)
        lag = _require_int("lag", self.lag, 1)
        _require_int("max_homology_dimension", self.max_homology_dimension, 1)
        homology_coeff_field = _require_int("homology_coeff_field", self.homology_coeff_field, 2)
        if not _is_prime(homology_coeff_field):
            raise TopologyConfigError(
                f"homology_coeff_field must be a prime number, got {homology_coeff_field!r}"
            )
        reference_window = _require_int("reference_window", self.reference_window, 1)
        min_interval = _require_finite_number("min_interval", self.min_interval, minimum=0.0)
        score_scale = _require_finite_number("score_scale", self.score_scale, minimum=0.0)
        if score_scale <= 0.0:
            raise TopologyConfigError("score_scale must be > 0")
        normalization = _require_text("normalization", self.normalization)
        metric = _require_text("metric", self.metric)
        algorithm_version = _require_text("algorithm_version", self.algorithm_version)

        if normalization not in NORMALIZATIONS:
            raise TopologyConfigError(
                f"normalization must be one of: {', '.join(NORMALIZATIONS)}; got {normalization!r}"
            )
        if metric not in METRICS:
            raise TopologyConfigError(
                f"metric must be one of: {', '.join(METRICS)}; got {metric!r}"
            )

        required_points = (embedding_dimension - 1) * lag
        if window_sessions <= required_points:
            raise TopologyConfigError(
                "window_sessions must be greater than "
                f"(embedding_dimension - 1) * lag = {required_points}; "
                f"got {window_sessions}"
            )

        # Normalise numeric field types so equal configurations always hash
        # equally (for example 0 and 0.0 for min_interval).
        object.__setattr__(self, "window_sessions", window_sessions)
        object.__setattr__(self, "embedding_dimension", embedding_dimension)
        object.__setattr__(self, "lag", lag)
        object.__setattr__(self, "reference_window", reference_window)
        object.__setattr__(self, "min_interval", min_interval)
        object.__setattr__(self, "score_scale", score_scale)
        object.__setattr__(self, "normalization", normalization)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "algorithm_version", algorithm_version)

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        """Return the canonical configuration field order."""

        return tuple(field.name for field in fields(cls))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping of every configuration field."""

        return {name: getattr(self, name) for name in self.field_names()}

    #: Alias used by a few callers in the wider code base.
    as_dict = to_dict

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TopologyConfig:
        """Build a configuration from a mapping, rejecting unknown fields.

        Missing fields keep their defaults.  A mapping may contain the
        configuration fields directly or put them under a single nested
        ``config`` object.  Registry metadata such as ``name``, ``hash`` or
        ``config_hash`` belongs to the registry loader and is rejected here.
        """

        if not isinstance(data, Mapping):
            raise TopologyConfigError(
                f"TopologyConfig.from_dict expects a mapping, got {type(data).__name__}"
            )

        known = set(cls.field_names())
        nested = data.get("config")
        unknown = sorted(str(key) for key in data if key not in known and key != "config")
        if unknown:
            raise UnknownFieldError(f"unknown field(s) for TopologyConfig: {', '.join(unknown)}")

        if "config" in data:
            if not isinstance(nested, Mapping):
                raise TopologyConfigError("TopologyConfig 'config' entry must be a mapping")
            nested_unknown = sorted(str(key) for key in nested if key not in known)
            if nested_unknown:
                raise UnknownFieldError(
                    f"unknown field(s) in TopologyConfig 'config': {', '.join(nested_unknown)}"
                )
            flat = {key: data[key] for key in known if key in data}
            nested_values = {key: nested[key] for key in known if key in nested}
            conflicts = sorted(
                key for key in flat.keys() & nested_values.keys() if flat[key] != nested_values[key]
            )
            if conflicts:
                raise TopologyConfigError(
                    "TopologyConfig registry entry has conflicting flat and nested fields: "
                    f"{', '.join(conflicts)}"
                )
            values = {**flat, **nested_values}
        else:
            values = {key: data[key] for key in known if key in data}

        return cls(**values)

    def hash_payload(self) -> dict[str, Any]:
        """Return the canonical payload that :meth:`config_hash` hashes."""

        return {"config": self.to_dict(), "version": _package_version()}

    def canonical_json(self) -> str:
        """Return the unambiguous canonical JSON encoding of this config."""

        return json.dumps(
            self.hash_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    def config_hash(self) -> str:
        """Return the SHA-256 identity of this configuration and package version."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    # Common aliases for the canonical hash method.
    canonical_hash = config_hash
    compute_hash = config_hash
    sha256 = config_hash
    hash = config_hash

    def registry_entry(self, *, name: str = DEFAULT_NAME) -> dict[str, Any]:
        """Return a verifiable registry entry for this configuration."""

        return {
            "name": name,
            "config": self.to_dict(),
            "config_hash": self.config_hash(),
        }


DEFAULT_CONFIG = TopologyConfig()
DEFAULT_TOPOLOGY_CONFIG = DEFAULT_CONFIG
DEFAULT_TOPOLOGY_CONFIGURATION = DEFAULT_CONFIG

DEFAULT_CONFIG_HASH = DEFAULT_CONFIG.config_hash()
DEFAULT_HASH = DEFAULT_CONFIG_HASH

#: Immutable in-process view of the frozen registry.
FROZEN_CONFIG_REGISTRY = MappingProxyType({DEFAULT_NAME: DEFAULT_CONFIG})
FROZEN_TOPOLOGY_CONFIGS = FROZEN_CONFIG_REGISTRY
FROZEN_CONFIGS = MappingProxyType({DEFAULT_CONFIG_HASH: DEFAULT_CONFIG})
FROZEN_CONFIG_HASHES = MappingProxyType({DEFAULT_NAME: DEFAULT_CONFIG_HASH})
FROZEN_REGISTRY_BY_HASH = FROZEN_CONFIGS

SOURCE_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "config" / "topology.json"
SOURCE_CONFIG_PATH = SOURCE_REGISTRY_PATH
REPOSITORY_CONFIG_PATH = SOURCE_REGISTRY_PATH
PACKAGED_REGISTRY_PATH = Path(__file__).resolve().with_name("topology.json")
PACKAGED_CONFIG_PATH = PACKAGED_REGISTRY_PATH
PACKAGE_CONFIG_PATH = PACKAGED_REGISTRY_PATH

#: Default lookup path: source checkout first, packaged resource afterwards.
DEFAULT_CONFIG_PATH = (
    SOURCE_REGISTRY_PATH if SOURCE_REGISTRY_PATH.is_file() else PACKAGED_REGISTRY_PATH
)
DEFAULT_REGISTRY_PATH = DEFAULT_CONFIG_PATH


def _resolve_config_path(path: Path | str | None = None) -> Path:
    """Resolve a registry path without depending on the current directory."""

    if path is None:
        environment = os.environ.get(CONFIG_ENV_VAR)
        if environment:
            path = environment
        else:
            return DEFAULT_CONFIG_PATH
    candidate = Path(path).expanduser()
    if candidate.is_dir():
        candidate = candidate / "topology.json"
    return candidate


#: Public helper kept for callers that want the resolved registry path.
config_path = _resolve_config_path


def _select_entry(payload: Any, name: str) -> tuple[str, Mapping[str, Any]]:
    """Extract the selected registry entry and its name."""

    if isinstance(payload, list):
        for candidate in payload:
            if isinstance(candidate, Mapping) and str(candidate.get("name") or "") == name:
                return str(candidate.get("name") or name), candidate
        available = [str(item.get("name")) for item in payload if isinstance(item, Mapping)]
        raise FrozenConfigurationError(
            f"Registry has no {name!r} entry; available entries: {', '.join(available) or '(none)'}"
        )
    if not isinstance(payload, Mapping):
        raise FrozenConfigurationError("Topology configuration registry must contain a JSON object")

    default = payload.get("default")
    if name == DEFAULT_NAME and isinstance(default, Mapping):
        return str(default.get("name") or DEFAULT_NAME), default

    containers = [
        payload[container_name]
        for container_name in ("entries", "configs", "registry")
        if isinstance(payload.get(container_name), Mapping)
    ]
    for container in containers:
        selected = container.get(name)
        if isinstance(selected, Mapping):
            return str(selected.get("name") or name), selected
    if containers:
        available = sorted({str(key) for container in containers for key in container})
        raise FrozenConfigurationError(
            f"Registry has no {name!r} entry; available entries: {', '.join(available) or '(none)'}"
        )

    if isinstance(default, Mapping):
        entry_name = str(default.get("name") or DEFAULT_NAME)
        if entry_name == name:
            return entry_name, default
        raise FrozenConfigurationError(
            f"Registry has no {name!r} entry; available entries: {entry_name}"
        )

    entry_name = str(payload.get("name") or DEFAULT_NAME)
    if entry_name != name:
        raise FrozenConfigurationError(
            f"Registry has no {name!r} entry; available entries: {entry_name}"
        )
    return entry_name, payload


def _entry_config(entry: Mapping[str, Any], entry_name: str) -> TopologyConfig:
    """Validate a registry entry and return its configuration object."""

    known = set(TopologyConfig.field_names())
    outer_unknown = sorted(
        str(key) for key in entry if key not in known and key not in _REGISTRY_META_KEYS
    )
    if outer_unknown:
        raise UnknownFieldError(
            f"unknown field(s) in topology configuration entry {entry_name!r}: "
            f"{', '.join(outer_unknown)}"
        )

    nested = entry.get("config")
    if "config" in entry:
        if not isinstance(nested, Mapping):
            raise FrozenConfigurationError(
                f"Frozen configuration hash cannot be verified for {entry_name!r}: "
                "'config' must be a mapping"
            )
        nested_unknown = sorted(str(key) for key in nested if key not in known)
        if nested_unknown:
            raise UnknownFieldError(
                f"unknown field(s) in topology configuration entry {entry_name!r}: "
                f"{', '.join(nested_unknown)}"
            )
        flat = {key: entry[key] for key in known if key in entry}
        nested_values = {key: nested[key] for key in known if key in nested}
        conflicts = sorted(
            key for key in flat.keys() & nested_values.keys() if flat[key] != nested_values[key]
        )
        if conflicts:
            raise FrozenConfigurationError(
                f"Frozen configuration hash cannot be verified for {entry_name!r}: "
                "the entry was modified and its flat and nested fields disagree "
                f"({', '.join(conflicts)})"
            )
        values = {**flat, **nested_values}
    else:
        values = {key: entry[key] for key in known if key in entry}

    # ``from_dict`` performs the strict field/type validation.
    return TopologyConfig.from_dict(values)


def _declared_hash(entry: Mapping[str, Any], entry_name: str) -> str | None:
    """Return the single declared hash from a registry entry, if any."""

    declared: list[tuple[str, str]] = []
    for key in _HASH_KEYS:
        if key in entry and entry[key] is not None:
            value = entry[key]
            if not isinstance(value, str):
                raise FrozenConfigurationError(
                    f"Frozen configuration hash cannot be verified for {entry_name!r}: "
                    f"{key} must be a string"
                )
            declared.append((key, value))
    if not declared:
        return None
    values = {value for _, value in declared}
    if len(values) > 1:
        keys = ", ".join(key for key, _ in declared)
        raise FrozenConfigurationError(
            f"Frozen configuration hash cannot be verified for {entry_name!r}: "
            f"conflicting hashes in {keys}"
        )
    return declared[0][1]


def _read_registry(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise FrozenConfigurationError(
            f"Unable to read topology configuration registry {path}: {error}"
        ) from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise FrozenConfigurationError(
            f"Invalid JSON in topology configuration registry {path}: {error}"
        ) from error


def load_topology_config(
    path: Path | str | None = None,
    allow_custom: bool = False,
    *,
    name: str = DEFAULT_NAME,
    registry_path: Path | str | None = None,
    config_path: Path | str | None = None,
) -> LoadedTopologyConfig:
    """Load and verify a topology configuration registry entry.

    The frozen default is loaded from ``config/topology.json`` in a source
    checkout, or from the packaged copy when the project is installed.  A
    declared hash that does not match the loaded fields is always rejected;
    passing ``allow_custom=True`` never bypasses that check.  Entries without a
    verified frozen hash require ``allow_custom=True`` and are marked
    exploratory.
    """

    provided = [item for item in (path, registry_path, config_path) if item is not None]
    if len(provided) > 1:
        raise TypeError("pass at most one of path, registry_path and config_path")
    selected = provided[0] if provided else None

    if isinstance(selected, Mapping):
        payload = selected
        source_path = None
    else:
        resolved = _resolve_config_path(selected)
        payload = _read_registry(resolved)
        source_path = resolved

    entry_name, entry = _select_entry(payload, name)
    config = _entry_config(entry, entry_name)
    computed_hash = config.config_hash()
    declared_hash = _declared_hash(entry, entry_name)

    if declared_hash is not None and declared_hash != computed_hash:
        raise FrozenConfigurationError(
            f"Configuration hash mismatch for {entry_name!r}: declared "
            f"{declared_hash}, computed {computed_hash}. "
            "The frozen entry appears to have been modified."
        )

    if declared_hash is None:
        if not allow_custom:
            raise FrozenConfigurationError(
                f"Configuration {entry_name!r} has no verified config_hash; "
                "pass allow_custom=True to load it as exploratory"
            )
        exploratory = True
    elif entry_name == DEFAULT_NAME and computed_hash == DEFAULT_CONFIG_HASH:
        # The caller explicitly asked for exploratory loading; the fields still
        # match the frozen default, but the flag remains visible downstream.
        exploratory = bool(allow_custom)
    elif allow_custom:
        exploratory = True
    else:
        raise FrozenConfigurationError(
            f"Configuration {entry_name!r} is not the frozen default; "
            "pass allow_custom=True to load it as exploratory"
        )

    return LoadedTopologyConfig(
        config,
        exploratory=exploratory,
        source_path=source_path,
        entry_name=entry_name,
        declared_hash=declared_hash,
    )


class _HashValue(str):
    """A hash string that can also be called like ``config.config_hash()``."""

    def __call__(self) -> _HashValue:
        return self

    def hexdigest(self) -> str:
        return str(self)


class LoadedTopologyConfig(TopologyConfig):
    """A verified configuration plus its exploratory/frozen provenance.

    It behaves like a :class:`TopologyConfig` (so ``loaded.window_sessions``
    works) while also exposing ``loaded.config``, ``loaded.config_hash`` and
    ``loaded.exploratory`` for callers that prefer an explicit result object.
    """

    def __init__(
        self,
        config: TopologyConfig,
        *,
        exploratory: bool,
        source_path: Path | None = None,
        entry_name: str = DEFAULT_NAME,
        declared_hash: str | None = None,
    ) -> None:
        super().__init__(**config.to_dict())
        object.__setattr__(self, "_exploratory", bool(exploratory))
        object.__setattr__(self, "_source_path", source_path)
        object.__setattr__(self, "_entry_name", entry_name)
        object.__setattr__(self, "_declared_hash", declared_hash)

    @property
    def config(self) -> LoadedTopologyConfig:
        return self

    @property
    def config_hash(self) -> _HashValue:  # type: ignore[override]
        return _HashValue(TopologyConfig.config_hash(self))

    @property
    def hash(self) -> _HashValue:  # type: ignore[override]
        return self.config_hash

    @property
    def sha256(self) -> _HashValue:  # type: ignore[override]
        return self.config_hash

    def compute_hash(self) -> str:  # type: ignore[override]
        return TopologyConfig.config_hash(self)

    @property
    def exploratory(self) -> bool:
        return self._exploratory

    @property
    def is_exploratory(self) -> bool:
        return self._exploratory

    @property
    def frozen(self) -> bool:
        return not self._exploratory

    @property
    def is_frozen(self) -> bool:
        return not self._exploratory

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def path(self) -> Path | None:
        return self._source_path

    @property
    def entry_name(self) -> str:
        return self._entry_name

    @property
    def name(self) -> str:
        return self._entry_name

    @property
    def declared_hash(self) -> str | None:
        return self._declared_hash

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TopologyConfig:  # type: ignore[override]
        return TopologyConfig.from_dict(data)

    def __getitem__(self, key: str) -> Any:
        """Allow mapping-style access to the config and its provenance."""

        if key == "config":
            return self
        if key == "config_hash":
            return str(self.config_hash)
        if key == "exploratory":
            return self.exploratory
        fields = self.to_dict()
        if key in fields:
            return fields[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TopologyConfig):
            return self.to_dict() == other.to_dict()
        return NotImplemented

    __hash__ = TopologyConfig.__hash__


def config_hash(config: TopologyConfig | Mapping[str, Any] | None = None) -> str:
    """Return the canonical hash for a configuration (default when omitted)."""

    if config is None:
        return DEFAULT_CONFIG.config_hash()
    if isinstance(config, TopologyConfig):
        return config.config_hash()
    return TopologyConfig.from_dict(config).config_hash()


def compute_config_hash(config: TopologyConfig | Mapping[str, Any] | None = None) -> str:
    """Alias for :func:`config_hash`."""

    return config_hash(config)


canonical_config_hash = config_hash
topology_config_hash = config_hash
hash_config = config_hash

load_config = load_topology_config
load_default_config = load_topology_config
load_frozen_config = load_topology_config
load_frozen_topology_config = load_topology_config
load_topology_configuration = load_topology_config
load_registry = load_topology_config
load_topology_registry = load_topology_config
read_config = load_topology_config
read_topology_config = load_topology_config
resolve_topology_config = load_topology_config

configuration_hash = config_hash
config_sha256 = config_hash
hash_topology_config = config_hash

FROZEN_REGISTRY = FROZEN_CONFIG_REGISTRY
DEFAULT_REGISTRY = FROZEN_CONFIG_REGISTRY
DEFAULT_TOPOLOGY_CONFIG_PATH = DEFAULT_CONFIG_PATH
TOPOLOGY_CONFIG_PATH = DEFAULT_CONFIG_PATH
REGISTRY_PATH = SOURCE_REGISTRY_PATH
PACKAGE_REGISTRY_PATH = PACKAGED_REGISTRY_PATH
ConfigError = TopologyConfigError
FrozenError = FrozenConfigurationError

__all__ = [
    "CONFIG_ENV_VAR",
    "CONFIG_PATH_ENV_VAR",
    "ConfigError",
    "ConfigHashError",
    "ConfigurationError",
    "DEFAULT_CONFIG",
    "DEFAULT_CONFIG_HASH",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_ENTRY_NAME",
    "DEFAULT_HASH",
    "DEFAULT_NAME",
    "DEFAULT_REGISTRY",
    "DEFAULT_REGISTRY_PATH",
    "DEFAULT_TOPOLOGY_CONFIG",
    "DEFAULT_TOPOLOGY_CONFIG_PATH",
    "DEFAULT_TOPOLOGY_CONFIGURATION",
    "FROZEN_CONFIGS",
    "FROZEN_CONFIG_HASHES",
    "FROZEN_CONFIG_REGISTRY",
    "FROZEN_REGISTRY",
    "FROZEN_REGISTRY_BY_HASH",
    "FROZEN_TOPOLOGY_CONFIGS",
    "FrozenConfigError",
    "FrozenConfigurationError",
    "FrozenError",
    "LoadedTopologyConfig",
    "METRICS",
    "NORMALIZATIONS",
    "PACKAGED_CONFIG_PATH",
    "PACKAGED_REGISTRY_PATH",
    "PACKAGE_CONFIG_PATH",
    "PACKAGE_REGISTRY_PATH",
    "REGISTRY_PATH",
    "REPOSITORY_CONFIG_PATH",
    "SOURCE_CONFIG_PATH",
    "SOURCE_REGISTRY_PATH",
    "TOPOLOGY_CONFIG_PATH",
    "TopologyConfig",
    "TopologyConfigError",
    "UnknownField",
    "UnknownFieldError",
    "canonical_config_hash",
    "compute_config_hash",
    "config_hash",
    "config_path",
    "config_sha256",
    "configuration_hash",
    "hash_config",
    "hash_topology_config",
    "load_config",
    "load_default_config",
    "load_frozen_config",
    "load_frozen_topology_config",
    "load_registry",
    "load_topology_config",
    "load_topology_configuration",
    "load_topology_registry",
    "read_config",
    "read_topology_config",
    "resolve_topology_config",
    "topology_config_hash",
]
