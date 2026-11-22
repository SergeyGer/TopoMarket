"""Focused tests for the pure Step 7 dashboard selection model."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta

import pytest

from topomarket.ui.dashboard import (
    DEFAULT_WINDOW_SESSIONS,
    KEYBOARD_ACTIONS,
    MODES,
    SCREENS,
    DashboardActionError,
    DashboardSelection,
    DashboardSelectionError,
    KeyboardAction,
    UnknownFieldError,
    apply_keyboard_action,
    derive_window,
    next_member,
    next_session,
    next_window,
    previous_member,
    previous_session,
    previous_window,
    toggle_blind,
    toggle_reveal,
)


def _sessions(count: int = 150) -> list[str]:
    start = date(2020, 1, 2)
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def test_selection_is_frozen_and_has_the_documented_fields() -> None:
    selection = DashboardSelection()

    assert selection.screen == "overview"
    assert selection.mode in MODES
    assert selection.date is None
    assert selection.reveal is False
    assert selection.member is None
    assert selection.run is None
    with pytest.raises(FrozenInstanceError):
        selection.screen = "markets"  # type: ignore[misc]


@pytest.mark.parametrize("screen", SCREENS)
@pytest.mark.parametrize("mode", MODES)
def test_selection_accepts_every_screen_and_mode(screen: str, mode: str) -> None:
    selection = DashboardSelection(screen=screen, mode=mode)

    assert selection.screen == screen
    assert selection.mode == mode


def test_selection_accepts_common_screen_and_mode_aliases() -> None:
    selection = DashboardSelection(screen="Topology", mode="latest", date="2024-01-02")

    assert selection.screen == "topology"
    assert selection.mode == "live"
    assert selection.is_live is True
    assert selection.is_replay is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"screen": "mystery"},
        {"screen": ""},
        {"mode": "sideways"},
        {"date": "not-a-date"},
        {"date": "2024-02-30"},
        {"member": ""},
        {"run": ""},
        {"reveal": "yes"},
        {"reveal": True},
        {"mode": "live", "reveal": True},
        {"unknown_field": 1},
    ],
)
def test_selection_rejects_invalid_or_unknown_values(kwargs: dict) -> None:
    with pytest.raises((DashboardSelectionError, TypeError)):
        DashboardSelection(**kwargs)


def test_unknown_field_error_is_both_value_and_type_error() -> None:
    with pytest.raises(UnknownFieldError) as caught:
        DashboardSelection(nonsense=True)

    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value, TypeError)


def test_selection_rejects_unknown_loaded_session_member_and_run() -> None:
    sessions = _sessions(5)
    with pytest.raises(DashboardSelectionError, match="Unknown session date"):
        DashboardSelection(date="1999-01-01", session_dates=sessions)
    with pytest.raises(DashboardSelectionError, match="Unknown dashboard member"):
        DashboardSelection(member="Bogus", members=["Manuf", "Enrgy"])
    with pytest.raises(DashboardSelectionError, match="Unknown evaluation run"):
        DashboardSelection(run="missing", runs=["run-1", "run-2"])


def test_selection_round_trips_all_public_fields() -> None:
    selection = DashboardSelection(
        screen="evaluation",
        mode="replay",
        date="2024-03-04",
        reveal=True,
        member="Manuf",
        run="run-7",
    )

    restored = DashboardSelection.from_dict(selection.to_dict())

    assert restored == selection
    assert restored.to_dict() == selection.to_dict()
    assert DashboardSelection.from_json(selection.to_json()) == selection


def test_selection_window_is_derived_from_loaded_sessions() -> None:
    sessions = _sessions(150)
    selection = DashboardSelection(date=sessions[100], session_dates=sessions)

    assert len(selection.window) == DEFAULT_WINDOW_SESSIONS
    assert selection.window[0] == sessions[41]
    assert selection.window[-1] == sessions[100]
    assert selection.window_start == sessions[41]
    assert selection.window_end == sessions[100]
    assert selection.window_sessions == DEFAULT_WINDOW_SESSIONS
    assert selection.window(sessions) == tuple(sessions[41:101])
    assert derive_window(sessions, sessions[100]) == tuple(sessions[41:101])


def test_selection_window_defaults_to_latest_and_clamps_at_the_start() -> None:
    sessions = _sessions(10)

    latest = DashboardSelection(session_dates=sessions)
    assert latest.date == sessions[-1]
    assert latest.window == tuple(sessions)

    first = DashboardSelection(date=sessions[0], session_dates=sessions)
    assert first.window == (sessions[0],)
    assert derive_window([], None) == ()


def test_session_window_and_member_keyboard_stepping() -> None:
    sessions = _sessions(150)
    members = ["NoDur", "Durbl", "Manuf"]
    selection = DashboardSelection(
        screen="topology",
        mode="replay",
        date=sessions[100],
        reveal=True,
        member="NoDur",
        session_dates=sessions,
        members=members,
    )

    advanced = next_session(selection, sessions)
    assert advanced.date == sessions[101]
    assert advanced.reveal is False

    restored = previous_session(advanced, sessions)
    assert restored.date == sessions[100]

    window_selection = DashboardSelection(
        date=sessions[10],
        session_dates=sessions,
    )
    windowed = next_window(window_selection, sessions)
    assert windowed.date == sessions[10 + DEFAULT_WINDOW_SESSIONS]
    assert previous_window(windowed, sessions).date == sessions[10]

    member = next_member(selection, members)
    assert member.member == "Durbl"
    assert previous_member(member, members).member == "NoDur"


def test_keyboard_stepping_clamps_at_boundaries() -> None:
    sessions = _sessions(5)
    first = DashboardSelection(date=sessions[0], session_dates=sessions)
    last = DashboardSelection(date=sessions[-1], session_dates=sessions)

    assert previous_session(first, sessions).date == sessions[0]
    assert next_session(last, sessions).date == sessions[-1]
    assert next_window(last, sessions).date == sessions[-1]


def test_keyboard_actions_are_available_by_name_and_enum() -> None:
    sessions = _sessions(10)
    selection = DashboardSelection(date=sessions[4], session_dates=sessions)

    assert apply_keyboard_action(selection, "next_session", sessions).date == sessions[5]
    assert (
        apply_keyboard_action(selection, KeyboardAction.NEXT_SESSION, sessions=sessions).date
        == sessions[5]
    )
    assert apply_keyboard_action(selection, "ArrowRight", sessions=sessions).date == sessions[5]
    assert apply_keyboard_action(selection, "next-window", sessions=sessions).date == sessions[-1]
    assert apply_keyboard_action("next_session", selection, sessions).date == sessions[5]


def test_unknown_keyboard_action_raises_a_clear_error() -> None:
    selection = DashboardSelection()

    with pytest.raises(DashboardActionError, match="Unknown keyboard action"):
        apply_keyboard_action(selection, "launch_rocket")
    with pytest.raises(DashboardActionError, match="launch_rocket"):
        apply_keyboard_action(selection, "launch_rocket")


def test_reveal_and_blind_toggle_only_in_replay() -> None:
    replay = DashboardSelection(mode="replay", reveal=False)
    assert toggle_reveal(replay).reveal is True
    assert toggle_blind(toggle_reveal(replay)).reveal is False

    live = DashboardSelection(mode="live")
    with pytest.raises(DashboardActionError, match="replay mode"):
        toggle_reveal(live)


def test_changing_the_selected_session_clears_reveal() -> None:
    sessions = _sessions(20)
    selection = DashboardSelection(
        mode="replay",
        date=sessions[5],
        reveal=True,
        session_dates=sessions,
    )

    assert selection.with_date(sessions[6]).reveal is False
    assert selection.replace(date=sessions[6]).reveal is False
    assert selection.replace(date=sessions[5]).reveal is True
    assert replace(selection, member="Manuf").reveal is True


def test_changing_mode_away_from_replay_clears_reveal() -> None:
    selection = DashboardSelection(mode="replay", reveal=True)

    assert selection.with_mode("live").reveal is False
    assert selection.replace(mode="live").reveal is False


def test_keyboard_action_names_are_stable() -> None:
    assert set(KEYBOARD_ACTIONS) == {action.value for action in KeyboardAction}
    assert "next_session" in KEYBOARD_ACTIONS
    assert "toggle_reveal" in KEYBOARD_ACTIONS


# ---------------------------------------------------------------------------
# Regression tests for the Step 7 selection-model review findings
# ---------------------------------------------------------------------------
def test_explicit_reveal_update_is_cleared_when_the_session_changes() -> None:
    sessions = _sessions(20)
    selection = DashboardSelection(
        mode="replay",
        date=sessions[5],
        reveal=True,
        session_dates=sessions,
    )

    changed = selection.replace(date=sessions[6], reveal=True)

    assert changed.date == sessions[6]
    assert changed.reveal is False


def test_dataclasses_replace_keeps_loaded_context_and_clears_reveal() -> None:
    sessions = _sessions(20)
    selection = DashboardSelection(
        mode="replay",
        date=sessions[5],
        reveal=True,
        session_dates=sessions,
        window_size=3,
    )

    changed = replace(selection, date=sessions[6])

    assert changed.date == sessions[6]
    assert changed.reveal is False
    assert changed.session_dates == tuple(sessions)
    assert changed.window_size == 3
    assert changed.window == (sessions[4], sessions[5], sessions[6])


def test_dataclasses_replace_with_explicit_reveal_still_clears_on_a_new_session() -> None:
    sessions = _sessions(20)
    selection = DashboardSelection(
        mode="replay",
        date=sessions[5],
        reveal=True,
        session_dates=sessions,
        window_size=3,
    )

    changed = replace(selection, date=sessions[6], reveal=True)

    assert changed.date == sessions[6]
    assert changed.reveal is False
    assert changed.session_dates == tuple(sessions)
    assert changed.window_size == 3


def test_dataclasses_replace_leaving_replay_clears_reveal() -> None:
    selection = DashboardSelection(mode="replay", reveal=True)

    changed = replace(selection, mode="live")

    assert changed.mode == "live"
    assert changed.reveal is False


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"date": "2024-01-02", "session_dates": []}, "Unknown session date"),
        ({"member": "Manuf", "members": []}, "Unknown dashboard member"),
        ({"run": "run-7", "runs": []}, "Unknown evaluation run"),
    ],
)
def test_explicit_empty_collections_reject_selected_values(kwargs: dict, match: str) -> None:
    with pytest.raises(DashboardSelectionError, match=match):
        DashboardSelection(**kwargs)


def test_validate_rejects_values_absent_from_explicit_empty_collections() -> None:
    selection = DashboardSelection(
        screen="evaluation",
        mode="replay",
        date="2024-01-02",
        reveal=True,
        member="Manuf",
        run="run-7",
    )

    with pytest.raises(DashboardSelectionError, match="Unknown session date"):
        selection.validate(session_dates=[])
    with pytest.raises(DashboardSelectionError, match="Unknown dashboard member"):
        selection.validate(session_dates=["2024-01-02"], members=[])
    with pytest.raises(DashboardSelectionError, match="Unknown evaluation run"):
        selection.validate(session_dates=["2024-01-02"], runs=[])


def test_validate_rejects_an_unknown_date_against_an_explicit_empty_list() -> None:
    selection = DashboardSelection(date="2024-01-02")

    with pytest.raises(DashboardSelectionError, match="Unknown session date"):
        selection.validate(session_dates=[])


def test_misspelled_fields_are_rejected_instead_of_being_fuzzy_matched() -> None:
    with pytest.raises(UnknownFieldError, match="misspelled_reveal"):
        DashboardSelection(misspelled_reveal=True)

    selection = DashboardSelection(mode="replay", reveal=True)
    with pytest.raises(UnknownFieldError, match="misspelled_date"):
        selection.replace(misspelled_date="2024-01-02")


def test_window_stepping_uses_the_selection_window_size() -> None:
    sessions = _sessions(12)
    selection = DashboardSelection(
        date=sessions[2],
        session_dates=sessions,
        window_size=3,
    )

    assert next_window(selection).date == sessions[5]
    assert next_window(next_window(selection)).date == sessions[8]
    assert previous_window(next_window(selection)).date == sessions[2]

    # An explicit override still wins over the selection's stored size.
    assert next_window(selection, window_size=2).date == sessions[4]


def test_serialization_preserves_loaded_context_and_window_size() -> None:
    sessions = _sessions(10)
    selection = DashboardSelection(
        screen="topology",
        mode="replay",
        date=sessions[4],
        reveal=True,
        member="Manuf",
        run="run-7",
        session_dates=sessions,
        members=["NoDur", "Manuf"],
        runs=["run-7"],
        window_size=3,
    )

    restored = DashboardSelection.from_json(selection.to_json())

    assert restored == selection
    assert restored.session_dates == tuple(sessions)
    assert restored.members == ("NoDur", "Manuf")
    assert restored.runs == ("run-7",)
    assert restored.window_size == 3
    assert restored.window == (sessions[2], sessions[3], sessions[4])
    assert next_window(restored).date == sessions[7]


def test_context_can_be_reattached_after_a_minimal_round_trip() -> None:
    sessions = _sessions(10)
    selection = DashboardSelection(mode="replay", date=sessions[4], reveal=True)

    minimal = DashboardSelection.from_dict(selection.to_dict(include_context=False))
    assert minimal.session_dates == ()
    assert minimal.window == ()

    attached = minimal.attach_context(session_dates=sessions, window_size=3)
    assert attached.session_dates == tuple(sessions)
    assert attached.window == (sessions[2], sessions[3], sessions[4])
    assert next_window(attached).date == sessions[7]


def test_unsorted_loaded_sessions_are_sorted_for_window_and_stepping() -> None:
    sessions = ["2024-01-03", "2024-01-01", "2024-01-02"]

    selection = DashboardSelection(date="2024-01-01", session_dates=sessions)

    assert selection.session_dates == ("2024-01-01", "2024-01-02", "2024-01-03")
    assert selection.window == ("2024-01-01",)
    assert derive_window(sessions, "2024-01-02") == ("2024-01-01", "2024-01-02")
    assert next_session(selection).date == "2024-01-02"
    assert previous_session(DashboardSelection(date="2024-01-03", session_dates=sessions)).date == (
        "2024-01-02"
    )


def test_unsorted_sessions_use_the_chronological_trailing_window() -> None:
    sessions = ["2024-01-05", "2024-01-01", "2024-01-04", "2024-01-02", "2024-01-03"]

    selection = DashboardSelection(
        date="2024-01-03",
        session_dates=sessions,
        window_size=3,
    )

    assert selection.window == ("2024-01-01", "2024-01-02", "2024-01-03")
    assert next_window(selection).date == "2024-01-05"


def test_duplicate_loaded_session_dates_are_rejected() -> None:
    with pytest.raises(DashboardSelectionError, match="unique"):
        DashboardSelection(date="2024-01-02", session_dates=["2024-01-02", "2024-01-02"])
