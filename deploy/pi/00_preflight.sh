#!/usr/bin/env bash
# READ-ONLY inspection of a (shared) Raspberry Pi before deploying anything.
# Changes nothing: it only reads system state. Run it on the Pi:  bash deploy/pi/00_preflight.sh
set -u

hr() { printf '\n== %s\n' "$1"; }

hr "Hardware / OS"
cat /proc/device-tree/model 2>/dev/null | tr -d '\0'; echo
. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"
echo "kernel: $(uname -r)  arch: $(uname -m)  userland: $(dpkg --print-architecture 2>/dev/null || echo unknown)"
[ "$(uname -m)" = "aarch64" ] || echo "!! NOT 64-bit ARM: the pinned numpy/scipy/torch wheels need aarch64"

hr "Python"
for p in python3 python3.11 python3.12 python3.13; do command -v "$p" >/dev/null && echo "$p -> $($p --version 2>&1)"; done
python3 -c "import venv, ensurepip" 2>/dev/null && echo "venv/ensurepip: available" || echo "!! python3-venv missing (installing it is a system change: ask first)"
echo "glibc: $(ldd --version 2>&1 | head -1)  (torch aarch64 wheels need >= 2.28)"

hr "Memory and disk"
free -h | head -2
swapon --show 2>/dev/null | head -3
df -h / "$HOME" 2>/dev/null | awk 'NR==1 || !seen[$1]++'
echo "(demo data needs: models ~7 MB, one video 190-375 MB, IMS 1st_test 2.5 GB full / ~160 MB first 141 files)"

hr "cloudflared"
if command -v cloudflared >/dev/null; then cloudflared --version; else echo "not installed on PATH"; fi
[ -x "$(dirname "$0")/../../.run/bin/cloudflared" ] && echo "project-local copy present"

hr "Listening TCP ports (who owns them) - this project must NOT take any of these"
ss -ltnpH 2>/dev/null | awk '{printf "%-24s %s\n", $4, $6}' | sort -u
echo
echo "candidate range for this project: 18080-18199; already in use there:"
ss -ltnH 2>/dev/null | awk '{print $4}' | sed 's/.*://' | awk '$1>=18080 && $1<=18199' | sort -n | tr '\n' ' '; echo "(none above = all free)"

hr "Existing services, containers, proxies and tunnels (read only)"
systemctl list-units --type=service --state=running --no-legend 2>/dev/null | awk '{print "service:", $1}' | head -40
command -v docker >/dev/null && { echo "docker containers:"; docker ps --format '  {{.Names}}  {{.Ports}}' 2>&1 | head -20; }
ps -eo pid,user,args 2>/dev/null | grep -E "nginx|caddy|apache|traefik|haproxy|cloudflared|ngrok|tailscaled|uvicorn|gunicorn|node " | grep -v grep | cut -c1-150

hr "Firewall (read only)"
command -v ufw >/dev/null && (sudo -n ufw status 2>/dev/null || echo "ufw present; status needs sudo (not run)")

echo
echo "Done. Nothing was changed. Save this output; compare against the same listing after deployment."
