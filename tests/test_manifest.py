"""Tests for atomic manifest handling and snapshot identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket.data import manifest as manifest_module
from topomarket.data.manifest import (
    MANIFEST_FILENAME,
    REQUIRED_MANIFEST_FIELDS,
    ManifestIntegrityError,
    ManifestNotFoundError,
    atomic_write_json,
    compute_snapshot_id,
    read_manifest,
    snapshot_id,
    validate_manifest,
    write_manifest,
)


def _manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "profile": "demo",
        "data_source": "synthetic",
        "source": "tests",
        "files": [{"path": "demo_markets.json", "sha256": "abc"}],
        "metadata": {"note": "example"},
        "created_at": "2024-01-01T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_write_manifest_is_atomic_and_complete(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"

    written = write_manifest(data_dir, _manifest())

    location = data_dir / MANIFEST_FILENAME
    assert location.is_file()
    assert written == read_manifest(data_dir)
    for field in REQUIRED_MANIFEST_FIELDS:
        assert field in written, field
    assert written["snapshot_id"] == compute_snapshot_id(written)
    assert written["created_at"] == "2024-01-01T00:00:00Z"
    assert list(data_dir.glob("*.tmp")) == []
    assert list(data_dir.glob(".manifest.json.*")) == []


def test_manifest_paths_may_be_given_directly(tmp_path: Path) -> None:
    location = tmp_path / "custom" / "manifest.json"

    write_manifest(location, _manifest())

    assert location.is_file()
    assert read_manifest(location)["profile"] == "demo"


def test_atomic_write_failure_leaves_previous_manifest_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    write_manifest(data_dir, _manifest())
    location = data_dir / MANIFEST_FILENAME
    before = location.read_bytes()

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(manifest_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        write_manifest(data_dir, _manifest(data_source="changed"))

    assert location.read_bytes() == before
    assert list(data_dir.glob("*.tmp")) == []


def test_serialisation_failure_does_not_create_partial_json(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = data_dir / "manifest.json"

    class NotSerialisable:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": NotSerialisable()})

    assert not target.exists()
    assert list(data_dir.iterdir()) == []


def test_manifest_tampering_is_detected(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_manifest(data_dir, _manifest())
    location = data_dir / MANIFEST_FILENAME
    payload = json.loads(location.read_text(encoding="utf-8"))

    payload["data_source"] = "tampered"
    location.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestIntegrityError, match="snapshot_id"):
        read_manifest(data_dir)


def test_strict_validation_requires_provenance_fields(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / MANIFEST_FILENAME).write_text(
        json.dumps({"profile": "demo"}), encoding="utf-8"
    )

    with pytest.raises(ManifestIntegrityError, match="required provenance"):
        read_manifest(data_dir, strict=True)


@pytest.mark.parametrize("payload", ["not json", "[]", "null"])
def test_malformed_manifests_are_rejected(tmp_path: Path, payload: str) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / MANIFEST_FILENAME).write_text(payload, encoding="utf-8")

    with pytest.raises(ManifestIntegrityError):
        read_manifest(data_dir)


def test_missing_manifest_raises_not_found(tmp_path: Path) -> None:
    with pytest.raises(ManifestNotFoundError) as excinfo:
        read_manifest(tmp_path / "missing")

    assert isinstance(excinfo.value, FileNotFoundError)


def test_validate_manifest_detects_modified_content() -> None:
    complete = manifest_module.normalise_manifest(_manifest())
    assert validate_manifest(complete)["snapshot_id"] == complete["snapshot_id"]

    tampered = dict(complete)
    tampered["metadata"] = {"note": "changed"}
    with pytest.raises(ManifestIntegrityError):
        validate_manifest(tampered)


def test_snapshot_id_is_deterministic_and_ignores_created_at() -> None:
    first = _manifest(created_at="2024-01-01T00:00:00Z")
    second = _manifest(created_at="2030-12-31T23:59:59Z")

    assert snapshot_id(first) == snapshot_id(second)
    assert snapshot_id(first) == compute_snapshot_id(first)
    assert snapshot_id({**first, "snapshot_id": "stale"}) == snapshot_id(first)


def test_snapshot_id_changes_with_content() -> None:
    first = _manifest()
    second = _manifest(data_source="different")

    assert snapshot_id(first) != snapshot_id(second)


def test_snapshot_id_is_stable_across_process_runs() -> None:
    manifest = {
        "profile": "demo",
        "data_source": "synthetic",
        "created_at": "2024-01-01T00:00:00Z",
    }
    identifier = snapshot_id(manifest)
    assert len(identifier) == 64
    assert all(character in "0123456789abcdef" for character in identifier)
    # Mapping insertion order must not affect the content hash.
    assert identifier == snapshot_id(dict(reversed(list(manifest.items()))))
