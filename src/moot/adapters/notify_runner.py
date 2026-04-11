"""Entry point for the tmux notification daemon.

Usage:
    python -m moot.adapters.notify_runner --session convo-spec

    # With environment:
    CONVO_API_URL=https://gemoot.com:8443 \
    CONVO_API_KEY=convo_xxx \
    CONVO_ROLE=librarian \
    python -m moot.adapters.notify_runner

Runner script derives session name from CONVO_ROLE if --session
is not provided: convo-{role} (devcontainer) or moot-{role} (moot CLI).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from moot.adapters.tmux_delivery import TmuxDelivery


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser(description="Tmux notification daemon")
    parser.add_argument(
        "--session",
        default=None,
        help="Target tmux session name (default: convo-{CONVO_ROLE})",
    )
    args = parser.parse_args()

    api_url = os.environ.get("CONVO_API_URL", "http://localhost:8000")
    api_key = os.environ.get("CONVO_API_KEY")
    role = os.environ.get("CONVO_ROLE", "unknown")
    firehose = os.environ.get("CONVO_CHANNEL_FIREHOSE", "").lower() == "true"
    space_id = os.environ.get("CONVO_SPACE_ID")

    # Session name: explicit > CONVO_TMUX_SESSION env > convo-{role}
    tmux_session = (
        args.session
        or os.environ.get("CONVO_TMUX_SESSION")
        or f"convo-{role}"
    )

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
