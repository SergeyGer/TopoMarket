"""Focused offline tests for the correlation-distance industry Mapper graph."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import numpy as np
import pytest

from topomarket.analysis import (
    INDUSTRY_COLUMNS,
    INDUSTRY_LABELS,
    WINDOW_SESSIONS,
    IndustryWindow,
)
from topomarket.analysis.mapper import (
    NOT_APPLICABLE,
    MapperEdge,
    MapperError,
    MapperGraph,
    MapperInterval,
    MapperNode,
    _assemble_nodes,
    annualized_volatility,
    compute_mapper_graph,
    connected_components,
    correlation_distance,
    correlation_distances,
    mapper_intervals,
    mapper_payload,
    pearson_correlations,
)
from topomarket.topology.config import DEFAULT_CONFIG


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


def test_mapper_reuses_the_shared_60_session_canonical_window() -> None:
    rows = _rows(80)
    graph = compute_mapper_graph(rows, as_of=_as_of(rows, 69))

    assert isinstance(graph, MapperGraph)
    assert graph.window.shape == (WINDOW_SESSIONS, 12) == (60, 12)
    assert graph.window.columns == INDUSTRY_COLUMNS
    assert graph.window.labels == INDUSTRY_LABELS
    assert graph.as_of == _as_of(rows, 69)
    assert graph.dates == tuple(str(row["date"]) for row in rows[10:70])
    assert graph.window_sessions == 60
    assert graph.columns == INDUSTRY_COLUMNS
    assert graph.labels == INDUSTRY_LABELS
    assert graph.threshold == 1.0
    assert graph.annualization == 252.0
    assert graph.config == DEFAULT_CONFIG

    latest = compute_mapper_graph(rows)
    assert latest.as_of == _as_of(rows)
    assert latest.window == compute_mapper_graph(rows, as_of=_as_of(rows)).window


def test_pearson_correlations_match_numpy_and_are_clipped() -> None:
    generator = np.random.default_rng(7)
    values = generator.normal(size=(60, 4))
    expected = np.corrcoef(values, rowvar=False)

    correlations = pearson_correlations(values)

    np.testing.assert_allclose(correlations, expected)
    np.testing.assert_allclose(np.diag(correlations), np.ones(4))
    np.testing.assert_allclose(correlations, correlations.T)
    assert np.all(correlations >= -1.0)
    assert np.all(correlations <= 1.0)

    single = pearson_correlations(values[:, :1])
    np.testing.assert_array_equal(single, np.ones((1, 1)))


def test_correlation_distances_are_clipped_to_the_closed_unit_range() -> None:
    correlations = np.array([-2.0, -1.0, 0.0, 0.5, 1.0, 2.0])

    distances = correlation_distances(correlations)

    np.testing.assert_allclose(distances, np.array([2.0, 2.0, 1.0, 0.5, 0.0, 0.0]))
    assert correlation_distance(1.5) == 0.0
    assert correlation_distance(-1.5) == 2.0
    matrix = np.array([[1.0, 0.25], [0.25, 1.0]])
    np.testing.assert_allclose(correlation_distance(matrix), np.array([[0.0, 0.75], [0.75, 0.0]]))


def test_annualized_sample_volatility_uses_ddof_one_and_252_days() -> None:
    values = np.array(
        [
            [0.01, 0.02, -0.03],
            [0.02, -0.01, 0.00],
            [-0.01, 0.03, 0.01],
            [0.03, 0.00, -0.02],
            [0.00, 0.01, 0.02],
        ]
    )
    expected = np.std(values, axis=0, ddof=1) * math.sqrt(252.0)

    np.testing.assert_allclose(annualized_volatility(values), expected)
    np.testing.assert_allclose(
        annualized_volatility(values, annualization=52),
        expected / math.sqrt(252.0) * math.sqrt(52.0),
    )
    assert annualized_volatility(values[:, 0]) == pytest.approx(float(expected[0]))


def test_constant_vectors_raise_mapper_error_instead_of_nan_correlations() -> None:
    constant = np.ones((60, 2))
    with pytest.raises(MapperError, match="constant-vector"):
        pearson_correlations(constant)

    # 0.1 is not exactly representable in binary; repeating it can leave a
    # tiny non-zero sample standard deviation, so constant detection must not
    # rely on the computed standard deviation being exactly zero.
    non_binary_constant = np.column_stack((np.full(60, 0.1), np.linspace(0.0, 1.0, 60)))
    assert np.std(non_binary_constant[:, 0], ddof=1) != 0.0
    with pytest.raises(MapperError, match="constant-vector"):
        pearson_correlations(non_binary_constant)

    rows = _rows(80)
    for row in rows:
        row[INDUSTRY_COLUMNS[0]] = 0.1
    with pytest.raises(MapperError, match="constant-vector"):
        compute_mapper_graph(rows, as_of=_as_of(rows))


def test_three_inclusive_overlapping_intervals_and_equal_lens_case() -> None:
    intervals = mapper_intervals(np.array([0.0, 1.0]))

    # A5 cover: width = range / 2.2, stride = 0.6 * width (40% overlap).
    width = 1.0 / 2.2
    stride = 0.6 * width
    assert len(intervals) == 3
    expected = np.array(
        [
            [0.0, width],
            [stride, stride + width],
            [2.0 * stride, 1.0],
        ]
    )
    np.testing.assert_allclose([interval.bounds for interval in intervals], expected)
    np.testing.assert_allclose(intervals[0].width, width)
    np.testing.assert_allclose(intervals[1].lower - intervals[0].lower, stride)

    # Adjacent intervals overlap: a value inside the overlap belongs to both.
    boundary = width
    assert intervals[0].contains(boundary)
    assert intervals[1].contains(boundary)
    below = np.nextafter(stride, -np.inf)
    assert intervals[0].contains(below)
    assert not intervals[1].contains(below)

    equal = mapper_intervals(np.array([2.0, 2.0]))
    assert len(equal) == 1
    assert equal[0].bounds == (2.0, 2.0)
    assert equal[0].contains(2.0)
    assert len(mapper_intervals(np.array([1e-16, 2e-16, 3e-16]))) == 3

    tiny = mapper_intervals(np.array([1e-13, 2e-13, 3e-13]))
    assert len(tiny) == 3
    for value, expected_interval in (
        (1e-13, 0),
        (2e-13, 1),
        (3e-13, 2),
    ):
        membership = [index for index, interval in enumerate(tiny) if interval.contains(value)]
        assert membership == [expected_interval]


def test_tiny_nonconstant_returns_do_not_collapse_the_three_intervals() -> None:
    rows = _rows(80)
    for row_index, row in enumerate(rows):
        for column_index, column in enumerate(INDUSTRY_COLUMNS):
            scale = (column_index + 1) * 1e-15
            row[column] = scale * (
                np.sin(row_index / 5.0 + column_index) + 0.3 * np.cos(row_index / 3.0)
            )

    graph = compute_mapper_graph(rows, as_of=_as_of(rows))

    assert len(graph.intervals) == 3
    assert graph.volatilities.max() > graph.volatilities.min()
    for value in graph.volatilities:
        membership = [
            index for index, interval in enumerate(graph.intervals) if interval.contains(value)
        ]
        # The old absolute 1e-12 tolerance made every tiny value a member of
        # all three intervals; at most two adjacent intervals may overlap.
        assert 1 <= len(membership) <= 2
    assert any(
        sum(interval.contains(value) for interval in graph.intervals) == 1
        for value in graph.volatilities
    )


def test_threshold_one_connected_components_include_singletons_and_boundaries() -> None:
    distances = np.array(
        [
            [0.0, 0.5, 2.0, 1.0],
            [0.5, 0.0, 2.0, 1.0],
            [2.0, 2.0, 0.0, 2.0],
            [1.0, 1.0, 2.0, 0.0],
        ]
    )

    components = connected_components(distances, threshold=1.0)

    assert components == ((0, 1, 3), (2,))
    assert connected_components(distances, threshold=0.0) == ((0,), (1,), (2,), (3,))
    assert connected_components(distances, threshold=1.0, labels=("a", "b", "c", "d")) == (
        ("a", "b", "d"),
        ("c",),
    )

    strict = np.array(
        [
            [0.0, 1.0, np.nextafter(1.0, np.inf)],
            [1.0, 0.0, 2.0],
            [np.nextafter(1.0, np.inf), 2.0, 0.0],
        ]
    )
    assert connected_components(strict, threshold=1.0) == ((0, 1), (2,))


def _mapper_window() -> IndustryWindow:
    return IndustryWindow(
        columns=INDUSTRY_COLUMNS,
        dates=("2024-01-02", "2024-01-03"),
        values=np.zeros((2, 12)),
        as_of="2024-01-03",
        window_sessions=2,
        labels=INDUSTRY_LABELS,
    )


def test_duplicate_member_sets_keep_lowest_interval_and_shared_edges() -> None:
    window = _mapper_window()
    correlations = np.eye(12)
    correlations[0, 1] = correlations[1, 0] = 1.0
    correlations[2, 3] = correlations[3, 2] = 1.0
    distances = np.full((12, 12), 2.0)
    np.fill_diagonal(distances, 0.0)
    for left, right in ((0, 1), (0, 2), (1, 2), (2, 3)):
        distances[left, right] = distances[right, left] = 0.0

    volatilities = np.full(12, 1.0)
    volatilities[0] = volatilities[1] = 1.0 / 3.0
    volatilities[4] = 1.0 / 3.0
    volatilities[2] = 0.41
    volatilities[3] = 0.5
    intervals = (
        MapperInterval(0.0, 0.4, 0),
        MapperInterval(0.3, 0.7, 1),
        MapperInterval(0.6, 1.0, 2),
    )

    nodes, edges = _assemble_nodes(
        window,
        correlations,
        distances,
        volatilities,
        intervals,
        1.0,
    )

    assert tuple(node.member_indices for node in nodes) == tuple(
        sorted(node.member_indices for node in nodes)
    )
    assert [node.id for node in nodes] == [f"node-{index:02d}" for index in range(len(nodes))]

    duplicates = [node for node in nodes if node.member_indices == (0, 1)]
    assert len(duplicates) == 1
    assert duplicates[0].interval_index == 0
    duplicate_singleton = [node for node in nodes if node.member_indices == (4,)]
    assert len(duplicate_singleton) == 1
    assert duplicate_singleton[0].interval_index == 0

    supersets = [node for node in nodes if node.member_indices == (0, 1, 2, 3)]
    assert len(supersets) == 1
    shared_edges = [
        edge for edge in edges if {edge.source, edge.target} == {duplicates[0].id, supersets[0].id}
    ]
    assert len(shared_edges) == 1
    assert shared_edges[0].members == (INDUSTRY_LABELS[0], INDUSTRY_LABELS[1])
    assert shared_edges[0].member_indices == (0, 1)
    assert shared_edges[0].weight == 2.0


def test_graph_counts_density_largest_component_and_sorted_circular_nodes() -> None:
    rows = _rows(80)
    graph = compute_mapper_graph(rows, as_of=_as_of(rows))

    assert graph.node_count == len(graph.nodes)
    assert graph.edge_count == len(graph.edges)
    if graph.node_count > 1:
        assert graph.density == pytest.approx(
            2.0 * graph.edge_count / (graph.node_count * (graph.node_count - 1))
        )
    else:
        assert graph.density == 0.0
    assert 0.0 <= graph.largest_component_fraction <= 1.0

    node_ids = [node.id for node in graph.nodes]
    assert node_ids == sorted(node_ids)
    assert len(set(node_ids)) == len(node_ids)
    for index, node in enumerate(graph.nodes):
        angle = 2.0 * math.pi * index / graph.node_count
        assert node.position == (round(math.cos(angle), 6), round(math.sin(angle), 6))
        assert node.radius == pytest.approx(1.0)
        assert node.circular_position == node.position
        assert set(node.member_indices) <= set(range(len(INDUSTRY_COLUMNS)))
        assert node.members == tuple(INDUSTRY_LABELS[item] for item in node.member_indices)

    for left in range(graph.node_count):
        for right in range(left + 1, graph.node_count):
            shared = set(graph.nodes[left].member_indices) & set(graph.nodes[right].member_indices)
            matching = [
                edge
                for edge in graph.edges
                if {edge.source, edge.target} == {graph.nodes[left].id, graph.nodes[right].id}
            ]
            assert bool(matching) is bool(shared)
            if matching:
                assert matching[0].member_indices == tuple(sorted(shared))
                assert matching[0].members
    assert all(
        edge.member_indices
        and set(edge.member_indices)
        <= set(graph.nodes[[node.id for node in graph.nodes].index(edge.source)].member_indices)
        & set(graph.nodes[[node.id for node in graph.nodes].index(edge.target)].member_indices)
        for edge in graph.edges
    )


def test_largest_component_fraction_matches_a_known_multi_component_graph() -> None:
    window = _mapper_window()
    correlations = np.eye(12)
    distances = np.full((12, 12), 2.0)
    np.fill_diagonal(distances, 0.0)
    volatilities = np.linspace(0.1, 1.2, 12)
    nodes = tuple(
        MapperNode(
            id=f"node-{index:02d}",
            interval_index=0,
            members=(INDUSTRY_LABELS[index],),
            member_indices=(index,),
            member_columns=(INDUSTRY_COLUMNS[index],),
            member_volatilities=(float(volatilities[index]),),
            member_correlations=NOT_APPLICABLE,
            position=(
                math.cos(2.0 * math.pi * index / 4.0),
                math.sin(2.0 * math.pi * index / 4.0),
            ),
        )
        for index in range(4)
    )
    edges = (
        MapperEdge(
            source="node-00",
            target="node-01",
            members=(INDUSTRY_LABELS[0],),
        ),
        MapperEdge(
            source="node-02",
            target="node-03",
            members=(INDUSTRY_LABELS[2],),
        ),
    )
    graph = MapperGraph(
        window=window,
        correlations=correlations,
        distances=distances,
        volatilities=volatilities,
        intervals=(MapperInterval(0.0, 1.25, 0),),
        nodes=nodes,
        edges=edges,
        labels=INDUSTRY_LABELS,
    )

    assert graph.node_count == 4
    assert graph.edge_count == 2
    assert graph.density == pytest.approx(2.0 * 2.0 / (4.0 * 3.0))
    assert graph.largest_component_size == 2
    assert graph.largest_component_fraction == pytest.approx(0.5)
    assert mapper_payload(graph)["largest_component_fraction"] == pytest.approx(0.5)


def test_member_correlations_singletons_tooltips_and_payload() -> None:
    rows = _rows(80)
    graph = compute_mapper_graph(rows, as_of=_as_of(rows))

    for node in graph.nodes:
        if node.size < 2:
            assert node.member_correlations == NOT_APPLICABLE
            assert node.mean_correlation == NOT_APPLICABLE
            assert NOT_APPLICABLE in node.tooltip
        else:
            assert isinstance(node.member_correlations, tuple)
            assert node.member_correlations == tuple(sorted(node.member_correlations))
            assert all(-1.0 <= value <= 1.0 for value in node.member_correlations)
            assert node.mean_correlation == pytest.approx(float(np.mean(node.member_correlations)))
        assert node.id in node.tooltip
        assert "interval" in node.tooltip
        assert "correlations" in node.tooltip

    for edge in graph.edges:
        assert edge.source in edge.tooltip
        assert edge.target in edge.tooltip
        for member in edge.members:
            assert member in edge.tooltip

    payload = mapper_payload(graph)
    encoded = json.dumps(payload, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["node_count"] == graph.node_count
    assert decoded["edge_count"] == graph.edge_count
    assert len(decoded["nodes"]) == graph.node_count
    assert len(decoded["edges"]) == graph.edge_count
    assert decoded["intervals"][0]["lower"] == pytest.approx(graph.intervals[0].lower)
    assert json.loads(graph.to_json()) == decoded
    for node_payload in decoded["nodes"]:
        if node_payload["size"] < 2:
            assert node_payload["member_correlations"] == NOT_APPLICABLE


def test_repeated_mapper_runs_are_identical_and_config_is_deterministic() -> None:
    rows = _rows(80)
    first = compute_mapper_graph(rows, as_of=_as_of(rows))
    second = compute_mapper_graph(rows, as_of=_as_of(rows))

    assert first == second
    assert mapper_payload(first) == mapper_payload(second)
    np.testing.assert_array_equal(first.correlations, second.correlations)
    np.testing.assert_array_equal(first.distances, second.distances)
    np.testing.assert_array_equal(first.volatilities, second.volatilities)
    assert first.nodes == second.nodes
    assert first.edges == second.edges
    payload = mapper_payload(first)
    assert payload["config"] == second.config.to_dict()
    assert payload["config_hash"] == second.config.config_hash() == DEFAULT_CONFIG.config_hash()
    assert first.config_hash == DEFAULT_CONFIG.config_hash()


def test_mapper_payload_contains_descriptive_graph_statistics() -> None:
    rows = _rows(80)
    graph = compute_mapper_graph(rows, as_of=_as_of(rows))
    payload = mapper_payload(graph)

    assert payload["as_of"] == _as_of(rows)
    assert payload["window_sessions"] == 60
    assert payload["threshold"] == 1.0
    assert payload["annualization"] == 252.0
    assert len(payload["correlation_matrix"]) == 12
    assert all(len(row) == 12 for row in payload["correlation_matrix"])
    assert len(payload["distances"]) == 12
    assert all(len(row) == 12 for row in payload["distances"])
    assert len(payload["volatilities"]) == 12
    assert len(payload["intervals"]) == 3
    assert payload["density"] == pytest.approx(graph.density)
    assert payload["largest_component_fraction"] == pytest.approx(graph.largest_component_fraction)
    assert payload["member_correlation_values"] == list(graph.member_correlation_values)
    assert payload["member_correlation_values"] == sorted(payload["member_correlation_values"])
    assert list(payload) == list(mapper_payload(graph))

    # A non-graph object is rejected instead of silently inventing a payload.
    with pytest.raises(MapperError, match="MapperGraph"):
        mapper_payload(rows)  # type: ignore[arg-type]
