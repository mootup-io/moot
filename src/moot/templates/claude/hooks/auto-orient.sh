#!/bin/bash
# SessionStart hook — emits additionalContext instructing the agent to
# call orientation + list_participants as its first action. Covers
# fresh sessions, /resume, /compact continuations (source field varies
# but the instruction is the same).
set -euo pipefail

# Read stdin JSON (we don't branch on source — the instruction is
# source-agnostic — but we parse it so a future change is a 1-line
# edit).
INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source // "startup"')

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Before your first substantive action this session: call mcp__convo__orientation() to pick up your identity, focus space, and recent context, then call mcp__convo__list_participants(detail='full') to see who else is online. Post a status_update confirming you are ready. Skip this if you have already oriented in the current turn. (Injected by SessionStart hook, source=$SOURCE.)"
  }
}
JSON
