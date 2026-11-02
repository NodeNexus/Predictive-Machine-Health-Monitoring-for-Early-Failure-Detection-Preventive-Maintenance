#!/usr/bin/env bash
# Read-only status of THIS project's processes.
source "$(dirname "$0")/lib.sh"
set -u
if pid_is_ours "$API_PID" "uvicorn app.main:app"; then
  PORT="$(cat "$PORT_FILE" 2>/dev/null)"
  echo "backend : running, pid $(cat "$API_PID"), 127.0.0.1:$PORT"
  echo "health  : $(curl -fsS "http://127.0.0.1:$PORT/api/health" 2>&1 | cut -c1-120)"
else
  echo "backend : not running"
fi
if pid_is_ours "$TUN_PID" "cloudflared"; then
  echo "tunnel  : running, pid $(cat "$TUN_PID")"
  echo "url     : $(cat "$URL_FILE" 2>/dev/null) (changes on restart; no authentication)"
else
  echo "tunnel  : not running"
fi
if [ -f "$RENDER_ENV" ]; then
  if pid_is_ours "$SYNC_PID" "render_sync.sh"; then echo "render  : syncing, pid $(cat "$SYNC_PID") ($(tail -1 "$SYNC_LOG" 2>/dev/null | cut -c1-100))"
  else echo "render  : configured, sync not running"; fi
fi
echo "logs    : $API_LOG , $TUN_LOG"
