"""Frozen demonstration presets for the public Structure experience (UI01).

The specification requires four selectable scenes, each bound to a verified date
and a fixture ID:

* a quiet period;
* a stress transition (more industries begin moving together);
* a warning that the revised evaluator correctly matched to a breach episode;
* a missed or late warning.

The presets are derived deterministically from the committed synthetic showcase
when a frozen ``showcase/presets.json`` is absent, and read from the frozen file
once the demonstration is locked (build step 4).  Each record is verified against
the loaded session dates and the evaluation report; a preset that cannot be
verified is reported as unavailable with a reason instead of silently jumping to
an unrelated date.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from topomarket.analysis.network import (
    DEFAULT_CORRELATION_CUTOFF,
    DEFAULT_CORRELATION_WINDOW,
    PAIR_COUNT,
    build_correlation_network,
)

PRESET_ORDER: tuple[str, ...] = (
    "quiet",
    "stress_transition",
    "matched_warning",
    "missed_warning",
)

PRESET_LABELS: dict[str, str] = {
    "quiet": "Quiet period",
    "stress_transition": "Stress transition",
    "matched_warning": "Matched warning",
    "missed_warning": "Missed or late warning",
}

PRESET_DESCRIPTIONS: dict[str, str] = {
    "quiet": "Few industry pairs move together and the score is below the frozen threshold.",
    "stress_transition": "More industries begin moving together as the market turns.",
    "matched_warning": "A warning the revised evaluator correctly credited to a breach episode.",
    "missed_warning": "A decline the indicator missed or flagged only after the onset.",
}

#: Frozen preset dates freeze the demonstration once step 4 locks them.
FROZEN_PRESETS_FILENAME = "presets.json"


class PresetError(ValueError):
    """Raised for an invalid frozen preset file."""


@dataclass(frozen=True, slots=True)
class Preset:
    """One selectable demonstration scene."""

    preset_id: str
    label: str
    date: str | None
    mode: str = "replay"
    expected: tuple[str, ...] = ()
    description: str = ""
    fixture_id: str | None = None
    verified: bool = False
    reason: str | None = None
    teaching: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "label": self.label,
            "date": self.date,
            "mode": self.mode,
            "expected": list(self.expected),
            "description": self.description,
            "fixture_id": self.fixture_id,
            "verified": self.verified,
            "reason": self.reason,
            "teaching": self.teaching,
        }


def _showcase_root(data: Any) -> Path | None:
    """Return the committed showcase directory when the loaded data is its fixture."""

    snapshot = getattr(data, "snapshot_id", None)
    if snapshot != "showcase-synthetic":
        return None
    data_dir = Path(getattr(data, "data_dir", ""))
    for candidate in (data_dir, *data_dir.parents):
        if (candidate / FROZEN_PRESETS_FILENAME).is_file() and (
            candidate / "normalized" / "tda_daily.csv"
        ).is_file():
            return candidate
    return None


def load_frozen_presets(path: Path) -> list[Preset]:
    """Load and validate a frozen preset file."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:  # pragma: no cover - corrupt fixture
        raise PresetError(f"cannot read frozen presets: {error}") from error
    records = payload.get("presets")
    if not isinstance(records, list) or not records:
        raise PresetError("frozen presets must contain a non-empty 'presets' list")
    fixture_id = payload.get("fixture_id") or payload.get("snapshot_id")
    presets: list[Preset] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise PresetError("each frozen preset must be an object")
        preset_id = str(record.get("preset_id") or "")
        if not preset_id:
            raise PresetError("frozen preset is missing preset_id")
        presets.append(
            Preset(
                preset_id=preset_id,
                label=str(record.get("label") or PRESET_LABELS.get(preset_id, preset_id)),
                date=str(record["date"]) if record.get("date") else None,
                mode=str(record.get("mode") or "replay"),
                expected=tuple(str(value) for value in record.get("expected") or ()),
                description=str(record.get("description") or ""),
                fixture_id=str(fixture_id) if fixture_id else None,
                verified=bool(record.get("verified", True)),
                reason=record.get("reason"),
                teaching=bool(record.get("teaching", False)),
            )
        )
    return presets


def _quarter_candidates(data: Any, *, start: str = "2010-01-01", step: int = 63) -> list[str]:
    """Deterministic candidate sessions (one per quarter) for density analysis."""

    price_rows = getattr(data, "price_rows", ()) or data.rows
    dates = [str(row.get("date")) for row in price_rows if str(row.get("date")) >= start]
    return dates[::step]


def _network_density(data: Any, date: str) -> int | None:
    rows = getattr(data, "industry_rows", ()) or data.rows
    try:
        payload = build_correlation_network(
            rows,
            date,
            window=DEFAULT_CORRELATION_WINDOW,
            cutoff=DEFAULT_CORRELATION_CUTOFF,
        )
    except Exception:  # noqa: BLE001 - a preset candidate is allowed to be unavailable
        return None
    if not payload.get("available"):
        return None
    return int(payload["pairs_qualifying"])


def _evaluation_alerts(data: Any) -> list[dict[str, Any]]:
    reports = getattr(data, "evaluation_reports", ()) or ()
    if not reports:
        return []
    report = reports[0]
    methods = report.get("metrics") or {}
    primary = report.get("primary_method")
    method_payload = methods.get(primary) if primary in methods else None
    alerts: list[dict[str, Any]] = []
    if isinstance(method_payload, Mapping):
        matched = {
            str(entry.get("alert_date"))
            for entry in method_payload.get("matched") or ()
            if entry.get("alert_date")
        }
        post_onset = {str(value) for value in method_payload.get("post_onset_alerts") or ()}
        false_alerts = {str(value) for value in method_payload.get("false_alerts") or ()}
        for alert_date in method_payload.get("alerts") or ():
            text = str(alert_date)
            if text in matched:
                status = "matched"
            elif text in post_onset:
                status = "late"
            elif text in false_alerts:
                status = "false"
            else:
                status = "pending"
            alerts.append({"date": text, "status": status})
    return alerts


def _missed_onsets(data: Any) -> list[str]:
    reports = getattr(data, "evaluation_reports", ()) or ()
    if not reports:
        return []
    report = reports[0]
    methods = report.get("metrics") or {}
    primary = report.get("primary_method")
    method_payload = methods.get(primary) if primary in methods else None
    if not isinstance(method_payload, Mapping):
        return []
    examples = (report.get("examples") or {}).get(primary) or {}
    onsets: list[str] = []
    for entry in examples.get("missed") or ():
        onset = entry.get("episode_onset")
        if onset:
            onsets.append(str(onset))
    return onsets


def _latest(values: Sequence[str]) -> str | None:
    return max(values) if values else None


def derive_presets(data: Any) -> list[Preset]:
    """Derive the four presets deterministically from the loaded fixture."""

    session_dates = tuple(getattr(data, "session_dates", ()) or ())
    if not session_dates:
        return [
            Preset(
                preset_id=preset_id,
                label=PRESET_LABELS[preset_id],
                date=None,
                description=PRESET_DESCRIPTIONS[preset_id],
                verified=False,
                reason="no sessions loaded",
            )
            for preset_id in PRESET_ORDER
        ]
    fixture_id = getattr(data, "snapshot_id", None) or "synthetic-demo"
    candidates = _quarter_candidates(data)
    densities = {
        date: density
        for date in candidates
        if (density := _network_density(data, date)) is not None
    }
    quiet_date: str | None = None
    stress_date: str | None = None
    if densities:
        quiet_date = min(densities, key=lambda date: (densities[date], date))
        dense = [date for date, value in densities.items() if value >= int(PAIR_COUNT * 0.85)]
        if dense:
            stress_date = dense[0]
        else:
            stress_date = max(densities, key=lambda date: (densities[date], date))
        # Prefer the first date whose density jumps from a quiet run into the dense region.
        for date in sorted(densities):
            value = densities[date]
            if value < int(PAIR_COUNT * 0.85):
                continue
            previous = [densities[other] for other in sorted(densities) if other < date][-5:]
            if not previous or sum(previous) / len(previous) < int(PAIR_COUNT * 0.6):
                stress_date = date
                break
    alerts = _evaluation_alerts(data)
    matched = [alert["date"] for alert in alerts if alert["status"] == "matched"]
    late = [alert["date"] for alert in alerts if alert["status"] == "late"]
    missed = _missed_onsets(data)
    missed_date = _latest(missed)
    if missed_date is None:
        missed_date = _latest(late)
    matched_date = _latest(matched)
    teaching = False
    if matched_date is None and late:
        # The frozen synthetic showcase has no alert that the revised evaluator
        # credits; the storyboard fallback is a clearly labelled late-warning
        # teaching example that is not part of the evaluation.
        matched_date = _latest(late)
        teaching = True
    experiments = {
        "quiet": (quiet_date, ("score below threshold", "sparse correlation network")),
        "stress_transition": (
            stress_date,
            ("dense correlation network", "score near or above threshold"),
        ),
        "matched_warning": (
            matched_date,
            ("late alert", "decline already under way")
            if teaching
            else ("matched warning", "complete outcome"),
        ),
        "missed_warning": (missed_date, ("missed decline", "no early warning credited")),
    }
    presets: list[Preset] = []
    for preset_id in PRESET_ORDER:
        date, expected = experiments[preset_id]
        verified = bool(date and date in session_dates)
        is_teaching = teaching and preset_id == "matched_warning"
        presets.append(
            Preset(
                preset_id=preset_id,
                label=(
                    "Late warning (teaching example)" if is_teaching else PRESET_LABELS[preset_id]
                ),
                date=date if verified else None,
                mode="live" if preset_id == "quiet" else "replay",
                expected=expected if verified else (),
                description=(
                    "A late alert used as a labelled teaching example; it is not part of the "
                    "frozen evaluation."
                    if is_teaching
                    else PRESET_DESCRIPTIONS[preset_id]
                ),
                fixture_id=fixture_id,
                verified=verified,
                reason=None if verified else _preset_reason(preset_id, date),
                teaching=is_teaching,
            )
        )
    return presets


def _preset_reason(preset_id: str, date: str | None) -> str:
    if date is None:
        return f"no verified date is available for the {PRESET_LABELS[preset_id].lower()} preset"
    return f"derived date {date} is not in the loaded session calendar"


def build_presets(data: Any) -> dict[str, Any]:
    """Return the preset payload for the Structure screen."""

    cached = getattr(data, "_presets_cache", None)
    if cached is not None:
        return cached
    showcase_root = _showcase_root(data)
    source = "derived"
    presets: list[Preset] = []
    if showcase_root is not None and (showcase_root / FROZEN_PRESETS_FILENAME).is_file():
        frozen = load_frozen_presets(showcase_root / FROZEN_PRESETS_FILENAME)
        session_dates = set(getattr(data, "session_dates", ()) or ())
        presets = [
            replace(
                preset,
                verified=bool(preset.date and preset.date in session_dates),
            )
            for preset in frozen
        ]
        source = "frozen"
    if not presets:
        presets = derive_presets(data)
    payload = {
        "fixture_id": getattr(data, "snapshot_id", None) or "synthetic-demo",
        "source": source,
        "presets": [preset.as_dict() for preset in presets],
        "available": [preset.preset_id for preset in presets if preset.verified],
        "table_alternative": _preset_table(presets),
    }
    try:
        object.__setattr__(data, "_presets_cache", payload)
    except (AttributeError, TypeError):  # pragma: no cover - plain test doubles
        pass
    return payload


def _preset_table(presets: Sequence[Preset]) -> str:
    lines = ["Preset, Date, Fixture, Expected"]
    for preset in presets:
        lines.append(
            f"{preset.label}, {preset.date or 'unavailable'}, {preset.fixture_id or 'unknown'}, "
            f"{'; '.join(preset.expected) or preset.reason or 'n/a'}"
        )
    return "\n".join(lines)


def find_preset(data: Any, preset_id: str) -> Preset | None:
    payload = build_presets(data)
    for record in payload["presets"]:
        if record["preset_id"] == preset_id:
            return Preset(
                preset_id=record["preset_id"],
                label=record["label"],
                date=record["date"],
                mode=record["mode"],
                expected=tuple(record["expected"]),
                description=record["description"],
                fixture_id=record["fixture_id"],
                verified=record["verified"],
                reason=record["reason"],
                teaching=bool(record.get("teaching", False)),
            )
    return None


__all__ = [
    "FROZEN_PRESETS_FILENAME",
    "PRESET_LABELS",
    "PRESET_ORDER",
    "Preset",
    "PresetError",
    "build_presets",
    "derive_presets",
    "find_preset",
    "load_frozen_presets",
]
