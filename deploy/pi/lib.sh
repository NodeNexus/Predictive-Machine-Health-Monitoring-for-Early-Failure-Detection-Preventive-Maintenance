#!/usr/bin/env bash
# Shared settings for the demo scripts. Sourced, not run.
# Everything this project creates on the Pi lives under $APP_ROOT/.run (pid files, logs, port, tunnel URL).
# No system service, proxy config, firewall rule or shared path is touched.

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="$APP_ROOT/.run"
mkdir -p "$RUN_DIR"

APP_NAME="mmhm-demo"                       # unique name for this project's processes and files
PORT_FILE="$RUN_DIR/port"
API_PID="$RUN_DIR/backend.pid"
TUN_PID="$RUN_DIR/tunnel.pid"
API_LOG="$RUN_DIR/backend.log"
TUN_LOG="$RUN_DIR/tunnel.log"
URL_FILE="$RUN_DIR/public_url"
RENDER_ENV="$RUN_DIR/render.env"            # optional: Render gateway URL + token (docs/RENDER_GATEWAY.md)
SYNC_PID="$RUN_DIR/render_sync.pid"
SYNC_LOG="$RUN_DIR/render_sync.log"
STOP_FLAG="$RUN_DIR/manual_stop"           # set by stop.sh: autostart.sh then leaves the demo off until start.sh is run
PY="$APP_ROOT/backend/.venv/bin/python"

# cloudflared: the one on PATH, else a copy kept inside this project (never installed system-wide).
CLOUDFLARED="${CLOUDFLARED:-$(command -v cloudflared || true)}"
if [ -z "$CLOUDFLARED" ] && [ -x "$RUN_DIR/bin/cloudflared" ]; then CLOUDFLARED="$RUN_DIR/bin/cloudflared"; fi

die() { echo "ERROR: $*" >&2; exit 1; }
port_in_use() { ss -ltnH "( sport = :$1 )" 2>/dev/null | grep -q .; }

# pid_is_ours <pidfile> <cmdline fragment>: true only if the pid is alive AND its command line matches.
# This is what stops stop.sh from ever signalling a process that merely reused the number.
pid_is_ours() {
  [ -f "$1" ] || return 1
  local pid; pid="$(cat "$1")"
  [ -d "/proc/$pid" ] || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q -- "$2"
}
