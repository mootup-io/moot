"""Channel adapter -- push notifications through MCP or tmux.

MCP channel delivery backend for NotificationCore. Exposes subscribe,
unsubscribe, and list_subscriptions as MCP tools. Claude Code receives
notifications as JSONRPC notifications via the claude/channel capability;
other harnesses receive the same notifications through tmux stdin injection.

This adapter uses the low-level MCP Server (not FastMCP) because it
needs to declare the experimental claude/channel capability and send
custom notifications from background tasks.
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
from pathlib import Path
from typing import Any

import anyio
from anyio.abc import ObjectSendStream
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification, TextContent, Tool

from moot.adapters.notification_core import NotificationCore
from moot.adapters.tmux_delivery import send_channel_xml_via_tmux

logger = logging.getLogger("convo.channel")


class ChannelAdapter(NotificationCore):
    def __init__(
        self,
        api_url: str,
        api_key: str | None = None,
        agent_id: str = "unknown-agent",
        agent_name: str = "Unknown Agent",
        firehose: bool = False,
        auto_space_id: str | None = None,
    ) -> None:
        super().__init__(
            api_url=api_url,
            api_key=api_key,
            agent_id=agent_id,
            agent_name=agent_name,
            firehose=firehose,
            auto_space_id=auto_space_id,
        )

        # Write stream for pushing Claude channel notifications (set during run).
        self._write_stream: ObjectSendStream[SessionMessage] | None = None

        role = os.environ.get("CONVO_ROLE", agent_id)
        self._tmux_session = os.environ.get("CONVO_TMUX_SESSION") or f"moot-{role}"

        # Agent-local interval state. The task itself lives in _task_group;
        # retaining only its scope keeps replacement and shutdown cancellable.
        self._interval_scope: anyio.CancelScope | None = None
        self._interval_seconds: float | None = None
        self._interval_prompt: str | None = None

        self._server = Server(name="convo-channel", version="0.1.0")
        self._register_tools()

        logger.info(
            "ChannelAdapter created — %s (%s), API %s, auth=%s",
            agent_name,
            agent_id,
            self.api_url,
            "key" if api_key else "none",
        )

    # ── Tools ───────────────────────────────────────────────────────

    def _register_tools(self) -> None:
        adapter = self

        @self._server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="subscribe",
                    description=(
                        "Subscribe to push notifications for all Convo spaces "
                        "you participate in. You'll receive channel notifications "
                        "for mentions, thread replies, and decisions in real time."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "space_id": {
                                "type": "string",
                                "description": "Space ID to subscribe to (optional — omit to subscribe to all spaces)",
                            },
                        },
                        # space_id is NOT required
                    },
                ),
                Tool(
                    name="unsubscribe",
                    description=(
                        "Stop receiving push notifications. "
                        "Pass a space_id to unsubscribe from one space, "
                        "or omit to unsubscribe from all."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "space_id": {
                                "type": "string",
                                "description": "Space ID to unsubscribe from (optional — omit to unsubscribe from all)",
                            },
                        },
                    },
                ),
                Tool(
                    name="list_subscriptions",
                    description="List spaces you're currently subscribed to.",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="set_interval",
                    description=(
                        "Set one agent-local interval that injects a prompt into "
                        "this agent's session. Replaces any existing interval."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "seconds": {
                                "type": "number",
                                "minimum": 60,
                                "description": "Interval in seconds (minimum 60).",
                            },
                            "prompt": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 4096,
                                "description": "Prompt injected into this agent's session.",
                            },
                        },
                        "required": ["seconds", "prompt"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="clear_interval",
                    description="Cancel this agent's local interval, if one is set.",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
            ]

        @self._server.call_tool()
        async def call_tool(
            name: str, arguments: dict[str, Any] | None
        ) -> list[TextContent]:
            args = arguments or {}
            if name == "subscribe":
                space_id = args.get("space_id")
                if space_id:
                    return await adapter._handle_subscribe_space(space_id)
                return await adapter._handle_subscribe_all()
            elif name == "unsubscribe":
                space_id = args.get("space_id")
                if space_id:
                    return await adapter._handle_unsubscribe(space_id)
                return await adapter._handle_unsubscribe_all()
            elif name == "list_subscriptions":
                return await adapter._handle_list_subscriptions()
            elif name == "set_interval":
                return await adapter._handle_set_interval(
                    args.get("seconds"), args.get("prompt")
                )
            elif name == "clear_interval":
                return await adapter._handle_clear_interval()
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _handle_subscribe_space(self, space_id: str) -> list[TextContent]:
        """Join a space and subscribe to its WebSocket stream."""
        if space_id in self._subscriptions:
            return [
                TextContent(
                    type="text",
                    text=f"Already subscribed to {space_id}",
                )
            ]

        # Join the space
        await self._http.post(
            f"/api/spaces/{space_id}/join",
            json={
                "participant_id": self.agent_id,
                "name": self.agent_name,
                "participant_type": "agent",
                "agent_adapter": "channel",
            },
        )

        await self._subscribe_to_space(space_id)

        return [
            TextContent(
                type="text",
                text=f"Subscribed to {space_id}. You'll receive notifications for mentions, thread replies, and decisions.",
            )
        ]

    async def _handle_subscribe_all(self) -> list[TextContent]:
        """Discover all spaces and subscribe to active ones."""
        spaces = await self._discover_spaces()
        new_count = 0
        for space in spaces:
            sid = space["space_id"]
            if sid not in self._subscriptions and space.get("status") == "active":
                await self._subscribe_to_space(sid)
                new_count += 1

        total = len(self._subscriptions)
        if new_count == 0 and total > 0:
            return [
                TextContent(
                    type="text",
                    text=f"Already subscribed to all {total} spaces.",
                )
            ]
        return [
            TextContent(
                type="text",
                text=f"Subscribed to {new_count} new space(s). Total: {total} active subscriptions.",
            )
        ]

    async def _handle_unsubscribe(self, space_id: str) -> list[TextContent]:
        scope = self._subscriptions.pop(space_id, None)
        if scope:
            scope.cancel()
            self._participated_threads.pop(space_id, None)
            logger.info("Unsubscribed from space %s", space_id)
            return [TextContent(type="text", text=f"Unsubscribed from {space_id}")]
        return [TextContent(type="text", text=f"Not subscribed to {space_id}")]

    async def _handle_unsubscribe_all(self) -> list[TextContent]:
        """Unsubscribe from all spaces."""
        count = len(self._subscriptions)
        for scope in self._subscriptions.values():
            scope.cancel()
        self._subscriptions.clear()
        self._participated_threads.clear()
        logger.info("Unsubscribed from all %d spaces", count)
        return [TextContent(type="text", text=f"Unsubscribed from {count} space(s).")]

    async def _handle_list_subscriptions(self) -> list[TextContent]:
        if not self._subscriptions:
            return [TextContent(type="text", text="No active subscriptions")]
        lines = [f"- {sid}" for sid in self._subscriptions]
        return [TextContent(type="text", text="\n".join(lines))]

    # ── Agent-local interval ───────────────────────────────────────

    async def _handle_set_interval(
        self, seconds: Any, prompt: Any
    ) -> list[TextContent]:
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds < 60
        ):
            logger.warning("Rejected agent interval: seconds must be finite and >= 60")
            return [
                TextContent(
                    type="text",
                    text="Error: seconds must be a finite number of at least 60.",
                )
            ]
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 4096:
            prompt_length = len(prompt) if isinstance(prompt, str) else "non-string"
            logger.warning(
                "Rejected agent interval: prompt length must be 1..4096 (got %s)",
                prompt_length,
            )
            return [
                TextContent(
                    type="text",
                    text="Error: prompt must be a string of 1 to 4096 characters.",
                )
            ]
        if self._task_group is None:
            return [
                TextContent(
                    type="text",
                    text="Error: the channel adapter is not running.",
                )
            ]

        replaced = self._interval_scope is not None
        if self._interval_scope is not None:
            self._interval_scope.cancel()
        self._interval_scope = None
        self._interval_seconds = None
        self._interval_prompt = None

        effective_seconds = float(seconds)
        scope = anyio.CancelScope()
        self._interval_scope = scope
        self._interval_seconds = effective_seconds
        self._interval_prompt = prompt
        try:
            self._task_group.start_soon(
                self._interval_loop, scope, effective_seconds, prompt
            )
        except Exception as exc:
            scope.cancel()
            if self._interval_scope is scope:
                self._interval_scope = None
                self._interval_seconds = None
                self._interval_prompt = None
            logger.warning(
                "Failed to start agent interval for %s (%s)",
                self.agent_id,
                type(exc).__name__,
            )
            return [
                TextContent(
                    type="text",
                    text="Error: the agent interval could not be started.",
                )
            ]

        logger.info(
            "%s agent interval for %s: seconds=%s sink=auto",
            "Replaced" if replaced else "Set",
            self.agent_id,
            effective_seconds,
        )
        return [
            TextContent(
                type="text",
                text=f"Agent interval set for every {effective_seconds:g} seconds.",
            )
        ]

    async def _handle_clear_interval(self) -> list[TextContent]:
        scope = self._interval_scope
        if scope is None:
            return [TextContent(type="text", text="No agent interval was set.")]

        self._interval_scope = None
        self._interval_seconds = None
        self._interval_prompt = None
        scope.cancel()
        logger.info("Cleared agent interval for %s", self.agent_id)
        return [TextContent(type="text", text="Agent interval cleared.")]

    async def _interval_loop(
        self,
        scope: anyio.CancelScope,
        seconds: float,
        prompt: str,
    ) -> None:
        meta = {
            "source": "convo",
            "event_type": "agent_interval",
            "agent_id": self.agent_id,
        }
        try:
            with scope:
                while True:
                    await anyio.sleep(seconds)
                    try:
                        await self._push_notification(prompt, meta)
                    except Exception as exc:
                        logger.warning(
                            "Agent interval delivery failed for %s (%s); will retry",
                            self.agent_id,
                            type(exc).__name__,
                        )
        finally:
            if self._interval_scope is scope:
                self._interval_scope = None
                self._interval_seconds = None
                self._interval_prompt = None

    # ── Notification delivery ───────────────────────────────────────

    def _pane_command(self) -> str | None:
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "display-message",
                    "-p",
                    "-t",
                    self._tmux_session,
                    "#{pane_current_command}",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug(
                "Could not inspect tmux pane for session %s: %s",
                self._tmux_session,
                exc,
            )
            return None

        if result.returncode != 0:
            logger.debug(
                "Could not inspect tmux pane for session %s (exit %d): %s",
                self._tmux_session,
                result.returncode,
                result.stderr.strip(),
            )
            return None
        return result.stdout.strip() or None

    def _delivery_backend(self) -> tuple[str, str | None]:
        pane_command = self._pane_command()
        if pane_command is None:
            logger.warning(
                "Could not identify tmux pane command for session %s; using Claude channel backend",
                self._tmux_session,
            )
            return "claude", None

        executable = Path(pane_command).name.lower()
        if executable == "claude":
            return "claude", pane_command
        return "tmux", pane_command

    async def _push_notification(self, content: str, meta: dict[str, str]) -> None:
        backend, pane_command = self._delivery_backend()
        logger.info(
            "Selected %s notification backend for %s (session=%s, pane_command=%s)",
            backend,
            meta.get("event_type", "?"),
            self._tmux_session,
            pane_command or "unknown",
        )

        if backend == "tmux":
            pushed = await send_channel_xml_via_tmux(
                self._tmux_session, content, meta, log_success=False
            )
            if pushed:
                logger.info(
                    "Pushed %s notification via tmux: %s",
                    meta.get("event_type", "?"),
                    content.replace("\n", " ")[:80],
                )
            else:
                logger.warning(
                    "Failed to push %s notification via tmux for session %s",
                    meta.get("event_type", "?"),
                    self._tmux_session,
                )
            return

        await self._push_claude_channel_notification(content, meta)

    async def _push_claude_channel_notification(
        self, content: str, meta: dict[str, str]
    ) -> bool:
        if not self._write_stream:
            logger.warning(
                "Cannot push Claude channel notification -- write stream not available"
            )
            return False
        notification = JSONRPCNotification(
            jsonrpc="2.0",
            method="notifications/claude/channel",
            params={"content": content, "meta": meta},
        )
        message = SessionMessage(message=JSONRPCMessage(notification))
        try:
            await self._write_stream.send(message)
            logger.info(
                "Pushed %s notification via Claude channel: %s",
                meta.get("event_type", "?"),
                content[:80],
            )
            return True
        except anyio.ClosedResourceError:
            logger.warning(
                "Write stream closed, cannot push Claude channel notification"
            )
            return False

    # ── Lifecycle ───────────────────────────────────────────────────

    async def run(self) -> None:
        """Run the channel adapter: MCP stdio server + background tasks."""
        await self.resolve_identity()

        async with stdio_server() as (read_stream, write_stream):
            self._write_stream = write_stream
            init_options = self._server.create_initialization_options(
                notification_options=NotificationOptions(),
                experimental_capabilities={"claude/channel": {}},
            )
            async with anyio.create_task_group() as tg:
                self._task_group = tg

                # Auto-join primary space if specified
                if self.auto_space_id:
                    await self._handle_subscribe_space(self.auto_space_id)

                # Discover and subscribe to all spaces
                await self._handle_subscribe_all()

                # Start background tasks
                tg.start_soon(self._poll_spaces)

                async def run_server() -> None:
                    await self._server.run(read_stream, write_stream, init_options)

                tg.start_soon(run_server)

    async def stop(self) -> None:
        scope = self._interval_scope
        self._interval_scope = None
        self._interval_seconds = None
        self._interval_prompt = None
        if scope is not None:
            scope.cancel()
        await super().stop()
