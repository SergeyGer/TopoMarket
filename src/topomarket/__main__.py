"""Allow ``python -m topomarket`` to run the command-line interface."""

from __future__ import annotations

from topomarket.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
