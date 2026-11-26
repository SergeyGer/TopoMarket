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

try:  # UI extras; the plain-text fallback must import without them.
    from topomarket.ui import (
        charts,  # noqa: E402
        interactive,  # noqa: E402
    )
except ImportError:  # pragma: no cover - exercised by minimal installs
    charts = None  # type: ignore[assignment]
    interactive = None  # type: ignore[assignment]
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
from topomarket.ui.structure import build_window_comparison  # noqa: E402

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
    members = list(getattr(data, "members", ()) or ())
    if not members:
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
    node = _state_value(state, "tm_node", None) or None
    return DashboardSelection(
        screen=screen,
        mode=mode,
        date=date,
        reveal=reveal,
        member=member,
        run=run,
        network_view=network_view,
        edge=edge,
        node=node,
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
    state["tm_node"] = selection.node


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


CHART_CACHE_KEY = "tm_chart_cache"
CHART_CACHE_LIMIT = 120


def _chart_cache(ui: Any) -> dict[str, bytes] | None:
    """Return the per-session rendered-chart cache (works with Streamlit proxies)."""

    state = getattr(ui, "session_state", None)
    if state is None:
        return None
    try:
        store = state.get(CHART_CACHE_KEY)
    except Exception:  # pragma: no cover - defensive for session-state proxies
        return None
    if not isinstance(store, dict):
        store = {}
        try:
            state[CHART_CACHE_KEY] = store
        except Exception:  # pragma: no cover - read-only session state
            return None
    return store


def _render_figure(
    ui: Any,
    figure_factory: Any,
    *,
    caption: str,
    alt_text: str,
    cache_key: str | None = None,
) -> None:
    """Render a chart with a textual alternative, caching the rendered PNG bytes.

    The chart preparation is the expensive part of a date change; caching the PNG
    bytes per payload identity keeps a cached navigation at the Streamlit rerun
    floor (CL02) without changing the rendered image.
    """

    store = _chart_cache(ui) if cache_key is not None else None
    if store is not None and cache_key in store:
        # Cache hit: do not build the matplotlib figure at all.
        _call(ui, "image", store[cache_key])
        _call(ui, "caption", alt_text)
        if caption:
            _call(ui, "caption", caption)
        return
    figure = figure_factory() if callable(figure_factory) else figure_factory
    image = getattr(ui, "pyplot", None)
    if image is not None:
        image(figure)
    else:  # pragma: no cover - fake UI objects in tests
        _call(ui, "caption", f"[chart: {alt_text}]")
    if store is not None and cache_key is not None:
        try:
            store[cache_key] = charts.figure_png_bytes(figure)
            while len(store) > CHART_CACHE_LIMIT:
                store.pop(next(iter(store)))
        except Exception:  # pragma: no cover - cache failures must not break rendering
            pass
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
        current = selection.date if selection.date in dates else dates[-1]
        # The widget key is scoped to the current session date: a programmatic
        # date change (preset, alert jump, previous/next) must not be reverted by
        # the widget's retained state on the next rerun.
        slider_value = _call(
            sidebar,
            "select_slider",
            "Selected session",
            options=dates,
            value=current,
            key=f"tm_session_index::{selection.date}",
            help="The authoritative selected session for every panel.",
        )
        if slider_value and str(slider_value) != selection.date:
            selection = selection.with_date(str(slider_value))
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
    blind = str(getattr(selection, "mode", "live")).lower() in {
        "replay",
        "historical",
    } and not bool(getattr(selection, "reveal", False))
    if presets.get("available"):
        _call(sidebar, "markdown", "**Demo presets**")
        for record in presets["presets"]:
            preset_label = (
                record.get("blind_label") or record["label"]
                if blind
                else record.get("review_label") or record["label"]
            )
            preset_description = (
                record.get("blind_description") or record["description"]
                if blind
                else record.get("review_description") or record["description"]
            )
            if not record["verified"]:
                _call(sidebar, "caption", f"{preset_label}: {record['reason']}")
                continue
            if _call(
                sidebar,
                "button",
                f"{preset_label} · {record['date']}",
                key=f"tm_preset_{record['preset_id']}",
                help=preset_description,
            ):
                selection = (
                    selection.with_date(record["date"])
                    .replace(mode=record["mode"])
                    .replace(screen="structure")
                )
            if record.get("teaching") and not blind:
                _call(
                    sidebar,
                    "caption",
                    "Recorded late alert inside the frozen evaluation: episode onset 2025-03-06; "
                    "zero early-warning credit.",
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
        if str(selection.network_view) == "mapper":
            selection = _apply_mapper_edge_selector(sidebar, data, selection)

    if selection.screen == "structure" and presets.get("available"):
        _call(sidebar, "markdown", "**Guided tour**")
        steps = _guided_steps(presets, data)
        state = ui.session_state
        started = GUIDE_STEP_KEY in state
        step_index = int(state.get(GUIDE_STEP_KEY, 0) or 0) % max(1, len(steps))
        changed = False
        if _call(sidebar, "button", "Guided: back", key="tm_guide_prev"):
            step_index = (len(steps) - 1) if not started else (step_index - 1) % max(1, len(steps))
            changed = True
        if _call(sidebar, "button", "Guided: next step ▶", key="tm_guide_next"):
            step_index = 0 if not started else (step_index + 1) % max(1, len(steps))
            changed = True
        if changed:
            state[GUIDE_STEP_KEY] = step_index
            started = True
            selection = _apply_guided_step(selection, steps[step_index])
            step = steps[step_index]
            if step.get("compare"):
                state[COMPARE_TOGGLE_KEY] = True
                state[COMPARE_DATE_KEY] = step.get("compare_date")
        step = steps[step_index]
        if not started:
            _call(
                sidebar,
                "caption",
                "Guided tour not started. Next step opens the synthetic market shift "
                "(29/66 -> 66/66); Back/Next move through Quiet, Stress, Explain and Replay.",
            )
        elif str(selection.date) != str(step.get("date")):
            _call(
                sidebar,
                "caption",
                f"Guided tour paused: current selection differs from step "
                f"{step_index + 1}/{len(steps)} ({step['name']}). Next resumes the tour.",
            )
        else:
            _call(
                sidebar,
                "caption",
                f"Guided step {step_index + 1}/{len(steps)}: {step['name']}. {step['description']}",
            )
        if blind_structure_state(selection):
            state[COMPARE_TOGGLE_KEY] = False
            state.pop(COMPARE_DATE_KEY, None)
            _call(
                sidebar,
                "caption",
                "Blind replay: both windows and all annotations stay capped at the selected "
                "session. Reveal the outcome to enable the retrospective two-window comparison.",
            )
            compare_on = False
        else:
            compare_on = _call(
                sidebar,
                "checkbox",
                "Compare two windows",
                value=bool(state.get(COMPARE_TOGGLE_KEY, False)),
                key=COMPARE_TOGGLE_KEY,
            )
        if compare_on:
            dates = list(_loaded_context(data)["session_dates"])
            if dates:
                default_compare = next(
                    (
                        str(record.get("date"))
                        for record in presets["presets"]
                        if record.get("preset_id") == "quiet" and record.get("date")
                    ),
                    dates[0],
                )
                stored = state.get(COMPARE_DATE_KEY) or default_compare
                if stored not in dates:
                    stored = dates[-1]
                index = dates.index(stored)
                compare_index = _call(
                    sidebar,
                    "slider",
                    "Comparison window date",
                    min_value=0,
                    max_value=len(dates) - 1,
                    value=index,
                    key=f"tm_compare_index::{selection.date}",
                )
                if compare_index is not None and 0 <= int(compare_index) < len(dates):
                    state[COMPARE_DATE_KEY] = dates[int(compare_index)]
                else:
                    state[COMPARE_DATE_KEY] = stored
                _call(sidebar, "caption", f"Comparison window: {state.get(COMPARE_DATE_KEY)}")
                _call(
                    sidebar,
                    "caption",
                    "Both windows use the fixed 60-session window, r >= 0.80 cutoff and the same "
                    "node layout; changes are context, not proof of crisis emergence.",
                )
        else:
            state.pop(COMPARE_DATE_KEY, None)

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
            key=f"tm_member_select::{selection.member}",
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
    # Render the date caption after every date-changing control so it always
    # reflects the effective selection in the same rerun.
    _call(sidebar, "caption", f"Selected session: {selection.date}")
    return selection, options


def _apply_mapper_edge_selector(
    sidebar: Any, data: DashboardData, selection: DashboardSelection
) -> DashboardSelection:
    """Offer a keyboard-operable Mapper edge picker (UI02)."""

    from topomarket.ui.calendars import map_observation_date
    from topomarket.ui.structure import build_mapper_view

    selected_date = selection.date or (data.session_dates[-1] if data.session_dates else None)
    if selected_date is None:
        return selection
    map_info = map_observation_date(data, selected_date)
    map_date = map_info.get("date") or selected_date
    try:
        mapper = build_mapper_view(data, map_date, selected_member=selection.member)
    except Exception:  # noqa: BLE001 - short windows have no Mapper edges
        return selection
    edges = list(mapper.get("edges") or ())
    if not edges:
        return selection
    labels = ["(no edge highlighted)"]
    by_label: dict[str, str] = {}
    for edge in edges:
        shared = ", ".join(entry["label"] for entry in edge.get("shared_members") or ())
        label = f"{edge['source']} -- {edge['target']}: {shared}"
        labels.append(label)
        by_label[label] = str(edge["edge_id"])
    index = 0
    if selection.edge:
        for position, edge in enumerate(edges, start=1):
            if str(edge["edge_id"]) == str(selection.edge):
                index = position
                break
    value = _call(
        sidebar,
        "selectbox",
        "Highlight Mapper edge",
        labels,
        index=index,
        key="tm_edge_select",
        help="Highlight the member portfolios shared by the selected pair of groups.",
    )
    if value is None:
        return selection
    if str(value) == labels[0]:
        return selection.with_edge(None)
    edge_id = by_label.get(str(value))
    return selection.with_edge(edge_id) if edge_id else selection


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


GUIDE_STEP_KEY = "tm_guide_step"
COMPARE_TOGGLE_KEY = "tm_compare"
COMPARE_DATE_KEY = "tm_compare_date"


def _chronological_quiet_date(data: DashboardData, stress_date: str | None) -> str | None:
    """Latest low-density window that precedes the stress transition.

    The frozen "quiet period" preset sits after the stress window on the synthetic
    fixture, so the guided tour derives a chronological quiet -> stress pair for
    the story while the preset itself stays untouched.  The candidate is verified
    (sparse network) and cached on the data object.
    """

    if not stress_date:
        return None
    dates = list(getattr(data, "session_dates", ()) or ())
    if stress_date not in dates:
        return None
    stress_index = dates.index(stress_date)
    cache = getattr(data, "_topology_cache", None)
    key = f"guided-quiet:{stress_date}"
    if isinstance(cache, dict) and key in cache:
        return cache[key]
    from topomarket.analysis.network import build_correlation_network

    rows = getattr(data, "industry_rows", None) or getattr(data, "rows", ()) or ()
    chosen: str | None = None
    for offset in (120, 100, 80, 60):
        candidate_index = stress_index - offset
        if candidate_index < 0:
            continue
        candidate = dates[candidate_index]
        try:
            network = build_correlation_network(rows, candidate)
        except Exception:  # noqa: BLE001 - fall back to the next offset
            continue
        if network.get("available") and int(network.get("pairs_qualifying") or 0) <= 30:
            chosen = candidate
            break
    if chosen is None:
        chosen = dates[max(0, stress_index - 60)]
    if isinstance(cache, dict):
        cache[key] = chosen
    return chosen


def _guided_steps(
    presets: Mapping[str, Any], data: DashboardData | None = None
) -> list[dict[str, Any]]:
    """Guided sequence: synthetic market shift -> Quiet -> Stress -> Explain -> Replay.

    The first stop is the frozen retrospective synthetic pair required by the release
    audit (29/66 on 2008-08-29 -> 66/66 on 2008-10-10); later stops use the released
    presets.  The tour is only "active" after the visitor starts or navigates it, so
    the first screen never labels a stress selection as the quiet window.
    """

    change = presets.get("structure_change") or {}
    records = {str(record.get("preset_id")): record for record in presets.get("presets") or ()}
    quiet = records.get("quiet") or {}
    stress = records.get("stress_transition") or {}
    alert = records.get("matched_warning") or {}
    quiet_date = quiet.get("date")
    stress_date = stress.get("date")
    chronological_quiet = (
        _chronological_quiet_date(data, stress_date) if data is not None else None
    ) or quiet_date
    return [
        {
            "name": "Synthetic market shift",
            "description": (
                "Frozen retrospective example: 29/66 pairs on 2008-08-29 -> 66/66 on "
                "2008-10-10 (+37, none removed) after the 2008-09-16 onset."
            ),
            # Window A is the earlier date, window B the later date: the guided
            # comparison renders a chronological +37 change, matching the caption.
            "date": change.get("left_date"),
            "compare_date": change.get("right_date"),
            "compare": True,
            "mode": "live",
            "screen": "structure",
            "reveal": False,
        },
        {
            "name": "Quiet window",
            "description": (
                "Few industry pairs move together; the score is below the frozen threshold."
            ),
            "date": chronological_quiet,
            "mode": "live",
            "screen": "structure",
            "reveal": False,
        },
        {
            "name": "Stress transition",
            "description": "The same fixed layout, now with many more qualified pairs.",
            "date": stress.get("date"),
            "mode": "replay",
            "screen": "structure",
            "reveal": False,
        },
        {
            "name": "Explain the alert",
            "description": (
                "A recorded alert opens the Takens window and highlighted H1 interval inline."
            ),
            "date": alert.get("date"),
            "mode": "replay",
            "screen": "structure",
            "reveal": False,
        },
        {
            "name": "Replay it blind",
            "description": (
                "The Replay screen keeps the outcome hidden until you explicitly reveal it."
            ),
            "date": alert.get("date"),
            "mode": "replay",
            "screen": "replay",
            "reveal": False,
        },
    ]


def _apply_guided_step(
    selection: DashboardSelection, step: Mapping[str, Any]
) -> DashboardSelection:
    updated = selection
    if step.get("date"):
        updated = updated.with_date(str(step["date"]))
    return updated.replace(
        screen=str(step.get("screen") or "structure"),
        mode=str(step.get("mode") or "replay"),
        reveal=bool(step.get("reveal", False)),
        network_view="correlation",
    )


def _comparison_state(
    ui: Any, data: DashboardData, selection: DashboardSelection
) -> dict[str, Any] | None:
    """Build the two-window comparison when the visitor enabled it."""

    state = getattr(ui, "session_state", None)
    if not isinstance(state, Mapping):
        return None
    if not state.get(COMPARE_TOGGLE_KEY):
        return None
    if blind_structure_state(selection):
        return None
    compare_date = state.get(COMPARE_DATE_KEY)
    if not compare_date or not selection.date:
        return None
    cache = getattr(data, "_topology_cache", None)
    key = f"window-comparison:{selection.date}:{compare_date}"
    if isinstance(cache, dict) and key in cache:
        return cache[key]
    try:
        comparison = build_window_comparison(data, str(selection.date), str(compare_date))
    except Exception as error:  # noqa: BLE001 - comparison is an optional view
        return {"available": False, "reason": str(error)}
    presets = build_presets(data)
    frozen = presets.get("structure_change") or {}
    if frozen.get("available") and {frozen.get("left_date"), frozen.get("right_date")} == {
        str(selection.date),
        str(compare_date),
    }:
        comparison = dict(comparison)
        comparison["label"] = "Retrospective synthetic example"
        comparison["statement"] = str(frozen.get("statement") or comparison["statement"])
    if isinstance(cache, dict):
        cache[key] = comparison
    return comparison


def _render_interactive_or_static(
    ui: Any,
    figure_factory: Any,
    *,
    key: str,
    caption: str,
    alt_text: str,
    show_alt_caption: bool = True,
) -> Any:
    """Render a Plotly figure when the UI supports it, else the static fallback."""

    plotter = getattr(ui, "plotly_chart", None)
    if plotter is not None and interactive is not None:
        event = _call(
            ui,
            "plotly_chart",
            figure_factory(),
            key=key,
            on_select="rerun",
            selection_mode=("box", "lasso"),
            width="stretch",
            theme=None,
            config={
                "displayModeBar": False,
                "displaylogo": False,
                "scrollZoom": False,
                "doubleClick": False,
            },
        )
        if show_alt_caption:
            _call(ui, "caption", alt_text)
        if caption:
            _call(ui, "caption", caption)
        return event
    if charts is not None:
        _render_figure(
            ui,
            figure_factory,
            caption=caption,
            alt_text=alt_text,
            cache_key=key,
        )
    return None


def _commit_interactive_selection(ui: Any, selection: DashboardSelection) -> DashboardSelection:
    """Persist an interactive selection and request a clean rerun.

    The click/box selection arrives while the chart is being drawn, so the
    payload for the inspector/timeline below was built for the previous state.
    Persisting and rerunning once keeps a single authoritative session state
    (the alternative double render would duplicate the chart work).
    """

    _persist_selection(ui.session_state, selection)
    rerun = getattr(ui, "rerun", None)
    if callable(rerun):
        rerun()
    return selection


def _render_mini_timeline(
    ui: Any,
    selection: DashboardSelection,
    payload: Mapping[str, Any],
) -> DashboardSelection:
    """Compact above-the-fold timeline with click-to-select (Studio C)."""

    timeline = payload.get("timeline") or {}
    event = _render_interactive_or_static(
        ui,
        lambda: interactive.mini_timeline_figure(timeline, selected_date=selection.date),
        key="tm_mini_timeline_chart",
        caption="",
        alt_text=(
            "Compact S&P 500 timeline for the trailing "
            f"{timeline.get('window_sessions', 0)} sessions ending {timeline.get('selected')}; "
            "click a point to select that session (the sidebar date control is the keyboard "
            "equivalent)."
        ),
    )
    if interactive is not None:
        clicked = interactive.timeline_selection(event, list(timeline.get("dates") or ()))
        if clicked and clicked != selection.date:
            selection = _commit_interactive_selection(ui, selection.with_date(clicked))
    return selection


def _render_landing(
    ui: Any,
    network: Mapping[str, Any],
    timeline: Mapping[str, Any],
    selection: DashboardSelection,
) -> DashboardSelection:
    """Render the combined interactive network + compact timeline (one chart)."""

    plotter = getattr(ui, "plotly_chart", None)
    if plotter is not None and interactive is not None:
        state = getattr(ui, "session_state", None)
        cache = None
        cache_key = f"landing:{timeline.get('selected')}:{selection.member}"
        if isinstance(state, Mapping):
            cache = state.get("tm_landing_cache")
            if not isinstance(cache, dict):
                cache = {}
                state["tm_landing_cache"] = cache
        if cache is not None and cache_key in cache:
            figure = cache[cache_key]
        else:
            figure = interactive.landing_figure(
                network,
                timeline,
                selected_code=selection.member,
                selected_date=selection.date,
            ).to_plotly_json()
            if cache is not None:
                cache[cache_key] = figure
                while len(cache) > 80:
                    cache.pop(next(iter(cache)))
        event = _call(
            ui,
            "plotly_chart",
            figure,
            key="tm_landing_chart",
            on_select="rerun",
            selection_mode=("box", "lasso"),
            width="stretch",
            theme=None,
            config={
                "displayModeBar": False,
                "displaylogo": False,
                "scrollZoom": False,
                "doubleClick": False,
            },
        )
        dates = list(timeline.get("dates") or ())
        codes = [str(node.get("code")) for node in network.get("nodes") or ()]
        mapped = interactive.landing_selection(event, dates, codes)
        if mapped.get("member") and mapped["member"] != selection.member:
            selection = _commit_interactive_selection(ui, selection.with_member(mapped["member"]))
        elif mapped.get("date") and mapped["date"] != selection.date:
            selection = _commit_interactive_selection(ui, selection.with_date(mapped["date"]))
        _call(
            ui,
            "caption",
            "Interactive network and compact timeline in one frame · box-select a node or a "
            "timeline point (modebar Select) to update the inspector and the authoritative "
            "session; the sidebar controls are the keyboard equivalent.",
        )
        return selection
    if charts is not None:
        _render_figure(
            ui,
            lambda: charts.correlation_network_figure(network, selected_code=selection.member),
            caption=str(network.get("summary") or ""),
            alt_text=str(network.get("summary") or "Correlation network"),
            cache_key=f"network:{(network.get('window') or {}).get('end')}:{selection.member}",
        )
    return selection


def render_dashboard(
    data: DashboardData,
    selection: DashboardSelection,
    payloads: Mapping[str, Mapping[str, Any]],
    streamlit_module: Any | None = None,
    cache: PanelCache | None = None,
) -> DashboardSelection:
    """Render the four-screen shell; returns the effective selection.

    Widgets are applied *before* the screens are drawn.  When a cache is supplied
    the payloads are recomputed for the effective selection in the same rerun, so
    a preset click, reveal or screen switch never shows a one-rerun-stale view.
    """

    ui = _ui(streamlit_module)
    _call(ui, "set_page_config", page_title="TopoMarket research", layout="wide")
    _call(ui, "markdown", motion_css(), unsafe_allow_html=True)
    _call(
        ui,
        "markdown",
        "<style>"
        ".block-container {padding-top: 1.1rem; padding-bottom: 1.6rem;}"
        "div[data-testid='stVerticalBlock'] {gap: 0.45rem;}"
        "div[data-testid='stHorizontalBlock'] {gap: 0.6rem;}"
        ".js-plotly-plot {margin: 0 !important;}"
        "</style>",
        unsafe_allow_html=True,
    )
    selection, _options = _apply_widgets(ui, data, selection)
    _persist_selection(ui.session_state, selection)
    if cache is not None:
        payloads = _screen_payloads(cache, selection)
    screens = {name: payloads.get(name) or {} for name in SCREEN_ORDER}
    if selection.screen == "structure":
        updated = render_structure_screen(ui, data, selection, screens["structure"])
        if isinstance(updated, DashboardSelection):
            selection = updated
    elif selection.screen == "replay":
        render_replay_screen(ui, data, selection, screens["replay"])
    elif selection.screen == "validation":
        render_validation_screen(ui, data, selection, screens["validation"])
    elif selection.screen == "data":
        render_data_screen(ui, data, selection, screens["data"])
    else:  # pragma: no cover - selection validation prevents this
        _call(ui, "error", f"Unknown screen {selection.screen!r}")
    # Interactive Plotly selections (node click, timeline point, guided step)
    # update the selection during rendering; persist it for the next rerun so the
    # canonical session state - not a widget duplicate - drives the payload.
    _persist_selection(ui.session_state, selection)
    _call(ui, "caption", KEYBOARD_HELP)
    return selection


# --------------------------------------------------------------------------- #
# Screen renderers
# --------------------------------------------------------------------------- #
def blind_structure_state(selection: DashboardSelection) -> bool:
    """Blind mode for the Structure timeline: Replay without a reveal."""

    return str(getattr(selection, "mode", "live")).lower() in {"replay", "historical"} and not bool(
        getattr(selection, "reveal", False)
    )


def _render_node_tap_buttons(
    ui: Any, network: Mapping[str, Any], selection: DashboardSelection
) -> DashboardSelection:
    """U4: reliable single-tap portfolio selection (touch pointer + keyboard)."""

    nodes = list(network.get("nodes") or ())[:12]
    if not nodes:
        return selection
    _call(
        ui,
        "caption",
        "Tap a portfolio to inspect it (single tap works on touch and with the keyboard); "
        "box-select on the network does the same with a mouse.",
    )
    for start in (0, 6):
        row = nodes[start : start + 6]
        if not row:
            continue
        columns = _call(ui, "columns", len(row)) or []
        for column, node in zip(columns, row, strict=False):
            label = node.get("label") or node.get("code")
            if _call(column, "button", str(label), key=f"tm_node_tap::{node['code']}"):
                selection = _commit_interactive_selection(
                    ui, selection.with_member(str(node["code"]))
                )
    return selection


def _render_edge_inspector(
    ui: Any, network: Mapping[str, Any], selection: DashboardSelection
) -> DashboardSelection:
    """U4: reliable edge hit targets with correlation and text equivalent."""

    edges = list(network.get("edges") or ())
    if not edges:
        return selection
    labels = {node["code"]: node["label"] for node in network.get("nodes") or ()}
    options = ["(no edge highlighted)"] + [
        f"{labels.get(edge['source'], edge['source'])} – "
        f"{labels.get(edge['target'], edge['target'])} · r={float(edge['correlation']):.3f}"
        for edge in edges
    ]
    by_label = {
        option: f"{edge['source']}--{edge['target']}"
        for option, edge in zip(options[1:], edges, strict=False)
    }
    current = 0
    for position, option in enumerate(options[1:], start=1):
        if by_label[option] == str(selection.edge or ""):
            current = position
    chosen = _call(
        ui,
        "selectbox",
        "Edge inspector (reliable hit target)",
        options,
        index=current,
        key="tm_edge_inspect",
        help="Every qualifying pair can be selected here; hovering/box-selecting on the network "
        "shows the same correlation.",
    )
    if chosen and chosen != options[0]:
        selection = selection.replace(edge=by_label[chosen])
        edge_id = by_label[chosen]
        edge = next(
            (item for item in edges if edge_id == f"{item['source']}--{item['target']}"),
            None,
        )
        if edge is not None:
            _call(
                ui,
                "markdown",
                f"**Selected edge:** {labels.get(edge['source'], edge['source'])} – "
                f"{labels.get(edge['target'], edge['target'])} · "
                f"Pearson r = {float(edge['correlation']):.3f} (above the fixed cutoff).",
            )
    return selection


def _render_mapper_node_buttons(
    ui: Any, mapper: Mapping[str, Any], selection: DashboardSelection
) -> DashboardSelection:
    """U4: direct Mapper inspection without switching to the network view."""

    nodes = list(mapper.get("nodes") or ())[:8]
    if not nodes:
        return selection
    _call(ui, "caption", "Tap a Mapper group to inspect its members and within-group correlations.")
    columns = _call(ui, "columns", min(4, len(nodes))) or []
    for position, node in enumerate(nodes):
        column = columns[position % len(columns)] if columns else ui
        members = ", ".join(member["label"] for member in node.get("members") or ())
        if _call(
            column,
            "button",
            f"{node['node_id']} · {node.get('member_count', 0)} members",
            key=f"tm_mapper_node::{node['node_id']}",
            help=members,
        ):
            # Carry the exact Mapper node id so two groups sharing the same industry
            # code can never resolve to the wrong group (audit v1.2.0 remediation).
            selection = _commit_interactive_selection(
                ui, selection.replace(node=str(node["node_id"]))
            )
    return selection


def render_structure_screen(
    ui: Any, data: DashboardData, selection: DashboardSelection, payload: Mapping[str, Any]
) -> DashboardSelection:
    """Render the public Structure landing screen.

    Return the (possibly) updated selection so interactive selections - a node
    click on the network, a timeline point, the guided tour - flow through the
    same canonical session state as the keyboard controls (WP-C).
    """

    _call(ui, "title", "TopoMarket research")
    _synthetic_label(ui, data, selection)
    presets = payload.get("presets") or {}
    active_preset = next(
        (record for record in presets.get("presets") or () if record.get("date") == selection.date),
        None,
    )
    if active_preset and active_preset.get("teaching"):
        if blind_structure_state(selection):
            _call(
                ui,
                "caption",
                "Guided demonstration example. Reveal the outcome to review its "
                "retrospective label.",
            )
        else:
            _call(
                ui,
                "warning",
                "Recorded late alert: the episode began on 2025-03-06; the alert fired on "
                "2025-03-10 and is included in the frozen evaluation as a late alert with zero "
                "early-warning credit.",
            )
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
        selection = _render_mapper_node_buttons(ui, mapper, selection)
        _render_figure(
            ui,
            lambda: charts.mapper_figure(
                mapper,
                selected_node_id=mapper.get("selected_node_id"),
                selected_edge_id=(mapper.get("selected_edge") or {}).get("edge_id"),
            ),
            caption=str(mapper.get("position_rule") or ""),
            alt_text=str(mapper.get("table_alternative") or "Mapper groups")[:4000],
            cache_key=(
                f"mapper:{map_obs.get('date') or selection.date}:"
                f"{mapper.get('selected_node_id')}:"
                f"{(mapper.get('selected_edge') or {}).get('edge_id')}"
            ),
        )
        selected_node_id = mapper.get("selected_node_id")
        if selected_node_id:
            selected_node = next(
                (
                    item
                    for item in mapper.get("nodes") or ()
                    if item.get("node_id") == selected_node_id
                ),
                None,
            )
            if selected_node:
                names = ", ".join(member["label"] for member in selected_node.get("members") or ())
                _call(
                    ui,
                    "markdown",
                    f"**Selected Mapper group {selected_node_id} · "
                    f"{selected_node.get('member_count', 0)} members:** {names}",
                )
        selected_edge = mapper.get("selected_edge") or None
        if selected_edge:
            shared = ", ".join(
                entry["label"] for entry in selected_edge.get("shared_members") or ()
            )
            _call(
                ui,
                "markdown",
                f"**Highlighted edge {selected_edge['edge_id']}** - shared portfolios: {shared}",
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
        comparison = _comparison_state(ui, data, selection)
        if comparison and comparison.get("available"):
            _call(ui, "subheader", "Two-window comparison")
            _call(ui, "markdown", f"**{comparison['statement']}**")
            if comparison.get("label"):
                _call(ui, "caption", f"**{comparison['label']}**")
            event = _render_interactive_or_static(
                ui,
                lambda: interactive.comparison_figure(comparison, selected_code=selection.member),
                key="tm_comparison_chart",
                caption=str(comparison.get("edge_density_note") or ""),
                alt_text=str(
                    comparison.get("table_alternative") or "Two-window network comparison"
                ),
            )
            selected = interactive.network_selection(event) if interactive is not None else None
            if selected and selected != selection.member:
                selection = _commit_interactive_selection(ui, selection.with_member(selected))
            windows = comparison.get("windows") or {}
            left = windows.get("A") or {}
            right = windows.get("B") or {}
            metric_columns = _call(ui, "columns", 4) or []
            cards = (
                (
                    f"Window A · {left.get('date')}",
                    f"{left.get('pairs_qualifying')}/{left.get('pairs_total')} pairs",
                ),
                (
                    f"Window B · {right.get('date')}",
                    f"{right.get('pairs_qualifying')}/{right.get('pairs_total')} pairs",
                ),
                (
                    "Change in qualified pairs",
                    f"{comparison.get('delta_pairs'):+d} "
                    f"({comparison.get('delta_percentage_points'):+.1f} pp)",
                ),
                (
                    "Mean off-diagonal correlation",
                    f"{left.get('mean_off_diagonal_correlation'):.3f} → "
                    f"{right.get('mean_off_diagonal_correlation'):.3f}",
                ),
            )
            for position, (label, value) in enumerate(cards):
                target = metric_columns[position] if position < len(metric_columns) else ui
                _call(target, "metric", label, value)
            _call(
                ui,
                "caption",
                f"Edges added in window B: {comparison.get('added_count')} · removed: "
                f"{comparison.get('removed_count')} · material increase: "
                f"{comparison.get('material_increase')} · sequence claim: "
                f"{comparison.get('sequence_claim')}",
            )
            with _expander(ui, "Comparison table (keyboard equivalent)") as table_area:
                _call(table_area, "text", str(comparison.get("table_alternative") or ""))
                _call(
                    table_area,
                    "caption",
                    "Hover an edge in the figure for its exact Pearson correlation and both "
                    "portfolio names; added edges use the positive colour, removed edges amber.",
                )
            selection = _render_mini_timeline(ui, selection, payload)
        else:
            _call(ui, "subheader", "Industry correlation network")
            timeline = payload.get("timeline") or {}
            selection = _render_landing(ui, network, timeline, selection)
            _call(ui, "caption", str(network.get("summary") or ""))
            selection = _render_node_tap_buttons(ui, network, selection)
            selection = _render_edge_inspector(ui, network, selection)
            pairs = [
                pair for pair in network.get("pairs") or () if pair.get("correlation") is not None
            ]
            mean_correlation = (
                sum(float(pair["correlation"]) for pair in pairs) / len(pairs) if pairs else None
            )
            score = payload.get("score") or {}
            score_value = score.get("value")
            metric_columns = _call(ui, "columns", 3) or []
            cards = (
                (
                    "Qualified pairs",
                    f"{network.get('pairs_qualifying')}/{network.get('pairs_total')} "
                    f"at r ≥ {float(network.get('cutoff') or 0.0):.2f}",
                ),
                (
                    "Mean off-diagonal correlation",
                    "n/a" if mean_correlation is None else f"{mean_correlation:.3f}",
                ),
                (
                    "TDA score percentile",
                    "unavailable"
                    if score_value is None
                    else f"{float(score_value):.1f} (comparative)",
                ),
            )
            for position, (label, value) in enumerate(cards):
                target = metric_columns[position] if position < len(metric_columns) else ui
                _call(target, "metric", label, value)
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

    timeline = payload.get("timeline") or {}
    show_full_timeline = _call(
        ui,
        "checkbox",
        "Show the full shared timeline",
        value=False,
        key=f"tm_full_timeline::{selection.date}",
        help="The compact timeline above already supports click selection; enable this for all "
        "three full panels.",
    )
    if not show_full_timeline:
        _call(
            ui,
            "caption",
            "Compact timeline shown above · enable “Show the full shared timeline” for the full "
            "S&P 500, VIX and score panels.",
        )

    if show_full_timeline:
        timeline_event = _render_interactive_or_static(
            ui,
            lambda: interactive.timeline_figure(timeline, selected_date=selection.date),
            key="tm_full_timeline_chart",
            caption=str(timeline.get("legend") or ""),
            alt_text=(
                f"Aligned S&P 500, VIX and score panels for the trailing "
                f"{timeline.get('window_sessions', 0)} sessions ending {timeline.get('selected')}; "
                f"threshold {timeline.get('threshold')}; "
                f"{len(timeline.get('alert_markers') or ())} alert marker(s). Click a point to "
                f"select that session; the sidebar date control remains the keyboard equivalent."
            ),
        )
        if interactive is not None:
            clicked = interactive.timeline_selection(
                timeline_event, list(timeline.get("dates") or ())
            )
            if clicked and clicked != selection.date:
                selection = _commit_interactive_selection(ui, selection.with_date(clicked))
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
                    lambda: charts.takens_figure(explanation),
                    caption=str(explanation.get("display_note") or ""),
                    alt_text="2-D display-coordinate scatter of the 56-point price embedding.",
                    cache_key=f"takens:{selection.date}",
                )
            with columns[1]:
                _render_figure(
                    ui,
                    lambda: charts.h1_figure(explanation),
                    caption="H1 birth-death diagram with the diagonal reference and longest "
                    "finite lifetime highlighted.",
                    alt_text="H1 birth-death diagram; longest finite lifetime in amber.",
                    cache_key=f"h1:{selection.date}",
                )
        else:  # pragma: no cover - fake UI without columns
            _render_figure(
                ui,
                lambda: charts.takens_figure(explanation),
                caption="",
                alt_text="Takens",
                cache_key=f"takens:{selection.date}",
            )
        if explanation.get("industry_pca"):
            columns = _call(ui, "columns", 2) or []
            target = columns[0] if columns else ui
            _render_figure(
                target,
                lambda: charts.pca_figure(explanation),
                caption="Industry PCA display coordinates; each point is one session.",
                alt_text="Industry PCA scatter, one point per session, map date highlighted.",
                cache_key=f"pca:{map_obs.get('date') or selection.date}",
            )
    else:
        _call(ui, "caption", explanation.get("reason") or "No score explanation for this session.")

    # U5: reveal the outcome inline on the Structure screen instead of switching screens.
    if str(payload.get("mode")) == "replay":
        if not selection.reveal:
            if _call(
                ui,
                "button",
                f"Reveal next {OUTCOME_HORIZON} sessions (stay on Structure)",
                key="tm_structure_reveal",
            ):
                selection = _commit_interactive_selection(ui, toggle_reveal(selection))
            _call(
                ui,
                "caption",
                "Blind review: the network, selected date, threshold and H1 explanation stay "
                "visible; revealing adds the 20-session outcome inline.",
            )
        else:
            outcome = (payload.get("replay") or {}).get("outcome") or {}
            _call(ui, "subheader", "Inline outcome")
            _call(ui, "markdown", f"**{outcome.get('outcome_label') or 'Outcome revealed'}**")
            metrics = _call(ui, "columns", 5) or []
            values = [
                ("Origin close", outcome.get("origin", {}).get("close")),
                ("10% boundary", outcome.get("boundary", {}).get("close")),
                ("Lowest close", outcome.get("lowest", {}).get("close")),
                ("First breach", (outcome.get("first_breach") or {}).get("date") or "none"),
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
                _call(ui, "warning", "Outcome horizon is still pending.")
            if _call(ui, "button", "Hide outcome (blind view)", key="tm_structure_blind"):
                selection = _commit_interactive_selection(ui, toggle_blind(selection))
            _call(
                ui,
                "caption",
                "Retrospective outcome added inline. Hiding it restores the blind payload, "
                "including hover and accessibility text.",
            )
        replay_alert = (payload.get("replay") or {}).get("alert") or {}
        if replay_alert.get("status") == "late":
            _call(
                ui,
                "warning",
                f"Recorded late alert: the episode began on {replay_alert.get('episode_onset')}; "
                f"the alert fired on {selection.date} and is included in the frozen evaluation "
                "as a late alert with zero early-warning credit.",
            )
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

    return selection


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
        if alert.get("retrospective"):
            _call(
                ui,
                "markdown",
                f"**Review alert classification (retrospective):** {alert.get('label')}",
            )
        else:
            _call(ui, "markdown", f"**Alert state:** {alert.get('label')}")
    elif payload.get("blind"):
        _call(ui, "caption", "No alert recorded on the selected session.")
    _render_figure(
        ui,
        lambda: charts.replay_figure(payload),
        caption=str(payload.get("legend") or ""),
        alt_text=str(payload.get("accessible_summary") or "Replay chart"),
        cache_key=f"replay:{selection.date}:{bool(selection.reveal)}",
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

    if alert.get("status") == "late" and not payload.get("blind"):
        outcome = payload.get("outcome") or {}
        decline = outcome.get("max_decline_pct")
        onset = alert.get("episode_onset") or "2025-03-06"
        _call(
            ui,
            "warning",
            f"Recorded late alert: the episode began on {onset}; the alert fired on "
            f"{selection.date} and is included in the frozen evaluation as a late alert with "
            f"zero early-warning credit. The largest decline over the next 20 sessions was "
            f"{'n/a' if decline is None else f'{float(decline):.2f}%'}, below the 10% target.",
        )
    return selection


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
    evidence_table = list(payload.get("evidence_table") or ())
    primary_method = str(payload.get("primary_method") or "")
    primary_row = next(
        (row for row in evidence_table if row.get("method") == primary_method),
        evidence_table[0] if evidence_table else {},
    )
    if primary_row:
        metric_columns = _call(ui, "columns", 4) or []
        recall_text = "n/a"
        if (
            primary_row.get("recall_numerator") is not None
            and primary_row.get("recall_denominator") is not None
        ):
            recall_text = f"{primary_row['recall_numerator']}/{primary_row['recall_denominator']}"
        precision = primary_row.get("average_precision")
        false_rate = primary_row.get("false_alerts_per_year")
        lead = primary_row.get("median_lead_sessions")
        cards = (
            ("Primary method", "TDA score" if primary_method == "tda" else primary_method or "n/a"),
            ("Holdout recall", recall_text),
            ("Average precision", "n/a" if precision is None else f"{float(precision):.3f}"),
            ("False alerts / year", "n/a" if false_rate is None else f"{float(false_rate):.2f}"),
        )
        for position, (label, value) in enumerate(cards):
            target = metric_columns[position] if position < len(metric_columns) else ui
            _call(target, "metric", label, value)
        prevalence = primary_row.get("event_prevalence")
        _call(
            ui,
            "caption",
            "Event prevalence "
            f"{prevalence if prevalence is not None else 'n/a'} · "
            f"median lead {lead if lead is not None else 'n/a'} session(s) · "
            f"alerts {primary_row.get('alerts')} · eligible sessions "
            f"{primary_row.get('eligible_sessions')}. Recall shows matched/eligible episodes.",
        )
    if evidence_table:
        _render_figure(
            ui,
            lambda: charts.evidence_comparison_figure(payload),
            cache_key=f"evidence:{payload.get('run_id')}:{payload.get('snapshot_id')}",
            caption=(
                "Three-method comparison on the common eligible dates; the dashed line is the "
                "event prevalence. Average precision is computed over the complete daily series."
            ),
            alt_text=(
                "Bar charts comparing episode recall, average precision and false alerts per "
                "year for the TDA score, VIX level and realized volatility, with "
                "matched/eligible labels."
            ),
        )
    comparison = payload.get("calibration_comparison") or {}
    with _expander(ui, "Method details, intervals and limitations") as details:
        if evidence_table:
            _call(details, "dataframe", evidence_table)
        if comparison.get("methods"):
            _call(
                details,
                "markdown",
                "**Calibration before/after (v1.0 baseline -> F01-corrected v1.1).** "
                f"Same eligible dates: {comparison.get('same_eligible_dates')}. "
                "The holdout suffix is never used to fit the policy.",
            )
            _call(
                details,
                "dataframe",
                [
                    {
                        "method": method,
                        "v1.0 validation recall": block["calibration"]["before"].get(
                            "episode_recall"
                        ),
                        "v1.1 validation recall": block["calibration"]["after"].get(
                            "episode_recall"
                        ),
                        "v1.1 matched/eligible": (
                            f"{block['calibration']['after'].get('matched_count')}/"
                            f"{block['calibration']['after'].get('episode_count')}"
                        ),
                        "holdout AP v1.0": block["holdout"]["before"].get("average_precision"),
                        "holdout AP v1.1": block["holdout"]["after"].get("average_precision"),
                        "policy changed": block.get("policy_changed"),
                    }
                    for method, block in (comparison.get("methods") or {}).items()
                ],
            )
        bootstrap = payload.get("bootstrap") or {}
        if bootstrap:
            _call(
                details,
                "dataframe",
                [
                    {
                        "interval": key,
                        "mean": value.get("mean"),
                        "lower 95%": value.get("lower"),
                        "upper 95%": value.get("upper"),
                        "valid replicates": value.get("valid_replicates"),
                        "total replicates": value.get("total_replicates"),
                    }
                    for key, value in bootstrap.items()
                ],
            )
        for limitation in evidence.get("limitations") or ():
            _call(details, "markdown", f"- {limitation}")
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
def _screen_payloads(cache: Any, selection: DashboardSelection) -> dict[str, dict[str, Any]]:
    """Build the visible screen payloads, tolerant of older cached panel caches.

    A deployment can briefly run a newer ``app.py`` against an already-imported
    older ``topomarket`` module. The fallbacks keep the shell working until the
    app process restarts instead of failing the whole page.
    """

    getter = getattr(cache, "get_screen", None)
    if callable(getter):
        try:
            return getter(selection)
        except AttributeError:
            pass
    try:
        return cache.get(selection, screens=(selection.screen,))
    except TypeError:
        payloads = cache.get(selection)
    screen = selection.screen
    if isinstance(payloads, dict) and screen in payloads:
        return {screen: payloads[screen]}
    return payloads


def _data_stamp(profile: str, data_dir: Path | None) -> tuple[Any, ...]:
    """Return a cheap change stamp for the dashboard data cache.

    The stamp covers the committed showcase manifest/score files for the demo
    profile and the active-snapshot state/score files for a private profile, so a
    refresh or a new snapshot reloads the dashboard while ordinary reruns reuse
    the loaded data.
    """

    stamps: list[Any] = [profile, str(data_dir) if data_dir is not None else ""]
    candidates: list[Path] = []
    if data_dir is not None:
        candidates.extend(
            [
                Path(data_dir) / "scores.csv",
                Path(data_dir) / "import_manifest.json",
                Path(data_dir) / "state" / "active_snapshot.json",
            ]
        )
    else:
        from topomarket.profiles import REPOSITORY_ROOT

        showcase = REPOSITORY_ROOT / "showcase"
        candidates.extend(
            [
                showcase / "manifest.json",
                showcase / "scores.csv",
                showcase / "reports" / "evaluation-showcase.json",
                showcase / "presets.json",
            ]
        )
    for candidate in candidates:
        try:
            stat = candidate.stat()
        except OSError:
            stamps.append((str(candidate), None))
        else:
            stamps.append((str(candidate), stat.st_mtime_ns, stat.st_size))
    return tuple(stamps)


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
        runtime = ui is not None and _in_streamlit_runtime(ui)
        if runtime:
            stamp = _data_stamp(args.profile, args.data_dir)
            cached = ui.session_state.get("tm_dashboard_data")
            cached_stamp = ui.session_state.get("tm_dashboard_data_stamp")
            if isinstance(cached, DashboardData) and cached_stamp == stamp:
                data = cached
            else:
                data = load_dashboard_data(profile=args.profile, data_dir=args.data_dir)
                ui.session_state["tm_dashboard_data"] = data
                ui.session_state["tm_dashboard_data_stamp"] = stamp
                ui.session_state.pop("tm_panel_cache", None)
                ui.session_state.pop(CHART_CACHE_KEY, None)
        else:
            data = load_dashboard_data(profile=args.profile, data_dir=args.data_dir)
    except (OSError, ValueError, DashboardDataError) as exc:
        if ui is not None and _in_streamlit_runtime(ui):
            ui.error(f"Could not load dashboard data: {exc}")
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    if ui is None or not _in_streamlit_runtime(ui):
        cache = PanelCache(data)
        selection = default_selection(data)
        print(plain_text_dashboard(data, selection, cache.get(selection)))
        return 0
    state = ui.session_state
    cache = state.get("tm_panel_cache")
    if not isinstance(cache, PanelCache) or cache.data.data_signature != data.data_signature:
        cache = PanelCache(data)
        state["tm_panel_cache"] = cache
    selection = selection_from_state(state, data)
    payloads = _screen_payloads(cache, selection)
    selection = render_dashboard(data, selection, payloads, ui, cache=cache)
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
