"""R3: CLI evaluation resolves one non-empty snapshot identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from topomarket.data.identity import SnapshotIdentityError, resolve_snapshot_identity

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "showcase"


def test_direct_snapshot_identity_resolves_from_import_manifest() -> None:
    identity = resolve_snapshot_identity(SHOWCASE)
    assert identity["snapshot_id"] == "showcase-synthetic"
    assert identity["source"] == "import_manifest"
    assert identity["manifest_digest"]


def test_import_manifest_without_identifier_uses_content_digest(tmp_path: Path) -> None:
    (tmp_path / "import_manifest.json").write_text(
        json.dumps({"schema_version": 1, "row_counts": {"tda_daily": 10}}), encoding="utf-8"
    )
    first = resolve_snapshot_identity(tmp_path)
    second = resolve_snapshot_identity(tmp_path)
    assert first["snapshot_id"]
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["manifest_digest"] == second["manifest_digest"]


def test_conflicting_identity_sources_fail_visibly(tmp_path: Path) -> None:
    (tmp_path / "refresh_manifest.json").write_text(
        json.dumps({"snapshot_id": "alpha", "files": []}), encoding="utf-8"
    )
    (tmp_path / "import_manifest.json").write_text(
        json.dumps({"snapshot_id": "beta"}), encoding="utf-8"
    )
    with pytest.raises(SnapshotIdentityError):
        resolve_snapshot_identity(tmp_path)


def test_cli_evaluation_attaches_snapshot_identity(tmp_path: Path, capsys) -> None:
    from topomarket.cli import _run_evaluation

    report_path = tmp_path / "evaluation.json"
    status = _run_evaluation(
        data_dir=SHOWCASE,
        emit_json=True,
        report_out=report_path,
        ledger=None,
        seed=42,
        ablations=False,
    )
    assert status == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["snapshot_id"] == "showcase-synthetic"
    assert report["provenance"]["snapshot_provenance"]["source"] == "import_manifest"
    assert report["provenance"]["snapshot_provenance"]["manifest_digest"]
