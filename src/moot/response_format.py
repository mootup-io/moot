"""Shared response formatting for MCP tools and timer evaluator.

Provides detail-level formatting (minimal/standard/full) for the 6
read-heavy MCP tools. Both the MCP adapter and timer evaluator use
these functions to ensure consistent output.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal

from moot.models import ContextEvent, Participant, SpaceStatus

logger = logging.getLogger("convo.response_format")

Detail = Literal["minimal", "standard", "full"]


def format_events(events: list[ContextEvent], detail: Detail = "standard") -> str:
    """Format context events at the given detail level."""
    if not events:
        return "(no events)"
    lines: list[str] = []
    for e in events:
        ts = e.timestamp[:19] if e.timestamp else ""
        eid = e.event_id
        thread = f" [thread:{e.thread_id}]" if e.thread_id else ""

        if detail == "minimal":
            lines.append(f"[{ts}] {e.speaker_name} ({eid}){thread}")

        elif detail == "full":
            meta = e.metadata or {}
            mentions = meta.get("mentions", [])
            msg_type = meta.get("message_type", "message")
            refs = len(e.references) if e.references else 0
            parent = f" | Parent: {e.parent_event_id}" if e.parent_event_id else ""
            mention_str = ", ".join(f"@{m}" for m in mentions) if mentions else "none"
            lines.append(
                f"**[{ts}] {e.speaker_name}** (event:{eid}){thread}\n"
                f"Type: {msg_type} | Mentions: {mention_str} | Refs: {refs}{parent}\n"
                f"{e.text}\n"
            )

        else:  # standard
            lines.append(f"**[{ts}] {e.speaker_name}** (event:{eid}){thread}\n{e.text}\n")

    return "\n".join(lines)


def format_mentions(
    events: list[ContextEvent],
    detail: Detail = "standard",
    since_event_id: str | None = None,
) -> str:
    """Format mention events at the given detail level."""
    if not events:
        return "(no mentions)"

    if detail == "minimal":
        latest = events[-1]
        ts = latest.timestamp[:19] if latest.timestamp else ""
        since_part = f" since {since_event_id}" if since_event_id else ""
        return (
            f"{len(events)} mention{'s' if len(events) != 1 else ''}{since_part}\n"
            f"Latest: [{ts}] {latest.speaker_name} ({latest.event_id})"
        )

    # standard and full both delegate to format_events
    return format_events(events, detail=detail)


def format_participants(
    participants: list[Participant], detail: Detail = "standard"
) -> str:
    """Format participant list at the given detail level."""
    if not participants:
        return "(no participants)"

    if detail == "minimal":
        lines: list[str] = []
        for p in participants:
            status_time = ""
            if p.status_updated_at:
                status_time = f" ({p.status_updated_at[11:16]})"
            status = p.status or "no status"
            lines.append(f"{p.name}: {status}{status_time}")
        return "\n".join(lines)

    elif detail == "full":
        now = datetime.now(timezone.utc)
        lines = []
        for p in participants:
            adapter = f" [{p.agent_adapter}]" if p.agent_adapter else ""
            lines.append(
                f"**{p.name}** ({p.participant_id}) {p.participant_type}{adapter}"
            )
            status = p.status or "no status"
            status_time = ""
            if p.status_updated_at:
                status_time = f" ({p.status_updated_at[11:16]})"
            lines.append(f"Status: {status}{status_time}")
            joined = p.joined_at[:19] if p.joined_at else "?"
            seen_part = ""
            online = ""
            if p.last_seen_at:
                try:
                    seen_dt = datetime.fromisoformat(p.last_seen_at)
                    delta = now - seen_dt
                    mins = int(delta.total_seconds() / 60)
                    seen_part = f" | Last seen: {mins}m ago"
                    online = " | Online" if mins < 5 else " | Offline"
                except (ValueError, TypeError):
                    seen_part = f" | Last seen: {p.last_seen_at[:19]}"
            lines.append(f"Joined: {joined}{seen_part}{online}")
            lines.append("")  # blank line between participants
        return "\n".join(lines).rstrip()

    else:  # standard — JSON pass-through (current behavior)
        return json.dumps(
            [p.model_dump() for p in participants], indent=2
        )


def format_activity(data: dict, detail: Detail = "standard") -> str:
    """Format activity digest at the given detail level."""
    lines: list[str] = [f"Activity since {data.get('since', '?')}:\n"]

    for p in data.get("participants", []):
        name = p.get("name", "?")
        count = p.get("event_count", 0)
        last = p.get("last_active", "")

        if detail == "minimal":
            last_short = last[11:16] if len(last) > 16 else last
            event_word = "event" if count == 1 else "events"
            lines.append(f"  {name}: {count} {event_word}, last {last_short}")

        elif detail == "full":
            last_ts = last[:19]
            lines.append(f"## {name} ({count} events, last active {last_ts})\n")
            for e in p.get("summary_events", []):
                ts = e.get("timestamp", "")[:19]
                text = e.get("text", "")
                meta = e.get("metadata", {}) or {}
                msg_type = meta.get("message_type", "")
                type_prefix = f" [{msg_type}]" if msg_type else ""
                lines.append(f"  [{ts}]{type_prefix} {text}\n")

        else:  # standard
            last_ts = last[:19]
            lines.append(f"## {name} ({count} events, last active {last_ts})\n")
            for e in p.get("summary_events", []):
                ts = e.get("timestamp", "")[:19]
                text = e.get("text", "")
                if len(text) > 300:
                    text = text[:300] + "..."
                lines.append(f"  [{ts}] {text}\n")

    return "\n".join(lines)


def format_space_status(status: SpaceStatus, detail: Detail = "standard") -> str:
    """Format space status at the given detail level."""
    if detail == "minimal":
        return f"{status.status} | {status.event_count} events"

    elif detail == "full":
        lines = [
            f"Space: {status.space_id}",
            f"Description: {status.description}" if status.description else None,
            f"Status: {status.status}",
            f"Events: {status.event_count}",
            f"Last event: {status.last_event_at}" if status.last_event_at else None,
            f"Started: {status.started_at}",
        ]
        parts = [l for l in lines if l is not None]

        if status.participants:
            parts.append(f"\nParticipants ({len(status.participants)}):")
            for p in status.participants:
                status_text = p.status or "no status"
                time_part = ""
                if p.status_updated_at:
                    time_part = f" ({p.status_updated_at[11:16]})"
                parts.append(f"  {p.name}: {status_text}{time_part}")
        return "\n".join(parts)

    else:  # standard — JSON pass-through (current behavior)
        return status.model_dump_json(indent=2)
