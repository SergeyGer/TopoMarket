"""Local data-directory management for TopoMarket.

The :class:`DataDirectory` wrapper groups the filesystem layout (a root
directory, its ``manifest.json`` and optional ``snapshots/`` children) with the
atomic helpers from :mod:`topomarket.data.manifest`. Module-level functions are
also available for callers that prefer a functional style.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .manifest import (
    MANIFEST_FILENAME,
    SNAPSHOTS_DIRNAME,
    Snapshot,
    ensure_data_directory,
    latest_snapshot,
    list_snapshots,
    normalise_manifest,
    read_manifest,
    resolve_relative_path,
    validate_relative_path,
    write_manifest,
    write_snapshot,
)
from .manifest import (
    snapshot_id as compute_snapshot_id,
)


class DataDirectory:
    """A local directory holding a manifest and optional snapshots.

    The directory does not need to exist when the object is constructed. Call
    :meth:`ensure` (or one of the classmethod constructors) before writing.
    Passing a ``manifest.json`` path to the constructor also works; the parent
    directory becomes the data directory.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        create: bool = False,
        snapshots_dirname: str = SNAPSHOTS_DIRNAME,
    ) -> None:
        path = Path(root).expanduser()
        if path.name == MANIFEST_FILENAME:
            path = path.parent
        self.root = path
        self.snapshots_dirname = snapshots_dirname
        if create:
            self.ensure()

    @classmethod
    def create(cls, root: Path | str, **kwargs: Any) -> DataDirectory:
        """Create the directory if needed and return a wrapper for it."""

        kwargs["create"] = True
        return cls(root, **kwargs)

    @classmethod
    def open(cls, root: Path | str, **kwargs: Any) -> DataDirectory:
        """Alias for :meth:`create` that keeps existing data intact."""

        return cls.create(root, **kwargs)

    @property
    def path(self) -> Path:
        """The data-directory root."""

        return self.root

    @property
    def manifest_path(self) -> Path:
        """Path to the directory's ``manifest.json``."""

        return self.root / MANIFEST_FILENAME

    @property
    def snapshots_dir(self) -> Path:
        """Path to the directory's ``snapshots/`` child."""

        return self.root / self.snapshots_dirname

    @property
    def snapshot_directory(self) -> Path:
        """Alias for :attr:`snapshots_dir`."""

        return self.snapshots_dir

    def exists(self) -> bool:
        """Whether the data directory currently exists."""

        return self.root.is_dir()

    def ensure(self, *, create: bool = True) -> Path:
        """Create the data directory if needed and return its resolved path."""

        self.root = ensure_data_directory(self.root, create=create)
        return self.root

    def mkdir(self, *, parents: bool = True, exist_ok: bool = True) -> Path:
        """Create the data-directory root and return it."""

        self.root.mkdir(parents=parents, exist_ok=exist_ok)
        return self.root

    def write_manifest(
        self,
        manifest: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Atomically write this directory's manifest."""

        self.ensure()
        return write_manifest(self.root, manifest, **fields)

    def read_manifest(
        self,
        *,
        verify: bool = True,
        strict: bool = False,
    ) -> dict[str, Any]:
        """Read this directory's manifest."""

        return read_manifest(self.root, verify=verify, strict=strict)

    def manifest(self, **fields: Any) -> dict[str, Any]:
        """Build a complete manifest for this directory without writing it."""

        return normalise_manifest(None, data_dir=self.root, **fields)

    def write_snapshot(
        self,
        manifest: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> Snapshot:
        """Atomically write a content-addressed snapshot below this directory."""

        self.ensure()
        return write_snapshot(self.root, manifest, **fields)

    # ``create_snapshot`` reads naturally at call sites as well.
    create_snapshot = write_snapshot
    save_snapshot = write_snapshot

    def list_snapshots(self) -> list[Snapshot]:
        """Return snapshots ordered from oldest to newest."""

        return list_snapshots(self.root)

    def latest_snapshot(self) -> Snapshot | None:
        """Return the newest snapshot, or ``None`` when there are none."""

        return latest_snapshot(self.root)

    def snapshot_id(self, manifest: Mapping[str, Any] | None = None) -> str:
        """Return the id for ``manifest`` or for the current manifest file."""

        if manifest is None:
            manifest = self.read_manifest()
        return compute_snapshot_id(manifest)

    def resolve(self, *parts: str | Path) -> Path:
        """Resolve one or more relative parts safely below the data directory."""

        if not parts:
            return self.root.resolve()
        relative = Path(parts[0])
        for part in parts[1:]:
            relative = relative / part
        return resolve_relative_path(self.root.resolve(), relative)

    # Friendly aliases.
    safe_path = resolve
    resolve_relative = resolve
    safe_join = resolve

    def validate_relative(self, relative: str | Path) -> Path:
        """Validate a relative path without resolving it against the root."""

        return validate_relative_path(relative)

    def __fspath__(self) -> str:
        return str(self.root)

    def __truediv__(self, relative: str | Path) -> Path:
        return self.resolve(relative)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DataDirectory):
            return self.root == other.root
        if isinstance(other, (str, os.PathLike)):
            return Path(os.fspath(other)) == self.root
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.root)

    def __repr__(self) -> str:
        return f"DataDirectory({str(self.root)!r})"

    def __enter__(self) -> DataDirectory:
        self.ensure()
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


# Common alternative spellings.
DataDir = DataDirectory
LocalDataDirectory = DataDirectory


def open_data_directory(
    root: Path | str,
    *,
    create: bool = True,
) -> DataDirectory:
    """Open (and optionally create) a local data directory."""

    return DataDirectory(root, create=create)


open_data_dir = open_data_directory
data_directory = open_data_directory


__all__ = [
    "DataDir",
    "DataDirectory",
    "LocalDataDirectory",
    "data_directory",
    "open_data_dir",
    "open_data_directory",
]
