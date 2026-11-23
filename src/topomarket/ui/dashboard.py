"""Pure dashboard selection and keyboard helpers for the Step 7 shell.

The dashboard itself is rendered by :mod:`app`, which owns the optional
Streamlit dependency.  This module deliberately contains only immutable state
and small, deterministic helpers so every screen can be tested offline.  In
particular, importing this module never imports Streamlit and never reads a
data directory.

The central type is :class:`DashboardSelection`.  It records which screen is
visible, whether the user is browsing the latest data or replaying a historical
session, the selected session date, whether a replayed outcome has been
revealed, and the selected industry/member and evaluation run.  The session
window is *derived* from the loaded session dates so the selection object stays
small and JSON serialisable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import date as date_type
from datetime import datetime
from enum import Enum
from typing import Any

#: The four dashboard screens.  Values are lower-case, stable identifiers.
SCREENS: tuple[str, ...] = ("overview", "topology", "validation", "data")

#: Replay reveals a future outcome only when explicitly requested.
MODES: tuple[str, ...] = ("live", "replay")

DASHBOARD_SCREENS = SCREENS
DASHBOARD_MODES = MODES
SCREEN_NAMES = SCREENS
MODE_NAMES = MODES
LIVE_MODE = MODES[0]
REPLAY_MODE = MODES[1]
LATEST_MODE = MODES[0]
BROWSE_MODE = MODES[0]

DEFAULT_SCREEN = SCREENS[0]
DEFAULT_MODE = MODES[0]

#: A topology/industry dashboard window is the trailing 60 sessions.
DEFAULT_WINDOW_SESSIONS = 60
WINDOW_SESSIONS = DEFAULT_WINDOW_SESSIONS
WINDOW_SIZE = DEFAULT_WINDOW_SESSIONS
DEFAULT_WINDOW = DEFAULT_WINDOW_SESSIONS

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# ``live`` is the canonical spelling, but older shells and the issue text use
# several equivalent names.  The alias string keeps comparisons friendly while
# still serialising to a plain string.
_LIVE_ALIASES = frozenset({"live", "latest", "current", "browse", "explore", "observe"})
_REPLAY_ALIASES = frozenset({"replay", "historical", "history", "playback"})
_MODE_ALIASES = {
    **{name: "live" for name in _LIVE_ALIASES},
    **{name: "replay" for name in _REPLAY_ALIASES},
}

_SCREEN_ALIASES = {
    "overview": "overview",
    "overview_screen": "overview",
    "data": "data",
    "data_status": "data",
    "data_screen": "data",
    "status": "overview",
    "markets": "topology",
    "market": "topology",
    "market_screen": "topology",
    "topology": "topology",
    "tda": "topology",
    "topology_screen": "topology",
    "evaluation": "validation",
    "evaluate": "validation",
    "alerts": "validation",
    "validation": "validation",
    "validation_screen": "validation",
    "evaluation_screen": "validation",
}


class DashboardSelectionError(ValueError):
    """Raised when a dashboard selection or keyboard action is invalid."""


#: Compatibility aliases used by callers that prefer shorter names.
SelectionError = DashboardSelectionError
DashboardError = DashboardSelectionError


class UnknownFieldError(DashboardSelectionError, TypeError):
    """Raised when an unknown field is passed to :class:`DashboardSelection`."""


class DashboardActionError(DashboardSelectionError):
    """Raised when a keyboard action is not recognised."""


ActionError = DashboardActionError


class _AliasString(str):
    """A string that compares equal to its documented aliases.

    The canonical value is what is stored and serialised.  Alias equality only
    makes the public API forgiving when a caller uses ``latest`` instead of
    ``live`` (or vice versa).
    """

    _aliases: frozenset[str] = frozenset()

    def __new__(cls, value: str, aliases: Iterable[str] = ()) -> _AliasString:
        instance = super().__new__(cls, value)
        instance._aliases = frozenset(str(alias) for alias in aliases)
        return instance

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            if str.__eq__(self, other) is True:
                return True
            candidate = str(other).casefold()
            if candidate == str(self).casefold():
                return True
            return any(candidate == alias.casefold() for alias in self._aliases)
        return NotImplemented

    def __hash__(self) -> int:
        return str.__hash__(self)

    def __reduce__(self) -> tuple[Any, tuple[str, frozenset[str]]]:
        return (type(self), (str(self), self._aliases))


def _live_mode() -> _AliasString:
    return _AliasString("live", _LIVE_ALIASES)


def _replay_mode() -> _AliasString:
    return _AliasString("replay", _REPLAY_ALIASES)


def _normalise_screen(value: Any) -> _AliasString:
    if not isinstance(value, str) or not value.strip():
        raise DashboardSelectionError(f"screen must be a non-empty string, got {value!r}")
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    try:
        canonical = _SCREEN_ALIASES[key]
    except KeyError:
        expected = ", ".join(SCREENS)
        raise DashboardSelectionError(
            f"Unknown dashboard screen {value!r}; expected one of: {expected}"
        ) from None
    aliases = {alias for alias, target in _SCREEN_ALIASES.items() if target == canonical}
    aliases.update({canonical.title(), canonical.upper(), canonical.capitalize()})
    aliases.add(value.strip())
    return _AliasString(canonical, aliases)


def _normalise_mode(value: Any) -> _AliasString:
    if not isinstance(value, str) or not value.strip():
        raise DashboardSelectionError(f"mode must be a non-empty string, got {value!r}")
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    try:
        canonical = _MODE_ALIASES[key]
    except KeyError:
        expected = ", ".join(MODES)
        raise DashboardSelectionError(
            f"Unknown dashboard mode {value!r}; expected one of: {expected}"
        ) from None
    return _replay_mode() if canonical == "replay" else _live_mode()


def _normalise_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date_type):
        return value.isoformat()
    text = str(value).strip()
    if not _DATE_RE.fullmatch(text):
        raise DashboardSelectionError(f"date must be an ISO YYYY-MM-DD value, got {value!r}")
    try:
        date_type.fromisoformat(text)
    except ValueError as exc:
        raise DashboardSelectionError(f"invalid calendar date {value!r}: {exc}") from None
    return text


def _normalise_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise DashboardSelectionError(f"{name} must be a boolean, got {value!r}")


def _normalise_optional_text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise DashboardSelectionError(f"{name} must be a non-empty string or None")
        return text
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise DashboardSelectionError(f"{name} must be a string or None, got {value!r}")


def _normalise_session_dates(values: Iterable[Any] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise DashboardSelectionError("session_dates must be a sequence of dates, not a string")
    result: list[str] = []
    for value in values:
        normalised = _normalise_date(value)
        if normalised is None:
            raise DashboardSelectionError("session_dates must not contain empty values")
        result.append(normalised)
    # Loaded sessions are a chronological series.  Callers may hold them in a
    # mapping or other unspecified order, so normalise once here instead of
    # letting a "trailing" window or keyboard step follow the input order.
    result.sort()
    if len(set(result)) != len(result):
        raise DashboardSelectionError("session_dates must contain unique dates")
    return tuple(result)


def _normalise_items(values: Iterable[Any] | None, name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise DashboardSelectionError(f"{name} must be a sequence, not a string")
    result: list[str] = []
    for value in values:
        normalised = _normalise_optional_text(name, value)
        if normalised is not None:
            result.append(normalised)
    return tuple(result)


def _window_size(value: Any) -> int:
    if value is None:
        return DEFAULT_WINDOW_SESSIONS
    if isinstance(value, bool) or not isinstance(value, int):
        raise DashboardSelectionError(f"window size must be a positive integer, got {value!r}")
    if value <= 0:
        raise DashboardSelectionError(f"window size must be positive, got {value!r}")
    return value


class _WindowView(tuple[str, ...]):
    """A tuple of session dates that can also be re-derived on demand.

    ``selection.window`` behaves like the derived tuple, while
    ``selection.window(session_dates, 20)`` returns the window for another
    loaded session list.  Supporting both access styles keeps the model
    convenient for renderers and tests without storing duplicate state.
    """

    def __new__(
        cls,
        values: Iterable[str],
        selection: DashboardSelection | None = None,
    ) -> _WindowView:
        instance = super().__new__(cls, tuple(values))
        instance._selection = selection
        return instance

    def __call__(
        self,
        session_dates: Iterable[Any] | None = None,
        size: int | None = None,
        **kwargs: Any,
    ) -> _WindowView:
        for key in ("window_size", "window_sessions", "sessions", "dates"):
            if key in kwargs:
                if key in {"sessions", "dates"} and session_dates is None:
                    session_dates = kwargs.pop(key)
                else:
                    size = kwargs.pop(key)
        if kwargs:
            names = ", ".join(sorted(kwargs))
            raise TypeError(f"unknown window argument(s): {names}")
        selection = self._selection
        if selection is None:
            dates = _normalise_session_dates(session_dates)
            return _WindowView(derive_window(dates, None, size=size))
        return _WindowView(selection.window_for(session_dates, size=size))


@dataclass(frozen=True)
class _LoadedContext:
    """Private loaded data retained for a selection.

    The public selection fields can be copied with :func:`dataclasses.replace`;
    carrying the context in a real field lets that helper preserve it too.
    ``source_date``/``source_mode`` let the constructor notice a session or mode
    change and clear the replay reveal state.
    """

    session_dates: tuple[str, ...] = ()
    members: tuple[str, ...] = ()
    runs: tuple[str, ...] = ()
    window_size: int = DEFAULT_WINDOW_SESSIONS
    sessions_supplied: bool = False
    members_supplied: bool = False
    runs_supplied: bool = False
    source_date: str | None = None
    source_mode: str = "live"


# ``DashboardSelection`` is declared before ``_WindowView`` is used at runtime;
# the annotation is a string so the class does not need to exist yet.
def _freeze_private(
    selection: DashboardSelection,
    *,
    sessions: tuple[str, ...],
    members: tuple[str, ...],
    runs: tuple[str, ...],
    window_size: int,
    sessions_supplied: bool,
    members_supplied: bool,
    runs_supplied: bool,
    context: _LoadedContext,
) -> None:
    object.__setattr__(selection, "_session_dates", sessions)
    object.__setattr__(selection, "_members", members)
    object.__setattr__(selection, "_runs", runs)
    object.__setattr__(selection, "_window_size", window_size)
    object.__setattr__(selection, "_sessions_supplied", sessions_supplied)
    object.__setattr__(selection, "_members_supplied", members_supplied)
    object.__setattr__(selection, "_runs_supplied", runs_supplied)
    object.__setattr__(selection, "_loaded", context)


_UNSET: Any = object()


@dataclass(frozen=True, init=False)
class DashboardSelection:
    """Immutable dashboard state for one visible screen.

    ``window`` is not a field: it is derived from ``date`` and the loaded
    session dates.  This keeps the serialised state stable even when a new
    snapshot adds sessions.
    """

    screen: str = DEFAULT_SCREEN
    mode: _AliasString = _live_mode()
    date: str | None = None
    reveal: bool = False
    member: str | None = None
    run: str | None = None
    # Private loaded context.  It is a dataclass field (compare=False) so the
    # standard-library ``dataclasses.replace`` copies it instead of dropping it.
    _loaded: _LoadedContext | None = field(default=None, repr=False, compare=False)

    def __init__(
        self,
        screen: Any = _UNSET,
        mode: Any = _UNSET,
        date: Any = _UNSET,
        reveal: Any = _UNSET,
        member: str | None = _UNSET,
        run: str | None = _UNSET,
        *args: Any,
        **unknown: Any,
    ) -> None:
        if args:
            raise TypeError(
                "DashboardSelection accepts at most six positional arguments "
                "(screen, mode, date, reveal, member, run)"
            )

        values: dict[str, Any] = {
            "screen": DEFAULT_SCREEN if screen is _UNSET else screen,
            "mode": _live_mode() if mode is _UNSET else mode,
            "date": None if date is _UNSET else date,
            "reveal": False if reveal is _UNSET else reveal,
            "member": None if member is _UNSET else member,
            "run": None if run is _UNSET else run,
        }

        loaded = unknown.pop("_loaded", None)
        if isinstance(loaded, Mapping):
            loaded = _LoadedContext(
                session_dates=_normalise_session_dates(loaded.get("session_dates")),
                members=_normalise_items(loaded.get("members"), "members"),
                runs=_normalise_items(loaded.get("runs"), "runs"),
                window_size=_window_size(loaded.get("window_size")),
                sessions_supplied=bool(loaded.get("session_dates") is not None),
                members_supplied=bool(loaded.get("members") is not None),
                runs_supplied=bool(loaded.get("runs") is not None),
                source_date=_normalise_date(loaded.get("source_date")),
                source_mode=str(loaded.get("source_mode", DEFAULT_MODE)),
            )
        elif loaded is not None and not isinstance(loaded, _LoadedContext):
            raise UnknownFieldError(f"invalid loaded context for DashboardSelection: {loaded!r}")

        sessions = _UNSET
        members = _UNSET
        runs = _UNSET
        window_size: Any = _UNSET
        blind_values: list[Any] = []

        aliases = {
            "selected_screen": "screen",
            "current_screen": "screen",
            "view": "screen",
            "page": "screen",
            "screen_name": "screen",
            "selected_mode": "mode",
            "selection_mode": "mode",
            "selected_date": "date",
            "session": "date",
            "session_date": "date",
            "selected_session": "date",
            "as_of": "date",
            "as_of_date": "date",
            "selected_member": "member",
            "industry": "member",
            "industry_member": "member",
            "node": "member",
            "selected_run": "run",
            "run_id": "run",
            "evaluation_run": "run",
            "show_reveal": "reveal",
            "is_revealed": "reveal",
            "revealed": "reveal",
            "sessions": "sessions",
            "session_dates": "sessions",
            "dates": "sessions",
            "members": "members",
            "industries": "members",
            "runs": "runs",
            "run_ids": "runs",
            "window_size": "window_size",
            "window_sessions": "window_size",
            "window": "window_size",
        }

        for key, value in unknown.items():
            lowered = key.strip().lower().replace("-", "_").replace(" ", "_")
            if lowered == "blind":
                blind_values.append(value)
                continue
            target = aliases.get(lowered)
            if target is None:
                # Reject unknown/misspelled fields.  Inferring a target from
                # substrings used to turn e.g. ``misspelled_reveal`` into a
                # real state change, which hid user mistakes.
                names = ", ".join(sorted(unknown))
                raise UnknownFieldError(f"unknown field(s) for DashboardSelection: {names}")
            if target == "sessions":
                sessions = value
            elif target == "members":
                members = value
            elif target == "runs":
                runs = value
            elif target == "window_size":
                window_size = value
            else:
                values[target] = value

        sessions_supplied = sessions is not _UNSET or bool(
            loaded is not None and loaded.sessions_supplied
        )
        members_supplied = members is not _UNSET or bool(
            loaded is not None and loaded.members_supplied
        )
        runs_supplied = runs is not _UNSET or bool(loaded is not None and loaded.runs_supplied)
        if sessions is _UNSET and loaded is not None and loaded.sessions_supplied:
            sessions = loaded.session_dates
        if members is _UNSET and loaded is not None and loaded.members_supplied:
            members = loaded.members
        if runs is _UNSET and loaded is not None and loaded.runs_supplied:
            runs = loaded.runs
        if window_size is _UNSET and loaded is not None:
            window_size = loaded.window_size

        screen_value = _normalise_screen(values["screen"])
        mode_value = _normalise_mode(values["mode"])
        date_value = _normalise_date(values["date"])
        reveal_value = _normalise_bool("reveal", values["reveal"])
        member_value = _normalise_optional_text("member", values["member"])
        run_value = _normalise_optional_text("run", values["run"])

        if blind_values:
            blind = _normalise_bool("blind", blind_values[-1])
            reveal_value = not blind

        session_values = () if sessions is _UNSET else _normalise_session_dates(sessions)
        member_values = () if members is _UNSET else _normalise_items(members, "members")
        run_values = () if runs is _UNSET else _normalise_items(runs, "runs")
        size_value = DEFAULT_WINDOW_SESSIONS if window_size is _UNSET else _window_size(window_size)

        if date_value is None and session_values:
            date_value = session_values[-1]

        # A supported session/mode change always clears the future-outcome
        # reveal state, even when the caller also passed ``reveal=True``.
        if loaded is not None:
            session_changed = date_value != loaded.source_date
            mode_left_replay = mode_value != loaded.source_mode and mode_value != "replay"
            if session_changed or mode_left_replay:
                reveal_value = False

        object.__setattr__(self, "screen", screen_value)
        object.__setattr__(self, "mode", mode_value)
        object.__setattr__(self, "date", date_value)
        object.__setattr__(self, "reveal", reveal_value)
        object.__setattr__(self, "member", member_value)
        object.__setattr__(self, "run", run_value)
        context = _LoadedContext(
            session_dates=session_values,
            members=member_values,
            runs=run_values,
            window_size=size_value,
            sessions_supplied=sessions_supplied,
            members_supplied=members_supplied,
            runs_supplied=runs_supplied,
            source_date=date_value,
            source_mode=str(mode_value),
        )
        _freeze_private(
            self,
            sessions=session_values,
            members=member_values,
            runs=run_values,
            window_size=size_value,
            sessions_supplied=sessions_supplied,
            members_supplied=members_supplied,
            runs_supplied=runs_supplied,
            context=context,
        )
        self.__post_init__()

    def __post_init__(self) -> None:
        if self.reveal and self.mode != "replay":
            raise DashboardSelectionError(
                f"reveal is only available in replay mode; got mode={self.mode!r}, reveal=True"
            )
        session_dates = getattr(self, "_session_dates", ())
        if (
            self.date is not None
            and getattr(self, "_sessions_supplied", False)
            and self.date not in session_dates
        ):
            raise DashboardSelectionError(
                f"Unknown session date {self.date!r}; not present in the loaded sessions"
            )
        member_values = getattr(self, "_members", ())
        if (
            self.member is not None
            and getattr(self, "_members_supplied", False)
            and self.member not in member_values
        ):
            raise DashboardSelectionError(
                f"Unknown dashboard member {self.member!r}; "
                f"expected one of: {', '.join(member_values)}"
            )
        run_values = getattr(self, "_runs", ())
        if (
            self.run is not None
            and getattr(self, "_runs_supplied", False)
            and self.run not in run_values
        ):
            raise DashboardSelectionError(
                f"Unknown evaluation run {self.run!r}; expected one of: {', '.join(run_values)}"
            )

    # ------------------------------------------------------------------
    # Public views of the selection
    # ------------------------------------------------------------------
    @property
    def blind(self) -> bool:
        """``True`` while a replay outcome is hidden."""

        return not self.reveal

    @property
    def is_replay(self) -> bool:
        return self.mode == "replay"

    @property
    def is_live(self) -> bool:
        return not self.is_replay

    @property
    def revealed(self) -> bool:
        return self.reveal

    @property
    def is_revealed(self) -> bool:
        return self.reveal

    @property
    def is_blind(self) -> bool:
        return self.blind

    @property
    def selected_screen(self) -> str:
        return self.screen

    @property
    def current_screen(self) -> str:
        return self.screen

    @property
    def selected_mode(self) -> str:
        return self.mode

    @property
    def selected_date(self) -> str | None:
        return self.date

    @property
    def session_date(self) -> str | None:
        return self.date

    @property
    def as_of(self) -> str | None:
        return self.date

    @property
    def selected_member(self) -> str | None:
        return self.member

    @property
    def industry(self) -> str | None:
        return self.member

    @property
    def selected_run(self) -> str | None:
        return self.run

    @property
    def run_id(self) -> str | None:
        return self.run

    @property
    def session_dates(self) -> tuple[str, ...]:
        return getattr(self, "_session_dates", ())

    @property
    def sessions(self) -> tuple[str, ...]:
        return self.session_dates

    @property
    def members(self) -> tuple[str, ...]:
        return getattr(self, "_members", ())

    @property
    def runs(self) -> tuple[str, ...]:
        return getattr(self, "_runs", ())

    @property
    def window_size(self) -> int:
        return getattr(self, "_window_size", DEFAULT_WINDOW_SESSIONS)

    @property
    def session_index(self) -> int | None:
        if not self.session_dates:
            return None
        if self.date is None:
            return len(self.session_dates) - 1
        try:
            return self.session_dates.index(self.date)
        except ValueError:
            return None

    @property
    def window(self) -> _WindowView:
        """The trailing session window ending at :attr:`date`."""

        values = derive_window(self.session_dates, self.date, size=self.window_size)
        return _WindowView(values, self)

    @property
    def window_dates(self) -> tuple[str, ...]:
        return tuple(self.window)

    @property
    def session_window(self) -> tuple[str, ...]:
        return tuple(self.window)

    @property
    def window_start(self) -> str | None:
        return self.window[0] if self.window else None

    @property
    def window_end(self) -> str | None:
        return self.window[-1] if self.window else None

    @property
    def window_sessions(self) -> int:
        return len(self.window)

    def window_for(
        self,
        session_dates: Iterable[Any] | None = None,
        size: int | None = None,
        **kwargs: Any,
    ) -> tuple[str, ...]:
        """Derive the window for ``session_dates`` (defaults to loaded dates)."""

        for key in ("sessions", "dates"):
            if key in kwargs and session_dates is None:
                session_dates = kwargs.pop(key)
        for key in ("window_size", "window_sessions"):
            if key in kwargs:
                size = kwargs.pop(key)
        if kwargs:
            names = ", ".join(sorted(kwargs))
            raise TypeError(f"unknown window argument(s): {names}")
        dates = (
            self.session_dates if session_dates is None else _normalise_session_dates(session_dates)
        )
        return derive_window(dates, self.date, size=self.window_size if size is None else size)

    # ------------------------------------------------------------------
    # Serialisation and immutable updates
    # ------------------------------------------------------------------
    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls) if not field.name.startswith("_"))

    def to_dict(self, *, include_context: bool = True) -> dict[str, Any]:
        """Return a JSON-serialisable mapping of the selection.

        The six public fields are always included.  With ``include_context``
        (the default) the loaded session dates, members, runs and non-default
        window size are included too, so a restored selection can derive its
        window and step without the caller having to reattach data.  Use
        ``include_context=False`` for a minimal presentation payload.
        """

        payload: dict[str, Any] = {
            "screen": self.screen,
            "mode": self.mode,
            "date": self.date,
            "reveal": self.reveal,
            "member": self.member,
            "run": self.run,
        }
        if include_context:
            payload["window_size"] = self.window_size
            # Omitted collections are not serialised as empty ones: an
            # explicitly empty collection means "nothing is loaded" and must
            # stay distinguishable from "no collection supplied".
            if getattr(self, "_sessions_supplied", False):
                payload["session_dates"] = list(self.session_dates)
            if getattr(self, "_members_supplied", False):
                payload["members"] = list(self.members)
            if getattr(self, "_runs_supplied", False):
                payload["runs"] = list(self.runs)
        return payload

    as_dict = to_dict
    as_mapping = to_dict
    to_mapping = to_dict
    serialize = to_dict

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, **kwargs)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DashboardSelection:
        if not isinstance(data, Mapping):
            raise DashboardSelectionError(
                f"DashboardSelection.from_dict expects a mapping, got {type(data).__name__}"
            )
        payload = dict(data)
        nested = payload.pop("context", None)
        if nested is None:
            nested = payload.pop("_loaded", None)
        if nested is not None:
            if not isinstance(nested, Mapping):
                raise DashboardSelectionError("selection context must be a mapping")
            context = dict(nested)
            supplied_flags = {
                "session_dates": "sessions_supplied",
                "members": "members_supplied",
                "runs": "runs_supplied",
            }
            for key, flag in supplied_flags.items():
                if key in context and context.get(flag, True) and key not in payload:
                    payload[key] = context[key]
            if "window_size" in context and "window_size" not in payload:
                payload["window_size"] = context["window_size"]
        return cls(**payload)

    def attach_context(
        self,
        *,
        session_dates: Iterable[Any] | None = None,
        members: Iterable[Any] | None = None,
        runs: Iterable[Any] | None = None,
        window_size: int | None = None,
    ) -> DashboardSelection:
        """Return a copy with loaded data reattached after deserialisation.

        Pass ``[]`` explicitly to mark a collection as loaded-but-empty; the
        resulting selection rejects a date/member/run that is absent from it.
        """

        changes: dict[str, Any] = {}
        if session_dates is not None:
            changes["session_dates"] = session_dates
        if members is not None:
            changes["members"] = members
        if runs is not None:
            changes["runs"] = runs
        if window_size is not None:
            changes["window_size"] = window_size
        return self.replace(**changes)

    with_loaded_context = attach_context

    from_mapping = from_dict
    from_state = from_dict
    deserialize = from_dict

    @classmethod
    def from_json(cls, payload: str) -> DashboardSelection:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise DashboardSelectionError(f"invalid selection JSON: {exc}") from None
        if not isinstance(data, Mapping):
            raise DashboardSelectionError("selection JSON must contain an object")
        return cls.from_dict(data)

    def replace(self, **changes: Any) -> DashboardSelection:
        """Return a copy with ``changes`` applied.

        Private loaded dates/members/runs and ``window_size`` are preserved.
        Changing the selected session (or leaving replay mode) always clears
        the replay reveal state, even when the caller also passes
        ``reveal=True``.  Unknown field names are rejected by the constructor.
        """

        payload = self.to_dict(include_context=False)
        context_changes: dict[str, Any] = {}
        if "sessions" in changes or "session_dates" in changes:
            context_changes["session_dates"] = _normalise_session_dates(
                changes.pop("sessions", changes.pop("session_dates", self.session_dates))
            )
        if "members" in changes:
            context_changes["members"] = _normalise_items(changes.pop("members"), "members")
        if "runs" in changes:
            context_changes["runs"] = _normalise_items(changes.pop("runs"), "runs")
        if "window_size" in changes:
            context_changes["window_size"] = _window_size(changes.pop("window_size"))
        payload.update(changes)
        return type(self)(**payload, _loaded=self._loaded, **context_changes)

    update = replace

    def with_screen(self, screen: str) -> DashboardSelection:
        return self.replace(screen=screen)

    def with_mode(self, mode: str) -> DashboardSelection:
        changes: dict[str, Any] = {"mode": mode}
        if _normalise_mode(mode) != "replay":
            changes["reveal"] = False
        return self.replace(**changes)

    def with_date(self, date: Any) -> DashboardSelection:
        normalised = _normalise_date(date)
        changes: dict[str, Any] = {"date": normalised}
        if normalised != self.date:
            changes["reveal"] = False
        return self.replace(**changes)

    select_session = with_date
    with_session = with_date

    def with_member(self, member: str | None) -> DashboardSelection:
        return self.replace(member=member)

    select_member = with_member

    def with_run(self, run: str | None) -> DashboardSelection:
        return self.replace(run=run)

    select_run = with_run

    def with_reveal(self, reveal: bool = True) -> DashboardSelection:
        return self.replace(reveal=_normalise_bool("reveal", reveal))

    def validate(
        self,
        session_dates: Iterable[Any] | None = None,
        *,
        members: Iterable[Any] | None = None,
        runs: Iterable[Any] | None = None,
        **kwargs: Any,
    ) -> DashboardSelection:
        """Validate the selection against loaded dates/members/runs.

        The method returns ``self`` so callers can chain it; it raises
        :class:`DashboardSelectionError` for an unknown selection.
        """

        for key in ("sessions", "dates"):
            if key in kwargs and session_dates is None:
                session_dates = kwargs.pop(key)
        for key in ("industries", "member_ids"):
            if key in kwargs and members is None:
                members = kwargs.pop(key)
        for key in ("run_ids", "evaluation_runs"):
            if key in kwargs and runs is None:
                runs = kwargs.pop(key)
        if kwargs:
            names = ", ".join(sorted(kwargs))
            raise TypeError(f"unknown validation argument(s): {names}")

        dates = (
            self.session_dates if session_dates is None else _normalise_session_dates(session_dates)
        )
        sessions_available = session_dates is not None or getattr(self, "_sessions_supplied", False)
        if self.date is not None and sessions_available and self.date not in dates:
            raise DashboardSelectionError(
                f"Unknown session date {self.date!r}; not present in the loaded sessions"
            )

        if members is None:
            member_values = self.members
            members_available = getattr(self, "_members_supplied", False)
        else:
            member_values = _normalise_items(members, "members")
            members_available = True
        if self.member is not None and members_available and self.member not in member_values:
            raise DashboardSelectionError(
                f"Unknown dashboard member {self.member!r}; "
                f"expected one of: {', '.join(member_values)}"
            )

        if runs is None:
            run_values = self.runs
            runs_available = getattr(self, "_runs_supplied", False)
        else:
            run_values = _normalise_items(runs, "runs")
            runs_available = True
        if self.run is not None and runs_available and self.run not in run_values:
            raise DashboardSelectionError(
                f"Unknown evaluation run {self.run!r}; expected one of: {', '.join(run_values)}"
            )
        return self


#: Friendly aliases for embedders and tests.
DashboardState = DashboardSelection
Selection = DashboardSelection
SelectionState = DashboardSelection


def derive_window(
    session_dates: Iterable[Any],
    date: Any = None,
    size: int | None = None,
    **kwargs: Any,
) -> tuple[str, ...]:
    """Return the trailing ``size`` sessions ending on ``date``.

    ``date`` defaults to the newest loaded session.  A date that is not in the
    loaded sessions is an unknown selection and raises
    :class:`DashboardSelectionError`.
    """

    for key in ("window_size", "window_sessions"):
        if key in kwargs:
            size = kwargs.pop(key)
    if "sessions" in kwargs:
        session_dates = kwargs.pop("sessions")
    if kwargs:
        names = ", ".join(sorted(kwargs))
        raise TypeError(f"unknown window argument(s): {names}")

    dates = _normalise_session_dates(session_dates)
    if not dates:
        return ()
    selected = _normalise_date(date)
    if selected is None:
        index = len(dates) - 1
    else:
        try:
            index = dates.index(selected)
        except ValueError:
            raise DashboardSelectionError(
                f"Unknown session date {selected!r}; not present in the loaded sessions"
            ) from None
    width = _window_size(size)
    start = max(0, index - width + 1)
    return dates[start : index + 1]


def window_for_selection(
    selection: DashboardSelection,
    session_dates: Iterable[Any] | None = None,
    size: int | None = None,
    **kwargs: Any,
) -> tuple[str, ...]:
    """Compatibility helper returning ``selection.window_for(...)``."""

    return selection.window_for(session_dates, size=size, **kwargs)


# ---------------------------------------------------------------------------
# Keyboard actions
# ---------------------------------------------------------------------------
class DashboardScreen(str, Enum):
    """Enumeration form of :data:`SCREENS` for embedders that prefer enums."""

    OVERVIEW = "overview"
    TOPOLOGY = "topology"
    VALIDATION = "validation"
    DATA = "data"


Screen = DashboardScreen


class DashboardMode(str, Enum):
    """Enumeration form of :data:`MODES`."""

    LIVE = "live"
    REPLAY = "replay"


Mode = DashboardMode


class KeyboardAction(str, Enum):
    """Stable keyboard action identifiers used by the dashboard shell."""

    NEXT_SESSION = "next_session"
    PREVIOUS_SESSION = "previous_session"
    NEXT_WINDOW = "next_window"
    PREVIOUS_WINDOW = "previous_window"
    NEXT_MEMBER = "next_member"
    PREVIOUS_MEMBER = "previous_member"
    TOGGLE_REVEAL = "toggle_reveal"
    TOGGLE_BLIND = "toggle_blind"


#: Short aliases, including the arrow/page/Vim keys the shell may forward.
KEY_BINDINGS: dict[str, str] = {
    "arrowright": "next_session",
    "right": "next_session",
    "l": "next_session",
    "j": "next_session",
    "down": "next_session",
    "arrowleft": "previous_session",
    "left": "previous_session",
    "h": "previous_session",
    "k": "previous_session",
    "up": "previous_session",
    "pagedown": "next_window",
    "page_down": "next_window",
    "]": "next_window",
    "next": "next_session",
    "pageup": "previous_window",
    "page_up": "previous_window",
    "[": "previous_window",
    "previous": "previous_session",
    "prior": "previous_window",
    "nextmember": "next_member",
    "next_member": "next_member",
    "member_next": "next_member",
    "membernext": "next_member",
    "m": "next_member",
    "previousmember": "previous_member",
    "previous_member": "previous_member",
    "prev_member": "previous_member",
    "prevmember": "previous_member",
    "member_previous": "previous_member",
    "shift+m": "previous_member",
    "r": "toggle_reveal",
    "toggle_reveal": "toggle_reveal",
    "reveal": "toggle_reveal",
    "b": "toggle_blind",
    "toggle_blind": "toggle_blind",
    "blind": "toggle_blind",
}

_ACTION_ALIASES: dict[str, str] = {
    **KEY_BINDINGS,
    "next_session": "next_session",
    "nextsession": "next_session",
    "session_next": "next_session",
    "sessionnext": "next_session",
    "step_session_forward": "next_session",
    "step_session": "next_session",
    "session_forward": "next_session",
    "next_date": "next_session",
    "date_next": "next_session",
    "next_day": "next_session",
    "day_next": "next_session",
    "next_session_action": "next_session",
    "previous_session": "previous_session",
    "previoussession": "previous_session",
    "prev_session": "previous_session",
    "prevsession": "previous_session",
    "session_previous": "previous_session",
    "session_prev": "previous_session",
    "step_session_back": "previous_session",
    "session_back": "previous_session",
    "previous_date": "previous_session",
    "date_previous": "previous_session",
    "prev_date": "previous_session",
    "date_prev": "previous_session",
    "previous_day": "previous_session",
    "day_previous": "previous_session",
    "previous_session_action": "previous_session",
    "next_window": "next_window",
    "nextwindow": "next_window",
    "window_next": "next_window",
    "windownext": "next_window",
    "step_window_forward": "next_window",
    "step_window": "next_window",
    "window_forward": "next_window",
    "previous_window": "previous_window",
    "previouswindow": "previous_window",
    "prev_window": "previous_window",
    "prevwindow": "previous_window",
    "window_previous": "previous_window",
    "window_prev": "previous_window",
    "step_window_back": "previous_window",
    "window_back": "previous_window",
    "next_member": "next_member",
    "nextmember": "next_member",
    "member_next": "next_member",
    "membernext": "next_member",
    "step_member_forward": "next_member",
    "step_member": "next_member",
    "previous_member": "previous_member",
    "previousmember": "previous_member",
    "prev_member": "previous_member",
    "prevmember": "previous_member",
    "member_previous": "previous_member",
    "member_prev": "previous_member",
    "step_member_back": "previous_member",
    "toggle_reveal": "toggle_reveal",
    "togglereveal": "toggle_reveal",
    "reveal_toggle": "toggle_reveal",
    "show_reveal": "toggle_reveal",
    "toggle_blind": "toggle_blind",
    "toggleblind": "toggle_blind",
    "blind_toggle": "toggle_blind",
    "hide_outcome": "toggle_blind",
}

ACTION_NEXT_SESSION = KeyboardAction.NEXT_SESSION.value
ACTION_PREVIOUS_SESSION = KeyboardAction.PREVIOUS_SESSION.value
ACTION_NEXT_WINDOW = KeyboardAction.NEXT_WINDOW.value
ACTION_PREVIOUS_WINDOW = KeyboardAction.PREVIOUS_WINDOW.value
ACTION_NEXT_MEMBER = KeyboardAction.NEXT_MEMBER.value
ACTION_PREVIOUS_MEMBER = KeyboardAction.PREVIOUS_MEMBER.value
ACTION_TOGGLE_REVEAL = KeyboardAction.TOGGLE_REVEAL.value
ACTION_TOGGLE_BLIND = KeyboardAction.TOGGLE_BLIND.value

#: Public list of action names accepted by :func:`apply_keyboard_action`.
KEYBOARD_ACTIONS: tuple[str, ...] = tuple(action.value for action in KeyboardAction)
ACTIONS = KEYBOARD_ACTIONS


def normalise_action(action: Any) -> str:
    """Return the canonical action name for ``action``."""

    if isinstance(action, KeyboardAction):
        return action.value
    if isinstance(action, Enum):
        action = action.value
    if not isinstance(action, str) or not action.strip():
        raise DashboardActionError(f"Unknown keyboard action: {action!r}")
    key = (
        action.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace(".", "_")
        .replace(":", "_")
    )
    key = key[4:] if key.startswith("key_") else key
    canonical = _ACTION_ALIASES.get(key)
    if canonical is None:
        raise DashboardActionError(f"Unknown keyboard action: {action!r}")
    return canonical


def _resolve_action_inputs(
    args: Sequence[Any],
    kwargs: dict[str, Any],
) -> tuple[
    tuple[str, ...] | None,
    tuple[str, ...] | None,
    tuple[str, ...] | None,
    int | None,
]:
    for key in ("sessions", "session_dates", "dates"):
        if key in kwargs:
            kwargs.setdefault("_sessions", kwargs.pop(key))
    for key in ("members", "industries", "member_ids"):
        if key in kwargs:
            kwargs.setdefault("_members", kwargs.pop(key))
    for key in ("runs", "run_ids"):
        if key in kwargs:
            kwargs.setdefault("_runs", kwargs.pop(key))
    for key in ("window_size", "window_sessions", "size"):
        if key in kwargs:
            kwargs.setdefault("_window_size", kwargs.pop(key))

    sessions = kwargs.pop("_sessions", None)
    members = kwargs.pop("_members", None)
    runs = kwargs.pop("_runs", None)
    size = kwargs.pop("_window_size", None)

    positional = list(args)
    if positional:
        if sessions is None:
            sessions = positional.pop(0)
        else:
            positional.pop(0)
    if positional:
        if members is None:
            members = positional.pop(0)
        else:
            positional.pop(0)
    if positional:
        if runs is None:
            runs = positional.pop(0)
        else:
            positional.pop(0)
    if positional:
        if size is None:
            size = positional.pop(0)
        else:
            positional.pop(0)
    if positional:
        raise TypeError("too many positional arguments for apply_keyboard_action")
    if kwargs:
        names = ", ".join(sorted(kwargs))
        raise TypeError(f"unknown keyboard argument(s): {names}")

    session_values = None if sessions is None else _normalise_session_dates(sessions)
    member_values = None if members is None else _normalise_items(members, "members")
    run_values = None if runs is None else _normalise_items(runs, "runs")
    size_value = None if size is None else _window_size(size)
    return session_values, member_values, run_values, size_value


def _selection_for_action(
    selection: DashboardSelection,
    sessions: tuple[str, ...] | None,
) -> tuple[DashboardSelection, tuple[str, ...], int]:
    dates = selection.session_dates if sessions is None else sessions
    if sessions is not None and sessions != selection.session_dates:
        selection = selection.replace(session_dates=sessions)
    if not dates:
        raise DashboardActionError("session actions require loaded session dates")
    index = selection.session_index
    if index is None:
        index = len(dates) - 1
    if selection.date is None:
        selection = selection.replace(date=dates[index])
    return selection, dates, index


def apply_keyboard_action(
    selection: DashboardSelection,
    action: str | KeyboardAction,
    *args: Any,
    **kwargs: Any,
) -> DashboardSelection:
    """Apply a keyboard action and return a new selection.

    Session/window stepping clamps at the loaded boundaries and changing the
    selected session clears ``reveal``.  Unknown actions raise a
    :class:`DashboardActionError` with the offending value in the message.
    """

    if not isinstance(selection, DashboardSelection) and isinstance(action, DashboardSelection):
        selection, action = action, selection
    if not isinstance(selection, DashboardSelection):
        raise TypeError("apply_keyboard_action expects a DashboardSelection")

    canonical = normalise_action(action)
    sessions, members, runs, size = _resolve_action_inputs(args, dict(kwargs))

    if canonical in {
        KeyboardAction.NEXT_SESSION.value,
        KeyboardAction.PREVIOUS_SESSION.value,
        KeyboardAction.NEXT_WINDOW.value,
        KeyboardAction.PREVIOUS_WINDOW.value,
    }:
        current, dates, index = _selection_for_action(selection, sessions)
        is_window_action = canonical in {
            KeyboardAction.NEXT_WINDOW.value,
            KeyboardAction.PREVIOUS_WINDOW.value,
        }
        # Window stepping follows the selection's own window size unless the
        # caller explicitly overrides it.
        step = (size if size is not None else current.window_size) if is_window_action else 1
        if canonical in {
            KeyboardAction.PREVIOUS_SESSION.value,
            KeyboardAction.PREVIOUS_WINDOW.value,
        }:
            step = -step
        new_index = min(max(index + step, 0), len(dates) - 1)
        reveal = False if new_index != index else current.reveal
        return current.replace(date=dates[new_index], reveal=reveal)

    if canonical in {
        KeyboardAction.NEXT_MEMBER.value,
        KeyboardAction.PREVIOUS_MEMBER.value,
    }:
        current = selection
        available_members = tuple(members) if members is not None else current.members
        if not available_members:
            raise DashboardActionError("member actions require loaded members")
        if current.member in available_members:
            index = available_members.index(current.member)
        else:
            index = -1 if canonical == KeyboardAction.NEXT_MEMBER.value else 0
        delta = 1 if canonical == KeyboardAction.NEXT_MEMBER.value else -1
        new_index = min(max(index + delta, 0), len(available_members) - 1)
        payload: dict[str, Any] = {"member": available_members[new_index]}
        if members is not None:
            payload["members"] = members
        if runs is not None:
            payload["runs"] = runs
        return current.replace(**payload)

    if canonical in {
        KeyboardAction.TOGGLE_REVEAL.value,
        KeyboardAction.TOGGLE_BLIND.value,
    }:
        if selection.mode != "replay":
            raise DashboardActionError(
                f"reveal can only be toggled in replay mode; got mode={selection.mode!r}"
            )
        return selection.replace(reveal=not selection.reveal)

    raise DashboardActionError(f"Unknown keyboard action: {action!r}")


#: Alias names used by the app shell and tests.
apply_action = apply_keyboard_action
apply_keyboard = apply_keyboard_action
handle_action = apply_keyboard_action
handle_keyboard_action = apply_keyboard_action
handle_keyboard = apply_keyboard_action
handle_key = apply_keyboard_action
handle_keypress = apply_keyboard_action
handle_key_press = apply_keyboard_action
keyboard_action = apply_keyboard_action
keypress = apply_keyboard_action
on_key = apply_keyboard_action
respond_to_key = apply_keyboard_action
apply_key = apply_keyboard_action
dispatch_keyboard_action = apply_keyboard_action


def next_session(
    selection: DashboardSelection,
    sessions: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    return apply_keyboard_action(
        selection, KeyboardAction.NEXT_SESSION, sessions=sessions, **kwargs
    )


def previous_session(
    selection: DashboardSelection,
    sessions: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    return apply_keyboard_action(
        selection, KeyboardAction.PREVIOUS_SESSION, sessions=sessions, **kwargs
    )


prev_session = previous_session


def next_window(
    selection: DashboardSelection,
    sessions: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    return apply_keyboard_action(selection, KeyboardAction.NEXT_WINDOW, sessions=sessions, **kwargs)


def previous_window(
    selection: DashboardSelection,
    sessions: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    return apply_keyboard_action(
        selection, KeyboardAction.PREVIOUS_WINDOW, sessions=sessions, **kwargs
    )


prev_window = previous_window


def next_member(
    selection: DashboardSelection,
    members: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    return apply_keyboard_action(selection, KeyboardAction.NEXT_MEMBER, members=members, **kwargs)


def previous_member(
    selection: DashboardSelection,
    members: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    return apply_keyboard_action(
        selection, KeyboardAction.PREVIOUS_MEMBER, members=members, **kwargs
    )


prev_member = previous_member


def toggle_reveal(selection: DashboardSelection, **kwargs: Any) -> DashboardSelection:
    return apply_keyboard_action(selection, KeyboardAction.TOGGLE_REVEAL, **kwargs)


def toggle_blind(selection: DashboardSelection, **kwargs: Any) -> DashboardSelection:
    return apply_keyboard_action(selection, KeyboardAction.TOGGLE_BLIND, **kwargs)


toggle = toggle_reveal
toggle_hidden = toggle_blind


def _direction_action(
    direction: Any, forward: KeyboardAction, back: KeyboardAction
) -> KeyboardAction:
    if isinstance(direction, str):
        text = direction.strip().lower()
        if text in {"back", "backward", "previous", "prev", "-", "-1", "left", "up"}:
            return back
        if text in {"forward", "next", "+", "1", "right", "down"}:
            return forward
    if isinstance(direction, (int, float)) and not isinstance(direction, bool):
        return back if direction < 0 else forward
    return forward


def step_session(
    selection: DashboardSelection,
    direction: Any = 1,
    sessions: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    action = _direction_action(
        direction, KeyboardAction.NEXT_SESSION, KeyboardAction.PREVIOUS_SESSION
    )
    return apply_keyboard_action(selection, action, sessions=sessions, **kwargs)


def step_window(
    selection: DashboardSelection,
    direction: Any = 1,
    sessions: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    action = _direction_action(
        direction, KeyboardAction.NEXT_WINDOW, KeyboardAction.PREVIOUS_WINDOW
    )
    return apply_keyboard_action(selection, action, sessions=sessions, **kwargs)


def step_member(
    selection: DashboardSelection,
    direction: Any = 1,
    members: Iterable[Any] | None = None,
    **kwargs: Any,
) -> DashboardSelection:
    action = _direction_action(
        direction, KeyboardAction.NEXT_MEMBER, KeyboardAction.PREVIOUS_MEMBER
    )
    return apply_keyboard_action(selection, action, members=members, **kwargs)


def __getattr__(name: str) -> Any:
    """Expose forgiving aliases for action constants and simple predicates."""

    lowered = name.strip().lower()
    if lowered.endswith("_action"):
        lowered = lowered[: -len("_action")]
    if lowered.startswith("action_"):
        lowered = lowered[len("action_") :]
    try:
        return normalise_action(lowered)
    except DashboardActionError:
        pass
    if lowered in {"dashboardselection", "dashboard_selection"}:
        return DashboardSelection
    if lowered in {"derived_window", "selection_window"}:
        return derive_window
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ACTIONS",
    "ACTION_NEXT_MEMBER",
    "ACTION_NEXT_SESSION",
    "ACTION_NEXT_WINDOW",
    "ACTION_PREVIOUS_MEMBER",
    "ACTION_PREVIOUS_SESSION",
    "ACTION_PREVIOUS_WINDOW",
    "ACTION_TOGGLE_BLIND",
    "ACTION_TOGGLE_REVEAL",
    "DEFAULT_MODE",
    "DEFAULT_SCREEN",
    "DASHBOARD_MODES",
    "DASHBOARD_SCREENS",
    "LATEST_MODE",
    "LIVE_MODE",
    "MODE_NAMES",
    "Mode",
    "REPLAY_MODE",
    "BROWSE_MODE",
    "SCREEN_NAMES",
    "Screen",
    "DEFAULT_WINDOW",
    "DEFAULT_WINDOW_SESSIONS",
    "DashboardActionError",
    "DashboardError",
    "DashboardMode",
    "DashboardScreen",
    "DashboardSelection",
    "DashboardSelectionError",
    "DashboardState",
    "KEYBOARD_ACTIONS",
    "KEY_BINDINGS",
    "KeyboardAction",
    "MODES",
    "SCREENS",
    "Selection",
    "SelectionError",
    "SelectionState",
    "UnknownFieldError",
    "WINDOW_SESSIONS",
    "WINDOW_SIZE",
    "apply_action",
    "apply_key",
    "apply_keyboard",
    "apply_keyboard_action",
    "derive_window",
    "dispatch_keyboard_action",
    "handle_action",
    "handle_key",
    "handle_key_press",
    "handle_keyboard",
    "handle_keyboard_action",
    "handle_keypress",
    "keyboard_action",
    "keypress",
    "next_member",
    "next_session",
    "next_window",
    "normalise_action",
    "normalize_action",
    "on_key",
    "previous_member",
    "previous_session",
    "previous_window",
    "prev_member",
    "prev_session",
    "prev_window",
    "respond_to_key",
    "step_member",
    "step_session",
    "step_window",
    "toggle",
    "toggle_blind",
    "toggle_hidden",
    "toggle_reveal",
    "window_for_selection",
]

normalize_action = normalise_action
