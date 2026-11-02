#!/usr/bin/env bash
# Keeps THIS project's demo running on the Pi. Started by this user's cron (see docs/PI_DEMO.md):
#   autostart.sh boot    @reboot: wait for the network, then run start.sh (backend + Quick Tunnel + Render link update)
#   autostart.sh watch   every 2 min: if the demo, its tunnel or the Render sync is down, or the public tunnel URL stops
#                        answering, run start.sh again (a new Quick Tunnel URL is registered with Render automatically)
# A deliberate `stop.sh` sets .run/manual_stop; `watch` then leaves the demo off until start.sh is run again.
# Touches only this project's processes and files under .run/.
source "$(dirname "$0")/lib.sh"
set -u
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
LOGF="$RUN_DIR/autostart.log"
FAILS="$RUN_DIR/tunnel_fail_count"
log() { echo "$(date -Is) [$1] $2" >> "$LOGF"; }
trim_log() { [ "$(wc -l < "$LOGF" 2>/dev/null || echo 0)" -gt 800 ] && tail -n 400 "$LOGF" > "$LOGF.tmp" && mv "$LOGF.tmp" "$LOGF"; return 0; }

exec 9>"$RUN_DIR/.autostart.lock"
flock -n 9 || exit 0          # another autostart run (start.sh can take a minute) is in progress

run_start() {                 # 9>&- so the backend and tunnel do not inherit (and forever hold) the lock
  bash "$APP_ROOT/deploy/pi/start.sh" >> "$LOGF" 2>&1 9>&-
}

case "${1:-watch}" in
  boot)
    log boot "waiting for the network"
    for _ in $(seq 1 90); do
      getent hosts api.trycloudflare.com >/dev/null 2>&1 && curl -fsS -m 5 -o /dev/null https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null && break
      sleep 2
    done
    rm -f "$STOP_FLAG" "$FAILS"
    for attempt in 1 2 3; do
      if run_start; then log boot "demo started: $(cat "$URL_FILE" 2>/dev/null)"; break; fi
      log boot "start.sh failed (attempt $attempt of 3); retrying in 20 s"; sleep 20
    done ;;
  watch)
    [ -f "$STOP_FLAG" ] && exit 0
    need_start=""
    pid_is_ours "$API_PID" "uvicorn app.main:app" || need_start="backend down"
    pid_is_ours "$TUN_PID" "cloudflared" || need_start="${need_start:+$need_start, }tunnel down"
    if [ -f "$RENDER_ENV" ] && ! pid_is_ours "$SYNC_PID" "render_sync.sh"; then need_start="${need_start:+$need_start, }render sync down"; fi
    if [ -z "$need_start" ] && [ -s "$URL_FILE" ]; then
      # processes are up: also require the public tunnel URL to answer (two misses in a row = dead tunnel)
      if curl -fsS -m 20 -o /dev/null "$(cat "$URL_FILE")/api/health" 2>/dev/null; then rm -f "$FAILS"; exit 0; fi
      n=$(( $(cat "$FAILS" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$FAILS"
      [ "$n" -lt 2 ] && exit 0
      need_start="public tunnel URL not answering"
      if pid_is_ours "$TUN_PID" "cloudflared"; then kill "$(cat "$TUN_PID")" 2>/dev/null; sleep 2; fi
      rm -f "$URL_FILE"
    fi
    [ -z "$need_start" ] && exit 0
    rm -f "$FAILS"
    log watch "$need_start; running start.sh"
    if run_start; then log watch "recovered: $(cat "$URL_FILE" 2>/dev/null)"; else log watch "start.sh failed; will retry on the next run"; fi
    trim_log ;;
  *) echo "usage: autostart.sh [boot|watch]" >&2; exit 2 ;;
esac
