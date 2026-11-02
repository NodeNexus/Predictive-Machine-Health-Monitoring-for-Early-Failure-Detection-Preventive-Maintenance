#!/usr/bin/env bash
# Stop THIS project only. It signals exactly the two pids recorded in .run/ and only after confirming that each
# one's command line is still this project's backend or tunnel. Nothing else on the Pi is touched.
source "$(dirname "$0")/lib.sh"
set -u

stop_one() { # <label> <pidfile> <cmdline fragment>
  local label="$1" file="$2" frag="$3"
  if pid_is_ours "$file" "$frag"; then
    local pid; pid="$(cat "$file")"
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 15); do [ -d "/proc/$pid" ] || break; sleep 1; done
    if [ -d "/proc/$pid" ]; then kill -9 "$pid" 2>/dev/null; echo "$label: did not exit on TERM; killed pid $pid"; else echo "$label: stopped (pid $pid)"; fi
  elif [ -f "$file" ]; then
    echo "$label: pid file is stale (process gone or not ours); left no process running by this project"
  else
    echo "$label: not running"
  fi
  rm -f "$file"
}

# Remember the deliberate stop so the autostart watchdog (autostart.sh) does not bring the demo back.
touch "$STOP_FLAG"
# A running demo session holds no external resources; stopping the backend ends it.
stop_one "sync   " "$SYNC_PID" "render_sync.sh"
stop_one "tunnel " "$TUN_PID" "cloudflared"
[ -f "$RENDER_ENV" ] && bash "$(dirname "$0")/render_sync.sh" clear >/dev/null 2>&1 && echo "render : gateway now shows the offline page"
stop_one "backend" "$API_PID" "uvicorn app.main:app"
rm -f "$URL_FILE" "$PORT_FILE"
echo "done. The public URL is no longer valid."
