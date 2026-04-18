#!/bin/bash
# Stop hook — warns when the turn posts an mcp__convo__share (with
# mentions) but does not also call mcp__convo__update_status. Does
# NOT block; emits a system reminder for the next turn via stderr.
set -euo pipefail

INPUT=$(cat)
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
[ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ] && exit 0

# Find the last user-turn boundary: scan backward for the last line
# where type=user and the content is NOT a tool_result or system
# reminder. Everything after that is the current assistant turn.
LAST_USER_LINE=$(awk -v target='"type":"user"' '
    $0 ~ target && $0 !~ /"tool_use_id"/ && $0 !~ /system-reminder/ { last=NR }
    END { print last }
' "$TRANSCRIPT")

[ -z "$LAST_USER_LINE" ] && exit 0

# Slice the turn's assistant entries.
TURN=$(awk -v start="$LAST_USER_LINE" 'NR > start' "$TRANSCRIPT")

# Detect handoff signal: mcp__convo__share or mcp__convo__reply_to
# with a non-empty mentions array.
HANDOFF=$(echo "$TURN" | grep -cE '"name":"mcp__convo__(share|reply_to|reply_to_thread)"' || true)
STATUS=$(echo "$TURN" | grep -cE '"name":"mcp__convo__update_status"' || true)

# Only fire when handoff present AND status_update absent AND the
# share/reply had mentions. Last check: grep the turn for a non-empty
# mentions array on any convo post.
MENTIONS=$(echo "$TURN" | grep -cE '"mentions":\["[^"]' || true)

if [ "$HANDOFF" -gt 0 ] && [ "$MENTIONS" -gt 0 ] && [ "$STATUS" -eq 0 ]; then
    echo "WARNING: handoff message with mentions detected, but no mcp__convo__update_status call this turn. Pipeline handoffs must update status (CLAUDE.md § Status updates on handoff). Next turn should call update_status before returning to idle." >&2
    # Exit 0 — non-blocking warning. stderr lands in the transcript
    # for the operator and is injected as system context next turn.
fi

exit 0
