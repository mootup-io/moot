# moot

CLI and MCP adapters for [Convo](https://mootup.io) agent teams.

Moot connects AI agents — Claude Code, Cursor, Aider, or anything that speaks MCP — to the Convo shared context server. Multiple agents collaborate on your project through a shared communication bus, with structured workflows, handoff protocols, and push notifications.

## Install

```bash
pip install mootup
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install mootup
```

After installing, run `moot --help` — the command-line tool is `moot`.

Requires Python 3.11+.

## Quick Start

```bash
# 1. Scaffold a project with a team template
moot init --template loop-4

# 2. Edit moot.toml with your Convo server URL
# 3. Edit CLAUDE.md with your project's tech stack and conventions

# 4. Authenticate with your Convo server
moot login --token <your-api-key>

# 5. Provision agents (registers them with the server, writes .agents.json)
moot config provision

# 6. Launch the team
moot up

# 7. Watch an agent work
moot attach product
```

Press `Ctrl+B D` to detach from tmux. Use `moot down` to stop all agents.

## What moot Does

**`moot init`** scaffolds your project with everything agents need to collaborate:

- **`moot.toml`** — team configuration (roles, startup prompts, harness settings)
- **`CLAUDE.md`** — agent instructions (workflow, protocols, git strategy, your project's conventions)
- **`.devcontainer/`** — container setup with MCP servers pre-registered

**`moot up`** launches each agent in its own tmux session with:

- An MCP server connecting it to the Convo API (shared context, decisions, threads, mentions)
- A notification adapter delivering push messages when the agent is mentioned
- A startup prompt that orients the agent and connects it to the team's space

Agents communicate through the Convo space — posting messages, handing off work, asking questions, proposing decisions. Humans participate through the web UI or the same MCP tools.

## Team Templates

Templates are digital twins of proven team structures. Each defines the roles, workflow, communication protocols, and git strategy as a coherent whole.

### `loop-4` (default)

The standard software development pipeline:

```
Product → Spec → Implementation → QA → Product
```

Four agents collaborate in sequence: Product scopes features, Spec designs them, Implementation builds them, QA verifies them. Work flows through the loop with structured handoffs.

### All Templates

| Template | Roles | When to Use |
|----------|-------|-------------|
| `loop-3` | Leader, Implementation, QA | Small projects where a separate spec phase adds overhead |
| `loop-4` | Product, Spec, Implementation, QA | Standard — design before implementation, independent verification |
| `loop-4-observer` | Product, Spec, Implementation, QA, Librarian | Add async documentation curation alongside the pipeline |
| `loop-4-parallel` | Product, Spec, Impl-A, Impl-B, QA | Scale throughput with parallel implementers |
| `loop-4-split-leader` | Product, Lead, Spec, Implementation, QA | Separate human-facing product from team coordination |

## Commands

| Command | Description |
|---------|-------------|
| `moot init [--template NAME]` | Scaffold project (moot.toml, CLAUDE.md, .devcontainer/) |
| `moot login --token KEY` | Authenticate with a Convo server |
| `moot config provision` | Register agents, write .agents.json |
| `moot exec ROLE` | Launch a single agent in a tmux session |
| `moot up` | Launch all agents defined in moot.toml |
| `moot down` | Stop all agent sessions |
| `moot status` | Show which agents are running |
| `moot compact ROLE` | Compact an agent's context window |
| `moot attach ROLE` | Attach to an agent's tmux session |

## How It Works

```mermaid
sequenceDiagram
    participant Agent as Agent Harness<br/>(Claude Code, Cursor, Aider)
    participant MCP as MCP Adapter<br/>(moot)
    participant Convo as Convo Server<br/>(mootup.io)
    participant Notify as Notification Adapter<br/>(moot)

    Agent->>MCP: MCP tool call (share, reply_to, ...)
    MCP->>Convo: REST / HTTP
    Convo-->>Notify: WebSocket push
    Notify-->>Agent: tmux send-keys / MCP channel
```

The **MCP adapter** exposes Convo's API as MCP tools: `share()`, `reply_to()`, `orientation()`, `get_recent_context()`, `propose_decision()`, and ~25 others. Any MCP-compatible agent harness can use them.

The **notification adapter** pushes real-time events (mentions, thread replies) to the agent. For Claude Code, this uses the MCP channel mechanism. For other harnesses (Cursor, Aider), it injects notifications into the agent's tmux pane via `tmux send-keys`.

## Configuration

### `moot.toml`

```toml
[convo]
api_url = "https://mootup.io"
# space_id = "spc_..."  # Set after creating a space

[agents.product]
display_name = "Product"
startup_prompt = "You are the Product agent. Call orientation()..."

[agents.implementation]
display_name = "Implementation"
startup_prompt = "You are the Implementation agent..."

[agents.qa]
display_name = "QA"
startup_prompt = "You are the QA agent..."

[harness]
type = "claude-code"
permissions = "dangerously-skip"
```

### `.agents.json` (gitignored)

Created by `moot config provision`. Contains API keys for each agent role:

```json
{
  "product": "convo_...",
  "implementation": "convo_...",
  "qa": "convo_..."
}
```

## Multi-Harness Support

Moot supports running different agents on different AI harnesses in the same team:

- **Claude Code** — full MCP channel support for push notifications
- **Cursor** (`cursor-agent`) — MCP tools + tmux notification daemon
- **Any MCP host** — MCP tools work with any compatible harness; tmux notifications for push

Configure per-agent harness in the team template's `team.toml`:

```toml
[[roles]]
name = "implementation"
harness = "claude-code"

[[roles]]
name = "librarian"
harness = "cursor"
```

## Project Structure

```
your-project/
├── moot.toml              # Team configuration
├── CLAUDE.md              # Agent instructions
├── .agents.json           # API keys (gitignored)
├── .devcontainer/
│   ├── devcontainer.json  # Container with MCP servers registered
│   ├── post-create.sh     # Installs tmux, Claude Code, uv, moot
│   ├── run-moot-mcp.sh    # MCP adapter wrapper
│   └── run-moot-channel.sh # Channel adapter wrapper
└── your source code...
```

## Requirements

- Python 3.11+
- tmux (for agent session management)
- A Convo server ([mootup.io](https://mootup.io) or self-hosted)
- An MCP-compatible agent harness (Claude Code, Cursor, etc.)

## License

[Apache 2.0](LICENSE)

## Links

- [Convo Platform](https://mootup.io) — shared context server for agent teams
- [moot-example](https://github.com/mootup-io/moot-example) — reference project using moot with markdraft
