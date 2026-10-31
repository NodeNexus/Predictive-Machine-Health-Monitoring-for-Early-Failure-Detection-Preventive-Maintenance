"""Benchmark one real demo session and report playback time and analysis time SEPARATELY.

The browser plays the video in real time; the backend decodes the same file on its own and runs inference as fast
as it can. This starts a real session through the API, listens to the real telemetry socket, and measures how far
the backend's analysis has advanced against the wall clock.  Uses only the standard library plus `websockets`
(already installed with the backend).  Example:

    backend/.venv/bin/python deploy/pi/benchmark_session.py --base http://127.0.0.1:18080 --video honda_engine_1 --seconds 90
"""
import argparse
import json
import statistics
import time
import urllib.request

from websockets.sync.client import connect


def call(base, path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if body is not None else "GET"),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="e.g. http://127.0.0.1:18080")
    ap.add_argument("--video", default="honda_engine_1", help="machine_video_id from /api/demo/machine-videos")
    ap.add_argument("--seconds", type=int, default=90)
    a = ap.parse_args()
    base = a.base.rstrip("/")

    video = next((v for v in call(base, "/api/demo/machine-videos") if v["machine_video_id"] == a.video), None)
    if video is None:
        raise SystemExit(f"unknown video id {a.video!r}")
    name = "Benchmark machine (reused)"
    machine = next((m for m in call(base, "/api/machines") if m["machine_name"] == name), None) or call(base, "/api/machines", {"machine_name": name})

    ws_url = base.replace("http", "ws", 1) + "/ws/telemetry"
    samples = []  # (wall seconds since start, analysed position seconds, ml_prediction, ml_confidence)
    with connect(ws_url) as ws:
        t0 = time.perf_counter()
        call(base, "/api/demo/start", {"machine_id": machine["machine_id"], "thermal_source": video["path"], "playback_speed": 1})
        total = None
        try:
            while time.perf_counter() - t0 < a.seconds:
                try:
                    msg = json.loads(ws.recv(timeout=5))
                except TimeoutError:
                    continue
                th, prog = msg.get("thermal"), (msg.get("progress") or {}).get("thermal")
                if th and prog:
                    total = prog["total"]
                    samples.append((time.perf_counter() - t0, prog["position"], th["ml_prediction"], th["ml_confidence"]))
        finally:
            call(base, "/api/demo/stop", {})

    print(f"clip: {video['name']} (clip {video['video_id']}), length {total:.1f} s" if total else "no thermal telemetry received")
    if len(samples) < 4:
        raise SystemExit("too few samples to benchmark (is the model loading slowly or the video unreadable?)")
    first = samples[0]
    half = samples[len(samples) // 2:]
    rate = (half[-1][1] - half[0][1]) / (half[-1][0] - half[0][0])
    classes = sorted({s[2] for s in samples if s[2]})
    conf = [s[3] for s in samples if s[3] is not None]
    print(f"playback (browser)         : real time, {total:.1f} s for the whole clip")
    print(f"time to first thermal result: {first[0]:.1f} s after Start (model load + first frame)")
    print(f"analysis speed (steady)    : {rate:.2f}x real time ({'keeps up with' if rate >= 0.97 else 'LAGS'} playback)")
    print(f"analysed at end of run     : {samples[-1][1]:.1f} s of video after {samples[-1][0]:.1f} s of wall time (lag {samples[-1][0] - samples[-1][1] - 0:.1f} s)")
    if rate > 0:
        print(f"whole clip analysed in     : about {total / rate:.0f} s of wall time at that speed")
    print(f"telemetry messages         : {len(samples)}; confident classes seen: {classes or 'none'}; "
          f"confidence min/median/max: {min(conf):.2f}/{statistics.median(conf):.2f}/{max(conf):.2f}")


if __name__ == "__main__":
    main()
