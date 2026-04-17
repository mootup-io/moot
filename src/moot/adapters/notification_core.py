"""NotificationCore — shared WebSocket, filtering, and formatting logic.

Base class for notification delivery backends. Handles:
- WebSocket connection management with exponential backoff
- Event filtering: mentions, thread participation, decisions, firehose
- Thread participation tracking (seeds from last 200 events)
- Space discovery and auto-subscription (polls every 30s)
- Identity resolution via /api/actors/me
- Notification formatting (500 char truncation)

Subclasses override _push_notification() to deliver notifications
via their specific mechanism (MCP channel, tmux send-keys, etc.).
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import anyio
import httpx
import websockets
from anyio.abc import TaskGroup

from moot.models import ContextEvent

logger = logging.getLogger("convo.notify")


class NotificationCore(ABC):
    def __init__(
        self,
        api_url: str,
        api_key: str | None = None,
        agent_id: str = "unknown-agent",
        agent_name: str = "Unknown Agent",
        firehose: bool = False,
        auto_space_id: str | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.agent_id = agent_id
        self.agent_name = agent_name
        self._firehose = firehose
        self.auto_space_id = auto_space_id

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        ssl_cert = os.environ.get("SSL_CERT_FILE")
        verify: str | bool = ssl_cert if ssl_cert else True
        self._http = httpx.AsyncClient(
            base_url=self.api_url, timeout=30, headers=headers, verify=verify
        )

        # Per-space state
        self._participated_threads: dict[str, set[str]] = {}
        self._subscriptions: dict[str, anyio.CancelScope] = {}
        self._task_group: TaskGroup | None = None

    # ── Space discovery ──────────────────────────────────────────

    async def _discover_spaces(self) -> list[dict]:
        """Query API for all spaces this agent participates in."""
        resp = await self._http.get(
            "/api/actors/me/spaces", params={"status": "active"}
        )
        if resp.status_code != 200:
            logger.warning("Failed to discover spaces: %d", resp.status_code)
            return []
        return resp.json()

    async def _subscribe_to_space(self, space_id: str) -> None:
        """Start WebSocket stream for a space. Assumes already a participant."""
        if space_id in self._subscriptions:
            return
        await self._seed_thread_participation(space_id)
        if self._task_group:
            scope = anyio.CancelScope()
            self._subscriptions[space_id] = scope
            self._task_group.start_soon(self._scoped_stream_loop, space_id, scope)
        logger.info("Subscribed to space %s", space_id)

    async def _poll_spaces(self) -> None:
        """Periodically discover new spaces and subscribe."""
        while True:
            await anyio.sleep(30)
            try:
                spaces = await self._discover_spaces()
                for space in spaces:
                    sid = space["space_id"]
                    if sid not in self._subscriptions and space.get("status") == "active":
                        await self._subscribe_to_space(sid)
                        logger.info("Auto-subscribed to new space %s (via poll)", sid)
            except Exception:
                logger.exception("Error polling for new spaces")

    # ── WebSocket Stream ──────────────────────────────────────────────

    def _ws_url(self, space_id: str) -> str:
        """Build WS URL from HTTP API URL: http→ws, https→wss."""
        base = self.api_url.replace("https://", "wss://").replace("http://", "ws://")
        token = self._http.headers.get("Authorization", "").removeprefix("Bearer ")
        return f"{base}/api/spaces/{space_id}/ws?token={token}"

    async def _scoped_stream_loop(
        self, space_id: str, scope: anyio.CancelScope
    ) -> None:
        with scope:
            await self._stream_loop_with_retry(space_id)

    async def _stream_loop_with_retry(self, space_id: str) -> None:
        logger.info("Starting WS stream loop for %s", space_id)
        backoff = 1
        while True:
            try:
                await self._stream_loop(space_id)
                logger.info("WS stream ended cleanly for %s, reconnecting in %ds", space_id, backoff)
            except (
                websockets.ConnectionClosed,
                websockets.InvalidHandshake,
                OSError,
            ) as e:
                logger.warning(
                    "WS connection lost for %s (%s: %s), reconnecting in %ds",
                    space_id, type(e).__name__, e, backoff,
                )
            except anyio.get_cancelled_exc_class():
                logger.info("WS stream cancelled for %s", space_id)
                return
            except Exception as e:
                logger.exception(
                    "WS unexpected error for %s (%s: %s), reconnecting in %ds",
                    space_id, type(e).__name__, e, backoff,
                )
            await anyio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _stream_loop(self, space_id: str) -> None:
        ws_url = self._ws_url(space_id)
        logger.info("WS connecting to %s", ws_url[:80])
        # websockets requires a truthy ssl= value for wss:// URIs; passing
        # ssl=None is treated as "no TLS" and raises ValueError. Default to
        # True (uses the system CA bundle) and only build a custom context
        # when SSL_CERT_FILE is set (dev stacks with a private CA).
        ssl_cert = os.environ.get("SSL_CERT_FILE")
        ssl_context: Any
        if ssl_cert:
            import ssl
            ssl_context = ssl.create_default_context(cafile=ssl_cert)
        elif ws_url.startswith("wss://"):
            ssl_context = True
        else:
            ssl_context = None  # ws:// — plain TCP, no TLS
        async with websockets.connect(
            ws_url, ssl=ssl_context, open_timeout=10,
            proxy=None,  # disable proxy auto-detection (v16 default)
        ) as ws:
            logger.info("WS connected to %s", space_id)
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._ws_heartbeat_loop, ws)
                async for raw in ws:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")

                    if msg_type == "participant_update":
                        continue  # Channel adapter doesn't use these currently

                    if msg_type != "context_event":
                        continue

                    event = ContextEvent.model_validate(msg["data"])

                    # Don't notify about our own messages
                    if event.speaker_id == self.agent_id:
                        # But track thread participation
                        if event.thread_id:
                            self._participated_threads.setdefault(
                                space_id, set()
                            ).add(event.thread_id)
                        continue

                    relevance = self._check_relevance(space_id, event)
                    if relevance:
                        content = self._format_notification(event, relevance)
                        meta = self._build_meta(space_id, event, relevance)
                        await self._push_notification(content, meta)
                tg.cancel_scope.cancel()  # WS closed, stop heartbeat

    # ── Relevance ───────────────────────────────────────────────────

    def _check_relevance(self, space_id: str, event: ContextEvent) -> str | None:
        meta = event.metadata or {}

        # Mentions — structured (highest priority)
        mentions = meta.get("mentions", [])
        if self.agent_id in mentions:
            return "mention"

        # Mentions — text-based fallback (belt and suspenders)
        if f"@{self.agent_name}".lower() in event.text.lower():
            return "mention"

        # Thread participation
        threads = self._participated_threads.get(space_id, set())
        if event.thread_id and event.thread_id in threads:
            return "thread_reply"

        # Decision lifecycle
        if event.text.startswith("[DECISION"):
            return "decision"
        if meta.get("message_type") == "decision":
            return "decision"

        # Firehose mode
        if self._firehose:
            return "firehose"

        return None

    # ── Formatting ──────────────────────────────────────────────────

    def _format_notification(self, event: ContextEvent, relevance: str) -> str:
        speaker = event.speaker_name
        text = event.text
        if len(text) > 500:
            text = text[:500] + "... [truncated, use get_recent_context for full]"

        if relevance == "mention":
            return f"@you mentioned by {speaker}:\n{text}"
        elif relevance == "thread_reply":
            return f"Thread reply from {speaker}:\n{text}"
        elif relevance == "decision":
            return f"Decision event from {speaker}:\n{text}"
        else:
            return f"{speaker} ({event.speaker_type}):\n{text}"

    def _build_meta(
        self, space_id: str, event: ContextEvent, relevance: str
    ) -> dict[str, str]:
        return {
            "source": "convo",
            "space_id": space_id,
            "event_type": relevance,
            "event_id": event.event_id,
            "speaker": event.speaker_id,
        }

    # ── Heartbeat ───────────────────────────────────────────────────

    async def _ws_heartbeat_loop(self, ws: Any, interval: int = 60) -> None:
        """Send heartbeat over WS connection. Replaces REST POST /actors/me/heartbeat."""
        while True:
            await anyio.sleep(interval)
            await ws.send(json.dumps({"type": "heartbeat"}))
            logger.debug("WS heartbeat sent for %s", self.agent_name)

    # ── Notification delivery (abstract) ───────────────────────────

    @abstractmethod
    async def _push_notification(self, content: str, meta: dict[str, str]) -> None:
        """Deliver a notification. Override in subclass."""

    # ── Thread participation seeding ────────────────────────────────

    async def _seed_thread_participation(self, space_id: str) -> None:
        resp = await self._http.get(
            f"/api/spaces/{space_id}/events",
            params={"limit": 200},
        )
        if resp.status_code != 200:
            return
        events = resp.json()
        threads: set[str] = set()
        for e in events:
            if e.get("speaker_id") == self.agent_id and e.get("thread_id"):
                threads.add(e["thread_id"])
        self._participated_threads[space_id] = threads
        if threads:
            logger.info(
                "Seeded %d thread(s) for %s in space %s",
                len(threads),
                self.agent_id,
                space_id,
            )

    # ── Lifecycle ───────────────────────────────────────────────────

    async def resolve_identity(self) -> None:
        """Resolve agent identity from API key if available."""
        if not self.api_key:
            return
        resp = await self._http.get("/api/actors/me")
        if resp.status_code == 200:
            actor = resp.json()
            self.agent_id = actor["actor_id"]
            self.agent_name = actor["display_name"]
            logger.info(
                "Identity resolved: %s (%s)", self.agent_name, self.agent_id[:8]
            )

    async def stop(self) -> None:
        for scope in self._subscriptions.values():
            scope.cancel()
        self._subscriptions.clear()
        await self._http.aclose()
