"""Pure dashboard data loading and screen payloads for the Step 7 shell.

The module never imports Streamlit and never touches the network.  It loads a
profile's local data once and builds the four A7 screen payloads for a
:class:`~topomarket.ui.dashboard.DashboardSelection`:

* Overview - selected session, score percentile, frozen cutoff status, horizon
  and pending-label state;
* Topology - the 60-session industry cloud/mapper for the selected date, member
  inspector data, display flags and a replay-only outcome layer;
* Validation - frozen evaluation runs (metrics, bootstrap, evidence, drill-down
  tables, CSV-exportable rows);
* Data - import preview, active snapshot, refresh attempts/failures, revisions,
  schema/units/coverage and per-source observation ranges.

Replay safety is enforced here: outcome data is only added when a replay
selection has ``reveal=True`` and never alters scores, cutoffs or features.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from topomarket.analysis.evaluation import report_digest
from topomarket.data.normalized import NORMALIZED_TABLE_NAMES
from topomarket.data.refresh import active_snapshot_id, load_refresh_status, resolve_active_data_dir
from topomarket.demo.generator import demo_tables
from topomarket.profiles import load_profile
from topomarket.topology import load_daily_rows

from .accessibility import alert_marker, alternative_text, table_alternative
from .dashboard import (
    DEFAULT_WINDOW_SESSIONS,
    SCREENS,
    DashboardSelection,
    derive_window,
)

REPLAY = "replay"
LIVE = "live"
OUTCOME_HORIZON = 20
DRAWDOWN_TARGET = 0.10
SCREEN_LABELS = {
    "overview": "Overview",
    "topology": "Topology",
    "validation": "Validation",
    "data": "Data",
}
SCREEN_TITLES = {
    "overview": "Overview",
    "topology": "Topology",
    "validation": "Validation",
    "data": "Data",
}
DISPLAY_DEFAULT_2D = True
DISPLAY_OPTIONAL_3D = True

__all__ = [
    "DRAWDOWN_TARGET",
    "DashboardData",
    "LIVE",
    "OUTCOME_HORIZON",
    "PanelCache",
    "REPLAY",
    "SCREEN_LABELS",
    "SCREEN_TITLES",
    "build_screen_payloads",
    "load_dashboard_data",
    "session_dates",
]


class DashboardDataError(ValueError):
    """Raised when a profile/data directory cannot be loaded for the dashboard."""


@dataclass
class DashboardData:
    """Loaded, read-only dashboard inputs plus lazy topology caches."""

    profile: str
    data_dir: Path
    active_data_dir: Path
    session_dates: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    snapshot_id: str | None
    score_points: tuple[dict[str, Any], ...] = ()
    evaluation_reports: tuple[dict[str, Any], ...] = ()
    evaluation_runs: tuple[dict[str, Any], ...] = ()
    refresh_status: dict[str, Any] = field(default_factory=dict)
    import_manifest: dict[str, Any] = field(default_factory=dict)
    normalized_schema: dict[str, Any] = field(default_factory=dict)
    sources: tuple[dict[str, Any], ...] = ()
    revisions: tuple[dict[str, Any], ...] = ()
    snapshots: tuple[str, ...] = ()
    demo: bool = False
    data_signature: str = ""
    _topology_cache: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    @property
    def date_index(self) -> dict[str, int]:
        return {value: index for index, value in enumerate(self.session_dates)}

    @property
    def row_by_date(self) -> dict[str, dict[str, Any]]:
        return dict(zip(self.session_dates, self.rows, strict=True))

    @property
    def score_by_date(self) -> dict[str, dict[str, Any]]:
        return {str(point.get("date")): point for point in self.score_points}

    def selected_date(self, selection: DashboardSelection) -> str:
        if selection.date is not None:
            if selection.date not in self.date_index:
                raise DashboardDataError(
                    f"selected date {selection.date!r} is not a loaded session"
                )
            return str(selection.date)
        if not self.session_dates:
            raise DashboardDataError("dashboard has no sessions for the selected profile")
        return self.session_dates[-1]


def _business_days(start: date, end: date) -> list[date]:
    values: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            values.append(current)
        current += __import__("datetime").timedelta(days=1)
    return values


def _demo_rows() -> list[dict[str, Any]]:
    tables = demo_tables()
    tda = tables.get(NORMALIZED_TABLE_NAMES[2]) if len(NORMALIZED_TABLE_NAMES) > 2 else None
    if tda is None:
        raise DashboardDataError("demo generator does not expose tda_daily")
    rows: list[dict[str, Any]] = []
    for row in tda:
        rows.append({str(key): row[key] for key in row})
    return rows


def _score_file_candidates(data_dir: Path) -> list[Path]:
    return [
        data_dir / "scores.csv",
        data_dir / "topology_scores.csv",
        data_dir / "reports" / "scores.csv",
        data_dir / "reports" / "topology_scores.csv",
    ]


def _load_score_points(data_dir: Path) -> tuple[dict[str, Any], ...]:
    for candidate in _score_file_candidates(data_dir):
        if not candidate.is_file():
            continue
        points: list[dict[str, Any]] = []
        with candidate.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                points.append(
                    {
                        "date": row.get("date"),
                        "state": row.get("state") or "scored",
                        "score": row.get("score") or None,
                        "L": row.get("L") or None,
                        "D": row.get("D") or None,
                    }
                )
        return tuple(points)
    return ()


def _evaluation_report_paths(data_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for directory in (data_dir / "reports", data_dir, data_dir / "evaluations"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("evaluation*.json")):
            if path.is_file():
                candidates.append(path)
    return candidates


def _load_evaluation_reports(data_dir: Path) -> tuple[dict[str, Any], ...]:
    reports: list[dict[str, Any]] = []
    for path in _evaluation_report_paths(data_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        digest = report_digest(payload)
        payload.setdefault("run_id", digest[:12])
        payload.setdefault("report_path", str(path))
        payload.setdefault("run_digest", digest)
        reports.append(payload)
    return tuple(reports)


def _evaluation_run_summaries(reports: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "run_id": report.get("run_id"),
            "snapshot_id": report.get("snapshot_id"),
            "seed": report.get("seed"),
            "wording": (report.get("evidence") or {}).get("wording"),
            "historical_evidence": bool((report.get("evidence") or {}).get("historical_evidence")),
            "periods": report.get("periods"),
            "methods": report.get("methods"),
            "config_hash": report.get("config_hash"),
            "package_version": report.get("package_version"),
        }
        for report in reports
    )


def _load_import_manifest(data_dir: Path) -> dict[str, Any]:
    for name in ("import_manifest.json", "manifest.json"):
        path = data_dir / name
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
    return {}


def _load_normalized_schema(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "normalized" / "schemas.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_parser_reports(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "parser_reports.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_summaries(
    data_dir: Path, import_manifest: Mapping[str, Any]
) -> tuple[dict[str, Any], ...]:
    reports = _load_parser_reports(data_dir)
    by_source = reports.get("reports_by_source") or reports.get("by_source") or {}
    row_counts = import_manifest.get("row_counts") or {}
    source_ids = import_manifest.get("source_ids") or sorted(row_counts)
    summaries: list[dict[str, Any]] = []
    for source_id in source_ids:
        report = by_source.get(source_id) if isinstance(by_source, Mapping) else None
        report = report if isinstance(report, dict) else {}
        rows = row_counts.get(source_id) or report.get("row_count") or report.get("rows") or 0
        summaries.append(
            {
                "source_id": source_id,
                "row_count": int(rows) if isinstance(rows, (int, float)) else rows,
                "first_observation": report.get("first_observation") or report.get("first_date"),
                "last_observation": report.get("last_observation") or report.get("last_date"),
                "warnings": list(report.get("warnings") or ()),
            }
        )
    return tuple(summaries)


def _snapshot_manifests(root: Path) -> tuple[dict[str, Any], ...]:
    manifests: list[dict[str, Any]] = []
    snapshots = root / "snapshots"
    if snapshots.is_dir():
        for path in sorted(snapshots.iterdir()):
            if not path.is_dir():
                continue
            manifest = path / "refresh_manifest.json"
            if manifest.is_file():
                try:
                    payload = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    payload = dict(payload)
                    payload.setdefault("snapshot_id", path.name)
                    manifests.append(payload)
            else:
                manifests.append({"snapshot_id": path.name})
    return tuple(manifests)


def _revisions_from_snapshots(manifests: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    revisions: list[dict[str, Any]] = []
    for manifest in manifests:
        for revision in manifest.get("revisions") or ():
            if isinstance(revision, Mapping):
                revisions.append(dict(revision))
    return tuple(revisions)


def _data_signature(**parts: Any) -> str:
    encoded = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_dashboard_data(profile: str = "demo", data_dir: Path | str | None = None) -> DashboardData:
    """Load the local dashboard inputs for a profile (offline, deterministic)."""
    resolved = load_profile(profile, data_dir=Path(data_dir) if data_dir is not None else None)
    if resolved.profile == "demo":
        rows = tuple(_demo_rows())
        dates = tuple(str(row.get("date")) for row in rows)
        signature = _data_signature(
            profile="demo", rows=len(rows), end=dates[-1] if dates else None
        )
        return DashboardData(
            profile="demo",
            data_dir=Path(resolved.data_dir),
            active_data_dir=Path(resolved.data_dir),
            session_dates=dates,
            rows=rows,
            snapshot_id=None,
            demo=True,
            data_signature=signature,
        )

    root = Path(resolved.data_dir)
    active = resolve_active_data_dir(root)
    rows = tuple(load_daily_rows(active))
    dates = tuple(str(row.get("date")) for row in rows)
    import_manifest = _load_import_manifest(active)
    snapshot_id = active_snapshot_id(root) or (
        str(import_manifest.get("snapshot_id") or "") or None
    )
    evaluation_reports = _load_evaluation_reports(active)
    manifests = _snapshot_manifests(root)
    signature = _data_signature(
        profile=profile,
        snapshot=snapshot_id,
        row_count=len(rows),
        end=dates[-1] if dates else None,
        reports=len(evaluation_reports),
    )
    return DashboardData(
        profile=profile,
        data_dir=root,
        active_data_dir=active,
        session_dates=dates,
        rows=rows,
        snapshot_id=snapshot_id,
        score_points=_load_score_points(active),
        evaluation_reports=evaluation_reports,
        evaluation_runs=_evaluation_run_summaries(evaluation_reports),
        refresh_status=load_refresh_status(root),
        import_manifest=import_manifest,
        normalized_schema=_load_normalized_schema(active),
        sources=_source_summaries(active, import_manifest),
        revisions=_revisions_from_snapshots(manifests),
        snapshots=tuple(manifest.get("snapshot_id") for manifest in manifests),
        data_signature=signature,
    )


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def session_dates(data: DashboardData) -> tuple[str, ...]:
    return data.session_dates


def _score_value(data: DashboardData, selected: str) -> tuple[float | None, str]:
    point = data.score_by_date.get(selected)
    if point is None:
        return None, "no precomputed TDA score for this session"
    state = str(point.get("state") or "")
    if state != "scored":
        return None, f"score state is {state or 'unknown'}"
    raw = point.get("score")
    if raw in (None, ""):
        return None, "score value is unavailable"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "score value is not numeric"
    if not math.isfinite(value):
        return None, "score value is not finite"
    return value, "scored"


def _close(row: Mapping[str, Any]) -> float | None:
    raw = row.get("sp500_close")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _horizon_rows(data: DashboardData, selected: str) -> tuple[dict[str, Any], ...]:
    index = data.date_index.get(selected)
    if index is None:
        return ()
    return tuple(data.rows[index + 1 : index + 1 + OUTCOME_HORIZON])


def _outcome(data: DashboardData, selected: str, origin_close: float | None) -> dict[str, Any]:
    horizon = _horizon_rows(data, selected)
    pending = len(horizon) < OUTCOME_HORIZON
    breach_date: str | None = None
    breach_close: float | None = None
    if origin_close is not None:
        for row in horizon:
            close = _close(row)
            if close is not None and close <= origin_close * (1.0 - DRAWDOWN_TARGET):
                breach_date = str(row.get("date"))
                breach_close = close
                break
    target = None if pending else (1 if breach_date is not None else 0)
    return {
        "horizon_sessions": len(horizon),
        "required_sessions": OUTCOME_HORIZON,
        "pending": pending,
        "target": target,
        "breach_date": breach_date,
        "breach_close": breach_close,
        "dates": [str(row.get("date")) for row in horizon],
        "closes": [_close(row) for row in horizon],
    }


def _policy_for(report: Mapping[str, Any] | None, method: str = "tda") -> dict[str, Any] | None:
    if not isinstance(report, Mapping):
        return None
    policies = report.get("policies") or {}
    policy = policies.get(method)
    return dict(policy) if isinstance(policy, Mapping) else None


def _selected_report(data: DashboardData, selection: DashboardSelection) -> dict[str, Any] | None:
    if not data.evaluation_reports:
        return None
    if selection.run is not None:
        for report in data.evaluation_reports:
            if str(report.get("run_id")) == str(selection.run):
                return dict(report)
        raise DashboardDataError(f"unknown evaluation run {selection.run!r}")
    return dict(data.evaluation_reports[0])


def _score_status(score: float | None, policy: Mapping[str, Any] | None) -> dict[str, Any]:
    if score is None:
        return {"state": "unavailable", "cutoff": None, "policy_hash": None}
    if policy is None:
        return {"state": "no_frozen_policy", "cutoff": None, "policy_hash": None}
    raw_cutoff = policy.get("cutoff")
    try:
        cutoff = float(raw_cutoff)
    except (TypeError, ValueError):
        return {"state": "no_frozen_policy", "cutoff": None, "policy_hash": None}
    state = "above" if score >= cutoff else "below"
    return {
        "state": state,
        "cutoff": cutoff,
        "policy_hash": policy.get("policy_hash"),
        "method": policy.get("method", "tda"),
        "percentile": policy.get("percentile"),
    }


def _score_history(data: DashboardData, *, limit: int = 120) -> list[dict[str, Any]]:
    """Recent scored sessions for the Overview timeline (deterministic order)."""

    history: list[dict[str, Any]] = []
    for session in data.session_dates[-limit:]:
        point = data.score_by_date.get(session)
        if not point or str(point.get("state") or "") != "scored":
            continue
        raw = point.get("score")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        history.append({"date": session, "score": value})
    return history


# --------------------------------------------------------------------------- #
# Screen payloads
# --------------------------------------------------------------------------- #
def _overview_payload(
    data: DashboardData, selection: DashboardSelection, selected: str
) -> dict[str, Any]:
    row = data.row_by_date[selected]
    close = _close(row)
    score, reason = _score_value(data, selected)
    report = _selected_report(data, selection)
    policy = _policy_for(report)
    horizon = _outcome(data, selected, close)
    mode = str(selection.mode)
    return {
        "screen": "overview",
        "title": SCREEN_TITLES["overview"],
        "mode": mode,
        "date": selected,
        "source_date": selected,
        "row": {
            "date": selected,
            "sp500_close": close,
            "vix_close": row.get("vix_close"),
        },
        "score": {
            "value": score,
            "percentile_units": score,
            "state": "scored" if score is not None else "unavailable",
            "reason": reason,
            "cutoff_status": _score_status(score, policy),
        },
        "score_history": _score_history(data),
        "data_source": "synthetic demo" if data.demo else "private research",
        "snapshot_id": data.snapshot_id,
        "horizon": {
            "sessions": horizon["horizon_sessions"],
            "required": horizon["required_sessions"],
            "pending": horizon["pending"],
            "pending_labels": horizon["pending"],
            "target": horizon["target"],
        },
        "evidence": {
            "wording": (report or {}).get("evidence", {}).get("wording") if report else None,
            "historical_evidence": bool(
                (report or {}).get("evidence", {}).get("historical_evidence")
            )
            if report
            else False,
            "run_id": (report or {}).get("run_id"),
        },
        "replay": {
            "blind": mode == REPLAY and not selection.reveal,
            "reveal_available": mode == REPLAY,
            "revealed": bool(mode == REPLAY and selection.reveal),
        },
        "accessible_summary": alternative_text(
            f"Overview for session {selected}",
            description=(
                f"Selected session overview; score {score if score is not None else 'unavailable'}"
            ),
        ),
    }


def _topology_payload(
    data: DashboardData, selection: DashboardSelection, selected: str
) -> dict[str, Any]:
    window = derive_window(data.session_dates, selected, DEFAULT_WINDOW_SESSIONS)
    base: dict[str, Any] = {
        "screen": "topology",
        "title": SCREEN_TITLES["topology"],
        "mode": str(selection.mode),
        "date": selected,
        "window": list(window),
        "window_sessions": len(window),
        "required_sessions": DEFAULT_WINDOW_SESSIONS,
        "available": len(window) == DEFAULT_WINDOW_SESSIONS,
        "display": {
            "default_projection": "2d",
            "optional_3d": DISPLAY_OPTIONAL_3D,
            "default_2d": DISPLAY_DEFAULT_2D,
        },
        "member": selection.member,
        "snapshot_id": data.snapshot_id,
    }
    if not base["available"]:
        base["reason"] = (
            f"needs {DEFAULT_WINDOW_SESSIONS} sessions, selected window has {len(window)}"
        )
        base["outcome"] = None
        return base

    cache_key = f"topology:{selected}"
    payload = data._topology_cache.get(cache_key)
    if payload is None:
        from topomarket.analysis import industry_explorer_payload

        payload = industry_explorer_payload(list(data.rows), as_of=selected)
        data._topology_cache[cache_key] = payload
    base["cloud"] = payload.get("cloud")
    base["mapper"] = payload.get("mapper")
    nodes = (payload.get("mapper") or {}).get("nodes") or ()
    selected_node = None
    if selection.member:
        for node in nodes:
            members = node.get("members") or ()
            if selection.member in members or selection.member in (
                node.get("member_columns") or ()
            ):
                selected_node = dict(node)
                break
    if selected_node is None and nodes:
        selected_node = dict(nodes[0])
    base["selected_node"] = selected_node
    base["member_inspector"] = {
        "member": selection.member,
        "node_id": (selected_node or {}).get("id"),
        "members": list((selected_node or {}).get("members") or ()),
        "member_correlations": (selected_node or {}).get("member_correlations") or "Not applicable",
        "member_volatilities": (selected_node or {}).get("member_volatilities"),
    }
    cloud_payload = payload.get("cloud") or {}
    h1_intervals = cloud_payload.get("h1") or []
    base["accessible_summary"] = alternative_text(
        f"Topology window {window[0]} to {window[-1]}",
        description=f"{len(h1_intervals)} H1 interval(s) for the selected window",
    )
    if bool(selection.mode == REPLAY and selection.reveal):
        close = _close(data.row_by_date[selected])
        base["outcome"] = _outcome(data, selected, close)
    else:
        base["outcome"] = None
    return base


def _validation_payload(data: DashboardData, selection: DashboardSelection) -> dict[str, Any]:
    base: dict[str, Any] = {
        "screen": "validation",
        "title": SCREEN_TITLES["validation"],
        "runs": [dict(run) for run in data.evaluation_runs],
        "selected_run_id": selection.run,
        "snapshot_id": data.snapshot_id,
    }
    report = _selected_report(data, selection)
    if report is None:
        base["available"] = False
        base["empty_state"] = (
            "No frozen evaluation run is available for this data directory. "
            "Run `topomarket evaluate --report-out reports/evaluation.json` first."
        )
        base["export_table"] = {"columns": [], "rows": []}
        return base
    base["available"] = True
    base["run_id"] = report.get("run_id")
    base["evidence"] = report.get("evidence")
    base["periods"] = report.get("periods")
    base["bootstrap"] = report.get("bootstrap")
    base["policies"] = report.get("policies")
    base["calibrations"] = report.get("calibrations")
    base["config_hash"] = report.get("config_hash")
    base["seed"] = report.get("seed")
    base["episode_count"] = report.get("episode_count")
    base["resolved_episode_count"] = report.get("resolved_episode_count")
    base["censored_episodes"] = report.get("censored_episodes")
    base["purged_validation_sessions"] = report.get("purged_validation_sessions")
    metrics = report.get("metrics") or {}
    base["metrics"] = {method: dict(value) for method, value in metrics.items()}
    examples = report.get("examples") or {}
    drilldown: dict[str, Any] = {}
    table_rows: list[list[Any]] = []
    columns = ["kind", "method", "date", "episode_onset", "lead_sessions"]
    for method, payload in examples.items():
        matched = list(payload.get("matched") or ())
        missed = list(payload.get("missed") or ())
        false_alerts = list(payload.get("false_alerts") or ())
        drilldown[method] = {
            "matched": matched,
            "missed": missed,
            "false_alerts": false_alerts,
        }
        for entry in matched:
            table_rows.append(
                [
                    "matched",
                    method,
                    entry.get("alert_date"),
                    entry.get("episode_onset"),
                    entry.get("lead_sessions"),
                ]
            )
        for entry in missed:
            table_rows.append(["missed", method, None, entry.get("episode_onset"), None])
        for date_value in false_alerts:
            table_rows.append(["false_alert", method, date_value, None, None])
    base["drilldown"] = drilldown
    base["export_table"] = {"columns": columns, "rows": table_rows}
    base["table_alternative"] = table_alternative(
        "Evaluation alerts and episodes",
        columns=columns,
        rows=[tuple(row) for row in table_rows],
    )
    return base


def _data_payload(data: DashboardData, selection: DashboardSelection) -> dict[str, Any]:
    status = data.refresh_status or {}
    sources = [dict(source) for source in data.sources]
    status_sources = status.get("sources") or {}
    for source in sources:
        source_status = status_sources.get(source.get("source_id"), {})
        source["last_attempt_at"] = source_status.get("last_attempt_at")
        source["last_success_at"] = source_status.get("last_success_at")
        source["attempt_outcome"] = source_status.get("outcome")
        source["attempt_error"] = source_status.get("error")
    failures = [
        source
        for source in sources
        if source.get("attempt_outcome") in {"failed", "optional_failed"}
    ]
    schema_tables = data.normalized_schema.get("tables") or {}
    coverage = {}
    for name in NORMALIZED_TABLE_NAMES:
        table_payload = schema_tables.get(name) or {}
        rows = (data.import_manifest.get("normalized_row_counts") or {}).get(name)
        coverage[name] = {
            "row_count": rows,
            "columns": list((table_payload.get("columns") or ())[:0])
            or list(table_payload.get("columns") or ()),
            "units": table_payload.get("units"),
        }
    return {
        "screen": "data",
        "title": SCREEN_TITLES["data"],
        "profile": data.profile,
        "data_dir": str(data.data_dir),
        "active_data_dir": str(data.active_data_dir),
        "active_snapshot_id": data.snapshot_id,
        "snapshots": list(data.snapshots),
        "snapshot_id": data.snapshot_id,
        "sources": sources,
        "failures": failures,
        "revisions": [dict(value) for value in data.revisions[:100]],
        "revision_count": len(data.revisions),
        "refresh": {
            "updated_at_utc": status.get("updated_at_utc"),
            "published": status.get("published"),
            "error": status.get("error"),
            "warnings": list(status.get("warnings") or ()),
        },
        "schema": {
            "schema_version": data.normalized_schema.get("schema_version"),
            "tables": {
                name: {
                    "columns": list(table_payload.get("columns") or ()),
                    "units": table_payload.get("units"),
                }
                for name, table_payload in schema_tables.items()
            },
        },
        "coverage": coverage,
        "import_manifest": {
            "source_ids": list(data.import_manifest.get("source_ids") or ()),
            "row_counts": data.import_manifest.get("row_counts") or {},
            "normalized_row_counts": data.import_manifest.get("normalized_row_counts") or {},
            "latest_data_date": data.import_manifest.get("latest_data_date"),
        },
        "selected_date": selection.date,
        "table_alternative": table_alternative(
            "Data sources and refresh state",
            columns=[
                "source",
                "rows",
                "first",
                "last",
                "last_attempt",
                "last_success",
                "outcome",
            ],
            rows=[
                (
                    source.get("source_id"),
                    source.get("row_count"),
                    source.get("first_observation"),
                    source.get("last_observation"),
                    source.get("last_attempt_at"),
                    source.get("last_success_at"),
                    source.get("attempt_outcome"),
                )
                for source in sources
            ],
        ),
        "alert_marker": alert_marker("warning", "refresh attention")
        if failures
        else alert_marker("success", "sources healthy"),
    }


def build_screen_payloads(
    data: DashboardData, selection: DashboardSelection
) -> dict[str, dict[str, Any]]:
    """Build all four screen payloads for a selection."""
    if not isinstance(data, DashboardData):
        raise DashboardDataError("build_screen_payloads requires DashboardData")
    if not isinstance(selection, DashboardSelection):
        raise DashboardDataError("build_screen_payloads requires DashboardSelection")
    selected = data.selected_date(selection)
    payloads = {
        "overview": _overview_payload(data, selection, selected),
        "topology": _topology_payload(data, selection, selected),
        "validation": _validation_payload(data, selection),
        "data": _data_payload(data, selection),
    }
    for screen in SCREENS:
        payloads.setdefault(screen, {"screen": screen, "title": SCREEN_TITLES[screen]})
    return payloads


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #
class PanelCache:
    """Per-data in-memory cache of screen payloads keyed by selection identity."""

    def __init__(self, data: DashboardData) -> None:
        self.data = data
        self._payload_cache: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
        self._topology_cache: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    def selection_key(self, selection: DashboardSelection) -> tuple[Any, ...]:
        return (
            selection.screen,
            str(selection.mode),
            selection.date,
            bool(selection.reveal),
            selection.member,
            selection.run,
        )

    def get(self, selection: DashboardSelection) -> dict[str, dict[str, Any]]:
        key = self.selection_key(selection)
        if key in self._payload_cache:
            self.hits += 1
            return self._payload_cache[key]
        self.misses += 1
        payloads = build_screen_payloads(self.data, selection)
        self._payload_cache[key] = payloads
        return payloads

    payloads = get

    def invalidate(self) -> None:
        self._payload_cache.clear()
        self._topology_cache.clear()


__all__ = [
    "DRAWDOWN_TARGET",
    "DashboardData",
    "DashboardDataError",
    "LIVE",
    "OUTCOME_HORIZON",
    "PanelCache",
    "REPLAY",
    "SCREEN_LABELS",
    "SCREEN_TITLES",
    "build_screen_payloads",
    "load_dashboard_data",
    "session_dates",
]
