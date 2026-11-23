"""Focused tests for the Step 7 accessibility helpers."""

from __future__ import annotations

import pytest

from topomarket.ui.accessibility import (
    ALERT_MARKERS,
    COLOR_TOKENS,
    REDUCED_MOTION_CSS,
    REDUCED_MOTION_QUERY,
    TEXT_TOKEN_PAIRS,
    alert_marker,
    animation_duration,
    chart_alternative,
    check_text_contrast,
    composite_color,
    contrast_ratio,
    motion_enabled,
    motion_style,
    relative_luminance,
    table_alternative,
    token_contrast_report,
    validate_accessibility,
    validate_color_tokens,
)


def test_relative_luminance_and_contrast_extremes() -> None:
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0)
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert contrast_ratio("white", "white") == pytest.approx(1.0)


def test_short_hex_rgb_and_token_colours_are_supported() -> None:
    assert contrast_ratio("#000", "#fff") == pytest.approx(21.0)
    assert contrast_ratio("rgb(0, 0, 0)", "rgb(255, 255, 255)") == pytest.approx(21.0)
    assert contrast_ratio("text", "background") == contrast_ratio(
        COLOR_TOKENS["text"], COLOR_TOKENS["background"]
    )


def test_every_text_token_pair_meets_wcag_aa() -> None:
    ratios = check_text_contrast()

    assert set(ratios) == set(TEXT_TOKEN_PAIRS)
    for foreground, background in TEXT_TOKEN_PAIRS:
        assert COLOR_TOKENS[foreground]
        assert COLOR_TOKENS[background]
        assert ratios[(foreground, background)] >= 4.5


def test_contrast_report_reports_passes_and_tokens() -> None:
    report = token_contrast_report()

    assert report["passed"] is True
    assert report["minimum"] == 4.5
    assert report["pairs"]
    assert all(pair["passed"] for pair in report["pairs"])
    for token in ("background", "surface", "text", "muted", "accent", "warning", "danger"):
        assert token in COLOR_TOKENS


def test_validate_color_tokens_and_accessibility_checks() -> None:
    assert validate_color_tokens() is True
    report = validate_accessibility()
    assert report["contrast"] is True
    assert report["reduced_motion"] is True
    assert report["chart_alternative"]
    assert report["table_alternative"]


def test_chart_alternatives_are_nonempty_and_descriptive() -> None:
    alternative = chart_alternative(
        "H1 persistence",
        description="Persistence score over the trailing 60 sessions.",
        data=[1, 2, 3],
    )

    assert str(alternative).strip()
    assert "H1 persistence" in alternative
    assert alternative.alt == str(alternative)
    assert alternative.text == str(alternative)
    assert chart_alternative("").strip()
    assert chart_alternative("Empty", data=[]).strip()


def test_table_alternatives_are_nonempty_and_descriptive() -> None:
    alternative = table_alternative(
        "Industry returns",
        columns=["NoDur", "Durbl"],
        rows=[1, 2, 3],
    )

    assert str(alternative).strip()
    assert "Industry returns" in alternative
    assert "3 row(s)" in alternative
    assert alternative.alt == str(alternative)
    assert table_alternative("").strip()


def test_alert_markers_use_shape_plus_text() -> None:
    warning = alert_marker("warning")
    critical = alert_marker("critical")
    info = alert_marker("info")

    assert warning.shape
    assert warning.text
    assert warning.shape in str(warning)
    assert warning.text in str(warning)
    assert warning["shape"] == warning.shape
    assert warning["text"] == warning.text
    assert len({warning.shape, critical.shape, info.shape}) == 3
    assert "warning" in ALERT_MARKERS
    custom = alert_marker("danger", "Market breach")
    assert custom.shape == "◆"
    assert "Market breach" in custom


def test_alert_markers_reject_unknown_levels() -> None:
    with pytest.raises(ValueError, match="Unknown alert level"):
        alert_marker("plasma")


def test_reduced_motion_css_and_helpers() -> None:
    css = REDUCED_MOTION_CSS

    assert REDUCED_MOTION_QUERY in css
    assert "animation: none" in css
    assert "transition: none" in css
    assert "scroll-behavior: auto" in css
    assert motion_style(True) == "transition: none; animation: none; scroll-behavior: auto;"
    assert "transition: 180ms" in motion_style(False)
    assert animation_duration(True) == "0s"
    assert animation_duration(False) == "180ms"
    assert motion_enabled(False) is True
    assert motion_enabled(True) is False


def test_translucent_colours_are_composited_before_contrast_is_measured() -> None:
    assert contrast_ratio("rgba(0, 0, 0, 0.5)", "#FFFFFF") == pytest.approx(3.95, abs=0.05)
    assert contrast_ratio("rgba(0, 0, 0, 0)", "#FFFFFF") == pytest.approx(1.0)
    assert contrast_ratio("rgba(0, 0, 0, 0.5)", "#FFFFFF") < contrast_ratio("#000000", "#FFFFFF")


def test_composite_colour_and_luminance_require_opacity() -> None:
    assert composite_color("rgba(0, 0, 0, 0.5)", "#FFFFFF") == "#808080"
    with pytest.raises(ValueError, match="opaque"):
        relative_luminance("rgba(0, 0, 0, 0.5)")
    with pytest.raises(ValueError, match="alpha"):
        contrast_ratio("rgba(0, 0, 0, 1.5)", "#FFFFFF")
