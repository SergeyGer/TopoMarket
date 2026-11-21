#!/usr/bin/env python3
"""Streamlit shell and repository entry point for TopoMarket.

The module can be imported without Streamlit installed. Streamlit is treated
as an optional UI dependency: its import is guarded and rendering falls back
to plain text when it is unavailable, which keeps CLI usage and smoke tests
working offline.
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
from topomarket.ui.overview import (  # noqa: E402
    build_overview,
    plain_text_overview,
)

try:  # Streamlit is optional; importing app.py must work without it.
    import streamlit as st  # type: ignore[import-not-found]  # noqa: E402
except ImportError:  # pragma: no cover - exercised when Streamlit is absent
    st = None  # type: ignore[assignment]


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the Streamlit shell entry point."""

    parser = argparse.ArgumentParser(
        prog="app.py",
        description=(
            "TopoMarket Streamlit shell. Run with "
            "`streamlit run app.py -- --profile demo|private`."
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


def render_overview(
    overview: Mapping[str, Any],
    streamlit_module: Any | None = None,
) -> None:
    """Render ``overview`` with Streamlit."""

    ui = streamlit_module if streamlit_module is not None else st
    if ui is None:  # pragma: no cover - defensive; main() falls back to text
        raise RuntimeError("Streamlit is not available")

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


def _in_streamlit_runtime(streamlit_module: Any | None = None) -> bool:
    """Return whether the real Streamlit script runner is active."""

    ui = streamlit_module if streamlit_module is not None else st
    if ui is None:
        return False
    try:
        return bool(ui.runtime.exists())
    except Exception:  # pragma: no cover - defensive for alternative runtimes
        return False


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
        return 0

    if not _in_streamlit_runtime(st):
        # Running ``python app.py`` instead of ``streamlit run app.py`` is
        # useful for smoke checks, so print the same overview as plain text.
        print(plain_text_overview(overview))
        if getattr(st, "__name__", "") == "streamlit":
            return 0

    render_overview(overview, st)
    return 0


if __name__ == "__main__":
    if st is not None and (
        getattr(st, "__name__", "") == "streamlit" or _in_streamlit_runtime(st)
    ):
        # Raising SystemExit inside ``streamlit run`` would abort the script
        # runner before it can finalise the page.
        main()
    else:
        raise SystemExit(main())


__all__ = [
    "build_overview",
    "build_parser",
    "load_overview",
    "main",
    "parse_args",
    "render_overview",
    "run",
]

# Friendly aliases for embedders and tests.
load_overview = build_overview
run = main
