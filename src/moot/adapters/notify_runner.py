"""Entry point for the tmux notification daemon.

Usage:
    python -m moot.adapters.notify_runner --session moot-spec

    # With environment:
    CONVO_API_URL=https://gemoot.com:8443 \
    CONVO_API_KEY=convo_xxx \
    CONVO_ROLE=librarian \
    python -m moot.adapters.notify_runner

Runner script derives session name from CONVO_ROLE if --session
is not provided: moot-{role}.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from moot.adapters.tmux_delivery import TmuxDelivery


def default_tmux_session(role: str, explicit_session: str | None = None) -> str:
    return explicit_session or os.environ.get("CONVO_TMUX_SESSION") or f"moot-{role}"


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser(description="Tmux notification daemon")
    parser.add_argument(
        "--session",
        default=None,
        help="Target tmux session name (default: moot-{CONVO_ROLE})",
    )
    args = parser.parse_args()

    api_url = os.environ.get("CONVO_API_URL", "http://localhost:8000")
    api_key = os.environ.get("CONVO_API_KEY")
    role = os.environ.get("CONVO_ROLE", "unknown")
    firehose = os.environ.get("CONVO_CHANNEL_FIREHOSE", "").lower() == "true"
    space_id = os.environ.get("CONVO_SPACE_ID")

    # Session name: explicit > CONVO_TMUX_SESSION env > moot-{role}
    tmux_session = default_tmux_session(role, args.session)

    daemon = TmuxDelivery(
        api_url=api_url,
        tmux_session=tmux_session,
        api_key=api_key,
        firehose=firehose,
        auto_space_id=space_id,
    )

    # Graceful shutdown on SIGTERM/SIGINT
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(daemon.stop()))

    try:
        await daemon.run()
    finally:
        await daemon.stop()


if __name__ == "__main__":
    asyncio.run(main())
