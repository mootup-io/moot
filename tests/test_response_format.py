"""Tests for response formatting at all detail levels."""
from __future__ import annotations

from moot.models import ContextEvent, Participant, SpaceStatus
from moot.response_format import (
    format_events,
    format_mentions,
    format_participants,
    format_space_status,
    format_activity,
)


def _make_event(**overrides) -> ContextEvent:
    defaults = {
        "event_id": "evt_abc",
        "space_id": "spc_123",
        "speaker_id": "agt_x",
        "speaker_name": "TestAgent",
        "speaker_type": "agent",
        "text": "Hello world",
        "timestamp": "2026-04-10T12:00:00+00:00",
    }
    defaults.update(overrides)
    return ContextEvent.model_validate(defaults)


def _make_participant(**overrides) -> Participant:
    defaults = {
        "participant_id": "agt_x",
        "name": "TestAgent",
        "participant_type": "agent",
        "joined_at": "2026-04-10T10:00:00+00:00",
        "agent_adapter": "mcp",
        "status": "ready",
        "status_updated_at": "2026-04-10T12:00:00+00:00",
    }
    defaults.update(overrides)
    return Participant.model_validate(defaults)


def test_format_events_minimal() -> None:
    """Minimal detail shows timestamp + speaker only, no text."""
    events = [_make_event()]
    result = format_events(events, detail="minimal")
    assert "TestAgent" in result
    assert "evt_abc" in result
    # Minimal should NOT include the full text body on a separate line
    assert "Hello world" not in result


def test_format_events_standard() -> None:
    """Standard detail includes text."""
    events = [_make_event()]
    result = format_events(events, detail="standard")
    assert "TestAgent" in result
    assert "Hello world" in result


def test_format_events_full() -> None:
    """Full detail includes metadata fields."""
    events = [_make_event(metadata={"mentions": ["agt_y"], "message_type": "question"})]
    result = format_events(events, detail="full")
    assert "question" in result
    assert "@agt_y" in result


def test_format_events_empty() -> None:
    """Empty event list returns placeholder."""
    result = format_events([], detail="standard")
    assert "no events" in result


def test_format_participants_minimal() -> None:
    """Minimal participants show name + status only."""
    participants = [_make_participant()]
    result = format_participants(participants, detail="minimal")
    assert "TestAgent" in result
    assert "ready" in result


def test_format_participants_full() -> None:
    """Full participants include adapter and joined info."""
    participants = [_make_participant()]
    result = format_participants(participants, detail="full")
    assert "mcp" in result
    assert "TestAgent" in result


def test_format_space_status_minimal() -> None:
    """Minimal space status shows status + event count."""
    status = SpaceStatus(
        space_id="spc_1",
        status="active",
        started_at="2026-04-10T10:00:00+00:00",
        event_count=42,
    )
    result = format_space_status(status, detail="minimal")
    assert "active" in result
    assert "42" in result


def test_format_space_status_full() -> None:
    """Full space status includes description and participants."""
    status = SpaceStatus(
        space_id="spc_1",
        description="Test space",
        status="active",
        started_at="2026-04-10T10:00:00+00:00",
        event_count=10,
        participants=[_make_participant()],
    )
    result = format_space_status(status, detail="full")
    assert "Test space" in result
    assert "TestAgent" in result


def test_format_mentions_minimal() -> None:
    """Minimal mentions show count + latest."""
    events = [
        _make_event(event_id="evt_1", speaker_name="A"),
        _make_event(event_id="evt_2", speaker_name="B"),
    ]
    result = format_mentions(events, detail="minimal")
    assert "2 mentions" in result
    assert "B" in result  # latest


def test_format_activity_minimal() -> None:
    """Minimal activity shows counts only."""
    data = {
        "since": "2026-04-10T10:00:00",
        "participants": [
            {
                "name": "Agent1",
                "event_count": 5,
                "last_active": "2026-04-10T12:30:00+00:00",
                "summary_events": [],
            }
        ],
    }
    result = format_activity(data, detail="minimal")
    assert "Agent1" in result
    assert "5 events" in result


def test_detail_levels_produce_different_output() -> None:
    """All 5 format functions produce different output at different detail levels."""
    events = [_make_event(metadata={"mentions": ["x"], "message_type": "msg"})]
    participants = [_make_participant()]
    status = SpaceStatus(
        space_id="spc_1",
        description="desc",
        status="active",
        started_at="2026-04-10T10:00:00+00:00",
        event_count=10,
        participants=participants,
    )
    activity = {
        "since": "2026-04-10T10:00:00",
        "participants": [
            {
                "name": "A",
                "event_count": 3,
                "last_active": "2026-04-10T12:00:00+00:00",
                "summary_events": [
                    {"timestamp": "2026-04-10T12:00:00", "text": "hello", "metadata": {}}
                ],
            }
        ],
    }

    for fn, args in [
        (format_events, (events,)),
        (format_mentions, (events,)),
        (format_participants, (participants,)),
        (format_space_status, (status,)),
        (format_activity, (activity,)),
    ]:
        minimal = fn(*args, detail="minimal")
        standard = fn(*args, detail="standard")
        full = fn(*args, detail="full")
        # At least 2 of 3 levels should be distinct
        outputs = {minimal, standard, full}
        assert len(outputs) >= 2, (
            f"{fn.__name__} produced identical output at all detail levels"
        )
