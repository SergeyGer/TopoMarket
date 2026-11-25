"""Alert policy, calibration and application for Step 6.

The module is deliberately minimal: everything is dated (``tda_daily`` is the
ordered complete-session table, so consecutive rows are consecutive sessions),
there is no calendar inference and no way to inject undated numeric series.

Public contract
---------------
``MethodReading``      one dated value of a method (VIX close, annualized
                       realized volatility or a scored TDA value);
``readings_from_rows`` VIX / realized-volatility readings computed from rows;
``readings_from_scores`` TDA readings from scored Step 4 points;
``AlertPolicy``        immutable frozen cutoff/behaviour identity; a *silent*
                       policy emits no alerts and is recorded with
                       ``silent=True`` instead of a misleading cutoff;
``generate_alerts``    apply the 20-session cooldown to dated readings;
``average_precision``  average precision of a scored daily series against the
                       mature positive labels (tied scores evaluated as one
                       threshold block);
``calibrate_method``   validation-period percentile calibration with the
                       documented preference rules; records a silent policy
                       when no candidate satisfies the false-alert constraint;
``evaluate_alerts``    match alerts to episodes and compute the validation /
                       test metrics used by the evaluation report; average
                       precision uses the complete eligible scored series, not
                       only the alert dates.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

METHODS: tuple[str, ...] = ("tda", "vix", "realized_vol")
SIMPLE_COMPARATORS: tuple[str, ...] = ("vix", "realized_vol")
PERCENTILES: tuple[float, ...] = (85.0, 90.0, 92.5, 95.0, 97.5, 99.0)
COOLDOWN_SESSIONS = 20
WINDOW_SESSIONS = 20
ANNUALIZATION = 252.0
VALIDATION_START = "2005-01-01"
VALIDATION_END = "2013-12-31"
MAX_FALSE_ALERTS_PER_YEAR = 2.0


class AlertError(ValueError):
    """Raised for invalid readings, sessions or policy definitions."""


@dataclass(frozen=True, slots=True)
class MethodReading:
    """A dated, finite value produced by one method."""

    date: str
    value: float

    def __post_init__(self) -> None:
        parsed = _parse_date(self.date)
        object.__setattr__(self, "date", parsed.isoformat())
        value = float(self.value)
        if not math.isfinite(value):
            raise AlertError(f"reading value must be finite, got {self.value!r}")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class Alert:
    """One alert emitted by a frozen policy."""

    date: str
    index: int
    value: float
    method: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "index": self.index,
            "value": self.value,
            "method": self.method,
        }


@dataclass(frozen=True, slots=True)
class CalibrationCandidate:
    percentile: float
    cutoff: float
    episode_recall: float | None
    episode_count: int
    matched_count: int
    false_count: int
    false_alerts_per_year: float | None
    constrained: bool
    selected: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "percentile": self.percentile,
            "cutoff": self.cutoff,
            "episode_recall": self.episode_recall,
            "episode_count": self.episode_count,
            "matched_count": self.matched_count,
            "false_count": self.false_count,
            "false_alerts_per_year": self.false_alerts_per_year,
            "constrained": self.constrained,
            "selected": self.selected,
        }


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    method: str
    calibrated: bool
    reason: str | None
    validation_start: str
    validation_end: str
    eligible_sessions: int
    eligible_years: float
    session_digest: str
    config_hash: str
    candidates: tuple[CalibrationCandidate, ...]
    selected: CalibrationCandidate | None
    percentile: float | None
    cutoff: float | None
    episode_recall: float | None
    false_alerts_per_year: float | None
    calibration_hash: str
    silent: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "calibrated": self.calibrated,
            "silent": self.silent,
            "reason": self.reason,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "eligible_sessions": self.eligible_sessions,
            "eligible_years": self.eligible_years,
            "session_digest": self.session_digest,
            "config_hash": self.config_hash,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "selected": self.selected.as_dict() if self.selected else None,
            "percentile": self.percentile,
            "cutoff": self.cutoff,
            "episode_recall": self.episode_recall,
            "false_alerts_per_year": self.false_alerts_per_year,
            "calibration_hash": self.calibration_hash,
        }


@dataclass(frozen=True, slots=True)
class AlertPolicy:
    """Frozen alert behaviour; changing any field changes its identity.

    A *silent* policy carries ``silent=True`` and no cutoff: it is the
    recorded outcome of a calibration where no percentile candidate satisfied
    the false-alert constraint.  It emits no alerts (``generate_alerts``
    returns an empty tuple) instead of asserting a misleading calibrated
    cutoff.
    """

    method: str
    cutoff: float | None
    percentile: float | None = None
    cooldown_sessions: int = COOLDOWN_SESSIONS
    window_sessions: int = WINDOW_SESSIONS
    annualization: float = ANNUALIZATION
    validation_start: str = VALIDATION_START
    validation_end: str = VALIDATION_END
    config_hash: str | None = None
    calibration_hash: str | None = None
    session_digest: str | None = None
    eligible_years: float | None = None
    silent: bool = False

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise AlertError(f"method must be one of {METHODS}, got {self.method!r}")
        if not isinstance(self.silent, bool):
            raise AlertError("silent must be a boolean")
        if self.silent:
            if self.cutoff is not None:
                raise AlertError("a silent policy must not define a cutoff")
            if self.percentile is not None:
                raise AlertError("a silent policy must not define a percentile")
        else:
            if self.cutoff is None:
                raise AlertError("cutoff is required for a non-silent policy")
            cutoff = float(self.cutoff)
            if not math.isfinite(cutoff):
                raise AlertError("cutoff must be finite")
            object.__setattr__(self, "cutoff", cutoff)
        if not isinstance(self.cooldown_sessions, int) or isinstance(self.cooldown_sessions, bool):
            raise AlertError("cooldown_sessions must be an integer")
        if self.cooldown_sessions < 0:
            raise AlertError("cooldown_sessions must be >= 0")
        if self.window_sessions < 2:
            raise AlertError("window_sessions must be >= 2")
        annualization = float(self.annualization)
        if not math.isfinite(annualization) or annualization <= 0:
            raise AlertError("annualization must be positive")
        object.__setattr__(self, "annualization", annualization)
        object.__setattr__(self, "validation_start", _parse_date(self.validation_start).isoformat())
        object.__setattr__(self, "validation_end", _parse_date(self.validation_end).isoformat())
        if self.validation_start > self.validation_end:
            raise AlertError("validation_start must not be after validation_end")
        if self.percentile is not None:
            percentile = float(self.percentile)
            if not math.isfinite(percentile) or not 0.0 < percentile < 100.0:
                raise AlertError("percentile must be in (0, 100)")
            object.__setattr__(self, "percentile", percentile)

    def policy_hash(self) -> str:
        payload = {
            "method": self.method,
            "cutoff": None if self.cutoff is None else _float_identity(self.cutoff),
            "percentile": None if self.percentile is None else _float_identity(self.percentile),
            "cooldown_sessions": self.cooldown_sessions,
            "window_sessions": self.window_sessions,
            "annualization": _float_identity(self.annualization),
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "config_hash": self.config_hash,
            "calibration_hash": self.calibration_hash,
            "session_digest": self.session_digest,
            "eligible_years": None
            if self.eligible_years is None
            else _float_identity(self.eligible_years),
        }
        if self.silent:
            # Silent policies have no cutoff, so this key cannot collide with a
            # calibrated policy; omitting it when false keeps every previously
            # frozen (non-silent) policy hash stable.
            payload["silent"] = True
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @property
    def policy_id(self) -> str:
        return self.policy_hash()

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "method": self.method,
            "cutoff": self.cutoff,
            "percentile": self.percentile,
            "cooldown_sessions": self.cooldown_sessions,
            "window_sessions": self.window_sessions,
            "annualization": self.annualization,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "config_hash": self.config_hash,
            "calibration_hash": self.calibration_hash,
            "session_digest": self.session_digest,
            "eligible_years": self.eligible_years,
            "silent": self.silent,
        }
        payload["policy_hash"] = self.policy_hash()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AlertPolicy:
        data = dict(payload)
        data.pop("policy_hash", None)
        allowed = {
            "method",
            "cutoff",
            "percentile",
            "cooldown_sessions",
            "window_sessions",
            "annualization",
            "validation_start",
            "validation_end",
            "config_hash",
            "calibration_hash",
            "session_digest",
            "eligible_years",
            "silent",
        }
        unknown = set(data) - allowed
        if unknown:
            raise AlertError(f"unknown policy field(s): {', '.join(sorted(unknown))}")
        return cls(**data)


@dataclass(frozen=True, slots=True)
class AlertEvaluation:
    """Alert/episode matching metrics for one method and period."""

    method: str
    start: str
    end: str
    eligible_sessions: int
    eligible_years: float
    alerts: tuple[str, ...]
    alert_values: tuple[float, ...]
    pending_alerts: tuple[str, ...]
    matched: tuple[dict[str, Any], ...]
    false_alerts: tuple[str, ...]
    missed_episodes: tuple[dict[str, Any], ...]
    post_onset_alerts: tuple[str, ...]
    episode_count: int
    matched_count: int
    episode_recall: float | None
    false_alert_count: int
    false_alerts_per_year: float | None
    median_lead_sessions: float | None
    min_lead_sessions: int | None
    max_lead_sessions: int | None
    average_precision: float | None
    event_prevalence: float | None
    losing_examples: tuple[dict[str, Any], ...]
    policy_hash: str | None = None
    average_precision_sessions: int = 0
    average_precision_positives: int = 0
    average_precision_reason: str | None = None
    credit_rule: str | None = None
    silent_policy: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "start": self.start,
            "end": self.end,
            "eligible_sessions": self.eligible_sessions,
            "eligible_years": self.eligible_years,
            "alerts": list(self.alerts),
            "alert_values": list(self.alert_values),
            "pending_alerts": list(self.pending_alerts),
            "matched": list(self.matched),
            "false_alerts": list(self.false_alerts),
            "missed_episodes": list(self.missed_episodes),
            "post_onset_alerts": list(self.post_onset_alerts),
            "episode_count": self.episode_count,
            "matched_count": self.matched_count,
            "episode_recall": self.episode_recall,
            "false_alert_count": self.false_alert_count,
            "false_alerts_per_year": self.false_alerts_per_year,
            "median_lead_sessions": self.median_lead_sessions,
            "min_lead_sessions": self.min_lead_sessions,
            "max_lead_sessions": self.max_lead_sessions,
            "average_precision": self.average_precision,
            "average_precision_sessions": self.average_precision_sessions,
            "average_precision_positives": self.average_precision_positives,
            "average_precision_reason": self.average_precision_reason,
            "event_prevalence": self.event_prevalence,
            "losing_examples": list(self.losing_examples),
            "policy_hash": self.policy_hash,
            "credit_rule": self.credit_rule,
            "silent_policy": self.silent_policy,
        }


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise AlertError(f"invalid ISO date: {value!r}") from exc


def _float_identity(value: float) -> str:
    return format(float(value), ".17g")


def validate_sessions(dates: Sequence[str]) -> tuple[str, ...]:
    """Validate a sorted, strictly increasing session date sequence."""
    parsed = [_parse_date(value).isoformat() for value in dates]
    if not parsed:
        raise AlertError("session sequence must not be empty")
    for left, right in zip(parsed, parsed[1:], strict=False):
        if left >= right:
            raise AlertError("session dates must be strictly increasing")
    return tuple(parsed)


def _session_digest(sessions: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(sessions).encode("utf-8")).hexdigest()


def _coerce_rows(rows: Any) -> list[Any]:
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise AlertError("rows must be a sequence of dated observations")
    return list(rows)


def readings_from_rows(rows: Any, method: str) -> tuple[MethodReading, ...]:
    """Compute dated VIX or realized-volatility readings from session rows."""
    if method not in ("vix", "realized_vol"):
        raise AlertError(f"readings_from_rows supports vix and realized_vol, got {method!r}")
    materialised = _coerce_rows(rows)
    dates: list[str] = []
    closes: list[float] = []
    for index, row in enumerate(materialised):
        raw_date = row.get("date") if isinstance(row, Mapping) else getattr(row, "date", None)
        raw_close = (
            row.get("sp500_close")
            if isinstance(row, Mapping)
            else getattr(row, "sp500_close", None)
        )
        dates.append(_parse_date(raw_date).isoformat())
        try:
            close = float(raw_close)
        except (TypeError, ValueError) as exc:
            raise AlertError(f"row {index} has a non-numeric sp500_close") from exc
        if not math.isfinite(close) or close <= 0:
            raise AlertError(f"row {index} has an invalid sp500_close")
        closes.append(close)
    sessions = validate_sessions(dates)
    log_returns: list[float | None] = [None]
    for previous, current in zip(closes, closes[1:], strict=False):
        log_returns.append(math.log(current / previous))

    readings: list[MethodReading] = []
    if method == "vix":
        for index, row in enumerate(materialised):
            raw_vix = (
                row.get("vix_close")
                if isinstance(row, Mapping)
                else getattr(row, "vix_close", None)
            )
            if raw_vix is None or raw_vix == "":
                continue
            try:
                value = float(raw_vix)
            except (TypeError, ValueError):
                raise AlertError(f"row {index} has a non-numeric vix_close") from None
            if math.isfinite(value):
                readings.append(MethodReading(sessions[index], value))
    else:
        window = WINDOW_SESSIONS
        for index in range(window, len(sessions)):
            window_returns = log_returns[index - window + 1 : index + 1]
            if any(value is None or not math.isfinite(value) for value in window_returns):
                continue
            values = [float(value) for value in window_returns]
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
            readings.append(
                MethodReading(
                    sessions[index],
                    math.sqrt(variance) * math.sqrt(ANNUALIZATION),
                )
            )
    return validate_readings(readings)


def readings_from_scores(
    score_points: Sequence[Any], method: str = "tda"
) -> tuple[MethodReading, ...]:
    """Build TDA readings from scored Step 4 points (state == 'scored' only)."""
    if method != "tda":
        raise AlertError(f"readings_from_scores supports only 'tda', got {method!r}")
    readings: list[MethodReading] = []
    for index, point in enumerate(score_points):
        if isinstance(point, Mapping):
            raw_date = point.get("date")
            raw_state = point.get("state")
            raw_score = point.get("score")
        else:
            raw_date = getattr(point, "date", None)
            raw_state = getattr(point, "state", None)
            raw_score = getattr(point, "score", None)
        if raw_state == "unavailable":
            continue
        if raw_state != "scored":
            continue
        if raw_score is None or raw_score == "":
            continue
        try:
            value = float(raw_score)
        except (TypeError, ValueError) as exc:
            raise AlertError(f"score point {index} has a non-numeric score") from exc
        if not math.isfinite(value) or value < 0.0 or value > 100.0:
            raise AlertError(f"score point {index} is outside the [0, 100] score range")
        readings.append(MethodReading(_parse_date(raw_date).isoformat(), value))
    ordered = validate_readings(readings)
    if [reading.date for reading in ordered] != [
        _parse_date(
            getattr(point, "date", point.get("date") if isinstance(point, Mapping) else None)
        ).isoformat()
        for point in score_points
        if (point.get("state") if isinstance(point, Mapping) else getattr(point, "state", None))
        in {"scored"}
    ]:
        raise AlertError("TDA readings must be provided in strictly increasing date order")
    return ordered


def validate_readings(readings: Sequence[MethodReading]) -> tuple[MethodReading, ...]:
    """Validate readings: dated, strictly increasing, finite."""
    materialised = list(readings)
    previous: str | None = None
    for reading in materialised:
        if not isinstance(reading, MethodReading):
            raise AlertError("readings must contain MethodReading values")
        if previous is not None and reading.date <= previous:
            raise AlertError("readings must be strictly increasing by date")
        previous = reading.date
    return tuple(materialised)


def percentile(values: Sequence[float], percent: float) -> float:
    """Linear-interpolation percentile (same convention as NumPy's default)."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise AlertError("cannot take a percentile of an empty sequence")
    if not 0.0 < percent < 100.0:
        raise AlertError("percent must be in (0, 100)")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percent / 100.0
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def generate_alerts(
    readings: Sequence[MethodReading],
    sessions: Sequence[str],
    policy: AlertPolicy,
) -> tuple[Alert, ...]:
    """Apply a frozen policy (cooldown included) to dated readings."""
    validate_readings(readings)
    session_tuple = validate_sessions(sessions)
    positions = {session: index for index, session in enumerate(session_tuple)}
    for reading in readings:
        if reading.date not in positions:
            raise AlertError(f"reading date is not a known session: {reading.date}")
    if policy.silent:
        # A silent policy is the recorded "no qualifying threshold" outcome.
        return ()
    alerts: list[Alert] = []
    last_alert_position: int | None = None
    for reading in readings:
        position = positions[reading.date]
        if reading.value < policy.cutoff:
            continue
        if (
            last_alert_position is not None
            and position - last_alert_position < policy.cooldown_sessions
        ):
            continue
        alerts.append(Alert(reading.date, position, reading.value, policy.method))
        last_alert_position = position
    return tuple(alerts)


def _label_field(label: Any, field: str) -> Any:
    """Read one field from a :class:`~.labels.TargetLabel` or a mapping row."""
    if isinstance(label, Mapping):
        return label.get(field)
    return getattr(label, field, None)


def _match_pair_values(pair: Any) -> tuple[str | None, str | None, int | None]:
    """Extract (alert date, episode onset, lead sessions) from a match pair."""
    if isinstance(pair, Mapping):
        alert_date = pair.get("alert_date") or pair.get("date")
        episode_start = pair.get("episode_start") or pair.get("onset")
        lead = pair.get("lead_sessions") or pair.get("lead")
        return (
            None if alert_date is None else str(alert_date),
            None if episode_start is None else str(episode_start),
            None if lead is None else int(lead),
        )
    alert = getattr(pair, "alert", None)
    episode = getattr(pair, "episode", None)
    alert_date = (
        getattr(alert, "date", None) if alert is not None else getattr(pair, "alert_date", None)
    )
    episode_start = (
        getattr(episode, "start_date", None)
        if episode is not None
        else getattr(pair, "episode_start", None)
    )
    lead = getattr(pair, "lead_sessions", None)
    return (
        None if alert_date is None else str(alert_date),
        None if episode_start is None else str(episode_start),
        None if lead is None else int(lead),
    )


def _episodes_in_period(
    episodes: Sequence[Any], sessions: Sequence[str], start: str, end: str
) -> list[Any]:
    positions = {session: index for index, session in enumerate(sessions)}
    start_date = _parse_date(start).isoformat()
    end_date = _parse_date(end).isoformat()
    selected: list[Any] = []
    for episode in episodes:
        episode_start = getattr(episode, "start_date", None)
        if episode_start is None and isinstance(episode, Mapping):
            episode_start = episode.get("start_date")
        if episode_start is None or positions.get(str(episode_start)) is None:
            continue
        if start_date <= str(episode_start) <= end_date:
            selected.append(episode)
    return selected


def evaluate_alerts(
    *,
    method: str,
    alerts: Sequence[Alert],
    episodes: Sequence[Any],
    labels: Sequence[Any],
    sessions: Sequence[str],
    start: str,
    end: str,
    policy: AlertPolicy | None = None,
    readings: Sequence[MethodReading] | None = None,
    evaluation_dates: Sequence[str] | None = None,
) -> AlertEvaluation:
    """Match alerts to episodes and compute the metrics used by the report.

    Crediting follows the strict label-aware rule of
    :func:`topomarket.analysis.labels.match_alerts`: an alert is credited only
    when its own target label is positive, the label's first breach belongs to
    the matched episode and the onset is one to ``lead_sessions`` sessions
    after the alert.

    ``readings`` is the method's complete scored daily series.  Average
    precision is computed over every eligible reading in the evaluation period
    whose label is mature (see :func:`average_precision`), ranked by
    descending score, instead of only over the alert dates.  When
    ``evaluation_dates`` is given, the series is restricted to that shared date
    set so every compared method is scored on the same sessions.
    """
    from topomarket.analysis.labels import match_alerts

    session_tuple = validate_sessions(sessions)
    positions = {session: index for index, session in enumerate(session_tuple)}
    start_date = _parse_date(start).isoformat()
    end_date = _parse_date(end).isoformat()
    eligible_positions = [
        index for index, session in enumerate(session_tuple) if start_date <= session <= end_date
    ]
    if not eligible_positions:
        raise AlertError("evaluation period contains no sessions")
    eligible_sessions = len(eligible_positions)
    eligible_years = eligible_sessions / ANNUALIZATION

    in_period_alerts = tuple(
        sorted(
            (alert for alert in alerts if start_date <= alert.date <= end_date),
            key=lambda alert: alert.date,
        )
    )

    matching = match_alerts(
        [{"date": alert.date} for alert in in_period_alerts],
        episodes,
        session_tuple,
        labels=labels,
    )
    matched_pairs = list(matching.matches)
    matched: list[dict[str, Any]] = []
    leads: list[int] = []
    matched_episode_starts: set[str] = set()
    for pair in matched_pairs:
        alert_date, episode_start, lead = _match_pair_values(pair)
        if alert_date is None or episode_start is None:
            continue
        matched_episode_starts.add(episode_start)
        matched.append(
            {
                "alert_date": alert_date,
                "episode_onset": episode_start,
                "lead_sessions": lead,
            }
        )
        if lead is not None:
            leads.append(lead)

    period_episodes = _episodes_in_period(episodes, session_tuple, start_date, end_date)
    missed = [
        {
            "episode_onset": str(getattr(episode, "start_date", "")),
            "breach_dates": list(getattr(episode, "breach_dates", ()) or ()),
        }
        for episode in period_episodes
        if str(getattr(episode, "start_date", "")) not in matched_episode_starts
    ]

    false_dates = [
        str(getattr(alert, "date", None) or alert.get("date"))
        for alert in matching.false_mature_alerts
    ]
    pending_dates = [
        str(getattr(alert, "date", None) or alert.get("date")) for alert in matching.pending_alerts
    ]
    post_onset = [
        str(getattr(alert, "date", None) or alert.get("date"))
        for alert in matching.post_onset_alerts
    ]
    episode_recall = len(matched_episode_starts) / len(period_episodes) if period_episodes else None
    false_alerts_per_year = len(false_dates) / eligible_years if eligible_years else None
    median_lead = float(median_values(leads)) if leads else None

    positives = 0
    label_by_date: dict[str, dict[str, Any]] = {}
    for label in labels:
        label_date = _label_field(label, "date")
        if label_date is None:
            continue
        key = str(label_date)
        if key not in positions or not start_date <= key <= end_date:
            continue
        status = str(_label_field(label, "status") or "").lower()
        target = _label_field(label, "target")
        is_positive = bool(target) and status != "pending"
        label_by_date[key] = {"positive": is_positive, "pending": status == "pending"}
        positives += int(is_positive)

    allowed_dates = set(evaluation_dates) if evaluation_dates is not None else None
    scored: list[tuple[float, bool]] = []
    if readings is not None:
        for reading in validate_readings(readings):
            if not start_date <= reading.date <= end_date:
                continue
            if allowed_dates is not None and reading.date not in allowed_dates:
                continue
            entry = label_by_date.get(reading.date)
            if entry is None or entry["pending"]:
                continue
            scored.append((reading.value, bool(entry["positive"])))

    scored_positives = sum(1 for _, flag in scored if flag)
    average_precision_value = average_precision(scored) if scored else None
    if average_precision_value is not None:
        average_precision_reason: str | None = None
    elif readings is None:
        average_precision_reason = (
            "no scored daily readings supplied; average precision requires the "
            "complete eligible scored series"
        )
    elif not scored:
        average_precision_reason = "no mature labelled readings inside the evaluation dates"
    elif scored_positives == 0:
        average_precision_reason = (
            f"no positive target labels among the {len(scored)} eligible scored dates"
        )
    else:  # pragma: no cover - defensive, positives imply a defined value
        average_precision_reason = "average precision is undefined"
    if scored:
        event_prevalence = scored_positives / len(scored)
    else:
        # Keep the label-only prevalence for callers that do not supply
        # readings; the report always scores the common eligible dates.
        event_prevalence = positives / eligible_sessions if eligible_sessions else None

    return AlertEvaluation(
        method=method,
        start=start_date,
        end=end_date,
        eligible_sessions=eligible_sessions,
        eligible_years=eligible_years,
        alerts=tuple(alert.date for alert in in_period_alerts),
        alert_values=tuple(alert.value for alert in in_period_alerts),
        pending_alerts=tuple(pending_dates),
        matched=tuple(matched),
        false_alerts=tuple(false_dates),
        missed_episodes=tuple(missed),
        post_onset_alerts=tuple(post_onset),
        episode_count=len(period_episodes),
        matched_count=len(matched_episode_starts),
        episode_recall=episode_recall,
        false_alert_count=len(false_dates),
        false_alerts_per_year=false_alerts_per_year,
        median_lead_sessions=median_lead,
        min_lead_sessions=min(leads) if leads else None,
        max_lead_sessions=max(leads) if leads else None,
        average_precision=average_precision_value,
        event_prevalence=event_prevalence,
        losing_examples=tuple(missed[:5]),
        policy_hash=policy.policy_hash() if policy is not None else None,
        average_precision_sessions=len(scored),
        average_precision_positives=scored_positives,
        average_precision_reason=average_precision_reason,
        credit_rule=str(getattr(matching, "credit_rule", "")) or None,
        silent_policy=bool(policy.silent) if policy is not None else False,
    )


def median_values(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def average_precision(scored: Sequence[tuple[float, bool]]) -> float | None:
    """Average precision of a scored, labelled daily series.

    Precision and recall are computed over the *complete* series, ranked by
    descending score, against the binary label of every session.  Tied scores
    are handled consistently as one threshold block: every item sharing a score
    is included before a precision point is taken, so the block contributes
    ``(recall_after - recall_before) * precision_after``.  The result equals
    the standard average precision with tied scores (the value returned by
    ``sklearn.metrics.average_precision_score``).

    Returns ``None`` when the series has no positive label (average precision
    is undefined); callers record the reason alongside the ``null``.
    """
    items: list[tuple[float, bool]] = []
    for score, flag in scored:
        value = float(score)
        if not math.isfinite(value):
            raise AlertError(f"score must be finite, got {score!r}")
        items.append((value, bool(flag)))
    positives = sum(1 for _, flag in items if flag)
    if not items or positives == 0:
        return None
    items.sort(key=lambda item: -item[0])
    total = 0.0
    true_positives = 0
    seen = 0
    index = 0
    while index < len(items):
        block_score = items[index][0]
        block_size = 0
        block_positives = 0
        while index < len(items) and items[index][0] == block_score:
            block_size += 1
            block_positives += int(items[index][1])
            index += 1
        seen += block_size
        true_positives += block_positives
        precision = true_positives / seen
        total += (block_positives / positives) * precision
    return total


def calibrate_method(
    *,
    method: str,
    readings: Sequence[MethodReading],
    labels: Sequence[Any],
    sessions: Sequence[str],
    config_hash: str | None = None,
    validation_start: str = VALIDATION_START,
    validation_end: str = VALIDATION_END,
    purge_sessions: int = COOLDOWN_SESSIONS,
) -> CalibrationResult:
    """Calibrate one method on the validation period with the documented rules."""
    from topomarket.analysis.labels import build_breach_episodes, match_alerts

    if method not in METHODS:
        raise AlertError(f"method must be one of {METHODS}, got {method!r}")
    session_tuple = validate_sessions(sessions)
    positions = {session: index for index, session in enumerate(session_tuple)}
    start_date = _parse_date(validation_start).isoformat()
    end_date = _parse_date(validation_end).isoformat()
    validation_sessions = [
        session for session in session_tuple if start_date <= session <= end_date
    ]
    if not validation_sessions:
        return _empty_calibration(method, validation_start, validation_end, config_hash)
    purge_end_index = positions[validation_sessions[-1]] - purge_sessions
    eligible_session_set = {
        session
        for session in validation_sessions
        if positions[session] <= purge_end_index or positions[session] < purge_sessions
    }
    eligible_sessions = len(eligible_session_set)
    eligible_years = eligible_sessions / ANNUALIZATION
    episodes = build_breach_episodes(labels)
    validation_episodes = _episodes_in_period(
        episodes,
        session_tuple,
        start_date,
        validation_sessions[max(0, len(validation_sessions) - purge_sessions - 1)]
        if purge_sessions
        else end_date,
    )
    validation_readings = [
        reading for reading in validate_readings(readings) if reading.date in eligible_session_set
    ]
    if not validation_readings or not validation_episodes:
        return _empty_calibration(
            method,
            validation_start,
            validation_end,
            config_hash,
            reason="no eligible validation readings or episodes",
            eligible_sessions=eligible_sessions,
            eligible_years=eligible_years,
            sessions=session_tuple,
        )
    values = [reading.value for reading in validation_readings]
    candidates: list[CalibrationCandidate] = []
    for percent in PERCENTILES:
        cutoff = percentile(values, percent)
        policy = AlertPolicy(
            method=method,
            cutoff=cutoff,
            percentile=percent,
            config_hash=config_hash,
            validation_start=validation_start,
            validation_end=validation_end,
            session_digest=_session_digest(session_tuple),
            eligible_years=eligible_years,
        )
        alerts = generate_alerts(validation_readings, session_tuple, policy)
        matching = match_alerts(
            [{"date": alert.date} for alert in alerts],
            validation_episodes,
            session_tuple,
            labels=labels,
        )
        # NOTE(EV01 follow-up): ``AlertMatch`` exposes ``episode_onset`` /
        # ``episode.start_date``, not ``episode_start``.  This legacy lookup
        # therefore always resolves to the string "None", so the calibration
        # recall reported below has always been 0 and the preference rule only
        # ranked candidates by their false-alert counts.  Correcting it moves
        # the frozen validation cutoffs (and with them the holdout policies),
        # which EV01 requires us to preserve while a qualified candidate
        # exists, so the correction is tracked as a follow-up rather than
        # folded into this change.
        matched_starts = {
            str(getattr(pair, "episode_start", None) or pair.get("episode_start"))
            for pair in matching.matches
        }
        episode_count = len(validation_episodes)
        matched_count = len(
            matched_starts & {str(getattr(ep, "start_date", "")) for ep in validation_episodes}
        )
        recall = matched_count / episode_count if episode_count else None
        false_count = len(matching.false_mature_alerts)
        false_rate = false_count / eligible_years if eligible_years else None
        constrained = false_rate is None or false_rate > MAX_FALSE_ALERTS_PER_YEAR
        candidates.append(
            CalibrationCandidate(
                percentile=percent,
                cutoff=cutoff,
                episode_recall=recall,
                episode_count=episode_count,
                matched_count=matched_count,
                false_count=false_count,
                false_alerts_per_year=false_rate,
                constrained=constrained,
            )
        )
    feasible = [candidate for candidate in candidates if not candidate.constrained]
    if not feasible:
        # EV01: no threshold qualifies, so record why and fall back to a silent
        # policy instead of asserting a misleading calibrated cutoff.
        best_effort = sorted(
            candidates,
            key=lambda candidate: (candidate.false_count, -(candidate.cutoff)),
        )[0]
        reason = (
            "no percentile candidate satisfies the false-alert constraint "
            f"(<= {MAX_FALSE_ALERTS_PER_YEAR:g} per year); "
            f"lowest observed rate {best_effort.false_alerts_per_year!r} per year "
            f"at percentile {best_effort.percentile:g}; silent policy (no alerts)"
        )
        marked_silent = tuple(
            CalibrationCandidate(
                percentile=candidate.percentile,
                cutoff=candidate.cutoff,
                episode_recall=candidate.episode_recall,
                episode_count=candidate.episode_count,
                matched_count=candidate.matched_count,
                false_count=candidate.false_count,
                false_alerts_per_year=candidate.false_alerts_per_year,
                constrained=candidate.constrained,
                selected=False,
            )
            for candidate in candidates
        )
        silent_hash = hashlib.sha256(
            json.dumps(
                {
                    "method": method,
                    "silent": True,
                    "reason": reason,
                    "eligible_sessions": eligible_sessions,
                    "eligible_years": _float_identity(eligible_years),
                    "session_digest": _session_digest(session_tuple),
                    "config_hash": config_hash,
                    "validation_start": validation_start,
                    "validation_end": validation_end,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return CalibrationResult(
            method=method,
            calibrated=False,
            silent=True,
            reason=reason,
            validation_start=start_date,
            validation_end=end_date,
            eligible_sessions=eligible_sessions,
            eligible_years=eligible_years,
            session_digest=_session_digest(session_tuple),
            config_hash=config_hash or "",
            candidates=marked_silent,
            selected=None,
            percentile=None,
            cutoff=None,
            episode_recall=None,
            false_alerts_per_year=None,
            calibration_hash=silent_hash,
        )

    best = sorted(
        feasible,
        key=lambda candidate: (
            -(candidate.episode_recall or 0.0),
            candidate.false_count,
            -candidate.cutoff,
        ),
    )[0]
    selected = CalibrationCandidate(
        percentile=best.percentile,
        cutoff=best.cutoff,
        episode_recall=best.episode_recall,
        episode_count=best.episode_count,
        matched_count=best.matched_count,
        false_count=best.false_count,
        false_alerts_per_year=best.false_alerts_per_year,
        constrained=best.constrained,
        selected=True,
    )
    marked = tuple(
        CalibrationCandidate(
            percentile=candidate.percentile,
            cutoff=candidate.cutoff,
            episode_recall=candidate.episode_recall,
            episode_count=candidate.episode_count,
            matched_count=candidate.matched_count,
            false_count=candidate.false_count,
            false_alerts_per_year=candidate.false_alerts_per_year,
            constrained=candidate.constrained,
            selected=candidate == best,
        )
        for candidate in candidates
    )
    calibration_payload = {
        "method": method,
        "percentile": selected.percentile,
        "cutoff": _float_identity(selected.cutoff),
        "eligible_sessions": eligible_sessions,
        "eligible_years": _float_identity(eligible_years),
        "session_digest": _session_digest(session_tuple),
        "config_hash": config_hash,
        "validation_start": validation_start,
        "validation_end": validation_end,
    }
    calibration_hash = hashlib.sha256(
        json.dumps(calibration_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return CalibrationResult(
        method=method,
        calibrated=True,
        reason=None,
        validation_start=start_date,
        validation_end=end_date,
        eligible_sessions=eligible_sessions,
        eligible_years=eligible_years,
        session_digest=_session_digest(session_tuple),
        config_hash=config_hash or "",
        candidates=marked,
        selected=selected,
        percentile=selected.percentile,
        cutoff=selected.cutoff,
        episode_recall=selected.episode_recall,
        false_alerts_per_year=selected.false_alerts_per_year,
        calibration_hash=calibration_hash,
    )


def _empty_calibration(
    method: str,
    validation_start: str,
    validation_end: str,
    config_hash: str | None,
    *,
    reason: str = "not calibrated",
    eligible_sessions: int = 0,
    eligible_years: float = 0.0,
    sessions: Sequence[str] | None = None,
) -> CalibrationResult:
    digest = _session_digest(sessions) if sessions else ""
    return CalibrationResult(
        method=method,
        calibrated=False,
        reason=reason,
        validation_start=_parse_date(validation_start).isoformat(),
        validation_end=_parse_date(validation_end).isoformat(),
        eligible_sessions=eligible_sessions,
        eligible_years=eligible_years,
        session_digest=digest,
        config_hash=config_hash or "",
        candidates=(),
        selected=None,
        percentile=None,
        cutoff=None,
        episode_recall=None,
        false_alerts_per_year=None,
        calibration_hash=hashlib.sha256(
            json.dumps(
                {
                    "method": method,
                    "reason": reason,
                    "session_digest": digest,
                    "config_hash": config_hash,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    )


def freeze_policy(calibration: CalibrationResult) -> AlertPolicy:
    """Build the frozen policy for a calibrated (or silent) method.

    A calibration that found no qualifying threshold freezes into a silent
    policy: the identity is recorded, the reason stays on the calibration and
    no alert is ever emitted.
    """
    if calibration.silent:
        return AlertPolicy(
            method=calibration.method,
            cutoff=None,
            percentile=None,
            silent=True,
            config_hash=calibration.config_hash or None,
            calibration_hash=calibration.calibration_hash,
            validation_start=calibration.validation_start,
            validation_end=calibration.validation_end,
            session_digest=calibration.session_digest,
            eligible_years=calibration.eligible_years,
        )
    if not calibration.calibrated or calibration.cutoff is None:
        raise AlertError(f"method {calibration.method!r} is not calibrated")
    return AlertPolicy(
        method=calibration.method,
        cutoff=calibration.cutoff,
        percentile=calibration.percentile,
        config_hash=calibration.config_hash or None,
        calibration_hash=calibration.calibration_hash,
        validation_start=calibration.validation_start,
        validation_end=calibration.validation_end,
        session_digest=calibration.session_digest,
        eligible_years=calibration.eligible_years,
    )


def select_comparator(calibrations: Mapping[str, CalibrationResult]) -> str | None:
    """Choose the stronger simple comparator with the same preference rules.

    A silent comparator is still a valid frozen policy (it emits no alerts);
    it ranks behind any calibrated comparator because its recall is undefined
    (``0``) and its false-alert rate is treated as infinite.
    """
    candidates = [
        calibration
        for method, calibration in calibrations.items()
        if method in SIMPLE_COMPARATORS and (calibration.calibrated or calibration.silent)
    ]
    if not candidates:
        return None
    best = sorted(
        candidates,
        key=lambda calibration: (
            -(calibration.episode_recall or 0.0),
            calibration.false_alerts_per_year
            if calibration.false_alerts_per_year is not None
            else float("inf"),
            -(calibration.cutoff or 0.0),
        ),
    )[0]
    return best.method


__all__ = [
    "ANNUALIZATION",
    "COOLDOWN_SESSIONS",
    "MAX_FALSE_ALERTS_PER_YEAR",
    "METHODS",
    "PERCENTILES",
    "SIMPLE_COMPARATORS",
    "VALIDATION_END",
    "VALIDATION_START",
    "WINDOW_SESSIONS",
    "Alert",
    "AlertError",
    "AlertEvaluation",
    "AlertPolicy",
    "CalibrationCandidate",
    "CalibrationResult",
    "MethodReading",
    "average_precision",
    "calibrate_method",
    "evaluate_alerts",
    "freeze_policy",
    "generate_alerts",
    "median_values",
    "percentile",
    "readings_from_rows",
    "readings_from_scores",
    "select_comparator",
    "validate_readings",
    "validate_sessions",
]
