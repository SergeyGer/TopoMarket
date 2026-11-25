"""Shared visual tokens for the upgraded Structure/Replay dashboard (UI04).

The tokens keep the canvas neutral, market series teal and benchmarks/thresholds
amber, while all text tokens pass WCAG AA contrast on the canvas.  Charts and the
Streamlit shell import the same values so the legend colour of a series never
disagrees with the chart.  The module has no Streamlit dependency and can be
used from tests and offline tooling.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Neutral canvas and ink tokens.  Contrast values are asserted in tests.
CANVAS = "#F8FAFC"
CANVAS_SOFT = "#EEF2F7"
INK = "#0F172A"
MUTED = "#475569"
GRID = "#CBD5E1"
BORDER = "#94A3B8"

#: Market series (teal) and benchmark/threshold (amber) tokens.
TEAL = "#0F766E"
TEAL_LIGHT = "#14B8A6"
TEAL_SOFT = "#99F6E4"
BLUE = "#0369A1"
AMBER = "#B45309"
AMBER_SOFT = "#FDE68A"
ALERT = "#B91C1C"
ALERT_SOFT = "#FEE2E2"
POSITIVE = "#047857"
NEGATIVE = "#B91C1C"

#: Series -> colour/legend mappings shared by charts and the shell.
SERIES_COLORS: dict[str, str] = {
    "sp500": TEAL,
    "vix": BLUE,
    "score": TEAL,
    "threshold": AMBER,
    "alert": AMBER,
    "matched": POSITIVE,
    "late": ALERT,
    "false": MUTED,
    "pending": AMBER,
    "outcome": AMBER,
    "origin": INK,
}

SERIES_LABELS: dict[str, str] = {
    "sp500": "S&P 500 close (index points)",
    "vix": "VIX close (index points)",
    "score": "TDA score percentile (comparative)",
    "threshold": "Frozen alert threshold (percentile)",
    "alert": "Alert",
    "matched": "Warning matched a breach episode",
    "late": "Late alert (after onset)",
    "false": "Mature false alert",
    "pending": "Pending alert (lead not matured)",
    "outcome": "Outcome horizon",
    "origin": "Origin close",
}

#: Marker symbols keep signals distinguishable without colour (UI04).
SERIES_MARKERS: dict[str, str] = {
    "alert": "^",
    "matched": "*",
    "late": "v",
    "false": "x",
    "pending": "o",
    "breach": "D",
    "origin": "_",
    "lowest": "s",
}

#: Minimum WCAG AA contrast for normal text.
MIN_TEXT_CONTRAST = 4.5


@dataclass(frozen=True, slots=True)
class Theme:
    """Resolved theme tokens used by the chart layer."""

    canvas: str = CANVAS
    canvas_soft: str = CANVAS_SOFT
    ink: str = INK
    muted: str = MUTED
    grid: str = GRID
    border: str = BORDER
    teal: str = TEAL
    teal_light: str = TEAL_LIGHT
    teal_soft: str = TEAL_SOFT
    blue: str = BLUE
    amber: str = AMBER
    amber_soft: str = AMBER_SOFT
    alert: str = ALERT
    alert_soft: str = ALERT_SOFT
    positive: str = POSITIVE
    negative: str = NEGATIVE


DEFAULT_THEME = Theme()


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    """Return the sRGB components (0..1) for a ``#rrggbb`` colour."""

    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    return tuple(int(text[index : index + 2], 16) / 255.0 for index in (0, 2, 4))  # type: ignore[return-value]


def relative_luminance(value: str) -> float:
    """Return the WCAG relative luminance of a colour."""

    channels = []
    for component in hex_to_rgb(value):
        channels.append(
            component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two colours."""

    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def text_contrast_tokens(theme: Theme | None = None) -> dict[str, float]:
    """Return contrast ratios for every text colour used on the canvas."""

    resolved = theme or DEFAULT_THEME
    return {
        "ink": contrast_ratio(resolved.ink, resolved.canvas),
        "muted": contrast_ratio(resolved.muted, resolved.canvas),
        "teal": contrast_ratio(resolved.teal, resolved.canvas),
        "blue": contrast_ratio(resolved.blue, resolved.canvas),
        "amber": contrast_ratio(resolved.amber, resolved.canvas),
        "alert": contrast_ratio(resolved.alert, resolved.canvas),
        "positive": contrast_ratio(resolved.positive, resolved.canvas),
        "border": contrast_ratio(resolved.border, resolved.canvas),
    }


def wcag_aa_failures(theme: Theme | None = None) -> list[str]:
    """Return text tokens that fail WCAG AA contrast on the canvas."""

    return [
        name
        for name, ratio in text_contrast_tokens(theme).items()
        if name not in {"border"} and ratio < MIN_TEXT_CONTRAST
    ]


__all__ = [
    "ALERT",
    "ALERT_SOFT",
    "AMBER",
    "AMBER_SOFT",
    "BLUE",
    "BORDER",
    "CANVAS",
    "CANVAS_SOFT",
    "DEFAULT_THEME",
    "GRID",
    "INK",
    "MIN_TEXT_CONTRAST",
    "MUTED",
    "NEGATIVE",
    "POSITIVE",
    "SERIES_COLORS",
    "SERIES_LABELS",
    "SERIES_MARKERS",
    "TEAL",
    "TEAL_LIGHT",
    "TEAL_SOFT",
    "Theme",
    "contrast_ratio",
    "hex_to_rgb",
    "relative_luminance",
    "text_contrast_tokens",
    "wcag_aa_failures",
]
