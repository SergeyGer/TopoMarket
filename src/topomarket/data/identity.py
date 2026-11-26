"""Resolve one stable snapshot identity for CLI evaluation and reporting (R3).

The evaluation CLI must attach the same non-empty identity whether it receives a
profile data directory (active snapshot pointer), a direct snapshot directory
(``refresh_manifest.json`` / ``import_manifest.json``) or a directory with only an
import manifest.  Conflicting identities fail visibly instead of silently
emitting an empty snapshot id.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .manifest import compute_snapshot_id, path_text
from .refresh import active_snapshot_id, resolve_active_data_dir

IMPORT_MANIFEST = "import_manifest.json"
REFRESH_MANIFEST = "refresh_manifest.json"


class SnapshotIdentityError(ValueError):
    """Raised when identity sources disagree or manifests are unreadable."""


def _read_json(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def resolve_snapshot_identity(data_dir: Path | str) -> dict[str, Any]:
    """Return ``{snapshot_id, source, manifest_digest, data_dir}`` for evaluation.

    Resolution order follows R3: active snapshot pointer, then the direct refresh
    manifest, then the import manifest and its content digest.  If two independent
    sources disagree the call raises :class:`SnapshotIdentityError`.
    """

    requested = Path(data_dir).expanduser()
    active = active_snapshot_id(requested)
    target = resolve_active_data_dir(requested)
    candidates: list[tuple[str, str]] = []
    manifest_digest: str | None = None

    refresh_manifest = _read_json(target / REFRESH_MANIFEST)
    if refresh_manifest is not None:
        recorded = refresh_manifest.get("snapshot_id")
        if isinstance(recorded, str) and recorded:
            candidates.append((recorded, "refresh_manifest"))
            if active is not None and recorded != active:
                raise SnapshotIdentityError(
                    "conflicting snapshot identities: active pointer "
                    f"{active!r} vs refresh manifest {recorded!r}"
                )
        manifest_digest = compute_snapshot_id(refresh_manifest)

    import_manifest = _read_json(target / IMPORT_MANIFEST)
    if import_manifest is not None:
        candidate = import_manifest.get("snapshot_id")
        if not isinstance(candidate, str) or not candidate:
            candidate = compute_snapshot_id(import_manifest)
        candidates.append((str(candidate), "import_manifest"))
        if manifest_digest is None:
            manifest_digest = compute_snapshot_id(import_manifest)

    if active is not None:
        candidates.append((active, "active_snapshot"))

    unique = {snapshot_id for snapshot_id, _source in candidates}
    if len(unique) > 1:
        raise SnapshotIdentityError(
            "conflicting snapshot identities: "
            + ", ".join(f"{snapshot_id!r} ({source})" for snapshot_id, source in candidates)
        )
    if candidates:
        snapshot_id, source = candidates[0]
    else:
        snapshot_id, source = "", "unavailable"
    return {
        "snapshot_id": snapshot_id,
        "source": source,
        "manifest_digest": manifest_digest,
        "data_dir": path_text(target),
    }


__all__ = ["SnapshotIdentityError", "resolve_snapshot_identity"]
