"""Renderer and shell tests for the v1.0 Streamlit app (fake UI, no runtime)."""

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
    """Minimal Streamlit stand-in that records calls and returns defaults."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.session_state: dict = {}
        self._buttons: set[str] = set()

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
            if name in {"slider", "select_slider"}:
                return kwargs.get("value")
            if name in {"button", "checkbox"}:
                return kwargs.get("key") in self._buttons
            if name == "text_input":
                return ""
            if name == "columns":
                return [self for _ in range(int(args[0]))]
            if name in {"expander", "spinner"}:
                return _Ctx(self)
            return None

        return method

    def __enter__(self) -> _FakeUI:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    @property
    def sidebar(self) -> _FakeUI:
        return self

    def call_names(self) -> set[str]:
        return {name for name, _args, _kwargs in self.calls}


@pytest.fixture(scope="module")
def data():
    return load_dashboard_data("demo")


def test_render_dashboard_all_four_screens(data) -> None:
    cache = PanelCache(data)
    for screen in SCREENS:
        ui = _FakeUI()
        selection = DashboardSelection(screen=screen, sessions=data.session_dates)
        payloads = cache.get(selection)
        result = app.render_dashboard(data, selection, payloads, ui)
        assert result.screen == screen
        assert ui.calls
        assert "title" in ui.call_names()


def test_render_structure_emits_charts_and_synthetic_label(data) -> None:
    ui = _FakeUI()
    selection = DashboardSelection(
        screen="structure", mode="replay", date="2020-03-13", sessions=data.session_dates
    )
    payloads = PanelCache(data).get(selection)
    app.render_dashboard(data, selection, payloads, ui)
    rendered = [kwargs for name, _args, kwargs in ui.calls if name == "pyplot"]
    captions = " ".join(
        str(call_args) for name, call_args, _kwargs in ui.calls if name == "caption"
    )
    markdown = " ".join(
        str(call_args) for name, call_args, _kwargs in ui.calls if name == "markdown"
    )
    assert rendered, "structure screen must render chart figures"
    assert "Synthetic demo" in markdown
    assert "Selected session" in captions or "Synthetic demo" in markdown


def test_render_replay_revealed_shows_outcome_metrics(data) -> None:
    ui = _FakeUI()
    selection = DashboardSelection(
        screen="replay", mode="replay", date="2020-02-24", reveal=True, sessions=data.session_dates
    )
    payloads = PanelCache(data).get(selection)
    app.render_dashboard(data, selection, payloads, ui)
    metrics = [(args, kwargs) for name, args, kwargs in ui.calls if name == "metric"]
    assert metrics
    assert any(len(args) >= 2 or kwargs.get("value") is not None for args, kwargs in metrics)


def test_plain_text_dashboard_mentions_all_screens(data) -> None:
    selection = app.default_selection(data)
    text = app.plain_text_dashboard(data, selection, PanelCache(data).get(selection))
    for label in ("Structure", "Replay", "Validation", "Data"):
        assert label in text
    assert selection.date in text


def test_main_demo_without_streamlit_prints_dashboard(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app, "st", None)
    assert app.main(["--profile", "demo"]) == 0
    output = capsys.readouterr().out
    assert "TopoMarket dashboard" in output
    assert "Structure" in output
    assert "Data" in output


def test_selection_from_state_and_keyboard_command(data) -> None:
    state = {
        "tm_screen": "replay",
        "tm_mode": "replay",
        "tm_date": data.session_dates[10],
        "tm_reveal": True,
        "tm_member": None,
        "tm_run": None,
        "tm_network_view": "mapper",
    }
    selection = app.selection_from_state(state, data)
    assert selection.screen == "replay"
    assert selection.mode == "replay"
    assert selection.reveal is True
    assert selection.network_view == "mapper"

    updated = app.apply_action_to_state(state, "toggle_blind", data)
    assert updated.reveal is False

    updated = app.apply_action_to_state(state, "next_session", data)
    assert updated.date == data.session_dates[11]


def test_run_shell_plain_fallback(capsys: pytest.CaptureFixture[str]) -> None:
    args = app.parse_args(["--profile", "demo"])
    assert app.run_shell(args, streamlit_module=None) == 0
    output = capsys.readouterr().out
    assert "TopoMarket dashboard" in output


def test_default_selection_uses_a_warm_showcase_scene(data) -> None:
    default = app.default_selection(data)
    assert default.screen == "structure"
    assert default.date in data.session_dates
    assert data.session_dates.index(default.date) >= 60


def test_parser_defaults_to_the_public_demo() -> None:
    parsed = app.parse_args([])
    assert parsed.profile == "demo"
    assert parsed.data_dir is None
