"""Rendering tests for the Step 7 Streamlit shell (no Streamlit runtime)."""

from __future__ import annotations

import app
import pytest

from topomarket.ui.dashboard import SCREENS, DashboardSelection
from topomarket.ui.panels import PanelCache, load_dashboard_data


class _Ctx:
    def __init__(self, recorder: _FakeUI) -> None:
        self.recorder = recorder

    def __enter__(self) -> _FakeUI:
        return self.recorder

    def __exit__(self, *_exc: object) -> bool:
        return False


class _FakeUI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.session_state: dict = {}

    def __getattr__(self, name: str):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "selectbox":
                options = args[1]
                index = kwargs.get("index", 0)
                return options[index]
            if name == "radio":
                options = args[1]
                index = kwargs.get("index", 0)
                return options[index]
            if name in {"button", "checkbox"}:
                return False
            if name == "text_input":
                return ""
            if name == "columns":
                return [_FakeUI() for _ in range(int(args[0]))]
            if name == "expander":
                return _Ctx(self)
            if name == "download_button":
                return None
            return None

        return method

    @property
    def sidebar(self) -> _FakeUI:
        return self


def _data():
    return load_dashboard_data("demo")


def test_render_dashboard_all_four_screens() -> None:
    data = _data()
    cache = PanelCache(data)
    for screen in SCREENS:
        ui = _FakeUI()
        selection = DashboardSelection(screen=screen, sessions=data.session_dates)
        payloads = cache.get(selection)
        result = app.render_dashboard(data, selection, payloads, ui)
        assert result.screen == screen
        assert ui.calls
        names = {name for name, _args, _kwargs in ui.calls}
        assert "title" in names
        if screen == "data":
            assert "dataframe" in names or "caption" in names


def test_plain_text_dashboard_mentions_all_screens() -> None:
    data = _data()
    selection = app.default_selection(data)
    text = app.plain_text_dashboard(data, selection)
    for label in ("Overview", "Topology", "Validation", "Data"):
        assert label in text
    assert data.session_dates[-1] in text


def test_main_demo_without_streamlit_prints_dashboard(capsys: pytest.CaptureFixture[str]) -> None:
    assert app.main(["--profile", "demo"]) in {0}
    output = capsys.readouterr().out
    assert "TopoMarket dashboard" in output
    assert "Overview" in output
    assert "Data" in output


def test_selection_from_state_and_keyboard_command() -> None:
    data = _data()
    state = {
        "tm_screen": "topology",
        "tm_mode": "replay",
        "tm_date": data.session_dates[10],
        "tm_reveal": True,
        "tm_member": None,
        "tm_run": None,
    }
    selection = app.selection_from_state(state, data)
    assert selection.screen == "topology"
    assert selection.mode == "replay"
    assert selection.reveal is True

    updated = app.apply_action_to_state(state, "toggle_blind", data)
    assert updated.reveal is False

    updated = app.apply_action_to_state(state, "next_session", data)
    assert updated.date == data.session_dates[11]


def test_run_shell_plain_fallback(capsys: pytest.CaptureFixture[str]) -> None:
    args = app.parse_args(["--profile", "demo"])
    assert app.run_shell(args, streamlit_module=None) == 0
    output = capsys.readouterr().out
    assert "TopoMarket dashboard" in output
