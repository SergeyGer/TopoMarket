"""Focused tests for the reusable industry window and cloud analysis."""

from __future__ import annotations

import importlib
import json
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from topomarket.analysis import (
    INDUSTRY_COLUMNS,
    INDUSTRY_LABELS,
    PCA_LABELS,
    WINDOW_SESSIONS,
    IndustryAnalysisError,
    IndustryCloud,
    IndustryWindow,
    build_industry_cloud,
    select_industry_window,
)
from topomarket.data.schemas import (
    INDUSTRIES_DAILY_COLUMNS,
    INDUSTRY_NAMES,
    industry_return_column,
)
from topomarket.topology import (
    DEFAULT_CONFIG,
    Diagrams,
    Lifetimes,
    finite_lifetimes,
    robust_scale,
)

industry_module = importlib.import_module("topomarket.analysis.industries")
persistence_module = importlib.import_module("topomarket.topology.persistence")


def _rows(count: int = 80) -> list[dict[str, object]]:
    """Return deterministic, non-constant industry observations."""

    start = date(2024, 1, 2)
    rows: list[dict[str, object]] = []
    for index in range(count):
        row: dict[str, object] = {
            "date": (start + timedelta(days=index)).isoformat(),
            "vix_close": 12.0 + index / 7.0,
        }
        for column_index, column in enumerate(INDUSTRY_COLUMNS):
            row[column] = (
                0.01 * np.sin(index / 5.0 + column_index)
                + 0.002 * ((index + 2 * column_index) % 7)
                + 0.0001 * column_index
            )
        rows.append(row)
    return rows


def _as_of(rows: list[dict[str, object]], index: int = -1) -> str:
    return str(rows[index]["date"])


def test_canonical_columns_match_the_industries_daily_contract() -> None:
    assert INDUSTRY_COLUMNS == tuple(
        column for column in INDUSTRIES_DAILY_COLUMNS if column != "date"
    )
    assert INDUSTRY_COLUMNS == tuple(industry_return_column(name) for name in INDUSTRY_NAMES)
    assert INDUSTRY_LABELS == INDUSTRY_NAMES  # twelve human-readable labels


def test_as_of_window_selects_trailing_sixty_rows_in_ascending_iso_order() -> None:
    rows = _rows(80)
    as_of = _as_of(rows, 69)
    window = select_industry_window(rows, as_of=as_of)

    assert isinstance(window, IndustryWindow)
    assert window.columns == INDUSTRY_COLUMNS
    assert window.window_sessions == WINDOW_SESSIONS == 60
    assert window.shape == (60, 12)
    assert window.dates == tuple(str(row["date"]) for row in rows[10:70])
    assert list(window.dates) == sorted(window.dates)
    assert window.dates[-1] == as_of
    assert window.as_of == as_of
    for value in window.dates:
        assert datetime.strptime(value, "%Y-%m-%d").date().isoformat() == value

    expected = np.array(
        [[float(row[column]) for column in INDUSTRY_COLUMNS] for row in rows[10:70]]
    )
    np.testing.assert_allclose(window.values, expected)
    assert "vix_close" in rows[0]  # unrelated row fields are permitted


def test_selection_is_order_independent_and_defaults_to_the_latest_date() -> None:
    rows = _rows(75)
    ascending = select_industry_window(rows, as_of=rows[64]["date"])
    descending = select_industry_window(list(reversed(rows)), as_of=rows[64]["date"])
    latest = select_industry_window(rows)

    assert ascending == descending
    assert latest.as_of == _as_of(rows)
    assert latest.dates == tuple(str(row["date"]) for row in rows[-60:])


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda rows: [row.pop(INDUSTRY_COLUMNS[0]) for row in rows],
            "missing industry column",
        ),
        (
            lambda rows: [row.update({"ind_mystery_return": 0.0}) for row in rows],
            "unknown industry column",
        ),
        (
            lambda rows: rows[-1].update({"date": rows[-2]["date"]}),
            "duplicate observation date",
        ),
        (
            lambda rows: rows[-1].update({INDUSTRY_COLUMNS[1]: None}),
            "missing value",
        ),
        (
            lambda rows: rows[-1].update({INDUSTRY_COLUMNS[1]: float("nan")}),
            "non-finite value",
        ),
        (
            lambda rows: rows[-1].update({INDUSTRY_COLUMNS[1]: float("inf")}),
            "non-finite value",
        ),
        (
            lambda rows: rows[-1].pop("date"),
            "missing a date",
        ),
    ],
)
def test_readable_window_validation_errors(mutate: object, match: str) -> None:
    rows = _rows(80)
    mutate(rows)  # type: ignore[operator]

    with pytest.raises(IndustryAnalysisError, match=match):
        select_industry_window(rows)


def test_absent_as_of_and_insufficient_rows_are_readable_errors() -> None:
    rows = _rows(80)

    with pytest.raises(IndustryAnalysisError, match="as-of date .* is not present"):
        select_industry_window(rows, as_of="2030-01-01")

    with pytest.raises(IndustryAnalysisError, match="too short: requires at least 60"):
        select_industry_window(rows[:59])


def test_missing_value_outside_the_selected_window_is_ignored() -> None:
    rows = _rows(80)
    rows[0][INDUSTRY_COLUMNS[0]] = None

    window = select_industry_window(rows, as_of=rows[-1]["date"])

    assert window.shape == (60, 12)


def test_cloud_uses_shared_median_mad_scaling_and_rejects_zero_scale() -> None:
    rows = _rows(80)
    window = select_industry_window(rows, as_of=_as_of(rows))
    cloud = build_industry_cloud(rows, as_of=_as_of(rows))

    expected = robust_scale(window.values, axis=0)
    medians = np.median(window.values, axis=0)
    mads = np.median(np.abs(window.values - medians), axis=0)

    assert isinstance(cloud, IndustryCloud)
    np.testing.assert_allclose(cloud.scaled_cloud, expected)
    np.testing.assert_allclose(cloud.medians, medians)
    np.testing.assert_allclose(cloud.mads, mads)
    np.testing.assert_allclose(cloud.scales, 1.4826 * mads)
    np.testing.assert_allclose(np.median(cloud.scaled_cloud, axis=0), 0.0, atol=1e-12)

    constant_rows = _rows(80)
    for row in constant_rows:
        row[INDUSTRY_COLUMNS[0]] = 5.0
    with pytest.raises(IndustryAnalysisError, match="zero median/MAD scale"):
        build_industry_cloud(constant_rows, as_of=_as_of(constant_rows))


def test_cloud_and_pca_shapes_variance_and_labels() -> None:
    rows = _rows(80)
    cloud = build_industry_cloud(rows, as_of=_as_of(rows))

    assert cloud.cloud.shape == (60, 12)
    assert cloud.scaled_cloud.shape == (60, 12)
    assert cloud.pca.shape == (60, 2)
    assert cloud.pca_shape == (60, 2)
    assert cloud.explained_variance.shape == (2,)
    assert cloud.explained_variance_ratio.shape == (2,)
    assert np.all(cloud.explained_variance > 0.0)
    assert np.all(np.diff(cloud.explained_variance) <= 0.0)
    assert np.all(cloud.explained_variance_ratio > 0.0)
    assert np.all(cloud.explained_variance_ratio <= 1.0)
    assert np.sum(cloud.explained_variance_ratio) <= 1.0
    assert cloud.labels == PCA_LABELS == ("PC1", "PC2")
    assert cloud.pca_labels == cloud.component_labels == ("PC1", "PC2")
    assert cloud.pca_components.shape == (2, 12)
    assert isinstance(cloud.diagrams, Diagrams)
    assert cloud.h0.shape[1] == 2
    assert cloud.h1.shape[1] == 2
    assert np.all(np.asarray(cloud.h1_lifetimes) > DEFAULT_CONFIG.min_interval)

    # Deterministic sign convention: the largest-magnitude loading is positive.
    for component in cloud.pca_components:
        pivot = int(np.argmax(np.abs(component)))
        assert component[pivot] > 0.0


def test_repeated_cloud_runs_are_identical() -> None:
    rows = _rows(80)
    first = build_industry_cloud(rows, as_of=_as_of(rows))
    second = build_industry_cloud(rows, as_of=_as_of(rows))

    assert first == second
    assert first.to_payload() == second.to_payload()
    np.testing.assert_array_equal(first.scaled_cloud, second.scaled_cloud)
    np.testing.assert_array_equal(first.pca, second.pca)
    np.testing.assert_array_equal(first.explained_variance, second.explained_variance)
    np.testing.assert_array_equal(first.pca_components, second.pca_components)


def test_cloud_uses_complete_h0_h1_filtration_and_finite_lifetime_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    threshold_calls: list[float] = []

    def fake_ripser(points: object, **kwargs: object) -> dict[str, object]:
        captured["points"] = np.asarray(points)
        captured.update(kwargs)
        return {
            "dgms": [
                np.array([[0.0, 1.0], [0.0, np.inf]]),
                np.array(
                    [
                        [0.0, 1e-9],
                        [0.0, 1e-8],
                        [0.0, 1e-7],
                        [0.0, 2.0],
                        [0.0, np.inf],
                    ]
                ),
            ]
        }

    real_finite_lifetimes = industry_module.finite_lifetimes

    def spy_finite_lifetimes(
        diagram: object, threshold: object = None, *args: object, **kwargs: object
    ):
        threshold_calls.append(float(threshold))
        return real_finite_lifetimes(diagram, threshold, *args, **kwargs)

    monkeypatch.setattr(persistence_module, "ripser", fake_ripser)
    monkeypatch.setattr(industry_module, "finite_lifetimes", spy_finite_lifetimes)

    rows = _rows(80)
    cloud = build_industry_cloud(rows, as_of=_as_of(rows))

    assert captured["thresh"] == np.inf
    assert captured["maxdim"] == DEFAULT_CONFIG.max_homology_dimension == 1
    assert captured["coeff"] == DEFAULT_CONFIG.homology_coeff_field == 2
    assert captured["metric"] == "euclidean"
    assert threshold_calls == [DEFAULT_CONFIG.min_interval]

    assert isinstance(cloud.diagrams, Diagrams)
    assert isinstance(cloud.lifetimes, Lifetimes)
    assert cloud.h0.shape == (2, 2)
    assert cloud.h1.shape == (5, 2)
    # The cutoff is strict: exactly 1e-8 is excluded, as is the infinite bar.
    np.testing.assert_allclose(cloud.h0_lifetimes, np.array([1.0]))
    np.testing.assert_allclose(cloud.h1_lifetimes, np.array([1e-7, 2.0]))
    np.testing.assert_allclose(
        np.asarray(cloud.lifetimes), finite_lifetimes(cloud.h1, DEFAULT_CONFIG.min_interval)
    )


def test_cloud_payload_is_json_serialisable() -> None:
    rows = _rows(80)
    cloud = build_industry_cloud(rows, as_of=_as_of(rows))

    payload = cloud.payload
    assert callable(payload)
    encoded = json.dumps(payload, allow_nan=False)
    decoded = json.loads(encoded)

    assert decoded["as_of"] == _as_of(rows)
    assert len(decoded["dates"]) == 60
    assert len(decoded["columns"]) == 12
    assert len(decoded["cloud"]) == 60
    assert all(len(row) == 12 for row in decoded["cloud"])
    assert len(decoded["pca"]) == 60
    assert all(len(row) == 2 for row in decoded["pca"])
    assert decoded["pca_labels"] == ["PC1", "PC2"]
    assert len(decoded["explained_variance"]) == 2
    assert json.loads(cloud.to_json()) == decoded


def test_columns_override_cannot_add_unknown_industry_column() -> None:
    rows = _rows(80)

    with pytest.raises(IndustryAnalysisError, match="unknown industry column"):
        select_industry_window(rows, columns=(*INDUSTRY_COLUMNS, "ind_mystery_return"))


def test_columns_override_cannot_omit_canonical_industry_columns() -> None:
    rows = _rows(80)

    with pytest.raises(IndustryAnalysisError, match="missing industry column"):
        select_industry_window(rows, columns=INDUSTRY_COLUMNS[:-1])


def test_columns_override_cannot_hide_an_unknown_row_column() -> None:
    rows = _rows(80)
    for row in rows:
        row["ind_mystery_return"] = 0.0

    with pytest.raises(IndustryAnalysisError, match="unknown industry column"):
        select_industry_window(rows, columns=INDUSTRY_COLUMNS)


def test_canonical_columns_override_is_accepted_in_any_order() -> None:
    rows = _rows(80)

    window = select_industry_window(rows, columns=tuple(reversed(INDUSTRY_COLUMNS)))

    assert window.columns == INDUSTRY_COLUMNS
    assert window.shape == (60, 12)


def test_explicit_n_components_and_component_alias_are_supported() -> None:
    rows = _rows(80)

    explicit = build_industry_cloud(rows, as_of=_as_of(rows), n_components=2)
    aliased = build_industry_cloud(rows, as_of=_as_of(rows), components=2)

    assert explicit.pca.shape == (60, 2)
    assert aliased.pca.shape == (60, 2)
    assert explicit.pca_labels == aliased.pca_labels == PCA_LABELS


@pytest.mark.parametrize("value", ["2", True, 0, 13])
def test_invalid_component_counts_are_readable_errors(value: object) -> None:
    rows = _rows(80)

    with pytest.raises(IndustryAnalysisError, match="n_components"):
        build_industry_cloud(rows, as_of=_as_of(rows), n_components=value)
