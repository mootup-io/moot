"""TmuxDelivery -- push notifications via tmux send-keys.

Notification delivery backend for CLI agents that don't support MCP
channel notifications (Cursor, Aider, etc.). Injects formatted
<channel> XML into the agent's tmux pane stdin.

Runs as a standalone background daemon alongside the agent process.
"""

from __future__ import annotations

import logging

import anyio

from moot.adapters.notification_core import NotificationCore

logger = logging.getLogger("convo.tmux")


class TmuxDelivery(NotificationCore):
    def __init__(
        self,
        api_url: str,
        tmux_session: str,
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
        self._tmux_session = tmux_session
        logger.info(
            "TmuxDelivery created -- %s (%s), session=%s, API %s, auth=%s",
            agent_name,
            agent_id,
            tmux_session,
            self.api_url,
            "key" if api_key else "none",
        )

    # -- Notification delivery -----------------------------------------------

    async def _push_notification(self, content: str, meta: dict[str, str]) -> None:
        """Inject notification into tmux pane as a <channel> XML block."""
        # Build <channel> XML -- single line for clean stdin injection
        attrs = " ".join(f'{k}="{v}"' for k, v in meta.items())
        flat_content = content.replace("\n", " ")
        text = f"<channel {attrs}>{flat_content}</channel>"

        try:
            # -l: literal text (no key name interpretation)
            result = await anyio.run_process(
                ["tmux", "send-keys", "-t", self._tmux_session, "-l", text],
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode().strip() if result.stderr else ""
                logger.warning(
                    "tmux send-keys failed (exit %d): %s -- session '%s' may not exist",
                    result.returncode,
                    stderr,
                    self._tmux_session,
                )
                return

            # Press Enter to submit the text as input
            await anyio.run_process(
                ["tmux", "send-keys", "-t", self._tmux_session, "Enter"],
                check=False,
            )
            logger.info(
                "Pushed %s notification via tmux: %s",
                meta.get("event_type", "?"),
                flat_content[:80],
            )
        except Exception:
            logger.exception("Failed to inject notification via tmux")

    # -- Space joining -------------------------------------------------------

    async def _join_space(self, space_id: str) -> None:
        """Join a space via the API. Idempotent -- safe to call if already joined."""
        resp = await self._http.post(
            f"/api/spaces/{space_id}/join",
            json={
                "participant_id": self.agent_id,
                "name": self.agent_name,
                "participant_type": "agent",
                "agent_adapter": "tmux",
            },
        )
        if resp.status_code in (200, 201):
            logger.info("Joined space %s", space_id)
        else:
            logger.warning(
                "Failed to join space %s: %d", space_id, resp.status_code
            )

    # -- Lifecycle -----------------------------------------------------------

    async def run(self) -> None:
        """Run the tmux notification daemon."""
        await self.resolve_identity()

        async with anyio.create_task_group() as tg:
            self._task_group = tg

            # Join and subscribe to primary space if specified
            if self.auto_space_id:
                await self._join_space(self.auto_space_id)
                await self._subscribe_to_space(self.auto_space_id)

            # Discover and subscribe to all spaces the agent participates in
            spaces = await self._discover_spaces()
            for space in spaces:
                sid = space["space_id"]
                if sid not in self._subscriptions and space.get("status") == "active":
                    await self._subscribe_to_space(sid)

            # Poll for new spaces in background
            tg.start_soon(self._poll_spaces)

            logger.info(
                "TmuxDelivery running -- %d space(s), session=%s",
                len(self._subscriptions),
                self._tmux_session,
            )
            # Task group keeps running until cancelled (SIGTERM/SIGINT)
