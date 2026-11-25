#!/usr/bin/env python3
"""Bump the TopoMarket package version and regenerate frozen/versioned artifacts.

Steps:
1. update ``src/topomarket/__init__.py`` and ``pyproject.toml`` versions;
2. recompute the frozen topology configuration registry (config + packaged copy)
   because the canonical config hash binds the package version;
3. rebuild the committed synthetic showcase so score metadata, the evaluation
   report and the manifest hashes carry the new version.

Run only after all code changes are in place.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"


def _update(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"pattern not found in {path}: {pattern!r}")
    path.write_text(updated, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bump the package version and regenerate artifacts."
    )
    parser.add_argument("version", help="New semantic version, for example 0.9.0")
    args = parser.parse_args(argv)
    new_version = args.version.strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", new_version):
        raise SystemExit(f"invalid version: {new_version!r}")
    _update(
        ROOT / "src" / "topomarket" / "__init__.py",
        r'__version__ = "[^"]+"',
        f'__version__ = "{new_version}"',
    )
    _update(
        ROOT / "pyproject.toml",
        r'^version = "[^"]+"',
        f'version = "{new_version}"',
    )
    registry_script = """
import json
import sys

sys.path.insert(0, "src")
from topomarket.topology.config import (
    DEFAULT_CONFIG,
    PACKAGED_REGISTRY_PATH,
    SOURCE_REGISTRY_PATH,
)

payload = {"schema_version": 1, "default": DEFAULT_CONFIG.registry_entry()}
text = json.dumps(payload, indent=2, sort_keys=False) + "\\n"
for path in (SOURCE_REGISTRY_PATH, PACKAGED_REGISTRY_PATH):
    path.write_text(text, encoding="utf-8")
    print("wrote", path)
print("config_hash:", DEFAULT_CONFIG.config_hash())
"""
    result = subprocess.run(
        [str(PYTHON), "-c", registry_script], cwd=ROOT, capture_output=True, text=True
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    result = subprocess.run(
        [str(PYTHON), "scripts/build_showcase.py"], cwd=ROOT, capture_output=True, text=True
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    result = subprocess.run(
        [str(PYTHON), "scripts/build_presets.py"], cwd=ROOT, capture_output=True, text=True
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    result = subprocess.run(
        [str(PYTHON), "scripts/build_showcase.py", "--verify"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    print("version bumped to", new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
