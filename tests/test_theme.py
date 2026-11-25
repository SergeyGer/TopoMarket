"""Visual tokens and WCAG AA contrast tests (UI04)."""

from __future__ import annotations

import pytest

from topomarket.ui.theme import (
    AMBER,
    CANVAS,
    DEFAULT_THEME,
    MIN_TEXT_CONTRAST,
    SERIES_COLORS,
    SERIES_LABELS,
    SERIES_MARKERS,
    TEAL,
    Theme,
    contrast_ratio,
    hex_to_rgb,
    relative_luminance,
    text_contrast_tokens,
    wcag_aa_failures,
)


def test_text_tokens_pass_wcag_aa_on_the_canvas() -> None:
    assert wcag_aa_failures() == []
    for name, ratio in text_contrast_tokens().items():
        if name == "border":
            continue
        assert ratio >= MIN_TEXT_CONTRAST, (name, ratio)


def test_muted_text_remains_readable() -> None:
    assert contrast_ratio(DEFAULT_THEME.muted, CANVAS) >= 4.5


def test_market_and_threshold_tokens_are_distinct_and_labelled() -> None:
    assert TEAL != AMBER
    assert SERIES_COLORS["sp500"] == TEAL
    assert SERIES_COLORS["threshold"] == AMBER
    for token in ("sp500", "vix", "score", "threshold", "alert"):
        assert token in SERIES_LABELS
        assert SERIES_LABELS[token]


def test_signals_are_distinguishable_without_colour() -> None:
    # Every signal that can appear on the timeline has a distinct marker symbol.
    symbols = {
        value
        for key, value in SERIES_MARKERS.items()
        if key in {"alert", "matched", "late", "false"}
    }
    assert len(symbols) >= 4


def test_contrast_helpers_are_correct() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0)
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert hex_to_rgb("#FF0000")[0] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        hex_to_rgb("not-a-colour")


def test_custom_theme_with_low_contrast_is_flagged() -> None:
    weak = Theme(ink="#BBBBBB", muted="#BBBBBB", teal="#BBBBBB", blue="#BBBBBB", amber="#BBBBBB")
    failures = wcag_aa_failures(weak)
    assert failures
