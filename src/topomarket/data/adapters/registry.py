"""Deterministic raw-file hash registry for imported seed archives."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from ..manifest import atomic_write_json, ensure_data_directory
from .base import AliasDict, ParsedSource, sha256_bytes, sha256_file

RAW_HASHES_FILENAME = "raw_hashes.json"
RAW_HASH_REGISTRY_FILENAME = RAW_HASHES_FILENAME
RAW_HASH_REGISTRY_ALIAS_FILENAME = "raw_hash_registry.json"
HASH_REGISTRY_FILENAME = RAW_HASHES_FILENAME
RAW_HASH_SCHEMA_VERSION = 1
HASH_ALGORITHM = "sha256"


class RawHashEntry(AliasDict):
    """A single raw-file provenance record."""

    aliases: Mapping[str, str] = {
        "name": "filename",
        "file": "filename",
        "file_name": "filename",
        "path": "filename",
        "digest": "sha256",
        "hash": "sha256",
        "checksum": "sha256",
        "sha": "sha256",
        "source": "source_id",
        "source_name": "source_id",
        "meta": "metadata",
    }

    def __init__(
        self,
        filename: str,
        sha256: str,
        source_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        payload = {
            "filename": str(filename),
            "sha256": str(sha256),
            "source_id": str(source_id),
            "metadata": dict(metadata or {}),
        }
        super().__init__(payload)

    @property
    def filename(self) -> str:
        return str(dict.__getitem__(self, "filename"))

    @property
    def sha256(self) -> str:
        return str(dict.__getitem__(self, "sha256"))

    @property
    def source_id(self) -> str:
        return str(dict.__getitem__(self, "source_id"))

    def to_dict(self) -> dict[str, Any]:
        return dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RawHashEntry:
        return cls(
            filename=str(payload.get("filename") or payload.get("name") or payload.get("path")),
            sha256=str(payload.get("sha256") or payload.get("digest") or payload.get("hash")),
            source_id=str(payload.get("source_id") or payload.get("source") or "unknown"),
            metadata=payload.get("metadata") or {},
        )


class RawHashRegistry:
    """An ordered collection of raw-file SHA-256 records.

    The registry is independent of the filesystem: callers can register bytes,
    parsed sources or paths and then decide where (and whether) to write the
    JSON document.
    """

    filename = RAW_HASHES_FILENAME
    schema_version = RAW_HASH_SCHEMA_VERSION
    algorithm = HASH_ALGORITHM

    def __init__(
        self,
        entries: Iterable[RawHashEntry | Mapping[str, Any]] | str | Path | None = None,
        *,
        schema_version: int = RAW_HASH_SCHEMA_VERSION,
        algorithm: str = HASH_ALGORITHM,
    ) -> None:
        self.schema_version = int(schema_version)
        self.algorithm = str(algorithm)
        if isinstance(entries, (str, Path)) and Path(entries).suffix.lower() == ".json":
            loaded = type(self).from_file(entries)
            self.schema_version = loaded.schema_version
            self.algorithm = loaded.algorithm
            self.entries = list(loaded.entries)
            return
        self.entries: list[RawHashEntry] = [
            entry if isinstance(entry, RawHashEntry) else RawHashEntry.from_dict(entry)
            for entry in (entries or [])
        ]

    # Recording ---------------------------------------------------------
    def register_bytes(
        self,
        data: bytes | bytearray,
        filename: str,
        source_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RawHashEntry:
        """Register in-memory ``data`` and return its new entry."""

        payload = dict(metadata or {})
        payload.setdefault("size_bytes", len(data))
        entry = RawHashEntry(filename, sha256_bytes(bytes(data)), source_id, payload)
        self.entries.append(entry)
        return entry

    def register(
        self,
        source: ParsedSource | str | bytes | bytearray | Path | Any,
        source_id: str = "unknown",
        metadata: Mapping[str, Any] | None = None,
        *,
        filename: str | None = None,
    ) -> RawHashEntry:
        """Compute and register the digest of a source file."""

        if isinstance(source, ParsedSource):
            payload = source.as_metadata()
            payload.update(metadata or {})
            entry = RawHashEntry(
                filename or source.filename,
                source.sha256 or sha256_bytes(source.data),
                source_id,
                payload,
            )
            self.entries.append(entry)
            return entry

        if isinstance(source, (bytes, bytearray)):
            return self.register_bytes(source, filename or "<bytes>", source_id, metadata=metadata)

        if isinstance(source, str) and "\n" in source and not Path(source).exists():
            return self.register_bytes(
                source.encode("utf-8"),
                filename or "<text>",
                source_id,
                metadata=metadata,
            )

        if hasattr(source, "read"):
            payload = source.read()
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            return self.register_bytes(
                bytes(payload),
                filename or "<stream>",
                source_id,
                metadata=metadata,
            )

        path = Path(source).expanduser()
        size = path.stat().st_size
        payload = {"size_bytes": size, "relative_path": path.name, **dict(metadata or {})}
        entry = RawHashEntry(
            filename or path.name,
            sha256_file(path),
            source_id,
            payload,
        )
        self.entries.append(entry)
        return entry

    def register_text(
        self,
        text: str,
        filename: str = "<text>",
        source_id: str = "unknown",
        metadata: Mapping[str, Any] | None = None,
    ) -> RawHashEntry:
        """Register an in-memory text payload."""

        if not isinstance(text, str):
            raise TypeError("register_text() expects a string")
        return self.register_bytes(text.encode("utf-8"), filename, source_id, metadata=metadata)

    register_data = register_bytes
    register_file = register
    register_path = register
    add = register
    add_file = register
    add_path = register
    add_data = register_bytes
    add_text = register_text

    @staticmethod
    def compute(data: bytes | bytearray) -> str:
        """Return the SHA-256 digest of in-memory bytes."""

        return sha256_bytes(bytes(data))

    @staticmethod
    def compute_file(path: Path | str) -> str:
        """Return the SHA-256 digest of a file."""

        return sha256_file(path)

    hash_bytes = compute
    hash_file = compute_file
    sha256 = compute

    def register_entry(self, entry: RawHashEntry | Mapping[str, Any]) -> RawHashEntry:
        prepared = entry if isinstance(entry, RawHashEntry) else RawHashEntry.from_dict(entry)
        self.entries.append(prepared)
        return prepared

    add_entry = register_entry

    def register_directory(
        self,
        directory: Path | str,
        source_id: str = "unknown",
        *,
        pattern: str = "*",
        recursive: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> list[RawHashEntry]:
        """Register every matching file below ``directory`` in sorted order."""

        root = Path(directory).expanduser()
        candidates = root.rglob(pattern) if recursive else root.glob(pattern)
        registered: list[RawHashEntry] = []
        for path in sorted(candidate for candidate in candidates if candidate.is_file()):
            relative = path.relative_to(root).as_posix()
            entry = self.register(
                path,
                source_id,
                metadata={**dict(metadata or {}), "relative_path": relative},
                filename=path.name,
            )
            registered.append(entry)
        return registered

    @classmethod
    def from_directory(
        cls,
        directory: Path | str,
        source_id: str = "unknown",
        *,
        pattern: str = "*",
        recursive: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> RawHashRegistry:
        """Build a registry from every matching file in ``directory``."""

        registry = cls()
        registry.register_directory(
            directory,
            source_id,
            pattern=pattern,
            recursive=recursive,
            metadata=metadata,
        )
        return registry

    # Lookup ------------------------------------------------------------
    @property
    def records(self) -> list[RawHashEntry]:
        return self.entries

    @property
    def files(self) -> list[RawHashEntry]:
        return self.entries

    @property
    def hashes(self) -> dict[str, str]:
        return {entry.filename: entry.sha256 for entry in self.entries}

    @property
    def digests(self) -> dict[str, str]:
        """Alias for :attr:`hashes` used by some import scripts."""

        return self.hashes

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def by_source(self) -> dict[str, list[RawHashEntry]]:
        grouped: dict[str, list[RawHashEntry]] = {}
        for entry in self.entries:
            grouped.setdefault(entry.source_id, []).append(entry)
        return grouped

    def find(
        self,
        *,
        source_id: str | None = None,
        filename: str | None = None,
    ) -> list[RawHashEntry]:
        entries = self.entries
        if source_id is not None:
            entries = [entry for entry in entries if entry.source_id == source_id]
        if filename is not None:
            entries = [entry for entry in entries if entry.filename == filename]
        return list(entries)

    def get(self, filename: str, default: Any = None) -> RawHashEntry | Any:
        for entry in self.entries:
            if entry.filename == filename:
                return entry
        return default

    def __getitem__(self, key: int | str) -> RawHashEntry:
        if isinstance(key, int):
            return self.entries[key]
        entry = self.get(key)
        if entry is None:
            raise KeyError(key)
        return entry

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return any(entry.filename == key for entry in self.entries)
        return key in self.entries

    def __iter__(self) -> Iterator[RawHashEntry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    # Serialisation -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        # Sorting makes the on-disk document independent of directory traversal
        # or archive-member order, while every entry keeps its original data.
        entries = sorted(
            (dict(entry) for entry in self.entries),
            key=lambda entry: (
                str(entry.get("filename", "")),
                str(entry.get("source_id", "")),
                str(entry.get("sha256", "")),
            ),
        )
        # The plural aliases mirror the way the synthetic manifest exposes
        # checksums, making the document easy to consume from older scripts.
        hashes = {entry["filename"]: entry["sha256"] for entry in entries}
        return {
            "schema_version": self.schema_version,
            "algorithm": self.algorithm,
            "entry_count": len(entries),
            "entries": entries,
            "records": [dict(entry) for entry in entries],
            "files": [dict(entry) for entry in entries],
            "hashes": hashes,
            "digests": dict(hashes),
            "source_ids": sorted({str(entry.get("source_id", "")) for entry in entries}),
        }

    as_dict = to_dict

    def to_json(self, *, indent: int | None = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False)

    def write(self, path: Path | str | None = None) -> Path:
        """Write the registry atomically and return the destination path."""

        destination = Path(path) if path is not None else Path(self.filename)
        if destination.parent and str(destination.parent) not in ("", "."):
            ensure_data_directory(destination.parent)
        atomic_write_json(destination, self.to_dict())
        return destination

    save = write
    write_json = write
    to_file = write
    to_path = write

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> RawHashRegistry:
        if isinstance(payload, Mapping):
            entries = (
                payload.get("entries") or payload.get("records") or payload.get("files") or []
            )
            schema_version = int(payload.get("schema_version", RAW_HASH_SCHEMA_VERSION))
            algorithm = str(payload.get("algorithm", HASH_ALGORITHM))
        else:
            entries = list(payload)
            schema_version = RAW_HASH_SCHEMA_VERSION
            algorithm = HASH_ALGORITHM
        if isinstance(entries, Mapping):
            entries = [
                {"filename": filename, "sha256": digest, "source_id": "unknown"}
                for filename, digest in entries.items()
            ]
        return cls(
            entries=entries,
            schema_version=schema_version,
            algorithm=algorithm,
        )

    @classmethod
    def from_file(cls, path: Path | str) -> RawHashRegistry:
        import json

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, (Mapping, list, tuple)):
            raise ValueError("raw hash registry must contain a JSON object or list")
        return cls.from_dict(payload)

    load = from_file
    read = from_file
    from_path = from_file
    read_file = from_file
    load_file = from_file

    def __repr__(self) -> str:
        return f"RawHashRegistry(entries={len(self.entries)!r})"


# Friendly aliases for callers that use a different vocabulary.
HashRegistry = RawHashRegistry
RawHashes = RawHashRegistry
FileHashRegistry = RawHashRegistry
HashEntry = RawHashEntry
RawFileHash = RawHashEntry
RawFile = RawHashEntry
REGISTRY_FILENAME = RAW_HASHES_FILENAME
DEFAULT_REGISTRY_FILENAME = RAW_HASHES_FILENAME
def register_file(
    source: ParsedSource | str | bytes | bytearray | Path | Any,
    source_id: str = "unknown",
    metadata: Mapping[str, Any] | None = None,
    *,
    filename: str | None = None,
    registry: RawHashRegistry | None = None,
) -> RawHashEntry:
    """Register one file/bytes source and return its entry.

    A registry may be supplied; otherwise a temporary in-memory registry is
    used, which keeps the helper convenient for one-off hashing calls.
    """

    target = registry if registry is not None else RawHashRegistry()
    return target.register(
        source,
        source_id,
        metadata=metadata,
        filename=filename,
    )


compute_sha256 = sha256_bytes
sha256_digest = sha256_bytes
hash_file = sha256_file


def build_raw_hash_registry(
    input_dir: Path | str | None = None,
    *,
    input_zip: Path | str | None = None,
    input_path: Path | str | None = None,
    source_id: str = "auto",
    detect_source: bool = True,
) -> RawHashRegistry:
    """Build a registry for every seed file in a directory or zip archive."""

    # Imported lazily to keep the registry module independent of adapter
    # detection during normal single-file use.
    from .pipeline import detect_adapter, load_input_sources

    registry = RawHashRegistry()
    for source in load_input_sources(
        input_dir,
        input_zip=input_zip,
        input_path=input_path,
    ):
        detected = detect_adapter(source=source) if detect_source else None
        resolved_source_id = (
            detected.source_id
            if detected is not None
            else (source_id if source_id not in ("auto", "detect", None) else "unknown")
        )
        registry.register(
            source,
            source_id=resolved_source_id,
            metadata=source.as_metadata(),
        )
    return registry


raw_hash_registry = build_raw_hash_registry
registry_for_sources = build_raw_hash_registry


def load_registry(path: Path | str) -> RawHashRegistry:
    """Load a raw hash registry from ``path``."""

    return RawHashRegistry.from_file(path)


def write_registry(registry: RawHashRegistry, path: Path | str) -> Path:
    """Write ``registry`` to ``path`` and return the path."""

    return registry.write(path)


__all__ = [
    "build_raw_hash_registry",
    "raw_hash_registry",
    "registry_for_sources",
    "HASH_ALGORITHM",
    "HASH_REGISTRY_FILENAME",
    "RAW_HASHES_FILENAME",
    "RAW_HASH_REGISTRY_ALIAS_FILENAME",
    "RAW_HASH_REGISTRY_FILENAME",
    "RAW_HASH_SCHEMA_VERSION",
    "DEFAULT_REGISTRY_FILENAME",
    "FileHashRegistry",
    "HashEntry",
    "HashRegistry",
    "REGISTRY_FILENAME",
    "RawFile",
    "RawFileHash",
    "RawHashEntry",
    "RawHashRegistry",
    "RawHashes",
    "compute_sha256",
    "hash_file",
    "load_registry",
    "register_file",
    "sha256_digest",
    "write_registry",
]
