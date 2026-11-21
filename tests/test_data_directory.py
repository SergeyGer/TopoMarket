"""Tests for data directories, snapshot listing, and path traversal guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket.data import (
    DataDirectory,
    ManifestIntegrityError,
    PathTraversalError,
    ensure_data_directory,
    latest_snapshot,
    list_snapshot_ids,
    list_snapshots,
    open_data_directory,
    read_manifest,
    resolve_relative_path,
    safe_join,
    snapshot_id,
    validate_relative_path,
    write_manifest,
    write_snapshot,
)


def _manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "profile": "demo",
        "data_source": "synthetic",
        "source": "tests",
        "files": ["demo_markets.json"],
        "metadata": {"note": "snapshot"},
    }
    payload.update(overrides)
    return payload


def test_ensure_data_directory_creates_and_validates(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "data"

    created = ensure_data_directory(target)

    assert created == target.resolve()
    assert target.is_dir()

    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        ensure_data_directory(file_path)


def test_data_directory_round_trip(tmp_path: Path) -> None:
    with DataDirectory.create(tmp_path / "data") as data_directory:
        written = data_directory.write_manifest(_manifest())
        read_back = data_directory.read_manifest()

    assert data_directory.exists()
    assert written == read_back
    assert data_directory.manifest_path == tmp_path / "data" / "manifest.json"
    assert data_directory.resolve("nested", "file.json") == (
        tmp_path / "data" / "nested" / "file.json"
    )
    assert data_directory.snapshot_id(read_back) == read_back["snapshot_id"]


def test_open_data_directory_alias(tmp_path: Path) -> None:
    directory = open_data_directory(tmp_path / "data")

    assert isinstance(directory, DataDirectory)
    assert directory.exists()


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    base = tmp_path / "data"
    base.mkdir()

    unsafe = [
        "../secret",
        "a/../../b",
        "/etc/passwd",
        "..\\secret",
        "C:\\Windows\\system32",
        "",
        ".",
        "~/private",
    ]
    for relative in unsafe:
        with pytest.raises(PathTraversalError):
            validate_relative_path(relative)
        with pytest.raises(PathTraversalError):
            resolve_relative_path(base, relative)

    with pytest.raises(PathTraversalError):
        safe_join(base, "safe", "..", "escape")


def test_valid_relative_paths_resolve_below_base(tmp_path: Path) -> None:
    base = tmp_path / "data"
    base.mkdir()

    assert validate_relative_path("nested/file.json") == Path("nested/file.json")
    assert validate_relative_path("nested/./file.json") == Path("nested/file.json")
    assert resolve_relative_path(base, "nested/file.json") == base / "nested" / "file.json"
    assert safe_join(base, "nested", "file.json") == base / "nested" / "file.json"


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    base = tmp_path / "data"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    try:
        (base / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("symlinks are not supported on this platform")

    with pytest.raises(PathTraversalError):
        resolve_relative_path(base, "link/secret.txt")


def test_list_snapshots_accepts_single_manifest(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "data", _manifest())

    assert [snapshot.snapshot_id for snapshot in list_snapshots(manifest)] == [
        manifest["snapshot_id"]
    ]
    assert latest_snapshot(manifest) == manifest


def test_snapshot_listing_and_latest(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    older = write_snapshot(
        data_dir,
        _manifest(created_at="2024-01-01T00:00:00Z", metadata={"version": 1}),
    )
    newer = write_snapshot(
        data_dir,
        _manifest(created_at="2025-01-01T00:00:00Z", metadata={"version": 2}),
    )

    snapshots = list_snapshots(data_dir)

    assert len(snapshots) == 2
    assert [snapshot.snapshot_id for snapshot in snapshots] == [
        older.snapshot_id,
        newer.snapshot_id,
    ]
    assert latest_snapshot(data_dir) == newer
    assert latest_snapshot(data_dir).snapshot_id == newer.snapshot_id
    assert list_snapshot_ids(data_dir) == [older.snapshot_id, newer.snapshot_id]
    assert json.loads((newer.path / "manifest.json").read_text(encoding="utf-8"))[
        "metadata"
    ] == {"version": 2}


def test_list_snapshots_supports_json_snapshot_files(tmp_path: Path) -> None:
    snapshots_dir = tmp_path / "data" / "snapshots"
    snapshots_dir.mkdir(parents=True)
    first = _manifest(created_at="2024-01-01T00:00:00Z", metadata={"version": 1})
    second = _manifest(created_at="2025-01-01T00:00:00Z", metadata={"version": 2})
    (snapshots_dir / "first.json").write_text(json.dumps(first), encoding="utf-8")
    (snapshots_dir / "second.json").write_text(json.dumps(second), encoding="utf-8")

    listed = list_snapshots(snapshots_dir.parent)

    assert len(listed) == 2
    assert listed[-1].created_at == "2025-01-01T00:00:00Z"
    assert latest_snapshot(snapshots_dir.parent) == listed[-1]


def test_latest_snapshot_is_none_for_empty_directory(tmp_path: Path) -> None:
    assert list_snapshots(tmp_path / "empty") == []
    assert latest_snapshot(tmp_path / "empty") is None


def test_data_directory_manifest_is_not_a_snapshot(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_manifest(data_dir, _manifest())

    assert list_snapshots(data_dir) == []
    assert latest_snapshot(data_dir) is None


def test_snapshots_with_identical_content_share_an_id(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    first = write_snapshot(
        data_dir, _manifest(created_at="2024-01-01T00:00:00Z")
    )
    second = write_snapshot(
        data_dir, _manifest(created_at="2030-01-01T00:00:00Z")
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.path == second.path
    assert len(list_snapshots(data_dir)) == 1


def test_data_directory_rejects_traversal(tmp_path: Path) -> None:
    data_directory = DataDirectory.create(tmp_path / "data")

    with pytest.raises(PathTraversalError):
        data_directory.resolve("../manifest.json")
    with pytest.raises(PathTraversalError):
        data_directory.validate_relative("nested/../../escape")


def test_manifest_integrity_survives_data_directory_reopen(tmp_path: Path) -> None:
    data_directory = DataDirectory.create(tmp_path / "data")
    written = data_directory.write_manifest(_manifest())

    reopened = DataDirectory(tmp_path / "data")
    assert reopened.read_manifest() == written
    assert reopened.snapshot_id() == snapshot_id(written)

    (tmp_path / "data" / "manifest.json").write_text(
        json.dumps({**written, "profile": "private"}), encoding="utf-8"
    )
    with pytest.raises(ManifestIntegrityError):
        reopened.read_manifest()


def test_write_manifest_defaults_provenance_fields(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"

    written = write_manifest(data_dir, _manifest(created_at=None))

    assert written["schema_version"] == 1
    assert written["generator"] == "topomarket"
    assert written["generator_version"]
    assert written["data_dir"] == str(data_dir)
    assert read_manifest(data_dir)["snapshot_id"] == written["snapshot_id"]
