"""Compatibility alias for :mod:`topomarket.data.synthetic`.

The synthetic generator lives in :mod:`topomarket.data.synthetic`; this module
re-exports its public API so callers that import
``topomarket.data.generator`` keep working.
"""

from __future__ import annotations

from .synthetic import *  # noqa: F401,F403
from .synthetic import __all__ as __all__
