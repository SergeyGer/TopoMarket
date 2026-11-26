"""Tests for the deterministic 12-industry correlation network (UI02)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from topomarket.analysis.network import (
    DEFAULT_CORRELATION_CUTOFF,
    DEFAULT_CORRELATION_WINDOW,
    INDUSTRY_CODES,
    INDUSTRY_LABELS,
    PAIR_COUNT,
    NetworkError,
    build_correlation_network,
    fixed_node_positions,
    industry_nodes,
    node_by_code,
    pair_lookup,
    pearson_correlation,
    return_column,
    select_correlation_window,
)
from topomarket.topology import load_daily_rows

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "showcase"


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    return load_daily_rows(SHOWCASE)


def _reference_correlations(window: dict, codes: tuple[str, ...] = INDUSTRY_CODES):
    """Independent numpy computation of the pair correlations."""

    values = np.array([[value for value in window["series"][code]] for code in codes], dtype=float)
    matrix = np.corrcoef(values)
    return {
        (codes[left], codes[right]): float(matrix[left, right])
        for left in range(len(codes))
        for right in range(left + 1, len(codes))
    }


def test_industry_labels_cover_the_twelve_french_portfolios() -> None:
    assert len(INDUSTRY_CODES) == 12
    assert PAIR_COUNT == 66
    assert set(INDUSTRY_LABELS) == set(INDUSTRY_CODES)
    for code in INDUSTRY_CODES:
        assert return_column(code) == f"ind_{code}_return"


def test_fixed_positions_are_deterministic_and_on_the_unit_circle() -> None:
    first = fixed_node_positions()
    second = fixed_node_positions()
    assert first == second
    assert set(first) == set(INDUSTRY_CODES)
    for x, y in first.values():
        assert math.isclose(math.hypot(x, y), 1.0, rel_tol=1e-9)
    nodes = industry_nodes()
    assert [node.code for node in nodes] == list(INDUSTRY_CODES)


def test_window_is_trailing_valid_sessions_and_ends_at_as_of(rows) -> None:
    as_of = "2020-02-24"
    window = select_correlation_window(rows, as_of)
    assert window["available"] is True
    assert window["sessions"] == DEFAULT_CORRELATION_WINDOW
    assert window["end"] == as_of
    dates = [str(row["date"]) for row in rows]
    assert window["dates"][-1] == as_of
    end = dates.index(as_of)
    assert window["dates"] == dates[end - DEFAULT_CORRELATION_WINDOW + 1 : end + 1]


def test_blind_window_ignores_future_rows(rows) -> None:
    """RE01/A03: a blind window must not change when future rows are mutated."""

    as_of = "2020-02-24"
    index = next(position for position, row in enumerate(rows) if row["date"] == as_of)
    baseline = build_correlation_network(rows, as_of)
    mutated = [dict(row) for row in rows]
    for row in mutated[index + 1 :]:
        for code in INDUSTRY_CODES:
            row[return_column(code)] = "999.0"
    changed = build_correlation_network(mutated, as_of)
    assert changed["pairs"] == baseline["pairs"]
    assert changed["edges"] == baseline["edges"]
    assert changed["pairs_qualifying"] == baseline["pairs_qualifying"]


def test_correlations_match_numpy_reference(rows) -> None:
    as_of = "2020-02-24"
    window = select_correlation_window(rows, as_of)
    reference = _reference_correlations(window)
    network = build_correlation_network(rows, as_of)
    computed = {(pair["source"], pair["target"]): pair["correlation"] for pair in network["pairs"]}
    assert len(reference) == PAIR_COUNT == len(computed)
    for pair, expected in reference.items():
        assert math.isclose(computed[pair], expected, abs_tol=1e-6), pair


def test_edges_are_the_positive_pairs_above_the_cutoff(rows) -> None:
    as_of = "2020-02-24"
    network = build_correlation_network(rows, as_of)
    expected = [
        {key: value for key, value in pair.items() if key != "correlation_full"}
        for pair in network["pairs"]
        if pair["correlation_full"] >= DEFAULT_CORRELATION_CUTOFF
    ]
    assert network["edges"] == expected
    assert network["pairs_qualifying"] == len(expected)
    assert network["pairs_qualifying"] <= network["pairs_total"] == PAIR_COUNT
    assert all(edge["correlation"] >= DEFAULT_CORRELATION_CUTOFF for edge in network["edges"])
    assert ">= 0.80" in network["cutoff_display"] or network["cutoff_display"].endswith("0.80")
    summary = network["summary"]
    assert f"{network['pairs_qualifying']} of 66" in summary


def test_node_degree_and_incident_edges_match_the_edge_list(rows) -> None:
    network = build_correlation_network(rows, "2020-02-24")
    for node in network["nodes"]:
        incident = [
            edge for edge in network["edges"] if node["code"] in (edge["source"], edge["target"])
        ]
        assert node["degree"] == len(incident)
        assert node["incident_edges"] == incident


def test_custom_cutoff_changes_edge_count(rows) -> None:
    loose = build_correlation_network(rows, "2020-02-24", cutoff=0.5)
    strict = build_correlation_network(rows, "2020-02-24", cutoff=0.99)
    assert loose["pairs_qualifying"] >= strict["pairs_qualifying"]
    assert loose["cutoff"] == 0.5


def test_pair_lookup_and_node_inspector_are_canonical(rows) -> None:
    network = build_correlation_network(rows, "2020-02-24")
    lookup = pair_lookup(network)
    for (left, right), value in lookup.items():
        assert left <= right
        assert math.isfinite(value)
        assert lookup[(left, right)] == value
    node = node_by_code(network, "money")
    assert node is not None and node["label"] == INDUSTRY_LABELS["money"]
    assert node_by_code(network, "nope") is None


def test_insufficient_observations_are_reported_explicitly() -> None:
    rows = [
        {
            "date": f"2024-01-{day:02d}",
            **{return_column(code): "0.01" for code in INDUSTRY_CODES},
        }
        for day in range(1, 11)
    ]
    payload = build_correlation_network(rows, "2024-01-10")
    assert payload["available"] is False
    assert payload["nodes"] == []
    assert "needs 60" in payload["reason"]


def test_constant_series_are_undefined_not_zero() -> None:
    from datetime import date, timedelta

    rows = []
    for offset in range(60):
        row = {"date": (date(2024, 1, 1) + timedelta(days=offset)).isoformat()}
        for position, code in enumerate(INDUSTRY_CODES):
            value = 0.0 if code == "money" else 0.001 * position + offset * 1e-6
            row[return_column(code)] = f"{value}"
        rows.append(row)
    payload = build_correlation_network(rows, rows[-1]["date"])
    assert payload["available"] is True
    undefined = {frozenset((pair["source"], pair["target"])) for pair in payload["undefined_pairs"]}
    assert all(
        frozenset(("money", code)) in undefined for code in INDUSTRY_CODES if code != "money"
    )


def test_unknown_as_of_and_bad_cutoff_raise(rows) -> None:
    with pytest.raises(NetworkError):
        build_correlation_network(rows, "1999-01-01")
    with pytest.raises(NetworkError):
        build_correlation_network(rows, "2020-02-24", cutoff=2.0)
    with pytest.raises(NetworkError):
        select_correlation_window(rows, "2020-02-24", window=1)


def test_payload_is_json_serialisable(rows) -> None:
    payload = build_correlation_network(rows, "2020-02-24")
    encoded = json.dumps(payload)
    assert json.loads(encoded)["pairs_qualifying"] == payload["pairs_qualifying"]


def test_pearson_correlation_edge_cases() -> None:
    assert pearson_correlation([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert pearson_correlation([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(-1.0)
    assert pearson_correlation([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None
    assert pearson_correlation([1.0], [1.0]) is None
    with pytest.raises(NetworkError):
        pearson_correlation([1.0, 2.0], [1.0])


def test_boundary_qualification_uses_full_precision(monkeypatch) -> None:
    """Network builder qualifies exact full-precision rho, not the rounded tag."""

    import math
    from datetime import date, timedelta

    from topomarket.analysis.network import build_correlation_network
    from topomarket.data.schemas import INDUSTRY_NAMES, industry_return_column

    days = [date(2020, 1, 1) + timedelta(days=offset) for offset in range(60)]
    x = [math.cos(2 * math.pi * index / 60) for index in range(60)]
    orth = [math.sin(2 * math.pi * index / 60) for index in range(60)]

    def correlated(level: float) -> list[float]:
        scale = math.sqrt(1.0 - level * level)
        return [level * left + scale * right for left, right in zip(x, orth, strict=False)]

    series: dict[str, list[float]] = {}
    for name in INDUSTRY_NAMES:
        series[name] = [float(index + position) for position, index in enumerate(range(60))]
    # nodur/durbl: true rho 0.7999996 (rounds to 0.800000); manuf/enrgy: exactly 0.8.
    series["NoDur"] = x
    series["Durbl"] = correlated(0.7999996)
    series["Manuf"] = correlated(0.8)
    series["Enrgy"] = correlated(0.8)
    rows = [
        {
            "date": day.isoformat(),
            **{industry_return_column(n): f"{series[n][i]:.12f}" for n in INDUSTRY_NAMES},
        }
        for i, day in enumerate(days)
    ]
    network = build_correlation_network(rows, days[-1].isoformat())
    pairs = {(pair["source"], pair["target"]): pair for pair in network["pairs"]}
    nodur_durbl = pairs[("nodur", "durbl")]
    assert nodur_durbl["correlation"] == 0.8  # six-decimal display tag
    assert nodur_durbl["correlation_full"] < 0.8
    assert all((edge["source"], edge["target"]) != ("nodur", "durbl") for edge in network["edges"])
    assert any((edge["source"], edge["target"]) == ("manuf", "enrgy") for edge in network["edges"])
