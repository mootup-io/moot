#!/bin/bash
set -euo pipefail

# System packages
sudo apt-get update && sudo apt-get install -y tmux

# Claude Code CLI (npm-installed binary lands on PATH at
# /usr/local/share/npm-global/bin/claude; `claude install` would
# move the native build to ~/.local/bin and delete this symlink,
# breaking the `claude mcp add` lines below — see Run V).
npm install -g @anthropic-ai/claude-code

# Python tooling
pip install uv

# Install moot package
pip install mootup

# Register MCP servers for Claude Code at user scope so claude finds
# them regardless of cwd (agents launch in worktrees under .worktrees/,
# not the project root). Use absolute paths to the wrapper scripts so
# they resolve from any cwd. The wrappers read CONVO_ROLE at runtime
# to look up the per-role API key from .moot/actors.json.
DEVCONTAINER_DIR="$(realpath .devcontainer)"
claude mcp add convo "$DEVCONTAINER_DIR/run-moot-mcp.sh" -s user
claude mcp add convo-channel "$DEVCONTAINER_DIR/run-moot-channel.sh" -s user

echo "Container ready."
