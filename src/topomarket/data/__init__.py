"""Data access helpers for the TopoMarket demo profile.

Only synthetic, repository-safe sample data belongs in this package. Private
research inputs are expected to live outside the repository (by default under
``private_data/``) and are never packaged or committed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEMO_DATA_FILE = Path(__file__).with_name("demo_markets.json")


def load_demo_markets(path: Path | None = None) -> list[dict[str, Any]]:
    """Return the bundled synthetic demo markets.

    ``path`` may point to alternative JSON data with the same shape, which is
    useful for tests and for local experiments.
    """

    source = Path(path) if path is not None else DEMO_DATA_FILE
    with source.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    markets = payload.get("markets", [])
    if not isinstance(markets, list):
        raise ValueError(f"Expected a list of markets in {source}")
    return markets


__all__ = ["DEMO_DATA_FILE", "load_demo_markets"]
