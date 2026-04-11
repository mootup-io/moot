"""Entry point for the MCP space adapter.

Usage:
    # stdio mode (for agent harness config):
    python -m moot.adapters.mcp_runner

    # HTTP mode (for remote access):
    python -m moot.adapters.mcp_runner --transport http --port 8100

    # Custom API URL:
    CONVO_API_URL=https://convo.example.com python -m moot.adapters.mcp_runner

Agent harness configuration (e.g., .mcp.json):
    {
        "mcpServers": {
            "convo": {
                "command": "python",
                "args": ["-m", "adapters.mcp_runner"],
                "cwd": "/path/to/convo/backend",
                "env": {
                    "CONVO_AGENT_ID": "alice-agent",
                    "CONVO_AGENT_NAME": "Alice's Agent",
                    "CONVO_API_URL": "http://localhost:8000"
                }
            }
        }
    }
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from moot.adapters.mcp_adapter import MCPSpaceAdapter


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(description="MCP space adapter")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    api_url = os.environ.get("CONVO_API_URL", "http://localhost:8000")
    api_key = os.environ.get("CONVO_API_KEY")
    agent_id = os.environ.get("CONVO_AGENT_ID", "unknown-agent")
    agent_name = os.environ.get("CONVO_AGENT_NAME", agent_id)
    space_id = os.environ.get("CONVO_SPACE_ID")

    adapter = MCPSpaceAdapter(
        api_url=api_url,
        api_key=api_key,
        agent_id=agent_id,
        agent_name=agent_name,
        auto_space_id=space_id,
    )

    try:
        if args.transport == "http":
            await adapter.start_http(port=args.port)
        else:
            await adapter.start()
    finally:
        await adapter.stop()


if __name__ == "__main__":
    asyncio.run(main())
