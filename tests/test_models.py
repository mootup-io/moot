"""Tests for API response model parsing."""
from __future__ import annotations


def test_model_parse_event() -> None:
    """ContextEvent parses from API JSON dict."""
    from moot.models import ContextEvent

    data = {
        "event_id": "evt_abc123",
        "space_id": "spc_def456",
        "speaker_id": "agt_ghi789",
        "speaker_name": "TestAgent",
        "speaker_type": "agent",
        "text": "Hello, world!",
        "timestamp": "2026-04-10T12:00:00+00:00",
        "parent_event_id": None,
        "references": ["ref1", "ref2"],
        "thread_id": "thr_jkl012",
        "metadata": {"mentions": ["agt_xyz"]},
    }

    event = ContextEvent.model_validate(data)
    assert event.event_id == "evt_abc123"
    assert event.speaker_name == "TestAgent"
    assert event.text == "Hello, world!"
    assert event.thread_id == "thr_jkl012"
    assert event.references == ["ref1", "ref2"]
    assert event.metadata == {"mentions": ["agt_xyz"]}


def test_model_parse_event_defaults() -> None:
    """ContextEvent uses defaults for missing fields."""
    from moot.models import ContextEvent

    event = ContextEvent.model_validate({})
    assert event.event_id == ""
    assert event.speaker_name == "?"
    assert event.references == []
    assert event.thread_id is None


def test_model_parse_space_status() -> None:
    """SpaceStatus with nested Participant list parses correctly."""
    from moot.models import SpaceStatus

    data = {
        "space_id": "spc_abc",
        "description": "Test space",
        "status": "active",
        "links": ["https://example.com"],
        "started_at": "2026-04-10T10:00:00+00:00",
        "participants": [
            {
                "participant_id": "agt_123",
                "name": "Agent1",
                "participant_type": "agent",
                "joined_at": "2026-04-10T10:01:00+00:00",
                "agent_adapter": "mcp",
                "status": "ready",
            },
            {
                "participant_id": "usr_456",
                "name": "Human1",
                "participant_type": "human",
                "joined_at": "2026-04-10T10:02:00+00:00",
            },
        ],
        "event_count": 42,
        "last_event_at": "2026-04-10T12:00:00+00:00",
    }

    status = SpaceStatus.model_validate(data)
    assert status.space_id == "spc_abc"
    assert status.status == "active"
    assert status.event_count == 42
    assert len(status.participants) == 2
    assert status.participants[0].name == "Agent1"
    assert status.participants[0].agent_adapter == "mcp"
    assert status.participants[1].participant_type == "human"
    assert status.participants[1].agent_adapter is None
