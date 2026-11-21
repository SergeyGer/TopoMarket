"""Compatibility alias for :mod:`topomarket.data.normalize`."""

from __future__ import annotations

from .normalize import *  # noqa: F401,F403
from .normalize import __all__ as __all__
from .normalized import *  # noqa: E402,F401,F403
from .normalized import __all__ as _NORMALIZED_ALL

__all__ += [name for name in _NORMALIZED_ALL if name not in __all__]
