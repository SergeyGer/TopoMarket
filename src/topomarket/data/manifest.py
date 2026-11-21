"""Manifest handling for local TopoMarket data directories.

A data directory is a plain directory on disk that contains a ``manifest.json``
file describing where its contents came from (provenance) and one optional
``snapshots/`` directory holding immutable, content-addressed snapshots.

The helpers in this module deliberately avoid touching the network and never
follow a relative path that escapes the data directory it belongs to. Writes
are atomic: payloads are serialised into a temporary file in the destination
directory and then moved into place with :func:`os.replace`, so a crashed
write can never leave a truncated ``manifest.json`` behind.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

MANIFEST_FILENAME = "manifest.json"
SNAPSHOTS_DIRNAME = "snapshots"
SNAPSHOTS_DIR = SNAPSHOTS_DIRNAME

# Common alternative names used by callers.
MANIFEST_NAME = MANIFEST_FILENAME
MANIFEST_FILE = MANIFEST_FILENAME
SNAPSHOT_DIR = SNAPSHOTS_DIRNAME
SNAPSHOT_DIRNAME = SNAPSHOTS_DIRNAME

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_GENERATOR = "topomarket"

#: Fields every manifest written by this package carries. They capture enough
#: provenance to reproduce and audit a local data snapshot.
REQUIRED_MANIFEST_FIELDS: tuple[str, ...] = (
    "schema_version",
    "snapshot_id",
    "created_at",
    "profile",
    "data_source",
    "source",
    "generator",
    "generator_version",
    "files",
)
PROVENANCE_FIELDS = REQUIRED_MANIFEST_FIELDS
REQUIRED_PROVENANCE_FIELDS = REQUIRED_MANIFEST_FIELDS

# ``created_at`` is metadata rather than content, so it must not affect a
# snapshot's identity. ``snapshot_id`` is excluded as well because it is the
# value being derived from the remaining content.
SNAPSHOT_ID_EXCLUDED_FIELDS: tuple[str, ...] = ("created_at", "snapshot_id")


class ManifestError(ValueError):
    """Base class for invalid or unreadable manifests."""


class ManifestNotFoundError(ManifestError, FileNotFoundError):
    """Raised when a manifest file does not exist."""


class ManifestIntegrityError(ManifestError):
    """Raised when a manifest is malformed or its snapshot id does not match."""


class PathTraversalError(ManifestError):
    """Raised when a relative path would escape its base directory."""


def _package_version() -> str:
    """Return the installed TopoMarket version without importing the package."""

    try:  # pragma: no cover - the package is normally importable
        from topomarket import __version__

        return str(__version__)
    except Exception:  # pragma: no cover - defensive only
        return "0.0.0"


def _json_default(value: Any) -> Any:
    """Convert common non-JSON values into deterministic JSON values."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serialisable")


def canonical_json(payload: Any) -> str:
    """Return a stable JSON encoding used for hashing and tests."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def compute_snapshot_id(manifest: Mapping[str, Any] | Any) -> str:
    """Return a deterministic SHA-256 identifier for ``manifest`` content.

    ``created_at`` is excluded so two identical snapshots created at different
    times share an id. ``snapshot_id`` itself is excluded to avoid a circular
    dependency. All other content, including nested metadata, contributes to
    the hash.
    """

    if not isinstance(manifest, Mapping):
        raise TypeError("snapshot_id() expects a manifest mapping")

    content = {
        key: value for key, value in manifest.items() if key not in SNAPSHOT_ID_EXCLUDED_FIELDS
    }
    digest = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
    return digest


def snapshot_id(manifest: Mapping[str, Any] | Any) -> str:
    """Public alias for :func:`compute_snapshot_id`."""

    return compute_snapshot_id(manifest)


def _utc_now() -> str:
    """Return the current time as an ISO-8601 UTC string."""

    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _coerce_timestamp(value: Any) -> str:
    """Return ``value`` as an ISO-8601 timestamp string."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return _utc_now()
    return str(value)


def _normalise_files(value: Any) -> list[Any]:
    """Validate and copy the optional ``files`` provenance list."""

    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ManifestError("'files' must be a list of file entries")
    files = list(value)
    for entry in files:
        if not isinstance(entry, (Mapping, str, Path)):
            raise ManifestError("'files' entries must be mappings or paths")
    return files


def _normalise_metadata(value: Any) -> dict[str, Any]:
    """Validate and copy the optional ``metadata`` mapping."""

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ManifestError("'metadata' must be a JSON object")
    return dict(value)


def normalise_manifest(
    manifest: Mapping[str, Any] | None = None,
    *,
    profile: str | None = None,
    data_source: str | None = None,
    source: str | Path | None = None,
    data_dir: str | Path | None = None,
    created_at: str | datetime | None = None,
    files: Sequence[Any] | Iterable[Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    schema_version: int | None = None,
    generator: str | None = None,
    generator_version: str | None = None,
) -> dict[str, Any]:
    """Return a complete manifest with a freshly computed ``snapshot_id``.

    Existing provenance fields are preserved. Missing fields are filled with
    sensible defaults so callers can write a small description and let the
    helper take care of the bookkeeping. ``created_at`` is only defaulted when
    it is absent, which lets callers (and tests) pin a timestamp.
    """

    if manifest is None:
        result: dict[str, Any] = {}
    elif isinstance(manifest, Mapping):
        result = dict(manifest)
    else:
        raise ManifestError("manifest must be a mapping")

    if profile is not None:
        result["profile"] = str(profile)
    result.setdefault("profile", "unknown")

    if data_source is not None:
        result["data_source"] = str(data_source)
    result.setdefault("data_source", "local")

    if source is not None:
        result["source"] = str(source)
    elif "source" not in result:
        result["source"] = str(data_dir) if data_dir is not None else "local"

    if data_dir is not None:
        result.setdefault("data_dir", str(data_dir))

    if schema_version is not None:
        result["schema_version"] = schema_version
    result.setdefault("schema_version", MANIFEST_SCHEMA_VERSION)

    if generator is not None:
        result["generator"] = generator
    result.setdefault("generator", MANIFEST_GENERATOR)

    if generator_version is not None:
        result["generator_version"] = generator_version
    result.setdefault("generator_version", _package_version())

    if files is not None:
        result["files"] = _normalise_files(files)
    else:
        result["files"] = _normalise_files(result.get("files"))

    if metadata is not None:
        result["metadata"] = _normalise_metadata(metadata)
    elif "metadata" in result:
        result["metadata"] = _normalise_metadata(result.get("metadata"))
    else:
        result.setdefault("metadata", {})

    if created_at is not None:
        result["created_at"] = _coerce_timestamp(created_at)
    elif result.get("created_at") is None:
        result["created_at"] = _utc_now()
    else:
        result["created_at"] = _coerce_timestamp(result["created_at"])

    result["snapshot_id"] = compute_snapshot_id(result)
    return result


# A spelling that some callers prefer.
normalize_manifest = normalise_manifest


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    require_provenance: bool = True,
    verify_snapshot_id: bool = True,
) -> dict[str, Any]:
    """Validate a manifest and return a plain ``dict`` copy.

    Raises :class:`ManifestIntegrityError` when required provenance fields are
    missing, field types are wrong, or the recorded ``snapshot_id`` no longer
    matches the manifest content.
    """

    if not isinstance(manifest, Mapping):
        raise ManifestIntegrityError("manifest must be a JSON object")

    data = dict(manifest)

    if require_provenance:
        missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in data]
        if missing:
            raise ManifestIntegrityError(
                "manifest is missing required provenance fields: " + ", ".join(missing)
            )

    if "schema_version" in data and data["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ManifestIntegrityError(
            f"unsupported manifest schema_version: {data['schema_version']!r}"
        )

    if "files" in data and not isinstance(data["files"], list):
        raise ManifestIntegrityError("'files' must be a list")

    if "metadata" in data and not isinstance(data["metadata"], Mapping):
        raise ManifestIntegrityError("'metadata' must be a JSON object")

    if verify_snapshot_id and "snapshot_id" in data:
        expected = compute_snapshot_id(data)
        if data["snapshot_id"] != expected:
            raise ManifestIntegrityError(
                "manifest snapshot_id does not match its content "
                f"(expected {expected}, found {data['snapshot_id']})"
            )

    return data


class Manifest(dict):
    """A manifest mapping that remembers the file it was read from or written to.

    Subclassing :class:`dict` keeps manifests JSON-serialisable and lets callers
    use either ``manifest["snapshot_id"]`` or ``manifest.snapshot_id``. The
    location-related attributes (``path``, ``exists()``, ...) are conveniences
    for callers that expect a writer to return the path it wrote.
    """

    def __init__(self, manifest: Mapping[str, Any], path: Path | str | None = None):
        super().__init__(manifest)
        self._path = Path(path) if path is not None else None

    @property
    def path(self) -> Path | None:
        """The manifest file location, when known."""

        return self._path

    @property
    def location(self) -> Path | None:
        """Alias for :attr:`path`."""

        return self._path

    @property
    def snapshot_id(self) -> str:
        """The content-addressed identifier recorded in this manifest."""

        return str(self["snapshot_id"])

    def as_dict(self) -> dict[str, Any]:
        """Return a plain ``dict`` copy of the manifest."""

        return dict(self)

    def __fspath__(self) -> str:
        if self._path is None:
            raise TypeError("this manifest is not associated with a filesystem path")
        return str(self._path)

    def __getattr__(self, name: str) -> Any:
        path = self.__dict__.get("_path")
        if path is not None and hasattr(path, name):
            return getattr(path, name)
        raise AttributeError(name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Manifest):
            return dict.__eq__(self, other) and self._path == other._path
        if isinstance(other, Mapping):
            return dict.__eq__(self, other)
        if isinstance(other, (str, os.PathLike)):
            text = os.fspath(other)
            if self._path is not None and Path(text) == self._path:
                return True
            return text == self.get("snapshot_id")
        return NotImplemented

    def __hash__(self) -> int:  # pragma: no cover - manifests are mutable mappings
        return hash(self.get("snapshot_id"))

    def __repr__(self) -> str:
        location = f", path={str(self._path)!r}" if self._path is not None else ""
        return f"Manifest(keys={sorted(self)!r}{location})"


def manifest_path(target: Path | str, *, filename: str = MANIFEST_FILENAME) -> Path:
    """Return the manifest path for a data-directory or manifest path.

    ``target`` may point at a directory (``<target>/manifest.json``), at a
    manifest file directly, or at any ``*.json`` path.
    """

    path = Path(target)
    if path.name == filename or path.suffix == ".json":
        return path
    return path / filename


def _resolve_target(
    data_dir: Path | str | None,
    *,
    target: Path | str | None = None,
    path: Path | str | None = None,
    directory: Path | str | None = None,
) -> Path:
    """Pick the destination from the supported keyword spellings."""

    for candidate in (target, path, directory, data_dir):
        if candidate is not None:
            return candidate  # type: ignore[return-value]
    raise TypeError("a data directory or manifest path is required")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically via a sibling temporary file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        # Best effort durability of the directory entry. Some platforms do not
        # allow opening directories, so failures are intentionally ignored.
        try:
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
        except OSError:  # pragma: no cover - platform dependent
            directory_fd = None
        if directory_fd is not None:  # pragma: no branch - platform dependent
            try:
                os.fsync(directory_fd)
            except OSError:  # pragma: no cover - platform dependent
                pass
            finally:
                os.close(directory_fd)
    except BaseException:
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(
    path: Path | str,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
) -> Path:
    """Serialise ``payload`` to ``path`` atomically and return the path."""

    destination = Path(path)
    text = json.dumps(
        payload,
        indent=indent,
        sort_keys=sort_keys,
        ensure_ascii=False,
        default=_json_default,
    )
    _atomic_write_text(destination, text + "\n")
    return destination


# Common aliases for the atomic writer.
write_json_atomic = atomic_write_json
atomic_write_manifest = atomic_write_json
atomic_write = atomic_write_json


def write_manifest(
    data_dir: Path | str | None = None,
    manifest: Mapping[str, Any] | None = None,
    *,
    target: Path | str | None = None,
    path: Path | str | None = None,
    directory: Path | str | None = None,
    filename: str = MANIFEST_FILENAME,
    created_at: str | datetime | None = None,
    profile: str | None = None,
    data_source: str | None = None,
    source: str | Path | None = None,
    files: Sequence[Any] | Iterable[Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically write a complete ``manifest.json`` and return its content.

    The destination may be a data directory or an explicit manifest path. A
    temporary file is created next to the destination and moved into place with
    :func:`os.replace` only after it has been fully written and flushed.
    """

    destination = _resolve_target(data_dir, target=target, path=path, directory=directory)
    location = manifest_path(destination, filename=filename)
    root = location.parent

    complete = normalise_manifest(
        manifest,
        profile=profile,
        data_source=data_source,
        source=source,
        data_dir=root,
        created_at=created_at,
        files=files,
        metadata=metadata,
    )
    atomic_write_json(location, complete)
    return Manifest(complete, path=location)


def read_manifest(
    data_dir: Path | str | None = None,
    *,
    target: Path | str | None = None,
    path: Path | str | None = None,
    directory: Path | str | None = None,
    filename: str = MANIFEST_FILENAME,
    verify: bool = True,
    strict: bool = False,
) -> dict[str, Any]:
    """Read and optionally verify a ``manifest.json`` file.

    By default a missing ``snapshot_id`` is computed and added (useful for
    hand-authored manifests), while an existing id that does not match the
    content raises :class:`ManifestIntegrityError`. Pass ``strict=True`` to
    require every provenance field to be present.
    """

    source = _resolve_target(data_dir, target=target, path=path, directory=directory)
    location = manifest_path(source, filename=filename)
    try:
        text = location.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ManifestNotFoundError(f"manifest not found: {location}") from exc
    except OSError as exc:
        raise ManifestError(f"could not read manifest {location}: {exc}") from exc

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestIntegrityError(f"invalid JSON in manifest {location}: {exc}") from exc

    if not isinstance(payload, Mapping):
        raise ManifestIntegrityError(f"manifest {location} must contain a JSON object")

    data = dict(payload)

    if strict:
        validated = validate_manifest(data, require_provenance=True, verify_snapshot_id=verify)
        return Manifest(validated, path=location)

    if verify and "snapshot_id" in data:
        expected = compute_snapshot_id(data)
        if data["snapshot_id"] != expected:
            raise ManifestIntegrityError(
                "manifest snapshot_id does not match its content "
                f"(expected {expected}, found {data['snapshot_id']})"
            )
    elif "snapshot_id" not in data:
        data["snapshot_id"] = compute_snapshot_id(data)
    return Manifest(data, path=location)


def ensure_data_directory(
    path: Path | str,
    *,
    create: bool = True,
    parents: bool = True,
) -> Path:
    """Ensure ``path`` is a usable directory and return its absolute path."""

    directory = Path(path).expanduser()
    if directory.exists():
        if not directory.is_dir():
            raise NotADirectoryError(f"data path is not a directory: {directory}")
    elif create:
        directory.mkdir(parents=parents, exist_ok=True)
    else:
        raise FileNotFoundError(f"data directory does not exist: {directory}")
    return directory.resolve()


def ensure_data_dir(path: Path | str, **kwargs: Any) -> Path:
    """Alias for :func:`ensure_data_directory`."""

    return ensure_data_directory(path, **kwargs)


create_data_directory = ensure_data_directory
create_data_dir = ensure_data_directory
make_data_directory = ensure_data_directory
init_data_directory = ensure_data_directory
init_data_dir = ensure_data_directory


def validate_relative_path(relative: str | Path) -> Path:
    """Validate a relative path that must stay below its base directory.

    Absolute paths, drive/UNC paths, empty paths, NUL bytes and any ``..``
    component are rejected. Backslashes are rejected as well so a path that is
    safe on POSIX cannot become a traversal on Windows.
    """

    if isinstance(relative, Path):
        text = str(relative)
    elif isinstance(relative, str):
        text = relative
    else:
        raise TypeError("relative path must be a string or pathlib.Path")

    if not text:
        raise PathTraversalError("relative path must not be empty")
    if "\x00" in text:
        raise PathTraversalError("relative path must not contain NUL bytes")
    if "\\" in text:
        raise PathTraversalError(f"relative path must not contain backslashes: {text!r}")

    windows = PureWindowsPath(text)
    if windows.is_absolute() or windows.drive or windows.root:
        raise PathTraversalError(f"absolute paths are not allowed: {text!r}")

    posix = PurePosixPath(text)
    if posix.is_absolute():
        raise PathTraversalError(f"absolute paths are not allowed: {text!r}")

    parts: list[str] = []
    for part in posix.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise PathTraversalError(f"path traversal is not allowed: {text!r}")
        if part == "~" or part.startswith("~"):
            raise PathTraversalError(f"home-relative paths are not allowed: {text!r}")
        parts.append(part)

    if not parts:
        raise PathTraversalError(f"relative path must name a file or directory: {text!r}")
    return Path(*parts)


def resolve_relative_path(
    base: Path | str,
    relative: str | Path,
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve ``relative`` below ``base``, rejecting traversal and escapes.

    The lexical check catches ``..`` components before touching the filesystem.
    A second check resolves symlinks and confirms the final path is still inside
    the base directory, which also rejects symlink-based escapes.
    """

    base_path = Path(base).expanduser().resolve()
    safe_relative = validate_relative_path(relative)
    candidate = base_path / safe_relative

    resolved = candidate.resolve(strict=False)
    if resolved != base_path and not resolved.is_relative_to(base_path):
        raise PathTraversalError(f"path escapes the data directory: {relative!r} -> {resolved}")

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"path does not exist: {resolved}")
    return resolved


def safe_join(base: Path | str, *parts: str | Path) -> Path:
    """Join one or more relative parts below ``base`` safely."""

    if not parts:
        raise TypeError("at least one relative path part is required")
    combined = Path(parts[0])
    for part in parts[1:]:
        combined = combined / part
    return resolve_relative_path(base, combined)


# Common aliases for the path helpers.
safe_path = resolve_relative_path
resolve_path = resolve_relative_path
resolve_relative = resolve_relative_path
join_relative = resolve_relative_path
validate_relative = validate_relative_path
ensure_within = resolve_relative_path
safe_relative_path = resolve_relative_path


class Snapshot(dict):
    """A manifest-backed snapshot that also behaves like its manifest mapping.

    ``Snapshot`` subclasses :class:`dict` so ``snapshot["snapshot_id"]`` and
    ``dict(snapshot)`` work exactly as expected, while ``snapshot.path`` and
    ``snapshot.snapshot_id`` provide convenient attribute access.
    """

    def __init__(self, manifest: Mapping[str, Any], path: Path | str | None = None):
        data = dict(manifest)
        if "snapshot_id" not in data:
            data["snapshot_id"] = compute_snapshot_id(data)
        super().__init__(data)
        self._path = Path(path) if path is not None else None

    @property
    def path(self) -> Path | None:
        """The snapshot directory, when the snapshot came from disk."""

        return self._path

    @property
    def directory(self) -> Path | None:
        """Alias for :attr:`path`."""

        return self._path

    @property
    def manifest_path(self) -> Path | None:
        """The ``manifest.json`` inside the snapshot directory."""

        if self._path is None:
            return None
        if self._path.name == MANIFEST_FILENAME:
            return self._path
        return self._path / MANIFEST_FILENAME

    @property
    def manifest(self) -> Snapshot:
        """Return this snapshot as its manifest mapping."""

        return self

    @property
    def id(self) -> str:
        """Alias for :attr:`snapshot_id`."""

        return str(self["snapshot_id"])

    @property
    def snapshot_id(self) -> str:
        """The content-addressed identifier of this snapshot."""

        return str(self["snapshot_id"])

    @property
    def created_at(self) -> Any:
        """The manifest's ``created_at`` value, if present."""

        return self.get("created_at")

    @property
    def name(self) -> str | None:
        """The snapshot directory's name, when backed by a path."""

        return self._path.name if self._path is not None else None

    @property
    def parent(self) -> Path | None:
        """The snapshot's parent directory, when backed by a path."""

        return self._path.parent if self._path is not None else None

    def as_dict(self) -> dict[str, Any]:
        """Return a plain ``dict`` copy of the manifest."""

        return dict(self)

    def __fspath__(self) -> str:
        if self._path is None:
            raise TypeError("this snapshot is not associated with a filesystem path")
        return str(self._path)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Snapshot):
            return dict.__eq__(self, other) and self._path == other._path
        if isinstance(other, Mapping):
            return dict.__eq__(self, other)
        if isinstance(other, (str, os.PathLike)):
            text = os.fspath(other)
            if self._path is not None and Path(text) == self._path:
                return True
            return text == self.snapshot_id
        return NotImplemented

    def __hash__(self) -> int:  # pragma: no cover - snapshots are mutable mappings
        return hash(self.snapshot_id)

    def __repr__(self) -> str:
        location = f", path={str(self._path)!r}" if self._path is not None else ""
        return f"Snapshot(snapshot_id={self.snapshot_id!r}{location})"


def _as_path(value: Any) -> Path | None:
    """Return ``value`` as a path when it looks like one."""

    if isinstance(value, (str, Path, os.PathLike)):
        return Path(value)
    return None


def _parse_created_at(value: Any) -> datetime:
    """Parse a manifest timestamp for ordering, falling back to the epoch."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _snapshot_sort_key(snapshot: Snapshot) -> tuple[datetime, str]:
    """Return the ordering key used by snapshot listings."""

    created = snapshot.created_at
    if created is None and snapshot.path is not None:
        try:
            modified = snapshot.path.stat().st_mtime
        except OSError:
            modified = 0.0
        created = datetime.fromtimestamp(modified, tz=timezone.utc)
    return (_parse_created_at(created), snapshot.snapshot_id)


def _snapshot_from_manifest(location: Path, manifest: Mapping[str, Any]) -> Snapshot:
    """Build a :class:`Snapshot` from a manifest file location."""

    snapshot_directory = location.parent
    data = dict(manifest)
    if "snapshot_id" not in data:
        data["snapshot_id"] = compute_snapshot_id(data)
    return Snapshot(data, path=snapshot_directory)


def _iter_snapshot_manifests(root: Path) -> list[Path]:
    """Return candidate manifest files for snapshots below ``root``."""

    candidates: list[Path] = []
    snapshots_directory = root / SNAPSHOTS_DIRNAME
    if snapshots_directory.is_dir():
        for child in sorted(snapshots_directory.iterdir()):
            if child.is_dir() and (child / MANIFEST_FILENAME).is_file():
                candidates.append(child / MANIFEST_FILENAME)
            elif child.is_file() and child.suffix == ".json":
                candidates.append(child)

    # Some callers keep each snapshot directly under the data root; accept
    # that layout when there is no conventional ``snapshots/`` content. The
    # data directory's own manifest is not a snapshot and is deliberately
    # excluded here.
    if not candidates and root.is_dir():
        for child in sorted(root.iterdir()):
            if child.name == SNAPSHOTS_DIRNAME:
                continue
            if child.is_dir() and (child / MANIFEST_FILENAME).is_file():
                candidates.append(child / MANIFEST_FILENAME)

    return candidates


def list_snapshots(data_dir: Any = None, *, path: Path | str | None = None) -> list[Snapshot]:
    """Return known snapshots ordered from oldest to newest.

    ``data_dir`` may be a directory, a :class:`~topomarket.data.directory.DataDirectory`
    instance, a single manifest mapping, or an iterable of manifests/snapshots.
    The newest snapshot is the one with the greatest ``created_at`` value;
    ``snapshot_id`` breaks ties. Missing snapshot directories simply yield an
    empty list.
    """

    if path is not None:
        data_dir = path

    if data_dir is None:
        raise TypeError("a data directory is required")

    # A single manifest mapping is not a directory; treat it as one snapshot.
    if isinstance(data_dir, Mapping):
        return [data_dir if isinstance(data_dir, Snapshot) else Snapshot(data_dir)]

    if not isinstance(data_dir, (str, Path, os.PathLike)):
        if hasattr(data_dir, "root") and hasattr(data_dir, "write_manifest"):
            data_dir = data_dir.root
        else:
            try:
                items = list(data_dir)
            except TypeError:
                items = None
            if items is not None:
                snapshots = [
                    item if isinstance(item, Snapshot) else Snapshot(item) for item in items
                ]
                return sorted(snapshots, key=_snapshot_sort_key)

    root = Path(data_dir)
    snapshots: list[Snapshot] = []
    for location in _iter_snapshot_manifests(root):
        try:
            manifest = read_manifest(location)
        except ManifestError:
            continue
        snapshots.append(_snapshot_from_manifest(location, manifest))

    snapshots.sort(key=_snapshot_sort_key)
    return snapshots


def list_snapshot_ids(data_dir: Any = None, *, path: Path | str | None = None) -> list[str]:
    """Return snapshot ids ordered from oldest to newest."""

    return [snapshot.snapshot_id for snapshot in list_snapshots(data_dir, path=path)]


snapshot_ids = list_snapshot_ids


def latest_snapshot(
    data_dir: Any = None,
    *,
    path: Path | str | None = None,
) -> Snapshot | None:
    """Return the newest snapshot below ``data_dir`` or ``None`` when empty."""

    snapshots = list_snapshots(data_dir, path=path)
    return snapshots[-1] if snapshots else None


def write_snapshot(
    data_dir: Path | str,
    manifest: Mapping[str, Any] | None = None,
    *,
    directory: Path | str | None = None,
    **manifest_fields: Any,
) -> Snapshot:
    """Write a content-addressed snapshot below ``data_dir`` and return it."""

    if directory is not None:
        data_dir = directory
    root = Path(data_dir)
    complete = normalise_manifest(manifest, data_dir=root, **manifest_fields)
    identifier = str(complete["snapshot_id"])
    snapshot_directory = root / SNAPSHOTS_DIRNAME / identifier
    written = write_manifest(snapshot_directory, complete)
    return Snapshot(written, path=snapshot_directory)


create_snapshot = write_snapshot
save_snapshot = write_snapshot


__all__ = [
    "MANIFEST_FILENAME",
    "MANIFEST_FILE",
    "MANIFEST_GENERATOR",
    "MANIFEST_NAME",
    "MANIFEST_SCHEMA_VERSION",
    "PROVENANCE_FIELDS",
    "REQUIRED_MANIFEST_FIELDS",
    "REQUIRED_PROVENANCE_FIELDS",
    "SNAPSHOTS_DIR",
    "SNAPSHOTS_DIRNAME",
    "SNAPSHOT_DIR",
    "SNAPSHOT_DIRNAME",
    "SNAPSHOT_ID_EXCLUDED_FIELDS",
    "Manifest",
    "ManifestError",
    "ManifestIntegrityError",
    "ManifestNotFoundError",
    "PathTraversalError",
    "Snapshot",
    "atomic_write",
    "atomic_write_json",
    "atomic_write_manifest",
    "canonical_json",
    "compute_snapshot_id",
    "create_data_dir",
    "create_data_directory",
    "create_snapshot",
    "ensure_data_dir",
    "ensure_data_directory",
    "ensure_within",
    "init_data_dir",
    "init_data_directory",
    "join_relative",
    "latest_snapshot",
    "list_snapshot_ids",
    "list_snapshots",
    "make_data_directory",
    "manifest_path",
    "normalise_manifest",
    "normalize_manifest",
    "read_manifest",
    "resolve_path",
    "resolve_relative",
    "resolve_relative_path",
    "safe_join",
    "safe_path",
    "safe_relative_path",
    "save_snapshot",
    "snapshot_id",
    "snapshot_ids",
    "validate_manifest",
    "validate_relative",
    "validate_relative_path",
    "write_json_atomic",
    "write_manifest",
    "write_snapshot",
]
