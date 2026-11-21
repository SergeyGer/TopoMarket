"""Run the local data adapters with ``python -m topomarket.data``."""

from __future__ import annotations

import sys

from .adapters.cli import main

if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main(sys.argv[1:]))
