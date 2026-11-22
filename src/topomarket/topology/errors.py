"""Error types for the topology primitives.

Keeping the errors in one module makes it possible for callers to catch the
whole topology family (:class:`TopologyError`) while still distinguishing
scaling, embedding, persistence and window failures when they need to.
"""

from __future__ import annotations


class TopologyError(ValueError):
    """Base class for invalid topology inputs or computations."""


class ScalingError(TopologyError):
    """Raised when a window cannot be robustly scaled."""


class ZeroScaleError(ScalingError):
    """Raised when the median absolute deviation of a window is zero."""


class NonFiniteScaleError(ScalingError):
    """Raised when a window has a non-finite location or scale."""


class EmbeddingError(TopologyError):
    """Raised when delay-embedding arguments or inputs are invalid."""


class PersistenceError(TopologyError):
    """Raised when a Vietoris-Rips persistence computation fails."""


class WindowError(TopologyError):
    """Raised for a malformed window request."""


class InvalidWindowError(WindowError):
    """Raised when a window cannot be interpreted at all (not just unavailable)."""


# Friendly aliases used by callers/tests.
ScaleError = ScalingError
InvalidScaleError = ScalingError
EmbeddingArgumentError = EmbeddingError
DelayEmbeddingError = EmbeddingError
PersistenceComputationError = PersistenceError
RipserError = PersistenceError
TopologyWindowError = WindowError
WindowTopologyError = WindowError
WindowUnavailableError = WindowError
UnavailableWindowError = WindowError
InvalidEmbeddingError = EmbeddingError


__all__ = [
    "DelayEmbeddingError",
    "EmbeddingArgumentError",
    "EmbeddingError",
    "InvalidEmbeddingError",
    "InvalidScaleError",
    "InvalidWindowError",
    "NonFiniteScaleError",
    "PersistenceComputationError",
    "PersistenceError",
    "RipserError",
    "ScaleError",
    "ScalingError",
    "TopologyError",
    "TopologyWindowError",
    "UnavailableWindowError",
    "WindowError",
    "WindowTopologyError",
    "WindowUnavailableError",
    "ZeroScaleError",
]
