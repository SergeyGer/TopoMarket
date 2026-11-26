"""Focused tests for manifest helpers beyond the core read/write path."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from topomarket.data import directory as directory_module
from topomarket.data.manifest import (
    MANIFEST_FILENAME,
    Manifest,
    ManifestError,
    ManifestIntegrityError,
    Snapshot,
    canonical_json,
    ensure_data_directory,
    list_snapshots,
    manifest_path,
    normalise_manifest,
    resolve_relative_path,
    safe_join,
    validate_manifest,
    validate_relative_path,
    write_manifest,
    write_snapshot,
)


def test_canonical_json_is_stable_and_supports_common_values() -> None:
    payload = {
        "path": Path("data") / "file.csv",
        "created": datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        "day": date(2024, 1, 2),
        "tags": {"b", "a"},
        "blob": b"hello",
    }

    first = canonical_json(payload)
    second = canonical_json(dict(reversed(list(payload.items()))))

    assert first == second
    assert '"tags":["a","b"]' in first
    assert '"blob":"hello"' in first
    assert '"path":"data/file.csv"' in first

    with pytest.raises(TypeError, match="not JSON serialisable"):
        canonical_json({"bad": object()})


def test_normalise_manifest_fills_and_overrides_fields(tmp_path: Path) -> None:
    result = normalise_manifest(
        {"profile": "demo", "metadata": {"keep": True}},
        profile="private",
        data_source="synthetic",
        source=tmp_path / "source.csv",
        data_dir=tmp_path,
        created_at=datetime(2024, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
        files=[Path("a.csv"), "b.csv"],
        metadata={"note": "updated"},
        schema_version=1,
        generator="custom",
        generator_version="9.9",
    )

    assert result["profile"] == "private"
    assert result["data_source"] == "synthetic"
    assert result["source"] == str(tmp_path / "source.csv")
    assert result["data_dir"] == str(tmp_path)
    assert result["created_at"] == "2024-02-03T04:05:06Z"
    assert result["files"] == [Path("a.csv"), "b.csv"]
    assert result["metadata"] == {"note": "updated"}
    assert result["schema_version"] == 1
    assert result["generator"] == "custom"
    assert result["generator_version"] == "9.9"
    assert result["snapshot_id"]


def test_normalise_manifest_defaults_source_to_data_dir(tmp_path: Path) -> None:
    result = normalise_manifest(data_dir=tmp_path)

    assert result["source"] == str(tmp_path)
    assert result["profile"] == "unknown"
    assert result["data_source"] == "local"
    assert result["files"] == []
    assert result["metadata"] == {}


@pytest.mark.parametrize(
    "manifest",
    [  # type: ignore[list-item]
        ["not", "a", "mapping"],
        "not a mapping",
    ],
)
def test_normalise_manifest_rejects_non_mappings(manifest: object) -> None:
    with pytest.raises(ManifestError, match="must be a mapping"):
        normalise_manifest(manifest)  # type: ignore[arg-type]


def test_normalise_manifest_validates_files_and_metadata() -> None:
    with pytest.raises(ManifestError, match="'files' must be a list"):
        normalise_manifest(files="not-a-list")  # type: ignore[arg-type]
    with pytest.raises(ManifestError, match="entries must be mappings"):
        normalise_manifest(files=[42])  # type: ignore[list-item]
    with pytest.raises(ManifestError, match="'metadata' must be a JSON object"):
        normalise_manifest(metadata=["bad"])  # type: ignore[arg-type]


def test_validate_manifest_returns_a_plain_copy() -> None:
    payload = normalise_manifest({"profile": "demo"})

    validated = validate_manifest(payload)

    assert type(validated) is dict
    assert validated == payload
    assert validated is not payload


def test_validate_manifest_checks_optional_field_types_and_schema() -> None:
    payload = normalise_manifest({"profile": "demo"})

    with pytest.raises(ManifestIntegrityError, match="schema_version"):
        validate_manifest({**payload, "schema_version": 999})
    with pytest.raises(ManifestIntegrityError, match="'files' must be a list"):
        validate_manifest({**payload, "files": "bad"})
    with pytest.raises(ManifestIntegrityError, match="'metadata' must be a JSON object"):
        validate_manifest({**payload, "metadata": ["bad"]})
    with pytest.raises(ManifestIntegrityError, match="must be a JSON object"):
        validate_manifest(["bad"])  # type: ignore[arg-type]


def test_validate_manifest_can_skip_optional_checks() -> None:
    assert validate_manifest(
        {"profile": "demo"}, require_provenance=False, verify_snapshot_id=False
    ) == {"profile": "demo"}


def test_manifest_helpers_expose_the_file_location(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, {"profile": "demo"})
    location = tmp_path / MANIFEST_FILENAME

    assert isinstance(manifest, Manifest)
    assert manifest.path == location
    assert manifest.location == location
    assert os.fspath(manifest) == str(location)
    assert manifest.name == MANIFEST_FILENAME
    assert manifest.exists()
    assert manifest.as_dict() == dict(manifest)
    assert repr(manifest).startswith("Manifest(keys=")
    assert "path=" in repr(manifest)

    assert manifest == dict(manifest)
    assert manifest == location
    assert manifest == str(location)
    assert manifest == manifest.snapshot_id
    assert manifest != object()


def test_manifest_without_a_path_cannot_be_a_filesystem_path() -> None:
    manifest = Manifest({"snapshot_id": "abc"})

    assert manifest.path is None
    assert manifest.location is None
    with pytest.raises(TypeError, match="not associated"):
        os.fspath(manifest)
    with pytest.raises(TypeError):
        Path(manifest)
    with pytest.raises(AttributeError):
        _ = manifest.no_such_attribute


def test_snapshot_helpers_work_without_a_path() -> None:
    snapshot = Snapshot({"profile": "demo"})

    assert snapshot.snapshot_id == snapshot.id
    assert snapshot.as_dict() == dict(snapshot)
    assert "snapshot_id=" in repr(snapshot)
    assert "path=" not in repr(snapshot)
    assert snapshot.path is None
    assert snapshot.directory is None
    assert snapshot.manifest_path is None
    assert snapshot.name is None
    assert snapshot.parent is None
    assert snapshot.created_at is None
    assert snapshot == dict(snapshot)
    assert snapshot == snapshot.snapshot_id
    with pytest.raises(TypeError, match="not associated"):
        os.fspath(snapshot)
    with pytest.raises(TypeError):
        Path(snapshot)


def test_snapshot_helpers_expose_the_directory_and_manifest(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "snapshot", {"profile": "demo"})
    snapshot = Snapshot(manifest, path=tmp_path / "snapshot")

    assert snapshot.path == tmp_path / "snapshot"
    assert snapshot.directory == tmp_path / "snapshot"
    assert snapshot.manifest_path == tmp_path / "snapshot" / MANIFEST_FILENAME
    assert snapshot.name == "snapshot"
    assert snapshot.parent == tmp_path
    assert Path(snapshot) == tmp_path / "snapshot"
    assert snapshot == tmp_path / "snapshot"
    assert snapshot == str(tmp_path / "snapshot")
    assert snapshot == manifest

    manifest_snapshot = Snapshot(manifest, path=manifest.path)
    assert manifest_snapshot.manifest_path == manifest.path


def test_snapshot_equality_requires_matching_paths(tmp_path: Path) -> None:
    first = Snapshot({"profile": "demo"}, path=tmp_path / "first")
    second = Snapshot({"profile": "demo"}, path=tmp_path / "second")

    assert not first == second
    assert first == dict(second)


def test_manifest_path_supports_directories_files_and_custom_names(tmp_path: Path) -> None:
    assert manifest_path(tmp_path) == tmp_path / MANIFEST_FILENAME
    assert manifest_path(tmp_path / "custom.json") == tmp_path / "custom.json"
    assert manifest_path(tmp_path, filename="other.json") == tmp_path / "other.json"


def test_ensure_data_directory_can_require_an_existing_path(tmp_path: Path) -> None:
    assert ensure_data_directory(tmp_path) == tmp_path.resolve()
    with pytest.raises(FileNotFoundError, match="does not exist"):
        ensure_data_directory(tmp_path / "missing", create=False)
    assert directory_module.open_data_directory(tmp_path).path == tmp_path


def test_relative_path_helpers_validate_types_and_existence(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="string or pathlib.Path"):
        validate_relative_path(42)  # type: ignore[arg-type]
    with pytest.raises(ManifestError, match="NUL"):
        validate_relative_path("bad\x00name")
    with pytest.raises(TypeError, match="at least one relative path"):
        safe_join(tmp_path)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve_relative_path(tmp_path, "missing.csv", must_exist=True)


def test_list_snapshots_accepts_mappings_and_iterables(tmp_path: Path) -> None:
    first = {"profile": "demo", "created_at": "2024-01-01T00:00:00Z"}
    second = Snapshot({"profile": "demo", "created_at": "2025-01-01T00:00:00Z"})

    single = list_snapshots(first)
    assert len(single) == 1
    assert isinstance(single[0], Snapshot)

    listed = list_snapshots([first, second])
    assert listed[0].created_at == "2024-01-01T00:00:00Z"
    assert listed[1] is second

    with pytest.raises(TypeError, match="data directory is required"):
        list_snapshots(None)
    assert list_snapshots(path=tmp_path) == []


def test_list_snapshots_skips_unreadable_snapshot_files(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    (snapshots / "broken.json").write_text("{not valid json", encoding="utf-8")

    assert list_snapshots(tmp_path) == []


def test_list_snapshots_accepts_snapshot_directories_at_the_root(tmp_path: Path) -> None:
    child = tmp_path / "snapshot-a"
    write_manifest(child, {"profile": "demo", "created_at": "2024-01-01T00:00:00Z"})

    listed = list_snapshots(tmp_path)

    assert len(listed) == 1
    assert listed[0].path == child


def test_write_snapshot_accepts_a_directory_keyword(tmp_path: Path) -> None:
    written = write_snapshot(
        tmp_path / "ignored",
        {"profile": "demo"},
        directory=tmp_path / "actual",
    )

    assert written.path.is_relative_to(tmp_path / "actual" / "snapshots")
    assert (written.path / MANIFEST_FILENAME).is_file()
    assert (
        json.loads((written.path / MANIFEST_FILENAME).read_text(encoding="utf-8"))["snapshot_id"]
        == written.snapshot_id
    )


def test_relative_paths_accept_windows_separators() -> None:
    """#84: host-native Path components must work on Windows without weakening safety."""

    import pytest

    from topomarket.data.manifest import PathTraversalError, validate_relative_path

    assert validate_relative_path("reports\\ledger.jsonl") == Path("reports/ledger.jsonl")
    assert validate_relative_path(Path("a") / "b") == Path("a/b")
    for unsafe in ("..\\..\\etc\\passwd", "C:\\Windows\\system.ini", "~\\secret", "a\\..\\b"):
        with pytest.raises(PathTraversalError):
            validate_relative_path(unsafe)


def test_path_text_is_host_independent() -> None:
    """#84: serialised identifiers always use forward slashes."""

    from topomarket.data.manifest import path_text

    assert path_text(Path("showcase") / "normalized" / "tda_daily.csv") == (
        "showcase/normalized/tda_daily.csv"
    )
