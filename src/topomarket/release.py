"""Release checks for the public TopoMarket release (Step 8).

The helpers are offline and deterministic: they verify version consistency,
repository hygiene, packaged data resources, the dependency lock, changelog
coverage, synthetic-fixture determinism and an offline public-mode smoke test.
They are used by the ``topomarket release-check`` CLI command and by the
release CI workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess  # nosec B404 - fixed local release commands
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from topomarket import __version__
from topomarket.data.manifest import path_text

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCKFILE_FILENAME = "requirements.lock"
CHANGELOG_FILENAME = "CHANGELOG.md"
FORBIDDEN_TRACKED_PREFIXES = (
    "private_data/",
    ".adp-inputs/",
    ".adp/",
    "data/local/",
    "artifacts/",
)
FORBIDDEN_TRACKED_NAMES = {".env", ".git-token", "ledger.jsonl", "forecast-ledger.jsonl"}
PACKAGE_DATA_RESOURCES = (
    "topomarket.data/demo_markets.json",
    "topomarket.topology/topology.json",
)
RUNTIME_DEPENDENCIES = ("httpx", "numpy", "ripser")


class ReleaseCheckError(ValueError):
    """Raised when the release environment is not a usable repository root."""


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "details": self.details}


def _run(
    command: Sequence[str], *, cwd: Path, timeout: float = 120.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed commands, no shell
        list(command),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def find_repo_root(start: Path | str | None = None) -> Path:
    """Locate the repository root (directory containing pyproject.toml)."""

    candidates: list[Path] = []
    if start is not None:
        candidates.append(Path(start).resolve())
    if os.environ.get("TOPOMARKET_ROOT"):
        candidates.append(Path(os.environ["TOPOMARKET_ROOT"]).resolve())
    candidates.append(Path.cwd().resolve())
    candidates.append(REPO_ROOT)
    for candidate in candidates:
        current = candidate
        for parent in (current, *current.parents):
            if (parent / "pyproject.toml").is_file() and (parent / "src" / "topomarket").is_dir():
                return parent
    raise ReleaseCheckError("could not locate the TopoMarket repository root")


def _pyproject_version(root: Path) -> str | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("version ="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def check_version_consistency(root: Path) -> CheckResult:
    """Compare the package version, pyproject version and changelog coverage."""

    declared = _pyproject_version(root)
    details: dict[str, Any] = {
        "package_version": __version__,
        "pyproject_version": declared,
    }
    problems: list[str] = []
    if declared is None:
        problems.append("pyproject.toml has no project version")
    elif declared != __version__:
        problems.append(f"pyproject version {declared!r} != package version {__version__!r}")
    changelog = root / CHANGELOG_FILENAME
    if changelog.is_file():
        text = changelog.read_text(encoding="utf-8")
        if f"v{__version__}" not in text:
            problems.append(f"CHANGELOG.md does not mention v{__version__}")
    details["problems"] = problems
    return CheckResult("version_consistency", not problems, details)


def _tracked_files(root: Path) -> list[str] | None:
    if not (root / ".git").exists():
        return None
    result = _run(("git", "ls-files"), cwd=root)
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def check_repository_hygiene(root: Path) -> CheckResult:
    """Ensure private inputs, credentials and local artifacts are not tracked."""

    tracked = _tracked_files(root)
    details: dict[str, Any] = {"tracked_count": None if tracked is None else len(tracked)}
    problems: list[str] = []
    if tracked is None:
        details["problems"] = ["not a git checkout; tracked-file check skipped"]
        return CheckResult("repository_hygiene", True, details)
    for path in tracked:
        normalized = path.replace("\\", "/")
        if normalized.startswith(FORBIDDEN_TRACKED_PREFIXES):
            problems.append(f"forbidden tracked path: {path}")
        if Path(normalized).name in FORBIDDEN_TRACKED_NAMES:
            problems.append(f"forbidden tracked file: {path}")
    gitignore = root / ".gitignore"
    for pattern in ("private_data/", ".adp-inputs/", ".env", ".venv/"):
        if not gitignore.is_file() or pattern not in gitignore.read_text(encoding="utf-8"):
            problems.append(f".gitignore does not cover {pattern!r}")
    details["problems"] = problems
    return CheckResult("repository_hygiene", not problems, details)


def check_package_data() -> CheckResult:
    """Verify packaged JSON resources are importable from the installed package."""

    from importlib import resources

    details: dict[str, Any] = {"resources": {}}
    problems: list[str] = []
    for requirement in PACKAGE_DATA_RESOURCES:
        package, _, filename = requirement.partition("/")
        try:
            resource = resources.files(package).joinpath(filename)
            payload = resource.read_text(encoding="utf-8")
            json.loads(payload)
            details["resources"][requirement] = len(payload)
        except (ModuleNotFoundError, FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            problems.append(f"{requirement}: {type(exc).__name__}: {exc}")
    details["problems"] = problems
    return CheckResult("package_data", not problems, details)


def check_config_parity(root: Path) -> CheckResult:
    """Verify packaged profile templates match the canonical repository configs."""

    details: dict[str, Any] = {"files": {}}
    problems: list[str] = []
    source_dir = root / "config"
    package_dir = Path(__file__).resolve().parent / "config"
    for name in ("demo.json", "private.json"):
        source = source_dir / name
        packaged = package_dir / name
        if not source.is_file() or not packaged.is_file():
            problems.append(f"missing profile template: {name}")
            continue
        try:
            source_payload = json.loads(source.read_text(encoding="utf-8"))
            packaged_payload = json.loads(packaged.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"invalid profile template {name}: {exc}")
            continue
        details["files"][name] = {
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "package_sha256": hashlib.sha256(packaged.read_bytes()).hexdigest(),
        }
        if source_payload != packaged_payload:
            problems.append(f"packaged profile template differs from config/: {name}")
    details["problems"] = problems
    return CheckResult("config_parity", not problems, details)


def check_lockfile(root: Path) -> CheckResult:
    """Verify the dependency lock exists with pinned runtime dependencies."""

    path = root / LOCKFILE_FILENAME
    details: dict[str, Any] = {"path": path_text(path)}
    problems: list[str] = []
    if not path.is_file():
        problems.append(f"{LOCKFILE_FILENAME} is missing")
    else:
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        details["entries"] = len(lines)
        pinned = {line.split("==", 1)[0].lower(): line for line in lines if "==" in line}
        for dependency in RUNTIME_DEPENDENCIES:
            if dependency not in pinned:
                problems.append(f"lockfile has no pinned entry for {dependency}")
        if any("editable" in line.lower() or line.startswith("-e ") for line in lines):
            problems.append("lockfile must not contain editable installs")
    details["problems"] = problems
    return CheckResult("lockfile", not problems, details)


def check_synthetic_fixtures(root: Path, *, workdir: Path | None = None) -> CheckResult:
    """Regenerate the synthetic demo twice and verify deterministic hashes."""

    details: dict[str, Any] = {}
    problems: list[str] = []
    temporary = (
        Path(tempfile.mkdtemp(prefix="topomarket-fixtures-")) if workdir is None else workdir
    )
    try:
        hashes = []
        for index in (1, 2):
            target = temporary / f"fixture-{index}"
            result = _run(
                (
                    sys.executable,
                    "-m",
                    "topomarket",
                    "synthetic",
                    "--out",
                    str(target),
                    "--seed",
                    "42",
                ),
                cwd=root,
                timeout=180.0,
            )
            if result.returncode != 0:
                problems.append(f"synthetic run {index} failed: {result.stderr.strip()[:300]}")
                break
            hashes.append(_hash_tree(target))
        details["hashes"] = hashes
        if len(hashes) == 2 and hashes[0] != hashes[1]:
            problems.append("synthetic fixture generation is not deterministic")
        details["identical"] = len(hashes) == 2 and hashes[0] == hashes[1]
    finally:
        if workdir is None:
            import shutil

            shutil.rmtree(temporary, ignore_errors=True)
    details["problems"] = problems
    return CheckResult("synthetic_fixtures", not problems, details)


def _hash_tree(directory: Path) -> str:
    """Hash the generated data files (the manifest records a generation timestamp)."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            digest.update(path.relative_to(directory).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def check_public_smoke(root: Path, *, workdir: Path | None = None) -> CheckResult:
    """Run the offline public-mode smoke commands (no network, no credentials)."""

    temporary = Path(tempfile.mkdtemp(prefix="topomarket-smoke-")) if workdir is None else workdir
    details: dict[str, Any] = {"commands": {}}
    problems: list[str] = []
    environment = {
        k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "DEEPSEEK_API_KEY"}
    }
    samples = [
        ("demo", (sys.executable, "-m", "topomarket", "demo", "--json")),
        (
            "synthetic",
            (
                sys.executable,
                "-m",
                "topomarket",
                "synthetic",
                "--out",
                str(temporary / "synthetic"),
                "--seed",
                "42",
            ),
        ),
        (
            "validate",
            (
                sys.executable,
                "-m",
                "topomarket",
                "validate",
                "--data-dir",
                str(temporary / "synthetic"),
            ),
        ),
        (
            "status",
            (
                sys.executable,
                "-m",
                "topomarket",
                "status",
                "--data-dir",
                str(temporary / "synthetic"),
                "--json",
            ),
        ),
        ("app-fallback", (sys.executable, "app.py", "--profile", "demo")),
    ]
    try:
        for name, command in samples:
            result = subprocess.run(  # nosec B603 - fixed commands
                list(command),
                cwd=str(root),
                text=True,
                capture_output=True,
                timeout=180.0,
                check=False,
                env=environment,
            )
            details["commands"][name] = {
                "returncode": result.returncode,
                "stdout_head": result.stdout.strip()[:120],
                "has_dashboard": "TopoMarket dashboard" in result.stdout,
            }
            if result.returncode != 0:
                problems.append(
                    f"public smoke command {name!r} exited {result.returncode}: "
                    f"{result.stderr.strip()[:300]}"
                )
        app_details = details["commands"].get("app-fallback", {})
        if not app_details.get("has_dashboard"):
            problems.append("app fallback did not print the dashboard summary")
    finally:
        if workdir is None:
            import shutil

            shutil.rmtree(temporary, ignore_errors=True)
    details["problems"] = problems
    return CheckResult("public_smoke", not problems, details)


def check_showcase_fixture(root: Path) -> CheckResult:
    """Verify the committed synthetic showcase files against their manifest."""

    showcase = root / "showcase"
    manifest_path = showcase / "manifest.json"
    details: dict[str, Any] = {"path": path_text(showcase)}
    problems: list[str] = []
    if not manifest_path.is_file():
        # The showcase is optional for the minimal package; report as skipped.
        details["problems"] = []
        details["skipped"] = True
        return CheckResult("showcase_fixture", True, details)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(
            "showcase_fixture",
            False,
            {"problems": [f"invalid showcase manifest: {exc}"]},
        )
    for filename, expected in (manifest.get("hashes") or {}).items():
        path = showcase / filename
        if not path.is_file():
            problems.append(f"showcase file missing: {filename}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"showcase file hash mismatch: {filename}")
    details["problems"] = problems
    details["files"] = len(manifest.get("hashes") or {})
    return CheckResult("showcase_fixture", not problems, details)


def run_release_check(
    root: Path | str | None = None,
    *,
    skip_smoke: bool = False,
) -> dict[str, Any]:
    """Run every release check and return a JSON-serialisable report."""

    resolved = find_repo_root(root)
    checks = [
        check_version_consistency(resolved),
        check_repository_hygiene(resolved),
        check_package_data(),
        check_config_parity(resolved),
        check_lockfile(resolved),
        check_showcase_fixture(resolved),
    ]
    if not skip_smoke:
        checks.append(check_synthetic_fixtures(resolved))
        checks.append(check_public_smoke(resolved))
    report = {
        "package_version": __version__,
        "repository_root": str(resolved),
        "checks": [check.as_dict() for check in checks],
        "passed": all(check.passed for check in checks),
    }
    return report


__all__ = [
    "CHANGELOG_FILENAME",
    "CheckResult",
    "FORBIDDEN_TRACKED_NAMES",
    "FORBIDDEN_TRACKED_PREFIXES",
    "LOCKFILE_FILENAME",
    "ReleaseCheckError",
    "check_lockfile",
    "check_config_parity",
    "check_package_data",
    "check_public_smoke",
    "check_repository_hygiene",
    "check_showcase_fixture",
    "check_synthetic_fixtures",
    "check_version_consistency",
    "find_repo_root",
    "run_release_check",
]
