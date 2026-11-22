"""Reusable analysis helpers for TopoMarket.

The industry module owns the shared as-of window selection and the robust
industry cloud/PCA/persistence pipeline.  Keeping the public imports here lets
CLI, UI and Mapper code depend on ``topomarket.analysis`` without importing the
module's internals.
"""

from __future__ import annotations

from .industries import *  # noqa: F401,F403 - public industry analysis API
from .industries import __all__ as _INDUSTRIES_ALL

__all__ = [*_INDUSTRIES_ALL]
