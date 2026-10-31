# Raspberry Pi demo: run the dashboard behind a Cloudflare Quick Tunnel

**Status: deployed and verified on the Pi** (Raspberry Pi 4 Model B, 7.6 GB, Debian 13, Python 3.13, 64-bit) in
`~/mmhm-demo`, port 18080 (localhost only). Run `bash deploy/pi/status.sh` for the current Quick Tunnel URL.

## Design (nothing shared is touched)

- **One origin, no reverse proxy.** The project's own backend also serves the built dashboard
  (`IDEALAB_SERVE_FRONTEND_DIR=frontend/dist`, off by default). `/`, `/api/...`, `/api/demo/thermal-video` (Range
  supported) and `/ws/telemetry` all live on one local port, so one Quick Tunnel carries everything and the browser
  uses `wss://` automatically on the public URL. No nginx/caddy, no Vite, no Node on the Pi.
- **Own port, never taken over.** `start.sh` picks the first free port in `18080-18199` (or `MMHM_PORT`) and refuses a
  port that is in use. It listens on `127.0.0.1` only, not the LAN.
- **Own files and processes.** Everything lives under `<project>/.run/` (pid files, logs, port, URL). No systemd unit,
  proxy config, firewall rule or package is installed. `stop.sh` signals only the two pids it recorded, and only after
  confirming each command line is still this project's backend or `cloudflared`.

## What must be copied (list first, then copy; nothing is overwritten)

| What | Size | How |
|---|---|---|
| Source package: `backend`, built `frontend/dist`, `models`, `data/manifests`, `deploy`, `ml`, `scripts` (no DB, venv, logs or data) | 9.5 MB | one `tar` stream, into a NEW empty folder |
| Minimal demo data, `deploy/pi/demo_data_minimal.txt`: videos 3 and 4, the demo wav, IMS first 141 files, 18 example images | 162 files, 563 MB | `tar` stream with `--keep-old-files` |
| *Optional full data*: all 7 videos ~2.0 GB, full IMS `1st_test` 2.5 GB | ~4.5 GB | same method |

Minimal data supports: videos 3 and 4, the **Healthy** vibration run, the sound clip, the held-out examples. Other
dropdown entries return a clear "source cannot be replayed" message until their files are present. Models are small and
are inside the package (the thermal weights are 6.2 MB, tracked in Git). The thermal model needs **PyTorch**: `01_setup.sh` installs the **CPU-only** build from PyTorch's own index, because the PyPI aarch64 wheel pulls several GB of NVIDIA CUDA libraries a Pi cannot use.

## Steps (run on the dev PC unless stated)

```bash
PI=unibackvnavpi@raspberrypi          # your Pi login

# 0. On the Pi: read-only inspection. Save the output, you will compare it afterwards.
ssh $PI 'bash -s' < deploy/pi/00_preflight.sh | tee pi_before.txt

# 1. Source package into a NEW folder (fails if it exists, so nothing is overwritten)
tar --force-local --exclude=__pycache__ --exclude=backend/.venv --exclude=backend/logs --exclude=backend/idealab.db \
    -czf - backend frontend/dist models data/manifests deploy ml scripts .gitattributes \
  | ssh $PI 'test ! -e ~/mmhm-demo && mkdir ~/mmhm-demo && tar -xzf - -C ~/mmhm-demo'

# 2. Minimal demo data (existing files are kept, never replaced)
tar --force-local -cf - -T deploy/pi/demo_data_minimal.txt \
  | ssh $PI 'mkdir -p ~/mmhm-demo && tar -xf - -C ~/mmhm-demo --keep-old-files'

# 3. On the Pi, once: venv + packages inside the project folder, then proof that the models load
ssh $PI 'cd ~/mmhm-demo && bash deploy/pi/01_setup.sh'

# 4. cloudflared. If not installed, put the arm64 binary INSIDE the project (no system change):
#    https://github.com/cloudflare/cloudflared/releases  ->  ~/mmhm-demo/.run/bin/cloudflared  (chmod +x)

# 5. Benchmark before the audience does (playback and analysis time are reported separately)
ssh $PI 'cd ~/mmhm-demo && (bash deploy/pi/start.sh >/dev/null; backend/.venv/bin/python deploy/pi/benchmark_session.py --base http://127.0.0.1:$(cat .run/port) --video hydraulic --seconds 90)'
```

## Before the presentation / afterwards

```bash
ssh $PI 'cd ~/mmhm-demo && bash deploy/pi/start.sh'    # prints the public URL (changes every start)
ssh $PI 'cd ~/mmhm-demo && bash deploy/pi/status.sh'
ssh $PI 'cd ~/mmhm-demo && bash deploy/pi/stop.sh'     # stops only this project's backend and tunnel
ssh $PI 'bash -s' < deploy/pi/00_preflight.sh > pi_after.txt   # then diff pi_before.txt pi_after.txt
```

## Verification checklist on the public URL

Dashboard loads; `/api/health`; video list; Start a video test, the video plays and **seeks**; telemetry updates
(Output changes, "Updated" time advances); Stop; a second Start; browser console clean; `backend.log` and
`tunnel.log` free of errors; `pi_before.txt` and `pi_after.txt` list the same other services and ports.

## Limitations (read before presenting)

- **No authentication.** Anyone who gets the public URL can open the dashboard and use Start/Stop. Share it only with
  the audience and run `stop.sh` right after.
- **The URL changes** on every tunnel start; a Quick Tunnel has no uptime guarantee.
- **Analysis lags playback.** The browser plays in real time; the backend decodes separately. Measured on the Pi:
  **0.36x** real time (`benchmark_session.py`, 90 s run: 31.7 s of video analysed, 58.8 s behind). A 96 s clip needs about
  270 s to analyse. On the development PC it was 0.60x. The dashboard shows both positions and makes no lockstep claim.
- **Video over the tunnel needs a preview copy.** The Pi serves video at ~595 Mbit/s locally but only ~4.4 Mbit/s reached a
  remote PC through the Quick Tunnel, while the 1080p clips need ~15.6 Mbit/s, so playback stalled. `VIDEO_preview/` holds
  640x360 copies (same duration and frame count, ~2 MB). The browser plays them; the backend still analyses the originals.
  Create more with `ffmpeg -i VIDEO/N.mp4 -an -vf scale=640:-2 -c:v libx264 -preset veryfast -crf 30 -maxrate 1200k -movflags +faststart VIDEO_preview/N.mp4`.
- **Video accuracy has not been measured.** The saved metrics are for held-out still images only. On the clips the
  classifier often gives no confident class, and its classes are induction-motor classes.
- **First acoustic prediction in a new backend process takes ~50 s on the Pi** (library warm-up, off the request path).
- The Pi has all seven videos (each with a `VIDEO_preview/` copy), the full IMS `1st_test` folder (2,156 files), the sound
  clip and the example images, so every dropdown option starts (checked). `demo_data_rest.txt` lists what was added after
  the minimal set. A missing file is reported as "the file is not available on this server", without a server path.
