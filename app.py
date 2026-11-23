#!/usr/bin/env python3
"""Streamlit shell and repository entry point for TopoMarket.

The module can be imported without Streamlit installed. Streamlit is treated
as an optional UI dependency: its import is guarded and rendering falls back
to plain text when it is unavailable, which keeps CLI usage and smoke tests
working offline.

The shell implements the four Step 7 screens (Overview, Topology, Validation,
Data) with a persistent global selection, replay safety controls and
accessible rendering. All analysis is provided by the pure
:mod:`topomarket.ui.panels` layer; the shell only renders payloads.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from topomarket import __version__  # noqa: E402  (path is configured above)
from topomarket.profiles import PROFILE_NAMES  # noqa: E402
from topomarket.ui.accessibility import motion_css  # noqa: E402
from topomarket.ui.dashboard import (  # noqa: E402
    DashboardSelection,
    apply_keyboard_action,
    next_session,
    previous_session,
    toggle_blind,
    toggle_reveal,
)
from topomarket.ui.overview import (  # noqa: E402
    build_overview,
    plain_text_overview,
)
from topomarket.ui.panels import (  # noqa: E402
    LIVE,
    OUTCOME_HORIZON,
    REPLAY,
    SCREEN_LABELS,
    DashboardData,
    DashboardDataError,
    PanelCache,
    load_dashboard_data,
)

try:  # Streamlit is optional; importing app.py must work without it.
    import streamlit as st  # type: ignore[import-not-found]  # noqa: E402
except ImportError:  # pragma: no cover - exercised when Streamlit is absent
    st = None  # type: ignore[assignment]

SCREEN_ORDER = ("overview", "topology", "validation", "data")
DEFAULT_PROFILE = "demo"
DEFAULT_WINDOW = 60


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the Streamlit shell entry point."""

    parser = argparse.ArgumentParser(
        prog="app.py",
        description=(
            "TopoMarket Streamlit shell. Run with `streamlit run app.py -- --profile demo|private`."
        ),
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="demo",
        help="Profile to display (default: demo).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Optional local data directory that overrides the profile's data_dir.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse shell arguments, ignoring options owned by Streamlit itself."""

    args, _unknown = build_parser().parse_known_args(argv)
    return args


# --------------------------------------------------------------------------- #
# Selection / session state
# --------------------------------------------------------------------------- #
def _loaded_context(data: DashboardData) -> dict[str, Any]:
    members: list[str] = []
    for row in data.rows:
        for key in row:
            if key.startswith("ind_") and key.endswith("_return"):
                code = key[len("ind_") : -len("_return")]
                if code not in members:
                    members.append(code)
    return {
        "session_dates": list(data.session_dates),
        "members": members,
        "runs": [str(run.get("run_id")) for run in data.evaluation_runs],
    }


def _context_kwargs(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sessions": context.get("session_dates"),
        "members": context.get("members"),
        "runs": context.get("runs"),
    }


def default_selection(data: DashboardData) -> DashboardSelection:
    context = _loaded_context(data)
    return DashboardSelection(
        screen="overview",
        mode=LIVE,
        date=data.session_dates[-1] if data.session_dates else None,
        **_context_kwargs(context),
    )


def _state_value(state: Mapping[str, Any], name: str, default: Any = None) -> Any:
    for key in (name, f"tm_{name.removeprefix('tm_')}", f"topomarket_{name}"):
        if key in state:
            return state[key]
    return default


def selection_from_state(state: Mapping[str, Any], data: DashboardData) -> DashboardSelection:
    """Build a validated dashboard selection from Streamlit session state."""

    context = _loaded_context(data)
    default = default_selection(data)
    screen = _state_value(state, "tm_screen", default.screen)
    mode = _state_value(state, "tm_mode", default.mode)
    if str(mode).lower() in {"latest", "live"}:
        mode = LIVE
    elif str(mode).lower() in {"replay", "historical"}:
        mode = REPLAY
    else:
        mode = default.mode
    date = _state_value(state, "tm_date", default.date)
    reveal = bool(_state_value(state, "tm_reveal", False))
    member = _state_value(state, "tm_member", None) or None
    run = _state_value(state, "tm_run", None) or None
    return DashboardSelection(
        screen=screen,
        mode=mode,
        date=date,
        reveal=reveal,
        member=member,
        run=run,
        **_context_kwargs(context),
    )


def apply_action_to_state(
    state: dict[str, Any], action: str, data: DashboardData
) -> DashboardSelection:
    """Apply a keyboard action to session state and return the new selection."""

    selection = selection_from_state(state, data)
    updated = apply_keyboard_action(action, selection)
    state["tm_screen"] = updated.screen
    state["tm_mode"] = updated.mode
    state["tm_date"] = updated.date
    state["tm_reveal"] = bool(updated.reveal)
    state["tm_member"] = updated.member
    state["tm_run"] = updated.run
    return updated


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def _ui(streamlit_module: Any | None = None) -> Any:
    module = streamlit_module if streamlit_module is not None else st
    if module is None:
        raise RuntimeError("Streamlit is not available")
    return module


def _call(module: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    method = getattr(module, name, None)
    if method is None:
        return None
    return method(*args, **kwargs)


def _sidebar(module: Any) -> Any:
    return getattr(module, "sidebar", module)


def _expander(ui: Any, label: str) -> Any:
    expander = getattr(ui, "expander", None)
    if expander is None:
        return _NullContext(ui)
    return expander(label)


class _NullContext:
    def __init__(self, target: Any) -> None:
        self.target = target

    def __enter__(self) -> Any:
        return self.target

    def __exit__(self, *_exc: object) -> bool:
        return False


def render_overview(
    overview: Mapping[str, Any],
    streamlit_module: Any | None = None,
) -> None:
    """Render the legacy overview with Streamlit."""

    ui = _ui(streamlit_module)
    ui.set_page_config(page_title=str(overview.get("title", "TopoMarket")))
    ui.title(str(overview.get("title", "TopoMarket")))
    ui.subheader(str(overview.get("heading", "Overview")))

    ui.markdown(f"Profile badge: **{overview.get('profile_badge', 'unknown')}**")
    ui.markdown(str(overview.get("data_source_label", "Data source: unknown")))
    if overview.get("profile_description"):
        ui.caption(str(overview["profile_description"]))

    latest = overview.get("latest_data_date")
    if latest:
        ui.markdown(f"**Latest data date:** {latest}")
    else:
        ui.markdown("**Latest data date:** none")
    if overview.get("empty_state"):
        ui.info(str(overview["empty_state"]))

    ui.caption(f"Data directory: {overview.get('data_dir', '')}")

    ui.sidebar.header("Navigation")
    ui.sidebar.caption("Placeholder pages")
    for item in overview.get("navigation", []):
        ui.sidebar.markdown(f"- {item}")


def _screen_from_label(value: Any) -> str:
    text = str(value).strip().lower()
    for name, label in SCREEN_LABELS.items():
        if text == label.lower():
            return name
    return text if text in SCREEN_ORDER else "overview"


def _replace_selection(selection: DashboardSelection, **changes: Any) -> DashboardSelection:
    values = {
        "screen": selection.screen,
        "mode": selection.mode,
        "date": selection.date,
        "reveal": selection.reveal,
        "member": selection.member,
        "run": selection.run,
    }
    values.update(changes)
    return DashboardSelection(**values)


def render_dashboard(
    data: DashboardData,
    selection: DashboardSelection,
    payloads: Mapping[str, Mapping[str, Any]],
    streamlit_module: Any | None = None,
) -> DashboardSelection:
    """Render the four-screen shell; returns the effective selection."""

    ui = _ui(streamlit_module)
    _call(ui, "set_page_config", page_title="TopoMarket research", layout="wide")
    _call(ui, "markdown", motion_css(), unsafe_allow_html=True)

    sidebar = _sidebar(ui)
    _call(sidebar, "header", "TopoMarket")
    _call(sidebar, "caption", f"Profile: {data.profile}")
    _call(sidebar, "caption", f"Snapshot: {data.snapshot_id or 'demo'}")

    screen_index = SCREEN_ORDER.index(selection.screen) if selection.screen in SCREEN_ORDER else 0
    screen_value = _call(
        sidebar,
        "selectbox",
        "Screen",
        [SCREEN_LABELS[name] for name in SCREEN_ORDER],
        index=screen_index,
        key="tm_screen_label",
    )
    screen = _screen_from_label(screen_value) if screen_value is not None else selection.screen
    selection = _replace_selection(selection, screen=screen)

    mode_index = 1 if selection.mode == REPLAY else 0
    mode_value = _call(
        sidebar,
        "radio",
        "Mode",
        ["latest", "replay"],
        index=mode_index,
        key="tm_mode_label",
    )
    mode = REPLAY if str(mode_value).lower().startswith("replay") else LIVE
    selection = _replace_selection(selection, mode=mode)

    session_options = list(data.session_dates) or [""]
    date_index = (
        session_options.index(selection.date)
        if selection.date in session_options
        else len(session_options) - 1
    )
    date_value = _call(
        sidebar,
        "selectbox",
        "Selected session",
        session_options,
        index=date_index,
        key="tm_date_select",
    )
    if date_value:
        selection = _replace_selection(selection, date=str(date_value))

    replay_presets = [
        value
        for value in ("2020-03-16", "2020-03-13", "2008-10-10", "2008-09-15")
        if value in data.session_dates
    ]
    if replay_presets:
        _call(sidebar, "caption", "Replay presets")
        for preset in replay_presets:
            label = f"Jump to {preset}"
            if _call(sidebar, "button", label, key=f"tm_preset_{preset}"):
                selection = _replace_selection(selection, date=preset, mode=REPLAY)

    if _call(sidebar, "button", "◀ Previous session"):
        try:
            selection = previous_session(selection)
        except Exception:  # noqa: BLE001 - boundary keeps the selection unchanged
            pass
    if _call(sidebar, "button", "Next session ▶"):
        try:
            selection = next_session(selection)
        except Exception:  # noqa: BLE001 - boundary keeps the selection unchanged
            pass

    if selection.mode == REPLAY:
        if not selection.reveal:
            if _call(sidebar, "button", "Reveal next 20 sessions"):
                selection = toggle_reveal(selection)
        else:
            if _call(sidebar, "button", "Hide outcome (blind view)"):
                selection = toggle_blind(selection)

    with _expander(sidebar, "Advanced controls") as advanced:
        member_options = ["(none)"] + list(_loaded_context(data)["members"])
        member_index = (
            member_options.index(selection.member) if selection.member in member_options else 0
        )
        member_value = _call(
            advanced,
            "selectbox",
            "Industry member",
            member_options,
            index=member_index,
            key="tm_member_select",
        )
        if member_value and member_value != "(none)":
            selection = _replace_selection(selection, member=str(member_value))
        run_ids = [str(run.get("run_id")) for run in data.evaluation_runs]
        if run_ids:
            run_index = run_ids.index(selection.run) if selection.run in run_ids else 0
            run_value = _call(
                advanced,
                "selectbox",
                "Evaluation run",
                run_ids,
                index=run_index,
                key="tm_run_select",
            )
            if run_value:
                selection = _replace_selection(selection, run=str(run_value))
        _call(advanced, "checkbox", "Show 3D cloud (optional)", value=False, key="tm_3d")
        command = _call(advanced, "text_input", "Keyboard command", key="tm_keyboard")
        if command:
            try:
                selection = apply_keyboard_action(str(command), selection)
            except Exception as error:  # noqa: BLE001 - readable UI error
                _call(ui, "warning", f"Unknown keyboard command {command!r}: {error}")

    _call(ui, "title", "TopoMarket research")
    _call(
        ui,
        "caption",
        f"Snapshot: {data.snapshot_id or 'demo'} · window {DEFAULT_WINDOW} sessions",
    )
    _call(ui, "caption", f"Selected session: {selection.date or 'none'}")

    if screen == "overview":
        render_observation_panel(ui, payloads.get("overview", {}))
    elif screen == "topology":
        render_topology_panel(ui, payloads.get("topology", {}))
    elif screen == "validation":
        render_validation_panel(ui, payloads.get("validation", {}))
    elif screen == "data":
        render_data_panel(ui, payloads.get("data", {}))
    else:  # pragma: no cover - selection validation prevents this
        _call(ui, "error", f"Unknown screen {screen!r}")

    _call(
        ui,
        "caption",
        "Keyboard: Alt+Left/Right date, Alt+PageUp/PageDown window, Alt+R reveal, "
        "Alt+B blind, Alt+M member.",
    )
    return selection


def render_observation_panel(ui: Any, payload: Mapping[str, Any]) -> None:
    """Render the Overview screen."""

    _call(ui, "subheader", "Overview")
    score = payload.get("score") or {}
    columns = _call(ui, "columns", 3) or []
    if columns and len(columns) >= 3:
        _call(columns[0], "metric", "Selected session", payload.get("date", "—"))
        percentile = score.get("percentile_units")
        _call(
            columns[1],
            "metric",
            "Score percentile",
            "unavailable" if percentile is None else f"{percentile:.1f}",
        )
        cutoff = (score.get("cutoff_status") or {}).get("state", "unavailable")
        _call(columns[2], "metric", "Cutoff status", cutoff)
    else:
        _call(ui, "markdown", f"**Selected session:** {payload.get('date', '—')}")

    history = payload.get("score_history") or []
    if len(history) >= 2:
        _call(
            ui,
            "line_chart",
            {
                "date": [item["date"] for item in history],
                "score percentile": [item["score"] for item in history],
            },
            x="date",
            y="score percentile",
        )
        cutoff = (score.get("cutoff_status") or {}).get("cutoff")
        if cutoff is not None:
            _call(ui, "caption", f"Frozen cutoff: {cutoff:.1f} percentile")
    horizon = payload.get("horizon") or {}
    _call(
        ui,
        "markdown",
        f"Outcome horizon: {horizon.get('sessions', 0)}/{horizon.get('required', OUTCOME_HORIZON)} "
        f"sessions · pending: {bool(horizon.get('pending'))}",
    )
    if int(horizon.get("sessions", 0)) == 0:
        _call(
            ui,
            "info",
            "This is the latest available session, so there are no future sessions to reveal. "
            "Choose an earlier session or a replay preset to inspect a historical alert.",
        )
    replay = payload.get("replay") or {}
    if replay.get("blind"):
        _call(ui, "info", "Blind replay: outcome layer hidden until you reveal it.")
    elif replay.get("revealed"):
        _call(ui, "warning", "Outcome layer revealed for this replay selection only.")
    evidence = payload.get("evidence") or {}
    if evidence.get("wording"):
        _call(ui, "markdown", f"**Evidence:** {evidence['wording']}")
    _call(ui, "markdown", f"_{payload.get('accessible_summary', '')}_")


def render_topology_panel(ui: Any, payload: Mapping[str, Any]) -> None:
    """Render the Topology screen."""

    _call(ui, "subheader", "Topology")
    if not payload.get("available"):
        _call(ui, "info", payload.get("reason", "Window unavailable"))
        return
    window = payload.get("window") or []
    _call(
        ui,
        "caption",
        f"Window: {window[0] if window else '—'} … {window[-1] if window else '—'} "
        f"({len(window)} sessions)",
    )
    cloud = payload.get("cloud") or {}
    projection = cloud.get("pca") or []
    if projection:
        table = {
            "t": list(range(len(projection))),
            "x": [row[0] if row else None for row in projection],
            "y": [row[1] if len(row) > 1 else None for row in projection],
        }
        _call(ui, "line_chart", table)
    else:
        _call(ui, "info", "No 2D projection available for this window.")
    mapper = payload.get("mapper") or {}
    nodes = mapper.get("nodes") or []
    _call(
        ui,
        "markdown",
        f"Mapper nodes: {len(nodes)} · edges: {len(mapper.get('edges') or [])}",
    )
    if nodes:
        _call(
            ui,
            "dataframe",
            [
                {
                    "node": node.get("id"),
                    "members": ", ".join(node.get("members") or ()),
                    "correlations": str(node.get("member_correlations")),
                }
                for node in nodes
            ],
        )
    inspector = payload.get("member_inspector") or {}
    _call(ui, "markdown", f"**Selected member:** {inspector.get('member') or '—'}")
    _call(ui, "caption", f"Node: {inspector.get('node_id') or '—'}")
    outcome = payload.get("outcome")
    if outcome:
        _call(ui, "warning", "Outcome layer revealed (replay only).")
        _call(
            ui,
            "dataframe",
            [
                {"date": date, "close": close}
                for date, close in zip(
                    outcome.get("dates") or [], outcome.get("closes") or [], strict=False
                )
            ],
        )
    else:
        _call(ui, "info", "Blind view: outcomes hidden.")
    _call(ui, "markdown", f"_{payload.get('accessible_summary', '')}_")


def render_validation_panel(ui: Any, payload: Mapping[str, Any]) -> None:
    """Render the Validation screen."""

    _call(ui, "subheader", "Validation")
    if not payload.get("available"):
        _call(ui, "info", payload.get("empty_state", "No frozen evaluation run"))
        return
    evidence = payload.get("evidence") or {}
    _call(
        ui,
        "markdown",
        f"**Evidence:** {evidence.get('wording')} · run {payload.get('run_id')}",
    )
    metrics = payload.get("metrics") or {}
    _call(
        ui,
        "dataframe",
        [
            {
                "method": method,
                "episode_recall": value.get("episode_recall"),
                "false_per_year": value.get("false_alerts_per_year"),
                "average_precision": value.get("average_precision"),
                "median_lead": value.get("median_lead_sessions"),
                "alerts": len(value.get("alerts") or ()),
            }
            for method, value in metrics.items()
        ],
    )
    table = payload.get("export_table") or {}
    if table.get("columns"):
        _call(
            ui,
            "dataframe",
            [dict(zip(table["columns"], row, strict=False)) for row in table.get("rows") or []],
        )
        _call(
            ui,
            "download_button",
            "Download evaluation table (CSV)",
            _to_csv(table["columns"], table.get("rows") or []),
            file_name="evaluation.csv",
            mime="text/csv",
        )
    _call(ui, "caption", str(payload.get("table_alternative", "")))


def render_data_panel(ui: Any, payload: Mapping[str, Any]) -> None:
    """Render the Data screen."""

    _call(ui, "subheader", "Data")
    _call(ui, "caption", f"Active snapshot: {payload.get('active_snapshot_id') or 'none'}")
    sources = payload.get("sources") or []
    if sources:
        _call(
            ui,
            "dataframe",
            [
                {
                    "source": source.get("source_id"),
                    "rows": source.get("row_count"),
                    "first": source.get("first_observation"),
                    "last": source.get("last_observation"),
                    "outcome": source.get("attempt_outcome"),
                }
                for source in sources
            ],
        )
    failures = payload.get("failures") or []
    if failures:
        _call(
            ui,
            "warning",
            f"{len(failures)} source failure(s): "
            + ", ".join(str(failure.get("source_id")) for failure in failures),
        )
    revisions = payload.get("revision_count", 0)
    _call(ui, "markdown", f"Revisions: {revisions}")
    if payload.get("snapshots"):
        _call(ui, "markdown", "Snapshots: " + ", ".join(payload["snapshots"]))
    _call(ui, "caption", str(payload.get("table_alternative", "")))


def _to_csv(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def plain_text_dashboard(
    data: DashboardData,
    selection: DashboardSelection,
    payloads: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Render a readable four-screen summary without Streamlit."""

    if payloads is None:
        payloads = PanelCache(data).get(selection)
    overview = payloads.get("overview") or {}
    topology = payloads.get("topology") or {}
    validation = payloads.get("validation") or {}
    data_payload = payloads.get("data") or {}
    evidence = validation.get("evidence") or {}
    lines = [
        "TopoMarket dashboard",
        f"Profile: {data.profile}",
        f"Snapshot: {data.snapshot_id or 'demo'}",
        f"Selected session: {selection.date or 'none'}",
        f"Screens: {', '.join(SCREEN_LABELS[name] for name in SCREEN_ORDER)}",
        "",
        "Overview",
        f"  Score percentile: {(overview.get('score') or {}).get('percentile_units')}",
        "  Cutoff status: "
        f"{(((overview.get('score') or {}).get('cutoff_status')) or {}).get('state')}",
        f"  Outcome horizon pending: {bool((overview.get('horizon') or {}).get('pending'))}",
        "",
        "Topology",
        f"  Window available: {bool(topology.get('available'))}",
        f"  Mapper nodes: {len((topology.get('mapper') or {}).get('nodes') or [])}",
        "",
        "Validation",
        f"  Frozen runs: {len(validation.get('runs') or [])}",
        f"  Evidence: {evidence.get('wording') or 'not available'}",
        "",
        "Data",
        f"  Sources: {len(data_payload.get('sources') or [])}",
        f"  Revisions: {data_payload.get('revision_count', 0)}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Shell entry point
# --------------------------------------------------------------------------- #
def _in_streamlit_runtime(streamlit_module: Any | None = None) -> bool:
    """Return whether the real Streamlit script runner is active."""

    ui = streamlit_module if streamlit_module is not None else st
    if ui is None:
        return False
    try:
        return bool(ui.runtime.exists())
    except Exception:  # pragma: no cover - defensive for alternative runtimes
        return False


def run_shell(args: argparse.Namespace, streamlit_module: Any | None = None) -> int:
    """Render the four-screen dashboard (or plain-text fallback)."""

    ui = streamlit_module if streamlit_module is not None else st
    try:
        data = load_dashboard_data(profile=args.profile, data_dir=args.data_dir)
    except (OSError, ValueError, DashboardDataError) as exc:
        if ui is not None and _in_streamlit_runtime(ui):
            ui.error(f"Could not load dashboard data: {exc}")
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    cache = PanelCache(data)
    if ui is None or not _in_streamlit_runtime(ui):
        selection = default_selection(data)
        print(plain_text_dashboard(data, selection, cache.get(selection)))
        return 0
    state = ui.session_state
    selection = selection_from_state(state, data)
    payloads = cache.get(selection)
    selection = render_dashboard(data, selection, payloads, ui)
    state["tm_screen"] = selection.screen
    state["tm_mode"] = selection.mode
    state["tm_date"] = selection.date
    state["tm_reveal"] = bool(selection.reveal)
    state["tm_member"] = selection.member
    state["tm_run"] = selection.run
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Streamlit shell (or a plain-text fallback) and return an exit code."""

    args = parse_args(argv)
    try:
        overview = build_overview(args.profile, data_dir=args.data_dir)
    except (OSError, ValueError) as exc:
        if st is not None and _in_streamlit_runtime(st):
            st.error(f"Could not load profile {args.profile!r}: {exc}")
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    if st is None:
        print(plain_text_overview(overview))
        print()
        return run_shell(args, streamlit_module=None)

    if not _in_streamlit_runtime(st):
        print(plain_text_overview(overview))
        print()
        return run_shell(args, streamlit_module=None)

    return run_shell(args, streamlit_module=st)


if __name__ == "__main__":
    if st is not None and (getattr(st, "__name__", "") == "streamlit" or _in_streamlit_runtime(st)):
        main()
    else:
        raise SystemExit(main())


__all__ = [
    "apply_action_to_state",
    "build_overview",
    "build_parser",
    "default_selection",
    "load_overview",
    "main",
    "parse_args",
    "plain_text_dashboard",
    "render_dashboard",
    "render_data_panel",
    "render_observation_panel",
    "render_overview",
    "render_topology_panel",
    "render_validation_panel",
    "run",
    "run_shell",
    "selection_from_state",
]

load_overview = build_overview
run = main
