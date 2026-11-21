"""End-to-end integration tests across profiles, data, CLI, and the UI.

The tests only use bundled synthetic data or temporary directories. They never
read private inputs, contact the network, or depend on ambient user settings.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from topomarket import __version__
from topomarket.cli import main
from topomarket.data import (
    SYNTHETIC_FILE_NAMES,
    latest_snapshot,
    read_manifest,
    snapshot_id,
    write_snapshot,
)
from topomarket.profiles import load_profile
from topomarket.ui.overview import build_overview

REPO_ROOT = Path(__file__).resolve().parents[1]


def _manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "profile": "demo",
        "data_source": "synthetic",
        "source": "integration-test",
        "files": [],
    }
    payload.update(overrides)
    return payload


def test_synthetic_cli_pipeline_reaches_the_overview(tmp_path: Path, capsys) -> None:
    data_dir = tmp_path / "synthetic"

    assert main(["synthetic", "--out", str(data_dir), "--seed", "123"]) == 0
    generated = capsys.readouterr().out
    assert "seed=123" in generated
    for filename in SYNTHETIC_FILE_NAMES:
        assert (data_dir / filename).is_file()

    manifest = read_manifest(data_dir)
    assert manifest["seed"] == 123
    assert manifest["snapshot_id"] == snapshot_id(manifest)

    profile = load_profile("demo", data_dir=data_dir)
    assert profile.data_dir == data_dir
    assert profile.private_data is False

    overview = build_overview(profile.profile, data_dir=data_dir)
    assert overview["profile"] == "demo"
    assert overview["data_available"] is True
    assert overview["manifest"]["snapshot_id"] == manifest["snapshot_id"]
    assert overview["latest_data_date"] == "2024-01-30"
    assert overview["empty_state"] is None

    assert main(["status", "--data-dir", str(data_dir), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["profile"] == "demo"
    assert status["data_source"] == "synthetic"
    assert status["manifest_present"] is True
    assert status["manifest_valid"] is True
    assert status["snapshot_count"] == 0
    assert status["latest_data_date"] == "2024-01-30"

    assert main(["validate", "--data-dir", str(data_dir)]) == 0
    assert "is valid" in capsys.readouterr().out.lower()


def test_snapshot_round_trip_is_visible_to_the_overview(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    written = write_snapshot(
        data_dir,
        _manifest(created_at="2025-05-06T12:00:00Z"),
    )

    latest = latest_snapshot(data_dir)
    assert latest is not None
    assert latest.snapshot_id == written.snapshot_id
    assert latest.path == written.path
    assert read_manifest(data_dir / "snapshots" / written.snapshot_id) == written

    overview = build_overview("demo", data_dir=data_dir)
    assert overview["data_available"] is True
    assert overview["data_status"]["snapshot_count"] == 1
    assert overview["latest_data_date"] == "2025-05-06"


def test_bundled_demo_profile_needs_no_private_data(capsys) -> None:
    profile = load_profile("demo")

    assert profile.private_data is False
    assert profile.data_dir.is_relative_to(REPO_ROOT)
    assert (profile.data_dir / "demo_markets.json").is_file()

    assert main(["demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "demo"
    assert payload["data_source"] == "synthetic"
    assert payload["market_count"] >= 1


def test_python_m_topomarket_entry_point() -> None:
    environment = dict(os.environ)
    source_path = str(REPO_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = source_path + os.pathsep + existing if existing else source_path

    version = subprocess.run(
        [sys.executable, "-m", "topomarket", "--version"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert version.returncode == 0, version.stderr
    assert __version__ in version.stdout

    demo = subprocess.run(
        [sys.executable, "-m", "topomarket", "demo"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert demo.returncode == 0, demo.stderr
    assert "TopoMarket demo" in demo.stdout
    assert "synthetic" in demo.stdout
