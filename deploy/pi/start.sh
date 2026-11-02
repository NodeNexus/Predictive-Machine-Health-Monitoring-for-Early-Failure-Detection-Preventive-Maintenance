#!/usr/bin/env bash
# Start THIS project only: its backend (which also serves the dashboard) and a Cloudflare Quick Tunnel.
# Picks a free port, never takes over one that is in use, and binds to 127.0.0.1 only (not the LAN).
# Prints the public URL. Stop with deploy/pi/stop.sh.
source "$(dirname "$0")/lib.sh"
set -uo pipefail

rm -f "$STOP_FLAG"   # a manual start re-enables the autostart watchdog
[ -x "$PY" ] || die "backend/.venv not found. Run deploy/pi/01_setup.sh first"
[ -f "$APP_ROOT/frontend/dist/index.html" ] || die "frontend/dist is missing. Build it on the development PC (npm run build) and copy it here"
[ -n "$CLOUDFLARED" ] || die "cloudflared not found. Install it, or place a copy at $RUN_DIR/bin/cloudflared (see docs/PI_DEMO.md)"

# ---- backend -------------------------------------------------------------------------------------------
if pid_is_ours "$API_PID" "uvicorn app.main:app"; then
  PORT="$(cat "$PORT_FILE")"
  echo "backend already running on 127.0.0.1:$PORT"
else
  PORT="${MMHM_PORT:-}"
  if [ -z "$PORT" ]; then
    for candidate in $(seq 18080 18199); do
      if ! port_in_use "$candidate"; then PORT="$candidate"; break; fi
    done
  fi
  [ -n "$PORT" ] || die "no free port found in 18080-18199"
  port_in_use "$PORT" && die "port $PORT is already in use; not taking it over. Set MMHM_PORT to a free port"
  echo "$PORT" > "$PORT_FILE"

  cd "$APP_ROOT/backend"
  IDEALAB_SERVE_FRONTEND_DIR="$APP_ROOT/frontend/dist" IDEALAB_VIDEO_PREVIEW_DIR="$APP_ROOT/VIDEO_preview" IDEALAB_ENVIRONMENT=production \
    nohup "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$API_LOG" 2>&1 &
  echo $! > "$API_PID"
  echo "starting backend on 127.0.0.1:$PORT (pid $(cat "$API_PID")) ..."
  for _ in $(seq 1 120); do
    curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
    pid_is_ours "$API_PID" "uvicorn app.main:app" || { tail -20 "$API_LOG"; die "backend exited during startup (see $API_LOG)"; }
    sleep 1
  done
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 || die "backend did not answer within 120 s (see $API_LOG)"
fi
echo "local health: $(curl -fsS "http://127.0.0.1:$PORT/api/health")"

# ---- Quick Tunnel --------------------------------------------------------------------------------------
if pid_is_ours "$TUN_PID" "cloudflared"; then
  echo "tunnel already running"
else
  : > "$TUN_LOG"
  nohup "$CLOUDFLARED" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" > "$TUN_LOG" 2>&1 &
  echo $! > "$TUN_PID"
  echo "starting Quick Tunnel (pid $(cat "$TUN_PID")) ..."
  for _ in $(seq 1 60); do
    grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUN_LOG" | head -1 > "$URL_FILE"
    [ -s "$URL_FILE" ] && break
    pid_is_ours "$TUN_PID" "cloudflared" || { tail -20 "$TUN_LOG"; die "cloudflared exited (see $TUN_LOG)"; }
    sleep 1
  done
  [ -s "$URL_FILE" ] || die "no tunnel URL after 60 s (see $TUN_LOG)"
fi

# ---- Render gateway (optional) -------------------------------------------------------------------------
if [ -f "$RENDER_ENV" ]; then
  if pid_is_ours "$SYNC_PID" "render_sync.sh"; then
    bash "$APP_ROOT/deploy/pi/render_sync.sh" once >/dev/null 2>&1 # tunnel may have restarted: register now
  else
    nohup bash "$APP_ROOT/deploy/pi/render_sync.sh" loop >> "$SYNC_LOG" 2>&1 &
    echo $! > "$SYNC_PID"
  fi
  # shellcheck disable=SC1090
  GATEWAY_URL="$(source "$RENDER_ENV"; echo "${RENDER_GATEWAY_URL%/}")"
fi

echo
echo "================================================================"
echo " Public URL : $(cat "$URL_FILE")"
echo " This URL changes every time the tunnel restarts."
[ -n "${GATEWAY_URL:-}" ] && echo " Stable URL : $GATEWAY_URL (Render; follows the tunnel, may take ~1 min to wake)"
echo " It has NO authentication: anyone who has it can open the dashboard"
echo " and use its Start/Stop controls. Stop the demo when you are done:"
echo "   bash deploy/pi/stop.sh"
echo "================================================================"
