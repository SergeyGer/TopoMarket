"""Compatibility alias for :mod:`topomarket.data.synthetic`.

The synthetic generator lives in :mod:`topomarket.data.synthetic`; this module
re-exports its public API so callers that import
``topomarket.data.generator`` keep working.
"""

from __future__ import annotations

from .normalized import *  # noqa: E402,F401,F403
from .normalized import __all__ as _NORMALIZED_ALL  # noqa: E402
from .synthetic import *  # noqa: F401,F403
from .synthetic import __all__ as __all__

__all__ += [name for name in _NORMALIZED_ALL if name not in __all__]
