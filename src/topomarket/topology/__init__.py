"""Topology primitives used by TopoMarket.

The public surface combines the frozen configuration API with the causal-window
pipeline: robust median/MAD scaling, delay embedding, full Vietoris-Rips
persistence and the frozen per-window result.  Public callables intentionally do
not share names with submodules (for example, ``window_topology`` is a function
and the module is ``window``), so ordinary dotted imports cannot replace the
package-level API.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import *  # noqa: F401,F403 - public configuration API
from .config import __all__ as _CONFIG_ALL
from .embedding import *  # noqa: F401,F403 - public embedding API
from .embedding import __all__ as _EMBEDDING_ALL
from .errors import *  # noqa: F401,F403 - public error API
from .errors import __all__ as _ERROR_ALL
from .persistence import *  # noqa: F401,F403 - public persistence API
from .persistence import __all__ as _PERSISTENCE_ALL
from .scaling import *  # noqa: F401,F403 - public scaling API
from .scaling import __all__ as _SCALING_ALL
from .score import *  # noqa: F401,F403 - public daily score API
from .score import __all__ as _SCORE_ALL
from .window import *  # noqa: F401,F403 - public window API
from .window import __all__ as _WINDOW_ALL


@dataclass(frozen=True)
class Topology:
    """A small, immutable description of a market topology."""

    name: str
    nodes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Topology name must not be empty")

    @property
    def size(self) -> int:
        """Number of nodes in the topology."""

        return len(self.nodes)


__all__ = [
    *_CONFIG_ALL,
    *_ERROR_ALL,
    *_SCALING_ALL,
    *_EMBEDDING_ALL,
    *_PERSISTENCE_ALL,
    *_WINDOW_ALL,
    *_SCORE_ALL,
    "Topology",
]
