#!/usr/bin/env bash
# One-time setup, entirely inside this project folder (creates backend/.venv and installs into it).
# Needs: 64-bit OS, python3 with venv, internet. Installs NO system packages and edits NO system files.
# Run on the Pi:  bash deploy/pi/01_setup.sh
source "$(dirname "$0")/lib.sh"
set -euo pipefail

[ "$(uname -m)" = "aarch64" ] || die "this OS is $(uname -m), not 64-bit ARM; the pinned wheels (numpy, scipy, torch) will not install"
command -v python3 >/dev/null || die "python3 not found"
python3 -c "import venv, ensurepip" 2>/dev/null || die "python3-venv is missing. Installing it is a system change: ask the owner, then run: sudo apt install python3-venv"

cd "$APP_ROOT/backend"
if [ ! -x "$PY" ]; then
  echo "creating backend/.venv ..."
  python3 -m venv .venv
fi
"$PY" -m pip install --quiet --upgrade pip
echo "installing backend requirements (prebuilt aarch64 wheels; this takes several minutes) ..."
"$PY" -m pip install -r requirements.txt
# The thermal classifier needs PyTorch. Use PyTorch's CPU-only build: the aarch64 wheel on PyPI depends on several GB of
# NVIDIA CUDA libraries that a Raspberry Pi cannot use. --no-cache-dir keeps the large download out of the shared pip cache.
echo "installing CPU-only torch / torchvision ..."
"$PY" -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple   torch==2.14.0 torchvision==0.29.0

echo
echo "checking that the models really load on this machine ..."
"$PY" "$APP_ROOT/deploy/pi/check_models.py"
