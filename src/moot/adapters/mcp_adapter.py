"""MCP adapter — thin HTTP client that exposes convo API as MCP tools.

This adapter does NOT connect to PostgreSQL or Redis directly. It calls
the convo REST API over HTTP, just like the frontend does. This means
it works whether the API is local or remote.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

import re

from moot.models import ContextEvent, Participant, SpaceStatus
from moot.response_format import (
    format_activity,
    format_events,
    format_mentions,
    format_participants,
    format_space_status,
)

from pathlib import Path

_DURATION_RE = re.compile(r"^(\d+)(s|m|h)$")


def _find_transcript_path() -> str | None:
    """Find the current session's JSONL transcript file."""
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    claude_dir = Path.home() / ".claude" / "projects"

    if not claude_dir.exists():
        return None

    # Find the project directory (encoded cwd)
    cwd = os.getcwd().replace("/", "-").lstrip("-")
    project_dir = claude_dir / cwd

    if not project_dir.exists():
        project_dir = claude_dir / f"-{cwd}"

    if not project_dir.exists():
        return None

    if session_id:
        path = project_dir / f"{session_id}.jsonl"
        if path.exists():
            return str(path)

    # Fallback: most recently modified .jsonl file
    jsonl_files = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return str(jsonl_files[0]) if jsonl_files else None


def _extract_session_stats(path: str) -> dict:
    """Read a JSONL transcript and extract summary stats."""
    user_count = 0
    assistant_count = 0
    tool_call_count = 0
    model = None
    first_ts = None
    last_ts = None
    git_branch = None

    with open(path) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            ts = entry.get("timestamp")

            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            if entry_type == "user":
                user_count += 1
                if not git_branch:
                    git_branch = entry.get("gitBranch")

            elif entry_type == "assistant":
                assistant_count += 1
                msg = entry.get("message", {})
                if not model:
                    model = msg.get("model")
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_call_count += 1

    # Calculate duration
    duration_secs = 0
    if first_ts and last_ts:
        from datetime import datetime

        try:
            start = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            end = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            duration_secs = int((end - start).total_seconds())
        except (ValueError, TypeError):
            pass

    return {
        "message_count": user_count + assistant_count,
        "user_message_count": user_count,
        "tool_call_count": tool_call_count,
        "duration_seconds": duration_secs,
        "model": model,
        "start_time": first_ts,
        "end_time": last_ts,
        "transcript_path": path,
        "file_size_bytes": os.path.getsize(path),
        "git_branch": git_branch,
    }


def _parse_duration(s: str) -> int:
    """Parse a duration string like '5m', '1h', '90s' into seconds."""
    m = _DURATION_RE.match(s.strip())
    if not m:
        raise ValueError(
            f"Invalid duration '{s}'. Use format like '5m', '1h', or '90s'."
        )
    value = int(m.group(1))
    unit = m.group(2)
    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    else:  # "h"
        return value * 3600


def _parse_events(raw: list[dict]) -> list[ContextEvent]:
    """Convert API response dicts to ContextEvent objects."""
    return [
        ContextEvent(
            event_id=e.get("event_id", ""),
            space_id=e.get("space_id", ""),
            speaker_id=e.get("speaker_id", ""),
            speaker_name=e.get("speaker_name", "?"),
            speaker_type=e.get("speaker_type", ""),
            text=e.get("text", ""),
            timestamp=e.get("timestamp", ""),
            parent_event_id=e.get("parent_event_id"),
            references=e.get("references", []),
            thread_id=e.get("thread_id"),
            metadata=e.get("metadata"),
        )
        for e in raw
    ]


def _parse_participants(raw: list[dict]) -> list[Participant]:
    """Convert API response dicts to Participant objects."""
    return [Participant(**p) for p in raw]


def _parse_space_status(raw: dict) -> SpaceStatus:
    """Convert API response dict to SpaceStatus object."""
    return SpaceStatus(**raw)


class MCPSpaceAdapter:
    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        api_key: str | None = None,
        agent_id: str = "unknown-agent",
        agent_name: str = "Unknown Agent",
        auto_space_id: str | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.auto_space_id = auto_space_id
        self._space_id: str | None = None
        # Per-agent logger: convo.mcp.product, convo.mcp.spec, etc.
        self.logger = logging.getLogger(
            f"convo.mcp.{agent_name.lower().replace(' ', '-')}"
        )
        self._actor_id: str | None = None
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        ssl_cert = os.environ.get("SSL_CERT_FILE")
        verify: str | bool = ssl_cert if ssl_cert else True
        transport = httpx.AsyncHTTPTransport(retries=3)
        self._http = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=30,
            headers=headers,
            transport=transport,
            verify=verify,
        )
        self.logger.info(
            "MCPSpaceAdapter created — agent %s (%s), API %s, auth=%s",
            agent_name,
            agent_id,
            self.api_url,
            "key" if api_key else "none",
        )
        self.mcp = FastMCP(
            name="convo",
            instructions=(
                "Convo shared context server. Call join_space first with a "
                "space ID to connect, then use the other tools to participate."
            ),
        )
        self._register_tools()

    def _require_space(self) -> str:
        if self._space_id is None:
            raise ValueError("Not connected to a space. Call join_space first.")
        return self._space_id

    def _url(self, path: str) -> str:
        sid = self._require_space()
        return f"/api/spaces/{sid}{path}"

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        """HTTP request with retry and error surfacing.

        Transport retries 3x on connection errors. This method checks
        the response and raises clear errors that surface to the agent.
        """
        self.logger.debug("%s %s", method, url)
        try:
            resp = await self._http.request(method, url, **kwargs)
        except httpx.ConnectError:
            self.logger.error("Connection failed: %s %s", method, url)
            raise ValueError(
                f"Cannot reach Convo backend at {self.api_url}. "
                "The server may be restarting. Try again in a few seconds."
            )
        except httpx.TimeoutException:
            self.logger.error("Timeout: %s %s", method, url)
            raise ValueError(
                f"Request to {url} timed out after 30s. "
                "The backend may be overloaded or unreachable."
            )
        self.logger.debug("%s %s → %d", method, url, resp.status_code)
        if resp.status_code >= 500:
            self.logger.error(
                "%s %s → %d: %s", method, url, resp.status_code, resp.text[:200]
            )
            raise ValueError(
                f"Backend error {resp.status_code} on {method} {url}: "
                f"{resp.text[:200]}"
            )
        if resp.status_code == 401:
            self.logger.error("Auth failed: %s %s", method, url)
            raise ValueError(
                "Authentication failed (401). Check your CONVO_API_KEY."
            )
        if resp.status_code == 403:
            raise ValueError(f"Forbidden (403): {resp.text[:200]}")
        # 409 is handled by specific callers (post_response maps it to a
        # structured error for the agent); everything else in the 4xx range
        # is a bug the caller needs to see, not silently swallow as an empty
        # event_id or similar shape-valid-but-wrong response.
        if 400 <= resp.status_code < 500 and resp.status_code != 409:
            self.logger.error(
                "%s %s → %d: %s", method, url, resp.status_code, resp.text[:200]
            )
            raise ValueError(
                f"Backend rejected request {resp.status_code} on {method} "
                f"{url}: {resp.text[:200]}"
            )
        return resp

    def _register_tools(self) -> None:
        adapter = self

        @self.mcp.tool()
        async def join_space(space_id: str) -> str:
            """Join a convo space by ID. Creates the space if it doesn't exist.

            You must call this before using any other tools. The space ID
            is typically a UUID — the user will provide it.
            """
            adapter.logger.info("join_space(%s) as %s", space_id, adapter.agent_name)
            # Ensure space exists
            await adapter._request("POST", 
                "/api/spaces",
                json={"space_id": space_id},
            )
            # Register as participant
            await adapter._request("POST", 
                f"/api/spaces/{space_id}/join",
                json={
                    "participant_id": adapter.agent_id,
                    "name": adapter.agent_name,
                    "participant_type": "agent",
                    "agent_adapter": "mcp",
                },
            )
            adapter._space_id = space_id
            # Cache actor_id for tools that need it
            if not adapter._actor_id:
                me_resp = await adapter._request("GET", "/api/actors/me")
                try:
                    adapter._actor_id = json.loads(me_resp.text).get("actor_id")
                except (json.JSONDecodeError, AttributeError):
                    pass
            # Return status
            resp = await adapter._request("GET", f"/api/spaces/{space_id}/status")
            return resp.text

        @self.mcp.tool()
        async def list_spaces() -> str:
            """List all active spaces on this convo server."""
            adapter.logger.info("list_spaces")
            resp = await adapter._request("GET", "/api/spaces")
            return resp.text

        @self.mcp.tool()
        async def get_recent_context(
            since_event_id: str | None = None,
            limit: int = 20,
            detail: str = "minimal",
        ) -> str:
            """Get recent space context events.

            Call with no arguments to get the latest events.
            Call with since_event_id to get only new events since that point.
            Each event has an event_id you can use as a cursor for the next call.

            detail: "minimal" (timestamps+speakers only), "standard" (full text),
                    or "full" (includes metadata, mentions, references).
                    Default is minimal — pass "standard" when you need message text.
            """
            adapter._require_space()
            if detail not in ("minimal", "standard", "full"):
                return f"Invalid detail level '{detail}'. Use 'minimal', 'standard', or 'full'."
            params: dict[str, str | int] = {"limit": limit}
            if since_event_id:
                params["since"] = since_event_id
            resp = await adapter._request("GET", adapter._url("/events"), params=params)
            events = _parse_events(resp.json())
            return format_events(events, detail=detail)

        @self.mcp.tool()
        async def post_response(
            text: str,
            parent_event_id: str | None = None,
            references: list[str] | None = None,
            mentions: list[str] | None = None,
            message_type: str | None = None,
            thread_id: str | None = None,
        ) -> str:
            """Post your response to the space. All participants will see this.

            Optionally reference a parent_event_id to thread your response
            to a specific earlier message. Include references as a list of
            URIs to external artifacts (GitHub PRs, Jira tickets, etc.).

            Use mentions to direct the message at specific participant_ids.
            Use message_type to categorize: "message", "question",
            "status_update", "code_share", "review_request".
            Use thread_id to post into an existing thread.
            """
            adapter._require_space()
            adapter.logger.info("post_response from %s: %s", adapter.agent_name, text[:80])
            metadata: dict[str, object] = {}
            if mentions:
                metadata["mentions"] = mentions
            if message_type:
                metadata["message_type"] = message_type
            resp = await adapter._request("POST", 
                adapter._url("/response"),
                json={
                    "agent_id": adapter.agent_id,
                    "agent_name": adapter.agent_name,
                    "text": text,
                    "parent_event_id": parent_event_id,
                    "thread_id": thread_id,
                    "metadata": metadata or None,
                },
            )
            if resp.status_code == 409:
                return json.dumps({"error": resp.json().get("detail", "Space not active")})
            data = resp.json()
            return json.dumps({
                "event_id": data.get("event_id", ""),
                "thread_id": data.get("thread_id"),
            })

        @self.mcp.tool()
        async def list_participants(detail: str = "minimal") -> str:
            """List all current space participants (humans and agents).

            detail: "minimal" (name+status only), "standard" (full JSON),
                    or "full" (includes online/offline, last seen).
            """
            adapter._require_space()
            if detail not in ("minimal", "standard", "full"):
                return f"Invalid detail level '{detail}'. Use 'minimal', 'standard', or 'full'."
            resp = await adapter._request("GET", adapter._url("/participants"))
            participants = _parse_participants(resp.json())
            return format_participants(participants, detail=detail)

        @self.mcp.tool()
        async def update_status(status: str) -> str:
            """Set your participant status (e.g. "ready", "implementing", "verifying").

            Short free-form string visible to other participants.
            """
            adapter._require_space()
            resp = await adapter._request(
                "PATCH",
                adapter._url(f"/participants/{adapter._actor_id}/status"),
                json={"status": status},
            )
            return json.dumps({"status": "updated"})

        @self.mcp.tool()
        async def get_space_status(detail: str = "minimal") -> str:
            """Get space status: space info, participant count, event count.

            detail: "minimal" (status+count only), "standard" (full JSON),
                    or "full" (includes participant summary, last event time).
            """
            adapter._require_space()
            if detail not in ("minimal", "standard", "full"):
                return f"Invalid detail level '{detail}'. Use 'minimal', 'standard', or 'full'."
            resp = await adapter._request("GET", adapter._url("/status"))
            status = _parse_space_status(resp.json())
            return format_space_status(status, detail=detail)

        @self.mcp.tool()
        async def get_transcript(
            start: str | None = None, end: str | None = None
        ) -> str:
            """Get the full space transcript.

            Optionally filter by time range using ISO 8601 timestamps.
            """
            adapter._require_space()
            params: dict[str, str] = {}
            if start:
                params["start"] = start
            if end:
                params["end"] = end
            resp = await adapter._request("GET", adapter._url("/transcript"), params=params)
            return resp.text

        @self.mcp.tool()
        async def propose_decision(text: str, question_id: str | None = None) -> str:
            """Propose a decision for the space.

            Creates a decision record that can be listed, resolved, or rejected.
            Optionally link to an open question by passing question_id —
            when this decision is resolved, the question auto-transitions to answered.
            Returns the decision with its decision_id for future reference.
            """
            adapter._require_space()
            adapter.logger.info("propose_decision from %s: %s", adapter.agent_name, text[:80])
            payload: dict = {
                "proposed_by": adapter.agent_id,
                "text": text,
            }
            if question_id:
                payload["question_id"] = question_id
            resp = await adapter._request("POST",
                adapter._url("/decisions"),
                json=payload,
            )
            if resp.status_code == 409:
                return json.dumps({"error": resp.json().get("detail", "Space not active")})
            data = resp.json()
            return json.dumps({"decision_id": data.get("decision_id", "")})

        @self.mcp.tool()
        async def list_decisions(status: str | None = None) -> str:
            """List decisions in the current space.

            Returns all decisions, optionally filtered by status.
            Status values: "proposed", "resolved", "rejected".
            """
            adapter._require_space()
            adapter.logger.info("list_decisions for %s (status=%s)", adapter.agent_name, status)
            params: dict[str, str] = {}
            if status:
                params["status"] = status
            resp = await adapter._request("GET", 
                adapter._url("/decisions"),
                params=params,
            )
            return resp.text

        @self.mcp.tool()
        async def resolve_decision(
            decision_id: str,
            resolution: str,
            status: str = "resolved",
        ) -> str:
            """Resolve or reject a decision.

            Pass the decision_id from list_decisions or propose_decision.
            Set status to "resolved" (default) or "rejected".
            The resolution field should describe the outcome.
            """
            adapter._require_space()
            adapter.logger.info(
                "resolve_decision %s as %s by %s",
                decision_id[:8],
                status,
                adapter.agent_name,
            )
            resp = await adapter._request("PUT",
                adapter._url(f"/decisions/{decision_id}/resolve"),
                json={
                    "resolved_by": adapter.agent_id,
                    "resolution": resolution,
                    "status": status,
                },
            )
            return json.dumps({"decision_id": decision_id, "status": status})

        @self.mcp.tool()
        async def ask_question(text: str, assigned_to: str | None = None) -> str:
            """Ask a question in the current space.

            Creates an open question that can be listed, assigned, deferred, or
            answered by a decision. Returns the question with its question_id.
            """
            adapter._require_space()
            adapter.logger.info("ask_question from %s: %s", adapter.agent_name, text[:80])
            resp = await adapter._request("POST",
                adapter._url("/questions"),
                json={
                    "asked_by": adapter.agent_id,
                    "text": text,
                    "assigned_to": assigned_to,
                },
            )
            if resp.status_code == 409:
                return json.dumps({"error": resp.json().get("detail", "Space not active")})
            data = resp.json()
            return json.dumps({"question_id": data.get("question_id", "")})

        @self.mcp.tool()
        async def list_questions(status: str | None = None) -> str:
            """List questions in the current space.

            Returns all questions, optionally filtered by status.
            Status values: "open", "answered", "deferred".
            """
            adapter._require_space()
            adapter.logger.info("list_questions for %s (status=%s)", adapter.agent_name, status)
            params: dict[str, str] = {}
            if status:
                params["status"] = status
            resp = await adapter._request("GET",
                adapter._url("/questions"),
                params=params,
            )
            return resp.text

        @self.mcp.tool()
        async def defer_question(question_id: str, reason: str | None = None) -> str:
            """Defer a question for later consideration.

            Moves the question to 'deferred' status. Optionally provide
            a reason which will be posted as a context event.
            """
            adapter._require_space()
            adapter.logger.info("defer_question %s by %s", question_id[:8], adapter.agent_name)
            resp = await adapter._request("PATCH",
                adapter._url(f"/questions/{question_id}"),
                json={"status": "deferred"},
            )
            if resp.status_code == 404:
                return json.dumps({"error": "Question not found"})
            if reason and resp.status_code == 200:
                await adapter._request("POST",
                    adapter._url("/events"),
                    json={
                        "speaker_id": adapter.agent_id,
                        "speaker_name": adapter.agent_name,
                        "speaker_type": "agent",
                        "text": f"Deferred question: {reason}",
                        "metadata": {"message_type": "question_deferred"},
                    },
                )
            return json.dumps({"question_id": question_id, "status": "deferred"})

        @self.mcp.tool()
        async def get_activity(
            since: str | None = None,
            max_events: int = 5,
            detail: str = "minimal",
        ) -> str:
            """Get a per-participant activity digest for the space.

            Returns events grouped by speaker since the given timestamp.
            Each participant shows their event count, last active time,
            and up to max_events most recent messages.

            If since is not provided, defaults to 1 hour ago.
            Use this to catch up on what happened while you were away.

            detail: "minimal" (counts only), "standard" (with truncated events),
                    or "full" (untruncated events with metadata).
            """
            adapter._require_space()
            if detail not in ("minimal", "standard", "full"):
                return f"Invalid detail level '{detail}'. Use 'minimal', 'standard', or 'full'."
            adapter.logger.info("get_activity for %s (since=%s)", adapter.agent_name, since)
            params: dict[str, str | int] = {}
            if since:
                params["since"] = since
            if max_events != 5:
                params["max_events"] = max_events
            resp = await adapter._request("GET",
                adapter._url("/activity"),
                params=params,
            )
            return format_activity(resp.json(), detail=detail)

        @self.mcp.tool()
        async def get_summary(
            start: str | None = None,
            end: str | None = None,
            regenerate: bool = False,
        ) -> str:
            """Get an LLM-generated summary of the space.

            Returns a cached summary if available, otherwise generates one.
            Default window: everything before the last hour (pairs with
            get_recent_context for the recent detail window).

            Use start/end (ISO 8601) for a specific time range.
            Set regenerate=true to bypass the cache.
            """
            adapter._require_space()
            adapter.logger.info("get_summary for %s (start=%s, end=%s)", adapter.agent_name, start, end)
            params: dict[str, str | bool] = {}
            if start:
                params["start"] = start
            if end:
                params["end"] = end
            if regenerate:
                params["regenerate"] = True
            resp = await adapter._request("GET",
                adapter._url("/summary"),
                params=params,
            )
            summary = resp.json()
            return summary.get("summary_text", "(no summary available)")

        @self.mcp.tool()
        async def get_context_with_summary(
            recent_limit: int = 20,
            detail: str = "standard",
        ) -> str:
            """Get space context with an LLM summary of older events.

            Returns a summary covering everything before the last hour,
            plus the most recent events in full detail. Use this to catch
            up on a long space without replaying the full history.

            For short spaces (under 50 events), returns just the events
            without a summary.

            detail: "minimal" (summary only, no events), "standard" (default),
                    or "full" (events include metadata, mentions, references).
            """
            adapter._require_space()
            if detail not in ("minimal", "standard", "full"):
                return f"Invalid detail level '{detail}'. Use 'minimal', 'standard', or 'full'."
            adapter.logger.info("get_context_with_summary for %s", adapter.agent_name)

            status_resp = await adapter._request("GET", adapter._url("/status"))
            status = status_resp.json()

            parts: list[str] = []

            if status.get("event_count", 0) > 50:
                summary_resp = await adapter._request("GET", adapter._url("/summary"))
                summary = summary_resp.json()
                parts.append(f"# Summary (covers events before the last hour)\n\n{summary.get('summary_text', '(no summary)')}")
                parts.append(f"\n---\n")

            # For minimal, skip the events fetch entirely
            if detail == "minimal":
                if not parts:
                    parts.append("# Summary\n\n(no summary available — space has fewer than 50 events)")
                return "\n".join(parts)

            events_resp = await adapter._request("GET",
                adapter._url("/events"),
                params={"limit": recent_limit},
            )
            events = _parse_events(events_resp.json())

            parts.append(f"# Recent events ({len(events)} messages)\n")
            parts.append(format_events(events, detail=detail))

            return "\n".join(parts)

        @self.mcp.tool()
        async def reply_to(
            event_id: str,
            text: str,
            mentions: list[str] | None = None,
            references: list[str] | None = None,
        ) -> str:
            """Reply to a specific message, creating a threaded conversation.

            This finds or creates a thread for the target event, posts your
            reply into that thread, and auto-mentions the original speaker.
            Pass additional participant IDs in mentions to notify them too.
            """
            adapter._require_space()
            adapter.logger.info(
                "reply_to %s from %s: %s", event_id, adapter.agent_name, text[:80]
            )
            sid = adapter._space_id

            # Fetch original event to get speaker_id for auto-mention
            event_resp = await adapter._request("GET", 
                f"/api/spaces/{sid}/events/{event_id}"
            )
            if event_resp.status_code == 404:
                return json.dumps({"error": f"Event {event_id} not found"})
            original = event_resp.json()

            # Join existing thread or create a new one
            if original.get("thread_id"):
                # Target event is already in a thread — join it
                tid = original["thread_id"]
            else:
                # Find thread rooted at this event, or create one
                thread_resp = await adapter._request("GET", 
                    f"/api/spaces/{sid}/threads/{event_id}"
                )
                if thread_resp.status_code == 404:
                    create_resp = await adapter._request("POST", 
                        f"/api/spaces/{sid}/threads",
                        json={"parent_event_id": event_id},
                    )
                    thread_data = create_resp.json()
                    tid = thread_data["thread_id"]
                else:
                    thread_data = thread_resp.json()
                    tid = thread_data["thread"]["thread_id"]

            # Post reply with auto-mention of original speaker + explicit mentions
            all_mentions = [original["speaker_id"]]
            if mentions:
                all_mentions.extend(m for m in mentions if m not in all_mentions)
            metadata: dict[str, object] = {
                "mentions": all_mentions,
            }
            resp = await adapter._request("POST", 
                f"/api/spaces/{sid}/response",
                json={
                    "agent_id": adapter.agent_id,
                    "agent_name": adapter.agent_name,
                    "text": text,
                    "parent_event_id": event_id,
                    "thread_id": tid,
                    "metadata": metadata,
                },
            )
            if resp.status_code == 409:
                return json.dumps({"error": resp.json().get("detail", "Space not active")})
            data = resp.json()
            return json.dumps({
                "event_id": data.get("event_id", ""),
                "thread_id": data.get("thread_id"),
            })

        @self.mcp.tool()
        async def get_mentions(
            since_event_id: str | None = None,
            limit: int = 20,
            detail: str = "minimal",
        ) -> str:
            """Get events where you are mentioned.

            Returns events directed at this agent via the mentions mechanism.
            Use since_event_id for cursor-based polling.

            detail: "minimal" (count+latest only), "standard" (full text),
                    or "full" (includes metadata, mentions, references).
            """
            adapter._require_space()
            if detail not in ("minimal", "standard", "full"):
                return f"Invalid detail level '{detail}'. Use 'minimal', 'standard', or 'full'."
            adapter.logger.info("get_mentions for %s", adapter.agent_id)
            params: dict[str, str | int] = {"limit": limit}
            if since_event_id:
                params["since"] = since_event_id
            resp = await adapter._request("GET",
                adapter._url(f"/mentions/{adapter.agent_id}"),
                params=params,
            )
            events = _parse_events(resp.json())
            return format_mentions(events, detail=detail, since_event_id=since_event_id)

        @self.mcp.tool()
        async def get_thread(event_id: str) -> str:
            """Get a conversation thread and all its messages.

            Pass the event_id of the message that started the thread.
            Returns the thread metadata and all messages in chronological order.
            """
            adapter._require_space()
            adapter.logger.info("get_thread for event %s", event_id)
            resp = await adapter._request("GET", adapter._url(f"/threads/{event_id}"))
            return resp.text

        @self.mcp.tool()
        async def share(
            text: str,
            mentions: list[str] | None = None,
            message_type: str | None = None,
            parent_event_id: str | None = None,
            thread_id: str | None = None,
        ) -> str:
            """Share a message to the Convo space. All participants will see this.

            Use this to post your response, analysis, or status update to the
            shared space. Optionally mention specific participants, thread to
            an existing message, or categorize the message type.
            """
            adapter._require_space()
            adapter.logger.info("share from %s: %s", adapter.agent_name, text[:80])
            metadata: dict[str, object] = {}
            if mentions:
                metadata["mentions"] = mentions
            if message_type:
                metadata["message_type"] = message_type
            resp = await adapter._request("POST",
                adapter._url("/response"),
                json={
                    "agent_id": adapter.agent_id,
                    "agent_name": adapter.agent_name,
                    "text": text,
                    "parent_event_id": parent_event_id,
                    "thread_id": thread_id,
                    "metadata": metadata or None,
                },
            )
            if resp.status_code == 409:
                return json.dumps({"error": resp.json().get("detail", "Space not active")})
            data = resp.json()
            return json.dumps({
                "event_id": data.get("event_id", ""),
                "thread_id": data.get("thread_id"),
            })

        @self.mcp.tool()
        async def search_spaces(
            query: str,
            scope: str = "linked",
        ) -> str:
            """Search for events across spaces.

            Scope controls which spaces are searched:
            - "current" — search only the current space
            - "linked" — search the current space + all linked spaces (default)
            - "mine" — search all spaces you participate in (requires auth)

            Returns matching events ranked by relevance, with text snippets
            highlighting matched terms.
            """
            adapter._require_space()
            adapter.logger.info(
                "search_spaces from %s: q=%s scope=%s",
                adapter.agent_name,
                query[:60],
                scope,
            )
            params: dict[str, str] = {"q": query}
            if scope == "current":
                params["space_id"] = adapter._space_id  # type: ignore[assignment]
            elif scope == "linked":
                params["linked_to"] = adapter._space_id  # type: ignore[assignment]
            elif scope == "mine":
                pass  # No space filter — auth determines scope
            resp = await adapter._request("GET", "/api/search", params=params)
            return resp.text

        @self.mcp.tool()
        async def link_space(
            link_type: str,
            target_space_id: str | None = None,
            target_uri: str | None = None,
            attributes: dict | None = None,
        ) -> str:
            """Create a link from the current space to another space or external URI.

            Provide exactly one of target_space_id (for space-to-space links)
            or target_uri (for links to external resources like Jira, GitHub, etc.).

            link_type is free-form. Common types: "parent", "related", "follow-up",
            "reference", "external".

            attributes is optional metadata, e.g. {"reason": "sprint planning"}.
            """
            adapter._require_space()
            adapter.logger.info("link_space from %s: type=%s", adapter.agent_name, link_type)
            from typing import Any

            body: dict[str, Any] = {"link_type": link_type}
            if target_space_id:
                body["target_id"] = target_space_id
            if target_uri:
                body["target_uri"] = target_uri
            if attributes:
                body["attributes"] = attributes
            resp = await adapter._request("POST",
                adapter._url("/links"),
                json=body,
            )
            data = resp.json()
            return json.dumps({"link_id": data.get("link_id", "")})

        @self.mcp.tool()
        async def list_links(
            link_type: str | None = None,
        ) -> str:
            """List all links for the current space (both outgoing and incoming).

            Optionally filter by link_type.
            """
            adapter._require_space()
            adapter.logger.info("list_links for %s (type=%s)", adapter.agent_name, link_type)
            params: dict[str, str] = {}
            if link_type:
                params["link_type"] = link_type
            resp = await adapter._request("GET", 
                adapter._url("/links"),
                params=params,
            )
            return resp.text

        @self.mcp.tool()
        async def unlink_space(link_id: str) -> str:
            """Remove a link by its link_id.

            Get link IDs from list_links.
            """
            adapter._require_space()
            adapter.logger.info("unlink_space %s by %s", link_id[:8], adapter.agent_name)
            resp = await adapter._request("DELETE",
                adapter._url(f"/links/{link_id}"),
            )
            return json.dumps({"status": "deleted"})

        @self.mcp.tool()
        async def whoami() -> str:
            """Returns your identity: actor ID, display name, type, and sponsor.

            Requires the adapter to be configured with a CONVO_API_KEY.
            """
            resp = await adapter._request("GET", "/api/actors/me")
            return resp.text

        @self.mcp.tool()
        async def orientation() -> str:
            """Get everything you need to start working in one call.

            Returns your identity, focus space, unread mention count,
            your last status, and space context (summary + recent events).
            Also joins you to the focus space as a side effect.

            Call this on startup instead of whoami + join_space +
            get_context_with_summary + get_mentions.
            """
            adapter.logger.info("orientation for %s", adapter.agent_name)
            resp = await adapter._request("GET", "/api/actors/me/orientation")
            data = resp.json()

            # Cache space_id and actor_id for other tools
            focus = data.get("focus_space")
            if focus:
                adapter._space_id = focus["space_id"]
            identity = data.get("identity", {})
            if identity.get("actor_id"):
                adapter._actor_id = identity["actor_id"]

            # Format as human-readable text
            parts: list[str] = []

            parts.append(
                f"**Identity:** {identity.get('display_name')} "
                f"({identity.get('actor_type')}, "
                f"{'admin' if identity.get('is_admin') else 'non-admin'})"
            )

            if focus:
                parts.append(
                    f"**Focus space:** {focus['space_id']} — "
                    f"{focus.get('description', '(no description)')} "
                    f"[{focus['status']}]"
                )
            else:
                parts.append("**Focus space:** None (no active spaces)")

            unread = data.get("unread_mentions", 0)
            if unread > 0:
                parts.append(f"**Unread mentions:** {unread}")

            last_status = data.get("last_status")
            if last_status:
                parts.append(f"**Last status:** {last_status}")

            participants = data.get("participants", [])
            if participants:
                lines = []
                for p in participants:
                    status_part = f" — {p['status']}" if p.get("status") else ""
                    lines.append(
                        f"  - {p['name']} (`{p['participant_id']}`) "
                        f"{p['participant_type']}{status_part}"
                    )
                parts.append("**Participants:**\n" + "\n".join(lines))

            context = data.get("context")
            if context:
                parts.append(f"\n---\n\n{context}")
            else:
                parts.append(
                    "\n---\n\n*No context available (empty space or no focus space).*"
                )

            return "\n".join(parts)

        @self.mcp.tool()
        async def update_space(
            description: str | None = None,
            status: str | None = None,
            links: list[str] | None = None,
        ) -> str:
            """Update space metadata: description, status, or external links.

            Status can be 'active', 'paused', or 'archived'.
            Links are URIs to external systems (Jira epics, GitHub repos, etc.).
            """
            adapter._require_space()
            body: dict = {}
            if description is not None:
                body["description"] = description
            if status is not None:
                body["status"] = status
            if links is not None:
                body["links"] = links
            resp = await adapter._request("PATCH",
                f"/api/spaces/{adapter._space_id}", json=body
            )
            return json.dumps({"status": "updated"})

        @self.mcp.tool()
        async def schedule_call(
            tool: str,
            args: dict | None = None,
            interval: str | None = None,
            delay: str | None = None,
        ) -> str:
            """Schedule a recurring or one-shot backend call.

            The platform executes the call on your behalf and delivers
            results via channel notification. Only fires when there's
            new data — empty results are suppressed.

            Args:
                tool: Tool to call. Allowed: get_recent_context, get_mentions,
                      get_activity, list_participants, get_space_status.
                args: Arguments for the tool (JSON object). Optional.
                interval: Recurring interval, e.g. "5m", "1h", "90s".
                          Mutually exclusive with delay. Minimum 1 minute.
                delay: One-shot delay, e.g. "10m", "30s".
                       Mutually exclusive with interval. Minimum 30 seconds.

            Returns: JSON with timer_id for cancellation.
            """
            adapter._require_space()
            if not interval and not delay:
                return json.dumps({"error": "Provide either 'interval' or 'delay'"})
            if interval and delay:
                return json.dumps({"error": "'interval' and 'delay' are mutually exclusive"})

            duration_str = interval or delay
            timer_type = "interval" if interval else "delay"

            # Parse duration string (e.g. "5m", "1h", "90s")
            try:
                secs = _parse_duration(duration_str)
            except ValueError as e:
                return json.dumps({"error": str(e)})

            resp = await adapter._request("POST",
                adapter._url("/timers"),
                json={
                    "tool_name": tool,
                    "tool_args": args or {},
                    "timer_type": timer_type,
                    "duration_secs": secs,
                },
            )
            if resp.status_code == 400:
                return json.dumps({"error": resp.json().get("detail", "Bad request")})
            data = resp.json()
            return json.dumps({"timer_id": data.get("timer_id", "")})

        @self.mcp.tool()
        async def cancel_call(timer_id: str) -> str:
            """Cancel a scheduled call by timer_id."""
            adapter._require_space()
            resp = await adapter._request("DELETE",
                adapter._url(f"/timers/{timer_id}"),
            )
            if resp.status_code == 404:
                return json.dumps({"error": "Timer not found or not owned by you"})
            return json.dumps({"status": "cancelled"})

        @self.mcp.tool()
        async def list_calls() -> str:
            """List your active timers in the current space."""
            adapter._require_space()
            resp = await adapter._request("GET", adapter._url("/timers"))
            timers = resp.json()
            if not timers:
                return "No active timers."
            lines = []
            for t in timers:
                tid = t.get("timer_id", "?")
                tool_name = t.get("tool_name", "?")
                ttype = t.get("timer_type", "?")
                dur = t.get("duration_secs", 0)
                fires = t.get("fire_count", 0)
                lines.append(
                    f"- {tid}: {tool_name} ({ttype}, every {dur}s, fired {fires}x)"
                )
            return "\n".join(lines)

        @self.mcp.tool()
        async def archive_session() -> str:
            """Archive the current session transcript before compact/clear.

            Reads your JSONL transcript file, extracts a summary (message count,
            tool call count, duration, model), and stores it in the Convo backend.

            Call this before request_context_reset to preserve session context.
            The archive is associated with your current space.
            """
            adapter._require_space()
            adapter.logger.info("archive_session by %s", adapter.agent_name)

            transcript_path = _find_transcript_path()
            if not transcript_path:
                return json.dumps({"error": "No JSONL transcript file found"})

            stats = _extract_session_stats(transcript_path)
            role = os.environ.get("CONVO_ROLE", "unknown")
            stats["role"] = role

            session_id = os.path.splitext(os.path.basename(transcript_path))[0]
            duration_mins = stats.get("duration_seconds", 0) // 60
            summary = (
                f"Session {session_id} ({role} agent)\n"
                f"Duration: {duration_mins}m | "
                f"Messages: {stats.get('user_message_count', 0)} user, "
                f"{stats.get('message_count', 0) - stats.get('user_message_count', 0)} assistant | "
                f"Tool calls: {stats.get('tool_call_count', 0)}\n"
                f"Model: {stats.get('model', 'unknown')}\n"
                f"Branch: {stats.get('git_branch', 'unknown')}"
            )

            resp = await adapter._request(
                "POST",
                adapter._url("/archives"),
                json={
                    "session_id": session_id,
                    "summary": summary,
                    "metadata": stats,
                },
            )
            if resp.status_code == 409:
                return json.dumps({"error": f"Session {session_id} already archived"})
            data = resp.json()
            return json.dumps({"archive_id": data.get("archive_id", ""), "session_id": session_id})

        @self.mcp.tool()
        async def request_context_reset(mode: str = "compact") -> str:
            """Request a context reset for this agent session.

            Call this when context is getting long or degraded — e.g., after a retro,
            between features, or when you notice confused behavior.

            IMPORTANT: This must be the LAST tool call in your response. Do not
            make any further tool calls or generate additional output after calling
            this. The reset command executes when you finish your current turn.

            Args:
                mode: "compact" (summarize context, default) or "clear" (full wipe + re-prompt)
            """
            role = os.environ.get("CONVO_ROLE", "unknown")
            session = f"convo-{role}"

            if mode not in ("compact", "clear"):
                return f"Invalid mode '{mode}'. Use 'compact' or 'clear'."

            # Verify tmux session exists
            result = await asyncio.create_subprocess_exec(
                "tmux", "has-session", "-t", session,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await result.wait()
            if result.returncode != 0:
                return f"No tmux session '{session}' found. Is this agent running inside tmux?"

            if mode == "compact":
                await asyncio.create_subprocess_exec(
                    "tmux", "send-keys", "-t", session, "/compact", "Enter",
                )
                adapter.logger.info("Context compact requested for %s", role)
                return (
                    "Compact command sent. Your context will be summarized shortly. "
                    "You may notice a brief pause while the compaction runs."
                )
            else:
                await asyncio.create_subprocess_exec(
                    "tmux", "send-keys", "-t", session, "/clear", "Enter",
                )
                await asyncio.sleep(2)
                prompt = (
                    f"Run your startup protocol from CLAUDE.md. "
                    f"You are the {'QA' if role == 'qa' else role.title()} agent."
                )
                await asyncio.create_subprocess_exec(
                    "tmux", "send-keys", "-t", session, prompt, "Enter",
                )
                adapter.logger.info("Context clear + re-prompt requested for %s", role)
                return (
                    "Clear + re-prompt sent. Your context will be wiped and the "
                    "startup protocol will run. This message may be the last thing "
                    "you see from the current context."
                )

    async def auto_join(self) -> None:
        """Auto-join a space if configured via CONVO_SPACE_ID."""
        if not self.auto_space_id:
            return
        self.logger.info("Auto-joining space %s", self.auto_space_id)
        try:
            await self._http.post(
                "/api/spaces",
                json={"space_id": self.auto_space_id},
            )
            await self._http.post(
                f"/api/spaces/{self.auto_space_id}/join",
                json={
                    "participant_id": self.agent_id,
                    "name": self.agent_name,
                    "participant_type": "agent",
                    "agent_adapter": "mcp",
                },
            )
            self._space_id = self.auto_space_id
            self.logger.info("Auto-joined space %s", self.auto_space_id)
        except Exception:
            self.logger.warning(
                "Auto-join failed for %s — use join_space manually",
                self.auto_space_id,
                exc_info=True,
            )

    async def start(self) -> None:
        """Run MCP server in stdio mode (for local agent harnesses)."""
        self.logger.info("Starting MCP server in stdio mode (API: %s)", self.api_url)
        await self.auto_join()
        await self.mcp.run_stdio_async()

    async def start_http(self, host: str = "0.0.0.0", port: int = 8100) -> None:
        """Run MCP server in HTTP mode (for remote/shared access)."""
        self.logger.info("Starting MCP server in HTTP mode on %s:%d", host, port)
        await self.auto_join()
        self.mcp.settings.host = host
        self.mcp.settings.port = port
        await self.mcp.run_streamable_http_async()

    async def stop(self) -> None:
        await self._http.aclose()
