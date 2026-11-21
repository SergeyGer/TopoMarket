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

    app_test = AppTest.from_file(str(APP_PATH), default_timeout=30)
    app_test.run()

    assert not list(app_test.exception)
    assert [title.value for title in app_test.title] == ["TopoMarket"]
    assert [heading.value for heading in app_test.subheader] == ["Overview"]

    markdown = " ".join(item.value.lower() for item in app_test.markdown)
    assert "profile badge" in markdown
    assert "demo" in markdown
    assert "data source" in markdown
    assert "synthetic" in markdown

    sidebar = " ".join(item.value for item in app_test.sidebar.markdown)
    for placeholder in ("Overview", "Markets", "Topology", "Evaluation"):
        assert placeholder in sidebar
