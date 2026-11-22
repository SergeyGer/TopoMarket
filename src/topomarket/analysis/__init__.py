"""Reusable analysis helpers for TopoMarket.

The package owns the shared as-of window selection plus the two Step 5
analysis products: the robust industry cloud/PCA/persistence pipeline and the
correlation-distance Mapper graph.  The combined explorer payload helper keeps
CLI and future UI consumers on one public surface.
"""

from __future__ import annotations

from .alerts import *  # noqa: F401,F403 - alert policy API (Step 6)
from .alerts import __all__ as _ALERTS_ALL
from .evaluation import *  # noqa: F401,F403 - chronological evaluation API (Step 6)
from .evaluation import __all__ as _EVALUATION_ALL
from .industries import *  # noqa: F401,F403 - public industry analysis API
from .industries import __all__ as _INDUSTRIES_ALL
from .labels import *  # noqa: F401,F403 - labels/episodes API (Step 6)
from .labels import __all__ as _LABELS_ALL
from .ledger import *  # noqa: F401,F403 - append-only private ledger (Step 6)
from .ledger import __all__ as _LEDGER_ALL
from .mapper import *  # noqa: F401,F403 - public Mapper analysis API
from .mapper import __all__ as _MAPPER_ALL

__all__ = [
    *_ALERTS_ALL,
    *_EVALUATION_ALL,
    *_INDUSTRIES_ALL,
    *_LABELS_ALL,
    *_LEDGER_ALL,
    *_MAPPER_ALL,
]
