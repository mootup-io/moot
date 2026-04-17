"""Entry point for the Convo Channel adapter.

Usage:
    # stdio mode (for agent harness config):
    python -m moot.adapters.channel_runner

Agent harness configuration (.mcp.json):
    {
        "mcpServers": {
            "convo-channel": {
                "command": "python",
                "args": ["-m", "adapters.channel_runner"],
                "cwd": "/path/to/convo/backend",
                "env": {
                    "CONVO_API_URL": "https://gemoot.com:8443",
                    "CONVO_API_KEY": "<agent-api-key>",
                    "CONVO_CHANNEL_FIREHOSE": "false"
                }
            }
        }
    }

The agent subscribes to spaces at runtime via the `subscribe` tool.
No space ID is required at startup.
"""

from __future__ import annotations

import asyncio
import logging
import os
from moot.adapters.channel_adapter import ChannelAdapter


async def main() -> None:
    # Default to DEBUG during alpha so ops can reconstruct what the adapter
    # actually did when users report "nothing happened" bugs. MOOT_LOG_LEVEL
    # lets us dial it back to INFO/WARNING once alpha stabilizes.
    level_name = os.environ.get("MOOT_LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.DEBUG)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    api_url = os.environ.get("CONVO_API_URL", "http://localhost:8000")
    api_key = os.environ.get("CONVO_API_KEY")
    agent_id = os.environ.get("CONVO_AGENT_ID", "unknown-agent")
    agent_name = os.environ.get("CONVO_AGENT_NAME", agent_id)
    firehose = os.environ.get("CONVO_CHANNEL_FIREHOSE", "").lower() == "true"
    space_id = os.environ.get("CONVO_SPACE_ID")

    adapter = ChannelAdapter(
        api_url=api_url,
        api_key=api_key,
        agent_id=agent_id,
        agent_name=agent_name,
        firehose=firehose,
        auto_space_id=space_id,
    )

    try:
        await adapter.run()
    finally:
        await adapter.stop()


if __name__ == "__main__":
    asyncio.run(main())
