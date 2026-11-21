"""Tests for the small topology and evaluation primitives."""

from __future__ import annotations

import pytest

from topomarket.evaluation import mean
from topomarket.topology import Topology


def test_topology_exposes_name_nodes_and_size() -> None:
    topology = Topology(name="ring", nodes=("a", "b", "c"))

    assert topology.name == "ring"
    assert topology.nodes == ("a", "b", "c")
    assert topology.size == 3


def test_topology_defaults_to_no_nodes() -> None:
    assert Topology(name="empty").nodes == ()
    assert Topology(name="empty").size == 0


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_topology_rejects_blank_names(name: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Topology(name=name)


def test_topology_is_immutable_and_hashable() -> None:
    topology = Topology(name="star", nodes=("hub", "leaf"))

    with pytest.raises(AttributeError):
        topology.name = "mesh"  # type: ignore[misc]

    assert hash(topology) == hash(Topology(name="star", nodes=("hub", "leaf")))


def test_mean_accepts_sequences() -> None:
    assert mean([1, 2, 3]) == 2
    assert mean((0.5, 1.5)) == 1.0
    assert mean([2.5]) == 2.5


def test_mean_rejects_empty_sequences() -> None:
    with pytest.raises(ValueError, match="at least one value"):
        mean([])
    with pytest.raises(ValueError, match="at least one value"):
        mean(())
