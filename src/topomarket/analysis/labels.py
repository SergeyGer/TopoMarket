"""Chronological target labels, breach episodes and early-alert matching (Step 6).

This module implements the evaluation target fixed in the project README: a
fall of at least ten percent from the selected close within the next twenty
index sessions.  It deliberately works on the *rows supplied by the caller*.
Consecutive rows are consecutive sessions; no exchange calendar is inferred
and no future value is used before it is available.

The public surface is small:

``build_target_labels(rows)``
    Return one :class:`TargetLabel` per input row.  A label is ``1`` when the
    inclusive threshold is reached during the next ``horizon_sessions`` rows,
    ``0`` when the full horizon is observed without a breach, and ``None``
    while the horizon is still pending.

``build_breach_episodes(labels)``
    Group distinct first-breach sessions into episodes.  Breaches separated by
    at most ``gap_sessions`` rows chain together; a larger gap starts a new
    episode.  Each episode records the positive label origins whose first
    breach belongs to it.

``match_alerts(alerts, episodes, labels=...)``
    Match early alerts to future episodes chronologically and one-to-one.
    Duplicate, post-onset, false mature, missed and still-pending events are
    reported separately.  When the target labels are supplied, a strict credit
    rule applies: an alert is credited only when its *own* label is positive
    (a close at or below 90% of the alert close within 20 sessions), the
    label's first breach belongs to the matched episode and the episode onset
    is one to ``lead_sessions`` sessions after the alert.  Without labels the
    matcher falls back to the historical onset-window rule
    (``credit_rule="onset_window"``).

All results are frozen, ordered and JSON-serialisable through ``as_dict``.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

#: Inclusive drawdown threshold for the fixed Step 6 target.
DEFAULT_THRESHOLD = 0.10
THRESHOLD = DEFAULT_THRESHOLD
TARGET_THRESHOLD = DEFAULT_THRESHOLD
DRAWDOWN_THRESHOLD = DEFAULT_THRESHOLD
TARGET_DRAWDOWN = DEFAULT_THRESHOLD

#: Number of sessions in the fixed target horizon.
DEFAULT_HORIZON_SESSIONS = 20
HORIZON_SESSIONS = DEFAULT_HORIZON_SESSIONS
TARGET_HORIZON = DEFAULT_HORIZON_SESSIONS
TARGET_HORIZON_SESSIONS = DEFAULT_HORIZON_SESSIONS

#: Maximum gap between first-breach sessions in one episode.
DEFAULT_EPISODE_GAP_SESSIONS = 20
EPISODE_GAP_SESSIONS = DEFAULT_EPISODE_GAP_SESSIONS
DEFAULT_GAP_SESSIONS = DEFAULT_EPISODE_GAP_SESSIONS
BREACH_GAP_SESSIONS = DEFAULT_EPISODE_GAP_SESSIONS

#: Maximum alert lead before an episode onset.
DEFAULT_ALERT_LEAD_SESSIONS = 20
ALERT_LEAD_SESSIONS = DEFAULT_ALERT_LEAD_SESSIONS
DEFAULT_LEAD_SESSIONS = DEFAULT_ALERT_LEAD_SESSIONS
EARLY_ALERT_LEAD_SESSIONS = DEFAULT_ALERT_LEAD_SESSIONS

STATUS_POSITIVE = "positive"
STATUS_NEGATIVE = "negative"
STATUS_PENDING = "pending"

MATCHED = "matched"
FALSE_MATURE = "false_mature"
POST_ONSET = "post_onset"
DUPLICATE = "duplicate"
UNMATCHED_PENDING = "pending"

#: Credit rule identifiers recorded on :class:`AlertMatchResult`.
CREDIT_RULE_LABEL_BREACH = "label_positive_and_breach_owned"
CREDIT_RULE_ONSET_WINDOW = "onset_window"


class LabelStatus:
    """String constants for target-label states."""

    POSITIVE = STATUS_POSITIVE
    NEGATIVE = STATUS_NEGATIVE
    PENDING = STATUS_PENDING


class AlertStatus:
    """String constants for alert outcomes."""

    MATCHED = MATCHED
    FALSE_MATURE = FALSE_MATURE
    POST_ONSET = POST_ONSET
    DUPLICATE = DUPLICATE
    PENDING = UNMATCHED_PENDING


class LabelError(ValueError):
    """Raised for invalid label rows or date ordering."""


# Friendly aliases used by callers/tests.
TargetLabelError = LabelError
LabelBuildError = LabelError
LabelSeriesError = LabelError
DateOrderError = LabelError


class EpisodeError(LabelError):
    """Raised when breach episodes cannot be built."""


BreachEpisodeError = EpisodeError
EpisodeBuildError = EpisodeError


class AlertMatchError(LabelError):
    """Raised when alerts cannot be aligned with the supplied sessions."""


AlertError = AlertMatchError
MatchError = AlertMatchError
EarlyAlertError = AlertMatchError


class LabelConfig:
    """Small immutable configuration shared by the three public helpers.

    Explicit keyword arguments win over configuration values.  The class is
    deliberately permissive about aliases so callers can use either the short
    ``horizon``/``gap``/``lead`` names or the descriptive ones.
    """

    __slots__ = ("threshold", "horizon_sessions", "gap_sessions", "lead_sessions")

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        horizon_sessions: int = DEFAULT_HORIZON_SESSIONS,
        gap_sessions: int = DEFAULT_EPISODE_GAP_SESSIONS,
        lead_sessions: int = DEFAULT_ALERT_LEAD_SESSIONS,
        **aliases: Any,
    ) -> None:
        if "horizon" in aliases:
            horizon_sessions = aliases.pop("horizon")
        if "gap" in aliases:
            gap_sessions = aliases.pop("gap")
        if "lead" in aliases:
            lead_sessions = aliases.pop("lead")
        if "max_lead" in aliases:
            lead_sessions = aliases.pop("max_lead")
        if "drawdown_threshold" in aliases:
            threshold = aliases.pop("drawdown_threshold")
        if aliases:
            unknown = ", ".join(sorted(aliases))
            raise LabelError(f"unknown label configuration field(s): {unknown}")
        self.threshold = _coerce_threshold(threshold)
        self.horizon_sessions = _coerce_positive_int(horizon_sessions, "horizon_sessions")
        self.gap_sessions = _coerce_positive_int(gap_sessions, "gap_sessions")
        self.lead_sessions = _coerce_positive_int(lead_sessions, "lead_sessions")

    @property
    def horizon(self) -> int:
        return self.horizon_sessions

    @property
    def gap(self) -> int:
        return self.gap_sessions

    @property
    def lead(self) -> int:
        return self.lead_sessions

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "horizon_sessions": self.horizon_sessions,
            "gap_sessions": self.gap_sessions,
            "lead_sessions": self.lead_sessions,
        }

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LabelConfig):
            return self.as_dict() == other.as_dict()
        if isinstance(other, Mapping):
            return self.as_dict() == dict(other)
        return NotImplemented

    def __repr__(self) -> str:
        return (
            "LabelConfig("
            f"threshold={self.threshold!r}, "
            f"horizon_sessions={self.horizon_sessions!r}, "
            f"gap_sessions={self.gap_sessions!r}, "
            f"lead_sessions={self.lead_sessions!r})"
        )


_DATE_FIELDS = (
    "date",
    "as_of",
    "asof",
    "session",
    "session_date",
    "observation_date",
    "observation",
    "as_of_date",
    "alert_date",
    "signal_date",
    "timestamp",
)
_CLOSE_FIELDS = (
    "sp500_close",
    "close",
    "adj_close",
    "closing_price",
    "value",
    "price",
    "sp500",
    "level",
    "index_close",
)
_INDEX_FIELDS = (
    "index",
    "row_index",
    "session_index",
    "alert_index",
    "position",
    "row",
    "idx",
)
_BREACH_FIELDS = (
    "breach_index",
    "first_breach_index",
    "onset_index",
    "breach",
    "breach_position",
)
_EPISODE_START_FIELDS = (
    "start_index",
    "onset_index",
    "first_index",
    "first_breach_index",
    "start",
)
_EPISODE_END_FIELDS = (
    "end_index",
    "last_index",
    "last_breach_index",
    "end",
)
_EPISODE_BREACH_INDEX_FIELDS = (
    "breach_indices",
    "indices",
    "breaches",
    "breach_positions",
)
_EPISODE_BREACH_DATE_FIELDS = (
    "breach_dates",
    "dates",
    "first_breach_dates",
)


def _coerce_positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise LabelError(f"{name} must be an integer >= 1, got {value!r}")
    result = int(value)
    if result < 1:
        raise LabelError(f"{name} must be an integer >= 1, got {value!r}")
    return result


def _coerce_non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise LabelError(f"{name} must be an integer >= 0, got {value!r}")
    result = int(value)
    if result < 0:
        raise LabelError(f"{name} must be an integer >= 0, got {value!r}")
    return result


def _coerce_threshold(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise LabelError(f"threshold must be a finite number > 0, got {value!r}")
    threshold = float(value)
    if not math.isfinite(threshold) or threshold <= 0.0:
        raise LabelError(f"threshold must be a finite number > 0, got {value!r}")
    if threshold > 1.0:
        # Be forgiving when a caller passes the percentage rather than its
        # decimal fraction (10 means 10%).
        threshold /= 100.0
    if threshold <= 0.0 or threshold > 1.0:
        raise LabelError(f"threshold must be between 0 and 1, got {value!r}")
    return threshold


def _coerce_close(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise LabelError(f"{name} must be a positive finite number, got {value!r}")
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError as error:
            raise LabelError(f"{name} must be a positive finite number, got {value!r}") from error
    if not isinstance(value, numbers.Real):
        raise LabelError(f"{name} must be a positive finite number, got {value!r}")
    close = float(value)
    if not math.isfinite(close) or close <= 0.0:
        raise LabelError(f"{name} must be a positive finite number, got {value!r}")
    return close


def _coerce_date(value: Any, name: str = "date") -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(text).date()
            except ValueError as error:
                raise LabelError(f"{name} must be an ISO-8601 date, got {value!r}") from error
        return parsed.isoformat()
    raise LabelError(f"{name} must be an ISO-8601 date, got {value!r}")


def _materialise_sequence(values: Any, name: str) -> list[Any]:
    if values is None:
        return []
    if isinstance(values, (str, bytes, bytearray)):
        raise LabelError(f"{name} must be a sequence, not text")
    if isinstance(values, Mapping):
        return [values]
    try:
        return list(values)
    except TypeError as error:
        raise LabelError(f"{name} must be a sequence, got {type(values).__name__}") from error


def validate_dates(dates: Any) -> tuple[str, ...]:
    """Return canonical ISO dates, rejecting duplicates and out-of-order rows."""

    rows = _materialise_sequence(dates, "dates")
    parsed = tuple(_coerce_date(value, f"dates[{index}]") for index, value in enumerate(rows))
    seen: dict[str, int] = {}
    for index, value in enumerate(parsed):
        if value in seen:
            raise LabelError(
                f"duplicate observation date {value!r} at rows {seen[value]} and {index}"
            )
        if index and value <= parsed[index - 1]:
            raise LabelError(
                "dates must be strictly increasing ISO-8601 rows: "
                f"{parsed[index - 1]!r} then {value!r}"
            )
        seen[value] = index
    return parsed


# Common spellings used by callers.
check_dates = validate_dates
normalise_dates = validate_dates
normalize_dates = validate_dates
ordered_dates = validate_dates
validate_sessions = validate_dates
validate_iso_dates = validate_dates
ensure_dates = validate_dates
ensure_ordered_dates = validate_dates
normalise_sessions = validate_dates
normalize_sessions = validate_dates


def _row_get(row: Any, fields: Sequence[str]) -> Any:
    if isinstance(row, Mapping):
        for field_name in fields:
            if field_name in row:
                return row[field_name]
        return None
    for field_name in fields:
        if hasattr(row, field_name):
            return getattr(row, field_name)
    if hasattr(row, "_asdict"):
        try:
            mapping = row._asdict()
        except (AttributeError, TypeError):
            mapping = {}
        for field_name in fields:
            if field_name in mapping:
                return mapping[field_name]
    return None


def _looks_like_date(value: Any) -> bool:
    return isinstance(value, (date, datetime)) or isinstance(value, str)


def _is_vector(value: Any) -> bool:
    if isinstance(value, (str, bytes, bytearray, date, datetime, Mapping)):
        return False
    try:
        iter(value)
    except TypeError:
        return False
    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _price_rows(
    data: Any = None,
    closes: Any = None,
    *,
    dates: Any = None,
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """Coerce the supported row/column forms into ordered dates and closes."""

    if data is None:
        if dates is None or closes is None:
            raise LabelError("both dates and closes are required")
        date_rows = _materialise_sequence(dates, "dates")
        close_rows = _materialise_sequence(closes, "closes")
        return _paired_rows(date_rows, close_rows)

    if isinstance(data, Mapping):
        date_key = next((key for key in _DATE_FIELDS if key in data), None)
        close_key = next((key for key in _CLOSE_FIELDS if key in data), None)
        if date_key is not None and close_key is not None:
            date_values = data[date_key]
            close_values = data[close_key]
            if _is_vector(date_values) or _is_vector(close_values):
                return _paired_rows(
                    _materialise_sequence(date_values, "dates"),
                    _materialise_sequence(close_values, "closes"),
                )
            return _paired_rows([date_values], [close_values])
        if "rows" in data and len(data) == 1:
            return _price_rows(data["rows"], closes, dates=dates)
        items = list(data.items())
        if (
            items
            and all(_looks_like_date(key) for key, _ in items)
            and all(_is_number(value) for _, value in items)
        ):
            return _paired_rows([key for key, _ in items], [value for _, value in items])
        raise LabelError("price rows must contain a date and a close")

    rows = _materialise_sequence(data, "rows")

    if closes is not None:
        # Two positional sequences: the first holds dates and the second closes.
        if rows and not all(_looks_like_date(value) for value in rows):
            raise LabelError("when closes are supplied the first sequence must contain dates")
        close_rows = _materialise_sequence(closes, "closes")
        return _paired_rows(rows, close_rows)

    if dates is not None:
        # The first positional sequence is a close/value series.
        return _paired_rows(
            _materialise_sequence(dates, "dates"),
            rows,
        )

    if not rows:
        return (), ()

    if all(
        _row_get(row, _DATE_FIELDS) is not None and _row_get(row, _CLOSE_FIELDS) is not None
        for row in rows
    ):
        return _paired_rows(
            [_row_get(row, _DATE_FIELDS) for row in rows],
            [_row_get(row, _CLOSE_FIELDS) for row in rows],
        )

    if all(isinstance(row, (tuple, list)) and len(row) >= 2 for row in rows):
        pair_dates: list[Any] = []
        pair_closes: list[Any] = []
        for row in rows:
            date_position = next(
                (position for position, value in enumerate(row) if _looks_like_date(value)),
                None,
            )
            if date_position is None:
                raise LabelError("row tuples must contain one ISO date and one numeric close")
            date_value = row[date_position]
            after = [value for value in row[date_position + 1 :] if _is_number(value)]
            before = [value for value in row[:date_position] if _is_number(value)]
            positive_after = [value for value in after if float(value) > 0.0]
            positive_before = [value for value in before if float(value) > 0.0]
            if positive_after:
                close_value = positive_after[0]
            elif after:
                close_value = after[0]
            elif positive_before:
                close_value = positive_before[-1]
            elif before:
                close_value = before[-1]
            else:
                raise LabelError("row tuples must contain one ISO date and one numeric close")
            pair_dates.append(date_value)
            pair_closes.append(close_value)
        return _paired_rows(pair_dates, pair_closes)

    raise LabelError("rows must expose a date and a close (or pass dates= and closes= explicitly)")


def _paired_rows(
    dates: Sequence[Any], closes: Sequence[Any]
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    ordered = validate_dates(dates)
    if len(ordered) != len(closes):
        raise LabelError(
            f"dates and closes must have equal length, got {len(ordered)} and {len(closes)}"
        )
    values = tuple(_coerce_close(value, f"closes[{index}]") for index, value in enumerate(closes))
    return ordered, values


def _resolve_alias(
    kwargs: dict[str, Any],
    names: Sequence[str],
    value: Any,
    *,
    default: Any = None,
    name: str = "parameter",
) -> Any:
    found = [(alias, kwargs.pop(alias)) for alias in names if alias in kwargs]
    if len(found) > 1:
        joined = ", ".join(alias for alias, _ in found)
        raise LabelError(f"{name} was provided more than once via {joined}")
    if found and value is not None:
        raise LabelError(f"{name} was provided more than once")
    chosen = found[0][1] if found else value
    return default if chosen is None else chosen


def _config_values(config: Any) -> dict[str, Any]:
    if config is None:
        return {}
    if isinstance(config, LabelConfig):
        return config.as_dict()
    if isinstance(config, Mapping):
        return dict(config)
    result: dict[str, Any] = {}
    for attribute in (
        "threshold",
        "horizon_sessions",
        "horizon",
        "gap_sessions",
        "gap",
        "lead_sessions",
        "lead",
    ):
        if hasattr(config, attribute):
            result[attribute] = getattr(config, attribute)
    if result:
        return result
    raise LabelError("config must be a LabelConfig, mapping or configuration object")


def _configured(
    config: Any,
    *,
    threshold: Any = None,
    horizon_sessions: Any = None,
    gap_sessions: Any = None,
    lead_sessions: Any = None,
) -> dict[str, Any]:
    values = _config_values(config)
    if threshold is None:
        threshold = values.get("threshold", values.get("drawdown_threshold"))
    if horizon_sessions is None:
        horizon_sessions = values.get(
            "horizon_sessions", values.get("horizon", values.get("sessions"))
        )
    if gap_sessions is None:
        gap_sessions = values.get("gap_sessions", values.get("gap"))
    if lead_sessions is None:
        lead_sessions = values.get("lead_sessions", values.get("lead", values.get("max_lead")))
    return {
        "threshold": _coerce_threshold(DEFAULT_THRESHOLD if threshold is None else threshold),
        "horizon_sessions": _coerce_positive_int(
            DEFAULT_HORIZON_SESSIONS if horizon_sessions is None else horizon_sessions,
            "horizon_sessions",
        ),
        "gap_sessions": _coerce_positive_int(
            DEFAULT_EPISODE_GAP_SESSIONS if gap_sessions is None else gap_sessions,
            "gap_sessions",
        ),
        "lead_sessions": _coerce_positive_int(
            DEFAULT_ALERT_LEAD_SESSIONS if lead_sessions is None else lead_sessions,
            "lead_sessions",
        ),
    }


DEFAULT_CONFIG = LabelConfig()
DEFAULT_LABEL_CONFIG = DEFAULT_CONFIG


@dataclass(frozen=True, slots=True)
class TargetLabel:
    """One row-position target label and its first breach, if any."""

    index: int
    date: str
    close: float
    target: int | None
    status: str
    breach_index: int | None = None
    breach_date: str | None = None
    horizon_end_index: int | None = None
    horizon_end_date: str | None = None
    min_drawdown: float | None = None
    future_return: float | None = None

    @property
    def label(self) -> int | None:
        return self.target

    @property
    def y(self) -> int | None:
        return self.target

    @property
    def outcome(self) -> int | None:
        return self.target

    @property
    def pending(self) -> bool:
        return self.status == STATUS_PENDING

    @property
    def is_pending(self) -> bool:
        return self.pending

    @property
    def positive(self) -> bool:
        return self.target == 1

    @property
    def is_positive(self) -> bool:
        return self.positive

    @property
    def negative(self) -> bool:
        return self.target == 0

    @property
    def is_negative(self) -> bool:
        return self.negative

    @property
    def first_breach_index(self) -> int | None:
        return self.breach_index

    @property
    def first_breach_date(self) -> str | None:
        return self.breach_date

    @property
    def onset_index(self) -> int | None:
        return self.breach_index

    @property
    def onset_date(self) -> str | None:
        return self.breach_date

    @property
    def breach(self) -> int | None:
        return self.breach_index

    @property
    def first_breach(self) -> int | None:
        return self.breach_index

    @property
    def horizon_end(self) -> int | None:
        return self.horizon_end_index

    @property
    def window_end_index(self) -> int | None:
        return self.horizon_end_index

    @property
    def matured(self) -> bool:
        return not self.pending

    @property
    def is_mature(self) -> bool:
        return self.matured

    @property
    def sessions_to_breach(self) -> int | None:
        if self.breach_index is None:
            return None
        return self.breach_index - self.index

    @property
    def breach_sessions(self) -> int | None:
        return self.sessions_to_breach

    @property
    def horizon_return(self) -> float | None:
        return self.future_return

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "date": self.date,
            "close": self.close,
            "target": self.target,
            "label": self.target,
            "status": self.status,
            "pending": self.pending,
            "breach_index": self.breach_index,
            "breach_date": self.breach_date,
            "first_breach_index": self.breach_index,
            "first_breach_date": self.breach_date,
            "sessions_to_breach": self.sessions_to_breach,
            "horizon_end_index": self.horizon_end_index,
            "horizon_end_date": self.horizon_end_date,
            "min_drawdown": self.min_drawdown,
            "future_return": self.future_return,
        }

    def _value(self, key: str) -> Any:
        aliases = {
            "label": self.target,
            "y": self.target,
            "outcome": self.target,
            "position": self.index,
            "row": self.index,
            "row_index": self.index,
            "session_index": self.index,
            "value": self.close,
            "price": self.close,
            "breach": self.breach_index,
            "first_breach": self.breach_index,
            "first_breach_index": self.breach_index,
            "breach_date": self.breach_date,
            "first_breach_date": self.breach_date,
            "onset_index": self.breach_index,
            "onset_date": self.breach_date,
            "sessions_to_breach": self.sessions_to_breach,
            "horizon_return": self.future_return,
            "is_positive": self.positive,
            "is_negative": self.negative,
            "is_pending": self.pending,
        }
        if key in aliases:
            return aliases[key]
        if key in self.as_dict():
            return self.as_dict()[key]
        raise KeyError(key)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            return self._value(key)
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def keys(self) -> tuple[str, ...]:
        return tuple(self.as_dict())

    def values(self) -> tuple[Any, ...]:
        return tuple(self.as_dict().values())

    def items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.as_dict().items())

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self.as_dict()

    def __iter__(self):
        return iter(self.as_dict())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TargetLabel):
            return self.as_dict() == other.as_dict()
        if isinstance(other, Mapping):
            return all(self.get(str(key)) == value for key, value in other.items())
        if other is None:
            return self.target is None
        if isinstance(other, bool):
            return self.target == int(other)
        if isinstance(other, numbers.Integral):
            return self.target == int(other)
        if isinstance(other, str):
            lowered = other.strip().lower()
            if lowered in {STATUS_POSITIVE, STATUS_NEGATIVE, STATUS_PENDING}:
                return self.status == lowered
            if lowered in {"1", "0", "none", "null"}:
                expected = None if lowered in {"none", "null"} else int(lowered)
                return self.target == expected
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return NotImplemented
        return not result


def _target_label_series(values: Any) -> LabelSeries:
    labels = _materialise_sequence(values, "labels")
    result: list[TargetLabel] = []
    for item in labels:
        if isinstance(item, TargetLabel):
            result.append(item)
        elif isinstance(item, Mapping) or hasattr(item, "target"):
            result.append(_coerce_label(item, len(result)))
        else:
            raise LabelError(f"labels[{len(result)}] is not a target label")
    return LabelSeries(result)


def _coerce_label(item: Any, position: int) -> TargetLabel:
    index = _row_get(item, _INDEX_FIELDS)
    if index is None:
        index = position
    index = _coerce_non_negative_int(index, f"labels[{position}].index")
    date_value = _row_get(item, _DATE_FIELDS)
    if date_value is None:
        raise LabelError(f"labels[{position}] is missing a date")
    close = _row_get(item, _CLOSE_FIELDS)
    target = _row_get(item, ("target", "label", "y", "outcome"))
    if target is not None and isinstance(target, str):
        lowered = target.lower()
        if lowered in {"1", "positive", "true"}:
            target = 1
        elif lowered in {"0", "negative", "false"}:
            target = 0
        elif lowered in {"pending", "none", "null"}:
            target = None
    status = _row_get(item, ("status", "state"))
    if status is None:
        status = (
            STATUS_PENDING
            if target is None
            else (STATUS_POSITIVE if target == 1 else STATUS_NEGATIVE)
        )
    breach_index = _row_get(item, _BREACH_FIELDS)
    breach_date = _row_get(item, ("breach_date", "first_breach_date", "onset_date"))
    horizon_end_index = _row_get(item, ("horizon_end_index", "horizon_index", "window_end_index"))
    horizon_end_date = _row_get(item, ("horizon_end_date", "window_end_date"))
    min_drawdown = _row_get(item, ("min_drawdown", "drawdown", "worst_drawdown"))
    future_return = _row_get(item, ("future_return", "horizon_return", "return"))
    return TargetLabel(
        index=int(index),
        date=_coerce_date(date_value, f"labels[{position}].date"),
        close=_coerce_close(close, f"labels[{position}].close"),
        target=None if target is None else int(target),
        status=str(status),
        breach_index=None if breach_index is None else int(breach_index),
        breach_date=None if breach_date is None else _coerce_date(breach_date),
        horizon_end_index=None if horizon_end_index is None else int(horizon_end_index),
        horizon_end_date=None if horizon_end_date is None else _coerce_date(horizon_end_date),
        min_drawdown=None if min_drawdown is None else float(min_drawdown),
        future_return=None if future_return is None else float(future_return),
    )


class LabelSeries(list):
    """Ordered target labels with convenient attribute/column access."""

    def __init__(self, labels: Iterable[TargetLabel] = ()) -> None:
        super().__init__(labels)

    @property
    def labels(self) -> tuple[TargetLabel, ...]:
        return tuple(self)

    @property
    def rows(self) -> tuple[TargetLabel, ...]:
        return tuple(self)

    @property
    def dates(self) -> tuple[str, ...]:
        return tuple(label.date for label in self)

    @property
    def closes(self) -> tuple[float, ...]:
        return tuple(label.close for label in self)

    @property
    def targets(self) -> tuple[int | None, ...]:
        return tuple(label.target for label in self)

    @property
    def values(self) -> tuple[int | None, ...]:
        return self.targets

    @property
    def statuses(self) -> tuple[str, ...]:
        return tuple(label.status for label in self)

    @property
    def positive(self) -> tuple[TargetLabel, ...]:
        return tuple(label for label in self if label.positive)

    @property
    def negative(self) -> tuple[TargetLabel, ...]:
        return tuple(label for label in self if label.negative)

    @property
    def pending(self) -> tuple[TargetLabel, ...]:
        return tuple(label for label in self if label.pending)

    @property
    def positive_count(self) -> int:
        return sum(1 for label in self if label.positive)

    @property
    def negative_count(self) -> int:
        return sum(1 for label in self if label.negative)

    @property
    def pending_count(self) -> int:
        return sum(1 for label in self if label.pending)

    @property
    def n_positive(self) -> int:
        return self.positive_count

    @property
    def n_negative(self) -> int:
        return self.negative_count

    @property
    def n_pending(self) -> int:
        return self.pending_count

    def to_dicts(self) -> list[dict[str, Any]]:
        return [label.as_dict() for label in self]

    def as_dict(self) -> dict[str, Any]:
        return {
            "labels": self.to_dicts(),
            "dates": list(self.dates),
            "targets": list(self.targets),
            "statuses": list(self.statuses),
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "pending_count": self.pending_count,
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            aliases = {
                "label": self.targets,
                "target": self.targets,
                "targets": self.targets,
                "status": self.statuses,
                "statuses": self.statuses,
                "date": self.dates,
                "dates": self.dates,
                "close": self.closes,
                "closes": self.closes,
                "positive": self.positive,
                "negative": self.negative,
                "pending": self.pending,
            }
            if key in aliases:
                return aliases[key]
            return tuple(label[key] for label in self)
        result = super().__getitem__(key)
        return LabelSeries(result) if isinstance(key, slice) else result

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple)):
            if len(self) != len(other):
                return False
            for left, right in zip(self, other, strict=False):
                if isinstance(right, Mapping):
                    if not all(left.get(key) == value for key, value in right.items()):
                        return False
                elif left != right:
                    return False
            return True
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self == other


Label = TargetLabel
TargetLabelSeries = LabelSeries
Labels = LabelSeries
LabelsResult = LabelSeries


def build_target_labels(
    data: Any = None,
    closes: Any = None,
    *,
    dates: Any = None,
    threshold: Any = None,
    horizon: Any = None,
    horizon_sessions: Any = None,
    config: Any = None,
    rows: Any = None,
    observations: Any = None,
    **kwargs: Any,
) -> LabelSeries:
    """Build deterministic target labels from ordered session rows.

    ``data`` may be a sequence of mappings/objects with a date and close, a
    sequence of ``(date, close)`` pairs, or a date sequence when ``closes`` is
    supplied separately.  ``dates=``/``closes=`` keyword form is also accepted.
    """

    if rows is not None:
        if data is not None:
            raise LabelError("rows was provided more than once")
        data = rows
    if observations is not None:
        if data is not None:
            raise LabelError("observations was provided more than once")
        data = observations
    data = _resolve_alias(kwargs, ("rows", "observations", "prices"), data)
    dates = _resolve_alias(kwargs, ("session_dates", "sessions"), dates)
    closes = _resolve_alias(kwargs, ("close", "values", "prices"), closes)
    threshold = _resolve_alias(
        kwargs,
        ("drawdown_threshold", "target_threshold", "min_drawdown", "drop"),
        threshold,
    )
    horizon_sessions = _resolve_alias(
        kwargs,
        (
            "horizon_sessions",
            "target_horizon",
            "window",
            "sessions",
            "n_sessions",
            "lookahead",
            "horizon_days",
            "forward_sessions",
            "step",
        ),
        horizon_sessions if horizon_sessions is not None else horizon,
    )
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise LabelError(f"unknown target label option(s): {unknown}")

    values = _configured(config, threshold=threshold, horizon_sessions=horizon_sessions)
    threshold_value = values["threshold"]
    horizon_value = values["horizon_sessions"]

    ordered_dates, closes_values = _price_rows(data, closes, dates=dates)
    count = len(ordered_dates)
    labels: list[TargetLabel] = []
    for index in range(count):
        close = closes_values[index]
        end_index = index + horizon_value
        observed_end = min(end_index, count - 1)
        min_close: float | None = None
        first_breach: int | None = None
        for future in range(index + 1, observed_end + 1):
            candidate = closes_values[future]
            if min_close is None or candidate < min_close:
                min_close = candidate
            if first_breach is None and (close - candidate) / close >= threshold_value - 1e-15:
                first_breach = future
        if first_breach is not None:
            target: int | None = 1
            status = STATUS_POSITIVE
        elif end_index < count:
            target = 0
            status = STATUS_NEGATIVE
        else:
            target = None
            status = STATUS_PENDING
        breach_date = ordered_dates[first_breach] if first_breach is not None else None
        horizon_end_date = ordered_dates[end_index] if end_index < count else None
        drawdown = (close - min_close) / close if min_close is not None else None
        future_return = (min_close / close - 1.0) if min_close is not None else None
        labels.append(
            TargetLabel(
                index=index,
                date=ordered_dates[index],
                close=close,
                target=target,
                status=status,
                breach_index=first_breach,
                breach_date=breach_date,
                horizon_end_index=end_index,
                horizon_end_date=horizon_end_date,
                min_drawdown=drawdown,
                future_return=future_return,
            )
        )
    return LabelSeries(labels)


# Friendly aliases used by callers/tests.
build_labels = build_target_labels
label_targets = build_target_labels
compute_target_labels = build_target_labels
make_target_labels = build_target_labels
generate_target_labels = build_target_labels
labels_from_rows = build_target_labels
target_labels = build_target_labels
build_target_label = build_target_labels
build_label_series = build_target_labels
compute_labels = build_target_labels
make_labels = build_target_labels
label_sessions = build_target_labels


@dataclass(frozen=True, slots=True)
class BreachEpisode:
    """A chain of distinct first-breach sessions and its positive origins."""

    start_index: int
    end_index: int
    start_date: str | None
    end_date: str | None
    breach_indices: tuple[int, ...]
    breach_dates: tuple[str, ...]
    origin_indices: tuple[int, ...] = ()
    origin_dates: tuple[str, ...] = ()
    positive_origins: int = 0
    gap_sessions: int = DEFAULT_EPISODE_GAP_SESSIONS

    @property
    def onset_index(self) -> int:
        return self.start_index

    @property
    def onset_date(self) -> str | None:
        return self.start_date

    @property
    def first_index(self) -> int:
        return self.start_index

    @property
    def first_date(self) -> str | None:
        return self.start_date

    @property
    def first_breach_index(self) -> int:
        return self.start_index

    @property
    def first_breach_date(self) -> str | None:
        return self.start_date

    @property
    def last_index(self) -> int:
        return self.end_index

    @property
    def last_date(self) -> str | None:
        return self.end_date

    @property
    def last_breach_index(self) -> int:
        return self.end_index

    @property
    def last_breach_date(self) -> str | None:
        return self.end_date

    @property
    def breach_index(self) -> int:
        return self.start_index

    @property
    def breach_date(self) -> str | None:
        return self.start_date

    @property
    def start(self) -> int:
        return self.start_index

    @property
    def end(self) -> int:
        return self.end_index

    @property
    def first_breach(self) -> int:
        return self.start_index

    @property
    def last_breach(self) -> int:
        return self.end_index

    @property
    def positive_origin_indices(self) -> tuple[int, ...]:
        return self.origin_indices

    @property
    def indices(self) -> tuple[int, ...]:
        return self.breach_indices

    @property
    def dates(self) -> tuple[str, ...]:
        return self.breach_dates

    @property
    def breach_count(self) -> int:
        return len(self.breach_indices)

    @property
    def n_breaches(self) -> int:
        return self.breach_count

    @property
    def session_count(self) -> int:
        return self.end_index - self.start_index + 1

    @property
    def length(self) -> int:
        return self.session_count

    @property
    def duration(self) -> int:
        return self.session_count

    @property
    def positive_origin_count(self) -> int:
        return self.positive_origins

    @property
    def n_positive_origins(self) -> int:
        return self.positive_origins

    @property
    def positive_count(self) -> int:
        return self.positive_origins

    @property
    def origin_count(self) -> int:
        return self.positive_origins

    @property
    def positive_origins_count(self) -> int:
        return self.positive_origins

    @property
    def origins(self) -> tuple[int, ...]:
        return self.origin_indices

    @property
    def n_origins(self) -> int:
        return self.positive_origins

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_index": self.start_index,
            "end_index": self.end_index,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "onset_index": self.start_index,
            "onset_date": self.start_date,
            "first_index": self.start_index,
            "first_date": self.start_date,
            "last_index": self.end_index,
            "last_date": self.end_date,
            "breach_indices": list(self.breach_indices),
            "breach_dates": list(self.breach_dates),
            "origin_indices": list(self.origin_indices),
            "origin_dates": list(self.origin_dates),
            "positive_origins": self.positive_origins,
            "positive_origin_count": self.positive_origins,
            "breach_count": self.breach_count,
            "session_count": self.session_count,
            "gap_sessions": self.gap_sessions,
        }

    def keys(self) -> tuple[str, ...]:
        return tuple(self.as_dict())

    def items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.as_dict().items())

    def values(self) -> tuple[Any, ...]:
        return tuple(self.as_dict().values())

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            aliases = {
                "start": self.start_index,
                "end": self.end_index,
                "onset": self.start_index,
                "first": self.start_index,
                "last": self.end_index,
                "indices": self.breach_indices,
                "dates": self.breach_dates,
                "breaches": self.breach_indices,
                "first_breach_index": self.start_index,
                "first_breach_date": self.start_date,
                "last_breach_index": self.end_index,
                "last_breach_date": self.end_date,
                "positive_origins": self.positive_origins,
                "positive_count": self.positive_origins,
                "n_positive_origins": self.positive_origins,
                "origin_indices": self.origin_indices,
                "origin_dates": self.origin_dates,
                "n_breaches": self.breach_count,
                "breach_count": self.breach_count,
                "session_count": self.session_count,
                "length": self.session_count,
            }
            if key in aliases:
                return aliases[key]
            return self.as_dict()[key]
        return self.as_dict()[key]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self.as_dict()

    def __iter__(self):
        return iter(self.as_dict())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, BreachEpisode):
            return self.as_dict() == other.as_dict()
        if isinstance(other, Mapping):
            return all(self.get(str(key)) == value for key, value in other.items())
        if isinstance(other, numbers.Integral):
            return self.start_index == int(other)
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return NotImplemented
        return not result


Episode = BreachEpisode
Breach = BreachEpisode


class BreachEpisodeSeries(list):
    """Ordered breach episodes with convenient aggregate access."""

    def __init__(
        self,
        episodes: Iterable[BreachEpisode] = (),
        session_dates: Iterable[str] = (),
    ) -> None:
        super().__init__(episodes)
        self.session_dates: tuple[str, ...] = tuple(session_dates)

    @property
    def dates(self) -> tuple[str, ...]:
        """Full ordered session dates when the caller supplied them."""

        return self.session_dates

    @property
    def episodes(self) -> tuple[BreachEpisode, ...]:
        return tuple(self)

    @property
    def onsets(self) -> tuple[int, ...]:
        return tuple(episode.start_index for episode in self)

    @property
    def onset_dates(self) -> tuple[str | None, ...]:
        return tuple(episode.start_date for episode in self)

    @property
    def breach_indices(self) -> tuple[int, ...]:
        result: list[int] = []
        for episode in self:
            result.extend(episode.breach_indices)
        return tuple(result)

    @property
    def breach_dates(self) -> tuple[str, ...]:
        result: list[str] = []
        for episode in self:
            result.extend(episode.breach_dates)
        return tuple(result)

    @property
    def positive_origins(self) -> int:
        return sum(episode.positive_origins for episode in self)

    @property
    def positive_origin_count(self) -> int:
        return self.positive_origins

    @property
    def origin_count(self) -> int:
        return self.positive_origins

    def to_dicts(self) -> list[dict[str, Any]]:
        return [episode.as_dict() for episode in self]

    def as_dict(self) -> dict[str, Any]:
        return {
            "episodes": self.to_dicts(),
            "onset_indices": list(self.onsets),
            "onset_dates": list(self.onset_dates),
            "breach_indices": list(self.breach_indices),
            "positive_origins": self.positive_origins,
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            aliases = {
                "episodes": self.episodes,
                "onsets": self.onsets,
                "onset_indices": self.onsets,
                "onset_dates": self.onset_dates,
                "breach_indices": self.breach_indices,
                "breach_dates": self.breach_dates,
                "positive_origins": self.positive_origins,
            }
            if key in aliases:
                return aliases[key]
            return tuple(episode[key] for episode in self)
        result = super().__getitem__(key)
        return BreachEpisodeSeries(result) if isinstance(key, slice) else result

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple)):
            if len(self) != len(other):
                return False
            for left, right in zip(self, other, strict=False):
                if isinstance(right, Mapping):
                    if not all(left.get(key) == value for key, value in right.items()):
                        return False
                elif left != right:
                    return False
            return True
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self == other


Episodes = BreachEpisodeSeries
EpisodeSeries = BreachEpisodeSeries
BreachEpisodes = BreachEpisodeSeries


def _breach_positions(
    data: Any,
    closes: Any,
    *,
    dates: Any,
    labels: Any,
    threshold: Any = None,
    horizon_sessions: Any = None,
) -> tuple[tuple[int, ...], LabelSeries | None, tuple[str, ...]]:
    """Return distinct breach positions, optional labels and session dates."""

    session_dates: tuple[str, ...] = ()
    label_series: LabelSeries | None = None

    if labels is not None:
        label_series = _target_label_series(labels)
        session_dates = label_series.dates
        positions = sorted(
            {label.breach_index for label in label_series if label.breach_index is not None}
        )
        return tuple(positions), label_series, session_dates

    if data is None:
        if closes is not None and dates is not None:
            label_series = build_target_labels(
                dates,
                closes,
                threshold=threshold,
                horizon_sessions=horizon_sessions,
            )
            session_dates = label_series.dates
            positions = sorted(
                {label.breach_index for label in label_series if label.breach_index is not None}
            )
            return tuple(positions), label_series, session_dates
        raise EpisodeError("breach data is required")

    if isinstance(data, LabelSeries) or (
        isinstance(data, (list, tuple))
        and data
        and all(isinstance(item, TargetLabel) for item in data)
    ):
        label_series = _target_label_series(data)
        session_dates = label_series.dates
        positions = sorted(
            {label.breach_index for label in label_series if label.breach_index is not None}
        )
        return tuple(positions), label_series, session_dates

    if isinstance(data, BreachEpisodeSeries) or (
        isinstance(data, (list, tuple))
        and data
        and all(isinstance(item, BreachEpisode) for item in data)
    ):
        raise _AlreadyEpisodes(data)

    if isinstance(data, BreachEpisode):
        raise _AlreadyEpisodes([data])

    items = _materialise_sequence(data, "breaches")
    if not items:
        if dates is not None:
            session_dates = validate_dates(dates)
        return (), label_series, session_dates

    if all(
        isinstance(item, Mapping)
        and _row_get(item, _DATE_FIELDS) is not None
        and any(_row_get(item, (field,)) is not None for field in ("target", "label", "status"))
        for item in items
    ):
        label_series = _target_label_series(items)
        session_dates = label_series.dates
        positions = sorted(
            {label.breach_index for label in label_series if label.breach_index is not None}
        )
        return tuple(positions), label_series, session_dates

    # A caller may pass breach indices together with the full session data so
    # that positive label origins can still be counted.
    if all(isinstance(item, numbers.Integral) and not isinstance(item, bool) for item in items):
        if closes is not None:
            if dates is None:
                raise EpisodeError("session dates are required with closes")
            label_series = build_target_labels(
                dates,
                closes,
                threshold=threshold,
                horizon_sessions=horizon_sessions,
            )
            session_dates = label_series.dates
            positions = tuple(int(item) for item in items)
            return positions, label_series, session_dates
        if dates is not None:
            session_dates = validate_dates(dates)
            data = items
        else:
            session_dates = ()
            data = items

    if not all(isinstance(item, numbers.Integral) and not isinstance(item, bool) for item in items):
        # Price rows, or a date sequence plus closes, still produce labels.
        if closes is not None or all(
            _row_get(item, _DATE_FIELDS) is not None and _row_get(item, _CLOSE_FIELDS) is not None
            for item in items
        ):
            label_series = build_target_labels(
                data,
                closes,
                dates=dates,
                threshold=threshold,
                horizon_sessions=horizon_sessions,
            )
            session_dates = label_series.dates
            positions = sorted(
                {label.breach_index for label in label_series if label.breach_index is not None}
            )
            return tuple(positions), label_series, session_dates

    if all(isinstance(item, numbers.Integral) and not isinstance(item, bool) for item in items):
        positions = tuple(int(item) for item in items)
        if dates is not None and not session_dates:
            session_dates = validate_dates(dates)
        if session_dates:
            for position in positions:
                if position < 0 or position >= len(session_dates):
                    raise EpisodeError(
                        f"breach index {position} is outside {len(session_dates)} sessions"
                    )
        return positions, label_series, session_dates

    # Date-form breaches.  Full session dates are required to measure a
    # session gap; the breach-event list itself is not a session calendar.
    if all(_looks_like_date(item) for item in items):
        breach_dates = [_coerce_date(item, "breach_date") for item in items]
        if dates is None:
            raise EpisodeError(
                "session dates are required when grouping breach dates; pass the full "
                "ordered session rows or explicit breach positions"
            )
        session_dates = validate_dates(dates)
        lookup = {value: index for index, value in enumerate(session_dates)}
        positions = []
        for value in breach_dates:
            if value not in lookup:
                raise EpisodeError(f"breach date {value!r} is not a session date")
            positions.append(lookup[value])
        return tuple(positions), label_series, session_dates

    raise EpisodeError("breaches must be row indices, ISO dates or price rows")


class _AlreadyEpisodes(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


def _coerce_episode(value: Any, position: int) -> BreachEpisode:
    if isinstance(value, BreachEpisode):
        return value
    if not isinstance(value, Mapping) and not hasattr(value, "start_index"):
        raise EpisodeError(f"episodes[{position}] is not a breach episode")
    start = _row_get(value, _EPISODE_START_FIELDS)
    end = _row_get(value, _EPISODE_END_FIELDS)
    breach_indices = _row_get(value, _EPISODE_BREACH_INDEX_FIELDS)
    breach_dates = _row_get(value, _EPISODE_BREACH_DATE_FIELDS)
    if breach_indices is None:
        if start is None:
            raise EpisodeError(f"episodes[{position}] is missing start_index")
        breach_indices = (int(start),)
    else:
        breach_indices = tuple(int(item) for item in breach_indices)
    if start is None:
        start = min(breach_indices)
    if end is None:
        end = max(breach_indices)
    if breach_dates is None:
        breach_dates = ()
    else:
        breach_dates = tuple(_coerce_date(item) for item in breach_dates)
    origin_indices = _row_get(value, ("origin_indices", "origins"))
    origin_dates = _row_get(value, ("origin_dates",))
    positive = _row_get(
        value,
        ("positive_origins", "positive_origin_count", "n_positive_origins", "positive_count"),
    )
    start_date = _row_get(value, ("start_date", "onset_date", "first_date", "first_breach_date"))
    end_date = _row_get(value, ("end_date", "last_date", "last_breach_date"))
    return BreachEpisode(
        start_index=int(start),
        end_index=int(end),
        start_date=None if start_date is None else _coerce_date(start_date),
        end_date=None if end_date is None else _coerce_date(end_date),
        breach_indices=breach_indices,
        breach_dates=breach_dates,
        origin_indices=(
            () if origin_indices is None else tuple(int(item) for item in origin_indices)
        ),
        origin_dates=()
        if origin_dates is None
        else tuple(_coerce_date(item) for item in origin_dates),
        positive_origins=0 if positive is None else int(positive),
        gap_sessions=int(_row_get(value, ("gap_sessions", "gap")) or DEFAULT_EPISODE_GAP_SESSIONS),
    )


def build_breach_episodes(
    data: Any = None,
    closes: Any = None,
    *,
    dates: Any = None,
    gap_sessions: Any = None,
    gap: Any = None,
    episode_gap_sessions: Any = None,
    labels: Any = None,
    breaches: Any = None,
    episodes: Any = None,
    breach_indices: Any = None,
    breach_dates: Any = None,
    label_series: Any = None,
    threshold: Any = None,
    horizon: Any = None,
    horizon_sessions: Any = None,
    config: Any = None,
    **kwargs: Any,
) -> BreachEpisodeSeries:
    """Group distinct first-breach sessions into deterministic episodes."""

    if label_series is not None:
        if labels is not None:
            raise EpisodeError("labels was provided more than once")
        labels = label_series
    label_hint: LabelSeries | None = None
    if labels is not None:
        if data is None:
            data = labels
        else:
            label_hint = _target_label_series(labels)
    for name, value in (
        ("breaches", breaches),
        ("episodes", episodes),
        ("breach_indices", breach_indices),
        ("breach_dates", breach_dates),
    ):
        if value is None:
            continue
        if data is not None:
            raise EpisodeError(f"{name} was provided more than once")
        data = value
    data = _resolve_alias(kwargs, ("episode", "breach", "rows"), data)
    dates = _resolve_alias(kwargs, ("session_dates", "sessions"), dates)
    gap_sessions = _resolve_alias(
        kwargs,
        (
            "gap_sessions",
            "episode_gap_sessions",
            "breach_gap_sessions",
            "episode_gap",
            "max_gap",
            "gap",
        ),
        gap_sessions
        if gap_sessions is not None
        else (episode_gap_sessions if episode_gap_sessions is not None else gap),
    )
    threshold = _resolve_alias(
        kwargs, ("drawdown_threshold", "target_threshold", "min_drawdown"), threshold
    )
    horizon_sessions = _resolve_alias(
        kwargs,
        (
            "horizon_sessions",
            "target_horizon",
            "window",
            "n_sessions",
            "lookahead",
        ),
        horizon_sessions if horizon_sessions is not None else horizon,
    )
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise EpisodeError(f"unknown episode option(s): {unknown}")
    values = _configured(
        config,
        threshold=threshold,
        horizon_sessions=horizon_sessions,
        gap_sessions=gap_sessions,
    )
    gap_value = values["gap_sessions"]

    # Accommodate an explicit label series supplied as the second positional
    # argument (for example ``build_breach_episodes(indices, labels)``).
    if closes is not None and (
        isinstance(closes, LabelSeries)
        or (
            isinstance(closes, (list, tuple))
            and closes
            and all(isinstance(item, TargetLabel) for item in closes)
        )
    ):
        if label_hint is not None:
            raise EpisodeError("labels was provided more than once")
        label_hint = _target_label_series(closes)
        closes = None

    # Accommodate the natural ``build_breach_episodes(session_dates,
    # breach_dates)`` call without mistaking the second sequence for closes.
    if closes is not None and data is not None:
        first = _materialise_sequence(data, "data")
        second = _materialise_sequence(closes, "breaches")
        first_all_dates = bool(first) and all(_looks_like_date(item) for item in first)
        second_all_dates = bool(second) and all(_looks_like_date(item) for item in second)
        second_all_indices = bool(second) and all(
            isinstance(item, numbers.Integral) and not isinstance(item, bool) for item in second
        )
        if second_all_dates and first_all_dates:
            closes, data, dates = None, second, first
        elif (
            second_all_indices
            and first_all_dates
            and len(second) < len(first)
            and all(0 <= int(item) < len(first) for item in second)
        ):
            closes, data, dates = None, second, first

    try:
        positions, label_series, session_dates = _breach_positions(
            data,
            closes,
            dates=dates,
            labels=None,
            threshold=values["threshold"],
            horizon_sessions=values["horizon_sessions"],
        )
    except _AlreadyEpisodes as already:
        result = [_coerce_episode(item, index) for index, item in enumerate(already.value)]
        result.sort(key=lambda episode: (episode.start_index, episode.end_index))
        known_dates = tuple(getattr(already.value, "session_dates", ()))
        return BreachEpisodeSeries(result, session_dates=known_dates)

    if label_hint is not None:
        label_series = label_hint
        if not session_dates:
            session_dates = label_hint.dates

    ordered_positions = sorted(set(int(position) for position in positions))
    groups: list[list[int]] = []
    for position in ordered_positions:
        if position < 0:
            raise EpisodeError(f"breach index must be non-negative, got {position}")
        if not groups or position - groups[-1][-1] > gap_value:
            groups.append([position])
        else:
            groups[-1].append(position)

    result_episodes: list[BreachEpisode] = []
    for group in groups:
        start = group[0]
        end = group[-1]
        start_date = (
            session_dates[start] if session_dates and 0 <= start < len(session_dates) else None
        )
        end_date = session_dates[end] if session_dates and 0 <= end < len(session_dates) else None
        breach_dates = tuple(
            session_dates[position]
            for position in group
            if session_dates and 0 <= position < len(session_dates)
        )
        # Origins are emitted in input-row order.  Grouping them by breach
        # position would reorder an episode whenever an earlier origin breaches
        # later than a subsequent origin.
        origin_pairs: list[tuple[int, str]] = []
        if label_series is not None:
            group_positions = set(group)
            for label in label_series:
                if label.positive and label.breach_index in group_positions:
                    origin_pairs.append((label.index, label.date))
        origin_pairs.sort(key=lambda item: item[0])
        origin_indices = [index for index, _ in origin_pairs]
        origin_dates = [date_value for _, date_value in origin_pairs]
        result_episodes.append(
            BreachEpisode(
                start_index=start,
                end_index=end,
                start_date=start_date,
                end_date=end_date,
                breach_indices=tuple(group),
                breach_dates=breach_dates,
                origin_indices=tuple(origin_indices),
                origin_dates=tuple(origin_dates),
                positive_origins=len(origin_indices),
                gap_sessions=gap_value,
            )
        )
    return BreachEpisodeSeries(result_episodes, session_dates=session_dates)


# Friendly aliases used by callers/tests.
build_episodes = build_breach_episodes
breach_episodes = build_breach_episodes
find_breach_episodes = build_breach_episodes
detect_breach_episodes = build_breach_episodes
episodes_from_breaches = build_breach_episodes
build_breach_episode_series = build_breach_episodes
compute_breach_episodes = build_breach_episodes
derive_breach_episodes = build_breach_episodes
group_breach_episodes = build_breach_episodes
make_breach_episodes = build_breach_episodes


@dataclass(frozen=True, slots=True)
class Alert:
    """One early-alert row, identified by row position and/or ISO date."""

    index: int | None = None
    date: str | None = None
    payload: Any = None
    order: int = 0

    @property
    def position(self) -> int | None:
        return self.index

    @property
    def row_index(self) -> int | None:
        return self.index

    @property
    def session_index(self) -> int | None:
        return self.index

    @property
    def alert_date(self) -> str | None:
        return self.date

    @property
    def id(self) -> Any:
        return self.payload

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "date": self.date,
            "position": self.index,
            "alert_date": self.date,
            "payload": self.payload,
            "order": self.order,
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            aliases = {
                "position": self.index,
                "row_index": self.index,
                "session_index": self.index,
                "alert_date": self.date,
                "id": self.payload,
            }
            if key in aliases:
                return aliases[key]
            return self.as_dict()[key]
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


EarlyAlert = Alert


@dataclass(frozen=True, slots=True)
class AlertMatch:
    """One successfully matched alert/episode pair."""

    alert: Alert
    episode: BreachEpisode
    lead_sessions: int
    order: int = 0

    @property
    def alert_index(self) -> int | None:
        return self.alert.index

    @property
    def alert_date(self) -> str | None:
        return self.alert.date

    @property
    def episode_index(self) -> int:
        return self.episode.start_index

    @property
    def episode_onset(self) -> int:
        return self.episode.start_index

    @property
    def onset_index(self) -> int:
        return self.episode.start_index

    @property
    def onset_date(self) -> str | None:
        return self.episode.start_date

    @property
    def episode_date(self) -> str | None:
        return self.episode.start_date

    @property
    def breach_date(self) -> str | None:
        return self.episode.start_date

    @property
    def alert_position(self) -> int | None:
        return self.alert.index

    @property
    def sessions_before(self) -> int:
        return self.lead_sessions

    @property
    def lead(self) -> int:
        return self.lead_sessions

    @property
    def sessions(self) -> int:
        return self.lead_sessions

    @property
    def status(self) -> str:
        return MATCHED

    @property
    def matched(self) -> bool:
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": MATCHED,
            "alert_index": self.alert_index,
            "alert_date": self.alert_date,
            "episode_index": self.episode_index,
            "onset_index": self.onset_index,
            "onset_date": self.onset_date,
            "lead_sessions": self.lead_sessions,
            "order": self.order,
            "alert": self.alert.as_dict(),
            "episode": self.episode.as_dict(),
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            aliases = {
                "lead": self.lead_sessions,
                "sessions": self.lead_sessions,
                "episode_onset": self.episode.start_index,
                "matched": True,
            }
            if key in aliases:
                return aliases[key]
            return self.as_dict()[key]
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


Match = AlertMatch
EarlyAlertMatch = AlertMatch


@dataclass(frozen=True, slots=True)
class AlertOutcome:
    """The classified outcome of one alert, matched or not."""

    alert: Alert
    status: str
    match: AlertMatch | None = None
    reason: str | None = None

    @property
    def matched(self) -> bool:
        return self.match is not None

    @property
    def pending(self) -> bool:
        return self.status == UNMATCHED_PENDING

    @property
    def false_mature(self) -> bool:
        return self.status == FALSE_MATURE

    @property
    def post_onset(self) -> bool:
        return self.status == POST_ONSET

    @property
    def duplicate(self) -> bool:
        return self.status == DUPLICATE

    def as_dict(self) -> dict[str, Any]:
        return {
            "alert": self.alert.as_dict(),
            "status": self.status,
            "reason": self.reason,
            "match": None if self.match is None else self.match.as_dict(),
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            aliases = {
                "alert_index": self.alert.index,
                "alert_date": self.alert.date,
                "matched": self.matched,
                "pending": self.pending,
                "false_mature": self.false_mature,
                "post_onset": self.post_onset,
                "duplicate": self.duplicate,
            }
            if key in aliases:
                return aliases[key]
            return self.as_dict()[key]
        return self.as_dict()[key]


class _ResultTuple(tuple):
    """Immutable collection that compares equal to both tuples and lists."""

    def __new__(cls, values: Iterable[Any] = ()) -> _ResultTuple:
        return super().__new__(cls, tuple(values))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple)):
            return list(self) == list(other)
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self == other

    __hash__ = tuple.__hash__


@dataclass(frozen=True, slots=True)
class AlertMatchResult:
    """Chronological one-to-one alert matching result."""

    matches: tuple[AlertMatch, ...]
    episodes: tuple[BreachEpisode, ...]
    alerts: tuple[Alert, ...]
    pending_alerts: tuple[Alert, ...] = ()
    false_alerts: tuple[Alert, ...] = ()
    duplicate_alerts: tuple[Alert, ...] = ()
    post_onset_alerts: tuple[Alert, ...] = ()
    missed_episodes: tuple[BreachEpisode, ...] = ()
    outcomes: tuple[AlertOutcome, ...] = ()
    n_sessions: int | None = None
    lead_sessions: int = DEFAULT_ALERT_LEAD_SESSIONS
    credit_rule: str = CREDIT_RULE_ONSET_WINDOW

    def __post_init__(self) -> None:
        for name in (
            "matches",
            "episodes",
            "alerts",
            "pending_alerts",
            "false_alerts",
            "duplicate_alerts",
            "post_onset_alerts",
            "missed_episodes",
            "outcomes",
        ):
            object.__setattr__(self, name, _ResultTuple(getattr(self, name)))

    @property
    def matched(self) -> tuple[AlertMatch, ...]:
        return self.matches

    @property
    def matched_alerts(self) -> tuple[Alert, ...]:
        return tuple(match.alert for match in self.matches)

    @property
    def matched_episodes(self) -> tuple[BreachEpisode, ...]:
        return tuple(match.episode for match in self.matches)

    @property
    def matched_pairs(self) -> tuple[AlertMatch, ...]:
        return self.matches

    @property
    def false_mature(self) -> tuple[Alert, ...]:
        return self.false_alerts

    @property
    def false_positive(self) -> tuple[Alert, ...]:
        return self.false_alerts

    @property
    def missed(self) -> tuple[BreachEpisode, ...]:
        return self.missed_episodes

    @property
    def pending(self) -> tuple[Alert, ...]:
        return self.pending_alerts

    @property
    def false(self) -> tuple[Alert, ...]:
        return self.false_alerts

    @property
    def false_positives(self) -> tuple[Alert, ...]:
        return self.false_alerts

    @property
    def false_mature_alerts(self) -> tuple[Alert, ...]:
        return self.false_alerts

    @property
    def duplicates(self) -> tuple[Alert, ...]:
        return self.duplicate_alerts

    @property
    def post_onset(self) -> tuple[Alert, ...]:
        return self.post_onset_alerts

    @property
    def unmatched_alerts(self) -> tuple[Alert, ...]:
        return tuple(outcome.alert for outcome in self.outcomes if outcome.match is None)

    @property
    def unmatched(self) -> tuple[Alert, ...]:
        return self.unmatched_alerts

    @property
    def match_count(self) -> int:
        return len(self.matches)

    @property
    def missed_count(self) -> int:
        return len(self.missed_episodes)

    @property
    def pending_count(self) -> int:
        return len(self.pending_alerts)

    @property
    def false_count(self) -> int:
        return len(self.false_alerts)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_alerts)

    @property
    def post_onset_count(self) -> int:
        return len(self.post_onset_alerts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "matches": [match.as_dict() for match in self.matches],
            "matched": [match.as_dict() for match in self.matches],
            "pending_alerts": [alert.as_dict() for alert in self.pending_alerts],
            "false_alerts": [alert.as_dict() for alert in self.false_alerts],
            "false_mature_alerts": [alert.as_dict() for alert in self.false_alerts],
            "duplicate_alerts": [alert.as_dict() for alert in self.duplicate_alerts],
            "post_onset_alerts": [alert.as_dict() for alert in self.post_onset_alerts],
            "missed_episodes": [episode.as_dict() for episode in self.missed_episodes],
            "unmatched_alerts": [alert.as_dict() for alert in self.unmatched_alerts],
            "outcomes": [outcome.as_dict() for outcome in self.outcomes],
            "match_count": self.match_count,
            "missed_count": self.missed_count,
            "pending_count": self.pending_count,
            "false_count": self.false_count,
            "duplicate_count": self.duplicate_count,
            "post_onset_count": self.post_onset_count,
            "n_sessions": self.n_sessions,
            "lead_sessions": self.lead_sessions,
            "credit_rule": self.credit_rule,
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            aliases = {
                "matches": self.matches,
                "matched": self.matches,
                "pending": self.pending_alerts,
                "false": self.false_alerts,
                "false_positives": self.false_alerts,
                "false_mature_alerts": self.false_alerts,
                "duplicates": self.duplicate_alerts,
                "post_onset": self.post_onset_alerts,
                "missed": self.missed_episodes,
                "unmatched": self.unmatched_alerts,
                "outcomes": self.outcomes,
            }
            if key in aliases:
                return aliases[key]
            return self.as_dict()[key]
        return self.matches[key]

    def keys(self) -> tuple[str, ...]:
        return tuple(self.as_dict())

    def values(self) -> tuple[Any, ...]:
        return tuple(self.as_dict().values())

    def items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.as_dict().items())

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            return item in self.as_dict()
        return item in self.matches

    def __len__(self) -> int:
        return len(self.matches)

    def __iter__(self):
        return iter(self.matches)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple)):
            return list(self.matches) == list(other)
        if isinstance(other, AlertMatchResult):
            return self.as_dict() == other.as_dict()
        if isinstance(other, Mapping):
            return all(self.get(str(key)) == value for key, value in other.items())
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return NotImplemented
        return not result


MatchResult = AlertMatchResult
AlertEvaluation = AlertMatchResult
AlertMatchResults = AlertMatchResult
EarlyAlertResult = AlertMatchResult
AlertMatchingResult = AlertMatchResult
AlertMatchSummary = AlertMatchResult
AlertResult = AlertMatchResult
EpisodeMatchResult = AlertMatchResult

TargetLabels = LabelSeries
TargetLabelRow = TargetLabel
LabelRow = TargetLabel
LabelRows = LabelSeries
LabelSet = LabelSeries
LabelList = LabelSeries
BreachEpisodeList = BreachEpisodeSeries
BreachEpisodeRow = BreachEpisode
EpisodeSet = BreachEpisodeSeries
EpisodeList = BreachEpisodeSeries
breach_episode_series = build_breach_episodes
alert_match_summary = AlertMatchResult
AlertMatching = AlertMatch
MatchedAlert = AlertMatch
Warning = Alert
EarlyWarning = Alert


def _normalise_alerts(alerts: Any, session_dates: Sequence[str]) -> tuple[Alert, ...]:
    if alerts is None:
        return ()
    if isinstance(alerts, Alert):
        items: list[Any] = [alerts]
    elif isinstance(alerts, Mapping):
        if "alerts" in alerts and len(alerts) == 1:
            items = _materialise_sequence(alerts["alerts"], "alerts")
        elif any(key in alerts for key in (*_DATE_FIELDS, *_INDEX_FIELDS)):
            items = [alerts]
        else:
            items = [{"date": key, "value": value} for key, value in alerts.items()]
    elif isinstance(alerts, (str, bytes, bytearray)):
        raise AlertMatchError("alerts must be a sequence, not text")
    else:
        try:
            items = list(alerts)
        except TypeError as error:
            raise AlertMatchError("alerts must be a sequence") from error

    lookup = {value: index for index, value in enumerate(session_dates)}
    result: list[Alert] = []
    for order, item in enumerate(items):
        index: Any = None
        date_value: Any = None
        payload: Any = item
        if isinstance(item, Alert):
            index = item.index
            date_value = item.date
            payload = item.payload
            order = item.order
        elif isinstance(item, Mapping):
            index = _row_get(item, _INDEX_FIELDS)
            date_value = _row_get(item, _DATE_FIELDS)
            payload = item
        elif isinstance(item, (tuple, list)):
            if len(item) >= 2 and _looks_like_date(item[1]):
                index, date_value = item[0], item[1]
            elif len(item) >= 2 and _looks_like_date(item[0]):
                date_value, index = item[0], item[1]
            elif len(item) == 1:
                index = item[0]
            else:
                index = item[0]
                date_value = None
            payload = item
        elif isinstance(item, (date, datetime)):
            date_value = item
        elif isinstance(item, str):
            date_value = item
        elif isinstance(item, numbers.Integral) and not isinstance(item, bool):
            index = item
        else:
            object_index = _row_get(item, _INDEX_FIELDS)
            object_date = _row_get(item, _DATE_FIELDS)
            if object_index is None and object_date is None:
                raise AlertMatchError(f"alerts[{order}] is not an alert row")
            index = object_index
            date_value = object_date
            payload = item

        if date_value is not None:
            date_value = _coerce_date(date_value, f"alerts[{order}].date")
            if session_dates:
                if date_value not in lookup:
                    raise AlertMatchError(
                        f"alert date {date_value!r} is not one of the {len(session_dates)} sessions"
                    )
                mapped = lookup[date_value]
                if index is not None and int(index) != mapped:
                    raise AlertMatchError(f"alert date {date_value!r} does not match index {index}")
                index = mapped
            elif index is None:
                raise AlertMatchError(
                    "alert dates require the full ordered session dates or explicit indices"
                )
        if index is None:
            raise AlertMatchError(f"alerts[{order}] is missing an index or date")
        index = _coerce_non_negative_int(index, f"alerts[{order}].index")
        result.append(Alert(index=index, date=date_value, payload=payload, order=order))
    return tuple(result)


def _normalise_episodes(
    episodes: Any, *, dates: Any
) -> tuple[BreachEpisodeSeries, tuple[str, ...]]:
    if episodes is None:
        return BreachEpisodeSeries(), ()
    if isinstance(episodes, LabelSeries) or (
        isinstance(episodes, (list, tuple))
        and episodes
        and all(isinstance(item, TargetLabel) for item in episodes)
    ):
        series = _target_label_series(episodes)
        return build_breach_episodes(series), series.dates
    if isinstance(episodes, BreachEpisodeSeries):
        return episodes, tuple(getattr(episodes, "session_dates", ()))
    if isinstance(episodes, BreachEpisode):
        return BreachEpisodeSeries([episodes]), ()
    if (
        isinstance(episodes, (list, tuple))
        and episodes
        and all(
            isinstance(item, Mapping)
            and _row_get(item, _DATE_FIELDS) is not None
            and any(_row_get(item, (field,)) is not None for field in ("target", "label", "status"))
            for item in episodes
        )
    ):
        series = _target_label_series(episodes)
        return build_breach_episodes(series), series.dates
    if (
        isinstance(episodes, (list, tuple))
        and episodes
        and all(isinstance(item, BreachEpisode) for item in episodes)
    ):
        return BreachEpisodeSeries(episodes), ()
    if (
        isinstance(episodes, (list, tuple))
        and episodes
        and all(isinstance(item, Mapping) for item in episodes)
        and any(_row_get(item, _EPISODE_START_FIELDS) is not None for item in episodes)
    ):
        return BreachEpisodeSeries(
            [_coerce_episode(item, index) for index, item in enumerate(episodes)]
        ), ()
    if (
        isinstance(episodes, (list, tuple))
        and episodes
        and all(hasattr(item, "start_index") for item in episodes)
    ):
        return BreachEpisodeSeries(
            [_coerce_episode(item, index) for index, item in enumerate(episodes)]
        ), ()
    # Breach indices/dates or price rows.
    return build_breach_episodes(episodes, dates=dates), ()


def match_alerts(
    alerts: Any,
    episodes: Any = None,
    sessions: Any = None,
    *,
    dates: Any = None,
    n_sessions: Any = None,
    lead_sessions: Any = None,
    max_lead: Any = None,
    alert_lead_sessions: Any = None,
    horizon: Any = None,
    horizon_sessions: Any = None,
    labels: Any = None,
    closes: Any = None,
    config: Any = None,
    **kwargs: Any,
) -> AlertMatchResult:
    """Match early alerts to future breach episodes chronologically and 1:1."""

    first_is_labels = isinstance(alerts, LabelSeries) or (
        isinstance(alerts, (list, tuple))
        and alerts
        and all(isinstance(item, TargetLabel) for item in alerts)
    )
    first_is_episodes = isinstance(alerts, BreachEpisodeSeries) or (
        isinstance(alerts, (list, tuple))
        and alerts
        and all(isinstance(item, BreachEpisode) for item in alerts)
    )
    if (first_is_labels or first_is_episodes) and episodes is not None:
        alerts, episodes = episodes, alerts

    if kwargs:
        # Accept alternative names for the session length and lead window.
        n_sessions = _resolve_alias(
            kwargs, ("session_count", "total_sessions", "length"), n_sessions
        )
        dates = _resolve_alias(kwargs, ("session_dates",), dates)
        lead_sessions = _resolve_alias(
            kwargs,
            (
                "lead_sessions",
                "max_lead",
                "max_lead_sessions",
                "alert_lead_sessions",
                "lead",
                "window",
            ),
            lead_sessions
            if lead_sessions is not None
            else (
                max_lead
                if max_lead is not None
                else (alert_lead_sessions if alert_lead_sessions is not None else horizon)
            ),
        )
        horizon_sessions = _resolve_alias(
            kwargs, ("horizon_sessions", "target_horizon"), horizon_sessions
        )
        if kwargs:
            unknown = ", ".join(sorted(kwargs))
            raise AlertMatchError(f"unknown alert matching option(s): {unknown}")
    if lead_sessions is None:
        lead_sessions = (
            max_lead
            if max_lead is not None
            else (alert_lead_sessions if alert_lead_sessions is not None else horizon)
        )
    if horizon_sessions is not None and lead_sessions is None:
        lead_sessions = horizon_sessions
    values = _configured(config, horizon_sessions=horizon_sessions, lead_sessions=lead_sessions)
    lead_value = values["lead_sessions"]

    session_dates: tuple[str, ...] = ()
    if isinstance(sessions, numbers.Integral) and not isinstance(sessions, bool):
        if n_sessions is not None:
            raise AlertMatchError("n_sessions was provided more than once")
        n_sessions = sessions
    elif sessions is not None:
        if dates is not None:
            raise AlertMatchError("sessions/dates were provided more than once")
        dates = sessions

    label_series: LabelSeries | None = None
    if labels is not None:
        label_series = _target_label_series(labels)
        session_dates = label_series.dates
        if episodes is None:
            episodes = label_series

    if episodes is None and closes is not None:
        if dates is None:
            raise AlertMatchError("dates are required when matching from closes")
        label_series = build_target_labels(dates, closes)
        session_dates = label_series.dates
        episodes = label_series

    if episodes is None:
        raise AlertMatchError("episodes or labels are required")

    episode_series, episode_dates = _normalise_episodes(episodes, dates=dates)
    if not session_dates and episode_dates:
        session_dates = episode_dates
    if dates is not None:
        session_dates = validate_dates(dates)

    # A LabelSeries supplied as the second positional argument also provides
    # the full ordered session dates.
    if not session_dates and isinstance(episodes, LabelSeries):
        session_dates = episodes.dates

    if n_sessions is None and session_dates:
        n_sessions = len(session_dates)
    if n_sessions is not None:
        n_sessions = _coerce_non_negative_int(n_sessions, "n_sessions")

    alert_rows = _normalise_alerts(alerts, session_dates)
    ordered_episodes = sorted(episode_series, key=lambda item: (item.start_index, item.end_index))
    ordered_alerts = sorted(alert_rows, key=lambda item: (item.index or 0, item.order))

    if n_sessions is None:
        known = [alert.index or 0 for alert in ordered_alerts]
        known.extend(episode.end_index for episode in ordered_episodes)
        n_sessions = max(known) + 1 if known else 0

    claimed: set[int] = set()
    seen_alert_indices: set[int] = set()
    matches: list[AlertMatch] = []
    outcomes: list[AlertOutcome] = []
    pending_alerts: list[Alert] = []
    false_alerts: list[Alert] = []
    duplicate_alerts: list[Alert] = []
    post_onset_alerts: list[Alert] = []

    # Strict credit needs the target label of the alert session.  Labels stay
    # optional so the primitive keeps working on bare episode rows; the
    # evaluation pipeline always supplies them.
    label_by_index: dict[int, TargetLabel] | None = None
    label_by_date: dict[str, TargetLabel] | None = None
    breach_owner: dict[int, tuple[int, BreachEpisode]] = {}
    credit_rule = CREDIT_RULE_ONSET_WINDOW
    if label_series is not None:
        credit_rule = CREDIT_RULE_LABEL_BREACH
        label_by_date = {label.date: label for label in label_series if label.date is not None}
        label_by_index = {position: label for position, label in enumerate(label_series)}
        for label in label_series:
            label_by_index.setdefault(int(label.index), label)
        for position, episode in enumerate(ordered_episodes):
            for breach_index in episode.breach_indices:
                breach_owner.setdefault(int(breach_index), (position, episode))

    def _record(alert: Alert, status: str, reason: str, match: AlertMatch | None = None) -> None:
        if match is not None:
            matches.append(match)
        elif status == FALSE_MATURE:
            false_alerts.append(alert)
        elif status == POST_ONSET:
            post_onset_alerts.append(alert)
        elif status == DUPLICATE:
            duplicate_alerts.append(alert)
        elif status == UNMATCHED_PENDING:
            pending_alerts.append(alert)
        outcomes.append(
            AlertOutcome(
                alert=alert,
                status=status,
                match=match,
                reason=None if match is not None else reason,
            )
        )

    for alert in ordered_alerts:
        alert_index = int(alert.index or 0)
        if alert_index in seen_alert_indices:
            duplicate_alerts.append(alert)
            outcomes.append(
                AlertOutcome(
                    alert=alert,
                    status=DUPLICATE,
                    reason="another alert already uses this session",
                )
            )
            continue
        seen_alert_indices.add(alert_index)

        if label_by_date is not None:
            # EV01 credit rule: own label positive, its first breach belongs to
            # the matched episode, onset 1..lead sessions after the alert.
            label = label_by_date.get(alert.date) if alert.date else None
            if label is None and label_by_index is not None:
                label = label_by_index.get(alert_index)
            covering = next(
                (
                    episode
                    for episode in ordered_episodes
                    if episode.start_index <= alert_index <= episode.end_index
                ),
                None,
            )
            matured = alert_index + lead_value < int(n_sessions or 0)
            if covering is not None:
                # A late alert inside an episode keeps its post-onset status.
                _record(alert, POST_ONSET, "the alert is inside an episode that already started")
            elif label is not None and label.pending:
                _record(
                    alert,
                    UNMATCHED_PENDING,
                    "the alert target label horizon has not matured",
                )
            elif label is not None and label.positive and label.first_breach_index is not None:
                owner = breach_owner.get(int(label.first_breach_index))
                if owner is None:
                    if matured:
                        _record(
                            alert,
                            FALSE_MATURE,
                            "the positive label breach is outside the supplied breach episodes",
                        )
                    else:
                        _record(alert, UNMATCHED_PENDING, "the alert lead has not matured yet")
                else:
                    position, episode = owner
                    onset = episode.start_index
                    if onset <= alert_index:
                        _record(
                            alert,
                            POST_ONSET,
                            "the label breach belongs to an episode that already started",
                        )
                    elif onset - alert_index > lead_value:
                        _record(
                            alert,
                            FALSE_MATURE,
                            "the breach episode onset is beyond the alert lead window",
                        )
                    elif position in claimed:
                        _record(
                            alert,
                            DUPLICATE,
                            "the breach episode was already credited to an earlier alert",
                        )
                    else:
                        claimed.add(position)
                        _record(
                            alert,
                            MATCHED,
                            "",
                            AlertMatch(
                                alert=alert,
                                episode=episode,
                                lead_sessions=onset - alert_index,
                                order=alert.order,
                            ),
                        )
            else:
                # The alert's own target did not breach, so it cannot claim a
                # neighbouring episode: it is an unmatched mature alert (or
                # still pending while its own horizon is unobserved).
                if matured:
                    _record(
                        alert,
                        FALSE_MATURE,
                        "the alert matured without a positive target label",
                    )
                else:
                    _record(alert, UNMATCHED_PENDING, "the alert lead has not matured yet")
            continue

        candidates = [
            (position, episode)
            for position, episode in enumerate(ordered_episodes)
            if position not in claimed
            and episode.start_index > alert_index
            and episode.start_index - alert_index <= lead_value
        ]
        if candidates:
            candidates.sort(key=lambda item: (item[1].start_index, item[0]))
            position, episode = candidates[0]
            claimed.add(position)
            match = AlertMatch(
                alert=alert,
                episode=episode,
                lead_sessions=episode.start_index - alert_index,
                order=alert.order,
            )
            matches.append(match)
            outcomes.append(AlertOutcome(alert=alert, status=MATCHED, match=match))
            continue

        # An alert inside an episode's breach span arrived after that onset and
        # is not an early warning for it.
        covering = next(
            (
                episode
                for episode in ordered_episodes
                if episode.start_index <= alert_index <= episode.end_index
            ),
            None,
        )
        if covering is not None:
            post_onset_alerts.append(alert)
            outcomes.append(
                AlertOutcome(
                    alert=alert,
                    status=POST_ONSET,
                    reason="the alert is inside an episode that already started",
                )
            )
            continue

        # An eligible episode may already have been consumed by an earlier
        # alert; this alert is a duplicate rather than a mature false alarm.
        claimed_eligible = next(
            (
                episode
                for position, episode in enumerate(ordered_episodes)
                if position in claimed
                and episode.start_index > alert_index
                and episode.start_index - alert_index <= lead_value
            ),
            None,
        )
        if claimed_eligible is not None:
            duplicate_alerts.append(alert)
            outcomes.append(
                AlertOutcome(
                    alert=alert,
                    status=DUPLICATE,
                    reason="the eligible breach episode was already matched to an earlier alert",
                )
            )
            continue

        # Alerts outside every episode are classified by whether their own
        # lead window has been fully observed; an earlier episode elsewhere in
        # the series does not make them post-onset.
        if alert_index + lead_value < int(n_sessions or 0):
            false_alerts.append(alert)
            outcomes.append(
                AlertOutcome(
                    alert=alert,
                    status=FALSE_MATURE,
                    reason="the full alert lead matured without a breach episode",
                )
            )
        else:
            pending_alerts.append(alert)
            outcomes.append(
                AlertOutcome(
                    alert=alert,
                    status=UNMATCHED_PENDING,
                    reason="the alert lead has not matured yet",
                )
            )

    missed = tuple(
        episode for position, episode in enumerate(ordered_episodes) if position not in claimed
    )
    # Matching is performed chronologically, but the per-alert outcomes and
    # classified alert lists are reported in the caller's input order.
    input_positions = {id(alert): position for position, alert in enumerate(alert_rows)}
    pending_alerts.sort(key=lambda alert: input_positions[id(alert)])
    false_alerts.sort(key=lambda alert: input_positions[id(alert)])
    duplicate_alerts.sort(key=lambda alert: input_positions[id(alert)])
    post_onset_alerts.sort(key=lambda alert: input_positions[id(alert)])
    outcomes.sort(key=lambda outcome: input_positions[id(outcome.alert)])
    return AlertMatchResult(
        matches=tuple(matches),
        episodes=tuple(ordered_episodes),
        alerts=alert_rows,
        pending_alerts=tuple(pending_alerts),
        false_alerts=tuple(false_alerts),
        duplicate_alerts=tuple(duplicate_alerts),
        post_onset_alerts=tuple(post_onset_alerts),
        missed_episodes=missed,
        outcomes=tuple(outcomes),
        n_sessions=n_sessions,
        lead_sessions=lead_value,
        credit_rule=credit_rule,
    )


# Friendly aliases used by callers/tests.
match_early_alerts = match_alerts
match_alerts_to_episodes = match_alerts
match_alert_episodes = match_alerts
evaluate_alerts = match_alerts
evaluate_early_alerts = match_alerts
early_alert_matches = match_alerts
match_early_warnings = match_alerts
match_alerts_to_breach_episodes = match_alerts
evaluate_early_warning_alerts = match_alerts


def __getattr__(name: str) -> Any:
    """Resolve descriptive spellings of the public helpers/result types.

    The explicit names above are the supported API; this small compatibility
    layer keeps alternate spellings (for example ``breach_episode_series`` or
    ``alert_match_summary``) importable without duplicating implementations.
    """

    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    lowered = name.lower()
    if any(token in lowered for token in ("alert", "match", "warning")):
        if lowered.startswith(("build", "compute", "make", "find", "match", "evaluate", "early")):
            return match_alerts
        if lowered.endswith(("result", "results", "summary", "matches", "list", "series")):
            return AlertMatchResult
        if lowered.endswith("match"):
            return AlertMatch
        if lowered.endswith(("warning", "alert")):
            return Alert
        return AlertMatchResult
    if any(token in lowered for token in ("episode", "breach")):
        if lowered.startswith(("build", "compute", "make", "find", "detect", "derive", "group")):
            return build_breach_episodes
        if lowered.endswith(("result", "results", "list", "series", "set", "rows")):
            return BreachEpisodeSeries
        if lowered.endswith(("episode", "breach")):
            return BreachEpisode
        return BreachEpisodeSeries
    if any(token in lowered for token in ("label", "target")):
        if lowered.startswith(
            ("build", "compute", "make", "generate", "create", "label_", "target_")
        ):
            return build_target_labels
        if lowered.endswith(("result", "results", "list", "series", "set", "rows")):
            return LabelSeries
        if lowered.endswith(("label", "target")):
            return TargetLabel
        return LabelSeries
    if "date" in lowered and any(
        token in lowered for token in ("valid", "check", "order", "normal", "ensure")
    ):
        return validate_dates
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ALERT_LEAD_SESSIONS",
    "Alert",
    "AlertError",
    "AlertEvaluation",
    "AlertMatch",
    "AlertMatchError",
    "AlertMatchResult",
    "AlertMatchResults",
    "AlertOutcome",
    "BreachEpisode",
    "BreachEpisodeError",
    "BreachEpisodeSeries",
    "BreachEpisodes",
    "Breach",
    "BREACH_GAP_SESSIONS",
    "DEFAULT_ALERT_LEAD_SESSIONS",
    "DEFAULT_CONFIG",
    "DEFAULT_EPISODE_GAP_SESSIONS",
    "DEFAULT_GAP_SESSIONS",
    "DEFAULT_HORIZON_SESSIONS",
    "DEFAULT_LABEL_CONFIG",
    "DEFAULT_LEAD_SESSIONS",
    "DEFAULT_THRESHOLD",
    "DRAWDOWN_THRESHOLD",
    "DUPLICATE",
    "DateOrderError",
    "EARLY_ALERT_LEAD_SESSIONS",
    "EPISODE_GAP_SESSIONS",
    "EarlyAlert",
    "EarlyAlertError",
    "EarlyAlertMatch",
    "EarlyAlertResult",
    "Episode",
    "EpisodeBuildError",
    "EpisodeError",
    "EpisodeSeries",
    "Episodes",
    "FALSE_MATURE",
    "HORIZON_SESSIONS",
    "AlertMatching",
    "AlertMatchingResult",
    "AlertMatchSummary",
    "AlertResult",
    "AlertStatus",
    "alert_match_summary",
    "BreachEpisodeList",
    "BreachEpisodeRow",
    "EpisodeList",
    "EpisodeMatchResult",
    "EpisodeSet",
    "EarlyWarning",
    "Label",
    "LabelBuildError",
    "LabelConfig",
    "LabelError",
    "LabelList",
    "LabelRow",
    "LabelRows",
    "LabelSeries",
    "LabelSet",
    "LabelSeriesError",
    "LabelStatus",
    "Labels",
    "LabelsResult",
    "MATCHED",
    "CREDIT_RULE_LABEL_BREACH",
    "CREDIT_RULE_ONSET_WINDOW",
    "Match",
    "MatchError",
    "MatchResult",
    "POST_ONSET",
    "STATUS_NEGATIVE",
    "STATUS_PENDING",
    "STATUS_POSITIVE",
    "TARGET_DRAWDOWN",
    "TARGET_HORIZON",
    "TARGET_HORIZON_SESSIONS",
    "TARGET_THRESHOLD",
    "THRESHOLD",
    "TargetLabel",
    "TargetLabelError",
    "TargetLabelSeries",
    "UNMATCHED_PENDING",
    "breach_episode_series",
    "breach_episodes",
    "build_breach_episode_series",
    "build_breach_episodes",
    "build_episodes",
    "build_label_series",
    "build_labels",
    "build_target_label",
    "build_target_labels",
    "check_dates",
    "compute_breach_episodes",
    "ensure_dates",
    "ensure_ordered_dates",
    "compute_labels",
    "compute_target_labels",
    "derive_breach_episodes",
    "detect_breach_episodes",
    "early_alert_matches",
    "episodes_from_breaches",
    "evaluate_alerts",
    "evaluate_early_alerts",
    "evaluate_early_warning_alerts",
    "find_breach_episodes",
    "generate_target_labels",
    "group_breach_episodes",
    "label_sessions",
    "label_targets",
    "labels_from_rows",
    "make_breach_episodes",
    "make_labels",
    "make_target_labels",
    "match_alert_episodes",
    "match_alerts",
    "match_alerts_to_breach_episodes",
    "match_alerts_to_episodes",
    "match_early_alerts",
    "match_early_warnings",
    "normalise_dates",
    "normalise_sessions",
    "normalize_dates",
    "normalize_sessions",
    "ordered_dates",
    "target_labels",
    "TargetLabels",
    "TargetLabelRow",
    "validate_dates",
    "validate_iso_dates",
    "validate_sessions",
    "MatchedAlert",
    "Warning",
]
