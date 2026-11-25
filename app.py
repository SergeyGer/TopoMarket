#!/usr/bin/env python3
"""Streamlit shell and repository entry point for the v1.0 TopoMarket release.

The module can be imported without Streamlit installed. Streamlit is treated as
an optional UI dependency: its import is guarded and rendering falls back to
plain text when it is unavailable, which keeps CLI usage and smoke tests working
offline.

The shell renders the four release screens - **Structure** (landing),
**Replay**, **Validation** and **Data** - over one authoritative selection from
:mod:`topomarket.ui.panels`.  All analysis lives in the pure payload builders;
the shell only draws payloads with the chart helpers in
:mod:`topomarket.ui.charts`.  Plain ``streamlit run app.py`` opens the bundled
synthetic showcase with no flags; explicit ``--profile private`` commands remain
supported for local research.
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

try:  # matplotlib is a UI extra; the plain-text fallback must import without it.
    from topomarket.ui import charts  # noqa: E402
except ImportError:  # pragma: no cover - exercised by minimal installs
    charts = None  # type: ignore[assignment]
from topomarket.ui.accessibility import motion_css  # noqa: E402
from topomarket.ui.dashboard import (  # noqa: E402
    DEFAULT_NETWORK_VIEW,
    NETWORK_VIEWS,
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
from topomarket.ui.presets import build_presets  # noqa: E402

try:  # Streamlit is optional; importing app.py must work without it.
    import streamlit as st  # type: ignore[import-not-found]  # noqa: E402
except ImportError:  # pragma: no cover - exercised when Streamlit is absent
    st = None  # type: ignore[assignment]

SCREEN_ORDER = ("structure", "replay", "validation", "data")
DEFAULT_PROFILE = "demo"
DEFAULT_WINDOW = 60
PUBLIC_PROFILE = "demo"
SYNTHETIC_LABEL = "Synthetic demo"
KEYBOARD_HELP = (
    "Keyboard: Alt+Left/Right previous/next session, Alt+R reveal, Alt+B blind, Alt+M next member."
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the Streamlit shell entry point."""

    parser = argparse.ArgumentParser(
        prog="app.py",
        description=(
            "TopoMarket Streamlit shell. Plain `streamlit run app.py` opens the bundled "
            "synthetic showcase; use `--profile private` for local research data."
        ),
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default=DEFAULT_PROFILE,
        help="Profile to display (default: demo; the public synthetic showcase).",
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
    """Return the default public selection: Structure on a warmed-up scene."""

    presets = build_presets(data)
    context = _loaded_context(data)
    date = data.session_dates[-1] if data.session_dates else None
    mode = LIVE
    for record in presets.get("presets") or ():
        if record["preset_id"] == "stress_transition" and record.get("date"):
            date = record["date"]
            mode = REPLAY
            break
    return DashboardSelection(
        screen="structure",
        mode=mode,
        date=date,
        network_view=DEFAULT_NETWORK_VIEW,
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
    network_view = _state_value(state, "tm_network_view", DEFAULT_NETWORK_VIEW)
    edge = _state_value(state, "tm_edge", None) or None
    return DashboardSelection(
        screen=screen,
        mode=mode,
        date=date,
        reveal=reveal,
        member=member,
        run=run,
        network_view=network_view,
        edge=edge,
        **_context_kwargs(context),
    )


def _persist_selection(state: dict[str, Any], selection: DashboardSelection) -> None:
    state["tm_screen"] = selection.screen
    state["tm_mode"] = selection.mode
    state["tm_date"] = selection.date
    state["tm_reveal"] = bool(selection.reveal)
    state["tm_member"] = selection.member
    state["tm_run"] = selection.run
    state["tm_network_view"] = str(selection.network_view)
    state["tm_edge"] = selection.edge


def apply_action_to_state(
    state: dict[str, Any], action: str, data: DashboardData
) -> DashboardSelection:
    """Apply a keyboard action to session state and return the new selection."""

    selection = selection_from_state(state, data)
    updated = apply_keyboard_action(action, selection)
    _persist_selection(state, updated)
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


def _synthetic_label(ui: Any, data: DashboardData, selection: DashboardSelection) -> None:
    """Persistently label public synthetic data next to the selected date (UI01)."""

    if data.demo or data.profile == PUBLIC_PROFILE:
        _call(
            ui,
            "markdown",
            f"**{SYNTHETIC_LABEL}** · selected session **{selection.date or '—'}** · "
            f"fixture `{data.snapshot_id or 'showcase'}`",
        )
        _call(
            ui,
            "caption",
            "Synthetic data only. No genuine market data is published in this repository.",
        )
    else:
        _call(ui, "caption", f"Private research profile · selected session {selection.date or '—'}")


def _render_figure(
    ui: Any,
    figure: Any,
    *,
    caption: str,
    alt_text: str,
) -> None:
    """Render a chart with a textual alternative (UI04)."""

    image = getattr(ui, "pyplot", None)
    if image is not None:
        image(figure)
    else:  # pragma: no cover - fake UI objects in tests
        _call(ui, "caption", f"[chart: {alt_text}]")
    _call(ui, "caption", alt_text)
    if caption:
        _call(ui, "caption", caption)
    import matplotlib.pyplot as plt

    plt.close(figure)


def _apply_widgets(
    ui: Any,
    data: DashboardData,
    selection: DashboardSelection,
) -> tuple[DashboardSelection, dict[str, Any]]:
    """Render the sidebar and return the updated selection plus view options."""

    sidebar = _sidebar(ui)
    options: dict[str, Any] = {}
    _call(sidebar, "header", "TopoMarket")
    _call(sidebar, "caption", f"Profile: {data.profile} · release {__version__}")
    if data.snapshot_id:
        _call(sidebar, "caption", f"Snapshot: {data.snapshot_id}")
    if data.demo or data.profile == PUBLIC_PROFILE:
        _call(sidebar, "markdown", f"**{SYNTHETIC_LABEL}**")

    screen_index = SCREEN_ORDER.index(selection.screen) if selection.screen in SCREEN_ORDER else 0
    screen_value = _call(
        sidebar,
        "selectbox",
        "Screen",
        [SCREEN_LABELS[name] for name in SCREEN_ORDER],
        index=screen_index,
        key="tm_screen_label",
    )
    if screen_value is not None:
        screen = _screen_from_label(screen_value)
        selection = selection.replace(screen=screen)

    mode_index = 1 if str(selection.mode) == REPLAY else 0
    mode_value = _call(
        sidebar, "radio", "Mode", ["latest", "replay"], index=mode_index, key="tm_mode_label"
    )
    if mode_value is not None:
        mode = REPLAY if str(mode_value).lower().startswith("replay") else LIVE
        selection = selection.replace(mode=mode)

    dates = list(data.session_dates)
    if dates:
        index = dates.index(selection.date) if selection.date in dates else len(dates) - 1
        slider_value = _call(
            sidebar,
            "slider",
            "Selected session",
            min_value=0,
            max_value=len(dates) - 1,
            value=index,
            key="tm_session_index",
            help="The authoritative selected session for every panel.",
        )
        if slider_value is not None and int(slider_value) != index:
            selection = selection.with_date(dates[int(slider_value)])
        alert_options = _alert_dates(data, selection)
        if alert_options:
            alert_labels = ["(jump to an alert)"] + alert_options
            alert_value = _call(
                sidebar, "selectbox", "Jump to an alert", alert_labels, key="tm_alert_jump"
            )
            applied = ui.session_state.get("tm_alert_jump_applied")
            if alert_value and alert_value != alert_labels[0] and alert_value != applied:
                selection = selection.with_date(str(alert_value)).replace(mode=REPLAY)
                ui.session_state["tm_alert_jump_applied"] = alert_value
        if _call(sidebar, "button", "◀ Previous session", key="tm_prev_session"):
            try:
                selection = previous_session(selection)
            except Exception:  # noqa: BLE001 - boundary keeps the selection unchanged
                pass
        if _call(sidebar, "button", "Next session ▶", key="tm_next_session"):
            try:
                selection = next_session(selection)
            except Exception:  # noqa: BLE001 - boundary keeps the selection unchanged
                pass

    presets = build_presets(data)
    if presets.get("available"):
        _call(sidebar, "markdown", "**Demo presets**")
        for record in presets["presets"]:
            if not record["verified"]:
                _call(sidebar, "caption", f"{record['label']}: {record['reason']}")
                continue
            if _call(
                sidebar,
                "button",
                f"{record['label']} · {record['date']}",
                key=f"tm_preset_{record['preset_id']}",
                help=record["description"],
            ):
                selection = (
                    selection.with_date(record["date"])
                    .replace(mode=record["mode"])
                    .replace(screen="structure")
                )

    if selection.screen == "structure":
        view_index = (
            NETWORK_VIEWS.index(str(selection.network_view))
            if str(selection.network_view) in NETWORK_VIEWS
            else 0
        )
        view_value = _call(
            sidebar,
            "radio",
            "Network view",
            ["Correlation map", "Mapper groups"],
            index=view_index,
            key="tm_view_label",
        )
        if view_value is not None:
            selection = selection.with_network_view(
                "correlation" if str(view_value).startswith("Correlation") else "mapper"
            )

    if selection.screen == "replay":
        if not selection.reveal:
            if _call(
                sidebar, "button", f"Reveal next {OUTCOME_HORIZON} sessions", key="tm_reveal_action"
            ):
                selection = toggle_reveal(selection)
        else:
            if _call(sidebar, "button", "Hide outcome (blind view)", key="tm_blind_action"):
                selection = toggle_blind(selection)

    with _expander(sidebar, "Inspectors and advanced controls") as advanced:
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
            selection = selection.replace(member=str(member_value))
        elif selection.member:
            selection = selection.replace(member=None)
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
                selection = selection.replace(run=str(run_value))
        command = _call(advanced, "text_input", "Keyboard command", key="tm_keyboard")
        if command:
            try:
                selection = apply_keyboard_action(str(command), selection)
            except Exception as error:  # noqa: BLE001 - readable UI error
                _call(ui, "warning", f"Unknown keyboard command {command!r}: {error}")
    options["presets"] = presets
    return selection, options


def _screen_from_label(value: Any) -> str:
    text = str(value).strip().lower()
    for name, label in SCREEN_LABELS.items():
        if text == label.lower():
            return name
    return text if text in SCREEN_ORDER else "structure"


def _alert_dates(data: DashboardData, selection: DashboardSelection) -> list[str]:
    metrics = data.primary_metrics()
    alerts = sorted(str(value) for value in metrics.get("alerts") or ())
    return [alert for alert in alerts if selection.date is None or alert <= selection.date]


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
    selection, _options = _apply_widgets(ui, data, selection)
    _persist_selection(ui.session_state, selection)
    screens = {name: payloads.get(name) or {} for name in SCREEN_ORDER}
    if selection.screen == "structure":
        render_structure_screen(ui, data, selection, screens["structure"])
    elif selection.screen == "replay":
        render_replay_screen(ui, data, selection, screens["replay"])
    elif selection.screen == "validation":
        render_validation_screen(ui, data, selection, screens["validation"])
    elif selection.screen == "data":
        render_data_screen(ui, data, selection, screens["data"])
    else:  # pragma: no cover - selection validation prevents this
        _call(ui, "error", f"Unknown screen {selection.screen!r}")
    _call(ui, "caption", KEYBOARD_HELP)
    return selection


# --------------------------------------------------------------------------- #
# Screen renderers
# --------------------------------------------------------------------------- #
def render_structure_screen(
    ui: Any, data: DashboardData, selection: DashboardSelection, payload: Mapping[str, Any]
) -> None:
    """Render the public Structure landing screen."""

    _call(ui, "title", "TopoMarket research")
    _synthetic_label(ui, data, selection)
    map_obs = payload.get("map_observation") or {}
    if map_obs.get("stale"):
        _call(
            ui,
            "warning",
            f"Industry snapshot shown: {map_obs.get('date')} "
            f"({map_obs.get('lag_sessions', 0)} session(s) behind the selected date).",
        )
    network = payload.get("network") or {}
    mapper = payload.get("mapper") or {}
    score = payload.get("score") or {}
    if str(selection.network_view) == "mapper":
        _call(ui, "subheader", "Mapper groups")
        figure = charts.mapper_figure(
            mapper,
            selected_node_id=mapper.get("selected_node_id"),
            selected_edge_id=(mapper.get("selected_edge") or {}).get("edge_id"),
        )
        _render_figure(
            ui,
            figure,
            caption=str(mapper.get("position_rule") or ""),
            alt_text=str(mapper.get("table_alternative") or "Mapper groups")[:4000],
        )
        inspector = mapper.get("member_inspector") or {}
        if inspector.get("members"):
            _call(
                ui,
                "dataframe",
                [
                    {
                        "member": member["label"],
                        "volatility": member.get("volatility"),
                        "within-group correlation": member.get("within_group_correlation"),
                    }
                    for member in inspector["members"]
                ],
            )
        with _expander(ui, "Mapper table (keyboard equivalent)") as table_area:
            _call(table_area, "text", str(mapper.get("table_alternative") or ""))
    else:
        _call(ui, "subheader", "Industry correlation network")
        figure = charts.correlation_network_figure(network, selected_code=selection.member)
        _render_figure(
            ui,
            figure,
            caption=str(network.get("summary") or ""),
            alt_text=str(network.get("summary") or "Correlation network"),
        )
        inspector = payload.get("member_inspector") or {}
        if selection.member and inspector.get("pairs"):
            _call(
                ui,
                "markdown",
                f"**Selected portfolio:** {inspector.get('label')} "
                f"· {inspector.get('degree')} qualifying pair(s)",
            )
            _call(
                ui,
                "dataframe",
                [
                    {
                        "portfolio": pair["label"],
                        "correlation": pair["correlation"],
                        "above cutoff": pair["qualifies"],
                    }
                    for pair in inspector["pairs"]
                ],
            )
        if network.get("undefined_pairs"):
            _call(
                ui,
                "caption",
                f"{len(network['undefined_pairs'])} pair(s) have undefined correlations "
                "(zero-variance series) and are not drawn.",
            )

    _call(ui, "subheader", "Shared timeline")
    timeline = payload.get("timeline") or {}
    _render_figure(
        ui,
        charts.timeline_figure(timeline),
        caption=str(timeline.get("legend") or ""),
        alt_text=(
            f"Aligned S&P 500, VIX and score panels for the trailing "
            f"{timeline.get('window_sessions', 0)} sessions ending {timeline.get('selected')}; "
            f"threshold {timeline.get('threshold')}; "
            f"{len(timeline.get('alert_markers') or ())} alert marker(s)."
        ),
    )
    explanation = payload.get("explanation") or {}
    _call(ui, "subheader", "Score explanation")
    if explanation.get("available"):
        _call(
            ui,
            "caption",
            "60-return Takens window · dimension 3 · lag 2 · 56 points · "
            "full-dimensional persistence; the scatter is a 2-D display projection.",
        )
        columns = _call(ui, "columns", 2) or []
        if columns and len(columns) >= 2:
            with columns[0]:
                _render_figure(
                    ui,
                    charts.takens_figure(explanation),
                    caption=str(explanation.get("display_note") or ""),
                    alt_text="2-D display-coordinate scatter of the 56-point price embedding.",
                )
            with columns[1]:
                _render_figure(
                    ui,
                    charts.h1_figure(explanation),
                    caption="H1 birth-death diagram with the diagonal reference and longest "
                    "finite lifetime highlighted.",
                    alt_text="H1 birth-death diagram; longest finite lifetime in amber.",
                )
        else:  # pragma: no cover - fake UI without columns
            _render_figure(ui, charts.takens_figure(explanation), caption="", alt_text="Takens")
        if explanation.get("industry_pca"):
            columns = _call(ui, "columns", 2) or []
            target = columns[0] if columns else ui
            _render_figure(
                target,
                charts.pca_figure(explanation),
                caption="Industry PCA display coordinates; each point is one session.",
                alt_text="Industry PCA scatter, one point per session, map date highlighted.",
            )
    else:
        _call(ui, "caption", explanation.get("reason") or "No score explanation for this session.")
    score_text = (
        "unavailable"
        if score.get("value") is None
        else f"{float(score['value']):.1f} percentile (comparative)"
    )
    cutoff = (score.get("cutoff_status") or {}).get("cutoff")
    _call(
        ui,
        "caption",
        f"Selected session {selection.date}: score {score_text}; "
        f"frozen threshold {cutoff if cutoff is not None else 'not available'}.",
    )


def render_replay_screen(
    ui: Any, data: DashboardData, selection: DashboardSelection, payload: Mapping[str, Any]
) -> None:
    """Render the Replay screen with blind/revealed outcome layers."""

    _call(ui, "title", "Replay")
    _synthetic_label(ui, data, selection)
    score = payload.get("score") or {}
    columns = _call(ui, "columns", 3) or []
    if columns and len(columns) >= 3:
        _call(
            columns[0],
            "metric",
            "Selected session",
            selection.date or "—",
            help="The single authoritative session for every panel.",
        )
        _call(
            columns[1],
            "metric",
            "Score percentile (comparative)",
            "unavailable" if score.get("value") is None else f"{float(score['value']):.1f}",
        )
        _call(
            columns[2],
            "metric",
            "Frozen threshold",
            cutoff if (cutoff := score.get("cutoff")) is not None else "not available",
        )
    alert = payload.get("alert") or {}
    if alert.get("is_alert"):
        _call(ui, "markdown", f"**Alert status:** {alert.get('label')} ({alert.get('status')})")
    _render_figure(
        ui,
        charts.replay_figure(payload),
        caption=str(payload.get("legend") or ""),
        alt_text=str(payload.get("accessible_summary") or "Replay chart"),
    )
    if payload.get("blind"):
        _call(
            ui,
            "info",
            "Blind replay: only observations available on the selected date are shown. "
            f"Press “Reveal next {OUTCOME_HORIZON} sessions” or Alt+R to add the outcome layer.",
        )
    else:
        outcome = payload.get("outcome") or {}
        if outcome:
            _call(ui, "markdown", f"**{outcome.get('outcome_label')}**")
            metrics = _call(ui, "columns", 5) or []
            values = [
                ("Origin close", outcome.get("origin", {}).get("close")),
                ("10% boundary", outcome.get("boundary", {}).get("close")),
                ("Lowest close", outcome.get("lowest", {}).get("close")),
                (
                    "First breach",
                    (outcome.get("first_breach") or {}).get("date") or "none",
                ),
                (
                    "Maximum decline",
                    None
                    if outcome.get("max_decline_pct") is None
                    else f"{outcome['max_decline_pct']:.2f}%",
                ),
            ]
            for column, (label, value) in zip(metrics, values, strict=False):
                _call(column, "metric", label, "—" if value is None else value)
            if outcome.get("pending"):
                _call(
                    ui,
                    "warning",
                    f"Pending outcome: {outcome.get('horizon_sessions')}/"
                    f"{outcome.get('required_sessions')} sessions observed.",
                )
            else:
                _call(ui, "caption", "Hide outcome (Alt+B) to return to the blind view.")
        else:
            _call(ui, "caption", "No outcome layer is available for this session.")
    evidence = payload.get("evidence") or {}
    if evidence.get("wording"):
        _call(
            ui, "caption", f"Evidence wording: {evidence.get('wording')} (experiment, not advice)."
        )


def render_validation_screen(
    ui: Any, data: DashboardData, selection: DashboardSelection, payload: Mapping[str, Any]
) -> None:
    """Render the Validation screen with corrected evaluation evidence."""

    _call(ui, "title", "Validation")
    _synthetic_label(ui, data, selection)
    if not payload.get("available"):
        _call(ui, "info", payload.get("empty_state", "No frozen evaluation run"))
        return
    evidence = payload.get("evidence") or {}
    _call(ui, "subheader", str(evidence.get("wording") or "Experimental market anomaly"))
    _call(
        ui,
        "markdown",
        "The forecast is an experiment; the score percentile is a comparative score. "
        "Event prevalence and false-alert rates are reported so the evidence can be judged.",
    )
    sample = payload.get("sample_size") or {}
    rate = payload.get("false_alert_rate")
    _call(
        ui,
        "caption",
        f"Run {payload.get('run_id')} · snapshot {payload.get('snapshot_id')} · package "
        f"{payload.get('package_version')} · holdout {payload.get('periods', {}).get('test')} · "
        f"evaluable episodes {sample.get('episode_count')} · eligible sessions "
        f"{sample.get('eligible_sessions')} · false alerts/year "
        f"{'n/a' if rate is None else f'{float(rate):.2f}'}",
    )
    metrics = payload.get("metrics") or {}
    if metrics:
        _call(
            ui,
            "dataframe",
            [
                {
                    "method": method,
                    "episode recall": value.get("episode_recall"),
                    "matched episodes": value.get("matched_count"),
                    "average precision": value.get("average_precision"),
                    "false alerts/year": value.get("false_alerts_per_year"),
                    "median lead (sessions)": value.get("median_lead_sessions"),
                    "eligible sessions": value.get("eligible_sessions"),
                    "alerts": len(value.get("alerts") or ()),
                }
                for method, value in metrics.items()
            ],
        )
    limitations = evidence.get("limitations") or ()
    if limitations:
        _call(ui, "markdown", "**Limitations**")
        for limitation in limitations:
            _call(ui, "markdown", f"- {limitation}")
    table = payload.get("export_table") or {}
    if table.get("columns"):
        with _expander(ui, "Alert and episode evidence") as evidence_area:
            _call(
                evidence_area,
                "dataframe",
                [dict(zip(table["columns"], row, strict=False)) for row in table.get("rows") or ()],
            )
            _call(
                evidence_area,
                "download_button",
                "Download evaluation table (CSV)",
                _to_csv(table["columns"], table.get("rows") or []),
                file_name="evaluation.csv",
                mime="text/csv",
            )
        _call(ui, "caption", str(payload.get("table_alternative", "")))
    _call(ui, "caption", str(payload.get("percentile_note", "")))


def render_data_screen(
    ui: Any, data: DashboardData, selection: DashboardSelection, payload: Mapping[str, Any]
) -> None:
    """Render the Data screen with independent calendars and source status."""

    _call(ui, "title", "Data")
    _synthetic_label(ui, data, selection)
    calendars = payload.get("calendars") or {}
    if calendars:
        _call(
            ui,
            "dataframe",
            [
                {
                    "calendar": label,
                    "observations": calendars[calendar_id]["observations"],
                    "first": calendars[calendar_id]["first"],
                    "last": calendars[calendar_id]["last"],
                    "gaps": calendars[calendar_id]["gaps"],
                    "status": calendars[calendar_id]["status"],
                }
                for calendar_id, label in (
                    ("price", "S&P 500 price"),
                    ("vix", "VIX"),
                    ("industry", "Industry returns"),
                )
                if calendar_id in calendars
            ],
        )
    if payload.get("map_lags_price"):
        _call(
            ui,
            "warning",
            "The industry calendar lags the price calendar; the map shows the last complete "
            "industry snapshot and labels the date actually shown.",
        )
    for note in payload.get("notes") or ():
        _call(ui, "caption", note)
    _call(ui, "markdown", f"**Score coverage:** {payload.get('scores')}")
    sources = payload.get("sources") or ()
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
                    "last success": source.get("last_success_at"),
                    "outcome": source.get("outcome"),
                    "error": source.get("error"),
                }
                for source in sources
            ],
        )
    failures = payload.get("failures") or ()
    if failures:
        _call(ui, "warning", f"{len(failures)} source failure(s) recorded for the last refresh.")
    _call(ui, "markdown", f"Revisions: {payload.get('revision_count', 0)}")
    if payload.get("refresh_available"):
        if _call(ui, "button", str(payload.get("refresh_action", "Run validated refresh"))):
            _run_private_refresh(ui, data)
    else:
        _call(ui, "caption", str(payload.get("refresh_action", "Read-only public demo")))
    refresh = payload.get("refresh") or {}
    _call(
        ui,
        "caption",
        f"Last refresh: {refresh.get('updated_at_utc') or 'never'} · "
        f"published: {refresh.get('published')} · error: {refresh.get('error') or 'none'}",
    )
    _call(ui, "caption", str(payload.get("table_alternative", "")))


def _run_private_refresh(ui: Any, data: DashboardData) -> None:
    """Run the validated private refresh pipeline from the Data screen (DA01)."""

    try:  # Local import keeps the public demo import graph small.
        from topomarket.data.refresh import refresh_sources
    except ImportError as error:  # pragma: no cover - defensive
        _call(ui, "error", f"Refresh pipeline unavailable: {error}")
        return
    spinner = getattr(ui, "spinner", None)
    context = spinner("Running validated refresh…") if spinner is not None else _NullContext(ui)
    try:
        with context:
            report = refresh_sources(data.data_dir)
        _call(ui, "success", f"Refresh finished: {report}")
    except Exception as error:  # noqa: BLE001 - surface refresh failures to the operator
        _call(ui, "error", f"Refresh failed; the last valid snapshot stays active: {error}")


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
    structure = payloads.get("structure") or {}
    replay = payloads.get("replay") or {}
    validation = payloads.get("validation") or {}
    data_payload = payloads.get("data") or {}
    score = structure.get("score") or {}
    network = structure.get("network") or {}
    lines = [
        "TopoMarket dashboard",
        f"Release: {__version__}",
        f"Profile: {data.profile}",
        f"Snapshot: {data.snapshot_id or 'demo'}",
        f"Selected session: {selection.date or 'none'}",
        f"Screens: {', '.join(SCREEN_LABELS[name] for name in SCREEN_ORDER)}",
        "",
        "Structure",
        f"  Correlation network: {network.get('pairs_qualifying')}/{network.get('pairs_total')} "
        f"pairs at r >= {network.get('cutoff')}",
        f"  Mapper groups: {len((structure.get('mapper') or {}).get('nodes') or [])}",
        f"  Timeline alerts: {len((structure.get('timeline') or {}).get('alert_markers') or [])}",
        f"  Score percentile: {score.get('value')}",
        "",
        "Replay",
        f"  Blind: {replay.get('blind')} · revealed: {replay.get('revealed')}",
        "  Outcome: "
        + (str(replay["outcome"].get("outcome_label")) if replay.get("outcome") else "hidden"),
        "",
        "Validation",
        f"  Evidence: {validation.get('wording') or 'not available'}",
        f"  Evaluable episodes: {(validation.get('sample_size') or {}).get('episode_count')}",
        f"  False alerts/year: {validation.get('false_alert_rate')}",
        "",
        "Data",
        f"  Calendars: {', '.join((data_payload.get('calendars') or {}).keys())}",
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
    _persist_selection(state, selection)
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
    "render_data_screen",
    "render_replay_screen",
    "render_structure_screen",
    "render_validation_screen",
    "run",
    "run_shell",
    "selection_from_state",
]

load_overview = build_overview
run = main
