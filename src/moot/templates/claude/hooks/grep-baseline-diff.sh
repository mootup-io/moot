#!/bin/bash
# PostToolUse hook — caches Grep results keyed by (pattern, path) and
# warns when an identical grep returns a different count within the
# same session. Non-blocking.
set -euo pipefail

INPUT=$(cat)
SESSION=$(echo "$INPUT" | jq -r '.session_id // empty')
PATTERN=$(echo "$INPUT" | jq -r '.tool_input.pattern // empty')
SEARCH_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // "."')
RESPONSE=$(echo "$INPUT" | jq -r '.tool_response // empty')

[ -z "$SESSION" ] || [ -z "$PATTERN" ] && exit 0

CACHE=/tmp/convo-grep-cache-"$SESSION".json
KEY=$(echo "${PATTERN}|${SEARCH_PATH}" | sha256sum | cut -d' ' -f1)

# Count matches in this response — the Grep tool's output format
# varies by output_mode; use line count as a cheap proxy.
COUNT=$(echo "$RESPONSE" | wc -l)

# Read prior count if cached.
PRIOR=""
if [ -f "$CACHE" ]; then
    PRIOR=$(jq -r --arg k "$KEY" '.[$k] // empty' "$CACHE" 2>/dev/null || echo "")
fi

# Write current count back to cache.
mkdir -p "$(dirname "$CACHE")"
if [ -f "$CACHE" ]; then
    jq --arg k "$KEY" --argjson v "$COUNT" '.[$k] = $v' "$CACHE" > "$CACHE.tmp" && mv "$CACHE.tmp" "$CACHE"
else
    jq -n --arg k "$KEY" --argjson v "$COUNT" '{($k): $v}' > "$CACHE"
fi

# Warn if count drifted.
if [ -n "$PRIOR" ] && [ "$PRIOR" != "$COUNT" ]; then
    echo "NOTICE: grep baseline drift — pattern='$PATTERN' path='$SEARCH_PATH' prior=$PRIOR current=$COUNT. A baseline measured earlier this session no longer matches; if you are mid-spec, re-ground before treating the current count as the new baseline." >&2
fi

exit 0
