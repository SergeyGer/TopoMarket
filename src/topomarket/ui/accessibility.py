"""Accessibility helpers for the Step 7 dashboard.

Everything here is pure Python and can be tested without a browser or
Streamlit.  The module owns the design-token palette, WCAG contrast maths,
chart/table alternative text, shape-plus-text alert markers and the
reduced-motion policy used by the shell.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

#: Minimum contrast ratio for normal-sized text under WCAG 2.1 AA.
WCAG_AA_TEXT_CONTRAST = 4.5
WCAG_AA_LARGE_TEXT_CONTRAST = 3.0
WCAG_AAA_TEXT_CONTRAST = 7.0

#: Colour tokens shared by every dashboard screen.  The values are deliberately
#: conservative, light-surface colours: every text pair below exceeds 4.5:1.
COLOR_TOKENS: dict[str, str] = {
    "background": "#FFFFFF",
    "background_alt": "#F5F7FA",
    "paper": "#FFFFFF",
    "surface": "#F6F8FA",
    "surface_alt": "#F5F7FA",
    "surface_raised": "#FFFFFF",
    "panel": "#F6F8FA",
    "card": "#FFFFFF",
    "foreground": "#1F2328",
    "text": "#1F2328",
    "text_primary": "#1F2328",
    "text_strong": "#1F2328",
    "ink": "#1F2328",
    "muted": "#57606A",
    "muted_text": "#57606A",
    "text_muted": "#57606A",
    "text_secondary": "#57606A",
    "subtle": "#57606A",
    "axis": "#57606A",
    "border": "#D0D7DE",
    "grid": "#D0D7DE",
    "accent": "#0969DA",
    "primary": "#0969DA",
    "focus": "#0969DA",
    "focus_ring": "#0969DA",
    "highlight": "#0969DA",
    "link": "#0969DA",
    "info": "#0969DA",
    "positive": "#1A7F37",
    "success": "#1A7F37",
    "warning": "#9A6700",
    "alert": "#9A6700",
    "danger": "#CF222E",
    "critical": "#CF222E",
    "negative": "#CF222E",
    "error": "#CF222E",
    "on_accent": "#FFFFFF",
    "on_primary": "#FFFFFF",
    "on_positive": "#FFFFFF",
    "on_success": "#FFFFFF",
    "on_warning": "#FFFFFF",
    "on_danger": "#FFFFFF",
    "on_critical": "#FFFFFF",
}

#: Common aliases for the palette.
PALETTE = COLOR_TOKENS
COLORS = COLOR_TOKENS
TOKENS = COLOR_TOKENS
COLOR_TOKEN_NAMES: tuple[str, ...] = tuple(COLOR_TOKENS)

#: Pairs used by the dashboard's text.  Every pair must reach 4.5:1.
TEXT_TOKEN_PAIRS: tuple[tuple[str, str], ...] = (
    ("text", "background"),
    ("text", "surface"),
    ("muted", "background"),
    ("muted", "surface"),
    ("muted", "surface_alt"),
    ("accent", "background"),
    ("accent", "surface"),
    ("positive", "background"),
    ("warning", "background"),
    ("warning", "surface"),
    ("danger", "background"),
    ("on_accent", "accent"),
    ("on_primary", "primary"),
    ("on_positive", "positive"),
    ("on_success", "success"),
    ("on_warning", "warning"),
    ("on_danger", "danger"),
    ("on_critical", "critical"),
)

TEXT_PAIRS = TEXT_TOKEN_PAIRS
TOKEN_PAIRS = TEXT_TOKEN_PAIRS
CONTRAST_PAIRS = TEXT_TOKEN_PAIRS
TEXT_CONTRAST_PAIRS = TEXT_TOKEN_PAIRS
TOKEN_CONTRAST_PAIRS = TEXT_TOKEN_PAIRS
COLOR_PAIRS = TEXT_TOKEN_PAIRS
COLOR_TOKEN_PAIRS = TEXT_TOKEN_PAIRS
TEXT_COLOR_PAIRS = TEXT_TOKEN_PAIRS
MIN_CONTRAST_RATIO = WCAG_AA_TEXT_CONTRAST
MIN_CONTRAST = WCAG_AA_TEXT_CONTRAST
WCAG_MIN_CONTRAST = WCAG_AA_TEXT_CONTRAST
AA_CONTRAST = WCAG_AA_TEXT_CONTRAST
MIN_TEXT_CONTRAST = WCAG_AA_TEXT_CONTRAST
WCAG_TEXT_CONTRAST = WCAG_AA_TEXT_CONTRAST
TOKEN_COLORS = COLOR_TOKENS
THEME_COLORS = COLOR_TOKENS
COLOR_MAP = COLOR_TOKENS
ACCESSIBILITY_COLORS = COLOR_TOKENS

_NAMED_COLORS = {
    "black": "#000000",
    "white": "#FFFFFF",
    "transparent": "rgba(255, 255, 255, 0)",
    "red": "#FF0000",
    "green": "#008000",
    "blue": "#0000FF",
    "gray": "#808080",
    "grey": "#808080",
}
_HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
_RGB_RE = re.compile(
    r"rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})"
    r"(?:\s*,\s*([0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?|\.?[0-9]+(?:[eE][+-]?[0-9]+)?))?"
    r"\s*\)"
)
_OPAQUE_WHITE = (255, 255, 255, 1.0)


def _resolve_color(color: Any) -> str:
    if not isinstance(color, str):
        raise ValueError(f"colour must be a string, got {color!r}")
    text = color.strip()
    lowered = text.lower()
    if lowered in COLOR_TOKENS:
        return COLOR_TOKENS[lowered]
    if lowered in _NAMED_COLORS:
        return _NAMED_COLORS[lowered]
    if _HEX_RE.fullmatch(text):
        return text
    if _RGB_RE.fullmatch(text):
        return text
    raise ValueError(f"unsupported colour value {color!r}")


def _color_components(color: Any) -> tuple[int, int, int, float]:
    """Return ``(red, green, blue, alpha)`` for a supported colour value."""

    text = _resolve_color(color)
    match = _HEX_RE.fullmatch(text)
    if match:
        value = match.group(1)
        if len(value) == 3:
            value = "".join(channel * 2 for channel in value)
        channels = tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
        return channels[0], channels[1], channels[2], 1.0

    match = _RGB_RE.fullmatch(text)
    if match:
        channels = tuple(int(match.group(index)) for index in (1, 2, 3))
        if any(channel < 0 or channel > 255 for channel in channels):
            raise ValueError(f"RGB channel outside 0-255 in {color!r}")
        alpha_text = match.group(4)
        alpha = 1.0 if alpha_text is None else float(alpha_text)
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha channel outside 0-1 in {color!r}")
        return channels[0], channels[1], channels[2], alpha
    raise ValueError(f"unsupported colour value {color!r}")


def color_channels(color: Any) -> tuple[int, int, int]:
    """Return the eight-bit red/green/blue channels of ``color``.

    Translucent colours are rejected here because relative luminance is only
    defined for an opaque colour; :func:`contrast_ratio` composites them
    against the other colour first.
    """

    red, green, blue, alpha = _color_components(color)
    if alpha != 1.0:
        raise ValueError(f"colour must be opaque to compute luminance: {color!r}")
    return red, green, blue


def _composite_over(
    foreground: tuple[int, int, int, float],
    background: tuple[int, int, int, float],
) -> tuple[int, int, int, float]:
    """Composite ``foreground`` over an opaque ``background`` in sRGB space."""

    red, green, blue, alpha = foreground
    background_red, background_green, background_blue, _ = background
    blended = (
        round(red * alpha + background_red * (1.0 - alpha)),
        round(green * alpha + background_green * (1.0 - alpha)),
        round(blue * alpha + background_blue * (1.0 - alpha)),
    )
    return blended[0], blended[1], blended[2], 1.0


def composite_color(foreground: Any, background: Any = "#FFFFFF") -> str:
    """Return ``foreground`` composited over an opaque ``background``."""

    base = _color_components(background)
    if base[3] != 1.0:
        base = _composite_over(base, _OPAQUE_WHITE)
    result = _composite_over(_color_components(foreground), base)
    return "#{:02X}{:02X}{:02X}".format(*result[:3])


def _linear_channel(value: int) -> float:
    channel = value / 255.0
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _opaque_luminance(color: tuple[int, int, int, float]) -> float:
    red, green, blue, _ = color
    return (
        0.2126 * _linear_channel(red)
        + 0.7152 * _linear_channel(green)
        + 0.0722 * _linear_channel(blue)
    )


def relative_luminance(color: Any) -> float:
    """Return the WCAG relative luminance of an opaque colour."""

    components = _color_components(color)
    if components[3] != 1.0:
        raise ValueError(f"colour must be opaque to compute luminance: {color!r}")
    return _opaque_luminance(components)


def contrast_ratio(foreground: Any, background: Any) -> float:
    """Return the WCAG contrast ratio between two colours or token names.

    Any alpha channel is composited before the luminance calculation, so a
    translucent colour cannot masquerade as its fully opaque equivalent.
    """

    base = _color_components(background)
    if base[3] != 1.0:
        base = _composite_over(base, _OPAQUE_WHITE)
    top = _color_components(foreground)
    if top[3] != 1.0:
        top = _composite_over(top, base)
    first = _opaque_luminance(top)
    second = _opaque_luminance(base)
    lighter = max(first, second)
    darker = min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def wcag_contrast_ratio(foreground: Any, background: Any) -> float:
    return contrast_ratio(foreground, background)


def contrast(foreground: Any, background: Any) -> float:
    return contrast_ratio(foreground, background)


def passes_wcag(
    foreground: Any,
    background: Any,
    minimum: float = WCAG_AA_TEXT_CONTRAST,
) -> bool:
    """Return whether a colour pair meets the requested WCAG threshold."""

    return contrast_ratio(foreground, background) >= float(minimum)


def meets_wcag_contrast(
    foreground: Any,
    background: Any,
    minimum: float = WCAG_AA_TEXT_CONTRAST,
) -> bool:
    return passes_wcag(foreground, background, minimum)


def check_text_contrast(
    pairs: Iterable[tuple[str, str]] | None = None,
    minimum: float = WCAG_AA_TEXT_CONTRAST,
) -> dict[tuple[str, str], float]:
    """Check token pairs and return their ratios.

    ``ValueError`` is raised when any pair fails so a renderer can fail closed
    instead of silently shipping unreadable text.
    """

    selected = TEXT_TOKEN_PAIRS if pairs is None else tuple(pairs)
    ratios: dict[tuple[str, str], float] = {}
    failures: list[str] = []
    for foreground, background in selected:
        ratio = contrast_ratio(foreground, background)
        ratios[(foreground, background)] = ratio
        if ratio < float(minimum):
            failures.append(f"{foreground} on {background}: {ratio:.2f}:1 < {float(minimum):.2f}:1")
    if failures:
        raise ValueError("WCAG contrast failure(s): " + "; ".join(failures))
    return ratios


def token_contrast_report(
    minimum: float = WCAG_AA_TEXT_CONTRAST,
) -> dict[str, Any]:
    """Return a JSON-friendly report for the built-in token pairs."""

    report: dict[str, Any] = {
        "minimum": float(minimum),
        "pairs": [],
        "passed": True,
    }
    for foreground, background in TEXT_TOKEN_PAIRS:
        ratio = contrast_ratio(foreground, background)
        passed = ratio >= float(minimum)
        report["pairs"].append(
            {
                "foreground": foreground,
                "background": background,
                "ratio": ratio,
                "passed": passed,
            }
        )
        report["passed"] = bool(report["passed"] and passed)
    return report


def validate_color_tokens(
    tokens: Mapping[str, str] | None = None,
    minimum: float = WCAG_AA_TEXT_CONTRAST,
) -> bool:
    """Validate the palette's text pairs, raising on any WCAG failure."""

    palette = COLOR_TOKENS if tokens is None else tokens
    if not isinstance(palette, Mapping):
        raise ValueError("color tokens must be a mapping")
    missing = [name for name in ("background", "text", "muted", "accent") if name not in palette]
    if missing:
        raise ValueError("missing colour token(s): " + ", ".join(missing))
    for foreground, background in TEXT_TOKEN_PAIRS:
        if foreground not in palette or background not in palette:
            continue
        ratio = contrast_ratio(palette[foreground], palette[background])
        if ratio < float(minimum):
            raise ValueError(
                f"WCAG contrast failure for {foreground} on {background}: "
                f"{ratio:.2f}:1 < {float(minimum):.2f}:1"
            )
    return True


#: Compatibility aliases for palette validation.
validate_contrast = validate_color_tokens
validate_palette = validate_color_tokens
validate_wcag = validate_color_tokens


def check_contrast(*args: Any, minimum: float = WCAG_AA_TEXT_CONTRAST) -> Any:
    """Check either one colour pair or all built-in text pairs.

    ``check_contrast(foreground, background)`` returns a boolean, while
    ``check_contrast()`` (or a single iterable of pairs) returns the ratio
    mapping used by :func:`check_text_contrast`.
    """

    if len(args) >= 2:
        return passes_wcag(args[0], args[1], minimum)
    if len(args) == 1:
        value = args[0]
        if isinstance(value, str):
            raise ValueError("check_contrast needs a foreground and a background colour")
        return check_text_contrast(value, minimum=minimum)
    return check_text_contrast(minimum=minimum)


def validate_accessibility(minimum: float = WCAG_AA_TEXT_CONTRAST) -> dict[str, Any]:
    """Run the static accessibility checks and return a compact report."""

    validate_color_tokens(minimum=minimum)
    for level in ("info", "warning", "critical"):
        marker = alert_marker(level)
        if not marker.shape or not marker.text:
            raise ValueError(f"alert marker {level!r} must include a shape and text")
    chart = chart_alternative("Dashboard chart")
    table = table_alternative("Dashboard table")
    if not str(chart).strip() or not str(table).strip():
        raise ValueError("chart and table alternatives must not be empty")
    css = reduced_motion_css()
    if REDUCED_MOTION_QUERY not in css:
        raise ValueError("reduced-motion CSS must honour the media query")
    return {
        "contrast": True,
        "minimum": float(minimum),
        "chart_alternative": str(chart),
        "table_alternative": str(table),
        "reduced_motion": True,
    }


# ---------------------------------------------------------------------------
# Alternative text
# ---------------------------------------------------------------------------
class AlternativeText(str):
    """A non-empty string exposing the usual alternative-text attribute names."""

    @property
    def alt(self) -> str:
        return str(self)

    @property
    def text(self) -> str:
        return str(self)

    @property
    def description(self) -> str:
        return str(self)

    @property
    def label(self) -> str:
        return str(self)

    @property
    def caption(self) -> str:
        return str(self)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if key in {"alt", "text", "description", "label", "caption", "value", "string"}:
                return str(self)
            raise KeyError(key)
        return str.__getitem__(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def _summary(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, Mapping):
        if not value:
            return None
        return f"{len(value)} item(s)"
    if isinstance(value, (list, tuple, set, frozenset)):
        if not value:
            return None
        return f"{len(value)} item(s)"
    text = str(value).strip()
    return text or None


def alternative_text(
    subject: Any = "Visual",
    *,
    description: Any = None,
    summary: Any = None,
    alt: Any = None,
    title: Any = None,
    kind: str = "Visual",
    **kwargs: Any,
) -> AlternativeText:
    """Build a non-empty alternative description for a visual element."""

    for key in ("data", "values", "series", "rows", "columns", "caption"):
        if key in kwargs and summary is None:
            summary = kwargs.pop(key)
    if kwargs:
        extra = ", ".join(f"{key}={value}" for key, value in sorted(kwargs.items()))
        description = extra if description is None else f"{description}; {extra}"

    primary = title if title is not None else subject
    heading = str(primary).strip() if primary is not None else ""
    if not heading:
        heading = kind
    parts = [f"{kind}: {heading}"]
    detail = _summary(alt) or _summary(description) or _summary(summary)
    if detail:
        parts.append(detail)
    else:
        parts.append("no data points are available")
    return AlternativeText(" — ".join(parts))


def chart_alternative(
    title: Any = "Chart",
    *,
    description: Any = None,
    summary: Any = None,
    alt: Any = None,
    data: Any = None,
    series: Any = None,
    **kwargs: Any,
) -> AlternativeText:
    """Return a non-empty text alternative for a chart."""

    if summary is None:
        summary = data if data is not None else series
    return alternative_text(
        title,
        description=description,
        summary=summary,
        alt=alt,
        kind="Chart",
        **kwargs,
    )


def table_alternative(
    title: Any = "Table",
    *,
    description: Any = None,
    summary: Any = None,
    alt: Any = None,
    columns: Any = None,
    rows: Any = None,
    **kwargs: Any,
) -> AlternativeText:
    """Return a non-empty text alternative for a data table."""

    if summary is None:
        if columns is not None and rows is not None:
            try:
                summary = f"{len(rows)} row(s) and {len(columns)} column(s)"
            except TypeError:
                summary = None
        elif rows is not None:
            summary = rows
        elif columns is not None:
            summary = columns
    return alternative_text(
        title,
        description=description,
        summary=summary,
        alt=alt,
        kind="Table",
        **kwargs,
    )


#: Aliases used by older renderers.
chart_alt = chart_alternative
table_alt = table_alternative
chart_alt_text = chart_alternative
table_alt_text = table_alternative
chart_description = chart_alternative
table_description = table_alternative
accessible_chart_alternative = chart_alternative
accessible_table_alternative = table_alternative
chart_accessible_text = chart_alternative
table_accessible_text = table_alternative
accessible_alternative = alternative_text
alt_text = alternative_text


def chart_table_alternatives(
    chart_title: Any = "Chart",
    table_title: Any = "Table",
    **kwargs: Any,
) -> dict[str, str]:
    """Return both alternatives in one JSON-friendly mapping."""

    chart_kwargs = kwargs.get("chart", {})
    table_kwargs = kwargs.get("table", {})
    return {
        "chart": str(chart_alternative(chart_title, **chart_kwargs)),
        "table": str(table_alternative(table_title, **table_kwargs)),
    }


# ---------------------------------------------------------------------------
# Shape-plus-text alert markers
# ---------------------------------------------------------------------------
class AlertMarker(str):
    """A marker whose string form contains both a shape and a text label."""

    shape: str
    text: str
    level: str

    def __new__(
        cls,
        level: str,
        shape: str,
        text: str,
    ) -> AlertMarker:
        instance = super().__new__(cls, f"{shape} {text}")
        instance.level = level
        instance.shape = shape
        instance.text = text
        return instance

    @property
    def glyph(self) -> str:
        return self.shape

    @property
    def symbol(self) -> str:
        return self.shape

    @property
    def label(self) -> str:
        return self.text

    @property
    def marker(self) -> str:
        return str(self)

    def __getitem__(self, key: str) -> str:
        if key in {"shape", "glyph", "symbol"}:
            return self.shape
        if key in {"text", "label", "name"}:
            return self.text
        if key in {"marker", "value", "string", "str"}:
            return str(self)
        if key == "level":
            return self.level
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> tuple[str, ...]:
        return ("level", "shape", "text")

    def values(self) -> tuple[str, ...]:
        return (self.level, self.shape, self.text)

    def items(self) -> tuple[tuple[str, str], ...]:
        return tuple((key, self[key]) for key in self.keys())

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str) and item in self.keys():
            return True
        return str.__contains__(self, item)

    def as_dict(self) -> dict[str, str]:
        return {"level": self.level, "shape": self.shape, "text": self.text}

    to_dict = as_dict


ALERT_MARKERS: dict[str, AlertMarker] = {
    "info": AlertMarker("info", "●", "Info"),
    "success": AlertMarker("success", "■", "Success"),
    "positive": AlertMarker("success", "■", "Success"),
    "warning": AlertMarker("warning", "▲", "Warning"),
    "alert": AlertMarker("warning", "▲", "Warning"),
    "caution": AlertMarker("warning", "▲", "Warning"),
    "danger": AlertMarker("danger", "◆", "Danger"),
    "critical": AlertMarker("critical", "◆", "Critical"),
    "error": AlertMarker("danger", "◆", "Danger"),
    "neutral": AlertMarker("neutral", "○", "Neutral"),
    "low": AlertMarker("info", "●", "Info"),
    "medium": AlertMarker("warning", "▲", "Warning"),
    "high": AlertMarker("critical", "◆", "Critical"),
}

ALERT_MARKER_SHAPES = {
    "info": "●",
    "success": "■",
    "warning": "▲",
    "danger": "◆",
    "critical": "◆",
    "neutral": "○",
}
ALERT_MARKER_TEXT = {
    "info": "Info",
    "success": "Success",
    "warning": "Warning",
    "danger": "Danger",
    "critical": "Critical",
    "neutral": "Neutral",
}


def alert_marker(level: Any = "info", text: Any = None) -> AlertMarker:
    """Return a shape-plus-text marker for an alert level.

    A custom ``text`` replaces the default label but never removes the shape,
    so the marker remains distinguishable without colour.
    """

    key = str(level).strip().lower().replace("-", "_").replace(" ", "_")
    try:
        marker = ALERT_MARKERS[key]
    except KeyError:
        expected = ", ".join(sorted(ALERT_MARKERS))
        raise ValueError(f"Unknown alert level {level!r}; expected one of: {expected}") from None
    if text is None:
        return marker
    label = str(text).strip()
    if not label:
        return marker
    if label.lower() == marker.text.lower():
        return marker
    return AlertMarker(marker.level, marker.shape, label)


def marker_for_alert(level: Any = "info", text: Any = None) -> AlertMarker:
    return alert_marker(level, text)


status_marker = alert_marker
alert_badge = alert_marker


def alert_markers() -> dict[str, AlertMarker]:
    """Return a copy of the marker table."""

    return dict(ALERT_MARKERS)


# ---------------------------------------------------------------------------
# Reduced motion
# ---------------------------------------------------------------------------
REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)"
PREFERS_REDUCED_MOTION = REDUCED_MOTION_QUERY

REDUCED_MOTION_CSS = """
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation: none !important;
    animation-duration: 0s !important;
    animation-iteration-count: 1 !important;
    transition: none !important;
    transition-duration: 0s !important;
    scroll-behavior: auto !important;
  }
}
""".strip()

MOTION_CSS = REDUCED_MOTION_CSS
REDUCED_MOTION = REDUCED_MOTION_CSS
REDUCED_MOTION_ENABLED = True
REDUCED_MOTION_STYLE = REDUCED_MOTION_CSS


def _motion_flag(default: bool, kwargs: dict[str, Any]) -> bool:
    value = default
    for key in ("prefers_reduced_motion", "reduced", "reduce", "enabled"):
        if key in kwargs:
            value = bool(kwargs.pop(key))
    if kwargs:
        names = ", ".join(sorted(kwargs))
        raise TypeError(f"unknown reduced-motion argument(s): {names}")
    return value


def reduced_motion_css(enabled: bool = True, **kwargs: Any) -> str:
    """Return CSS that disables non-essential motion when requested.

    ``enabled=False`` returns an empty stylesheet, which is convenient for
    renderers that conditionally include the media query.
    """

    enabled = _motion_flag(enabled, kwargs)
    return REDUCED_MOTION_CSS if enabled else ""


def motion_css(
    prefers_reduced_motion: bool = False,
    **kwargs: Any,
) -> str:
    return reduced_motion_css(prefers_reduced_motion, **kwargs)


def motion_style(prefers_reduced_motion: bool = False, **kwargs: Any) -> str:
    """Return an inline style for charts/tables under the motion preference."""

    if _motion_flag(prefers_reduced_motion, kwargs):
        return "transition: none; animation: none; scroll-behavior: auto;"
    return "transition: 180ms ease; animation-duration: 180ms;"


def animation_duration(prefers_reduced_motion: bool = False, **kwargs: Any) -> str:
    return "0s" if _motion_flag(prefers_reduced_motion, kwargs) else "180ms"


def transition_duration(prefers_reduced_motion: bool = False, **kwargs: Any) -> str:
    return "0s" if _motion_flag(prefers_reduced_motion, kwargs) else "180ms"


def motion_duration(prefers_reduced_motion: bool = False, **kwargs: Any) -> str:
    return animation_duration(prefers_reduced_motion, **kwargs)


def should_reduce_motion(prefers_reduced_motion: bool = False, **kwargs: Any) -> bool:
    return _motion_flag(prefers_reduced_motion, kwargs)


def motion_enabled(prefers_reduced_motion: bool = False, **kwargs: Any) -> bool:
    return not _motion_flag(prefers_reduced_motion, kwargs)


def prefers_reduced_motion(
    value: bool = True,
    **kwargs: Any,
) -> bool:
    """Return whether the reduced-motion preference is active."""

    return _motion_flag(value, kwargs)


def css_color_tokens() -> str:
    """Return the palette as CSS custom properties."""

    return "\n".join(
        f"  --tm-{name.replace('_', '-')}: {value};" for name, value in COLOR_TOKENS.items()
    )


def __getattr__(name: str) -> Any:
    """Expose forgiving aliases for the accessibility helpers."""

    lowered = name.strip().lower()
    if lowered.startswith("color_") or lowered.startswith("colour_"):
        token = lowered.split("_", 1)[1]
        if token in COLOR_TOKENS:
            return COLOR_TOKENS[token]
    if lowered.startswith("tm_"):
        token = lowered[len("tm_") :]
        if token in COLOR_TOKENS:
            return COLOR_TOKENS[token]
    for prefix in ("token_", "color_token_", "colour_token_"):
        if lowered.startswith(prefix):
            token = lowered[len(prefix) :]
            if token in COLOR_TOKENS:
                return COLOR_TOKENS[token]
    if lowered.endswith("_token"):
        token = lowered[: -len("_token")]
        if token in COLOR_TOKENS:
            return COLOR_TOKENS[token]
    if "contrast" in lowered and "report" not in lowered:
        return contrast_ratio
    if "luminance" in lowered:
        return relative_luminance
    if "chart" in lowered and ("alt" in lowered or "description" in lowered):
        return chart_alternative
    if "table" in lowered and ("alt" in lowered or "description" in lowered):
        return table_alternative
    if "alternative" in lowered:
        return alternative_text
    if "marker" in lowered:
        return alert_marker
    if "motion" in lowered:
        return reduced_motion_css
    if ("token" in lowered or "palette" in lowered) and "pair" not in lowered:
        return COLOR_TOKENS
    if name in {"chart_alternative_text", "chart_fallback_alt"}:
        return chart_alternative
    if name in {"table_alternative_text", "table_fallback_alt"}:
        return table_alternative
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ALERT_MARKERS",
    "ALERT_MARKER_SHAPES",
    "ALERT_MARKER_TEXT",
    "AlertMarker",
    "AlternativeText",
    "COLORS",
    "COLOR_TOKENS",
    "COLOR_TOKEN_NAMES",
    "COLOR_MAP",
    "COLOR_PAIRS",
    "COLOR_TOKEN_PAIRS",
    "CONTRAST_PAIRS",
    "ACCESSIBILITY_COLORS",
    "MIN_CONTRAST",
    "MIN_CONTRAST_RATIO",
    "MIN_TEXT_CONTRAST",
    "AA_CONTRAST",
    "WCAG_MIN_CONTRAST",
    "MOTION_CSS",
    "PALETTE",
    "PREFERS_REDUCED_MOTION",
    "REDUCED_MOTION",
    "REDUCED_MOTION_CSS",
    "REDUCED_MOTION_ENABLED",
    "REDUCED_MOTION_QUERY",
    "REDUCED_MOTION_STYLE",
    "TEXT_COLOR_PAIRS",
    "TEXT_CONTRAST_PAIRS",
    "TEXT_PAIRS",
    "TEXT_TOKEN_PAIRS",
    "THEME_COLORS",
    "TOKENS",
    "TOKEN_COLORS",
    "TOKEN_CONTRAST_PAIRS",
    "TOKEN_PAIRS",
    "WCAG_AA_LARGE_TEXT_CONTRAST",
    "WCAG_AA_TEXT_CONTRAST",
    "WCAG_AAA_TEXT_CONTRAST",
    "WCAG_TEXT_CONTRAST",
    "accessible_chart_alternative",
    "accessible_table_alternative",
    "accessible_alternative",
    "alert_badge",
    "alert_marker",
    "alert_markers",
    "alternative_text",
    "alt_text",
    "animation_duration",
    "chart_accessible_text",
    "chart_alt",
    "chart_alt_text",
    "chart_alternative",
    "chart_description",
    "chart_table_alternatives",
    "check_contrast",
    "check_text_contrast",
    "color_channels",
    "composite_color",
    "contrast",
    "contrast_ratio",
    "css_color_tokens",
    "marker_for_alert",
    "meets_wcag_contrast",
    "motion_css",
    "motion_duration",
    "motion_enabled",
    "motion_style",
    "passes_wcag",
    "prefers_reduced_motion",
    "relative_luminance",
    "reduced_motion_css",
    "should_reduce_motion",
    "status_marker",
    "table_accessible_text",
    "table_alt",
    "table_alt_text",
    "table_alternative",
    "table_description",
    "token_contrast_report",
    "transition_duration",
    "validate_accessibility",
    "validate_color_tokens",
    "validate_contrast",
    "validate_palette",
    "validate_wcag",
    "wcag_contrast_ratio",
]
