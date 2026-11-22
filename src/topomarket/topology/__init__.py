"""Minimal topology primitives used by TopoMarket examples.

The configuration API is frozen so every topology result can be traced back to
the exact parameters and package version that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import *  # noqa: F401,F403 - public configuration API
from .config import __all__ as _CONFIG_ALL


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


__all__ = [*_CONFIG_ALL, "Topology"]
