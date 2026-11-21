#!/usr/bin/env python3
"""Repository entry point for TopoMarket.

This wrapper keeps ``python app.py ...`` working from a fresh checkout
without requiring the package to be installed first. Installed users can
use the ``topomarket`` console script instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from topomarket.cli import main  # noqa: E402  (path is configured above)

if __name__ == "__main__":
    raise SystemExit(main())
