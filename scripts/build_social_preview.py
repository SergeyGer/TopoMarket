#!/usr/bin/env python3
"""Build the GitHub social preview (and the 16:9 opening/end cards) from synthetic data.

The image is a real frame of the TopoMarket Structure view: the 12 US industry
portfolios and their Pearson-correlation edges computed from the committed
synthetic ``showcase/`` fixture.  It is *not* a mock-up: the same
:func:`topomarket.analysis.network.build_correlation_network` payload drives the
application, so the preview can be regenerated from any accepted build.

The builder is deterministic and offline.  It writes:

* ``docs/assets/social_preview.png`` - 1280x640 GitHub social preview;
* ``docs/assets/opening_card_16x9.png`` - the same asset fitted to 1920x1080
  without stretching or cropping meaningful labels (opening shot);
* ``docs/assets/end_card_16x9.png`` - the static five-second end card with the
  repository URL.

Usage::

    python scripts/build_social_preview.py
    python scripts/build_social_preview.py --date 2020-03-16 --out docs/assets
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from topomarket.analysis.network import (  # noqa: E402
    DEFAULT_CORRELATION_CUTOFF,
    DEFAULT_CORRELATION_WINDOW,
    INDUSTRY_CODES,
    build_correlation_network,
)
from topomarket.topology import load_daily_rows  # noqa: E402

SHOWCASE = ROOT / "showcase"
REPOSITORY_URL = "github.com/SergeyGer/TopoMarket"
TAGLINE = "Market structure and early warning research"
TITLE = "TopoMarket"

INK = "#0B1220"
INK_SOFT = "#111C2E"
PAPER = "#F8FAFC"
MUTED = "#94A3B8"
TEAL = "#2DD4BF"
TEAL_DARK = "#0F766E"
AMBER = "#F59E0B"
GRID = "#1E2A3D"

DEFAULT_PREVIEW_DATE = "2020-02-24"


def _load_network(date: str) -> dict[str, Any]:
    rows = load_daily_rows(SHOWCASE)
    payload = build_correlation_network(
        rows,
        date,
        window=DEFAULT_CORRELATION_WINDOW,
        cutoff=DEFAULT_CORRELATION_CUTOFF,
    )
    if not payload["available"]:
        raise SystemExit(f"network unavailable for {date}: {payload['reason']}")
    payload["fixture"] = json.loads((SHOWCASE / "manifest.json").read_text(encoding="utf-8"))[
        "snapshot_id"
    ]
    payload["rows_path"] = "showcase/normalized/tda_daily.csv"
    return payload


def _draw_network(
    ax: plt.Axes,
    network: dict[str, Any],
    *,
    edge_alpha: float = 0.55,
    node_scale: float = 1.0,
    label_size: float = 9.5,
) -> None:
    ax.set_xlim(-1.72, 1.72)
    ax.set_ylim(-1.72, 1.72)
    ax.set_aspect("equal")
    ax.axis("off")
    nodes = {node["code"]: node for node in network["nodes"]}
    cutoff = float(network["cutoff"])
    low = max(cutoff, 0.0)
    span = max(1.0 - low, 0.05)
    for edge in network["edges"]:
        left = nodes[edge["source"]]
        right = nodes[edge["target"]]
        strength = (float(edge["correlation"]) - low) / span
        ax.plot(
            [left["x"], right["x"]],
            [left["y"], right["y"]],
            color=TEAL,
            linewidth=0.5 + 2.6 * strength,
            alpha=min(0.92, edge_alpha * (0.45 + 0.8 * strength)),
            solid_capstyle="round",
            zorder=1,
        )
    degree = {node["code"]: int(node.get("degree") or 0) for node in network["nodes"]}
    max_degree = max(degree.values()) if degree else 1
    for code in INDUSTRY_CODES:
        node = nodes[code]
        size = (150.0 + 420.0 * degree[code] / max(max_degree, 1)) * node_scale
        ax.scatter(
            [node["x"]],
            [node["y"]],
            s=size,
            color=TEAL,
            edgecolors=INK,
            linewidths=1.6,
            zorder=3,
        )
        ax.scatter(
            [node["x"]],
            [node["y"]],
            s=size * 0.38,
            color=INK,
            edgecolors="none",
            zorder=4,
        )
        label_radius = 1.28
        offset_x = math.copysign(0.14, node["x"]) if abs(node["x"]) > 0.05 else 0.0
        offset_y = math.copysign(0.10, node["y"]) if abs(node["y"]) > 0.05 else 0.14
        text = ax.annotate(
            node["short_label"],
            (node["x"], node["y"]),
            xytext=(
                label_radius * node["x"] + offset_x,
                label_radius * node["y"] + offset_y,
            ),
            textcoords="data",
            ha="center",
            va="center",
            fontsize=label_size,
            color=PAPER,
            fontweight="medium",
            zorder=5,
        )
        text.set_path_effects([patheffects.withStroke(linewidth=3, foreground=INK)])


def _figure() -> tuple[plt.Figure, plt.Axes]:
    figure = plt.figure(figsize=(12.8, 6.4), dpi=100)
    figure.patch.set_facecolor(INK)
    ax = figure.add_axes((0.415, 0.045, 0.57, 0.9))
    ax.set_facecolor(INK)
    return figure, ax


def _title_block(figure: plt.Figure, network: dict[str, Any]) -> None:
    figure.text(
        0.045,
        0.80,
        TITLE,
        fontsize=54,
        fontweight="bold",
        color=PAPER,
        ha="left",
        va="baseline",
    )
    figure.text(
        0.047,
        0.735,
        TAGLINE,
        fontsize=19.5,
        color=TEAL,
        ha="left",
        va="baseline",
    )
    figure.add_artist(Line2D([0.047, 0.295], [0.695, 0.695], color=TEAL_DARK, linewidth=2.4))
    figure.text(
        0.047,
        0.655,
        "How the shape of twelve industry portfolios changes under stress,",
        fontsize=13.0,
        color=MUTED,
        ha="left",
        va="baseline",
    )
    figure.text(
        0.047,
        0.607,
        "and whether topology flags a sharp S&P 500 decline early.",
        fontsize=13.0,
        color=MUTED,
        ha="left",
        va="baseline",
    )
    window = network["window"]
    provenance = (
        f"Synthetic demo  ·  {network['pairs_qualifying']}/{network['pairs_total']} pairs "
        f"at r >= {network['cutoff']:.2f}"
    )
    figure.text(
        0.047,
        0.205,
        provenance,
        fontsize=11.5,
        color=AMBER,
        ha="left",
        va="baseline",
    )
    figure.text(
        0.047,
        0.155,
        f"Trailing {window['required']} sessions {window['start']}..{window['end']}"
        f"  ·  fixture {network['fixture']}",
        fontsize=10.0,
        color=MUTED,
        ha="left",
        va="baseline",
    )
    figure.text(
        0.047,
        0.085,
        REPOSITORY_URL,
        fontsize=13.0,
        color=PAPER,
        ha="left",
        va="baseline",
        fontweight="medium",
    )
    figure.text(
        0.047,
        0.045,
        "Synthetic data only. No genuine market data is published.",
        fontsize=8.8,
        color="#64748B",
        ha="left",
        va="baseline",
    )


def build_social_preview(network: dict[str, Any], out: Path) -> Path:
    figure, ax = _figure()
    _draw_network(ax, network, edge_alpha=0.6, node_scale=1.15, label_size=10.5)
    _title_block(figure, network)
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=100, facecolor=INK)
    plt.close(figure)
    return out


def build_opening_card(preview_png: Path, out: Path) -> Path:
    """Fit the 1280x640 social preview onto a 1920x1080 card without distortion.

    The original 2:1 aspect ratio is preserved: the preview fills the full frame
    width and is letterboxed by 60 px top and bottom, so no title, tagline,
    label or plot area is stretched or cropped.  The synthetic provenance is
    already inside the preview, so the card adds no extra caption.
    """

    figure = plt.figure(figsize=(19.2, 10.8), dpi=100)
    figure.patch.set_facecolor(INK)
    axes = figure.add_axes((0.0, 0.0, 1.0, 1.0))
    axes.set_xlim(0.0, 19.2)
    axes.set_ylim(0.0, 10.8)
    axes.axis("off")
    image = plt.imread(preview_png)
    axes.imshow(image, extent=(0.0, 19.2, 0.6, 10.2), aspect="equal", zorder=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=100, facecolor=INK)
    plt.close(figure)
    return out


def build_end_card(out: Path) -> Path:
    figure = plt.figure(figsize=(19.2, 10.8), dpi=100)
    figure.patch.set_facecolor(INK)
    figure.text(
        0.5,
        0.66,
        TITLE,
        fontsize=96,
        fontweight="bold",
        color=PAPER,
        ha="center",
        va="center",
    )
    figure.text(
        0.5,
        0.545,
        TAGLINE,
        fontsize=32,
        color=TEAL,
        ha="center",
        va="center",
    )
    figure.add_artist(Line2D([0.30, 0.70], [0.475, 0.475], color=TEAL_DARK, linewidth=3))
    figure.text(
        0.5,
        0.36,
        "Explore the code and the live demo on GitHub",
        fontsize=27,
        color=MUTED,
        ha="center",
        va="center",
    )
    figure.text(
        0.5,
        0.255,
        REPOSITORY_URL,
        fontsize=48,
        fontweight="bold",
        color=AMBER,
        ha="center",
        va="center",
    )
    figure.text(
        0.5,
        0.115,
        "Synthetic demo fixture · no genuine market data · MIT licensed",
        fontsize=18,
        color="#64748B",
        ha="center",
        va="center",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=100, facecolor=INK)
    plt.close(figure)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the TopoMarket social preview and cards.")
    parser.add_argument("--date", default=DEFAULT_PREVIEW_DATE, help="Synthetic session frame.")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "assets")
    parser.add_argument("--preview-only", action="store_true")
    args = parser.parse_args(argv)
    network = _load_network(args.date)
    preview = build_social_preview(network, args.out / "social_preview.png")
    print(f"social preview: {preview} ({_image_size(preview)})")
    if not args.preview_only:
        opening = build_opening_card(preview, args.out / "opening_card_16x9.png")
        end = build_end_card(args.out / "end_card_16x9.png")
        print(f"opening card:   {opening} ({_image_size(opening)})")
        print(f"end card:       {end} ({_image_size(end)})")
    notes = {
        "title": TITLE,
        "tagline": TAGLINE,
        "frame_date": args.date,
        "fixture": network["fixture"],
        "rows_path": network["rows_path"],
        "window": network["window"],
        "pairs_qualifying": network["pairs_qualifying"],
        "pairs_total": network["pairs_total"],
        "cutoff": network["cutoff"],
        "synthetic": True,
        "private_data": False,
        "repository_url": REPOSITORY_URL,
    }
    notes_path = args.out / "social_preview.json"
    notes_path.write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8")
    print(f"notes:          {notes_path}")
    return 0


def _image_size(path: Path) -> str:
    from PIL import Image

    with Image.open(path) as image:
        return f"{image.width}x{image.height}"


if __name__ == "__main__":
    raise SystemExit(main())
