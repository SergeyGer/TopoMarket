"""Pure dashboard data loading and screen payloads for the v1.0 shell.

The module never imports Streamlit and never touches the network.  It loads a
profile's local data once and builds the four screen payloads for a
:class:`~topomarket.ui.dashboard.DashboardSelection`:

* **Structure** - correlation network, Mapper view, shared S&P 500/VIX/score
  timeline and the Takens/H1/PCA explanation (UI01-UI04);
* **Replay** - one authoritative selected session with a blind/revealed
  20-session outcome layer (RE01);
* **Validation** - frozen evaluation runs with corrected metrics, sample size,
  false-alert rate, bootstrap uncertainty and evidence wording (EV01);
* **Data** - independent observation calendars, source coverage, last refresh,
  revisions and errors (DA01).

Replay safety is enforced here: every payload is sliced by the selected session
before anything is serialised, and the outcome layer only exists when the
selection explicitly reveals it.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from topomarket.analysis.evaluation import report_digest
from topomarket.data.normalized import NORMALIZED_TABLE_NAMES
from topomarket.data.refresh import active_snapshot_id, load_refresh_status, resolve_active_data_dir
from topomarket.demo.generator import demo_tables
from topomarket.profiles import REPOSITORY_ROOT, load_profile
from topomarket.topology import load_daily_rows

from .calendars import build_calendar_status
from .dashboard import (
    SCREENS,
    DashboardSelection,
)
from .replay import build_replay_payload
from .structure import build_structure_payload

REPLAY = "replay"
LIVE = "live"
OUTCOME_HORIZON = 20
DRAWDOWN_TARGET = 0.10
SHOWCASE_DIRNAME = "showcase"
SCREEN_LABELS = {
    "structure": "Structure",
    "replay": "Replay",
    "validation": "Validation",
    "data": "Data",
}
SCREEN_TITLES = {
    "structure": "Structure",
    "replay": "Replay",
    "validation": "Validation",
    "data": "Data",
}
DEFAULT_PRIMARY_METHOD = "tda"

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


class DashboardDataError(ValueError):
    """Raised when a profile/data directory cannot be loaded for the dashboard."""


@dataclass
class DashboardData:
    """Loaded, read-only dashboard inputs plus lazy topology/preset caches.

    ``session_dates`` is the authoritative signal calendar (S&P 500 price
    observations).  ``rows`` is the joined tda table used for score/Mapper
    windows, while ``price_rows`` and ``industry_rows`` keep the independent
    observation calendars required by DA01.
    """

    profile: str
    data_dir: Path
    active_data_dir: Path
    session_dates: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    snapshot_id: str | None
    price_rows: tuple[dict[str, Any], ...] = ()
    industry_rows: tuple[dict[str, Any], ...] = ()
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
    _presets_cache: dict[str, Any] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.price_rows:
            self.price_rows = self.rows
        if not self.industry_rows:
            self.industry_rows = self.rows
        members: list[str] = []
        for row in self.rows:
            for key in row:
                if key.startswith("ind_") and key.endswith("_return"):
                    code = key[len("ind_") : -len("_return")]
                    if code not in members:
                        members.append(code)
        self._members_cache: tuple[str, ...] = tuple(members)

    @property
    def members(self) -> tuple[str, ...]:
        """Industry codes present in the loaded rows (computed once)."""

        return self._members_cache

    @property
    def date_index(self) -> dict[str, int]:
        return {value: index for index, value in enumerate(self.session_dates)}

    @property
    def row_by_date(self) -> dict[str, dict[str, Any]]:
        return {str(row.get("date")): row for row in self.rows if row.get("date")}

    @property
    def price_by_date(self) -> dict[str, dict[str, Any]]:
        return {str(row.get("date")): row for row in self.price_rows if row.get("date")}

    @property
    def industry_by_date(self) -> dict[str, dict[str, Any]]:
        return {str(row.get("date")): row for row in self.industry_rows if row.get("date")}

    @property
    def score_by_date(self) -> dict[str, dict[str, Any]]:
        return {str(point.get("date")): point for point in self.score_points if point.get("date")}

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

    def primary_report(self) -> dict[str, Any] | None:
        return dict(self.evaluation_reports[0]) if self.evaluation_reports else None

    def primary_method(self) -> str:
        report = self.primary_report() or {}
        return str(report.get("primary_method") or DEFAULT_PRIMARY_METHOD)

    def primary_metrics(self) -> dict[str, Any]:
        report = self.primary_report()
        if report is None:
            return {}
        method = str(report.get("primary_method") or DEFAULT_PRIMARY_METHOD)
        metrics = (report.get("metrics") or {}).get(method)
        return dict(metrics) if isinstance(metrics, Mapping) else {}

    def primary_policy(self) -> dict[str, Any] | None:
        report = self.primary_report()
        if report is None:
            return None
        method = str(report.get("primary_method") or DEFAULT_PRIMARY_METHOD)
        policy = (report.get("policies") or {}).get(method)
        return dict(policy) if isinstance(policy, Mapping) else None


# --------------------------------------------------------------------------- #
# Loading helpers
# --------------------------------------------------------------------------- #
def _demo_rows() -> list[dict[str, Any]]:
    tables = demo_tables()
    tda = tables.get(NORMALIZED_TABLE_NAMES[2]) if len(NORMALIZED_TABLE_NAMES) > 2 else None
    if tda is None:
        raise DashboardDataError("demo generator does not expose tda_daily")
    return [{str(key): row[key] for key in row} for row in tda]


def _load_optional_table(data_dir: Path, table: str) -> tuple[dict[str, Any], ...]:
    path = data_dir / "normalized" / f"{table}.csv"
    if not path.is_file():
        return ()
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return tuple(dict(row) for row in csv.DictReader(handle))
    except OSError:
        return ()


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
            "primary_method": report.get("primary_method"),
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


def _revisions_from_snapshots(
    manifests: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    revisions: list[dict[str, Any]] = []
    for manifest in manifests:
        for revision in manifest.get("revisions") or ():
            if isinstance(revision, Mapping):
                revisions.append(dict(revision))
    return tuple(revisions)


def _data_signature(**parts: Any) -> str:
    encoded = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _build_dataset(
    *,
    profile: str,
    root: Path,
    active: Path,
    demo: bool,
) -> DashboardData:
    rows = tuple(dict(row) for row in load_daily_rows(active))
    price_rows = _load_optional_table(active, "sp500_daily") or rows
    industry_rows = _load_optional_table(active, "industries_daily") or rows
    dates = tuple(str(row.get("date")) for row in price_rows if row.get("date"))
    if not dates:
        dates = tuple(str(row.get("date")) for row in rows if row.get("date"))
    import_manifest = _load_import_manifest(active)
    synthetic_fixture = bool(import_manifest.get("synthetic"))
    demo = demo or synthetic_fixture
    snapshot_id = active_snapshot_id(root) or (
        str(import_manifest.get("snapshot_id") or "") or None
    )
    evaluation_reports = _load_evaluation_reports(active)
    manifests = _snapshot_manifests(root)
    signature = _data_signature(
        profile=profile,
        snapshot=snapshot_id,
        row_count=len(rows),
        price_count=len(price_rows),
        industry_count=len(industry_rows),
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
        price_rows=tuple(dict(row) for row in price_rows),
        industry_rows=tuple(dict(row) for row in industry_rows),
        score_points=_load_score_points(active),
        evaluation_reports=evaluation_reports,
        evaluation_runs=_evaluation_run_summaries(evaluation_reports),
        refresh_status=load_refresh_status(root),
        import_manifest=import_manifest,
        normalized_schema=_load_normalized_schema(active),
        sources=_source_summaries(active, import_manifest),
        revisions=_revisions_from_snapshots(manifests),
        snapshots=tuple(manifest.get("snapshot_id") for manifest in manifests),
        demo=demo,
        data_signature=signature,
    )


def _showcase_dir() -> Path | None:
    candidate = REPOSITORY_ROOT / SHOWCASE_DIRNAME
    if (candidate / "normalized" / "tda_daily.csv").is_file():
        return candidate
    return None


def load_dashboard_data(profile: str = "demo", data_dir: Path | str | None = None) -> DashboardData:
    """Load the local dashboard inputs for a profile (offline, deterministic).

    The public ``demo`` profile defaults to the committed synthetic showcase
    fixture (5,673 sessions) so the topology window and the demonstration presets
    are populated without flags.  If the showcase is not available (for example
    an installed wheel without the repository checkout) the small bundled
    synthetic generator is used as a fallback.
    """

    resolved = load_profile(profile, data_dir=Path(data_dir) if data_dir is not None else None)
    if resolved.profile == "demo" and data_dir is None:
        showcase = _showcase_dir()
        if showcase is not None:
            return _build_dataset(profile="demo", root=showcase, active=showcase, demo=True)
        rows = tuple(_demo_rows())
        dates = tuple(str(row.get("date")) for row in rows)
        return DashboardData(
            profile="demo",
            data_dir=Path(resolved.data_dir),
            active_data_dir=Path(resolved.data_dir),
            session_dates=dates,
            rows=rows,
            price_rows=rows,
            industry_rows=rows,
            snapshot_id=None,
            demo=True,
            data_signature=_data_signature(
                profile="demo", rows=len(rows), end=dates[-1] if dates else None
            ),
        )
    root = Path(resolved.data_dir)
    active = resolve_active_data_dir(root)
    return _build_dataset(
        profile=str(resolved.profile), root=root, active=active, demo=resolved.profile == "demo"
    )


# --------------------------------------------------------------------------- #
# Screen payloads
# --------------------------------------------------------------------------- #
def _validation_payload(data: DashboardData, selection: DashboardSelection) -> dict[str, Any]:
    base: dict[str, Any] = {
        "screen": "validation",
        "title": SCREEN_TITLES["validation"],
        "runs": [dict(run) for run in data.evaluation_runs],
        "selected_run_id": selection.run,
        "snapshot_id": data.snapshot_id,
    }
    report = data.primary_report()
    if selection.run is not None:
        for candidate in data.evaluation_reports:
            if str(candidate.get("run_id")) == str(selection.run):
                report = dict(candidate)
                break
        else:
            raise DashboardDataError(f"unknown evaluation run {selection.run!r}")
    if report is None:
        base.update(
            {
                "available": False,
                "empty_state": (
                    "No frozen evaluation run is available for this data directory. "
                    "Run `topomarket evaluate --report-out reports/evaluation.json` first."
                ),
                "export_table": {"columns": [], "rows": []},
                "metrics": {},
                "evidence": {},
            }
        )
        return base
    metrics = {
        method: dict(value)
        for method, value in (report.get("metrics") or {}).items()
        if isinstance(value, Mapping)
    }
    primary = str(report.get("primary_method") or DEFAULT_PRIMARY_METHOD)
    primary_metrics = metrics.get(primary) or {}
    evidence = dict(report.get("evidence") or {})
    limitations = list(evidence.get("limitations") or ())
    examples = report.get("examples") or {}
    drilldown: dict[str, Any] = {}
    table_rows: list[list[Any]] = []
    columns = ["kind", "method", "date", "episode_onset", "lead_sessions"]
    for method, payload in examples.items():
        if not isinstance(payload, Mapping):
            continue
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
    method_order = [
        method
        for method in (str(report.get("primary_method") or ""), *metrics)
        if method in metrics
    ]
    seen: set[str] = set()
    ordered_methods = [
        method for method in method_order if not (method in seen or seen.add(method))
    ]
    evidence_table = [
        {
            "method": method,
            "recall_numerator": metrics[method].get("matched_count"),
            "recall_denominator": metrics[method].get("episode_count"),
            "episode_recall": metrics[method].get("episode_recall"),
            "average_precision": metrics[method].get("average_precision"),
            "event_prevalence": metrics[method].get("event_prevalence"),
            "false_count": metrics[method].get("false_alert_count"),
            "false_alerts_per_year": metrics[method].get("false_alerts_per_year"),
            "median_lead_sessions": metrics[method].get("median_lead_sessions"),
            "alerts": len(metrics[method].get("alerts") or ()),
            "eligible_sessions": metrics[method].get("eligible_sessions"),
        }
        for method in ordered_methods
    ]
    provenance = dict(report.get("provenance") or {})
    comparison = report.get("calibration_comparison")
    base.update(
        {
            "available": True,
            "run_id": report.get("run_id"),
            "report_version": report.get("report_version"),
            "calibration_version": report.get("calibration_version"),
            "schema_version": report.get("schema_version"),
            "provenance": provenance,
            "calibration_comparison": comparison,
            "evidence_table": evidence_table,
            "evidence": evidence,
            "wording": evidence.get("wording"),
            "historical_evidence": bool(evidence.get("historical_evidence")),
            "limitations": limitations,
            "periods": report.get("periods"),
            "bootstrap": report.get("bootstrap"),
            "policies": report.get("policies"),
            "calibrations": report.get("calibrations"),
            "config_hash": report.get("config_hash"),
            "package_version": report.get("package_version"),
            "seed": report.get("seed"),
            "primary_method": primary,
            "comparator_method": report.get("comparator_method"),
            "methods": list(metrics),
            "label_counts": report.get("label_counts"),
            "episode_count": report.get("episode_count"),
            "resolved_episode_count": report.get("resolved_episode_count"),
            "censored_episodes": report.get("censored_episodes"),
            "purged_validation_sessions": report.get("purged_validation_sessions"),
            "metrics": metrics,
            "primary_metrics": primary_metrics,
            "sample_size": {
                "episode_count": primary_metrics.get("episode_count"),
                "eligible_sessions": primary_metrics.get("eligible_sessions"),
                "matched_count": primary_metrics.get("matched_count"),
                "label_counts": report.get("label_counts"),
            },
            "false_alert_rate": primary_metrics.get("false_alerts_per_year"),
            "average_precision": primary_metrics.get("average_precision"),
            "percentile_note": "The score percentile is a comparative score; the forecast is an "
            "experiment and is not a trading recommendation.",
            "drilldown": drilldown,
            "export_table": {"columns": columns, "rows": table_rows},
            "table_alternative": _evaluation_table(columns, table_rows),
        }
    )
    return base


def _evaluation_table(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [", ".join(str(column) for column in columns)]
    for row in rows:
        lines.append(", ".join("" if value is None else str(value) for value in row))
    return "\n".join(lines)


def _data_payload(data: DashboardData, selection: DashboardSelection) -> dict[str, Any]:
    payload = build_calendar_status(data)
    payload["selected_date"] = selection.date
    payload["screen"] = "data"
    payload["title"] = SCREEN_TITLES["data"]
    return payload


def build_screen_payloads(
    data: DashboardData,
    selection: DashboardSelection,
    screens: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the requested screen payloads for a selection (all by default).

    The shell requests only the visible screen so a date change rebuilds a single
    payload set; callers that need the full four-screen matrix (tests, plain-text
    fallback) omit ``screens``.
    """

    if not isinstance(data, DashboardData):
        raise DashboardDataError("build_screen_payloads requires DashboardData")
    if not isinstance(selection, DashboardSelection):
        raise DashboardDataError("build_screen_payloads requires DashboardSelection")
    selected = data.selected_date(selection)
    requested = tuple(screens) if screens is not None else SCREENS
    builders = {
        "structure": lambda: build_structure_payload(data, selection),
        "replay": lambda: build_replay_payload(data, selection),
        "validation": lambda: _validation_payload(data, selection),
        "data": lambda: _data_payload(data, selection),
    }
    payloads: dict[str, dict[str, Any]] = {}
    for screen in requested:
        builder = builders.get(screen)
        payloads[screen] = (
            builder()
            if builder is not None
            else {"screen": screen, "title": SCREEN_TITLES.get(screen, screen)}
        )
    if "structure" in payloads:
        payloads["structure"]["selected"] = selected
    return payloads


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #
class PanelCache:
    """Per-data in-memory cache of screen payloads keyed by selection identity."""

    def __init__(self, data: DashboardData) -> None:
        self.data = data
        self._payload_cache: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
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
            str(selection.network_view),
            selection.edge,
            self.data.data_signature,
        )

    def get(
        self,
        selection: DashboardSelection,
        screens: Sequence[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Build (or return cached) payloads for the requested screens."""

        requested = tuple(screens) if screens is not None else SCREENS
        key = (*self.selection_key(selection), requested)
        if key in self._payload_cache:
            self.hits += 1
            return self._payload_cache[key]
        self.misses += 1
        payloads = build_screen_payloads(self.data, selection, screens=requested)
        self._payload_cache[key] = payloads
        return payloads

    def get_screen(self, selection: DashboardSelection) -> dict[str, dict[str, Any]]:
        """Return the payload for the currently visible screen only."""

        return self.get(selection, screens=(selection.screen,))

    payloads = get

    def invalidate(self) -> None:
        self._payload_cache.clear()
        self.data._topology_cache.clear()
        self.data._presets_cache = None


def session_dates(data: DashboardData) -> tuple[str, ...]:
    return data.session_dates


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
