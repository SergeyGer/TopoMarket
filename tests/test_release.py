"""Tests for the Step 8 release checks and package metadata."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from topomarket import __version__
from topomarket.release import (
    check_lockfile,
    check_package_data,
    check_repository_hygiene,
    check_showcase_fixture,
    check_version_consistency,
    find_repo_root,
    run_release_check,
)

ROOT = Path(__file__).resolve().parents[1]


def test_find_repo_root_points_at_checkout() -> None:
    assert find_repo_root(ROOT) == ROOT


def test_version_consistency() -> None:
    result = check_version_consistency(ROOT)
    assert result.passed, result.details


def test_repository_hygiene_has_no_tracked_private_inputs() -> None:
    result = check_repository_hygiene(ROOT)
    assert result.passed, result.details


def test_package_data_resources_load() -> None:
    result = check_package_data()
    assert result.passed, result.details
    assert result.details["resources"]


def test_lockfile_is_pinned() -> None:
    result = check_lockfile(ROOT)
    assert result.passed, result.details
    assert result.details["entries"] > 0


def test_showcase_fixture_hashes_match() -> None:
    result = check_showcase_fixture(ROOT)
    assert result.passed, result.details
    assert result.details.get("skipped") is not True


def test_release_check_report_without_smoke() -> None:
    report = run_release_check(ROOT, skip_smoke=True)
    assert report["package_version"] == __version__
    assert report["passed"] is True, report
    names = {check["name"] for check in report["checks"]}
    assert {
        "version_consistency",
        "repository_hygiene",
        "package_data",
        "lockfile",
        "showcase_fixture",
    } <= names


def _env() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


def test_release_check_cli_json() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "topomarket", "release-check", "--json", "--skip-smoke"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
        env=_env(),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_release_check_cli_reports_failure(tmp_path: Path) -> None:
    # A fake repository root with mismatched versions must fail the checks.
    fake = tmp_path / "fake-repo"
    (fake / "src" / "topomarket").mkdir(parents=True)
    (fake / "pyproject.toml").write_text(
        '[project]\nname = "fake"\nversion = "9.9.9"\n', encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "topomarket", "release-check", "--json", "--skip-smoke"],
        cwd=str(fake),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
        env=_env(),
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
