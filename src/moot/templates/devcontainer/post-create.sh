#!/bin/bash
set -e

# System packages
sudo apt-get update && sudo apt-get install -y tmux

# Claude Code CLI
npm install -g @anthropic-ai/claude-code
claude install

# Python tooling
pip install uv

# Install moot package
pip install moot

# Register MCP servers for Claude Code.
# The wrapper scripts read CONVO_ROLE and look up API keys from
# .agents.json at runtime — no keys needed here.
claude mcp add convo .devcontainer/run-moot-mcp.sh -s local
claude mcp add convo-channel .devcontainer/run-moot-channel.sh -s local

echo "Setup complete. Next: moot login --token <key>, then moot config provision"
