#!/bin/bash
# MCP adapter wrapper — reads CONVO_ROLE and looks up API key
# from .moot/actors.json. Set CONVO_ROLE before launching Claude Code
# to pick a different identity.

ROLE="${CONVO_ROLE:-implementation}"
ACTORS_FILE=".moot/actors.json"

# Find project root (walk up to moot.toml)
PROJECT_ROOT="$(pwd)"
while [ "$PROJECT_ROOT" != "/" ]; do
    [ -f "$PROJECT_ROOT/moot.toml" ] && break
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done

# Read per-role actor identity from .moot/actors.json. We MUST export
# CONVO_AGENT_ID and CONVO_AGENT_NAME — the mcp_runner defaults them to
# "unknown-agent", and the backend rejects any post whose agent_id in the
# body doesn't match the authenticated actor (HTTP 400, which the adapter
# surfaces as an empty event_id).
if [ -f "$PROJECT_ROOT/$ACTORS_FILE" ]; then
    eval $(python3 -c "
import json, shlex
with open('$PROJECT_ROOT/$ACTORS_FILE') as f:
    data = json.load(f)
entry = data.get('actors', {}).get('$ROLE', {})
print('KEY=' + shlex.quote(entry.get('api_key', '')))
print('AID=' + shlex.quote(entry.get('actor_id', '')))
print('ANAME=' + shlex.quote(entry.get('display_name', '$ROLE')))
" 2>/dev/null)
    if [ -n "$KEY" ]; then
        export CONVO_API_KEY="$KEY"
    else
        echo "WARNING: No API key for role '$ROLE' in $ACTORS_FILE" >&2
    fi
    [ -n "$AID" ] && export CONVO_AGENT_ID="$AID"
    [ -n "$ANAME" ] && export CONVO_AGENT_NAME="$ANAME"
fi

# Read API URL from moot.toml
if [ -z "$CONVO_API_URL" ] && [ -f "$PROJECT_ROOT/moot.toml" ]; then
    URL=$(python3 -c "
import tomllib
with open('$PROJECT_ROOT/moot.toml', 'rb') as f:
    data = tomllib.load(f)
print(data.get('convo', {}).get('api_url', ''))
" 2>/dev/null)
    if [ -n "$URL" ]; then
        export CONVO_API_URL="$URL"
    fi
fi

# Read space ID from moot.toml
if [ -z "$CONVO_SPACE_ID" ] && [ -f "$PROJECT_ROOT/moot.toml" ]; then
    SID=$(python3 -c "
import tomllib
with open('$PROJECT_ROOT/moot.toml', 'rb') as f:
    data = tomllib.load(f)
print(data.get('convo', {}).get('space_id', ''))
" 2>/dev/null)
    if [ -n "$SID" ]; then
        export CONVO_SPACE_ID="$SID"
    fi
fi

# Alpha-grade diagnostics: DEBUG-level logs to a per-role file under
# .moot/logs/ in the project root. Bind-mounted to the host so users
# and support can grep and share the logs without docker exec.
# Override with MOOT_LOG_LEVEL=INFO (or higher) once alpha stabilizes.
LOG_DIR="$PROJECT_ROOT/.moot/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/mcp-${ROLE}.log"
export MOOT_LOG_LEVEL="${MOOT_LOG_LEVEL:-DEBUG}"
exec python -u -m moot.adapters.mcp_runner "$@" 2>> "$LOG_FILE"
