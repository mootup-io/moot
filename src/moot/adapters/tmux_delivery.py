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


def format_channel_xml(content: str, meta: dict[str, str]) -> str:
    """Format a channel notification as one XML-ish line for stdin injection."""
    attrs = " ".join(f'{k}="{v}"' for k, v in meta.items())
    flat_content = content.replace("\n", " ")
    return f"<channel {attrs}>{flat_content}</channel>"


async def send_channel_xml_via_tmux(
    tmux_session: str,
    content: str,
    meta: dict[str, str],
    *,
    log_success: bool = True,
    enter_delay_seconds: float = 1.0,
) -> bool:
    """Inject a channel notification into a tmux pane.

    Returns True only after both the literal text and delayed carriage return were sent.
    """
    text = format_channel_xml(content, meta)
    flat_content = content.replace("\n", " ")

    try:
        result = await anyio.run_process(
            ["tmux", "send-keys", "-t", tmux_session, "-l", text],
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode().strip() if result.stderr else ""
            logger.warning(
                "tmux send-keys failed (exit %d): %s -- session '%s' may not exist",
                result.returncode,
                stderr,
                tmux_session,
            )
            return False

        # Wait a full second before the submit key. A payload over ~1KiB
        # arrives in the pane as one bracketed paste; a C-m sent inside the
        # paste-accumulation window is absorbed into the buffer instead of
        # submitting, and the seat then sits on `[Pasted Content NNNN chars]`
        # looking healthy with its ring blocked. 1s is the value validated on
        # the ken fleet; shorter delays (0.15s previously) strand codex panes.
        await anyio.sleep(enter_delay_seconds)
        enter = await anyio.run_process(
            ["tmux", "send-keys", "-t", tmux_session, "C-m"],
            check=False,
        )
        if enter.returncode != 0:
            stderr = enter.stderr.decode().strip() if enter.stderr else ""
            logger.warning(
                "tmux C-m send failed (exit %d): %s -- session '%s' may not exist",
                enter.returncode,
                stderr,
                tmux_session,
            )
            return False

        if log_success:
            logger.info(
                "Pushed %s notification via tmux: %s",
                meta.get("event_type", "?"),
                flat_content[:80],
            )
        return True
    except Exception:
        logger.exception("Failed to inject notification via tmux")
        return False


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
        await send_channel_xml_via_tmux(self._tmux_session, content, meta)

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
            logger.warning("Failed to join space %s: %d", space_id, resp.status_code)

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
