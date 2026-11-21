"""Minimal topology primitives used by TopoMarket examples."""

from __future__ import annotations

from dataclasses import dataclass, field


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


__all__ = ["Topology"]
