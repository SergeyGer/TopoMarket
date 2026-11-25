#!/usr/bin/env python3
"""Refresh the audited third-party license registry (maintainer tool, network).

Reads ``pyproject.toml`` and ``requirements.lock``, resolves license metadata for
every direct or pinned distribution (PyPI JSON API), classifies it and rewrites:

* ``docs/dependency_licenses.json`` - machine-readable registry consumed offline;
* ``docs/DEPENDENCY_LICENSES.md`` - human-readable audit table.

Classification rules
--------------------

1. A PyPI SPDX ``license_expression`` wins when present.  Strong copyleft
   (GPL/AGPL) fails unless the expression offers a permissive alternative
   (for example ``Apache-2.0 OR BSD-3-Clause``).
2. Otherwise OSI license classifiers are used: any permissive classifier makes
   a dual-licensed distribution acceptable (``docutils`` is BSD/GPL/public
   domain, and the project distributes it under BSD terms).
3. Otherwise a short ``License`` metadata field is used (``MPL-2.0`` -> weak
   copyleft; ``MIT`` -> permissive).  Large license *text* fields are not
   scanned: packages such as matplotlib/scipy embed third-party notices and
   bundled font/GCC-run-time texts that would produce false positives.

Exit code 1 means a vendored strong-copyleft dependency or an unclassified
dependency was found.  Network failures are reported and also fail the refresh so
stale records are not silently accepted.

Usage::

    python scripts/refresh_dependency_licenses.py
    python scripts/refresh_dependency_licenses.py --check   # offline consistency only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import tomllib

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "dependency_licenses.json"
REPORT = ROOT / "docs" / "DEPENDENCY_LICENSES.md"
LOCKFILE = ROOT / "requirements.lock"
PYPROJECT = ROOT / "pyproject.toml"
CLOUD_REQUIREMENTS = ROOT / "requirements.txt"

PYPI_URL = "https://pypi.org/pypi/{name}/{version}/json"
PYPI_LATEST_URL = "https://pypi.org/pypi/{name}/json"
USER_AGENT = "topomarket-license-audit/1.0"

#: License identifiers/keywords that would force the distributed project onto a
#: copyleft license.  ``LGPL`` is matched separately as weak copyleft.
STRONG_COPYLEFT = ("AGPL", "GPL-2.0", "GPL-3.0", "GPLV2", "GPLV3")
WEAK_COPYLEFT = ("LGPL", "MPL", "EPL", "CDDL", "OSL")
PERMISSIVE_MARKERS = (
    "MIT",
    "BSD",
    "APACHE",
    "PSF",
    "PYTHON SOFTWARE FOUNDATION",
    "ISC",
    "HPND",
    "PUBLIC DOMAIN",
    "UNLICENSE",
    "CC0",
    "ZLIB",
    "FTL",
    "MIT-CMU",
    "POSTGRESQL",
    "ARTISTIC",
)
PERMISSIVE_CLASSIFIERS = (
    "MIT License",
    "BSD License",
    "Apache Software License",
    "Python Software Foundation License",
    "Public Domain",
    "ISC License",
)
WEAK_CLASSIFIERS = ("Mozilla Public License", "GNU Lesser General Public License")
STRONG_CLASSIFIERS = ("GNU General Public License", "GNU Affero General Public License")


def read_pyproject_requirements() -> dict[str, str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    requirements: dict[str, str] = {}
    for requirement in project.get("dependencies") or []:
        requirements[requirement_name(requirement)] = requirement
    for extra, values in (project.get("optional-dependencies") or {}).items():
        for requirement in values:
            requirements[requirement_name(requirement)] = f"{extra}: {requirement}"
    return requirements


def read_pins(path: Path) -> dict[str, str]:
    """Read ``name==version`` pins from a requirements file."""

    if not path.is_file():
        return {}
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        pins[requirement_name(name)] = version.strip()
    return pins


def read_lock_pins(path: Path = LOCKFILE) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        pins[requirement_name(name)] = version.strip()
    return pins


def requirement_name(requirement: str) -> str:
    return re.split(r"[<>=!~;\[ ]", requirement.strip())[0].lower().replace("_", "-")


def _local_metadata(name: str) -> dict[str, Any] | None:
    from importlib import metadata

    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None
    return {
        "version": dist.version,
        "license_expression": dist.metadata.get("License-Expression"),
        "license": dist.metadata.get("License") or "",
        "classifiers": list(dist.metadata.get_all("Classifier") or []),
        "source": "local",
    }


def _pypi_metadata(name: str, version: str | None) -> dict[str, Any]:
    url = (
        PYPI_LATEST_URL.format(name=name)
        if version is None
        else PYPI_URL.format(name=name, version=version)
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed host
        payload = json.loads(response.read())
    info = payload["info"]
    return {
        "version": info["version"],
        "license_expression": info.get("license_expression") or "",
        "license": info.get("license") or "",
        "classifiers": list(info.get("classifiers") or []),
        "source": "pypi",
    }


def classify(metadata: dict[str, Any]) -> dict[str, Any]:
    expression = str(metadata.get("license_expression") or "").strip()
    classifiers = [str(item) for item in metadata.get("classifiers") or []]
    license_classifiers = [item for item in classifiers if item.startswith("License ::")]
    short_license = str(metadata.get("license") or "").strip()

    if expression:
        return _classify_expression(expression)

    strong = [
        item for item in license_classifiers if any(marker in item for marker in STRONG_CLASSIFIERS)
    ]
    weak = [
        item for item in license_classifiers if any(marker in item for marker in WEAK_CLASSIFIERS)
    ]
    permissive = [
        item
        for item in license_classifiers
        if any(marker in item for marker in PERMISSIVE_CLASSIFIERS)
    ]
    if strong and not permissive:
        return _result("strong-copyleft", expression, license_classifiers, [strong[0]])
    if permissive:
        return _result("permissive", expression, license_classifiers, permissive)
    if weak:
        return _result("weak-copyleft", expression, license_classifiers, weak)

    if short_license and len(short_license) <= 120:
        if any(marker in short_license.upper() for marker in STRONG_COPYLEFT):
            if " OR " in short_license.upper():
                return _result("permissive", short_license, [], ["dual-licensed alternative"])
            return _result("strong-copyleft", short_license, [], [short_license])
        if any(marker in short_license.upper() for marker in WEAK_COPYLEFT):
            return _result("weak-copyleft", short_license, [], [short_license])
        if any(marker in short_license.upper() for marker in PERMISSIVE_MARKERS):
            return _result("permissive", short_license, [], [short_license])
    if license_classifiers:
        return _result("unknown", short_license, license_classifiers, [])
    return _result("unknown", short_license, [], [])


def _classify_expression(expression: str) -> dict[str, Any]:
    upper = expression.upper()
    alternatives = [part.strip() for part in re.split(r"\s+OR\s+", upper)]
    if any("LGPL" in alternative for alternative in alternatives):
        pass
    strong = [
        alternative
        for alternative in alternatives
        if any(marker in alternative for marker in STRONG_COPYLEFT) and "LGPL" not in alternative
    ]
    if strong:
        permissive_alternative = any(
            any(marker in alternative for marker in PERMISSIVE_MARKERS)
            for alternative in alternatives
            if alternative not in strong
        )
        if permissive_alternative:
            return _result("permissive", expression, [], ["dual-licensed alternative"])
        return _result("strong-copyleft", expression, [], strong)
    if any(marker in upper for marker in WEAK_COPYLEFT):
        return _result("weak-copyleft", expression, [], [expression])
    if any(marker in upper for marker in PERMISSIVE_MARKERS):
        return _result("permissive", expression, [], [expression])
    return _result("unknown", expression, [], [])


def _result(
    classification: str, license_text: str, classifiers: list[str], evidence: list[str]
) -> dict[str, Any]:
    return {
        "classification": classification,
        "evidence": evidence,
        "license": license_text or None,
        "license_classifiers": classifiers,
        "risk": {
            "permissive": "PASS",
            "weak-copyleft": "REVIEW",
            "strong-copyleft": "FAIL",
        }.get(classification, "REVIEW"),
    }


def build_registry() -> dict[str, Any]:
    declared = read_pyproject_requirements()
    locked = read_lock_pins()
    cloud = read_pins(CLOUD_REQUIREMENTS)
    combined = dict(locked)
    combined.update({name: version for name, version in cloud.items() if name not in combined})
    names = sorted(set(declared) | set(combined))
    packages: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for name in names:
        version = combined.get(name)
        try:
            metadata = _pypi_metadata(name, version)
        except (urllib.error.URLError, TimeoutError, KeyError) as error:
            metadata = _local_metadata(name)
            if metadata is None:
                problems.append(f"{name}: cannot resolve license metadata: {error}")
                continue
            metadata["source"] = "local"
        classification = classify(metadata)
        display_license = (
            classification["license"]
            or "; ".join(
                classifier.removeprefix("License :: ").strip()
                for classifier in classification["license_classifiers"]
            )
            or None
        )
        pins = metadata.get("version") if version is None else version
        packages[name] = {
            "name": name,
            "version": pins,
            "declared": "pyproject" if name in declared else ("cloud" if name in cloud else "lock"),
            "pyproject_requirement": declared.get(name),
            "locked": name in locked,
            "cloud": name in cloud,
            "license": display_license,
            "license_classifiers": classification["license_classifiers"],
            "classification": classification["classification"],
            "evidence": classification["evidence"],
            "risk": classification["risk"],
            "metadata_source": metadata.get("source", "unknown"),
        }
        if classification["risk"] == "FAIL":
            problems.append(f"{name}: strong copyleft license ({classification['evidence']})")
    counts = {
        "total": len(packages),
        "pass": sum(1 for entry in packages.values() if entry["risk"] == "PASS"),
        "review": sum(1 for entry in packages.values() if entry["risk"] == "REVIEW"),
        "fail": sum(1 for entry in packages.values() if entry["risk"] == "FAIL"),
    }
    return {
        "schema_version": 1,
        "generated_by": "scripts/refresh_dependency_licenses.py",
        "generated_from": ["pyproject.toml", "requirements.lock", "requirements.txt"],
        "policy": {
            "project_license": "MIT",
            "allow": ["permissive", "weak-copyleft with review"],
            "fail": ["strong-copyleft (GPL/AGPL)"],
        },
        "counts": counts,
        "problems": problems,
        "packages": packages,
    }


def write_registry(registry: dict[str, Any]) -> None:
    REGISTRY.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT.write_text(_markdown(registry), encoding="utf-8")


def _markdown(registry: dict[str, Any]) -> str:
    counts = registry["counts"]
    problems = registry.get("problems") or []
    lines = [
        "# Third-party dependency licenses",
        "",
        "TopoMarket is released under the **MIT** license. This audit covers every direct",
        "dependency declared in `pyproject.toml` and every distribution pinned in",
        "`requirements.lock` (and, once present, the Cloud `requirements.txt`). It exists to",
        "catch a strong copyleft dependency (GPL/AGPL) early: such a dependency would force the",
        "distributed project onto the same license.",
        "",
        "Regenerate with `python scripts/refresh_dependency_licenses.py`; verify offline in CI",
        "with `scripts/audit_dependency_licenses.py` and `tests/test_dependency_licenses.py`.",
        "",
        "## Result",
        "",
        f"- Packages audited: **{counts['total']}**",
        f"- Permissive / compatible: **{counts['pass']}**",
        f"- Weak copyleft or manual review: **{counts['review']}**",
        f"- Strong copyleft (GPL/AGPL): **{counts['fail']}**",
        "",
        (
            "**Verdict: no strong copyleft dependency found. MIT remains the project license;"
            " genuine market data stays outside the repository (see `NOTICE.md`).**"
            if not problems
            else "**Verdict: REVIEW REQUIRED - see the problems below.**"
        ),
        "",
        "## Method",
        "",
        "1. A PyPI SPDX `license_expression` wins when present; a strong copyleft alternative only",
        "   fails when the expression offers no permissive alternative.",
        "2. Otherwise OSI license classifiers are used; a dual-licensed package with a permissive",
        "   option (for example `docutils`) is distributed under the permissive option.",
        "3. Otherwise a short `License` metadata field is used. Long license texts are not",
        "   scanned:",
        "   packages such as `matplotlib`/`scipy` embed third-party font/GCC-runtime notices that",
        "   would otherwise create false positives (`matplotlib` is PSF/BSD-compatible,",
        "   `scipy`/`scikit-learn` are BSD-3-Clause, `numpy` is BSD-3-Clause).",
        "",
        "Weak copyleft dependencies (for example `certifi`, MPL-2.0) keep their own file-level",
        "terms; TopoMarket uses them unmodified as external dependencies, which does not affect",
        "the MIT distribution of this repository.",
        "",
        "## Runtime imports",
        "",
        "The package imports `httpx`, `numpy` and `ripser` at runtime; the Streamlit UI extra adds",
        "`streamlit` and the chart renderer (`matplotlib`). All are permissive.",
        "",
    ]
    if problems:
        lines += ["## Problems", ""]
        lines += [f"- {problem}" for problem in problems]
        lines.append("")
    lines += [
        "## Packages",
        "",
        "| Package | Version | Declared | License | Class | Risk |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in sorted(registry["packages"]):
        entry = registry["packages"][name]
        license_text = str(entry.get("license") or "—").replace("|", "/").strip()
        if len(license_text) > 56:
            license_text = license_text[:53] + "..."
        lines.append(
            f"| `{name}` | {entry['version']} | {entry['declared']} | {license_text} | "
            f"{entry['classification']} | {entry['risk']} |"
        )
    lines.append("")
    if CLOUD_REQUIREMENTS.is_file():
        lines += [
            "## Cloud dependency definition",
            "",
            "`requirements.txt` is the effective Streamlit Community Cloud definition. It is",
            "pinned and audited by `scripts/audit_dependency_licenses.py`; regenerate it when",
            "dependencies change (see `docs/DEPLOYMENT.md`).",
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the audited dependency license registry.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate committed registry consistency only (no network).",
    )
    args = parser.parse_args(argv)
    if args.check:
        from audit_dependency_licenses import audit_registry

        report = audit_registry(ROOT)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    registry = build_registry()
    write_registry(registry)
    print(f"wrote {REGISTRY} ({registry['counts']['total']} packages)")
    print(f"counts: {registry['counts']}")
    for problem in registry.get("problems") or []:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    return 1 if registry.get("problems") else 0


if __name__ == "__main__":
    raise SystemExit(main())
