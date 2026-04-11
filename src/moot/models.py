"""API response models for the Convo REST API.

These describe the JSON contract — not the internal database schema.
They evolve independently of the backend models.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ContextEvent(BaseModel):
    """A single event in a Convo space."""
    event_id: str = ""
    space_id: str = ""
    speaker_id: str = ""
    speaker_name: str = "?"
    speaker_type: str = ""
    text: str = ""
    timestamp: str = ""
    parent_event_id: str | None = None
    references: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    metadata: dict[str, Any] | None = None


class Participant(BaseModel):
    """A space participant (human or agent)."""
    participant_id: str
    name: str
    participant_type: str
    joined_at: str
    agent_adapter: str | None = None
    actor_id: str | None = None
    status: str | None = None
    status_updated_at: str | None = None
    last_seen_at: str | None = None


class SpaceStatus(BaseModel):
    """Space metadata and summary."""
    space_id: str
    description: str = ""
    status: str = "active"
    links: list[str] = Field(default_factory=list)
    started_at: str
    participants: list[Participant] = Field(default_factory=list)
    event_count: int = 0
    last_event_at: str | None = None
