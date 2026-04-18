#!/bin/bash
# PreToolUse hook — blocks mutating git commands when the current
# working directory does not match $CONVO_WORKTREE.
#
# Read-only subcommands fall through (exit 0 with no stdout = allow).
# Mutating subcommands emit a deny decision with the exact mismatch.
set -euo pipefail

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Not a Bash tool call, or no command — allow.
[ -z "$CMD" ] && exit 0

# Only care about git invocations. Match `git ` at word start (handles
# leading env overrides like `GIT_PAGER=cat git ...`). Grep is enough;
# we don't need a full parser.
if ! echo "$CMD" | grep -qE '(^|\s|;|&&|\|\|)git(\s|$)'; then
    exit 0
fi

# Denylist of mutating subcommands. Fail-closed: unknown subcommands
# fall through (allow), but matched mutating ones are checked.
MUTATING='commit|merge|reset|rebase|cherry-pick|push|tag|clean\s+-[fd]|stash\s+drop|worktree\s+remove|branch\s+-[dD]|checkout\s+-[bB]'

if ! echo "$CMD" | grep -qE "\\bgit\\s+($MUTATING)\\b"; then
    exit 0
fi

# Mutating command detected. Verify worktree match.
EXPECTED="${CONVO_WORKTREE:-}"
if [ -z "$EXPECTED" ]; then
    # No worktree expectation set — allow (hook can't guard what it
    # doesn't know). This is the case for host-clone sessions outside
    # the agent launchers.
    exit 0
fi

ACTUAL=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
EXPECTED_CANON=$(realpath "$EXPECTED" 2>/dev/null || echo "$EXPECTED")
ACTUAL_CANON=$(realpath "$ACTUAL" 2>/dev/null || echo "$ACTUAL")

if [ "$EXPECTED_CANON" = "$ACTUAL_CANON" ]; then
    exit 0
fi

# Mismatch — block.
REASON="Cross-worktree git mutation blocked: CWD resolves to '$ACTUAL_CANON' but CONVO_WORKTREE is '$EXPECTED_CANON'. Change directory to the expected worktree before running mutating git commands, or unset CONVO_WORKTREE if this is a deliberate host-clone operation."

jq -n --arg reason "$REASON" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $reason
  }
}'
