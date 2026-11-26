"""Tests for the Streamlit shell in ``app.py``."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from topomarket.data import generate_synthetic, write_manifest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
REPO_ROOT = APP_PATH.parent

import app as app_module  # noqa: E402  (repository root is on sys.path)


def test_parse_args_forwards_profile_and_data_dir(tmp_path: Path) -> None:
    assert app_module.parse_args([]).profile == "demo"
    assert app_module.parse_args(["--profile", "private"]).profile == "private"

    parsed = app_module.parse_args(["--profile", "demo", "--data-dir", str(tmp_path)])
    assert parsed.profile == "demo"
    assert parsed.data_dir == tmp_path

    with pytest.raises(SystemExit):
        app_module.parse_args(["--profile", "mystery"])


def test_build_overview_for_demo_profile() -> None:
    overview = app_module.build_overview("demo")

    assert overview["title"] == "TopoMarket"
    assert overview["heading"] == "Overview"
    assert overview["profile"] == "demo"
    assert overview["profile_badge"] == "demo"
    assert overview["data_source"] == "synthetic"
    assert overview["data_source_label"] == "Data source: synthetic"
    assert "Overview" in overview["navigation"]
    assert "Markets" in overview["navigation"]
    assert overview["latest_data_date"] or overview["empty_state"]


def test_build_overview_for_empty_data_directory(tmp_path: Path) -> None:
    overview = app_module.build_overview("demo", data_dir=tmp_path / "empty")

    assert overview["latest_data_date"] is None
    assert overview["data_available"] is False
    assert overview["empty_state"]
    assert "no data" in overview["empty_state"].lower()


def test_build_overview_reads_latest_date_from_csv(tmp_path: Path) -> None:
    data_dir = tmp_path / "synthetic"
    generate_synthetic(data_dir)

    overview = app_module.build_overview("demo", data_dir=data_dir)

    assert overview["latest_data_date"] == "2024-01-30"
    assert overview["latest_data_date_label"] == "Latest data date: 2024-01-30"
    assert overview["empty_state"] is None


def test_build_overview_prefers_explicit_manifest_date(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_manifest(data_dir, {"latest_date": "2025-03-04"})

    overview = app_module.build_overview("demo", data_dir=data_dir)

    assert overview["latest_data_date"] == "2025-03-04"


def test_main_uses_plain_text_fallback_without_streamlit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app_module, "st", None)

    assert app_module.main(["--profile", "demo"]) == 0

    output = capsys.readouterr().out
    assert "TopoMarket" in output
    assert "Profile badge: demo" in output
    assert "Data source: synthetic" in output
    assert "Navigation:" in output


def test_app_imports_without_streamlit() -> None:
    script = "\n".join(
        [
            "import sys",
            "sys.modules['streamlit'] = None",
            "import app",
            "assert app.st is None",
            "print(app.parse_args(['--profile', 'demo']).profile)",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "demo"


@pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None,
    reason="Streamlit is an optional dependency",
)
def test_streamlit_app_smoke_run() -> None:
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:  # pragma: no cover - older Streamlit releases
        pytest.skip("streamlit.testing.v1 is not available")

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app_test.run()

    assert not list(app_test.exception), [item.message for item in app_test.exception]
    assert [title.value for title in app_test.title] == ["TopoMarket research"]
    assert [heading.value for heading in app_test.subheader][0] == "Industry correlation network"

    captions = " ".join(item.value.lower() for item in app_test.caption)
    assert "synthetic" in captions
    markdown = " ".join(item.value.lower() for item in app_test.markdown)
    assert "synthetic demo" in markdown
    assert "selected session" in markdown

    sidebar_labels = {widget.label for widget in app_test.sidebar.selectbox}
    assert "Screen" in sidebar_labels
    assert "Jump to an alert" in sidebar_labels
    sidebar_radios = {widget.label for widget in app_test.sidebar.radio}
    assert "Mode" in sidebar_radios
    assert "Network view" in sidebar_radios
    sidebar_sliders = {widget.label for widget in app_test.sidebar.select_slider}
    assert "Selected session" in sidebar_sliders

    # The landing screen renders the interactive network plus the compact timeline;
    # the full three-panel timeline is an explicit opt-in.
    headings = [item.value for item in app_test.subheader]
    assert headings[:2] == ["Industry correlation network", "Score explanation"]
    assert any(checkbox.label == "Show the full shared timeline" for checkbox in app_test.checkbox)


@pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None,
    reason="Streamlit is an optional dependency",
)
def test_streamlit_mapper_edge_selector_and_highlight() -> None:
    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=120).run()
    assert not list(app_test.exception)
    app_test.radio(key="tm_view_label").set_value("Mapper groups").run()
    assert not list(app_test.exception)
    edge_select = app_test.selectbox(key="tm_edge_select")
    assert len(edge_select.options) > 1, "mapper edge picker should list the group pairs"
    edge_select.select(edge_select.options[1]).run()
    markdown = " ".join(item.value for item in app_test.markdown)
    assert "Highlighted edge" in markdown
    assert "shared portfolios" in markdown


@pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None,
    reason="Streamlit is an optional dependency",
)
def test_streamlit_preset_date_persists_across_screen_switch() -> None:
    """Regression: a programmatic date change must not be reverted by widget state."""

    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=120).run()
    assert not list(app_test.exception)
    app_test.button(key="tm_preset_matched_warning").click().run()
    assert not list(app_test.exception)
    assert app_test.session_state["tm_date"] == "2025-03-10"
    app_test.selectbox(key="tm_screen_label").select("Replay").run()
    assert not list(app_test.exception)
    assert app_test.session_state["tm_date"] == "2025-03-10"
    app_test.button(key="tm_reveal_action").click().run()
    assert not list(app_test.exception)
    assert app_test.session_state["tm_reveal"] is True
    markdown = " ".join(item.value for item in app_test.markdown)
    assert "Replay" in [item.value for item in app_test.title]
    assert (
        "Outcome" in markdown
        or "boundary" in " ".join(item.value for item in app_test.caption).lower()
    )


@pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None,
    reason="Streamlit is an optional dependency",
)
def test_streamlit_blind_replay_is_neutral_about_outcomes() -> None:
    """F02: blind Replay must not show retrospective preset names or classifications."""

    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=120).run()
    assert not list(app_test.exception)
    sidebar_text = (
        " ".join(
            str(item.value)
            for item in [
                *app_test.sidebar.markdown,
                *app_test.sidebar.caption,
            ]
        )
        + " "
        + " ".join(button.label for button in app_test.sidebar.button)
    )
    assert "Guided alert example" in sidebar_text
    assert "Late warning" not in sidebar_text

    app_test.button(key="tm_preset_matched_warning").click().run()
    assert not list(app_test.exception)
    app_test.selectbox(key="tm_screen_label").select("Replay").run()
    assert not list(app_test.exception)
    page_text = " ".join(
        str(item.value)
        for item in [
            *app_test.markdown,
            *app_test.caption,
            *app_test.info,
            *app_test.warning,
        ]
    )
    for forbidden in ("Late warning", "matched warning", "post_onset", "episode_onset"):
        assert forbidden not in page_text
    assert "Alert recorded" in page_text or "No alert recorded" in page_text


@pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None,
    reason="Streamlit is an optional dependency",
)
def test_streamlit_market_studio_guided_tour_and_comparison() -> None:
    """U1/U2/U5: blind isolation, inline reveal, frozen pair and guided sequence."""

    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=120).run()
    assert not list(app_test.exception)
    # U2: the initial blind replay must not offer the comparative view.
    assert not any(
        checkbox.label == "Compare two windows" for checkbox in app_test.sidebar.checkbox
    )
    captions = " ".join(str(caption.value) for caption in app_test.sidebar.caption)
    assert "Guided tour not started" in captions
    assert "Blind" in captions
    assert any(button.label.startswith("Guided:") for button in app_test.sidebar.button)

    # U5: reveal inline on Structure; the network stays mounted and the comparative
    # view becomes available without switching screens.
    app_test.button(key="tm_structure_reveal").click().run()
    assert not list(app_test.exception)
    assert any(checkbox.label == "Compare two windows" for checkbox in app_test.sidebar.checkbox)
    assert "Industry correlation network" in [str(item.value) for item in app_test.subheader]
    assert "Inline outcome" in [str(item.value) for item in app_test.subheader]
    assert any("10% boundary" in str(metric.label) for metric in app_test.metric)
    app_test.button(key="tm_structure_blind").click().run()
    assert not list(app_test.exception)
    assert not any(
        checkbox.label == "Compare two windows" for checkbox in app_test.sidebar.checkbox
    )

    # U1: first guided stop is the frozen retrospective synthetic pair; it enables
    # the comparison and both dated windows render without a blind-mode contradiction.
    app_test.sidebar.button(key="tm_guide_next").click().run()
    assert not list(app_test.exception)
    captions = " ".join(str(caption.value) for caption in app_test.sidebar.caption)
    assert "Guided step 1/5" in captions and "Synthetic market shift" in captions
    assert app_test.sidebar.checkbox(key="tm_compare").value is True
    subheaders = [str(subheader.value) for subheader in app_test.subheader]
    assert "Two-window comparison" in subheaders
    page_captions = " ".join(str(item.value) for item in [*app_test.markdown, *app_test.caption])
    assert "Retrospective synthetic example" in page_captions
    assert "2008-08-29" in page_captions and "2008-10-10" in page_captions
    assert "Edges added in window B" in page_captions
    for expected_step in (2, 3, 4, 5):
        app_test.sidebar.button(key="tm_guide_next").click().run()
        assert not list(app_test.exception)
        guided = [
            str(caption.value)
            for caption in app_test.sidebar.caption
            if "Guided step" in str(caption.value)
        ]
        assert guided and f"Guided step {expected_step}/5" in guided[0]


@pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None,
    reason="Streamlit is an optional dependency",
)
def test_streamlit_direct_inspection_tap_targets() -> None:
    """U4: single-tap node, reliable edge hit target and direct Mapper inspection."""

    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=180).run()
    assert not list(app_test.exception)
    node_buttons = [
        button
        for button in app_test.button
        if button.key and button.key.startswith("tm_node_tap::")
    ]
    assert len(node_buttons) == 12
    node_buttons[0].click().run()
    assert not list(app_test.exception)
    page_text = " ".join(str(item.value) for item in [*app_test.markdown, *app_test.caption])
    assert "Selected portfolio:" in page_text
    assert any(edge.label == "Edge inspector (reliable hit target)" for edge in app_test.selectbox)
    edge_select = next(
        edge for edge in app_test.selectbox if edge.label == "Edge inspector (reliable hit target)"
    )
    edge_select.select_index(1).run()
    assert not list(app_test.exception)
    page_text = " ".join(str(item.value) for item in [*app_test.markdown, *app_test.caption])
    assert "Selected edge:" in page_text

    view_radio = next(item for item in app_test.sidebar.radio if item.key == "tm_view_label")
    view_radio.set_value("Mapper groups").run()
    assert not list(app_test.exception)
    mapper_buttons = [
        button
        for button in app_test.button
        if button.key and button.key.startswith("tm_mapper_node::")
    ]
    assert mapper_buttons
    mapper_buttons[0].click().run()
    assert not list(app_test.exception)
    assert "Mapper groups" in [str(item.value) for item in app_test.subheader]


@pytest.mark.skipif(importlib.util.find_spec("streamlit") is None, reason="Streamlit is optional")
def test_streamlit_guided_comparison_is_chronological() -> None:
    """#77: Window A is earlier (29/66), Window B later (66/66), change +37."""

    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=180).run()
    app_test.sidebar.button(key="tm_guide_next").click().run()
    assert not list(app_test.exception)
    metrics = {str(metric.label): str(metric.value) for metric in app_test.metric}
    window_a = next((label for label in metrics if "Window A" in label), "")
    window_b = next((label for label in metrics if "Window B" in label), "")
    assert "2008-08-29" in window_a and metrics[window_a].startswith("29/66")
    assert "2008-10-10" in window_b and metrics[window_b].startswith("66/66")
    change = next(value for label, value in metrics.items() if "Change in qualified pairs" in label)
    assert change.startswith("+37")
    page = " ".join(
        str(item.value) for item in [*app_test.markdown, *app_test.caption, *app_test.warning]
    )
    assert "Edges added in window B: 37" in page and "removed: 0" in page
    assert "Retrospective synthetic example" in page


@pytest.mark.skipif(importlib.util.find_spec("streamlit") is None, reason="Streamlit is optional")
def test_streamlit_mapper_node_identity() -> None:
    """#78: node-01 and node-02 resolve to their exact groups/member counts."""

    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=180).run()
    view_radio = next(item for item in app_test.sidebar.radio if item.key == "tm_view_label")
    view_radio.set_value("Mapper groups").run()
    assert not list(app_test.exception)
    app_test.button(key="tm_mapper_node::node-01").click().run()
    page = " ".join(str(item.value) for item in [*app_test.markdown, *app_test.caption])
    assert "Selected Mapper group node-01 · 7 members" in page
    app_test.button(key="tm_mapper_node::node-02").click().run()
    page = " ".join(str(item.value) for item in [*app_test.markdown, *app_test.caption])
    assert "Selected Mapper group node-02 · 6 members" in page


@pytest.mark.skipif(importlib.util.find_spec("streamlit") is None, reason="Streamlit is optional")
def test_streamlit_late_alert_copy_after_reveal() -> None:
    """#79: 2025-03-10 is a recorded post-onset late alert with zero credit."""

    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=180).run()
    app_test.button(key="tm_preset_matched_warning").click().run()
    screen = next(item for item in app_test.sidebar.selectbox if item.key == "tm_screen_label")
    screen.select("Replay").run()
    app_test.button(key="tm_reveal_action").click().run()
    assert not list(app_test.exception)
    page = " ".join(
        str(item.value) for item in [*app_test.markdown, *app_test.caption, *app_test.warning]
    )
    assert "episode began on 2025-03-06" in page
    assert "included in the frozen evaluation as a late alert" in page
    assert "zero early-warning credit" in page
    assert "2.02%" in page and "10% target" in page
