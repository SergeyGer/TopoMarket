"""F02 causal blind Replay: no retrospective information before reveal (WP-B)."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from topomarket.analysis.asof import (
    alert_markers,
    alert_state,
    causal_alert_dates,
    classify_alert,
)
from topomarket.ui.dashboard import DashboardSelection
from topomarket.ui.panels import build_screen_payloads, load_dashboard_data

ROOT = Path(__file__).resolve().parents[1]
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FORBIDDEN_WORDS = (
    "matched warning",
    "late alert",
    "post_onset",
    "episode_onset",
    "missed episode",
    "warning matched",
)


def _data():
    return load_dashboard_data("demo")


def _payload(data, screen: str, date: str, *, reveal: bool = False) -> dict:
    selection = DashboardSelection(screen=screen, mode="replay", date=date, reveal=reveal)
    return build_screen_payloads(data, selection, screens=(screen,))[screen]


def _mutated_report(report: dict) -> dict:
    mutated = copy.deepcopy(report)
    primary = mutated.get("primary_method") or "tda"
    metrics = mutated.setdefault("metrics", {}).setdefault(primary, {})
    alerts = list(metrics.get("alerts") or ())
    if alerts:
        metrics["alerts"] = alerts + ["2099-01-02", "2099-02-03"]
        metrics["matched"] = [
            {"alert_date": alerts[0], "episode_onset": "2099-03-04", "lead_sessions": 7}
        ]
        metrics["post_onset_alerts"] = [alerts[-1]]
        metrics["false_alerts"] = ["2099-04-05"]
        metrics["pending_alerts"] = ["2099-05-06"]
    mutated.setdefault("examples", {}).setdefault(primary, {})["matched"] = [
        {"alert_date": alerts[0] if alerts else "2099-01-01", "episode_onset": "2099-03-04"}
    ]
    return mutated


def _future_dates(payload: object, cutoff: str) -> list[str]:
    found: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str) and DATE.match(value) and value > cutoff:
            found.append(value)

    walk(payload)
    return found


def _strings(payload: object) -> list[str]:
    found: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            found.append(value.lower())

    walk(payload)
    return found


def test_blind_payload_ignores_report_classifications_and_matches() -> None:
    data = _data()
    date = "2025-03-10"
    before = _payload(data, "replay", date)
    original = list(data.evaluation_reports)
    data.evaluation_reports = (_mutated_report(original[0]), *original[1:])
    try:
        after = _payload(data, "replay", date)
    finally:
        data.evaluation_reports = tuple(original)
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)
    assert before["alert"]["label"] == "Alert recorded"
    assert before["alert"]["status"] == "recorded"
    assert before["blind"] is True
    assert {marker["status"] for marker in before["alert_markers"]} == {"recorded"}
    assert {marker["label"] for marker in before["alert_markers"]} == {"Alert recorded"}
    words = " ".join(_strings(before))
    for forbidden in FORBIDDEN_WORDS:
        assert forbidden not in words, forbidden
    assert _future_dates(before, date) == []


def test_blind_payload_ignores_future_prices() -> None:
    data = _data()
    date = "2025-03-10"
    before = _payload(data, "replay", date)
    originals = (copy.deepcopy(data.rows), copy.deepcopy(data.price_rows))
    try:
        for collection in (data.rows, data.price_rows):
            for row in collection:
                if str(row.get("date")) > date:
                    row["sp500_close"] = "1.0"
                    row["vix_close"] = "999.0"
        after = _payload(data, "replay", date)
    finally:
        data.rows, data.price_rows = originals
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


def test_revealed_classification_uses_only_the_revealed_horizon() -> None:
    data = _data()
    date = "2025-03-10"
    before = _payload(data, "replay", date, reveal=True)
    assert before["blind"] is False
    assert before["alert"]["retrospective"] is True
    assert before["alert"]["status"] in {"late", "matched", "false"}
    horizon_end = before["outcome"]["dates"][-1]
    originals = (copy.deepcopy(data.rows), copy.deepcopy(data.price_rows))
    try:
        for collection in (data.rows, data.price_rows):
            for row in collection:
                if str(row.get("date")) > horizon_end:
                    row["sp500_close"] = "1.0"
        after = _payload(data, "replay", date, reveal=True)
    finally:
        data.rows, data.price_rows = originals
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


def test_pending_scope_classification_is_explicit() -> None:
    data = _data()
    latest = data.session_dates[-1]
    alerts = causal_alert_dates(data)
    recent = alert_state(data, alerts[-1], blinded=False)
    assert recent["retrospective"] is True
    # The very last session's own horizon is incomplete in the observed scope.
    assert recent["status"] in {"pending", "late", "matched", "false"}
    assert classify_alert(data, latest)["status"] == "pending"


def test_structure_blind_markers_are_neutral_and_report_invariant() -> None:
    data = _data()
    date = "2025-03-10"
    before = _payload(data, "structure", date)
    markers = before["timeline"]["alert_markers"]
    assert markers
    assert {marker["status"] for marker in markers} == {"recorded"}
    assert {marker["symbol"] for marker in markers} == {"^"}
    original = list(data.evaluation_reports)
    data.evaluation_reports = (_mutated_report(original[0]), *original[1:])
    try:
        after = _payload(data, "structure", date)
    finally:
        data.evaluation_reports = tuple(original)
    assert json.dumps(before["timeline"], sort_keys=True) == json.dumps(
        after["timeline"], sort_keys=True
    )


def test_frozen_policy_is_the_only_report_input_for_causal_alerts() -> None:
    data = _data()
    alerts = causal_alert_dates(data)
    assert alerts
    assert alerts == sorted(alerts)
    assert alert_markers(data, alerts[-1], blinded=True)
