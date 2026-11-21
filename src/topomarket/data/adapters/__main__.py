"""Run the seed-file adapter CLI with ``python -m topomarket.data.adapters``."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main(sys.argv[1:]))
