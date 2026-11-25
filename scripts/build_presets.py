#!/usr/bin/env python3
"""Freeze the demonstration presets for the public synthetic showcase (UI01, VD02).

The four Structure presets are derived deterministically from the committed
``showcase/`` fixture and then frozen into ``showcase/presets.json`` with verified
dates, a fixture id and a ``teaching`` flag where a labelled teaching example is
used instead of an evaluation-matched alert.  The file hash is added to
``showcase/manifest.json`` so ``scripts/build_showcase.py --verify`` covers it.

Run after rebuilding the showcase:

    python scripts/build_showcase.py
    python scripts/build_presets.py
    python scripts/build_showcase.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from topomarket.ui.panels import load_dashboard_data  # noqa: E402
from topomarket.ui.presets import FROZEN_PRESETS_FILENAME, derive_presets  # noqa: E402

SHOWCASE = ROOT / "showcase"


def build(out: Path = SHOWCASE) -> dict:
    """Derive and freeze the presets, then register the file hash in the manifest."""

    data = load_dashboard_data("demo")
    if Path(data.data_dir).resolve() != out.resolve():
        raise SystemExit(
            f"expected the default demo profile to load {out}, got {data.data_dir}; "
            "run from a repository checkout with the committed showcase"
        )
    presets = derive_presets(data)
    records = [preset.as_dict() for preset in presets]
    for record in records:
        if record["verified"]:
            assert record["date"] in data.session_dates
            assert data.session_dates.index(record["date"]) >= 60
        else:
            assert record["reason"]
    payload = {
        "schema_version": 1,
        "fixture_id": data.snapshot_id,
        "synthetic": True,
        "private_data": False,
        "generated_by": "scripts/build_presets.py",
        "calendar_sessions": len(data.session_dates),
        "presets": records,
    }
    target = out / FROZEN_PRESETS_FILENAME
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = dict(manifest.get("hashes") or {})
    hashes[FROZEN_PRESETS_FILENAME] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest["hashes"] = hashes
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze the showcase demonstration presets.")
    parser.add_argument("--out", type=Path, default=SHOWCASE)
    args = parser.parse_args(argv)
    payload = build(args.out)
    for record in payload["presets"]:
        marker = "teaching" if record.get("teaching") else "evaluation"
        print(f"{record['preset_id']:18s} {record['date'] or 'unavailable':12s} {marker}")
    print(f"froze {len(payload['presets'])} presets in {args.out / FROZEN_PRESETS_FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
