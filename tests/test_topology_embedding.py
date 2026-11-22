"""Focused tests for causal scaling, delay embedding and window persistence."""

from __future__ import annotations

import dataclasses
import importlib

import numpy as np
import pytest
from ripser import ripser as reference_ripser

from topomarket.topology import (
    DEFAULT_CONFIG,
    Diagrams,
    EmbeddingError,
    Lifetimes,
    NonFiniteScaleError,
    PersistenceError,
    ScalingError,
    TopologyConfig,
    WindowTopologyResult,
    ZeroScaleError,
    causal_window,
    delay_embedding,
    finite_lifetimes,
    h1_lifetimes,
    persistence_diagrams,
    persistence_score,
    robust_scale,
    total_persistence,
    window_topology,
)

persistence_module = importlib.import_module("topomarket.topology.persistence")


def test_robust_scale_uses_median_and_mad() -> None:
    values = np.array([1.0, 2.0, 3.0, 4.0, 100.0])
    scaled = robust_scale(values)

    median = np.median(values)
    mad = np.median(np.abs(values - median))
    expected = (values - median) / (1.4826 * mad)

    np.testing.assert_allclose(scaled, expected)
    assert scaled.median == pytest.approx(median)
    assert scaled.mad == pytest.approx(mad)
    assert scaled.scale == pytest.approx(1.4826 * mad)
    assert np.median(scaled) == pytest.approx(0.0)


def test_zero_scale_is_rejected() -> None:
    with pytest.raises(ZeroScaleError):
        robust_scale([5.0, 5.0, 5.0])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_scale_is_rejected(value: float) -> None:
    with pytest.raises(NonFiniteScaleError):
        robust_scale([1.0, value, 2.0])


def test_scaling_errors_are_value_errors() -> None:
    assert issubclass(ScalingError, ValueError)
    assert issubclass(ZeroScaleError, ScalingError)
    assert issubclass(NonFiniteScaleError, ScalingError)


def test_robust_scale_axis_one_broadcasts_per_row() -> None:
    values = np.array(
        [
            [1.0, 2.0, 3.0, 4.0, 100.0],
            [10.0, 11.0, 12.0, 13.0, 14.0],
        ]
    )
    original = values.copy()

    scaled = robust_scale(values, axis=1)

    medians = np.median(values, axis=1)
    mads = np.median(np.abs(values - medians[:, None]), axis=1)
    expected = (values - medians[:, None]) / (1.4826 * mads[:, None])

    assert scaled.shape == values.shape
    np.testing.assert_allclose(scaled, expected)
    np.testing.assert_allclose(scaled.median, medians)
    np.testing.assert_allclose(scaled.mad, mads)
    np.testing.assert_array_equal(values, original)


def test_default_embedding_shape_and_exact_coordinate_order() -> None:
    values = np.arange(60, dtype=float)
    embedded = delay_embedding(values)

    assert embedded.shape == (56, 3)
    np.testing.assert_array_equal(embedded[0], np.array([0.0, 2.0, 4.0]))
    np.testing.assert_array_equal(embedded[1], np.array([1.0, 3.0, 5.0]))
    np.testing.assert_array_equal(embedded[-1], np.array([55.0, 57.0, 59.0]))


def test_embedding_accepts_config_and_explicit_arguments() -> None:
    values = np.arange(20, dtype=float)

    from_config = delay_embedding(values, TopologyConfig(embedding_dimension=2, lag=3))
    explicit = delay_embedding(values, dimension=2, lag=3)
    keyword = delay_embedding(values, embedding_dimension=2, lag=3)

    assert from_config.shape == explicit.shape == keyword.shape == (17, 2)
    np.testing.assert_allclose(from_config, explicit)
    np.testing.assert_allclose(from_config, keyword)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dimension": 1, "lag": 2},
        {"dimension": 2.5, "lag": 2},
        {"dimension": True, "lag": 2},
        {"dimension": 3, "lag": 0},
        {"dimension": 3, "lag": -1},
        {"dimension": 3, "lag": 1.5},
    ],
)
def test_embedding_argument_validation(kwargs: dict[str, object]) -> None:
    with pytest.raises(EmbeddingError):
        delay_embedding(np.arange(20, dtype=float), **kwargs)


def test_embedding_rejects_short_or_non_finite_windows() -> None:
    with pytest.raises(EmbeddingError):
        delay_embedding([1.0, 2.0, 3.0], dimension=3, lag=2)
    with pytest.raises(EmbeddingError):
        delay_embedding([1.0, np.nan, 3.0, 4.0, 5.0], dimension=3, lag=2)
    with pytest.raises(EmbeddingError):
        delay_embedding([[1.0, 2.0], [3.0, 4.0]], dimension=2, lag=1)


def test_window_result_is_a_frozen_dataclass_with_expected_fields() -> None:
    result = window_topology(np.linspace(-1.0, 1.0, 60))

    assert dataclasses.is_dataclass(result)
    assert result.__dataclass_params__.frozen is True
    assert set(result.to_dict()) == {
        "available",
        "reason",
        "points",
        "diagrams",
        "lifetimes",
        "L",
    }
    assert isinstance(result, WindowTopologyResult)
    assert result.available is True
    assert result.reason is None
    assert result.points.shape == (56, 3)
    assert isinstance(result.diagrams, Diagrams)
    assert isinstance(result.lifetimes, Lifetimes)
    assert isinstance(result.L, float)


def test_window_topology_uses_configured_ripser_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_ripser(points: object, **kwargs: object) -> dict[str, object]:
        captured["points"] = points
        captured.update(kwargs)
        return {
            "dgms": [
                np.array([[0.0, 1.0], [0.0, np.inf]]),
                np.array([[1.0, 1.5]]),
            ]
        }

    monkeypatch.setattr(persistence_module, "ripser", fake_ripser)

    result = window_topology(np.linspace(-1.0, 1.0, 60))

    assert result.available is True
    assert captured["maxdim"] == DEFAULT_CONFIG.max_homology_dimension
    assert captured["coeff"] == DEFAULT_CONFIG.homology_coeff_field
    assert captured["metric"] == "euclidean"
    assert captured["thresh"] == np.inf


@pytest.mark.parametrize(
    "values",
    [
        [1.0] * 10,
        [1.0] * 60,
        [float("nan")] * 60,
        [float("inf")] * 60,
    ],
)
def test_invalid_windows_are_unavailable_with_a_reason(values: list[float]) -> None:
    result = window_topology(values)

    assert result.available is False
    assert isinstance(result.reason, str) and result.reason
    assert result.L == 0.0


def _square_points() -> np.ndarray:
    return np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [1.0, 1.0],
            [0.0, 1.0],
        ]
    )


def test_square_diagrams_and_lifetimes_match_ripser_directly() -> None:
    points = _square_points()
    expected = reference_ripser(points, maxdim=1, coeff=2, metric="euclidean")["dgms"]

    result = window_topology(points, DEFAULT_CONFIG)

    assert result.available is True
    assert len(result.diagrams) == 2
    np.testing.assert_allclose(result.diagrams[0], expected[0])
    np.testing.assert_allclose(result.diagrams[1], expected[1])

    expected_lifetimes = finite_lifetimes(expected[1], DEFAULT_CONFIG.min_interval)
    np.testing.assert_allclose(np.asarray(result.lifetimes), expected_lifetimes)
    np.testing.assert_allclose(result.lifetimes[1], expected_lifetimes)
    assert result.L == pytest.approx(float(np.sum(expected_lifetimes)))


def test_l_zero_when_no_finite_h1_pair_exists() -> None:
    collinear = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])

    result = window_topology(collinear, DEFAULT_CONFIG)

    assert result.available is True
    assert result.diagrams[1].size == 0
    assert result.L == 0.0
    assert result.h1_count == 0


def test_infinite_deaths_and_small_lifetimes_are_excluded() -> None:
    diagram = np.array(
        [
            [0.0, 1.0],  # finite, above threshold
            [0.0, np.inf],  # infinite death
            [2.0, 2.0],  # zero lifetime
            [1.0, 1.0 + 1e-12],  # below the threshold
            [3.0, 4.0],  # finite, above threshold
        ]
    )

    values = finite_lifetimes(diagram, 1e-8)

    np.testing.assert_allclose(np.sort(values), np.array([1.0, 1.0]))
    assert total_persistence(diagram, 1e-8) == pytest.approx(2.0)


def test_lifetime_exactly_at_threshold_is_excluded() -> None:
    diagram = np.array(
        [
            [0.0, 1e-8],  # exactly at the threshold: excluded
            [0.0, 1e-8 + 1e-12],  # just above: retained
            [0.0, 1e-8 - 1e-12],  # just below: excluded
        ]
    )

    values = finite_lifetimes(diagram, 1e-8)

    assert values.size == 1
    assert values[0] == pytest.approx(1e-8 + 1e-12)
    assert total_persistence(diagram, 1e-8) == pytest.approx(1e-8 + 1e-12)


def test_square_lifetime_at_or_below_threshold_is_excluded() -> None:
    result = window_topology(
        _square_points(),
        TopologyConfig(min_interval=1.0),
    )

    assert result.diagrams[1].shape == (1, 2)
    assert result.L == 0.0


def test_persistence_defaults_to_frozen_maxdim_and_coefficient() -> None:
    points = _square_points()

    diagrams = persistence_diagrams(points)

    assert len(diagrams) == DEFAULT_CONFIG.max_homology_dimension + 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"thresh": 0.5},
        {"thresh": 0.0},
        {"thresh": float("nan")},
        {"n_perm": 3},
        {"n_perm": None},
    ],
)
def test_persistence_rejects_truncated_or_subsampled_filtrations(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(PersistenceError):
        persistence_diagrams(_square_points(), **kwargs)


@pytest.mark.parametrize(
    "entry_point",
    [
        persistence_module.ripser,
        persistence_module.vietoris_rips,
    ],
)
@pytest.mark.parametrize(
    "kwargs",
    [
        {"thresh": 0.5},
        {"thresh": float("nan")},
        {"n_perm": 3},
        {"n_perm": None},
    ],
)
def test_raw_persistence_entry_points_cannot_truncate_or_subsample(
    entry_point: object, kwargs: dict[str, object]
) -> None:
    with pytest.raises(PersistenceError):
        entry_point(_square_points(), **kwargs)  # type: ignore[operator]


def test_persistence_always_requests_the_complete_filtration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_ripser(points: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"dgms": [np.empty((0, 2)), np.empty((0, 2))]}

    monkeypatch.setattr(persistence_module, "ripser", fake_ripser)

    persistence_diagrams(_square_points())

    assert captured["thresh"] == np.inf
    assert "n_perm" not in captured


def test_persistence_score_square_sums_finite_h1_lifetimes() -> None:
    diagrams = persistence_diagrams(_square_points())
    expected = finite_lifetimes(diagrams[1], DEFAULT_CONFIG.min_interval)

    score = persistence_score(diagrams)

    assert np.asarray(expected).size == 1
    assert score > 0.0
    assert score == pytest.approx(float(np.sum(expected)))
    assert total_persistence(h1_lifetimes(diagrams)) == pytest.approx(score)


def test_persistence_score_is_zero_without_finite_h1() -> None:
    collinear = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])

    diagrams = persistence_diagrams(collinear)

    assert h1_lifetimes(diagrams).size == 0
    assert persistence_score(diagrams) == 0.0


def test_result_arrays_are_read_only_and_caller_points_are_not_modified() -> None:
    points = _square_points()

    result = window_topology(points, DEFAULT_CONFIG)

    assert result.points is not points
    assert points.flags.writeable is True
    assert result.points.flags.writeable is False
    assert result.diagrams[1].flags.writeable is False
    assert result.lifetimes[1].flags.writeable is False
    with pytest.raises(ValueError):
        result.diagrams[1][0, 0] = 99.0
    with pytest.raises(ValueError):
        result.lifetimes[1][0] = 99.0


@pytest.mark.parametrize("entry_point", [window_topology, causal_window])
def test_old_non_finite_observation_outside_trailing_window_is_ignored(entry_point: object) -> None:
    values = np.linspace(-1.0, 1.0, 61)
    values[0] = np.nan

    result = entry_point(values)  # type: ignore[operator]

    assert result.available is True
    assert result.points.shape == (56, 3)
    assert np.all(np.isfinite(result.points))


def test_package_api_survives_ordinary_module_imports() -> None:
    import topomarket.topology as topology

    importlib.import_module("topomarket.topology.window")
    assert callable(topology.window_topology)
    assert callable(topology.causal_window)

    importlib.import_module("topomarket.topology.persistence")
    assert callable(topology.persistence_diagrams)
    assert callable(topology.persistence_score)
    assert not callable(getattr(topology, "persistence", None))

    importlib.import_module("topomarket.topology.embedding")
    assert callable(topology.delay_embedding)
    assert not callable(getattr(topology, "embedding", None))

    importlib.import_module("topomarket.topology.scaling")
    assert callable(topology.robust_scale)
