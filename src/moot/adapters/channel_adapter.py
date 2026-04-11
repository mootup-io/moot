"""Channel adapter — push notifications to Claude Code via claude/channel.

MCP channel delivery backend for NotificationCore. Exposes subscribe,
unsubscribe, and list_subscriptions as MCP tools, and delivers
notifications as JSONRPC notifications via the claude/channel capability.

This adapter uses the low-level MCP Server (not FastMCP) because it
needs to declare the experimental claude/channel capability and send
custom notifications from background tasks.
"""

from __future__ import annotations

import logging
from typing import Any

import anyio
from anyio.abc import ObjectSendStream
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification, TextContent, Tool

from moot.adapters.notification_core import NotificationCore

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

        # Write stream for pushing notifications (set during run)
        self._write_stream: ObjectSendStream[SessionMessage] | None = None

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
            return [TextContent(
                type="text",
                text=f"Already subscribed to all {total} spaces.",
            )]
        return [TextContent(
            type="text",
            text=f"Subscribed to {new_count} new space(s). Total: {total} active subscriptions.",
        )]

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

    # ── Notification delivery ───────────────────────────────────────

    async def _push_notification(self, content: str, meta: dict[str, str]) -> None:
        if not self._write_stream:
            logger.warning("Cannot push notification — write stream not available")
            return
        notification = JSONRPCNotification(
            jsonrpc="2.0",
            method="notifications/claude/channel",
            params={"content": content, "meta": meta},
        )
        message = SessionMessage(message=JSONRPCMessage(notification))
        try:
            await self._write_stream.send(message)
            logger.info(
                "Pushed %s notification: %s",
                meta.get("event_type", "?"),
                content[:80],
            )
        except anyio.ClosedResourceError:
            logger.warning("Write stream closed, cannot push notification")

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
