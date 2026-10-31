#!/usr/bin/env bash
# Point the Render gateway (deploy/render) at this Pi's current Quick Tunnel.
#   render_sync.sh loop    re-register every 4 minutes while this project's tunnel runs (started by start.sh)
#   render_sync.sh once    register the current URL once
#   render_sync.sh clear   tell the gateway the demo is offline (called by stop.sh)
# Does nothing unless .run/render.env exists with RENDER_GATEWAY_URL and RENDER_TOKEN (see deploy/render/README.md).
# The token is passed to curl from a 600-mode file, never on the command line, so other users on the Pi cannot see it.
source "$(dirname "$0")/lib.sh"
set -u

[ -f "$RENDER_ENV" ] || exit 0
# shellcheck disable=SC1090
source "$RENDER_ENV"
[ -n "${RENDER_GATEWAY_URL:-}" ] && [ -n "${RENDER_TOKEN:-}" ] || die "$RENDER_ENV must set RENDER_GATEWAY_URL and RENDER_TOKEN"
GATEWAY="${RENDER_GATEWAY_URL%/}"

AUTH_HDR="$RUN_DIR/render_auth.hdr"
( umask 077; printf 'Authorization: Bearer %s\n' "$RENDER_TOKEN" > "$AUTH_HDR" )

post() { # <tunnel url or empty>
  # A sleeping free Render instance takes up to about a minute to wake, hence the long timeout.
  curl -fsS --max-time 90 -X POST -H @"$AUTH_HDR" -H 'content-type: application/json' \
    -d "{\"url\":\"$1\"}" "$GATEWAY/__tunnel"
}

case "${1:-once}" in
  once)  post "$(cat "$URL_FILE" 2>/dev/null)" ;;
  clear) post "" ;;
  loop)
    while pid_is_ours "$TUN_PID" "cloudflared"; do
      echo "$(date -Is) $(post "$(cat "$URL_FILE" 2>/dev/null)" 2>&1)"
      sleep 240
    done
    echo "$(date -Is) tunnel stopped; sync loop exiting" ;;
  *) die "usage: render_sync.sh [once|loop|clear]" ;;
esac
